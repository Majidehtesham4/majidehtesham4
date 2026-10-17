"""Numbers and dates in Persian words, as they are written on cheques and contracts.

number_words(1_250_000)        «یک میلیون و دویست و پنجاه هزار»
amount_words(1_250_000)        «یک میلیون و دویست و پنجاه هزار ریال»
date_words("2026-11-06")       «پانزدهم آبان یک هزار و چهارصد و پنج»
"""

import jdatetime
from frappe.utils import cint, getdate

ONES = ["", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه"]
TEENS = ["ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده"]
TENS = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
HUNDREDS = ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"]
SCALES = ["", "هزار", "میلیون", "میلیارد", "هزار میلیارد", "میلیون میلیارد"]
MONTHS = [
	"فروردین",
	"اردیبهشت",
	"خرداد",
	"تیر",
	"مرداد",
	"شهریور",
	"مهر",
	"آبان",
	"آذر",
	"دی",
	"بهمن",
	"اسفند",
]


def _below_thousand(n: int) -> str:
	parts = []
	if n >= 100:
		parts.append(HUNDREDS[n // 100])
		n %= 100
	if 10 <= n < 20:
		parts.append(TEENS[n - 10])
	else:
		if n >= 20:
			parts.append(TENS[n // 10])
		if n % 10:
			parts.append(ONES[n % 10])
	return " و ".join(parts)


def number_words(number) -> str:
	n = abs(cint(number))
	if n == 0:
		return "صفر"
	groups = []
	scale = 0
	while n:
		n, part = divmod(n, 1000)
		if part:
			words = _below_thousand(part)
			groups.append(f"{words} {SCALES[scale]}".strip())
		scale += 1
	text = " و ".join(reversed(groups))
	return f"منفی {text}" if cint(number) < 0 else text


def amount_words(amount, currency: str = "ریال") -> str:
	return f"{number_words(amount)} {currency}".strip()


def ordinal_words(number) -> str:
	"""یکم، دوم، سوم، ... سی‌ام"""
	words = number_words(number)
	if words.endswith("سه"):
		return words[:-2] + "سوم"
	if words.endswith("سی"):
		return words + "‌ام"
	return words + "م"


def date_words(date) -> str:
	j = jdatetime.date.fromgregorian(date=getdate(date))
	return f"{ordinal_words(j.day)} {MONTHS[j.month - 1]} {number_words(j.year)}"


def jalali_date(date) -> str:
	j = jdatetime.date.fromgregorian(date=getdate(date))
	return f"{j.year:04d}/{j.month:02d}/{j.day:02d}"
