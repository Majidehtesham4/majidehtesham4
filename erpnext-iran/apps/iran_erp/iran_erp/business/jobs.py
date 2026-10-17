"""Every day: the profit of instalments that fell due becomes income, the profit owed to investors
is entered, and the status of every running contract follows its cheques."""

import frappe
from frappe.utils import nowdate


def daily():
	today = nowdate()
	for name in frappe.get_all(
		"Iran Instalment Sale",
		filters={"docstatus": 1, "status": ("in", ("Active", "Overdue"))},
		pluck="name",
	):
		_run(
			"Iran Instalment Sale",
			name,
			lambda doc: (doc.recognize_interest(today), doc.update_status(today)),
		)
	for name in frappe.get_all(
		"Iran Investment Contract",
		filters={"docstatus": 1, "status": ("in", ("Active", "Matured"))},
		pluck="name",
	):
		_run(
			"Iran Investment Contract", name, lambda doc: (doc.accrue_profit(today), doc.update_status(today))
		)


def _run(doctype, name, work):
	try:
		work(frappe.get_doc(doctype, name))
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"{doctype} {name}: daily update failed")
