from odoo import fields, models


class ProductTemplate(models.Model):
	_inherit = "product.template"

	rent_ok = fields.Boolean("Can Be Rented")
	rental_price_day = fields.Monetary("Rent per Day", currency_field="currency_id")
	rental_late_fee_day = fields.Monetary("Late Fee per Day", currency_field="currency_id",
		help="Charged for each day returned after the agreed end")
	rental_units = fields.Integer("Units to Rent", default=1, help="How many can be rented out at the same time")
