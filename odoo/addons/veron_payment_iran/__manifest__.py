{
	"name": "ERP-VERON Iranian Payment Gateways",
	"summary": "Online payment with Iranian gateways (Zarinpal, Zibal, Behpardakht Mellat, Sadad, Asan Pardakht): website, portal and invoices",
	"description": """
Payment providers for the gateways of the Shetab network, each payment checked with the gateway
server to server before it is recorded:

- Zarinpal (zarinpal.com), API v4
- Zibal (zibal.ir)
- Behpardakht Mellat (bpm.shaparak.ir): terminal, username and password; verified and settled, reversed
  when the bank does not settle it
- Sadad of Bank Melli (sadad.shaparak.ir): merchant, terminal and the merchant key each request is signed
  with (Triple DES)
- Asan Pardakht (asanpardakht.ir): merchant configuration id, username and password; verified and settled

All of them are one kind of payment provider: a website or the portal offers the ones that are enabled,
and the customer chooses. The banks' gateways have no sandbox; their answers are read as their published
documents say: test each with a small payment before using it.

Amounts in rial (IRR). Set the merchant code in Accounting / Website: Configuration > Payment
Providers, first in test mode (Zarinpal's sandbox, Zibal's «zibal» test merchant).
""",
	"version": "19.0.1.1.0",
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
