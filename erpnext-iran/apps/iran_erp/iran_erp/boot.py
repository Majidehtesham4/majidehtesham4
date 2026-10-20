import frappe


def boot_session(bootinfo):
	from iran_erp.ai.openrouter import has_api_key

	ai_on = bool(frappe.db.get_single_value("Iran AI Settings", "enabled") and has_api_key())
	commands_on = bool(frappe.db.get_single_value("Iran AI Settings", "commands_enabled"))
	# The chat opens when either the built-in commands or an AI model can answer
	bootinfo.iran_ai_enabled = ai_on or commands_on
	bootinfo.iran_ai_model_enabled = ai_on
	# Administrators see the assistant button even before it is set up, so they can find the settings
	bootinfo.iran_ai_can_configure = "System Manager" in frappe.get_roles()
	bootinfo.iran_ai_voice = frappe.db.get_single_value("Iran AI Settings", "voice_input") or "Browser"
	# Jalali input is on until someone turns it off in Iran ERP Settings
	jalali_input = frappe.db.get_singles_dict("Iran ERP Settings").get("jalali_date_input")
	bootinfo.iran_jalali_input = jalali_input is None or bool(int(jalali_input))
	start_page = frappe.db.get_singles_dict("Iran ERP Settings").get("open_start_page")
	bootinfo.iran_open_start_page = start_page is None or bool(int(start_page))
	bootinfo.iran_version = frappe.get_attr("iran_erp.__version__")
	from iran_erp.build import build_label

	bootinfo.iran_build = build_label()
	bootinfo.iran_trade_name = frappe.db.get_single_value("Iran ERP Settings", "trade_name") or ""
	from iran_erp.business.visibility import home_page

	# The page the desk opens on: the business's own home, such as a car dealership's dashboard
	bootinfo.iran_home_page = home_page()
	# An investor's login opens on their own account and has no use for the rest of the desk
	others = set(frappe.get_roles()) - {"All", "Guest", "Desk User", "Investor"}
	bootinfo.iran_investor_only = "Investor" in frappe.get_roles() and not others
	if bootinfo.iran_investor_only:
		bootinfo.iran_ai_enabled = bootinfo.iran_ai_can_configure = False
		bootinfo.iran_open_start_page = False
	# Until the business is described in Easy Setup, an administrator's desk opens there
	bootinfo.iran_setup_pending = (
		not bootinfo.iran_investor_only and "System Manager" in frappe.get_roles() and _setup_pending()
	)
	_rebrand_apps(bootinfo)


def _setup_pending() -> bool:
	import json

	done = json.loads(frappe.db.get_single_value("Iran Setup", "steps_done") or "[]")
	return "business" not in done


def _rebrand_apps(bootinfo):
	"""The desk header and app switcher show ERP-VERON instead of ERPNext and Frappe."""
	from iran_erp.install import BRAND, BRAND_LOGO

	# One icon for the whole system: Frappe's own «Framework» (developer tools, /app/build) would be
	# a second «ERP-VERON»; it stays reachable by its address
	bootinfo.app_data = [
		app
		for app in bootinfo.get("app_data") or []
		if app.get("app_name") != "frappe" and (app.get("app_name") != "iran_erp" or app.get("app_route"))
	]
	for app in bootinfo.app_data:
		if app.get("app_name") in ("erpnext", "iran_erp"):
			app["app_logo_url"] = BRAND_LOGO
			app["app_title"] = BRAND
