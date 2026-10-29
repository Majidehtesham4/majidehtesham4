"""Understanding Persian requests without a language model: the text normalised, words compared with the
phrases of the library (typos and plural forms forgiven), periods ("دیروز", "ماه قبل", "مهر ۱۴۰۵",
"۳۰ روز اخیر"), amounts ("۵ میلیون تومان", "دویست و پنجاه هزار"), counts and document numbers."""

import re
from datetime import date, timedelta
from difflib import SequenceMatcher

from odoo.addons.veron_core.models import jalali

_CHARS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "أ": "ا", "إ": "ا", "ٱ": "ا", "ؤ": "و",
	"‌": " ", "‍": "", "ـ": ""})
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_DIACRITICS = re.compile("[ً-ٰٟ]")
_PUNCTUATION = re.compile(r"[؟?!،,؛;:«»\"'()\[\]{}…|\\]+")
# Words that carry no meaning for finding what is asked
STOP = set("""را رو از به در با که این اون آن ان برای تا و یا هم من ما شما ی ای هست هستند است بود باشه باشد چی چه
	لطفا لطفاً لطف میخوام می‌خواهم میخواهم خواهش کن کنید بکن بکنید بده بدید بگو بگید یه یک همه همون همین اینو اونو
	ها های کدوم کدام چند چقدر کجا کی رو کرد کردم کردی کنم کنی""".split())
SUFFIXES = ("هایی", "های", "ها", "ترین", "تر", "ی", "ات", "ان")
MONTHS = {name: index + 1 for index, name in enumerate(jalali.MONTHS)}
UNITS = {"صفر": 0, "یک": 1, "یه": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "شیش": 6, "هفت": 7, "هشت": 8,
	"نه": 9, "ده": 10, "یازده": 11, "دوازده": 12, "سیزده": 13, "چهارده": 14, "پانزده": 15, "پونزده": 15, "شانزده": 16,
	"هفده": 17, "هجده": 18, "هیجده": 18, "نوزده": 19, "بیست": 20, "سی": 30, "چهل": 40, "پنجاه": 50, "شصت": 60,
	"هفتاد": 70, "هشتاد": 80, "نود": 90, "صد": 100, "یکصد": 100, "دویست": 200, "سیصد": 300, "چهارصد": 400,
	"پانصد": 500, "پونصد": 500, "ششصد": 600, "هفتصد": 700, "هشتصد": 800, "نهصد": 900}
SCALES = {"هزار": 1000, "میلیون": 1_000_000, "ملیون": 1_000_000, "میلیارد": 1_000_000_000, "ملیارد": 1_000_000_000}
REF = re.compile(r"\b([A-Za-z]{1,8}[/-]?\d{2,}(?:[/-]\d+)*)\b")


JOINED_WORDS = {"پیشنویس": "پیش نویس", "پیشفاکتور": "پیش فاکتور", "صورت حساب": "صورتحساب", "اینو": "این را",
	"اونو": "ان را", "ثبتش": "ثبت", "بزنش": "بزن", "میخوام": "می خواهم", "میخواهم": "می خواهم"}
JOINED = re.compile(r"\b(" + "|".join(re.escape(word) for word in JOINED_WORDS) + r")\b")


def normalize(text):
	"""Persian letters and digits made one form, diacritics, punctuation and half-spaces out, lower case"""
	text = (text or "").translate(_CHARS).translate(_DIGITS)
	text = _DIACRITICS.sub("", text).replace("آ", "ا")
	text = _PUNCTUATION.sub(" ", text)
	text = re.sub(r"\s+", " ", text).strip().lower()
	# Words people write joined or apart: one form
	return JOINED.sub(lambda match: JOINED_WORDS[match.group(0)], text)


def stem(word):
	for suffix in SUFFIXES:
		if word.endswith(suffix) and len(word) - len(suffix) >= 3:
			return word[: -len(suffix)]
	return word


def tokens(text):
	"""The words that carry meaning, in a light stem form"""
	return [stem(word) for word in normalize(text).split() if word not in STOP and len(word) > 1]


