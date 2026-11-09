{
	"name": "ERP-VERON Iranian SMS",
	"summary": "SMS through Iranian providers (Kavenegar, SMS.ir, Melipayamak, Farapayamak, FarazSMS, Ghasedak) instead of Odoo's paid service, with backup panels",
	"description": """
Odoo sends SMS through its own paid service (IAP), which does not reach Iranian numbers. With this
module every SMS of Odoo (reminders, two-step login, marketing, notifications) goes through the
company's Iranian SMS panel:

- Kavenegar (kavenegar.com): API key, sender line optional
- SMS.ir: API key and line number
- Melipayamak (melipayamak.com) and Farapayamak (farapayamak.ir), one web service: username, password and line
- FarazSMS (farazsms.com, on IPPanel): API key and line number
- Ghasedak (ghasedak.me): API key, line optional

The hub: backup panels, tried in their order when the main one is not reached, has no credit or refuses
its account; a wrong number is not sent again. The answers of FarazSMS and Ghasedak are read as their
published documents say; check them with a first SMS.

Settings > General Settings > SMS.
""",
	"version": "19.0.1.1.0",
	"category": "Hidden/Tools",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["sms", "veron_core"],
	"data": ["security/ir.model.access.csv", "views/res_config_settings_views.xml"],
	"installable": True,
}
