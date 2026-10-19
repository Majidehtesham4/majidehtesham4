"""Only the parts a business uses are on its home screen.

The kind of business chosen in Easy Setup decides which home-screen icons are shown; every other
icon (the other modules, and the builder's tools such as Build, Data or Integrations) is hidden.
Hidden pages still open from the search bar or by their address.
"""

import frappe

# Every business sees these
COMMON = (
	"Start Page",
	"Easy Setup",
	"Accounting",
	"Financial Reports",
	"AI Assistant",
	"Iran ERP Settings",
	"Users",
	# Shown only to investors, by its roles
	"My Account",
)
# What each kind of business works with, on top of the common ones
BY_TYPE = {
	"Shop": ("Selling", "Buying", "Stock"),
	"Distribution": ("Selling", "Buying", "Stock", "CRM"),
	"Manufacturing": ("Selling", "Buying", "Stock", "Manufacturing", "Quality", "Subcontracting"),
	"Services": ("Selling", "CRM", "Projects", "Support"),
	"Contracting": ("Selling", "Buying", "Projects", "Assets"),
	"Car Dealership": ("Car Dealership", "Car Reception"),
}
# The page a business opens on after login
HOME = {"Car Dealership": "iran-dealership"}


def shown_icons(setup) -> set[str]:
	shown = set(COMMON) | set(BY_TYPE.get(setup.business_type, ()))
	keeps_stock = (setup.sells or "Goods") != "Services" and bool(setup.has_warehouse)
	if keeps_stock and setup.business_type != "Car Dealership":
		shown.add("Stock")
	else:
		shown.discard("Stock")
	if setup.uses_cheques:
		shown.add("Cheques")
	return shown


def apply(setup=None):
	"""Show the icons of the business's parts and hide the rest. Nothing changes before the kind of
	business is chosen."""
	from iran_erp.desktop import clear_every_users_desktop_icons

	setup = setup or frappe.get_single("Iran Setup")
	if not setup.business_type:
		return
	shown = shown_icons(setup)
	changed = False
	for icon in frappe.get_all(
		"Desktop Icon", filters={"parent_icon": ("is", "not set")}, fields=["name", "label", "hidden"]
	):
		hidden = 0 if icon.label in shown else 1
		if int(icon.hidden or 0) != hidden:
			frappe.db.set_value("Desktop Icon", icon.name, "hidden", hidden, update_modified=False)
			changed = True
	if changed:
		clear_every_users_desktop_icons()


def home_page() -> str:
	from iran_erp.business import RECEPTION_ROLE

	others = set(frappe.get_roles()) - {"All", "Guest", "Desk User", RECEPTION_ROLE}
	if RECEPTION_ROLE in frappe.get_roles() and not others:
		# Reception opens on the list of cars, to register the next one
		return "iran-vehicle"
	return HOME.get(frappe.db.get_single_value("Iran Setup", "business_type"), "iran-start")
