import tensorflow as tf
import numpy as np
from distillation.distillation_utils import logits_distillation, feature_distillation
from distillation.mmd_utils import margin_disparity_discrepancy

class KnowledgeDistillation(object):
	def __init__(self, config={}):
		self.config = config
		self.global_step = tf.train.get_or_create_global_step()

	def _ratio_decay(self, init_ratio, ratio_decay, decay_rate, num_train_steps):
		if ratio_decay == "polynomial_decay":
			ratio_rate = tf.train.polynomial_decay(
													init_ratio,
													self.global_step,
													num_train_steps,
													end_learning_rate=0.0,
													power=1.0,
													cycle=False)
		elif ratio_decay == "cosine_decay":
			ratio_rate = tf.train.cosin_decay(
												init_ratio,
												self.global_step,
												num_train_steps,
												alpha=0.0,
												cycle=False)
		elif ratio_decay == "exponential_decay":
			ratio_rate = tf.train.exponential_decay(
													init_ratio,
													self.global_step,
													num_train_steps,
													decay_rate=decay_rate,
													staircase=False)
		elif ratio_decay == "natural_exp_decay":
			ratio_rate = tf.train.natural_exp_decay(
													init_ratio,
													self.global_step,
													num_train_steps,
													decay_rate=decay_rate,
													staircase=False)
		else:
			ratio_rate = init_ratio
		return ratio_rate

	def distillation(self, features,
					num_labels, dropout_prob, model_reuse,
					num_train_steps, **kargs):

		output_dict = {
			"distillation_loss":0.0,
			"distillation_logits_loss":0.0,
			"distillation_feature_loss":0.0,
			"st_logits":None,
			"te_logits":None,
			"mdd_loss":0.0,
			"src_f1_logits":None,
			"tgt_f1_logits":None
		}

		for distillation_type in self.config.get("distillation", ["logits", "feature"]):

			if distillation_type == "logits":
				student_tensor = features["student_logits_tensor"]
				teacher_tensor = features["teacher_logits_tensor"]
				distillation_loss = logits_distillation(student_tensor, 
											teacher_tensor, 
											self.config.get("kd_type", "kd"))
				distillation_logits_loss = tf.reduce_sum(distillation_loss) / (1e-10+tf.reduce_sum(features["distillation_ratio"]))
				distillation_logits_loss *= self._ratio_decay(kargs.get("logits_ratio", 0.5),
														kargs.get("logits_ratio_decay", "constant"),
														 kargs.get("logits_decay_rate", 0.999),
														num_train_steps)
				output_dict["distillation_loss"] += distillation_logits_loss
				output_dict["distillation_logits_loss"] = distillation_logits_loss

			elif distillation_type == "feature":
				student_tensor = features["student_feature_tensor"]
				teacher_tensor = features["teacher_feature_tensor"]
				student_label = features["student_label"]
				teacher_label = features["teacher_label"]
				print(teacher_tensor.get_shape(), "==teacher feature shape==")
				with tf.variable_scope(self.config.get("scope", "bert")+"/dann_distillation", reuse=model_reuse):
					student_tensor = tf.layers.dense(student_tensor,
														student_tensor.get_shape()[-1],
														activation=tf.nn.tanh,
														name="shared_encoder")
					[student_loss, 
					student_example_loss, 
					student_logits] = feature_distillation(student_tensor, 1.0, 
													student_label, num_labels,
													dropout_prob,
													if_gradient_flip=True)

					tf.get_variable_scope().reuse_variables()

					teacher_tensor = tf.layers.dense(teacher_tensor,
														teacher_tensor.get_shape()[-1],
														activation=tf.nn.tanh,
														name="shared_encoder")

					[teacher_loss, 
					teacher_example_loss, 
					teacher_logits] = feature_distillation(teacher_tensor, 1.0, 
													teacher_label, num_labels,
													dropout_prob,
													if_gradient_flip=True)

					distillation_feature_loss = (student_loss + teacher_loss) * self._ratio_decay(
														kargs.get("feature_ratio", 0.5),
														kargs.get("feature_ratio_decay", "constant"),
														 kargs.get("feature_decay_rate", 0.999),
														num_train_steps)
					output_dict["distillation_loss"] += distillation_feature_loss / 2.0
					output_dict["distillation_feature_loss"] = distillation_feature_loss
					output_dict["st_logits"] = student_logits
					output_dict["te_logits"] = teacher_logits
			elif distillation_type == "mdd":
				src_f_logit = features["src_f_logit"]
				src_tensor = features["src_tensor"]
				tgt_f_logit = features['tgt_f_logit']
				tgt_tensor = features['tgt_tensor']
				[mdd_loss, 
				src_f1_logits, 
				tgt_f1_logits] = margin_disparity_discrepancy(src_f_logit,
															src_tensor,
															tgt_f_logit, tgt_tensor,
															model_reuse,
															**kargs)
				output_dict["mdd_loss"] = mdd_loss
				output_dict["distillation_loss"] += kargs.get("mdd_ratio", 0.1) * mdd_loss
				output_dict["src_f1_logits"] = src_f1_logits
				output_dict["tgt_f1_logits"] = tgt_f1_logits

		return output_dict













