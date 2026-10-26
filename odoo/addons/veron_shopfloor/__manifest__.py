{
	"name": "ERP-VERON Shop Floor",
	"summary": "A tablet screen for the workshop: start, pause and finish work orders, with their time",
	"description": """
The work orders of each work center on big cards, for a tablet next to the machine:

- Start, pause and finish a work order; the time worked is recorded by Odoo as usual
- The quantity produced, scrap, the components to use
- When the last operation is done, finish the manufacturing order from the same screen

Work orders appear when Manufacturing > Configuration > Settings > Work Orders is on and the bill of
materials has operations.
""",
	"version": "19.0.1.0.0",
	"category": "Manufacturing/Manufacturing",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["mrp", "veron_core"],
	"data": ["views/shopfloor_views.xml"],
	"assets": {
		"web.assets_backend": [
			"veron_shopfloor/static/src/shopfloor.js",
			"veron_shopfloor/static/src/shopfloor.xml",
			"veron_shopfloor/static/src/shopfloor.scss",
		],
	},
	"installable": True,
	"application": True,
}
