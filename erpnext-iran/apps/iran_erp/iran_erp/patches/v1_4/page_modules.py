"""«حساب من» (iran-my-account) moved to the dealership's module, but sites made before kept it
under Iran ERP, where its files are not: investors got «file not found» instead of their
account."""

import frappe


def execute():
	if frappe.db.exists("Page", "iran-my-account"):
		frappe.db.set_value("Page", "iran-my-account", "module", "Iran Dealership", update_modified=False)
