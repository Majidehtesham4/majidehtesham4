import math

from odoo import _, api, fields, models
from odoo.exceptions import UserError

BUSY = ("reserved", "picked_up")


class RentalOrder(models.Model):
	_name = "veron.rental.order"
	_description = "Rental Order"
	_inherit = ["mail.thread", "mail.activity.mixin"]
	_order = "start_date desc, id desc"

	name = fields.Char(readonly=True, copy=False, default=lambda self: _("New"))
	partner_id = fields.Many2one("res.partner", "Customer", required=True, tracking=True)
	user_id = fields.Many2one("res.users", "Salesperson", default=lambda self: self.env.user, tracking=True)
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
	currency_id = fields.Many2one(related="company_id.currency_id")
	start_date = fields.Datetime("Pickup", required=True, tracking=True)
	end_date = fields.Datetime("Return", required=True, tracking=True)
	returned_date = fields.Datetime("Returned On", readonly=True, copy=False, tracking=True)
	days = fields.Integer(compute="_compute_days", store=True)
	late_days = fields.Integer(compute="_compute_late", store=True)
	state = fields.Selection([("draft", "Quotation"), ("reserved", "Reserved"), ("picked_up", "Picked Up"),
		("returned", "Returned"), ("invoiced", "Invoiced"), ("cancel", "Cancelled")],
		default="draft", required=True, tracking=True, copy=False)
	line_ids = fields.One2many("veron.rental.line", "order_id", "Products", copy=True)
	deposit = fields.Monetary(tracking=True, help="Kept until the products come back")
	amount_rent = fields.Monetary("Rent", compute="_compute_amounts", store=True)
	amount_late = fields.Monetary("Late Fees", compute="_compute_amounts", store=True)
	amount_total = fields.Monetary("Total", compute="_compute_amounts", store=True)
	invoice_id = fields.Many2one("account.move", readonly=True, copy=False)
	is_late = fields.Boolean(compute="_compute_is_late", search="_search_is_late")
	note = fields.Html()

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if vals.get("name", _("New")) == _("New"):
				vals["name"] = self.env["ir.sequence"].next_by_code("veron.rental.order") or _("New")
		return super().create(vals_list)

	@api.depends("start_date", "end_date")
	def _compute_days(self):
		for order in self:
			if order.start_date and order.end_date and order.end_date > order.start_date:
				# A started day is a day
				order.days = max(1, math.ceil((order.end_date - order.start_date).total_seconds() / 86400 - 1e-9))
			else:
				order.days = 0

	@api.depends("end_date", "returned_date")
	def _compute_late(self):
		for order in self:
			if order.returned_date and order.end_date and order.returned_date > order.end_date:
				order.late_days = math.ceil((order.returned_date - order.end_date).total_seconds() / 86400 - 1e-9)
			else:
				order.late_days = 0

	@api.depends("line_ids.subtotal", "line_ids.product_id", "line_ids.quantity", "late_days")
	def _compute_amounts(self):
		for order in self:
			rent = sum(order.line_ids.mapped("subtotal"))
			late = sum(l.product_id.rental_late_fee_day * l.quantity for l in order.line_ids) * order.late_days
			order.amount_rent, order.amount_late, order.amount_total = rent, late, rent + late

	@api.depends("state", "end_date")
	def _compute_is_late(self):
		now = fields.Datetime.now()
		for order in self:
			order.is_late = order.state == "picked_up" and order.end_date and order.end_date < now

	def _search_is_late(self, operator, value):
		now = fields.Datetime.now()
		if (operator == "=") == bool(value):
			return [("state", "=", "picked_up"), ("end_date", "<", now)]
		return ["|", ("state", "!=", "picked_up"), ("end_date", ">=", now)]

	@api.constrains("start_date", "end_date")
	def _check_dates(self):
		for order in self:
			if order.end_date <= order.start_date:
				raise UserError(_("The return must be after the pickup."))

	def _check_availability(self):
		"""Each product's units rented by the other orders at the same time, plus these, against its units"""
		for order in self:
			for product in order.line_ids.product_id:
				wanted = sum(order.line_ids.filtered(lambda l: l.product_id == product).mapped("quantity"))
				others = self.env["veron.rental.line"].search([
					("product_id", "=", product.id),
					("order_id", "!=", order.id),
					("order_id.state", "in", BUSY),
					("order_id.start_date", "<", order.end_date),
					("order_id.end_date", ">", order.start_date),
				])
				busy = sum(others.mapped("quantity"))
				if busy + wanted > product.rental_units:
					raise UserError(_(
						"%(product)s: %(free)s free for these dates, %(wanted)s asked (rented in %(orders)s).",
						product=product.display_name, free=max(product.rental_units - busy, 0), wanted=wanted,
						orders=", ".join(others.order_id.mapped("name"))))

	def action_reserve(self):
		for order in self:
			if order.state != "draft":
				continue
			if not order.line_ids:
				raise UserError(_("Add the products to rent first."))
			order._check_availability()
			order.state = "reserved"
		return True

	def action_pickup(self):
		self.filtered(lambda o: o.state == "reserved").write({"state": "picked_up"})
		return True

	def action_return(self):
		for order in self.filtered(lambda o: o.state == "picked_up"):
			order.write({"state": "returned", "returned_date": fields.Datetime.now()})
			if order.late_days:
				order.message_post(body=_("Returned %s days late.", order.late_days))
		return True

	def action_cancel(self):
		if self.filtered(lambda o: o.state in ("picked_up", "returned", "invoiced")):
			raise UserError(_("A rental already picked up cannot be cancelled."))
		self.write({"state": "cancel"})

	def action_draft(self):
		self.filtered(lambda o: o.state == "cancel").write({"state": "draft"})

	def action_invoice(self):
		"""The invoice of the rent and the late fees, as a draft to check and post in Accounting"""
		self.ensure_one()
		if self.state != "returned":
			raise UserError(_("Invoice the rental once the products are back."))
		lines = []
		for line in self.line_ids:
			lines.append((0, 0, {
				"product_id": line.product_id.id,
				"name": _("%(product)s, %(days)s days", product=line.product_id.display_name, days=self.days),
				"quantity": line.quantity * self.days,
				"price_unit": line.price_day,
			}))
			if self.late_days and line.product_id.rental_late_fee_day:
				lines.append((0, 0, {
					"product_id": line.product_id.id,
					"name": _("%(product)s, late fee for %(days)s days", product=line.product_id.display_name, days=self.late_days),
					"quantity": line.quantity * self.late_days,
					"price_unit": line.product_id.rental_late_fee_day,
				}))
		invoice = self.env["account.move"].create({
			"move_type": "out_invoice",
			"partner_id": self.partner_id.id,
			"invoice_origin": self.name,
			"invoice_line_ids": lines,
		})
		self.write({"invoice_id": invoice.id, "state": "invoiced"})
		return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": invoice.id, "view_mode": "form"}

	def action_open_invoice(self):
		self.ensure_one()
		return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": self.invoice_id.id, "view_mode": "form"}


class RentalLine(models.Model):
	_name = "veron.rental.line"
	_description = "Rental Order Line"

	order_id = fields.Many2one("veron.rental.order", required=True, ondelete="cascade", index=True)
	product_id = fields.Many2one("product.product", required=True, domain="[('rent_ok', '=', True)]")
	quantity = fields.Integer(default=1, required=True)
	price_day = fields.Monetary("Per Day", compute="_compute_price_day", store=True, readonly=False)
	currency_id = fields.Many2one(related="order_id.currency_id")
	subtotal = fields.Monetary(compute="_compute_subtotal", store=True)

	@api.depends("product_id")
	def _compute_price_day(self):
		for line in self:
			line.price_day = line.product_id.rental_price_day

	@api.depends("quantity", "price_day", "order_id.days")
	def _compute_subtotal(self):
		for line in self:
			line.subtotal = line.quantity * line.price_day * line.order_id.days

	@api.constrains("quantity")
	def _check_quantity(self):
		for line in self:
			if line.quantity <= 0:
				raise UserError(_("The quantity must be at least one."))
