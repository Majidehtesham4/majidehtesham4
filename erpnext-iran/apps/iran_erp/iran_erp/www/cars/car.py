"""One car of the showroom: /cars/CAR-00012 (website_route_rules in hooks.py)."""

import json

import frappe

from iran_erp.iran_dealership.showroom import car_page, settings

no_cache = 1


def get_context(context):
	# The showroom speaks Persian whatever the visitor's browser asks for
	frappe.local.lang = "fa"
	s = settings()
	if not s.enabled:
		raise frappe.PageDoesNotExistError
	car = car_page(frappe.form_dict.name)
	context.s = s
	context.car = car
	context.no_breadcrumbs = 1
	# What the page's script needs: the calculator's terms and the 3D viewer's model
	context.page_data = json.dumps(
		{
			"name": car["name"],
			"price": car["price_value"],
			"toman": s.toman,
			"months": s.months,
			"min_down_percent": s.min_down_percent,
			"monthly_rate": s.monthly_rate,
			"color": car["color_code"],
			"model_3d": car["model_3d"],
		}
	).replace("<", "\\u003c")
	if frappe.session.user != "Guest":
		context.csrf_token = frappe.sessions.get_csrf_token()
	return context
