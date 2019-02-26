odpscmd=$1

pai_command="
pai -name tensorflow180 
	-Dscript='file:///Users/xuhaotian/Desktop/my_work/BERT.zip'
	-DentryFile='./BERT/t2t_bert/distributed_bin/evaluate_api.py' 
	-DgpuRequired=100
	-DhyperParameters='file:///Users/xuhaotian/Desktop/my_work/BERT/t2t_bert/distributed_single_sentence_classification/porn_eval'
	-Dbuckets='oss://alg-misc/BERT/?role_arn=acs:ram::1265628042679515:role/yuefeng2&host=cn-hangzhou.oss-internal.aliyun-inc.com';
"
echo "${pai_command}"
${odpscmd} -e "${pai_command}"
echo "finish..."


