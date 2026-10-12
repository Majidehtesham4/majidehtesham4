"""Switch the v16 desk home page to a flat grid of module icons.

Fresh v16 sites open on the "Apps" page, which only shows one folder per app
(ERPNext, Framework). This shows every module (Accounting, Selling, CRM, Website, ...)
directly on the home page instead.

Run with:
	bench --site <site> execute iran_erp.desktop.use_icon_grid
"""

import frappe
from frappe.desk.doctype.desktop_settings.desktop_settings import seed_desktop_icons
from frappe.utils.new_navigation_nudge import skip_new_navigation_prompt

APP_FOLDERS = ("ERPNext", "Framework", "Frappe Framework")
# Icons that duplicate another icon or only hold settings
HIDDEN_ICONS = ("Home", "ERPNext Settings", "Invoicing", "Payments", "Organization")


def use_icon_grid(icon_style: str = "Solid"):
	frappe.only_for("System Manager")

	settings = frappe.get_single("Desktop Settings")
	settings.desktop_page = "Desktop Icons"
	settings.icon_style = icon_style
	settings.save()

	# On the icon grid Frappe offers a one-time "Try the new navigation" dialog whose
	# "Try it" button switches the site straight back to the Apps page
	skip_new_navigation_prompt()

	# Normally enqueued by Desktop Settings; run it now so the grid exists right away
	seed_desktop_icons()

	for icon in frappe.get_all("Desktop Icon", fields=["name", "label", "icon_type", "parent_icon"]):
		if icon.icon_type == "App" or icon.label in HIDDEN_ICONS:
			frappe.db.set_value("Desktop Icon", icon.name, "hidden", 1)
		elif icon.parent_icon in APP_FOLDERS:
			frappe.db.set_value("Desktop Icon", icon.name, "parent_icon", None)

	# ERPNext ships no image for "Accounting" (it falls back to a letter), so reuse the Invoicing one
	if frappe.db.exists("Desktop Icon", "Accounting"):
		frappe.db.set_value(
			"Desktop Icon",
			"Accounting",
			"logo_url",
			f"/assets/erpnext/icons/desktop_icons/{icon_style.lower()}/invoicing.svg",
		)

	# Saved per-user arrangements still point at the old folders
	frappe.db.delete("Desktop Layout")
	frappe.db.commit()
	frappe.clear_cache()
