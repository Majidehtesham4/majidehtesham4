{
	"name": "ERP-VERON Stock Kardex",
	"summary": "The kardex of a product (کاردکس کالا): each receipt and issue in order, with the running balance and cost",
	"description": """
The card of a product in a warehouse or a location, for a period in Shamsi: the balance before the
period, then each stock move done with its date, reference, partner, the quantity in or out, the unit cost
and the value, and the balance after it. Moves inside the place chosen are not counted as in or out.
Shown on screen with totals, and printed.
""",
	"version": "19.0.1.0.0",
	"category": "Inventory/Inventory",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["stock", "veron_core"],
	"data": ["security/ir.model.access.csv", "wizard/kardex_views.xml", "report/kardex_report.xml"],
	"installable": True,
}
