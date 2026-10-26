{
	"name": "ERP-VERON Barcode",
	"summary": "Receive, ship and count stock with a barcode scanner or the phone's camera",
	"description": """
A screen for the warehouse, on a computer with a barcode scanner or on a phone with its camera:

- Receipts, deliveries and internal transfers: scan the products, the quantities fill in, validate
- Stock count: scan a location, then its products; apply the counted quantities
- Product lookup: scan a product to see its stock in each location and its price

Products are found by their barcode or by the barcode of one of their packagings (a box of 12...).
""",
	"version": "19.0.1.0.0",
	"category": "Inventory/Inventory",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["stock", "barcodes", "veron_core"],
	"data": ["views/barcode_views.xml"],
	"assets": {
		"web.assets_backend": [
			"veron_barcode/static/src/barcode_app.js",
			"veron_barcode/static/src/barcode_app.xml",
			"veron_barcode/static/src/barcode_app.scss",
		],
	},
	"installable": True,
	"application": True,
}
