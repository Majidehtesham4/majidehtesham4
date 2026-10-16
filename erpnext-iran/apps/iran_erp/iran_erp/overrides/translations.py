"""Translations for ERPNext's Banking page (/banking).

The page asks for `frappe.translate.get_boot_translations`, which this version of Frappe does not
have. The error that comes back replaced the translations the page already had with nothing, so the
whole page was in English. Hooked in through override_whitelisted_methods.
"""

import frappe
from frappe.translate import get_all_translations


@frappe.whitelist()
def get_boot_translations(v: str | None = None, lang: str | None = None) -> dict[str, str]:
	# Only the session's own language: the page passes it, but the user's setting decides
	return get_all_translations(frappe.local.lang)


def site_language_for_guests():
	"""The sign-in page and the other public pages in the site's language.

	A visitor who has not signed in got the language their browser asks for, so an English browser
	saw the sign-in page in English. A language they picked themselves (the page's language menu
	or `?_lang=`) still wins.
	"""
	if frappe.session.user != "Guest" or frappe.form_dict.get("_lang"):
		return
	request = getattr(frappe.local, "request", None)
	if request is not None and request.cookies.get("preferred_language"):
		return
	language = frappe.db.get_default("lang")
	if language and language.startswith("fa"):
		frappe.local.lang = language
