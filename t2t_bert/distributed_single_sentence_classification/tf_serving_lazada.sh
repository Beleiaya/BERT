python ./t2t_bert/distributed_bin/tf_serving_api.py \
	--buckets "/data/xuht" \
	--vocab "multi_cased_L-12_H-768_A-12/vocab.txt" \
	--do_lower_case True \
	--url "192.168.0.100" \
	--port "7901" \
	--model_name "textcnn_lazada" \
	--signature_name "serving_default" \
	--versions "1555594622" \
	--task_type "single_sentence_classification" \
	--tokenizer "bert" \
	--with_char "no_char" \
	--output_path "lazada_test.json" \
	--input_data "lazada_test.txt" \
	--model_type "bert_like_single_sentence_classification" \
	--max_seq_length 128