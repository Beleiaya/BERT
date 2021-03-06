# -*- coding: utf-8 -*-
import tensorflow as tf

from optimizer import distributed_optimizer as optimizer
from data_generator import distributed_tf_data_utils as tf_data_utils

# try:
# 	from .bert_model_fn import model_fn_builder
# 	from .bert_model_fn import rule_model_fn_builder
# except:
# 	from bert_model_fn import model_fn_builder
# 	from bert_model_fn import rule_model_fn_builder

try:
	# from .model_fn import model_fn_builder
	from .model_interface import model_config_parser
	from .model_data_interface import data_interface
	from .model_fn_interface import model_fn_interface
	# from .model_distillation_fn import model_fn_builder as model_distillation_fn
except:
	# from model_fn import model_fn_builder
	from model_interface import model_config_parser
	from model_data_interface import data_interface
	# from model_distillation_fn import model_fn_builder as model_distillation_fn
	from model_fn_interface import model_fn_interface

import numpy as np
import tensorflow as tf
from bunch import Bunch
from model_io import model_io
import json, os

from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report

try:
	import paisoar as pai
except Exception as e:
	pai = None

try:
	import horovod.tensorflow as hvd
except Exception as e:
	hvd = None

try:
	import _pickle as pkl
except Exception as e:
	pkl = None

import time

