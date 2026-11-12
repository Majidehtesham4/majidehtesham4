from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.veron_core.models import jalali


def shamsi(value):
	if not value:
		return ""
	year, month, day = jalali.to_jalali(fields.Date.to_date(value))
	return f"{year}/{month:02d}/{day:02d}"


class StockKardex(models.TransientModel):
	_name = "veron.stock.kardex"
	_description = "Stock Kardex"

	product_id = fields.Many2one("product.product", required=True, domain="[('is_storable', '=', True)]")
	warehouse_id = fields.Many2one("stock.warehouse", default=lambda self: self.env["stock.warehouse"].search(
		[("company_id", "=", self.env.company.id)], limit=1))
	location_id = fields.Many2one("stock.location", domain="[('usage', '=', 'internal')]",
		help="A location of its own; empty, all the internal locations of the warehouse")
	date_from = fields.Date(required=True, default=lambda self: jalali.to_gregorian(
		jalali.to_jalali(fields.Date.context_today(self))[0], 1, 1))
	date_to = fields.Date(required=True, default=fields.Date.context_today)
	opening = fields.Float("Balance Before", readonly=True)
	closing = fields.Float("Balance After", readonly=True)
	line_ids = fields.One2many("veron.stock.kardex.line", "kardex_id", readonly=True)

	@api.depends("product_id")
	def _compute_display_name(self):
		for kardex in self:
			kardex.display_name = _("Kardex: %s", kardex.product_id.display_name) if kardex.product_id else _("Stock Kardex")

	def _reference(self, move):
		if move.picking_id:
			return move.picking_id.name
		if move.is_inventory:
			return _("Inventory Count")
		return move.reference or ""

	def _places(self):
		self.ensure_one()
		Location = self.env["stock.location"]
		if self.location_id:
			return Location.search([("id", "child_of", self.location_id.id), ("usage", "=", "internal")])
		if self.warehouse_id:
			return Location.search([("id", "child_of", self.warehouse_id.view_location_id.id), ("usage", "=", "internal")])
		return Location.search([("usage", "=", "internal"), ("company_id", "=", self.env.company.id)])

	def _moves(self, places, before=False):
		domain = [("product_id", "=", self.product_id.id), ("state", "=", "done"), "|",
			("location_id", "in", places.ids), ("location_dest_id", "in", places.ids)]
		end = fields.Datetime.to_datetime(self.date_from) if before else fields.Datetime.add(
			fields.Datetime.to_datetime(self.date_to), days=1)
		domain.append(("date", "<", end))
		if not before:
			domain.append(("date", ">=", fields.Datetime.to_datetime(self.date_from)))
		return self.env["stock.move"].search(domain, order="date, id")

	def _quantity(self, move):
		return move.product_uom._compute_quantity(move.quantity, self.product_id.uom_id)

	def _signed(self, move, places):
		"""What a move adds to the place (in), takes from it (out), or neither (inside it)"""
		into, out_of = move.location_dest_id in places, move.location_id in places
		quantity = self._quantity(move)
		if into and not out_of:
			return quantity, 0.0
		if out_of and not into:
			return 0.0, quantity
		return 0.0, 0.0

	def action_compute(self):
		self.ensure_one()
		if self.date_to < self.date_from:
			raise UserError(_("The period ends after it starts."))
		places = self._places()
		opening = sum(i - o for i, o in (self._signed(move, places) for move in self._moves(places, before=True)))
		balance, lines = opening, [(5, 0, 0)]
		for move in self._moves(places):
			quantity_in, quantity_out = self._signed(move, places)
			if not quantity_in and not quantity_out:
				continue
			balance += quantity_in - quantity_out
			cost = abs(move.price_unit) if "price_unit" in move._fields and move.price_unit else self.product_id.standard_price
			partner = move.picking_id.partner_id or (move.partner_id if "partner_id" in move._fields else move.picking_id.partner_id)
			lines.append((0, 0, {"date": move.date, "reference": self._reference(move),
				"partner": partner.name or "", "quantity_in": quantity_in, "quantity_out": quantity_out, "balance": balance,
				"cost": cost, "value_in": quantity_in * cost, "value_out": quantity_out * cost, "move_id": move.id}))
		self.write({"opening": opening, "closing": balance, "line_ids": lines})
		return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
			"target": "current"}

	def action_print(self):
		self.ensure_one()
		if not self.line_ids and not self.opening:
			self.action_compute()
		return self.env.ref("veron_stock_kardex.action_report_kardex").report_action(self)

	def _shamsi(self, value):
		return shamsi(value)


class StockKardexLine(models.TransientModel):
	_name = "veron.stock.kardex.line"
	_description = "Stock Kardex Line"
	_order = "date, id"

	kardex_id = fields.Many2one("veron.stock.kardex", required=True, ondelete="cascade")
	date = fields.Datetime()
	reference = fields.Char()
	partner = fields.Char()
	quantity_in = fields.Float("In")
	quantity_out = fields.Float("Out")
	balance = fields.Float()
	cost = fields.Float("Unit Cost")
	value_in = fields.Float("Value In")
	value_out = fields.Float("Value Out")
	move_id = fields.Many2one("stock.move")
