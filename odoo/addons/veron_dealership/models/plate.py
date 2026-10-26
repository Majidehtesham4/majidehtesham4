"""Iranian number plates: «۱۲ ب ۳۴۵ ایران ۶۷», two digits, a letter, three digits and the city code."""

import re

LETTERS = (
	"الف", "ب", "پ", "ت", "ث", "ج", "د", "ز", "ژ", "س", "ش", "ص", "ط", "ع", "ف", "ق", "ک", "گ",
	"ل", "م", "ن", "و", "ه", "ی", "D", "S",
)  # fmt: skip
LATIN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك", "01234567890123456789یک")
PERSIAN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
PATTERN = re.compile(r"^(\d{2})\s*(الف|[^\d\s])\s*(\d{3})\s*(?:-|ایران)?\s*(\d{2})$")


def latin(text):
	return str(text or "").translate(LATIN).strip()


def parse(text):
	"""(left, letter, middle, city) of a plate, or None"""
	match = PATTERN.match(" ".join(latin(text).split()))
	if not match or match.group(2) not in LETTERS:
		return None
	return match.groups()


def text(left, letter, middle, city):
	"""The plate in its stored form, «12 ب 345 ایران 67», or False when a part is missing or wrong"""
	left, middle, city = latin(left), latin(middle), latin(city)
	if not (re.fullmatch(r"\d{2}", left) and letter in LETTERS and re.fullmatch(r"\d{3}", middle) and re.fullmatch(r"\d{2}", city)):
		return False
	return f"{left} {letter} {middle} ایران {city}"
