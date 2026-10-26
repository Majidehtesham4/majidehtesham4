{
	"name": "ERP-VERON Moadian",
	"summary": "Electronic invoices to the Moadian service of the tax organization: tax number, invoice pattern, signing, sending on request and the result",
	"description": """
Sales invoices and credit notes to the Moadian service (سامانه مودیان) of the Iranian tax organization:

- The 22-character tax number of each invoice (memory id, date, serial, Verhoeff check digit)
- The invoice in the tax organization's pattern (sale, type 1 with the buyer or type 2), from the
  invoice lines, VAT and payments; the problems that would make it rejected are listed first
- Signed with the taxpayer's key and certificate (JWS), encrypted with the tax organization's key
  (JWE), sent to its API v2, then asked for the result (accepted or rejected with the reasons)
- Nothing is sent by itself: an accounting manager sends each invoice; the result is fetched hourly
- A sent invoice is not set back to draft; it is corrected with a credit note
- The key is made here (the request for the certificate is downloaded) or given; it is never shown

The service itself was not reachable while this was built: the packets follow the published SDKs of
the service and are tested against them, not against the live service. Send a few invoices first and
check them in the taxpayer's portal.
""",
	"version": "19.0.1.0.0",
	"category": "Accounting/Localizations",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["account", "veron_accounting", "uom"],
	"external_dependencies": {"python": ["cryptography", "requests"]},
	"data": [
		"data/moadian_data.xml",
		"views/account_move_views.xml",
		"views/res_config_settings_views.xml",
		"views/partner_product_views.xml",
	],
	"installable": True,
	"application": False,
}
