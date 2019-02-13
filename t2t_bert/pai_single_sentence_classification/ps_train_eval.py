# -*- coding: utf-8 -*-
import sys,os
sys.path.append("..")

import tensorflow as tf
from train_eval_fn import train_eval_fn

flags = tf.flags

FLAGS = flags.FLAGS

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

## Required parameters
flags.DEFINE_string(
	"config_file", None,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_string(
	"init_checkpoint", None,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_string(
	"vocab_file", None,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_string(
	"label_id", None,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_integer(
	"max_length", 128,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_string(
	"train_file", None,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_string(
	"dev_file", None,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_string(
	"model_output", None,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_integer(
	"epoch", 5,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_integer(
	"num_classes", 5,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_integer(
	"train_size", 1402171,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_integer(
	"batch_size", 32,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_string(
	"model_type", None,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_string(
	"if_shard", None,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_integer(
	"eval_size", 1000,
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_string(
	"opt_type", "ps",
	"Input TF example files (can be a glob or comma separated).")

flags.DEFINE_bool(
	"is_debug", False,
	"Input TF example files (can be a glob or comma separated).")

def monitored_sess(worker_count, 
				task_index, 
				cluster, 
				is_chief, 
				target,
				init_checkpoint,
				train_file,
				dev_file,
				checkpoint_dir):
	
	sess_config = tf.ConfigProto()

	if worker_count >= 1 and FLAGS.opt_type == "ps":
		available_worker_device = "/job:worker/task:%d" % (task_index)
		with tf.device(tf.train.replica_device_setter(worker_device=available_worker_device, cluster=cluster)):
			train_eval_fn(FLAGS,
							worker_count, 
							task_index, 
							is_chief, 
							target,
							init_checkpoint,
							train_file,
							dev_file,
							checkpoint_dir,
							FLAGS.is_debug)
	else:
		train_eval_fn(FLAGS,
					worker_count, 
					task_index, 
					is_chief, 
					target,
					init_checkpoint,
					train_file,
					dev_file,
					checkpoint_dir,
					FLAGS.is_debug)

if __name__ == "__main__":
	monitored_sess(worker_count=1,
					task_index=0,
					cluster="",
					is_chief=True,
					target="",
					init_checkpoint=FLAGS.init_checkpoint,
					train_file=FLAGS.train_file,
					dev_file=FLAGS.dev_file,
					checkpoint_dir=FLAGS.model_output)
