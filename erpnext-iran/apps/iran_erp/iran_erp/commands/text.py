"""Persian text helpers for the command engine: normalizing, tokens, numbers, amounts and dates."""

import datetime
import re

import jdatetime
from frappe.utils import add_days, getdate, nowdate

from iran_erp.utils.jalali import MONTH_NAMES

_CHARS = str.maketrans(
	{
		"ي": "ی",
		"ى": "ی",
		"ئ": "ی",
		"ك": "ک",
		"ة": "ه",
		"ۀ": "ه",
		"أ": "ا",
		"إ": "ا",
		"آ": "ا",
		"ؤ": "و",
		"ـ": "",
		# A half space is typed as a space as often as not; joined endings are glued back in pieces()
		"\u200c": " ",
		"‏": "",
		"‎": "",
		**{d: str(i) for i, d in enumerate("۰۱۲۳۴۵۶۷۸۹")},
		**{d: str(i) for i, d in enumerate("٠١٢٣٤٥٦٧٨٩")},
		"٫": ".",
		"٪": "%",
	}
)
_DIACRITICS = re.compile(r"[ً-ٰٟ]")
_THOUSANDS = re.compile(r"(?<=\d)[,٬،](?=\d{3}(?!\d))")
_PUNCTUATION = re.compile(r"[^\w\s%./:,-]|_")
SEPARATOR = ","
# Written apart from the word they belong to: "فاکتور ها", "می خوام"
_SUFFIXES = {
	"ها",
	"های",
	"هایی",
	"هایم",
	"هایش",
	"هامون",
	"ای",
	"ام",
	"ات",
	"اش",
	"تر",
	"ترین",
	"مون",
	"تون",
	"شون",
}
_PREFIXES = {"می", "نمی"}


def normalize(text: str) -> str:
	"""One spelling for the many ways Persian is typed, so "فاكتورها" matches "فاکتور‌ها"."""
	text = _DIACRITICS.sub("", str(text or "")).translate(_CHARS).lower()
	text = _THOUSANDS.sub("", text)
	# Commas, semicolons and new lines separate the lines of a list, so they stay as their own word
	text = re.sub(r"[،؛;\n,]+", " , ", text)
	text = text.replace("%", " درصد ")
	text = _PUNCTUATION.sub(" ", text)
	# A dot or slash only matters inside numbers and dates
	text = re.sub(r"(?<!\d)[./:]|[./:](?!\d)", " ", text)
	# A dash stays inside codes and document names (ACC-SINV-2026-00006), and goes elsewhere
	text = re.sub(r"(?<!\w)-|-(?!\w)", " ", text)
	return " ".join(text.split())


_ARABIC_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ـ": ""})


def pieces(text: str) -> list[tuple[str, str]]:
	"""(normalized word, the word as the user wrote it) pairs; the original keeps its digits and آ."""
	out = []
	for raw in str(text or "").split():
		words = normalize(raw).split()
		clean = re.sub(r"^[^\w]+|[^\w]+$", "", raw.translate(_ARABIC_LETTERS)) or raw
		for word in words:
			original = clean if len(words) == 1 else word
			if word == SEPARATOR:
				original = SEPARATOR
			if out and (word in _SUFFIXES or out[-1][0] in _PREFIXES):
				joiner = "\u200c" if word in _SUFFIXES or out[-1][0] in _PREFIXES else " "
				out[-1] = (out[-1][0] + word, out[-1][1] + joiner + original)
			else:
				out.append((word, original))
	return _join_compounds(out)


# Two words that make one, so "پیش فاکتور" (quotation) is not read as "فاکتور" (invoice)
COMPOUNDS = {
	("پیش", "فاکتور"),
	("پیش", "فاکتورها"),
	("تامین", "کننده"),
	("تامین", "کنندگان"),
	("پیش", "نویس"),
	("پیش", "نویسها"),
}


def _join_compounds(out):
	joined = []
	for word, original in out:
		if joined and (joined[-1][0], word) in COMPOUNDS:
			joined[-1] = (joined[-1][0] + word, joined[-1][1] + "\u200c" + original)
		else:
			joined.append((word, original))
	return joined


