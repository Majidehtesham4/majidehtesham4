"""Jalali (Solar Hijri) calendar helpers.

Dates are always stored in Gregorian in the database; these helpers only
convert for display, print formats and Iranian fiscal years.
"""

import datetime

import jdatetime
from frappe.utils import getdate

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

MONTH_NAMES = (
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
)


def to_persian_digits(value) -> str:
	return str(value).translate(PERSIAN_DIGITS)


def to_jalali(date) -> jdatetime.date | None:
	"""Convert a Gregorian date (date, datetime or 'YYYY-MM-DD' string) to a Jalali date."""
	if not date:
		return None
	return jdatetime.date.fromgregorian(date=getdate(date))


def to_gregorian(year: int, month: int, day: int) -> datetime.date:
	return jdatetime.date(int(year), int(month), int(day)).togregorian()


def format_jalali(date, fmt: str = "numeric", persian_digits: bool = True) -> str:
	"""Format a Gregorian date as Jalali.

	fmt: "numeric" -> 1405/07/19, "long" -> 19 مهر 1405
	"""
	jdate = to_jalali(date)
	if not jdate:
		return ""
	if fmt == "long":
		text = f"{jdate.day} {MONTH_NAMES[jdate.month - 1]} {jdate.year}"
	else:
		text = f"{jdate.year:04d}/{jdate.month:02d}/{jdate.day:02d}"
	return to_persian_digits(text) if persian_digits else text


def jalali_year_bounds(jalali_year: int) -> tuple[datetime.date, datetime.date]:
	"""First day of Farvardin and last day of Esfand of a Jalali year, in Gregorian."""
	start = jdatetime.date(int(jalali_year), 1, 1)
	end = jdatetime.date(int(jalali_year) + 1, 1, 1) - jdatetime.timedelta(days=1)
	return start.togregorian(), end.togregorian()
