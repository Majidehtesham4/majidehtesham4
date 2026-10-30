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
# Latin («INV/2026/00012»، «S00045») or a Persian journal's own («فروش/1405/0015»), which always has its slashes
REF = re.compile(r"(?<!\w)([A-Za-z]{1,8}[/-]?\d{2,}(?:[/-]\d+)*|[\u0600-\u06FF]{2,10}/\d{2,}(?:/\d+)+)(?!\w)")


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


# --- the parts of a request: what is done, to what, and in relation to what

# Verbs and the action they ask; each list is matched on whole words, in any order of the request
ACTIONS = {
	"delete": ("حذف", "بردار", "برداری", "پاک"),
	"edit": ("تغییر", "عوض", "اصلاح", "ویرایش", "بشه", "بکنش"),
	"approve": ("تایید", "تأیید", "قطعی", "پست"),
	"send": ("بفرست", "ارسال", "بفرستید"),
	"open": ("بازش", "باز"),
	"compare": ("مقایسه", "تغییرات", "اختلاف"),
	"create": ("بساز", "بزن", "صادر", "صدور", "ایجاد", "بنویس", "ثبت", "اضافه", "پیشنویس", "پیش نویس", "درست"),
	"search": ("پیدا", "بگرد", "جستجو", "جست", "کجاست"),
	"report": ("گزارش", "خلاصه", "جمع", "آمار", "چقدر", "چند", "مانده", "وضعیت"),
	"view": ("نشان", "نشون", "ببینم", "لیست", "فهرست", "مشخصات", "اطلاعات", "بخوان", "بخون", "بیار", "بیاور", "محتوای",
		"محتوا", "جزئیات"),
}
# Nouns and what they are about
SUBJECTS = {
	"customer": ("مشتری", "مشتریان", "خریدار"),
	"vendor": ("تامین کننده", "تأمین کننده", "تامین‌کننده"),
	"contact": ("مخاطب", "طرف حساب", "شخص"),
	"invoice": ("فاکتور", "صورتحساب"),
	"quotation": ("پیش فاکتور", "پیشفاکتور"),
	"order": ("سفارش",),
	"product": ("کالا", "محصول", "جنس"),
	"stock": ("موجودی", "انبار"),
	"employee": ("کارمند", "پرسنل", "کارکنان", "کارمندان"),
	"payroll": ("حقوق", "فیش"),
	"cheque": ("چک",),
	"bank": ("بانک", "حساب بانکی"),
	"petty_cash": ("تنخواه",),
	"tax": ("مالیات", "ارزش افزوده"),
	"discount": ("تخفیف",),
	"expense": ("هزینه",),
	"receivable": ("مطالبات", "بدهکار", "بدهکاران"),
	"payable": ("بدهی", "پرداختنی"),
	"task": ("کار", "کارها", "پیگیری", "فعالیت"),
}
# Words that join a name to its role in the request: «از انبار مرکزی»، «به انبار شعبه»، «برای حسن پور»
MARKERS = ("از", "به", "برای", "واسه", "برا", "در", "توی", "تو", "با")


def _has(words, text, phrase):
	return (" " + phrase + " ") in (" " + text + " ") if " " in phrase else phrase in words or stem(phrase) in words


def action(text):
	"""The action a request asks (create, edit, delete, report...), or None; the most specific wins"""
	normal = normalize(text)
	words = set(normal.split()) | {stem(w) for w in normal.split()}
	for name, verbs in ACTIONS.items():
		if any(_has(words, normal, verb) for verb in verbs):
			return name
	return None


# A question about what is or was: «چی فاکتور شده»، «کدوم چک‌ها پاس شدن»; with no word of a command in it
QUESTION_WORDS = ("چی", "چه", "کدام", "کدوم", "چند", "چقدر", "ایا", "آیا", "کی")
DONE_WORDS = ("شده", "شدن", "شدند", "شد", "بوده", "شدہ")
COMMAND_WORDS = ("کن", "بکن", "کنید", "بکنید", "بزن", "بزنید", "بساز", "بسازید", "بنویس", "بنویسید", "بده", "بدید",
	"بفرست", "بفرستید", "کنم", "بشه", "شود", "بشود")


