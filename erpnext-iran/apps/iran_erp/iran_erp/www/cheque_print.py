"""A cheque printed on its leaf: /cheque_print?cheque=CHQ-...&layout=...&test=1

The page is the size of the cheque and every item sits where the layout (Iran Cheque Layout)
says, in millimetres from the top right corner. «test=1» draws a centimetre grid instead of
using the leaf, to line the layout up with the bank's cheque on plain paper first.
"""

import frappe
from frappe import _
from frappe.utils import flt

from iran_erp.utils.words import amount_words, date_words, jalali_date

no_cache = 1

ITEMS = ("date", "date_words", "amount_words", "payee", "payee_id", "amount", "purpose")

DEFAULT_LAYOUT = {
	"page_width": 180,
	"page_height": 80,
	"font_size": 11,
	"offset_x": 0,
	"offset_y": 0,
	"date_x": 22,
	"date_y": 12,
	"date_words_x": 70,
	"date_words_y": 12,
	"amount_words_x": 40,
	"amount_words_y": 30,
	"payee_x": 40,
	"payee_y": 41,
	"payee_id_x": 120,
	"payee_id_y": 41,
	"amount_x": 140,
	"amount_y": 52,
	"purpose_x": 40,
	"purpose_y": 52,
}


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to print cheques"), frappe.PermissionError)
	name = frappe.form_dict.get("cheque")
	cheque = frappe.get_doc("Iran Cheque", name)
	if not frappe.has_permission("Iran Cheque", "print", doc=cheque):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	layout_name = frappe.form_dict.get("layout") or frappe.db.get_single_value(
		"Iran ERP Settings", "cheque_layout"
	)
	layout = dict(DEFAULT_LAYOUT)
	if layout_name and frappe.db.exists("Iran Cheque Layout", layout_name):
		saved = frappe.get_doc("Iran Cheque Layout", layout_name).as_dict()
		layout.update({k: flt(saved[k]) for k in DEFAULT_LAYOUT if saved.get(k) is not None})

	payee_id = ""
	if cheque.party_type in ("Customer", "Supplier") and cheque.party:
		payee_id = frappe.db.get_value(cheque.party_type, cheque.party, "iran_national_id") or ""
		if not payee_id and cheque.party_type == "Supplier":
			payee_id = frappe.db.get_value("Iran Investor", {"supplier": cheque.party}, "national_id") or ""

	amount = f"{int(flt(cheque.amount)):,}"
	values = {
		"date": jalali_date(cheque.due_date),
		"date_words": date_words(cheque.due_date),
		"amount_words": amount_words(cheque.amount),
		"payee": cheque.party_name or "",
		"payee_id": payee_id,
		"amount": f"#{amount}#",
		"purpose": cheque.remarks or "",
	}
	context.no_breadcrumbs = True
	context.cheque = cheque
	context.layout = layout
	context.test = frappe.form_dict.get("test") == "1"
	context.items = [
		{
			"key": key,
			"text": values[key],
			"right": flt(layout[f"{key}_x"]) - flt(layout["offset_x"]),
			"top": flt(layout[f"{key}_y"]) + flt(layout["offset_y"]),
		}
		for key in ITEMS
	]
	context.title = _("Print Cheque") + f" {cheque.cheque_number or cheque.name}"
	return context
