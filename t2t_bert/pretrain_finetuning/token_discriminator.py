import tensorflow as tf
from utils.bert import bert_utils
from loss import loss_utils
from utils.bert import albert_modules
from metric import tf_metrics


def classifier(config, seq_output,
						input_ids,
						sampled_ids,
						input_mask,
						num_labels,
						dropout_prob,
						**kargs):
	"""
	input_ids: original input ids
	sampled_ids: generated fake ids
	"""
	output_layer = seq_output
	hidden_size = output_layer.shape[-1].value

	unk_mask = tf.cast(tf.math.equal(input_ids, 100), tf.float32) # not replace unk
	cls_mask =  tf.cast(tf.math.equal(input_ids, 101), tf.float32) # not replace cls
	sep_mask = tf.cast(tf.math.equal(input_ids, 102), tf.float32) # not replace sep

	none_replace_mask =  unk_mask + cls_mask + sep_mask

	input_mask = tf.cast(input_mask, tf.int32)
	input_mask *= tf.cast(1 - none_replace_mask, tf.int32) # cls, unk, sep are not considered as replace or original

	output_weights = tf.get_variable(
			"output_weights", [num_labels, hidden_size],
			initializer=tf.truncated_normal_initializer(stddev=0.02))

	output_bias = tf.get_variable(
			"output_bias", [num_labels], initializer=tf.zeros_initializer())

	if config.get('ln_type', 'postln') == 'preln':
		output_layer = albert_modules.layer_norm(output_layer)
		print('====preln transformer====')
	elif config.get('ln_type', 'postln') == 'postln':
		output_layer = output_layer
		print('====postln transformer====')
	else:
		output_layer = output_layer
		print('====no layer layer_norm====')

	output_layer = tf.nn.dropout(output_layer, keep_prob=1 - dropout_prob)

	logits = tf.einsum("abc,dc->abd", output_layer, output_weights)
	logits = tf.nn.bias_add(logits, output_bias) # batch x seq_length x 2

	input_ids = tf.cast(input_ids, tf.int32)
	sampled_ids = tf.cast(sampled_ids, tf.int32)

	# original:0, replace:1
	not_equal_label_ids = tf.cast(tf.not_equal(input_ids, sampled_ids), tf.int32)
	not_equal_label_ids *= tf.cast(input_mask, tf.int32)

	if kargs.get('loss', 'cross_entropy') == 'cross_entropy':
		per_example_loss = tf.nn.sparse_softmax_cross_entropy_with_logits(
													logits=logits,
													labels=tf.stop_gradient(not_equal_label_ids))
	elif kargs.get('loss', 'cross_entropy') == 'focal_loss':
		input_shape_list = bert_utils.get_shape_list(input_ids, expected_rank=2)
		batch_size = input_shape_list[0]
		seq_length = input_shape_list[1]
		not_equal_label_ids_ = tf.reshape(not_equal_label_ids, [batch_size*seq_length])
		logits_ = tf.reshape(logits, [batch_size*seq_length, -1])
		per_example_loss, _ = loss_utils.focal_loss_binary_v2(config, logits_, not_equal_label_ids_)
		per_example_loss = tf.reshape(per_example_loss, [batch_size, seq_length])

	# loss = per_example_loss * tf.cast(input_mask, tf.float32)
	# loss = tf.reduce_sum(loss) / (1e-10 + tf.reduce_sum(tf.cast(input_mask, tf.float32)))

	equal_label_ids = (1 - tf.cast(not_equal_label_ids, tf.float32)) * tf.cast(input_mask, tf.float32)
	equal_loss = tf.reduce_sum(per_example_loss * equal_label_ids)

	equal_loss_output = equal_loss / (1e-10 + tf.reduce_sum(equal_label_ids))

	not_equal_loss = tf.reduce_sum(per_example_loss * tf.cast(not_equal_label_ids, tf.float32)) # not equal:1, equal:0
	not_equal_loss_output = not_equal_loss / (1e-10 + tf.reduce_sum(tf.cast(not_equal_label_ids, tf.float32)))

	loss = (equal_loss + 10*not_equal_loss) / (1e-10 + tf.reduce_sum(tf.cast(input_mask, tf.float32)))

	if kargs.get('summary_debug', False):
		tf.summary.scalar('mask_based_loss', 
							loss)

		tf.summary.scalar('equal_loss', 
							equal_loss/(1e-10 + tf.reduce_sum(tf.cast(input_mask, tf.float32))))

		tf.summary.scalar('not_equal_loss', 
							not_equal_loss/(1e-10 + tf.reduce_sum(tf.cast(input_mask, tf.float32))))

		tf.summary.scalar('loss_decomposition', 
							loss - (equal_loss+not_equal_loss)/(1e-10 + tf.reduce_sum(tf.cast(input_mask, tf.float32))))

	return (loss, logits, per_example_loss)
	
