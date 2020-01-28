# BERT-keras
Keras implementation of Google BERT(Bidirectional Encoder Representations from Transformers), using pretrained OpenAI Transformer model for initialization!

## How to use it?
```python
# this is a pseudo code you can read an actual working example in tutorial.ipynb
text_encoder = MyTextEncoder(**my_text_encoder_params) # you create a text encoder (sentence piece and openai's bpe are included)
lm_generator = lm_generator(text_encoder, **lm_generator_params) # this is essentially your data reader (single sentence and double sentence reader with masking and is_next label are included)
task_meta_datas = [lm_task, classification_task, pos_task] # these are your tasks (the lm_generator must generate the labels for these tasks too)
encoder_model = create_transformer(**encoder_params) # or you could simply load_openai()
trained_model = train_model(encoder_model, task_meta_datas, lm_generator, **training_params) # it does both pretraing and finetuning
trained_model.save_weights('my_awesome_model') # save it
model = load_model('my_awesome_model', encoder_model) # load it later and use it!
```

## Notes
* The general idea of this library is to use OpenAI's pretrained model as a good initialization point so you can train your own model in no time. (without TPUs)
* Loading OpenAI model is tested with both tensorflow and theano as backend
* Training and fine-tuning a model is not possible with theano backend
* You can use the data generator and task meta data for most of the NLP tasks and you can use them in other frameworks
* There are some unit tests for both dataset and transformer model (read them if you are not sure about something)
* Even tough I don't like my keras code, it's readable :)
* You can use other encoders, like LSTM or BiQRNN for training if you follow the contract (have same inputs and outputs as transformer encoder)
* What will happen when the official code is out?, data reader will still be usable and we might even be able to import those weights into this library (I think we will, cause the actual transformer network is really easy to implement)
* Why keras? pytorch version is already out! (BTW you can use this data generator for training and fine-tuning that model too)
* I strongly advise you to read the tutorial.ipynb (I don't like notebooks so this is a poorly designed notebook, but read it though)

## important code concepts
* Task: there are two general tasks, sentence level tasks(like is_next and sentiment analysis), and token level tasks(like PoS and NER)
* Sentence: a sentence represents an example with it's labels and everything, for each task it provides a target(single one for sentence level tasks and per token label for token level tasks) and a mask, for token levels we need to not only ignore paddings but also we might want to predict class on first char of a word (like the BERT paper(first piece of a multi piece word)) and for sentence levels we want a extraction point(like start token in BERT paepr)
* TaskWeightScheduler: for training we might want to start with language modeling and smoothly move to classification, they can be easily implemented with this class
* attention_mask: with this you can 1.make your model causal 2.ignore paddings 3.do your crazy idea :D
* special_tokens: pad, start, end, delimiter, mask

## Ownership
[Neiron](neiron.ai)
