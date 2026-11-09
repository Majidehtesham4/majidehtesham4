{
	"name": "ERP-VERON Persian Fonts",
	"summary": "Persian fonts (Vazirmatn, Sahel, Shabnam, Samim) in the program, and the font of the printed documents chosen by each company",
	"description": """
Persian fonts that come with the program, so nothing is fetched from outside (Google Fonts does not reach
Iran): Vazirmatn, Sahel, Shabnam and Samim, each regular and bold, under the SIL Open Font License.

- The font of the printed documents (invoices, vouchers, payslips, letters) chosen by each company in
  Settings > Companies, among those fonts or Tahoma
- The fonts offered to the website and to the other modules, which name them by family
""",
	"version": "19.0.1.0.0",
	"category": "Hidden/Tools",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["web", "veron_core"],
	"data": ["views/report_layout.xml", "views/res_company_views.xml"],
	"assets": {
		"web.report_assets_common": ["veron_fonts_iran/static/src/css/report_fonts.css"],
		"web.assets_backend": ["veron_fonts_iran/static/src/css/fonts.css"],
		"web.assets_frontend": ["veron_fonts_iran/static/src/css/fonts.css"],
	},
	"installable": True,
}
