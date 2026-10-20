"""Iranian number plates: «۱۲ ب ۳۴۵ ایران ۶۷».

A plate is two digits, a letter, three digits and the two-digit code of the city («ایران ۶۷»). It is
kept as text in that order with Latin digits («12 ب 345 ایران 67»), entered in four boxes and shown
like the plate itself: the blue strip, the number and the city code beside it.
"""

import re

from frappe.utils import escape_html

from iran_erp.utils.jalali import to_persian_digits

LETTERS = (
	"الف", "ب", "پ", "ت", "ث", "ج", "د", "ز", "ژ", "س", "ش", "ص", "ط", "ع", "ف", "ق", "ک", "گ",
	"ل", "م", "ن", "و", "ه", "ی", "D", "S",
)  # fmt: skip
LATIN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك", "01234567890123456789یک")
PATTERN = re.compile(r"^(\d{2})\s*(الف|[^\d\s])\s*(\d{3})\s*(?:-|ایران)?\s*(\d{2})$")


def parse(text) -> dict | None:
	"""{"left", "letter", "middle", "city"} of a plate, or None when it is not one."""
	text = " ".join(str(text or "").translate(LATIN).split())
	match = PATTERN.match(text)
	if not match or match.group(2) not in LETTERS:
		return None
	left, letter, middle, city = match.groups()
	return {"left": left, "letter": letter, "middle": middle, "city": city}


def normal(text) -> str | None:
	"""The plate in the stored form, «12 ب 345 ایران 67», or None when it is not a plate."""
	parts = parse(text)
	if not parts:
		return None
	return f"{parts['left']} {parts['letter']} {parts['middle']} ایران {parts['city']}"


def plate_html(text, size: str = "") -> str:
	"""The plate drawn like the real one (for print formats and pages); plain text if it is not one."""
	parts = parse(text)
	if not parts:
		return escape_html(to_persian_digits(text or ""))
	d = to_persian_digits
	return (
		f'<span class="iran-plate {size}" dir="ltr">'
		'<span class="iran-plate-flag"><i></i><b>I.R.<br>IRAN</b></span>'
		f'<span class="iran-plate-number">{d(parts["left"])}<em>{escape_html(parts["letter"])}</em>'
		f'{d(parts["middle"])}</span>'
		f'<span class="iran-plate-city"><small>ایران</small>{d(parts["city"])}</span>'
		"</span>"
	)


# For print formats, which have no stylesheet of the app
PRINT_STYLE = """<style>
.iran-plate{display:inline-flex;align-items:stretch;border:2px solid #111;border-radius:5px;background:#fff;
font-weight:700;line-height:1;overflow:hidden;font-size:15pt;height:30px}
.iran-plate-flag{display:flex;flex-direction:column;justify-content:space-between;align-items:center;background:#1e3f9c;
color:#fff;padding:2px 3px;font-size:5pt;font-family:Arial,sans-serif}
.iran-plate-flag i{display:block;width:12px;height:8px;background:linear-gradient(#239f40 33%,#fff 33% 66%,#da0000 66%)}
.iran-plate-number{display:flex;align-items:center;gap:6px;padding:0 8px}
.iran-plate-number em{font-style:normal}
.iran-plate-city{display:flex;flex-direction:column;align-items:center;justify-content:center;border-left:2px solid #111;
padding:0 6px;font-size:13pt}
.iran-plate-city small{font-size:6pt}
</style>"""
