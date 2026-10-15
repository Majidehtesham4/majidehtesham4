"""ERPNext's Banking page, with Jalali dates and the labels it leaves in English translated.

The page itself is ERPNext's (www/banking.html includes it); this app's page is found first, so two
small scripts can be added after it. See public/js/banking_page.js.
"""

from erpnext.www import banking

no_cache = 1


def get_context(context):
	return banking.get_context(context)