def discriminator_metric_train(per_example_loss, logits, input_ids, sampled_ids,
						input_mask):
	# original:0, replace:1
	discriminator_label_ids = tf.not_equal(
						tf.cast(input_ids, tf.int32),
						tf.cast(sampled_ids, tf.int32)
					)

	unk_mask = tf.cast(tf.math.equal(input_ids, 100), tf.float32) # not replace unk
	cls_mask =  tf.cast(tf.math.equal(input_ids, 101), tf.float32) # not replace cls
	sep_mask = tf.cast(tf.math.equal(input_ids, 102), tf.float32) # not replace sep

	none_replace_mask =  unk_mask + cls_mask + sep_mask

	input_mask = tf.cast(input_mask, tf.int32)
	input_mask *= tf.cast(1 - none_replace_mask, tf.int32) # cls, unk, sep are not considered as replace or original

	discriminator_lm_predictions = tf.argmax(
		logits, axis=-1, output_type=tf.int32)

	discriminator_mean_loss = per_example_loss * tf.cast(input_mask, tf.float32)
	discriminator_mean_loss = tf.reduce_sum(discriminator_mean_loss) / (1e-10 + tf.reduce_sum(tf.cast(input_mask, tf.float32)))

	discriminator_lm_accuracy = tf.equal(
						tf.cast(discriminator_lm_predictions, tf.int32),
						tf.cast(discriminator_label_ids, tf.int32)
					)
	discriminator_lm_accuracy = tf.cast(discriminator_lm_accuracy, tf.float32)
	discriminator_lm_accuracy_original = tf.reduce_sum(discriminator_lm_accuracy * tf.cast(discriminator_label_ids, tf.float32)) / (1e-10 + tf.reduce_sum(tf.cast(input_mask, tf.float32)))
	discriminator_lm_accuracy_diff = tf.reduce_sum(discriminator_lm_accuracy * tf.cast(discriminator_label_ids, tf.float32)) / (1e-10 + tf.reduce_sum(tf.cast(discriminator_label_ids, tf.float32)))
	discriminator_lm_accuracy = tf.reduce_sum(discriminator_lm_accuracy * tf.cast(input_mask, tf.float32)) / (1e-10 + tf.reduce_sum(tf.cast(input_mask, tf.float32)))

	return {
		"discriminator_lm_accuracy": discriminator_lm_accuracy,
		"discriminator_lm_loss": discriminator_mean_loss,
		"discriminator_lm_accuracy_diff":discriminator_lm_accuracy_diff,
		"discriminator_lm_accuracy_original":discriminator_lm_accuracy_original,
		}

def discriminator_metric_eval(per_example_loss, logits, input_ids, sampled_ids,
					input_mask):
	# original:0, replace:1
	discriminator_label_ids = tf.not_equal(
		tf.cast(input_ids, tf.int32),
		tf.cast(sampled_ids, tf.int32)
	)

	unk_mask = tf.cast(tf.math.equal(input_ids, 100), tf.float32) # not replace unk
	cls_mask =  tf.cast(tf.math.equal(input_ids, 101), tf.float32) # not replace cls
	sep_mask = tf.cast(tf.math.equal(input_ids, 102), tf.float32) # not replace sep

	none_replace_mask =  unk_mask + cls_mask + sep_mask

	input_mask = tf.cast(input_mask, tf.int32)
	input_mask *= tf.cast(1 - none_replace_mask, tf.int32) # cls, unk, sep are not considered as replace or original

	discriminator_lm_predictions = tf.argmax(
		logits, axis=-1, output_type=tf.int32)

	discriminator_label_ids = tf.reshape(discriminator_label_ids, [-1])
	discriminator_lm_predictions = tf.reshape(discriminator_lm_predictions, [-1])

	discriminator_mask = tf.reshape(input_mask, [-1])
	discriminator_accuracy = tf.metrics.accuracy(
		labels=discriminator_label_ids,
		predictions=discriminator_lm_predictions,
		weights=discriminator_mask)

	discriminator_per_example_loss = tf.reshape(per_example_loss, [-1])

	discriminator_mean_loss = tf.metrics.mean(
		values=discriminator_per_example_loss, 
		weights=discriminator_mask)

	# discriminator_f1 = tf_metrics.f1(discriminator_label_ids, 
	# 						discriminator_lm_predictions, 
	# 						num_classes=2, 
	# 						weights=discriminator_mask, 
	# 						average="macro")


	return {
		"discriminator_accuracy":discriminator_accuracy,
		"discriminator_loss":discriminator_mean_loss,
		# "discriminator_f1":discriminator_f1
	}

	
