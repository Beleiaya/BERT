import tensorflow as tf
from data_generator import tokenization

class InputRuleExample(object):
	"""A single training/test example for simple sequence classification."""

	def __init__(self, guid, text_a, text_b=None, label=None,
		label_ratio=None):
		"""Constructs a InputExample.

		Args:
			guid: Unique id for the example.
			text_a: string. The untokenized text of the first sequence. For single
				sequence tasks, only this sequence must be specified.
			text_b: (Optional) string. The untokenized text of the second sequence.
				Only must be specified for sequence pair tasks.
			label: (Optional) string. The label of the example. This should be
				specified for train and dev examples, but not for test examples.
		"""
		self.guid = guid
		self.text_a = text_a
		self.text_b = text_b
		self.label = label

	def __str__(self):
		return self.__repr__()

	def __repr__(self):
		s = ""
		s += "guid: {}".format((self.guid))
		s += ", text_a: {}".format(
				tokenization.printable_text(self.text_a))
		if self.text_b:
			s += ", text_b: {}".format(self.text_b)
		if self.label:
			s += ", label: {}".format(self.label)
		return s

class InputFeatures(object):
	"""A single set of features of data."""

	def __init__(self, guid, input_ids, input_mask, segment_ids, rule_ids,
		label_ids):
		self.guid = guid
		self.input_ids = input_ids
		self.input_mask = input_mask
		self.segment_ids = segment_ids
		self.label_ids = label_ids
		self.rule_ids = rule_ids