def tokens(text: str) -> list[str]:
	return [word for word, _ in pieces(text)]


_STEM_SUFFIXES = (
	"هامون",
	"هاتون",
	"هاشون",
	"هایی",
	"هایم",
	"هایش",
	"های",
	"هام",
	"هات",
	"هاش",
	"ها",
	"مون",
	"تون",
	"شون",
	"ات",
)


def stem(token: str) -> str:
	"""A light stem: plural and possessive endings off, for matching only.

	Spoken plurals and possessives count too: "مشتریا" (مشتری‌ها), "طلبمون" (طلب‌مان).
	"""
	for suffix in _STEM_SUFFIXES:
		if token.endswith(suffix) and len(token) - len(suffix) >= 3:
			return token[: -len(suffix)]
	# Past participles read like the past tense: "واریز کرده" as "واریز کرد", "گرفته" as "گرفت"
	if len(token) >= 4 and token.endswith(("ده", "ته")):
		return token[:-1]
	# "مشتریا", "کارمندا": a final ا after a consonant or ی is the spoken plural
	if len(token) >= 5 and token.endswith("ا") and token[-2] not in "اوه":
		return token[:-1]
	return token


# Words that carry no meaning for matching names
STOPWORDS = {
	"را",
	"رو",
	"به",
	"از",
	"با",
	"در",
	"تو",
	"توی",
	"برای",
	"واسه",
	"که",
	"این",
	"اون",
	"ان",
	"یک",
	"یه",
	"و",
	"یا",
	"هم",
	"تا",
	"اما",
	"لطفا",
	"لطفاً",
	"بی",
	"زحمت",
	"ببخشید",
	"سلام",
	"من",
	"ما",
	"شما",
	"است",
	"هست",
	"بود",
	"باشه",
	"کن",
	"کنید",
	"بکن",
	"بکنید",
	"بده",
	"بدید",
	"میخوام",
	"میخواهم",
	"میخوایم",
	"چند",
	"چقدر",
	"چقد",
	"چی",
	"چه",
	"کدوم",
	"کدام",
	"ها",
	"های",
	"اینو",
	"اونو",
	"شده",
	"میشه",
	"بشه",
	"کنم",
	"کنیم",
	"ی",
	"دیگه",
	"الان",
	"همه",
	"تمام",
	"هنوز",
	"برام",
	"برامون",
	"واسم",
	"داریم",
	"دارم",
	"نشون",
	"نشان",
	"بیار",
	"بگو",
	"ببینم",
	"یکی",
	"میخواستم",
}

_UNITS = {
	"صفر": 0,
	"یک": 1,
	"یه": 1,
	"دو": 2,
	"سه": 3,
	"چهار": 4,
	"چار": 4,
	"پنج": 5,
	"شش": 6,
	"شیش": 6,
	"هفت": 7,
	"هشت": 8,
	"نه": 9,
	"ده": 10,
	"یازده": 11,
	"دوازده": 12,
	"سیزده": 13,
	"چهارده": 14,
	"پانزده": 15,
	"پونزده": 15,
	"شانزده": 16,
	"شونزده": 16,
	"هفده": 17,
	"هیفده": 17,
	"هجده": 18,
	"هیجده": 18,
	"نوزده": 19,
	"بیست": 20,
	"سی": 30,
	"چهل": 40,
	"پنجاه": 50,
	"شصت": 60,
	"هفتاد": 70,
	"هشتاد": 80,
	"نود": 90,
	"صد": 100,
	"یکصد": 100,
	"دویست": 200,
	"سیصد": 300,
	"چهارصد": 400,
	"پانصد": 500,
	"پونصد": 500,
	"ششصد": 600,
	"شیشصد": 600,
	"هفتصد": 700,
	"هشتصد": 800,
	"نهصد": 900,
	"نیم": 0.5,
}
_SCALES = {
	"هزار": 1_000,
	"میلیون": 1_000_000,
	"ملیون": 1_000_000,
	"میلیارد": 1_000_000_000,
	"ملیارد": 1_000_000_000,
}
_NUMBER = re.compile(r"^\d+(\.\d+)?$")
# Number words that are also ordinary words only count next to another number word
_AMBIGUOUS = {"نه", "سی", "ده", "یه", "یک", "نیم"}


