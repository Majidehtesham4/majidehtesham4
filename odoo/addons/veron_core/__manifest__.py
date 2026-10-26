{
	"name": "ERP-VERON Core",
	"summary": "Iran as the setting of everything: Shamsi dates, Persian, rial, Tehran, ERP-VERON's name",
	"description": """
The base of every ERP-VERON installation:

- Shamsi dates in the web client (lists, forms, the date picker, the calendar), in printed reports and
  emails, and in grouping by month, season and year; a Shamsi date can be typed;
- Persian with the week from Saturday, rial without decimals, Tehran time, for every user and company,
  and the price lists in rial;
- ERP-VERON in place of Odoo's name and links; the paid apps are not listed.
""",
	"version": "19.0.1.0.0",
	"category": "Hidden",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["base_setup", "web", "mail"],
	"data": ["data/iran.xml", "views/templates.xml"],
	"assets": {
		"web.assets_backend": [
			"veron_core/static/src/jalali/jalali.js",
			"veron_core/static/src/jalali/luxon_setup.js",
			"veron_core/static/src/jalali/datetime_picker.js",
			"veron_core/static/src/jalali/calendar.js",
			"veron_core/static/src/jalali/search_dates.js",
			"veron_core/static/src/jalali/calendar.scss",
			"veron_core/static/src/branding.js",
			"veron_core/static/src/sample.js",
		],
		# The website and the portal: dates and the date picker in Shamsi too
		"web.assets_frontend": [
			"veron_core/static/src/jalali/jalali.js",
			"veron_core/static/src/jalali/luxon_setup.js",
			"veron_core/static/src/jalali/datetime_picker.js",
		],
	},
	"installable": True,
	"auto_install": False,
}
