"""Sites made without the icon grid opened on the «Apps» page: two «ERP-VERON» folders, and no
icons for the business's own pages. They get the grid; after_migrate then adds the business's icons
and hides the parts it does not use."""

import frappe


def execute():
	if frappe.db.get_single_value("Desktop Settings", "desktop_page") == "Desktop Icons":
		return
	from iran_erp.desktop import use_icon_grid

	use_icon_grid()
