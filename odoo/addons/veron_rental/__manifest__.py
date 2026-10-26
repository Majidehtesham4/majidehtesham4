{
	"name": "ERP-VERON Rental",
	"summary": "Rent out products: reservations without double booking, pickup, return, late fees, invoices",
	"description": """
Renting cars, equipment, halls, anything:

- Products for rent with a price per day and the number of units there are
- Rental orders: a reservation is refused when the units are already rented out for those dates
- Pickup and return; a return after the agreed end adds a late fee per day
- A deposit kept on the order; the invoice of the rental made from it
- Calendar and timeline of the rentals; the ones not returned on time
""",
	"version": "19.0.1.0.0",
	"category": "Sales/Rental",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["account", "web_timeline", "veron_core"],
	"data": [
		"security/rental_security.xml",
		"security/ir.model.access.csv",
		"data/rental_data.xml",
		"views/rental_views.xml",
	],
	"installable": True,
	"application": True,
}
