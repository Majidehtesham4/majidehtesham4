{
	"name": "ERP-VERON Dashboards",
	"summary": "The spreadsheet dashboards in Persian and rial even while they show sample data, and dark in the dark theme",
	"description": """
- Odoo sends a sample dashboard (shown while there is no data yet) without the module it belongs to, so none of
  its words were translated, and without the company's currency, so its amounts were in dollars; they are sent
  with both, and with the user's locale
- In the dark theme the dashboards are dark too: Odoo keeps its spreadsheets light, the sheet and its charts are
  turned dark here, their colors kept
""",
	"version": "19.0.1.0.0",
	"category": "Productivity/Dashboard",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["spreadsheet_dashboard", "veron_core"],
	"assets": {
		"web.assets_web_dark": [
			"veron_spreadsheet_iran/static/src/scss/dashboard.dark.scss",
		],
	},
	"installable": True,
	"auto_install": True,
}
