{
	"name": "ERP-VERON Theme",
	"summary": "The look of the program: a dark theme by default and a light one, the home screen of apps, a cleaner bar, "
		"buttons, search, lists, cards, settings and sign-in page",
	"description": """
- Dark by default, light for whoever chooses it in the user menu («حالت تاریک»); the choice is kept for each user
- The program opens on a home screen of the apps: tiles on a dotted background, the search of the menus above
- The bar of an app with the app's icon, the buttons and the search field rounded, the views spaced and framed
- The settings with a larger list of apps and clear headings; the sign-in page with ERP-VERON's mark
- Vazirmatn as the font of the whole program; Persian, right to left
""",
	"version": "19.0.1.0.0",
	"category": "Hidden/Tools",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["web", "mail", "web_responsive", "web_dark_mode", "veron_core", "veron_fonts_iran"],
	"data": [
		"views/templates.xml",
	],
	"assets": {
		"web._assets_primary_variables": [
			("before", "web/static/src/scss/primary_variables.scss", "veron_theme/static/src/scss/primary_variables.scss"),
		],
		"web.assets_variables_dark": [
			("before", "web_dark_mode/static/src/scss/primary_variables.dark.scss",
				"veron_theme/static/src/scss/primary_variables.dark.scss"),
		],
		"web.assets_web_dark": [
			# The light colors are not those of the dark theme
			("remove", "veron_theme/static/src/scss/primary_variables.scss"),
		],
		"web.assets_backend": [
			"veron_theme/static/src/scss/theme.scss",
			"veron_theme/static/src/js/navbar.js",
			"veron_theme/static/src/xml/navbar.xml",
		],
		"web.assets_frontend": [
			"veron_theme/static/src/scss/login.scss",
		],
	},
	"post_init_hook": "post_init_hook",
	"installable": True,
	"auto_install": ["veron_core"],
}
