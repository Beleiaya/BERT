python ./t2t_bert/distributed_data_prepare/classification_distillation_data_prepare.py \
	--buckets /data/xuht \
	--train_file porn/clean_data/train.txt \
	--dev_file porn/clean_data/dev.txt \
	--test_file porn/clean_data/test.txt \
	--train_result_file porn/clean_data/textcnn/distillation/bert_small/train_tfrecords \
	--dev_result_file  porn/clean_data/textcnn/distillation/bert_small/dev_tfrecords\
	--test_result_file  porn/clean_data/textcnn/distillation/bert_small/test_tfrecords\
	--supervised_distillation_file porn/clean_data/bert_small/train_distillation.info \
	--unsupervised_distillation_file porn/clean_data/bert_small/dev_distillation.info \
	--vocab_file w2v/tencent_ai_lab/char_id.txt \
	--label_id /data/xuht/porn/label_dict.json \
	--lower_case True \
	--max_length 128 \
	--if_rule "no_rule" \
	--rule_word_dict /data/xuht/porn/rule/rule/phrases.json \
	--rule_word_path /data/xuht/porn/rule/rule/mined_porn_domain_adaptation_v2.txt \
	--rule_label_dict /data/xuht/porn/rule/rule/rule_label_dict.json \
	--with_char "no" \
	--char_len 5 \
	--predefined_vocab_size 50000 \
	--corpus_vocab_path porn/clean_data/bert_small/char_id.txt
