"""Validation of Iranian identifiers (کد ملی، شناسه ملی، کد اقتصادی)."""

import re

_NON_LATIN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_digits(value) -> str:
	"""Convert Persian/Arabic digits to Latin and strip spaces and dashes."""
	return re.sub(r"[\s\-]", "", str(value or "").translate(_NON_LATIN_DIGITS))


def is_valid_national_code(code) -> bool:
	"""Validate a 10 digit personal national code (کد ملی)."""
	code = normalize_digits(code)
	if not re.fullmatch(r"\d{10}", code) or len(set(code)) == 1:
		return False
	check = int(code[9])
	total = sum(int(code[i]) * (10 - i) for i in range(9)) % 11
	return check == total if total < 2 else check == 11 - total


def is_valid_legal_national_id(code) -> bool:
	"""Validate an 11 digit national ID of a legal entity (شناسه ملی اشخاص حقوقی)."""
	code = normalize_digits(code)
	if not re.fullmatch(r"\d{11}", code):
		return False
	decimal = int(code[9]) + 2
	coefficients = (29, 27, 23, 19, 17, 29, 27, 23, 19, 17)
	total = sum((int(code[i]) + decimal) * coefficients[i] for i in range(10)) % 11
	return int(code[10]) == (0 if total == 10 else total)


def is_valid_economic_code(code) -> bool:
	"""Validate an economic code (کد اقتصادی).

	Since the tax reform the economic code equals the national code (10 digits)
	for individuals and the national ID (11 digits) for legal entities; older
	12 digit codes are accepted as-is.
	"""
	code = normalize_digits(code)
	if len(code) == 10:
		return is_valid_national_code(code)
	if len(code) == 11:
		return is_valid_legal_national_id(code)
	return bool(re.fullmatch(r"\d{12}", code))
