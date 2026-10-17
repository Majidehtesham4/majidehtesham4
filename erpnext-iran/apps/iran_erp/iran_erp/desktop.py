"""Switch the v16 desk home page to a flat grid of module icons.

Fresh v16 sites open on the "Apps" page, which only shows one folder per app
(ERPNext, Framework). This shows every module (Accounting, Selling, CRM, Website, ...)
directly on the home page instead.

Run with:
	bench --site <site> execute iran_erp.desktop.use_icon_grid
"""

import frappe
from frappe.desk.doctype.desktop_icon.desktop_icon import clear_every_users_desktop_icons
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

	iran_labels = {icon[0] for icon in IRAN_ICONS}
	for icon in frappe.get_all("Desktop Icon", fields=["name", "label", "icon_type", "parent_icon"]):
		if icon.label in iran_labels:
			continue
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

	add_iran_icons()

	# Saved per-user arrangements still point at the old folders
	frappe.db.delete("Desktop Layout")
	frappe.db.commit()
	frappe.clear_cache()


# label, link, image, roles that see it
IRAN_ICONS = (
	(
		"Start Page",
		"/desk/iran-start",
		"start.svg",
		(
			"System Manager",
			"Accounts Manager",
			"Accounts User",
			"Sales User",
			"Sales Manager",
			"Purchase User",
			"Purchase Manager",
			"Stock User",
			"Stock Manager",
		),
	),
	("Easy Setup", "/desk/iran-easy-setup", "setup.svg", ("System Manager", "Accounts Manager")),
	("AI Assistant", "/desk/iran-ai-settings", "ai_assistant.svg", ("System Manager",)),
	("Iran ERP Settings", "/desk/iran-erp-settings", "iran_settings.svg", ("System Manager",)),
	("Cheques", "/desk/iran-cheque", "cheques.svg", ("System Manager", "Accounts Manager", "Accounts User")),
)


def add_iran_icons():
	"""Home-screen icons for this app's own pages, which otherwise only search can find.

	They are "App" icons: a "Link" icon is only shown when it leads to a module's sidebar, while
	an App icon of an installed app is shown to anyone with one of its roles.
	"""
	add_icons(IRAN_ICONS)


def add_icons(icons):
	"""Home-screen icons from (label, link, image in public/icons, roles) rows."""
	if frappe.db.get_single_value("Desktop Settings", "desktop_page") != "Desktop Icons":
		return
	for label, link, image, roles in icons:
		values = {
			"icon_type": "App",
			"link_type": "External",
			"link": link,
			"logo_url": f"/assets/iran_erp/icons/{image}",
			"app": "iran_erp",
		}
		if frappe.db.exists("Desktop Icon", label):
			# Keeps the user's choice to hide it, but repairs icons created by older versions
			frappe.db.set_value("Desktop Icon", label, values)
			continue
		frappe.get_doc(
			{
				"doctype": "Desktop Icon",
				"label": label,
				"standard": 0,
				"hidden": 0,
				"roles": [{"role": role} for role in roles],
				**values,
			}
		).insert(ignore_permissions=True)
	clear_every_users_desktop_icons()
