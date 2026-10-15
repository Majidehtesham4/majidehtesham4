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
