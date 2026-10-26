{
	"name": "ERP-VERON Car Showroom",
	"summary": "A car showroom: the file of each car, consignment and investors' cars, instalment sales, investment contracts and the website showroom",
	"description": """
The business pack of a car showroom (نمایشگاه خودرو):

- The file of each car: model, year, color, mileage, chassis and engine number, the Iranian plate in
  its boxes and drawn like a plate; parking and spot; documents; body condition part by part;
  the expert's inspection; costs of preparation, repair and paperwork; photos
- Ours, an investor's, or consigned by a customer with the showroom's commission; the profit of each
  car (managers only, with the purchase and the lowest price)
- Awaiting delivery, in preparation, ready for sale, reserved, sold, delivered; days in the lot
- Instalment sales: down payment, monthly profit, instalments due on the same Shamsi day, each paid by
  a cheque (veron_cheque) or in cash; reminders of overdue ones
- Investment contracts: equal monthly payments of (the amount + the profit) / the months, the profit
  monthly, or all at the end; a cheque for each payment
- The showroom on the website, /showroom: the published cars, a page for each with its photos,
  specifications and inspection, and an inquiry form that makes a lead
- Draft invoices and bills for the accountant: the sale, the purchase, the costs, the commission
- The lists to start with: 78 Iranian and imported models with their specifications, colors, body
  parts and conditions, inspection items, services
- Reception, salesperson and manager roles
""",
	"version": "19.0.1.0.0",
	"category": "Sales",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["veron_core", "veron_accounting", "veron_cheque", "crm", "website"],
	"data": [
		"security/dealership_security.xml",
		"security/ir.model.access.csv",
		"data/dealership_data.xml",
		"data/product_data.xml",
		"data/dealership_lists.xml",
		"views/vehicle_views.xml",
		"views/sale_views.xml",
		"views/list_views.xml",
		"views/website_templates.xml",
		"views/menus.xml",
	],
	"assets": {
		"web.assets_backend": ["veron_dealership/static/src/scss/plate.scss"],
		"web.assets_frontend": ["veron_dealership/static/src/scss/plate.scss"],
	},
	"installable": True,
	"application": True,
}
