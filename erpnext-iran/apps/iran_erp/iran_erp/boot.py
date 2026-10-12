import frappe


def boot_session(bootinfo):
	bootinfo.iran_ai_enabled = bool(
		frappe.db.get_single_value("Iran AI Settings", "enabled")
		and frappe.db.get_single_value("Iran AI Settings", "api_key")
	)
	# Jalali input is on until someone turns it off in Iran ERP Settings
	jalali_input = frappe.db.get_singles_dict("Iran ERP Settings").get("jalali_date_input")
	bootinfo.iran_jalali_input = jalali_input is None or bool(int(jalali_input))