class Number:
	"""A number found in the tokens, with the token positions it covers and the word after it."""

	def __init__(self, value, start, end, next_word=""):
		self.value = value
		self.start = start
		self.end = end
		self.next_word = next_word

	def __repr__(self):
		return f"Number({self.value}, {self.start}:{self.end}, {self.next_word!r})"


def find_numbers(words: list[str]) -> list[Number]:
	"""Numbers written with digits, words or both: "12", "۱۲ میلیون", "دو و نیم میلیون", "سه تا"."""
	found = []
	i = 0
	while i < len(words):
		start = i
		total, current, seen = 0, 0, False
		while i < len(words):
			word = words[i]
			if _NUMBER.match(word):
				if seen and current:
					break
				current += float(word)
				seen = True
			elif word in _UNITS and not (word in _AMBIGUOUS and not _near_number(words, i)):
				current += _UNITS[word]
				seen = True
			elif word in _SCALES and seen:
				total += (current or 1) * _SCALES[word]
				current = 0
			elif (
				word == "و"
				and seen
				and i + 1 < len(words)
				and (words[i + 1] in _UNITS or words[i + 1] in _SCALES or _NUMBER.match(words[i + 1]))
			):
				pass
			else:
				break
			i += 1
		if seen:
			value = total + current
			found.append(
				Number(
					int(value) if value == int(value) else value, start, i, words[i] if i < len(words) else ""
				)
			)
		else:
			i += 1
	return found


def _near_number(words, i):
	"""Whether the word at i sits next to another number word, so "نه" means nine and not "no"."""
	for j in (i - 1, i + 1):
		if 0 <= j < len(words) and (
			words[j] in _SCALES
			or (words[j] in _UNITS and words[j] not in _AMBIGUOUS)
			or words[j] in ("تا", "عدد", "درصد")
		):
			return True
	return False


QTY_WORDS = {
	"تا",
	"عدد",
	"دستگاه",
	"بسته",
	"کارتن",
	"کیلو",
	"کیلوگرم",
	"متر",
	"لیتر",
	"جفت",
	"شاخه",
	"ورق",
	"نفر",
	"قلم",
	"واحد",
	"دونه",
	"دانه",
}
TOMAN = {"تومان", "تومن", "تومنی", "تومانی"}
RIAL = {"ریال", "ریالی"}
PRICE_WORDS = {"قیمت", "فی", "مبلغ", "به‌قیمت", "دونهای", "دانهای", "عددی", "هرکدوم", "هرکدام"}


def to_rial(number: Number, currency: str = "IRR") -> float:
	"""An amount in the company currency: toman is ten rials."""
	value = number.value
	if number.next_word in TOMAN and currency == "IRR":
		value *= 10
	return value


MOBILE = re.compile(r"(?<!\d)(?:\+?98|0)?(9\d{9})(?!\d)")


def find_mobile(text: str) -> str | None:
	match = MOBILE.search(normalize(text).replace(" ", ""))
	return f"0{match.group(1)}" if match else None


YES = {
	"بله",
	"بلی",
	"اره",
	"اری",
	"باشه",
	"اوکی",
	"ok",
	"okay",
	"yes",
	"تایید",
	"درسته",
	"حتما",
	"بزن",
	"موافقم",
	"انجامبده",
	"ثبتکن",
	"اوکیه",
	"چشم",
	"بفرما",
}
NO = {"نه", "خیر", "نخیر", "no", "نمیخوام", "نمیخواد", "ولش", "منصرف", "بیخیال", "نکن", "نزن"}
CANCEL = {"لغو", "کنسل", "بیخیال", "انصراف", "منصرفشدم", "ولش", "cancel", "stop"}