def _near(word, words):
	if word in words:
		return 1.0
	best = 0.0
	for other in words:
		if abs(len(other) - len(word)) <= 2 and min(len(word), len(other)) >= 3:
			ratio = SequenceMatcher(None, word, other).ratio()
			if ratio > best:
				best = ratio
	return 0.8 if best >= 0.8 else 0.0


def similarity(message_tokens, phrase_tokens, known=None):
	"""How much a message says what a phrase says: the phrase's words found in the message, typos forgiven,
	weighted with how much of the message they cover. With «known» (the words of the whole library), only those
	words of the message count for the cover: a name or a number in the request does not make it less clear"""
	if not message_tokens or not phrase_tokens:
		return 0.0
	found = sum(_near(word, message_tokens) for word in phrase_tokens)
	if not found:
		return 0.0
	covered = sum(_near(word, phrase_tokens) for word in message_tokens)
	# A word the library does not have (a name, a number) counts a quarter
	size = len(message_tokens) if known is None else sum(1 if w in known else 0.25 for w in message_tokens)
	return 0.7 * found / len(phrase_tokens) + 0.3 * min(covered / size, 1.0)


def known_words(message_tokens, vocabulary):
	"""The words of the message that are words of the library, typos forgiven"""
	return {w for w in message_tokens if _near(w, vocabulary)}


# --- names of records

# Words around a name that are not part of it: titles of people and the words of a count
NAME_STOP = STOP | set("""اقای اقا خانم جناب سرکار اقایان استاد مهندس دکتر عدد عددی دونه دانه تایی بسته واحد برای""".split())
_LATIN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def name_words(text):
	"""The words of a name as they are compared: one form of letters and digits, the small words out"""
	return [w for w in normalize(text).split() if w not in NAME_STOP and (len(w) > 1 or w.isdigit())]


def variants(word):
	"""The ways a word may be written in the database: Arabic or Persian «ی» and «ک», Latin or Persian digits"""
	found = {word, word.replace("ی", "ي").replace("ک", "ك"), word.replace("ی", "ي"), word.replace("ک", "ك"),
		word.translate(_LATIN)}
	if word.startswith("ا"):
		found.add("آ" + word[1:])
	return found


_LOOSE = set("0123456789۰۱۲۳۴۵۶۷۸۹یيىکكهةۀاآأإ")


def like(word):
	"""An «ilike» pattern of a word that finds it however its digits and letters are written in the database, even
	mixed in one name («۱۱۵۴C_S93»): those letters and digits match any one character. None when too little of the
	word is left to search with."""
	if word.isdigit():
		return None
	pattern, fixed = [], 0
	for char in word:
		if char in _LOOSE:
			pattern.append("_")
		else:
			pattern.append("\\" + char if char in "%_\\" else char)
			fixed += 1
	return "%" + "".join(pattern) + "%" if fixed >= 2 else None


def name_score(words, name):
	"""How well the words of a request name a record: (score, the record's words found, how many it has)
	Each word found counts 1, one with a typo or written joined or apart a little less; digits only when equal"""
	own = name_words(name)
	if not own or not words:
		return 0.0, 0, len(own)
	stems = {stem(w): w for w in own}
	score, hit, used = 0.0, set(), set()
	for index, word in enumerate(words):
		if index in used:
			continue
		if word in own or stem(word) in stems:
			score += 1
			hit.add(word if word in own else stems[stem(word)])
			continue
		joined = word + words[index + 1] if index + 1 < len(words) else ""
		if joined and joined in own:
			score += 2
			hit.add(joined)
			used.add(index + 1)
			continue
		if word.isdigit():
			continue
		best, which = 0.0, None
		for other in own:
			if other.isdigit():
				continue
			if len(word) >= 4 and abs(len(other) - len(word)) <= 2:
				ratio = SequenceMatcher(None, word, other).ratio()
				if ratio >= 0.8 and ratio > best:
					best, which = 0.8, other
			if len(word) >= 3 and len(other) >= 3 and (other.startswith(word) or word.startswith(other)) and best < 0.5:
				best, which = 0.5, other
		if which:
			score += best
			hit.add(which)
	return score, len(hit), len(own)


