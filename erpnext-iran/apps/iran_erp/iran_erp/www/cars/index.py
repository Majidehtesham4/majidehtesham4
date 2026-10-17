"""The showroom's cars: /cars, with filters in the address (?brand=...&max_price=...)."""

import frappe
from frappe.utils import escape_html

from iran_erp.iran_dealership.showroom import list_cars, settings

no_cache = 1


def get_context(context):
	# The showroom speaks Persian whatever the visitor's browser asks for
	frappe.local.lang = "fa"
	s = settings()
	if not s.enabled:
		raise frappe.PageDoesNotExistError
	args = {k: v for k, v in frappe.form_dict.items() if isinstance(v, str)}
	context.s = s
	# Echoed back into the form: escaped
	context.args = {k: escape_html(v) for k, v in args.items()}
	context.data = list_cars(args)
	context.featured = [c for c in context.data["cars"] if c["featured"]][:3] if not args else []
	context.no_breadcrumbs = 1
	return context