def yes_no(text: str) -> bool | None:
	words = tokens(text)
	if not words or len(words) > 6:
		return None
	joined = "".join(words)
	if words[0] in NO or joined in NO or "بدون" in words:
		return False
	if words[0] in YES or joined in YES or "اضافه" in words or "با" == words[0]:
		return True
	return None


def is_cancel(text: str) -> bool:
	words = tokens(text)
	return bool(words) and len(words) <= 4 and (words[0] in CANCEL or "".join(words) in CANCEL)


# ---- dates ----

MONTHS = {name.replace("آ", "ا"): i + 1 for i, name in enumerate(MONTH_NAMES)}
MONTHS.update({"اردیبهشت": 2, "مرداد": 5, "امرداد": 5})
_DATE = re.compile(r"^(\d{2,4})[/.-](\d{1,2})[/.-](\d{1,4})$")
_RELATIVE_DAYS = {"امروز": 0, "دیروز": -1, "پریروز": -2, "فردا": 1, "پسفردا": 2}
ORDINAL_DAYS = {
	"اول": 1,
	"دوم": 2,
	"سوم": 3,
	"چهارم": 4,
	"پنجم": 5,
	"ششم": 6,
	"هفتم": 7,
	"هشتم": 8,
	"نهم": 9,
	"دهم": 10,
	"اخر": 0,
}


def today() -> datetime.date:
	return getdate(nowdate())


def _jalali_to_date(year, month, day):
	try:
		return jdatetime.date(int(year), int(month), int(day)).togregorian()
	except ValueError:
		return None


def _full_date(text):
	"""A written date: 1405/08/01 (Jalali) or 2026-10-23 (Gregorian)."""
	match = _DATE.match(text)
	if not match:
		return None
	a, b, c = (int(x) for x in match.groups())
	if a > 1700:
		try:
			return datetime.date(a, b, c)
		except ValueError:
			return None
	if c > 1300 and a <= 31:
		a, c = c, a
	if a < 100:
		a += 1400
	return _jalali_to_date(a, b, c)


def find_date(words: list[str]) -> tuple[datetime.date | None, set[int]]:
	"""The first date in the tokens and the token positions it used."""
	base = today()
	joined = ["".join(words[i : i + 2]) for i in range(len(words))]
	for i, word in enumerate(words):
		date = _full_date(word)
		if date:
			return date, {i}
		if word in _RELATIVE_DAYS or joined[i] in _RELATIVE_DAYS:
			used = {i} if word in _RELATIVE_DAYS else {i, i + 1}
			return add_days(base, _RELATIVE_DAYS.get(word, _RELATIVE_DAYS.get(joined[i]))), used
		if word in MONTHS:
			month = MONTHS[word]
			day, used = None, {i}
			if i > 0 and (words[i - 1].isdigit() or words[i - 1] in ORDINAL_DAYS):
				day = int(words[i - 1]) if words[i - 1].isdigit() else ORDINAL_DAYS[words[i - 1]]
				used.add(i - 1)
			if day is None:
				continue
			jtoday = jdatetime.date.fromgregorian(date=base)
			year = jtoday.year
			if i + 1 < len(words) and words[i + 1].isdigit() and len(words[i + 1]) == 4:
				year = int(words[i + 1])
				used.add(i + 1)
			if day == 0:
				day = 31 if month <= 6 else 30
				while day and not _jalali_to_date(year, month, day):
					day -= 1
			date = _jalali_to_date(year, month, day)
			if date:
				return date, used
	# "۱۰ روز دیگه", "دو هفته بعد", "یک ماه دیگر"
	for number in find_numbers(words):
		unit = number.next_word
		after = words[number.end + 1] if number.end + 1 < len(words) else ""
		if unit in ("روز", "هفته", "ماه") and after in ("دیگه", "دیگر", "بعد", "اینده"):
			days = number.value * {"روز": 1, "هفته": 7, "ماه": 30}[unit]
			return add_days(base, int(days)), set(range(number.start, number.end + 2))
	return None, set()