# --- numbers and amounts

def words_number(words):
	"""A number written in Persian words, e.g. «دویست و پنجاه هزار»; None when the words are not a number"""
	total, current, seen = 0, 0, False
	for word in words:
		if word == "و":
			continue
		if word.isdigit():
			current += int(word)
			seen = True
		elif word in UNITS:
			current += UNITS[word]
			seen = True
		elif word in SCALES:
			total += (current or 1) * SCALES[word]
			current = 0
			seen = True
		else:
			return None
	return total + current if seen else None


def amounts(text):
	"""Amounts in the text with their unit: [(value, "toman" | "rial" | None)]"""
	# Thousands separators go before the punctuation is taken out: «۲,۰۰۰,۰۰۰» is one number
	text = re.sub(r"(?<=\d)[,٬،](?=\d{3})", "", (text or "").translate(_DIGITS))
	words = normalize(text).split()
	found, index = [], 0
	number_words = set(UNITS) | set(SCALES) | {"و"}
	while index < len(words):
		word = words[index]
		if re.fullmatch(r"\d+(\.\d+)?", word) or word in UNITS or word in SCALES:
			end = index
			while end < len(words) and (re.fullmatch(r"\d+(\.\d+)?", words[end]) or words[end] in number_words):
				# A number in digits starts a number of its own, except after «و»: «هفت ۱ تا» is seven, then one;
				# «۱۱۵۴ ۵۰» two numbers; «۲ میلیون و ۵۰۰ هزار» one
				if end > index and words[end].replace(".", "").isdigit() and words[end - 1] != "و":
					break
				end += 1
			while end > index and words[end - 1] == "و":
				end -= 1
			chunk = words[index:end]
			value = None
			if len(chunk) == 1 and re.fullmatch(r"\d+(\.\d+)?", chunk[0]):
				value = float(chunk[0])
			elif chunk and re.fullmatch(r"\d+(\.\d+)?", chunk[0]) and all(w in SCALES or w == "و" for w in chunk[1:]):
				value = float(chunk[0])
				for scale in chunk[1:]:
					value *= SCALES.get(scale, 1)
			else:
				number = words_number(chunk)
				value = float(number) if number is not None else None
			unit = None
			if end < len(words) and words[end] in ("تومان", "تومن"):
				unit = "toman"
			elif end < len(words) and words[end] in ("ریال", "rial"):
				unit = "rial"
			if value is not None:
				found.append((value, unit))
			index = max(end, index + 1)
		else:
			index += 1
	return found


def count(text):
	"""A small count asked for, e.g. «۱۰ تا», «پنج مورد», «۲۰ مشتری اول»"""
	match = re.search(r"\b(\d{1,3})\s*(تا|مورد|عدد|نفر|ردیف|مشتری|کالا|فاکتور|سند)?\b", normalize(text))
	return int(match.group(1)) if match and match.group(2) else None


def refs(text):
	"""Document numbers like INV/2026/00012, S00045, PC-00038"""
	return [match.upper() for match in REF.findall((text or "").translate(_DIGITS))]


def quoted(text):
	return [part.strip() for part in re.findall(r"[«\"']([^»\"']{2,80})[»\"']", text or "")]


# --- periods

def _month_range(year, month):
	return jalali.to_gregorian(year, month, 1), jalali.to_gregorian(year, month, jalali.month_length(year, month))


def _shamsi_date(text):
	match = re.search(r"\b(1[34]\d\d)[/-](\d{1,2})[/-](\d{1,2})\b", text)
	if match:
		try:
			return jalali.to_gregorian(*(int(g) for g in match.groups())), match.end()
		except (ValueError, TypeError):
			return None, 0
	match = re.search(r"\b(20\d\d)-(\d{1,2})-(\d{1,2})\b", text)
	if match:
		try:
			return date(*(int(g) for g in match.groups())), match.end()
		except ValueError:
			return None, 0
	return None, 0


