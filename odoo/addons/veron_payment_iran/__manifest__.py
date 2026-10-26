{
	"name": "ERP-VERON Iranian Payment Gateways",
	"summary": "Online payment with Iranian gateways (Zarinpal, Zibal): website, portal and invoices",
	"description": """
Payment providers for the gateways of the Shetab network, each payment checked with the gateway
server to server before it is recorded:

- Zarinpal (zarinpal.com), API v4
- Zibal (zibal.ir)

Amounts in rial (IRR). Set the merchant code in Accounting / Website: Configuration > Payment
Providers, first in test mode (Zarinpal's sandbox, Zibal's «zibal» test merchant).
""",
	"version": "19.0.1.0.0",
	"category": "Accounting/Payment Providers",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["payment", "veron_core"],
	"data": [
		"views/payment_templates.xml",
		"views/payment_provider_views.xml",
		"data/payment_method_data.xml",
		"data/payment_provider_data.xml",
	],
	"post_init_hook": "post_init_hook",
	"uninstall_hook": "uninstall_hook",
	"installable": True,
}
