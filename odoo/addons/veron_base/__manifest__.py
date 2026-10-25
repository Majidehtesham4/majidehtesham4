{
	"name": "ERP-VERON Base",
	"summary": "A first module of your own: notes with a menu, list and form",
	"description": "Shows how a module adds a model, its views, a menu and access rights, without changing Odoo itself.",
	"version": "19.0.1.0.0",
	"category": "Tools",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["base"],
	"data": [
		"security/ir.model.access.csv",
		"views/veron_note_views.xml",
	],
	"installable": True,
	"application": True,
}
