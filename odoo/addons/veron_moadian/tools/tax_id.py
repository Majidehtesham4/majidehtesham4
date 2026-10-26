"""The 22-character unique tax number (شماره منحصر به فرد مالیاتی) of an electronic invoice.

Layout: memory ID (6) + days since 1970-01-01 in hex (5) + internal serial in hex (10) + check digit (1).
The check digit is the Verhoeff checksum of the decimal form: the memory ID with each letter
replaced by its ASCII code, the day count padded to 6 digits and the serial padded to 12 digits.
"""

import datetime
import re

EPOCH = datetime.date(1970, 1, 1)
MEMORY_ID = re.compile(r"^[A-Z0-9]{6}$")

# Verhoeff tables: multiplication in the dihedral group D5, the position permutation and the inverse
_D = (
	(0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
	(1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
	(2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
	(3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
	(4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
	(5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
	(6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
	(7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
	(8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
	(9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
	(0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
	(1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
	(5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
	(8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
	(9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
	(4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
	(2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
	(7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_digit(number: str) -> int:
	"""The check digit to append to a string of decimal digits."""
	check = 0
	for position, digit in enumerate(reversed(number)):
		check = _D[check][_P[(position + 1) % 8][int(digit)]]
	return _INV[check]


def is_valid_verhoeff(number: str) -> bool:
	check = 0
	for position, digit in enumerate(reversed(number)):
		check = _D[check][_P[position % 8][int(digit)]]
	return check == 0


def days_since_epoch(date: datetime.date) -> int:
	if isinstance(date, datetime.datetime):
		date = date.date()
	return (date - EPOCH).days


def memory_id_to_decimal(memory_id: str) -> str:
	return "".join(char if char.isdigit() else str(ord(char)) for char in memory_id)


def generate_tax_id(memory_id: str, invoice_date: datetime.date, serial: int) -> str:
	memory_id = (memory_id or "").strip().upper()
	if not MEMORY_ID.match(memory_id):
		raise ValueError("The tax memory ID must be 6 letters or digits")
	if not 0 < int(serial) < 16**10:
		raise ValueError("The internal serial must be between 1 and 16^10 - 1")
	days = days_since_epoch(invoice_date)
	decimal = memory_id_to_decimal(memory_id) + f"{days:06d}" + f"{int(serial):012d}"
	return f"{memory_id}{days:05X}{int(serial):010X}{verhoeff_digit(decimal)}"


def parse_tax_id(tax_id: str) -> dict:
	"""Split a tax number into its parts and check its check digit."""
	tax_id = (tax_id or "").strip().upper()
	if not re.fullmatch(r"[A-Z0-9]{6}[0-9A-F]{15}[0-9]", tax_id):
		return {"valid": False}
	memory_id, days, serial = tax_id[:6], int(tax_id[6:11], 16), int(tax_id[11:21], 16)
	decimal = memory_id_to_decimal(memory_id) + f"{days:06d}" + f"{serial:012d}"
	return {
		"valid": verhoeff_digit(decimal) == int(tax_id[21]),
		"memory_id": memory_id,
		"date": EPOCH + datetime.timedelta(days=days),
		"serial": serial,
	}
