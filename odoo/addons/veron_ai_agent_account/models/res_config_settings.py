from odoo import fields, models


class ResConfigSettings(models.TransientModel):
	_inherit = "res.config.settings"

	# How an assistant makes a draft invoice: decisions of the business, not of the assistant
	veron_ai_invoice_taxes = fields.Selection([
		("ask", "Ask Each Time"),
		("product", "The Taxes Set on Each Product"),
		("none", "No Taxes"),
	], "Taxes of a Draft Invoice", default="ask", config_parameter="veron_ai_agent_account.invoice_taxes",
		help="When the request does not say «with taxes» or «without taxes»")
	veron_ai_invoice_price = fields.Selection([
		("pricelist_history", "Price List, Then the Customer's Last Sale, Then the Product's Price"),
		("pricelist", "Price List, Then the Product's Price"),
	], "Price of a Line", default="pricelist_history", config_parameter="veron_ai_agent_account.invoice_price",
		help="When the request does not say the price. A product with none of these is not invoiced: the price is asked")
	veron_ai_invoice_discount = fields.Selection([
		("consistent", "The Same Discount of the Customer's Last Sales of the Product, When They Agree"),
		("said", "Only When Said"),
	], "Discount of a Line", default="consistent", config_parameter="veron_ai_agent_account.invoice_discount",
		help="Discounts of other products are never used; differing discounts are shown, not applied")
