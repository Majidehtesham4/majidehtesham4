import frappe
from frappe import _

from iran_erp.utils.national_id import (
	is_valid_economic_code,
	is_valid_legal_national_id,
	is_valid_national_code,
	normalize_digits,
)


def validate_iranian_ids(doc, method=None):
	if doc.get("iran_national_id"):
		doc.iran_national_id = normalize_digits(doc.iran_national_id)
		code = doc.iran_national_id
		valid = is_valid_national_code(code) if len(code) == 10 else is_valid_legal_national_id(code)
		if not valid:
			frappe.throw(_("National ID {0} is not valid").format(frappe.bold(code)))

	if doc.get("iran_economic_code"):
		doc.iran_economic_code = normalize_digits(doc.iran_economic_code)
		if not is_valid_economic_code(doc.iran_economic_code):
			frappe.throw(_("Economic Code {0} is not valid").format(frappe.bold(doc.iran_economic_code)))