def asks_what_is(text):
	"""Does the request ask what is or was done, rather than ask to do it: a question word or a «...شده» and
	no word of a command"""
	words = normalize(text).split()
	if any(word in COMMAND_WORDS for word in words):
		return False
	return any(word in QUESTION_WORDS for word in words) or any(word in DONE_WORDS for word in words)


def subjects(text):
	"""What a request is about (customer, invoice, product...), in the order of the list"""
	normal = normalize(text)
	words = set(normal.split()) | {stem(w) for w in normal.split()}
	return [name for name, nouns in SUBJECTS.items() if any(_has(words, normal, noun) for noun in nouns)]


def after(text, markers):
	"""The words of the text after one of the markers, up to the next marker: «از انبار مرکزی به شعبه» and
	«از» give «انبار مرکزی». The whole text when no marker is in it."""
	words = normalize(text).split()
	for index, word in enumerate(words):
		if word in markers:
			part = []
			for other in words[index + 1:]:
				if other in MARKERS:
					break
				part.append(other)
			if part:
				return " ".join(part)
	return normalize(text)


def opens(text):
	"""«بازش کن»، «باز کن»، «نشونم بده توی برنامه»: the last result opened in the program"""
	return bool(re.search(r"\b(بازش|باز کن|باز کنید|بازشون|باز شود|توی برنامه نشون|در برنامه نشان)\b", normalize(text)))


def days_ahead(text):
	"""In how many days a time said in the request falls: «فردا» 1, «پس فردا» 2, «۳ روز دیگه» 3, «هفته بعد» 7"""
	words = normalize(text)
	if re.search(r"\bپس ?فردا\b", words):
		return 2
	if re.search(r"\bفردا\b", words):
		return 1
	match = re.search(r"\b(\d{1,2})\s*روز\s*(دیگه|دیگر|بعد)\b", words)
	if match:
		return int(match.group(1))
	if re.search(r"\bهفته\s*(بعد|دیگه|دیگر|آینده|اینده)\b", words):
		return 7
	if re.search(r"\bامروز\b", words):
		return 0
	return None


# --- an order said in a sentence: its lines, its party and what is said of each line

COUNT_UNITS = ("عدد", "تا", "دونه", "دانه", "عددی", "تایی", "بسته", "کارتن", "شاخه", "متر", "کیلو", "جفت", "دست")
PARTY_MARKERS = ("برای", "واسه", "برا", "بنام", "بهنام")
# Words that end the name of a product in a line: what is said about it follows
LINE_MODIFIERS = ("بدون", "با", "به قیمت", "قیمت", "فی", "هر کدام", "هرکدام")
SPLITTERS = ("و",)


def _is_number(word):
	return word.replace(".", "").replace("/", "").isdigit() or word in UNITS or word in SCALES


# What may be said of a line after «بدون» or «با»
SAID_TERMS = {"تخفیف", "مالیات", "قیمت", "ارزش", "درصد"}
# Words that end a party's name: the command and what is said of the order («... برای عباسی فاکتور کن بدون مالیات»)
PARTY_ENDS = set(COMMAND_WORDS) | {"بدون", "با", "فی", "قیمت"}


