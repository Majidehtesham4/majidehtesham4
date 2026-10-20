# Copyright (c) 2026, Majid Ehtesham and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class IranIntentExample(Document):
	def validate(self):
		from iran_erp.commands.engine import INTENT_BY_NAME

		if self.capability and self.capability not in INTENT_BY_NAME:
			frappe.throw(_("Unknown capability {0}").format(self.capability))
		if self.status == "Approved" and not self.capability:
			frappe.throw(_("Choose the capability before approving"))
		if self.capability:
			self.capability_title = INTENT_BY_NAME[self.capability]["title"]

	def on_update(self):
		from iran_erp.commands.engine import reset_matcher

		reset_matcher()

	def on_trash(self):
		from iran_erp.commands.engine import reset_matcher

		reset_matcher()


@frappe.whitelist()
def check(names: str | list) -> list[dict]:
	"""Check examples against the ERP again (after the capability or the details were corrected)."""
	from iran_erp.commands.learning import evaluate

	frappe.only_for("System Manager")
	names = frappe.parse_json(names) if isinstance(names, str) and names.startswith("[") else names
	out = []
	for name in [names] if isinstance(names, str) else names:
		doc = frappe.get_doc("Iran Intent Example", name)
		out.append({"name": name, "passed": evaluate(doc) if doc.capability else False})
	return out


@frappe.whitelist()
def set_status(names: str | list, status: str):
	"""Approve or reject examples; only approved ones teach the assistant."""
	from iran_erp.commands.learning import set_status as set_one

	frappe.only_for("System Manager")
	if status not in ("Approved", "Rejected", "Proposed"):
		frappe.throw(_("Not allowed"))
	names = frappe.parse_json(names) if isinstance(names, str) and names.startswith("[") else names
	for name in [names] if isinstance(names, str) else names:
		if status == "Approved" and not frappe.db.get_value("Iran Intent Example", name, "capability"):
			frappe.throw(_("Choose the capability before approving"))
		set_one(name, status, _("By {0}").format(frappe.utils.get_fullname()))
