"""The Shamsi (Jalali) calendar: conversion, the start of a Shamsi month, quarter or year, and dates
formatted with an LDML pattern (as babel's) in Shamsi."""

import datetime

MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
SEASONS = ["بهار", "تابستان", "پاییز", "زمستان"]


def to_jalali(value):
	"""(year, month, day) in Shamsi of a date"""
	gy, gm, gd = value.year, value.month, value.day
	g_d_m = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
	gy2 = gy + 1 if gm > 2 else gy
	days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
	jy = -1595 + 33 * (days // 12053)
	days %= 12053
	jy += 4 * (days // 1461)
	days %= 1461
	if days > 365:
		jy += (days - 1) // 365
		days = (days - 1) % 365
	if days < 186:
		return jy, 1 + days // 31, 1 + days % 31
	return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def to_gregorian(jy, jm, jd):
	"""The date of a Shamsi day"""
	jy += 1595
	days = -355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd
	days += (jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186
	gy = 400 * (days // 146097)
	days %= 146097
	if days > 36524:
		days -= 1
		gy += 100 * (days // 36524)
		days %= 36524
		if days >= 365:
			days += 1
	gy += 4 * (days // 1461)
	days %= 1461
	if days > 365:
		gy += (days - 1) // 365
		days = (days - 1) % 365
	return datetime.date(gy, 1, 1) + datetime.timedelta(days=days)


def month_length(jy, jm):
	if jm <= 6:
		return 31
	if jm <= 11:
		return 30
	return (to_gregorian(jy + 1, 1, 1) - to_gregorian(jy, 12, 1)).days


def period_start(value, granularity):
	"""The first day of the Shamsi month, quarter (season) or year of a date"""
	jy, jm, _jd = to_jalali(value)
	if granularity == "quarter":
		jm = (jm - 1) // 3 * 3 + 1
	elif granularity == "year":
		jm = 1
	return to_gregorian(jy, jm, 1)


def period_next(start, granularity):
	"""The first day of the following Shamsi month, quarter or year"""
	jy, jm, _jd = to_jalali(start)
	jm += {"month": 1, "quarter": 3, "year": 12}[granularity]
	jy, jm = jy + (jm - 1) // 12, (jm - 1) % 12 + 1
	return to_gregorian(jy, jm, 1)


def period_label(start, granularity):
	jy, jm, _jd = to_jalali(start)
	if granularity == "month":
		return f"{MONTHS[jm - 1]} {jy}"
	if granularity == "quarter":
		return f"{SEASONS[(jm - 1) // 3]} {jy}"
	return str(jy)


def week_label(start, week_start=6):
	"""«هفته 32 1405» for a week starting on start; week_start as Odoo's (1 = Monday ... 7 = Sunday).
	The first week of a Shamsi year is the one holding 1 Farvardin."""
	jy = to_jalali(start + datetime.timedelta(days=6))[0]
	year_start = to_gregorian(jy, 1, 1)
	offset = (year_start.weekday() - (week_start - 1)) % 7
	return f"هفته {max(0, (start - year_start).days + offset) // 7 + 1} {jy}"


def format_pattern(value, pattern, other):
	"""value (a date, or a datetime already in its time zone) formatted with an LDML pattern, the
	date fields in Shamsi; other(field) formats the rest (weekday, hours...) as babel does."""
	import babel.dates

	parsed = babel.dates.parse_pattern(pattern)
	jy, jm, jd = to_jalali(value)
	fields = {}
	for field in _fields(parsed.format):
		kind, width = field[0], len(field)
		if kind == "y":
			fields[field] = f"{jy % 100:02d}" if width == 2 else str(jy).zfill(width)
		elif kind in "ML":
			fields[field] = MONTHS[jm - 1] if width >= 3 else str(jm).zfill(width)
		elif kind == "d":
			fields[field] = str(jd).zfill(width)
		elif kind == "Q":
			quarter = (jm - 1) // 3
			fields[field] = SEASONS[quarter] if width >= 3 else str(quarter + 1)
		elif kind == "D":
			fields[field] = str((value - to_gregorian(jy, 1, 1)).days + 1)
		else:
			fields[field] = other(field)
	return parsed.format % fields


def _fields(fmt):
	import re

	return re.findall(r"%\((\w+)\)s", fmt)
