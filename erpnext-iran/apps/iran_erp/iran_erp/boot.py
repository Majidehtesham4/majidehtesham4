import frappe


def boot_session(bootinfo):
	bootinfo.iran_ai_enabled = bool(
		frappe.db.get_single_value("Iran AI Settings", "enabled")
		and frappe.db.get_single_value("Iran AI Settings", "api_key")
	)