def train_eval_fn(FLAGS,
				worker_count, 
				task_index, 
				is_chief, 
				target,
				init_checkpoint,
				train_file,
				dev_file,
				checkpoint_dir,
				is_debug,
				**kargs):

	graph = tf.Graph()
	with graph.as_default():
		import json
				
		# config = json.load(open(FLAGS.config_file, "r"))

		# config = Bunch(config)
		# config.use_one_hot_embeddings = True
		# config.scope = "bert"
		# config.dropout_prob = 0.1
		# config.label_type = "single_label"

		# config.model = FLAGS.model_type

		config = model_config_parser(FLAGS)

		# print(config, "==model config==")
		
		if FLAGS.if_shard == "0":
			train_size = FLAGS.train_size
			epoch = int(FLAGS.epoch / worker_count)
		elif FLAGS.if_shard == "1":
			train_size = int(FLAGS.train_size/worker_count)
			epoch = FLAGS.epoch
		else:
			train_size = int(FLAGS.train_size/worker_count)
			epoch = FLAGS.epoch

		init_lr = config.init_lr

		label_dict = json.load(tf.gfile.Open(FLAGS.label_id))

		num_train_steps = int(
			train_size / FLAGS.batch_size * epoch)
		num_warmup_steps = int(num_train_steps * 0.1)

		num_storage_steps = int(train_size / FLAGS.batch_size)

		num_eval_steps = int(FLAGS.eval_size / FLAGS.batch_size)

		if is_debug == "0":
			num_storage_steps = 190
			num_eval_steps = 100
			num_train_steps = 200
		print("num_train_steps {}, num_eval_steps {}, num_storage_steps {}".format(num_train_steps, num_eval_steps, num_storage_steps))

		print(" model type {}".format(FLAGS.model_type))

		print(num_train_steps, num_warmup_steps, "=============")
		
		opt_config = Bunch({"init_lr":init_lr/worker_count, 
							"num_train_steps":num_train_steps,
							"num_warmup_steps":num_warmup_steps,
							"worker_count":worker_count,
							"opt_type":FLAGS.opt_type,
							"is_chief":is_chief,
							"train_op":kargs.get("train_op", "adam"),
							"decay":kargs.get("decay", "no"),
							"warmup":kargs.get("warmup", "no"),
							"grad_clip":config.get("grad_clip", "global_norm"),
							"clip_norm":config.get("clip_norm", 1.0),
							"epoch":FLAGS.epoch})

		anneal_config = Bunch({
					"initial_value":1.0,
					"num_train_steps":num_train_steps
			})

		model_io_config = Bunch({"fix_lm":False})
		
		num_classes = FLAGS.num_classes

		if FLAGS.opt_type == "hvd" and hvd:
			checkpoint_dir = checkpoint_dir if task_index == 0 else None
		else:
			checkpoint_dir = checkpoint_dir
		print("==checkpoint_dir==", checkpoint_dir, is_chief)

		# if kargs.get("rule_model", "rule"):
		# 	model_fn_interface = rule_model_fn_builder
		# 	print("==apply rule model==")
		# else:
		# 	model_fn_interface = model_fn_builder
		# 	print("==apply normal model==")

		model_fn_builder = model_fn_interface(FLAGS)

		model_train_fn = model_fn_builder(config, num_classes, init_checkpoint, 
												model_reuse=None, 
												load_pretrained=FLAGS.load_pretrained,
												opt_config=opt_config,
												model_io_config=model_io_config,
												exclude_scope=FLAGS.exclude_scope,
												not_storage_params=[],
												target=kargs.get("input_target", ""),
												output_type="sess",
												checkpoint_dir=checkpoint_dir,
												num_storage_steps=num_storage_steps,
												task_index=task_index,
												anneal_config=anneal_config,
												**kargs)
		
		model_eval_fn = model_fn_builder(config, num_classes, init_checkpoint, 
												model_reuse=True, 
												load_pretrained=FLAGS.load_pretrained,
												opt_config=opt_config,
												model_io_config=model_io_config,
												exclude_scope=FLAGS.exclude_scope,
												not_storage_params=[],
												target=kargs.get("input_target", ""),
												output_type="sess",
												checkpoint_dir=checkpoint_dir,
												num_storage_steps=num_storage_steps,
												task_index=task_index,
												anneal_config=anneal_config,
												**kargs)

		print("==succeeded in building model==")
		
		def eval_metric_fn(features, eval_op_dict):
			logits = eval_op_dict["logits"]
			print(logits.get_shape(), "===logits shape===")
			pred_label = tf.argmax(logits, axis=-1, output_type=tf.int32)
			prob = tf.nn.softmax(logits)
			accuracy = correct = tf.equal(
				tf.cast(pred_label, tf.int32),
				tf.cast(features["label_ids"], tf.int32)
			)
			accuracy = tf.reduce_mean(tf.cast(correct, tf.float32))

			return {"accuracy":accuracy, "loss":eval_op_dict["loss"], 
					"pred_label":pred_label, "label_ids":features["label_ids"]}

		def train_metric_fn(features, train_op_dict):
			logits = train_op_dict["logits"]
			print(logits.get_shape(), "===logits shape===")
			pred_label = tf.argmax(logits, axis=-1, output_type=tf.int32)
			prob = tf.nn.softmax(logits)
			accuracy = correct = tf.equal(
				tf.cast(pred_label, tf.int32),
				tf.cast(features["label_ids"], tf.int32)
			)
			accuracy = tf.reduce_mean(tf.cast(correct, tf.float32))
			train_op_dict["accuracy"] = accuracy
			# train_op_dict.pop("logits")
			# return {"accuracy":accuracy, "loss":train_op_dict["loss"], 
			# 		"train_op":train_op_dict["train_op"]}
			return train_op_dict
		
		# name_to_features = {
		# 		"input_ids":
		# 				tf.FixedLenFeature([FLAGS.max_length], tf.int64),
		# 		"input_mask":
		# 				tf.FixedLenFeature([FLAGS.max_length], tf.int64),
		# 		"segment_ids":
		# 				tf.FixedLenFeature([FLAGS.max_length], tf.int64),
		# 		"label_ids":
		# 				tf.FixedLenFeature([], tf.int64),
		# }

		name_to_features = data_interface(FLAGS)

		def _decode_record(record, name_to_features):
			"""Decodes a record to a TensorFlow example.
			"""
			example = tf.parse_single_example(record, name_to_features)

			# tf.Example only supports tf.int64, but the TPU only supports tf.int32.
			# So cast all int64 to int32.
			for name in list(example.keys()):
				t = example[name]
				if t.dtype == tf.int64:
					t = tf.to_int32(t)
				example[name] = t

			return example

		def _decode_batch_record(record, name_to_features):
			example = tf.parse_example(record, name_to_features)
			# for name in list(example.keys()):
			# 	t = example[name]
			# 	if t.dtype == tf.int64:
			# 		t = tf.to_int32(t)
			# 	example[name] = t

			return example

		params = Bunch({})
		params.epoch = epoch
		params.batch_size = FLAGS.batch_size

		print("==train_file==", train_file, params)

		if kargs.get("parse_type", "parse_single") == "parse_single":
			train_features = tf_data_utils.train_input_fn(train_file,
										_decode_record, name_to_features, params, if_shard=FLAGS.if_shard,
										worker_count=worker_count,
										task_index=task_index)

			eval_features = tf_data_utils.eval_input_fn(dev_file,
										_decode_record, name_to_features, params, if_shard=FLAGS.if_shard,
										worker_count=worker_count,
										task_index=task_index)
		elif kargs.get("parse_type", "parse_single") == "parse_batch":
			train_features = tf_data_utils.train_batch_input_fn(train_file,
										_decode_batch_record, name_to_features, params, if_shard=FLAGS.if_shard,
										worker_count=worker_count,
										task_index=task_index)

			eval_features = tf_data_utils.eval_batch_input_fn(dev_file,
										_decode_batch_record, name_to_features, params, if_shard=FLAGS.if_shard,
										worker_count=worker_count,
										task_index=task_index)

		train_op_dict = model_train_fn(train_features, [], tf.estimator.ModeKeys.TRAIN)
		eval_op_dict = model_eval_fn(eval_features, [], tf.estimator.ModeKeys.EVAL)
		eval_dict = eval_metric_fn(eval_features, eval_op_dict["eval"])
		train_dict = train_metric_fn(train_features, train_op_dict["train"])

		print("==succeeded in building data and model==")

		print(train_op_dict)
		
		def eval_fn(eval_dict, sess):
			i = 0
			total_accuracy = 0
			eval_total_dict = {}
			while True:
				try:
					eval_result = sess.run(eval_dict)
					for key in eval_result:
						if key not in eval_total_dict:
							if key in ["pred_label", "label_ids"]:
								eval_total_dict[key] = []
								eval_total_dict[key].extend(eval_result[key])
							if key in ["accuracy", "loss"]:
								eval_total_dict[key] = 0.0
								eval_total_dict[key] += eval_result[key]
						else:
							if key in ["pred_label", "label_ids"]:
								eval_total_dict[key].extend(eval_result[key])
							if key in ["accuracy", "loss"]:
								eval_total_dict[key] += eval_result[key]

					i += 1
					if np.mod(i, num_eval_steps) == 0:
						break
				except tf.errors.OutOfRangeError:
					print("End of dataset")
					break

			label_id = eval_total_dict["label_ids"]
			pred_label = eval_total_dict["pred_label"]

			label_dict_id = sorted(list(label_dict["id2label"].keys()))

			print(len(label_id), len(pred_label), len(set(label_id)))

			accuracy = accuracy_score(label_id, pred_label)
			print("==accuracy==", accuracy)
			if len(label_dict["id2label"]) < 10:
				result = classification_report(label_id, pred_label, 
										target_names=[label_dict["id2label"][key] for key in label_dict_id],
										digits=4)
				print(result, task_index)
				eval_total_dict["classification_report"] = result
				print("==classification report==")
			return eval_total_dict

		def train_fn(train_op_dict, sess):
			i = 0
			cnt = 0
			loss_dict = {}
			monitoring_train = []
			monitoring_eval = []
			while True:
				try:
					[train_result] = sess.run([train_op_dict])
					for key in train_result:
						if key == "train_op":
							continue
						else:
							try:
								if np.isnan(train_result[key]):
									print(train_loss, "get nan loss")
									break
								else:
									if key in loss_dict:
										loss_dict[key] += train_result[key]
									else:
										loss_dict[key] = train_result[key]
							except:
								# if key == "student_logit":
								# 	print(train_result[key])

								continue
					# print(pkl, "==pkl==")

					# if pkl:
					# 	pkl.dump(train_result, open("/data/xuht/distillation.pkl", "wb"))
					
					i += 1
					cnt += 1
					
					if np.mod(i, num_storage_steps) == 0:
						string = ""
						for key in loss_dict:
							tmp = key + " " + str(loss_dict[key]/cnt) + "\t"
							string += tmp
						print(string)
						monitoring_train.append(loss_dict)

						eval_finial_dict = eval_fn(eval_dict, sess)
						monitoring_eval.append(eval_finial_dict)

						for key in loss_dict:
							loss_dict[key] = 0.0
						cnt = 0

					if is_debug == "0":
						if i == num_train_steps:
							break

				except tf.errors.OutOfRangeError:
					print("==Succeeded in training model==")
					break
			return {"eval":monitoring_eval, 
					"train":monitoring_train}

		print("===========begin to train============")
		# sess_config = tf.ConfigProto(allow_soft_placement=False,
		# 							log_device_placement=False)
		# # sess_config.gpu_options.visible_device_list = str(task_index)

		# print(sess_config.gpu_options.visible_device_list, task_index, "==============")

		print("start training")

		hooks = []
		hooks.extend(train_op_dict["hooks"])
		if FLAGS.opt_type == "ps" or FLAGS.opt_type == "ps_sync":
			sess_config = tf.ConfigProto(allow_soft_placement=False,
									log_device_placement=False)
			print("==create monitored training session==", FLAGS.opt_type, is_chief)
			sess = tf.train.MonitoredTrainingSession(master=target,
												 is_chief=is_chief,
												 config=kargs.get("sess_config",sess_config),
												 hooks=hooks,
												 checkpoint_dir=checkpoint_dir,
												 save_checkpoint_steps=num_storage_steps)
		elif FLAGS.opt_type == "pai_soar" and pai:
			sess_config = tf.ConfigProto(allow_soft_placement=False,
									log_device_placement=False)
			sess = tf.train.MonitoredTrainingSession(master=target,
												 is_chief=is_chief,
												 config=kargs.get("sess_config",sess_config),
												 hooks=hooks,
												 checkpoint_dir=checkpoint_dir,
												 save_checkpoint_steps=num_storage_steps)
		elif FLAGS.opt_type == "hvd" and hvd:
			sess_config = tf.ConfigProto(allow_soft_placement=False,
									log_device_placement=False)
			sess_config.gpu_options.allow_growth = False
			sess_config.gpu_options.visible_device_list = str(hvd.local_rank())
			sess = tf.train.MonitoredTrainingSession(checkpoint_dir=checkpoint_dir,
												   hooks=hooks,
												   config=sess_config,
												   save_checkpoint_steps=num_storage_steps)
		else:
			print("==single sess==")
			sess_config = tf.ConfigProto(allow_soft_placement=False,
									log_device_placement=False)
			sess = tf.train.MonitoredTrainingSession(config=sess_config,
												   hooks=hooks,
												   checkpoint_dir=checkpoint_dir,
												   save_checkpoint_steps=num_storage_steps)
						
		print("==begin to train and eval==")
		# step = sess.run(tf.train.get_global_step())
		# print(step, task_index, "==task_index, global_step==")
		monitoring_info = train_fn(train_dict, sess)

		# for i in range(10):
		# 	l = sess.run(train_features)
		# print(l, task_index)

		if task_index == 0:
			start_time = time.time()
			print("===========begin to eval============")
			eval_finial_dict = eval_fn(eval_dict, sess)
			end_time = time.time()
			print("==total forward time==", end_time - start_time)

			# with tf.gfile.Open(os.path.join(checkpoint_dir, "train_and_eval_info.json"), "w") as fwobj:
			# 	import json
			# 	fwobj.write(json.dumps({"final_eval":eval_finial_dict, 
			# 							"train_and_eval":monitoring_info}))