def _jalali_month_bounds(year, month):
	start = jdatetime.date(year, month, 1)
	end = (jdatetime.date(year + (month == 12), month % 12 + 1, 1)) - jdatetime.timedelta(days=1)
	return start.togregorian(), end.togregorian()


def find_period(words: list[str], default=None) -> tuple[tuple | None, str]:
	"""A date range named in the message, with a Persian label: "این ماه", "دیروز", "مهر", "۳۰ روز گذشته"."""
	base = today()
	jtoday = jdatetime.date.fromgregorian(date=base)
	text = " " + " ".join(words) + " "
	past = r"(گذشته|قبل|پیش|قبلی)"

	def has(pattern):
		return re.search(pattern, text)

	# Saturday is the first day of the Iranian week
	week_start = add_days(base, -((base.weekday() + 2) % 7))
	if has(r" امروز "):
		return (base, base), "امروز"
	if has(r" دیروز "):
		day = add_days(base, -1)
		return (day, day), "دیروز"
	if has(rf" هفته {past} "):
		return (add_days(week_start, -7), add_days(week_start, -1)), "هفته گذشته"
	if has(r" (این|همین|جاری) هفته ") or has(r" هفته (جاری|اخیر) "):
		return (week_start, base), "این هفته"
	if has(rf" ماه {past} "):
		year, month = (jtoday.year, jtoday.month - 1) if jtoday.month > 1 else (jtoday.year - 1, 12)
		return _jalali_month_bounds(year, month), "ماه گذشته"
	if has(r" (این|همین|جاری) ماه ") or has(r" ماه (جاری|اخیر) "):
		return (_jalali_month_bounds(jtoday.year, jtoday.month)[0], base), "این ماه"
	season = (jtoday.month - 1) // 3
	if has(rf" (فصل|سه ?ماهه) {past} "):
		year, season = (jtoday.year, season - 1) if season else (jtoday.year - 1, 3)
		return (
			_jalali_month_bounds(year, season * 3 + 1)[0],
			_jalali_month_bounds(year, season * 3 + 3)[1],
		), "فصل گذشته"
	if has(r" (این|همین|جاری) (فصل|سه ?ماهه) ") or has(r" فصل جاری "):
		return (_jalali_month_bounds(jtoday.year, season * 3 + 1)[0], base), "این فصل"
	if has(rf" (سال {past}|پارسال) "):
		start = jdatetime.date(jtoday.year - 1, 1, 1).togregorian()
		end = jdatetime.date(jtoday.year, 1, 1).togregorian() - datetime.timedelta(days=1)
		return (start, end), "سال گذشته"
	if has(r" (امسال|(این|همین|جاری) سال|سال جاری) "):
		return (jdatetime.date(jtoday.year, 1, 1).togregorian(), base), "امسال"
	for number in find_numbers(words):
		after = words[number.end + 1] if number.end + 1 < len(words) else ""
		if number.next_word in ("روز", "هفته", "ماه") and after in ("گذشته", "اخیر", "قبل", "پیش"):
			days = int(number.value * {"روز": 1, "هفته": 7, "ماه": 30}[number.next_word])
			return (add_days(base, -days + 1), base), f"{number.value} {number.next_word} گذشته"
	for i, word in enumerate(words):
		if word in MONTHS and not (i > 0 and (words[i - 1].isdigit() or words[i - 1] in ORDINAL_DAYS)):
			month = MONTHS[word]
			year = jtoday.year if month <= jtoday.month else jtoday.year - 1
			if i + 1 < len(words) and words[i + 1].isdigit() and len(words[i + 1]) == 4:
				year = int(words[i + 1])
			return _jalali_month_bounds(year, month), f"{MONTH_NAMES[month - 1]} {year}"
	# "از ۱۴۰۵/۰۷/۰۱ تا ۱۴۰۵/۰۷/۳۰"
	dates = [d for d in (_full_date(w) for w in words) if d]
	if len(dates) >= 2:
		return (min(dates[:2]), max(dates[:2])), "بازه انتخابی"
	return default, ""