def order_parts(text, command_words=(), keep=()):
	"""The lines of an order said in one sentence, its party and what is said of each line:
	«یک فاکتور برای خبازیان بزن ۱ عدد درب شیشه ای و ۱۰ عدد مهره m5 بدون تخفیف» gives the party «خبازیان» and two
	lines: (1, «درب شیشه ای»), (10, «مهره m5», «بدون تخفیف»).

	A count is a number followed by a unit («عدد»، «تا») or by the first word of a name; the numbers after it are
	part of the name («فر ۱۱۵۴ عرض ۵۰»). «و», «،» and «+» part lines, except inside the names in `keep` (names of the
	database that have them: «قلم و قلتک»، «رنگ + قلم»). The party is what follows «برای» up to a count or a word of
	the command. `command_words` are the stems of the command («فاکتور»، «بزن»): out of names, except after a count."""
	raw = re.sub(r"[،,](?!\d)|(?<!\d)[،,]|\n", " و ", text or "")
	raw = re.sub(r"\s\+\s|\+", " + ", raw)
	words = normalize(raw).split()
	# The «و» and «+» inside a name kept are not where a line ends
	protected = set()
	for name in keep:
		name_words = normalize(name).replace("+", " + ").split()
		size = len(name_words)
		for start in range(len(words) - size + 1):
			if words[start:start + size] == name_words:
				protected.update(start + i for i, w in enumerate(name_words) if w in ("و", "+"))
	parts, current = [], []
	numberish = set(UNITS) | set(SCALES)
	for index, word in enumerate(words):
		before = words[index - 1] if index else ""
		after = words[index + 1] if index + 1 < len(words) else ""
		in_number = word == "و" and before in numberish and after in numberish
		if word in ("و", "+") and index not in protected and not in_number:
			if current:
				parts.append(current)
			current = []
		else:
			current.append(word)
	if current:
		parts.append(current)
	commands = {stem(w) for w in command_words}

	def is_command(word):
		return word in commands or stem(word) in commands

	party, lines = None, []
	for part in parts:
		# The party: after «برای», up to a count or a word of the command
		index = next((i for i, w in enumerate(part) if w in PARTY_MARKERS), None)
		if index is not None:
			end, whole = index + 1, False
			for name in keep:
				# A whole name of the database after the marker (and a title) is the party, whatever words it has
				name_words = normalize(name).split()
				for at in (index + 1, index + 2):
					if part[at:at + len(name_words)] == name_words and party is None:
						end, whole = max(end, at + len(name_words)), True
			while not whole and end < len(part) and not is_command(part[end]) and part[end] not in PARTY_ENDS and not (
					_is_number(part[end]) and (end + 1 < len(part) and (part[end + 1] in COUNT_UNITS or not _is_number(part[end + 1])))):
				end += 1
			if end > index + 1 and party is None:
				party = " ".join(part[index + 1:end])
			part = part[:index] + part[end:]
		# The count: the first number followed by a unit, or by a word when no name is begun before it («فر ریلی
		# ۱۴۵۶ عرض ۸۰»: those are numbers of the name); a count with its unit after the name («فر پیتزا ۲ عدد»)
		count, start, before = None, None, []
		for i, word in enumerate(part):
			if not _is_number(word):
				continue
			j = i
			while j < len(part) and (_is_number(part[j]) or part[j] == "و"):
				j += 1
			begun = [w for w in part[:i] if not (_is_number(w) or is_command(w) or w in STOP or w in COUNT_UNITS)]
			if j < len(part) and part[j] in COUNT_UNITS:
				count, start = words_number(part[i:j]) if not part[i].replace(".", "").isdigit() else float(part[i]), j + 1
				before = begun
				break
			if j < len(part) and not is_command(part[j]) and i == j - 1 and not begun:
				value = float(part[i]) if part[i].replace(".", "").isdigit() else words_number(part[i:j])
				count, start = value, j
				break
		if start is None:
			name_words = [w for w in part if not is_command(w) and w not in STOP]
		else:
			name_words = before + part[start:]
		# What is said of the line: «بدون تخفیف»، «با تخفیف همیشگی»، «به قیمت ۲ میلیون»
		said, name = [], []
		for i, word in enumerate(name_words):
			# «بدون»/«با» start what is said only before its terms: «بدون پایه» is part of a name, «بدون تخفیف» is not
			terms = word in ("بدون", "با") and any(w in SAID_TERMS or stem(w) in SAID_TERMS for w in name_words[i + 1:i + 4])
			if terms or word in ("فی", "قیمت") or (word == "به" and i + 1 < len(name_words) and name_words[i + 1] == "قیمت"):
				said = name_words[i:]
				break
			name.append(word)
		name = [w for w in name if not (start is None and is_command(w))]
		while name and (is_command(name[-1]) or name[-1] in STOP):
			name.pop()
		if name or count is not None:
			lines.append({"count": count, "name": " ".join(name), "said": " ".join(said)})
	return {"party": party, "lines": lines}