def period(text, today):
	"""(date_from, date_to, label) of a period said in the text, or None"""
	words = normalize(text)
	year, month, _day = jalali.to_jalali(today)
	if "از" in words.split() and "تا" in words.split():
		first, end = _shamsi_date(words)
		if first:
			second, _end = _shamsi_date(words[end:])
			if second:
				return first, second, f"{first} - {second}"
	match = re.search(r"\b(\d{1,3})\s*(روز|هفته|ماه)\s*(اخیر|گذشته|قبل|پیش|اخر|آخر)\b", words)
	if match:
		number, unit = int(match.group(1)), match.group(2)
		days = number * {"روز": 1, "هفته": 7, "ماه": 30}[unit]
		return today - timedelta(days=days - 1), today, f"{number} {unit} اخیر"
	for name, number in MONTHS.items():
		found = re.search(rf"\b{name}(?:\s*ماه)?(?:\s*(1[34]\d\d))?\b", words)
		if found:
			the_year = int(found.group(1)) if found.group(1) else (year if number <= month else year - 1)
			start, end = _month_range(the_year, number)
			return start, end, f"{name} {the_year}"
	simple = [
		(r"\bامروز\b", (today, today, "امروز")),
		(r"\bپریروز\b", (today - timedelta(days=2), today - timedelta(days=2), "پریروز")),
		(r"\bدیروز\b", (today - timedelta(days=1), today - timedelta(days=1), "دیروز")),
	]
	for pattern, value in simple:
		if re.search(pattern, words):
			return value
	if re.search(r"\b(این|همین) هفته\b", words):
		start = today - timedelta(days=(today.weekday() + 2) % 7)
		return start, today, "این هفته"
	if re.search(r"\bهفته (قبل|گذشته|پیش)\b", words):
		end = today - timedelta(days=(today.weekday() + 2) % 7) - timedelta(days=1)
		return end - timedelta(days=6), end, "هفته‌ی گذشته"
	if re.search(r"\b(این|همین) ماه\b", words) or re.search(r"\bماه جاری\b", words):
		start, _end = _month_range(year, month)
		return start, today, "این ماه"
	if re.search(r"\bماه (قبل|گذشته|پیش)\b", words):
		previous_year, previous_month = (year, month - 1) if month > 1 else (year - 1, 12)
		start, end = _month_range(previous_year, previous_month)
		return start, end, "ماه گذشته"
	if re.search(r"\b(امسال|سال جاری|این سال)\b", words):
		return jalali.to_gregorian(year, 1, 1), today, "امسال"
	if re.search(r"\b(پارسال|سال (قبل|گذشته|پیش))\b", words):
		return jalali.to_gregorian(year - 1, 1, 1), jalali.to_gregorian(year, 1, 1) - timedelta(days=1), "سال گذشته"
	single, _end = _shamsi_date(words)
	if single:
		return single, single, str(single)
	return None


def is_more(text):
	"""«بیشتر», «ادامه», «بقیه»: the next page of the last list"""
	return bool(re.search(r"\b(بیشتر|ادامه|بقیه|بعدی|باقی)\b", normalize(text)))


CONTEXT_WORDS = set("""امروز دیروز پریروز فردا روز روزه هفته ماه سال فصل قبل قبلی گذشته پیش بعد بعدی اخیر جاری همین
امسال پارسال پارسال اول دوم سوم چهارم اخر آخر از تا چطور چقدر چند چی چیه بود بوده شد شده الان اکنون بیشتر ادامه بقیه باقی""".split())


def only_context(text):
	"""Nothing but a period, «more» or a question word: «و ماه قبل؟», «پارسال چی؟», «بیشتر»"""
	words = [w for w in normalize(text).split() if w not in STOP]
	return bool(words) and all(w in CONTEXT_WORDS or w in MONTHS or w in UNITS or w.isdigit() for w in words)


def refers_back(text):
	"""«همین», «همون», «اون», «این مشتری»: the record spoken of before"""
	return bool(re.search(r"\b(همین|همون|همان|اون|او|این مشتری|این کالا|این فاکتور|این سند|این شخص)\b", normalize(text)))
