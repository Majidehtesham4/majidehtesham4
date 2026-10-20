"""/showroom leads to the showroom's website: the separate site (automodiran) when there is one,
on the address set in «Iran Showroom Settings», or else on this server's port 80, where it runs
beside the system. /showroom?car=CAR-00021 leads to that car's page there."""

import frappe
from frappe.utils import cint
from urllib.parse import quote, urlsplit

no_cache = 1


def website_url() -> str:
	url = (frappe.db.get_single_value("Iran Showroom Settings", "website_url") or "").strip().rstrip("/")
	if url:
		return url if url.startswith(("http://", "https://")) else f"https://{url}"
	host = urlsplit(f"//{frappe.get_request_header('Host') or 'localhost'}").hostname or "localhost"
	scheme = frappe.get_request_header("X-Forwarded-Proto") or "http"
	return f"{scheme}://{host}"


def get_context(context):
	car = (frappe.form_dict.get("car") or "").strip()
	if cint(frappe.form_dict.get("builtin")):
		# The pages this system draws itself
		location = f"/cars/{quote(car)}" if car else "/cars"
	else:
		location = website_url() + (f"/car/{quote(car)}" if car else "/inventory")
	frappe.local.flags.redirect_location = location
	# Temporary: the address can change in the settings, and browsers keep a permanent one
	raise frappe.Redirect(302)
