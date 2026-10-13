import frappe


def execute():
	# 8 steps was too few for requests that create items, customers and invoices together
	if (frappe.db.get_single_value("Iran AI Settings", "max_steps") or 0) <= 8:
		frappe.db.set_single_value("Iran AI Settings", "max_steps", 20)
