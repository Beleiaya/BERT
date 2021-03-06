import tensorflow as tf
import numpy as np
import re
from utils.bert import bert_utils
try:
	from .trf_gpt_noise import model_fn_builder as noise_dist
	from .trf_ebm_bert import model_fn_builder as ebm_dist
	from .trf_classifier import get_ebm_loss, get_noise_loss, ebm_noise_train_metric, ebm_noise_eval_metric
	from .trf_ebm_noise_mlm_sample import model_fn_builder as mlm_noise_dist
except:
	from trf_gpt_noise import model_fn_builder as noise_dist
	from trf_ebm_bert import model_fn_builder as ebm_dist
	from trf_ebm_noise_mlm_sample import model_fn_builder as mlm_noise_dist
	from trf_classifier import get_ebm_loss, get_noise_loss, ebm_noise_train_metric, ebm_noise_eval_metric

import tensorflow as tf
import numpy as np
from optimizer import optimizer
from optimizer import distributed_optimizer

from model_io import model_io

import tensorflow as tf
from metric import tf_metrics
from collections import OrderedDict

def get_train_op(ebm_dist_dict, noise_dist_dict, optimizer_fn, opt_config,
				ebm_dist_config, noise_dist_config,
				**kargs):
	
	if kargs.get('train_op_type', 'joint') in ['alternate', 'group', 'adaptive_alternate']:

		ebm_loss_ratio = kargs.get('ebm_loss_ratio', 1.0)
		noise_loss_ratio = kargs.get('noise_loss_ratio', 1.0)
		noise_loss = noise_dist_dict['loss']
		ebm_loss = ebm_dist_dict['loss']
		ebm_logz_loss = ebm_dist_dict['logz_loss']

		print(ebm_loss.get_shape(), "==ebm loss type==")
		print(noise_loss.get_shape(), "==noise loss type==")

		tf.logging.info("***** ebm_loss_ratio: %s, noise_loss_ratio: %s *****", 
					str(ebm_loss_ratio), str(noise_loss_ratio))
		
		# maximize parameters of ebm when noise distribution is fixed
		ebm_dist_loss = ebm_loss_ratio * ebm_loss
		# maximize loghilihood of noise distribution itself and minmize the nce loss that noise distribution should be 
		# able to generate more real samples
		noise_dist_loss = noise_loss_ratio * noise_loss
		
		if kargs.get('use_tpu', 0) == 0:
			tf.logging.info("====logging discriminator loss ====")
			tf.summary.scalar('ebm_dist_loss', 
								ebm_loss)
			tf.summary.scalar('noise_dist_loss', 
								noise_loss)
			tf.summary.scalar('ebm_loss_ratio', 
								ebm_loss_ratio)
			tf.summary.scalar('noise_loss_ratio', 
								noise_loss_ratio)

			if kargs.get('use_tpu', 0) == 0:
				optimizer_fn.gradient_norm_summary(ebm_dist_dict['loss'], ebm_dist_dict['tvars'], debug_grad_name="ebm_grad_norm")
				optimizer_fn.gradient_norm_summary(noise_dist_dict['loss'], ebm_dist_dict['tvars'], debug_grad_name="ebm_of_noise_grad_norm")
				optimizer_fn.gradient_norm_summary(noise_dist_dict['loss'], noise_dist_dict['tvars'], debug_grad_name="noise_grad_norm")

		loss_dict = OrderedDict(zip(['ebm', 'noise', 'ebm_logz'], [ebm_dist_loss, noise_dist_loss, ebm_logz_loss]))
		tvars_dict = OrderedDict(zip(['ebm', 'noise', 'ebm_logz'], [ebm_dist_dict['tvars'], noise_dist_dict['tvars'], ebm_dist_dict['logz_tvars']]))
		init_lr_dict = OrderedDict(zip(['ebm', 'noise', 'ebm_logz'], [ebm_dist_config['init_lr'], noise_dist_config['init_lr'], ebm_dist_config.get('logz_init_lr', ebm_dist_config['init_lr'])]))
		optimizer_type_dict = OrderedDict(zip(['ebm', 'noise', 'ebm_logz'], [ebm_dist_config['optimizer_type'], noise_dist_config['optimizer_type'], ebm_dist_config['logz_optimizer_type']]))
		loop_step_dict = OrderedDict(zip(['ebm', 'noise', 'ebm_logz'], [ebm_dist_config.get("steps", 1), noise_dist_config.get('steps', 1), ebm_dist_config.get("logz_steps", 1)]))
		if_grad_clip_dict = OrderedDict(zip(['ebm', 'noise', 'ebm_logz'], [True, True, True]))
		# global_step_dict = OrderedDict(zip(['ebm', 'noise'], [ebm_dist_dict['global_step'], noise_dist_dict['global_step']]))
		print(loss_dict, '===loss dict=====')
		if kargs.get('train_op_type', 'joint') == 'alternate':
			tf.logging.info("***** alternate train op for minmax *****")
			train_op_fn = optimizer_fn.get_alternate_train_op
		elif kargs.get('train_op_type', 'joint') == 'group':
			tf.logging.info("***** joint tr
				ain op for minmax *****")
			train_op_fn = optimizer_fn.get_group_train_op
		# elif kargs.get('train_op_type', 'joint') == 'adaptive_alternate':
		# 	tf.logging.info("***** adaptive alternate train op for minmax *****")
		# 	train_op_fn = optimizer_fn.get_adaptive_alternate_train_op
		else:
			tf.logging.info("***** alternate train op for minmax *****")
			train_op_fn = optimizer_fn.get_alternate_train_op

		update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
		with tf.control_dependencies(update_ops):
			train_op = train_op_fn(loss_dict, 
									tvars_dict, 
									init_lr_dict,
									optimizer_type_dict,
									opt_config.num_train_steps,
									loop_step_dict=loop_step_dict,
									if_grad_clip_dict=if_grad_clip_dict,
									# global_step_dict=global_step_dict,
									postive_key="ebm",
									negative_key="noise",
									alternate_order=['ebm_logz', 'ebm', 'noise'],
									**kargs)

			print("===train op===", train_op)

	return train_op

def ebm_logz_length_cond_loss(config, features, ebm_all_loss, valid_mask=None):
	"""
	we group by length and mean over loss by length
	and apply sgd to optimize logz's parameters just like center-loss for center updating
	"""
	input_mask = features['input_mask']
	shape = bert_utils.get_shape_list(input_mask)
	valid_seq_length = tf.cast(tf.reduce_sum(input_mask, axis=-1), tf.int32) # batch_size
	onehot_length_ids = tf.one_hot(valid_seq_length, config.max_position_embeddings)
	onehot_length_ids = tf.cast(onehot_length_ids, tf.float32)

	if_provided = 1
	if valid_mask is None:
		valid_mask = tf.ones(shape=[shape[0]])
		if_provided = 0
		tf.logging.info("====ones valid mask ====")
	if if_provided == 1:
		tf.logging.info("====provided valid mask ====")

	valid_mask = tf.expand_dims(tf.cast(valid_mask, tf.float32), axis=-1) # batch_size x 1

	length_accumulate_loss = tf.einsum("ab,a->ab", onehot_length_ids, ebm_all_loss)
	length_loss = tf.reduce_sum(length_accumulate_loss*valid_mask, axis=0)

	length_appear_time = tf.reduce_sum(onehot_length_ids*valid_mask, axis=0) + 1

	logz_length_attribute_loss = length_loss / length_appear_time # 1 x max_position_embeddings
	logz_length_loss = tf.reduce_sum(logz_length_attribute_loss)
	return logz_length_loss

def token_seq_truncted(token_seq, finished_index, max_length): 
	seq_shape = bert_utils.get_shape_list(token_seq, expected_rank=[2,3])
	batch_size = seq_shape[0]
	token_seq = token_seq[:, :max_length]

	token_seq = tf.concat([token_seq, finished_index*tf.cast(tf.ones((batch_size, 1)), tf.int32)], axis=-1)

	token_seq = tf.cast(token_seq, tf.int32)
	seq_shape = bert_utils.get_shape_list(token_seq, expected_rank=[2,3])
	match_indices = tf.where(                          # [[5, 5, 2, 5, 4],
	tf.equal(finished_index, token_seq),                              #  [0, 5, 2, 3, 5],
		x=tf.range(seq_shape[1]) * tf.ones_like(token_seq),  #  [5, 1, 5, 5, 5]]
		y=(seq_shape[1])*tf.ones_like(token_seq))

	finished_pos = tf.reduce_min(match_indices, axis=1)				
	sequence_mask = tf.sequence_mask(finished_pos+1, maxlen=seq_shape[1])

	token_seq = tf.cast(sequence_mask, tf.float32) * tf.cast(token_seq, tf.float32)
				
	return tf.cast(token_seq, tf.int32)

def mixed_sample(features, mix_ratio=0.2):
	shape = bert_utils.get_shape_list(features['input_mask'], expected_rank=[2,3])
	sample_probs = tf.ones((shape[0]))
	sample_probs = mix_ratio * tf.cast(sample_probs, tf.float32) #+ 0.8 * tf.cast(must_have_one, tf.float32) # mask 15% token

	noise_dist = tf.distributions.Bernoulli(probs=sample_probs, dtype=tf.float32)
	mixed_mask = noise_dist.sample()
	mixed_mask = tf.cast(mixed_mask, tf.float32)
	return mixed_mask

def classifier_model_fn_builder(
						model_config_dict,
						num_labels_dict,
						init_checkpoint_dict,
						load_pretrained_dict,
						model_io_config={},
						opt_config={},
						exclude_scope_dict={},
						not_storage_params_dict={},
						target_dict={},
						**kargs):
	
	def model_fn(features, labels, mode, params):

		train_op_type = kargs.get('train_op_type', 'joint')
		print("==input shape==", features["input_ids"].get_shape())

		ebm_dist_fn = ebm_dist(model_config_dict['ebm_dist'],
					num_labels_dict['ebm_dist'],
					init_checkpoint_dict['ebm_dist'],
					model_reuse=None,
					load_pretrained=load_pretrained_dict['ebm_dist'],
					model_io_config=model_io_config,
					opt_config=opt_config,
					exclude_scope=exclude_scope_dict.get('ebm_dist', ""),
					not_storage_params=not_storage_params_dict.get('ebm_dist', []),
					target=target_dict['ebm_dist'],
					prob_ln=False,
					transform=False,
					transformer_activation="linear",
					logz_mode='standard',
					normalized_constant="length_linear",
					energy_pooling="mi",
					softplus_features=False,
					**kargs)

		noise_prob_ln = False
		noise_sample = kargs.get("noise_sample", 'mlm')

		if kargs.get("noise_sample", 'mlm') == 'gpt':
			tf.logging.info("****** using gpt for noise dist sample *******")
			sample_noise_dist = True
		elif kargs.get("noise_sample", 'mlm') == 'mlm':
			tf.logging.info("****** using bert mlm for noise dist sample *******")
			sample_noise_dist = False
		else:
			tf.logging.info("****** using gpt for noise dist sample *******")
			sample_noise_dist = True

		noise_dist_fn = noise_dist(model_config_dict['noise_dist'],
					num_labels_dict['noise_dist'],
					init_checkpoint_dict['noise_dist'],
					model_reuse=None,
					load_pretrained=load_pretrained_dict['noise_dist'],
					model_io_config=model_io_config,
					opt_config=opt_config,
					exclude_scope=exclude_scope_dict.get('noise_dist', ""),
					not_storage_params=not_storage_params_dict.get('noise_dist', []),
					target=target_dict['noise_dist'],
					noise_true_distribution=True,
					sample_noise_dist=sample_noise_dist,
					noise_estimator_type=kargs.get("noise_estimator_type", "stop_gradient"),
					prob_ln=noise_prob_ln,
					if_bp=True,
					**kargs)

		if not sample_noise_dist:
			tf.logging.info("****** using bert mlm for noise dist sample *******")

			global_step = tf.train.get_or_create_global_step()
			noise_sample_ratio = tf.train.polynomial_decay(
													0.20,
													global_step,
													opt_config.num_train_steps,
													end_learning_rate=0.1,
													power=1.0,
													cycle=False)

			mlm_noise_dist_fn = mlm_noise_dist(model_config_dict['generator'],
						num_labels_dict['generator'],
						init_checkpoint_dict['generator'],
						model_reuse=None,
						load_pretrained=load_pretrained_dict['generator'],
						model_io_config=model_io_config,
						opt_config=opt_config,
						exclude_scope=exclude_scope_dict.get('generator', ""),
						not_storage_params=not_storage_params_dict.get('generator', []),
						target=target_dict['generator'],
						mask_probability=noise_sample_ratio,
						replace_probability=0.2,
						original_probability=0.0,
						**kargs)
		else:
			mlm_noise_dist_fn = None

		true_features = {}

		for key in features:
			if key == 'input_ori_ids':
				true_features["input_ids"] = tf.cast(features['input_ori_ids'], tf.int32)
			if key in ['input_mask', 'segment_ids']:
				true_features[key] = tf.cast(features[key], tf.int32)

		if kargs.get("dnce", False):

			if kargs.get("anneal_dnce", False):
				global_step = tf.train.get_or_create_global_step()
				noise_sample_ratio = tf.train.polynomial_decay(
														0.10,
														global_step,
														opt_config.num_train_steps,
														end_learning_rate=0.05,
														power=1.0,
														cycle=False)
				tf.logging.info("****** anneal dnce mix ratio *******")
			else:
				noise_sample_ratio = 0.10
				tf.logging.info("****** not anneal dnce mix ratio *******")

			mlm_noise_noise_dist_fn = mlm_noise_dist(model_config_dict['generator'],
						num_labels_dict['generator'],
						init_checkpoint_dict['generator'],
						model_reuse=None,
						load_pretrained=load_pretrained_dict['generator'],
						model_io_config=model_io_config,
						opt_config=opt_config,
						exclude_scope=exclude_scope_dict.get('generator', ""),
						not_storage_params=not_storage_params_dict.get('generator', []),
						target=target_dict['generator'],
						mask_probability=noise_sample_ratio,
						replace_probability=0.0,
						original_probability=0.0,
						**kargs)

			mlm_noise_dist_dict_noise = mlm_noise_noise_dist_fn(features, labels, mode, params)

			mixed_mask = mixed_sample(features, mix_ratio=noise_sample_ratio)
			tf.logging.info("****** apply dnce *******")
			mixed_mask = tf.expand_dims(mixed_mask, axis=-1) # batch_size x 1
			mixed_mask = tf.cast(mixed_mask, tf.int32)
			true_features["input_ids"] = (1-mixed_mask)*true_features["input_ids"] + mixed_mask * mlm_noise_dist_dict_noise['sampled_ids']

		if not sample_noise_dist:
			mlm_noise_dist_dict = mlm_noise_dist_fn(features, labels, mode, params)
		else:
			mlm_noise_dist_dict = {}

		# first get noise dict
		noise_dist_dict = noise_dist_fn(true_features, labels, mode, params)

		# third, get fake ebm dict
		fake_features = {}

		if noise_sample == 'gpt':
			if kargs.get("training_mode", "stop_gradient") == 'stop_gradient':
				fake_features["input_ids"] = noise_dist_dict['fake_samples']
				tf.logging.info("****** using samples stop gradient *******")
			elif kargs.get("training_mode", "stop_gradient") == 'adv_gumbel':
				fake_features["input_ids"] = noise_dist_dict['gumbel_probs']
				tf.logging.info("****** using samples with gradient *******")
			fake_features['input_mask'] = tf.cast(noise_dist_dict['fake_mask'], tf.int32)
			fake_features['segment_ids'] = tf.zeros_like(fake_features['input_mask'])
		elif noise_sample == 'mlm':
			fake_features["input_ids"] = mlm_noise_dist_dict['sampled_ids']
			fake_features['input_mask'] = tf.cast(features['input_mask'], tf.int32)
			fake_features['segment_ids'] = tf.zeros_like(features['input_mask'])
			tf.logging.info("****** using bert mlm stop gradient *******")

		# second, get true ebm dict
		true_ebm_dist_dict = ebm_dist_fn(true_features, labels, mode, params)
		fake_ebm_dist_dict = ebm_dist_fn(fake_features, labels, mode, params)
		if not sample_noise_dist:
			fake_noise_dist_dict = noise_dist_fn(fake_features, labels, mode, params)
			noise_dist_dict['fake_logits'] = fake_noise_dist_dict['true_logits']

		[ebm_loss, 
		ebm_all_true_loss,
		ebm_all_fake_loss] = get_ebm_loss(true_ebm_dist_dict['logits'], 
								noise_dist_dict['true_logits'], 
								fake_ebm_dist_dict['logits'], 
								noise_dist_dict['fake_logits'], 
								use_tpu=kargs.get('use_tpu', False),
								valid_mask=mlm_noise_dist_dict.get("valid_mask", None))

		logz_length_true_loss = ebm_logz_length_cond_loss(model_config_dict['ebm_dist'],
															true_features,
															ebm_all_true_loss,
															valid_mask=mlm_noise_dist_dict.get("valid_mask", None))

		logz_length_fake_loss = ebm_logz_length_cond_loss(model_config_dict['ebm_dist'],
															fake_features,
															ebm_all_fake_loss,
															valid_mask=mlm_noise_dist_dict.get("valid_mask", None))
		true_ebm_dist_dict['logz_loss'] = logz_length_true_loss + logz_length_fake_loss

		noise_loss = get_noise_loss(true_ebm_dist_dict['logits'], 
									noise_dist_dict['true_logits'], 
									fake_ebm_dist_dict['logits'], 
									noise_dist_dict['fake_logits'], 
									noise_loss_type=kargs.get('noise_loss_type', 'jsd_noise'),
									num_train_steps=opt_config.num_train_steps,
									num_warmup_steps=opt_config.num_warmup_steps,
									use_tpu=kargs.get('use_tpu', False),
									loss_mask=features['input_mask'],
									prob_ln=noise_prob_ln)

		model_io_fn = model_io.ModelIO(model_io_config)

		tvars = []
		loss = ebm_loss
		tvars.extend(true_ebm_dist_dict['tvars'])

		if kargs.get('joint_train', '1') == '1':
			tf.logging.info("****** joint generator and discriminator training *******")
			tvars.extend(noise_dist_dict['tvars'])
			loss += noise_loss
		tvars = list(set(tvars))

		ebm_opt_dict = {
			"loss":ebm_loss,
			"tvars":true_ebm_dist_dict['tvars'],
			"logz_tvars":true_ebm_dist_dict['logz_tvars'],
			"logz_loss":true_ebm_dist_dict['logz_loss']
		}

		noise_opt_dict = {
			"loss":noise_loss,
			"tvars":noise_dist_dict['tvars']
		}

		var_checkpoint_dict_list = []
		for key in init_checkpoint_dict:
			if load_pretrained_dict[key] == "yes":
				if key == 'ebm_dist':
					tmp = {
							"tvars":ebm_opt_dict['tvars']+ebm_opt_dict['logz_tvars'],
							"init_checkpoint":init_checkpoint_dict['ebm_dist'],
							"exclude_scope":exclude_scope_dict[key],
							"restore_var_name":model_config_dict['ebm_dist'].get('restore_var_name', [])
					}
					if kargs.get("sharing_mode", "none") != "none":
						tmp['exclude_scope'] = ''
					var_checkpoint_dict_list.append(tmp)
				elif key == 'noise_dist':
					tmp = {
							"tvars":noise_opt_dict['tvars'],
							"init_checkpoint":init_checkpoint_dict['noise_dist'],
							"exclude_scope":exclude_scope_dict[key],
							"restore_var_name":model_config_dict['noise_dist'].get('restore_var_name', [])
					}
					var_checkpoint_dict_list.append(tmp)
				elif key == 'generator':
					if not sample_noise_dist:
						tmp = {
								"tvars":mlm_noise_dist_dict['tvars'],
								"init_checkpoint":init_checkpoint_dict['generator'],
								"exclude_scope":exclude_scope_dict[key],
								"restore_var_name":model_config_dict['generator'].get('restore_var_name', [])
						}
						if kargs.get("sharing_mode", "none") != "none":
							tmp['exclude_scope'] = ''
						var_checkpoint_dict_list.append(tmp)

		use_tpu = 1 if kargs.get('use_tpu', False) else 0
			
		if len(var_checkpoint_dict_list) >= 1:
			scaffold_fn = model_io_fn.load_multi_pretrained(
											var_checkpoint_dict_list,
											use_tpu=use_tpu)
		else:
			scaffold_fn = None

		if mode == tf.estimator.ModeKeys.TRAIN:

			metric_dict = ebm_noise_train_metric(
										true_ebm_dist_dict['logits'], 
										noise_dist_dict['true_logits'], 
										fake_ebm_dist_dict['logits'], 
										noise_dist_dict['fake_logits'],
										features['input_ori_ids'],
										tf.cast(features['input_mask'], tf.float32),
										noise_dist_dict["true_seq_logits"],
										prob_ln=noise_prob_ln,
										)

			if not kargs.get('use_tpu', False):
				for key in metric_dict:
					tf.summary.scalar(key, metric_dict[key])
				tf.summary.scalar("ebm_loss", ebm_opt_dict['loss'])
				tf.summary.scalar("noise_loss", noise_opt_dict['loss'])
	
			if kargs.get('use_tpu', False):
				optimizer_fn = optimizer.Optimizer(opt_config)
				use_tpu = 1
			else:
				optimizer_fn = distributed_optimizer.Optimizer(opt_config)
				use_tpu = 0

			model_io_fn.print_params(tvars, string=", trainable params")

			train_op = get_train_op(ebm_opt_dict, noise_opt_dict, 
								optimizer_fn, opt_config,
								model_config_dict['ebm_dist'], 
								model_config_dict['noise_dist'],
								use_tpu=use_tpu, 
								train_op_type=train_op_type,
								fce_acc=metric_dict['all_accuracy'])
			
			# update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
			# with tf.control_dependencies(update_ops):
			# 	train_op = optimizer_fn.get_train_op(loss, list(set(tvars)),
			# 					opt_config.init_lr, 
			# 					opt_config.num_train_steps,
			# 					use_tpu=use_tpu)

			if kargs.get('use_tpu', False):
				estimator_spec = tf.contrib.tpu.TPUEstimatorSpec(
								mode=mode,
								loss=loss,
								train_op=train_op,
								scaffold_fn=scaffold_fn)
			else:
				estimator_spec = tf.estimator.EstimatorSpec(
								mode=mode, 
								loss=loss, 
								train_op=train_op)

			return estimator_spec

		elif mode == tf.estimator.ModeKeys.EVAL:

			tpu_eval_metrics = (ebm_noise_eval_metric, 
								[
								true_ebm_dist_dict['logits'], 
								noise_dist_dict['true_logits'], 
								fake_ebm_dist_dict['logits'], 
								noise_dist_dict['fake_logits'],
								features['input_ori_ids'],
								tf.cast(features['input_mask'], tf.float32),
								noise_dist_dict["true_seq_logits"]
								])
			gpu_eval_metrics = ebm_noise_eval_metric(
								true_ebm_dist_dict['logits'], 
								noise_dist_dict['true_logits'], 
								fake_ebm_dist_dict['logits'], 
								noise_dist_dict['fake_logits'],
								features['input_ori_ids'],
								tf.cast(features['input_mask'], tf.float32),
								noise_dist_dict["true_seq_logits"]
								)

			if kargs.get('use_tpu', False):
				estimator_spec = tf.contrib.tpu.TPUEstimatorSpec(
							  mode=mode,
							  loss=loss,
							  eval_metrics=tpu_eval_metrics,
							  scaffold_fn=scaffold_fn)
			else:
				estimator_spec = tf.estimator.EstimatorSpec(mode=mode, 
								loss=loss,
								eval_metric_ops=gpu_eval_metrics)

			return estimator_spec
		else:
			raise NotImplementedError()

	return model_fn


