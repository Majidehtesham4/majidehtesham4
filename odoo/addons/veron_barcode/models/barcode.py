"""What the barcode screen asks the server: every scan is checked and recorded here, with the user's
own rights on stock; the screen only shows the answers."""

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

KINDS = ("incoming", "outgoing", "internal")


def _n(quantity):
	"""2 rather than 2.0, 1.5 as it is"""
	return f"{quantity:.3f}".rstrip("0").rstrip(".")
OPEN = ("confirmed", "waiting", "assigned")


class VeronBarcode(models.AbstractModel):
	_name = "veron.barcode"
	_description = "Barcode screen"

	# --- what a barcode is

	@api.model
	def _product(self, barcode):
		"""(product, quantity) of a barcode: a product's, or a packaging's with the packaging's quantity"""
		product = self.env["product.product"].search([("barcode", "=", barcode)], limit=1)
		if product:
			return product, 1.0
		if "product.uom" in self.env:
			packaging = self.env["product.uom"].search([("barcode", "=", barcode)], limit=1)
			if packaging:
				return packaging.product_id, packaging.uom_id._compute_quantity(1, packaging.product_id.uom_id)
		return self.env["product.product"], 0.0

	@api.model
	def scan(self, barcode):
		"""What to open for a barcode scanned on the home screen"""
		barcode = (barcode or "").strip()
		picking = self.env["stock.picking"].search([("name", "=", barcode)], limit=1)
		if picking:
			return {"type": "picking", "id": picking.id}
		location = self.env["stock.location"].search([("barcode", "=", barcode)], limit=1)
		if location:
			return {"type": "count", "id": location.id}
		product, _qty = self._product(barcode)
		if product:
			return {"type": "product", "barcode": barcode}
		return {"type": "unknown", "message": _("Nothing has the barcode %s.", barcode)}

	# --- home

	@api.model
	def home(self):
		counts = {}
		for kind in KINDS:
			counts[kind] = self.env["stock.picking"].search_count([("picking_type_code", "=", kind), ("state", "in", OPEN)])
		warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
		return {"counts": counts, "stock_location": warehouse.lot_stock_id.id or False}

	@api.model
	def pickings(self, kind):
		pickings = self.env["stock.picking"].search(
			[("picking_type_code", "=", kind), ("state", "in", OPEN)], order="scheduled_date, id", limit=80
		)
		return [
			{
				"id": p.id,
				"name": p.name,
				"partner": p.partner_id.display_name or "",
				"origin": p.origin or "",
				"date": p.scheduled_date and p.scheduled_date.isoformat(),
				"state": p.state,
			}
			for p in pickings
		]

	# --- a transfer

	@api.model
	def picking(self, picking_id, message=None, level="info"):
		picking = self.env["stock.picking"].browse(picking_id).exists()
		if not picking:
			raise UserError(_("This transfer no longer exists."))
		moves = picking.move_ids.filtered(lambda m: m.state != "cancel")
		return {
			"id": picking.id,
			"name": picking.name,
			"kind": picking.picking_type_code,
			"partner": picking.partner_id.display_name or "",
			"from": picking.location_id.display_name,
			"to": picking.location_dest_id.display_name,
			"state": picking.state,
			"done": picking.state in ("done", "cancel"),
			"lines": [
				{
					"move_id": m.id,
					"product": m.product_id.display_name,
					"barcode": m.product_id.barcode or "",
					"demand": m.product_uom_qty,
					"quantity": m.quantity if m.picked else 0.0,
					"uom": m.product_uom.name,
					"complete": float_compare(m.quantity, m.product_uom_qty, precision_rounding=m.product_uom.rounding) >= 0 and m.picked,
				}
				for m in moves
			],
			"message": message,
			"level": level,
		}

	def _set_move_quantity(self, move, quantity):
		if move.picking_id.state in ("done", "cancel"):
			raise UserError(_("This transfer is already done."))
		move.quantity = max(quantity, 0.0)
		move.picked = bool(quantity)

	@api.model
	def picking_scan(self, picking_id, barcode):
		picking = self.env["stock.picking"].browse(picking_id)
		product, qty = self._product((barcode or "").strip())
		if not product:
			return self.picking(picking_id, _("Nothing has the barcode %s.", barcode), "danger")
		moves = picking.move_ids.filtered(lambda m: m.product_id == product and m.state != "cancel")
		if not moves:
			return self.picking(picking_id, _("%s is not in this transfer.", product.display_name), "danger")
		# The first line of the product still short of its demand, else its last line
		move = next((m for m in moves if not m.picked or m.quantity < m.product_uom_qty), moves[-1])
		current = move.quantity if move.picked else 0.0
		qty_in_move_uom = product.uom_id._compute_quantity(qty, move.product_uom)
		self._set_move_quantity(move, current + qty_in_move_uom)
		over = float_compare(move.quantity, move.product_uom_qty, precision_rounding=move.product_uom.rounding) > 0
		message = _("%(product)s: %(quantity)s of %(demand)s", product=product.display_name,
			quantity=_n(move.quantity), demand=_n(move.product_uom_qty))
		return self.picking(picking_id, message + (" — " + _("more than ordered") if over else ""), "warning" if over else "success")

	@api.model
	def picking_set(self, move_id, quantity):
		move = self.env["stock.move"].browse(move_id)
		self._set_move_quantity(move, float(quantity))
		return self.picking(move.picking_id.id)

	@api.model
	def picking_validate(self, picking_id):
		"""Done, or the action Odoo asks first (a backorder for what is missing...)"""
		picking = self.env["stock.picking"].browse(picking_id)
		if not any(m.picked and m.quantity for m in picking.move_ids):
			return {"data": self.picking(picking_id, _("Scan the products first."), "danger")}
		result = picking.button_validate()
		if isinstance(result, dict):
			return {"action": result}
		return {"data": self.picking(picking_id, _("%s is done.", picking.name), "success")}

	# --- a stock count

	@api.model
	def count(self, location_id, message=None, level="info"):
		location = self.env["stock.location"].browse(location_id).exists()
		if not location:
			raise UserError(_("This location no longer exists."))
		quants = self.env["stock.quant"].search([("location_id", "=", location.id), ("inventory_quantity_set", "=", True)])
		return {
			"id": location.id,
			"name": location.display_name,
			"lines": [
				{
					"quant_id": q.id,
					"product": q.product_id.display_name,
					"counted": q.inventory_quantity,
					"on_hand": q.quantity,
					"uom": q.product_uom_id.name,
				}
				for q in quants
			],
			"message": message,
			"level": level,
		}

	def _quant(self, location, product):
		Quant = self.env["stock.quant"].with_context(inventory_mode=True)
		quant = Quant.search([("location_id", "=", location.id), ("product_id", "=", product.id), ("lot_id", "=", False)], limit=1)
		return quant or Quant.create({"location_id": location.id, "product_id": product.id})

	@api.model
	def count_scan(self, location_id, barcode):
		location = self.env["stock.location"].browse(location_id)
		product, qty = self._product((barcode or "").strip())
		if not product:
			return self.count(location_id, _("Nothing has the barcode %s.", barcode), "danger")
		if not product.is_storable:
			return self.count(location_id, _("%s is not kept in stock.", product.display_name), "danger")
		quant = self._quant(location, product)
		counted = (quant.inventory_quantity if quant.inventory_quantity_set else 0.0) + qty
		quant.with_context(inventory_mode=True).write({"inventory_quantity": counted, "inventory_quantity_set": True})
		return self.count(location_id, _("%(product)s: %(quantity)s counted", product=product.display_name, quantity=_n(counted)), "success")

	@api.model
	def count_set(self, quant_id, quantity):
		quant = self.env["stock.quant"].browse(quant_id)
		quant.with_context(inventory_mode=True).write({"inventory_quantity": max(float(quantity), 0.0), "inventory_quantity_set": True})
		return self.count(quant.location_id.id)

	@api.model
	def count_apply(self, location_id):
		quants = self.env["stock.quant"].search([("location_id", "=", location_id), ("inventory_quantity_set", "=", True)])
		if not quants:
			return self.count(location_id, _("Nothing counted yet."), "danger")
		quants.action_apply_inventory()
		return self.count(location_id, _("The count is applied to the stock."), "success")

	# --- a product

	@api.model
	def product(self, barcode):
		product, _qty = self._product((barcode or "").strip())
		if not product:
			return {"found": False, "message": _("Nothing has the barcode %s.", barcode)}
		quants = self.env["stock.quant"].search([("product_id", "=", product.id), ("location_id.usage", "=", "internal")])
		return {
			"found": True,
			"name": product.display_name,
			"barcode": product.barcode or "",
			"price": product.lst_price,
			"currency": self.env.company.currency_id.symbol,
			"uom": product.uom_id.name,
			"on_hand": product.qty_available,
			"locations": [{"name": q.location_id.display_name, "quantity": q.quantity} for q in quants if q.quantity],
		}
