{
	"name": "ERP-VERON Iranian SMS",
	"summary": "SMS through Iranian providers (Kavenegar, SMS.ir, Melipayamak) instead of Odoo's paid service",
	"description": """
Odoo sends SMS through its own paid service (IAP), which does not reach Iranian numbers. With this
module every SMS of Odoo (reminders, two-step login, marketing, notifications) goes through the
company's Iranian SMS panel:

- Kavenegar (kavenegar.com): API key, sender line optional
- SMS.ir: API key and line number
- Melipayamak (melipayamak.com): username, password (or API key) and line number

Settings > General Settings > SMS.
""",
	"version": "19.0.1.0.0",
	"category": "Hidden/Tools",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["sms", "veron_core"],
	"data": ["views/res_config_settings_views.xml"],
	"installable": True,
}
