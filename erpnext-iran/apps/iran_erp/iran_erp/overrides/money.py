"""Amounts with the currency written after them, kept in Persian order in any text around them.

The rial is written after the number («۳۵٬۰۰۰ ریال»). Put as plain text in a right-to-left page,
the minus of a negative amount moved to the far side of the number («۳۵٬۰۰۰- ریال»), and in a
left-to-right cell the word went to the other side of the number. Marking the number as a
left-to-right part inside a right-to-left whole keeps «-۳۵٬۰۰۰» together with «ریال» on its left,
wherever the amount is shown. The desk does the same for the amounts it formats (money.js).
"""

import sys

import frappe

# Unicode directional isolates: right-to-left, left-to-right, end of isolate
RLI, LRI, PDI = "⁧", "⁦", "⁩"

_applied = False


def isolate(number: str, words: str) -> str:
	"""«number words» in Persian order: the number on the right, the words to its left."""
	return f"{RLI}{LRI}{number}{PDI} {words}{PDI}"


def _fmt_money(original):
	def fmt_money(amount, precision=None, currency=None, format=None):
		text = original(amount, precision, currency, format)
		if not currency or not isinstance(text, str) or RLI in text:
			return text
		if not frappe.db.get_value("Currency", currency, "symbol_on_right", cache=True):
			return text
		symbol = frappe._(frappe.db.get_value("Currency", currency, "symbol", cache=True) or currency)
		suffix = f" {symbol}"
		if text.endswith(suffix):
			return isolate(text[: -len(suffix)], symbol)
		return text

	fmt_money.iran_original = original
	return fmt_money


def apply():
	"""Swap in the isolated amounts once per process."""
	global _applied
	if _applied:
		return
	_applied = True
	from frappe.utils import data

	original = data.fmt_money
	if getattr(original, "iran_original", None):
		return
	patched = _fmt_money(original)
	# Modules that imported the function by name keep their own references
	for module_name, module in list(sys.modules.items()):
		if not module or not module_name.startswith(("frappe", "erpnext", "iran_erp")):
			continue
		if getattr(module, "fmt_money", None) is original:
			module.fmt_money = patched
