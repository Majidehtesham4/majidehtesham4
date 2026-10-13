"""Find the command a message asks for by comparing it with each command's sample sentences.

Samples and messages become TF-IDF vectors of words, word pairs and letter groups (letter groups
let "فاکتورهامون" still match "فاکتور"); the score is the cosine similarity with the closest
sample. Words the samples never use, such as a customer's name, are left out of the message's
vector, so they neither help nor hurt.
"""

import math
import re
from collections import Counter
from itertools import pairwise

from iran_erp.commands.text import MONTHS, SEPARATOR, STOPWORDS, stem, tokens

PLACEHOLDER = re.compile(r"\{\w+\}")
# Words that name a time span are details, not the request itself: "هزینه‌های این ماه" is about expenses
PERIOD_WORDS = {
	"این",
	"همین",
	"ماه",
	"هفته",
	"روز",
	"سال",
	"فصل",
	"امروز",
	"دیروز",
	"فردا",
	"امسال",
	"پارسال",
	# not "پیش": it is also the start of "پیش فاکتور"
	"گذشته",
	"قبل",
	"جاری",
	"اخیر",
	"بعد",
	"اینده",
} | set(MONTHS)
NUMERIC = re.compile(r"^\d+([./-]\d+)*$")


def features(text: str) -> Counter:
	words = [w for w in tokens(PLACEHOLDER.sub(" ", text)) if not NUMERIC.match(w) and w != SEPARATOR]
	found = Counter()
	stems = [stem(w) for w in words]
	for word, root in zip(words, stems, strict=True):
		weight = 0.2 if word in PERIOD_WORDS else 0.3 if word in STOPWORDS else 1.0
		found[f"w:{root}"] += weight
		padded = f"#{root}#"
		for n in (3, 4):
			for i in range(len(padded) - n + 1):
				found[f"c:{padded[i : i + n]}"] += 0.3 * weight
	for (a, b), (word_a, word_b) in zip(pairwise(stems), pairwise(words), strict=True):
		if word_a in PERIOD_WORDS and word_b in PERIOD_WORDS:
			continue
		minor = {word_a, word_b} & (PERIOD_WORDS | STOPWORDS)
		found[f"b:{a}_{b}"] += 0.3 if minor else 1.0
	return found


class Matcher:
	def __init__(self, samples: list[tuple[str, str, dict]]):
		"""samples: (intent name, sentence, slot values the sentence implies)."""
		self.samples = []
		document_frequency = Counter()
		raw = []
		for intent, sentence, values in samples:
			vector = features(sentence)
			if not vector:
				continue
			raw.append((intent, vector, values))
			document_frequency.update(vector.keys())
		count = len(raw)
		self.idf = {f: math.log((count + 1) / (df + 1)) + 1 for f, df in document_frequency.items()}
		for intent, vector, values in raw:
			self.samples.append((intent, self._weigh(vector), values))
		# Feature -> samples that have it, so a message is compared only with samples it shares words with
		self.index = {}
		for position, (_intent, vector, _values) in enumerate(self.samples):
			for feature in vector:
				self.index.setdefault(feature, []).append(position)

	def _weigh(self, vector: Counter) -> dict:
		weighted = {
			# Sublinear term frequency, so a word said twice does not count double
			f: (count if count <= 1 else 1 + math.log(count)) * self.idf[f]
			for f, count in vector.items()
			if f in self.idf and count > 0
		}
		norm = math.sqrt(sum(v * v for v in weighted.values())) or 1.0
		return {f: v / norm for f, v in weighted.items()}

	def rank(self, text: str, limit: int = 5) -> list[tuple[str, float, dict]]:
		"""The best intents for a message: (intent, score 0..1, slot values of the closest sample)."""
		query = self._weigh(features(text))
		if not query:
			return []
		scores = {}
		for feature, weight in query.items():
			for position in self.index.get(feature, ()):
				scores[position] = scores.get(position, 0.0) + weight * self.samples[position][1][feature]
		best = {}
		for position, score in scores.items():
			intent, _vector, values = self.samples[position]
			# Samples made from a list of names (open the list of ...) give way to written ones on a tie
			if values.get("_generated"):
				score *= 0.97
			if score > best.get(intent, (0, None))[0]:
				best[intent] = (score, values)
		ranked = sorted(best.items(), key=lambda item: item[1][0], reverse=True)
		return [(intent, round(score, 3), values) for intent, (score, values) in ranked[:limit]]
