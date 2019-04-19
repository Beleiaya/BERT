CUDA_VISIBLE_DEVICES="0" python ./t2t_bert/distributed_bin/evaluate_api.py \
	--buckets "/data/xuht" \
	--config_file "./data/textcnn/textcnn.json" \
	--init_checkpoint "lazada/new_data/20190415/data/distillation/feature_distillation/model/textcnn_0417/model.ckpt-59431" \
	--vocab_file "multi_cased_L-12_H-768_A-12/vocab.txt" \
	--label_id "lazada/new_data/20190415/label_dict.json" \
	--max_length 128 \
	--train_file "lazada/new_data/20190415/data/distillation/feature_distillation/dev_tfrecords" \
	--dev_file "lazada/new_data/20190415/data/distillation/feature_distillation/dev_tfrecords" \
	--model_output "lazada/new_data/20190415/data/distillation/feature_distillation/model/textcnn_0417/" \
	--epoch 8 \
	--num_classes 4 \
	--train_size 760760 \
	--eval_size 190190 \
	--batch_size 24 \
	--model_type "textcnn" \
	--if_shard 2 \
	--is_debug 1 \
	--run_type "sess" \
	--opt_type "all_reduce" \
	--num_gpus 4 \
	--parse_type "parse_batch" \
	--rule_model "normal" \
	--profiler "no" \
	--train_op "adam_weight_decay_exclude" \
	--running_type "eval" \
	--cross_tower_ops_type "paisoar" \
	--distribution_strategy "MirroredStrategy" \
	--load_pretrained "yes" \
	--w2v_path "multi_cased_L-12_H-768_A-12/vocab_w2v.txt" \
	--with_char "no_char" \
	--input_target "a" \
	--decay "no" \
	--warmup "no" \
	--distillation "normal" \
    --task_type "single_sentence_classification"