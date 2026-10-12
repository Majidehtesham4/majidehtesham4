import frappe

from iran_erp.accounts.chart import DEFAULT_VAT_RATE


def execute():
	# Settings saved before the field existed have no rate; the form would show 0
	if not frappe.db.get_single_value("Iran ERP Settings", "vat_rate"):
		frappe.db.set_single_value("Iran ERP Settings", "vat_rate", DEFAULT_VAT_RATE)
