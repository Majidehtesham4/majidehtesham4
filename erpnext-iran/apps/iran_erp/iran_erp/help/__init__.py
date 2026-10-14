"""The «آموزش» (help) panel: what a page is for and what each of its parts does."""

import frappe
from frappe import _

from iran_erp.help.guides import DOCTYPES, FIELD_TYPES, REPORTS, WORKSPACES


@frappe.whitelist()
def get_guide(kind: str, name: str) -> dict:
	"""kind: "doctype", "report" or "workspace"."""
	if kind == "doctype":
		guide = dict(DOCTYPES.get(name) or {})
		if frappe.db.exists("DocType", name):
			meta = frappe.get_meta(name)
			if not guide.get("about") and meta.description:
				guide["about"] = _(meta.description)
			guide["module"] = _(meta.module)
			guide["module_about"] = WORKSPACES.get(meta.module)
			guide["is_submittable"] = meta.is_submittable
		return guide
	if kind == "report":
		guide = dict(REPORTS.get(name) or {})
		if not guide.get("about") and frappe.db.exists("Report", name):
			ref = frappe.db.get_value("Report", name, "ref_doctype")
			if ref:
				guide["about"] = _("This report is based on {0} documents.").format(_(ref))
		return guide
	if kind == "workspace":
		return {"about": WORKSPACES.get(name) or WORKSPACES.get(name.title())}
	return {}


@frappe.whitelist()
def get_field_types() -> dict:
	return FIELD_TYPES
