import frappe


def execute():
	"""Sites set up before the command engine get it switched on, like new ones."""
	frappe.reload_doc("iran_erp", "doctype", "iran_ai_settings")
	frappe.db.set_single_value("Iran AI Settings", "commands_enabled", 1)
