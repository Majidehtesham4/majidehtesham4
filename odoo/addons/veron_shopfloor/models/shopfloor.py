"""What the shop floor screen asks the server: Odoo's own work order buttons, with the user's rights"""

from odoo import _, api, models
from odoo.exceptions import UserError

OPEN = ("ready", "progress", "blocked")


class VeronShopfloor(models.AbstractModel):
	_name = "veron.shopfloor"
	_description = "Shop floor screen"

	def _workorders(self, domain=()):
		return self.env["mrp.workorder"].search(
			[("state", "in", OPEN), ("production_state", "not in", ("draft", "done", "cancel")), *domain],
			order="date_start, id",
		)

	@api.model
	def workcenters(self):
		workorders = self._workorders()
		centers = workorders.workcenter_id
		return [
			{
				"id": center.id,
				"name": center.display_name,
				"progress": len(workorders.filtered(lambda w: w.workcenter_id == center and w.state == "progress")),
				"todo": len(workorders.filtered(lambda w: w.workcenter_id == center and w.state != "progress")),
			}
			for center in centers
		]

	def _data(self, workorder):
		production = workorder.production_id
		raw = production.move_raw_ids.filtered(lambda m: m.state != "cancel")
		if workorder.operation_id and raw.filtered("operation_id"):
			raw = raw.filtered(lambda m: m.operation_id == workorder.operation_id)
		running = self.env["mrp.workcenter.productivity"].search(
			[("workorder_id", "=", workorder.id), ("date_end", "=", False)], order="date_start"
		)
		siblings = production.workorder_ids.filtered(lambda w: w.state != "cancel")
		return {
			"id": workorder.id,
			"name": workorder.name,
			"production_id": production.id,
			"production": production.name,
			"product": production.product_id.display_name,
			"quantity": production.product_qty,
			"producing": workorder.qty_producing or production.product_qty,
			"uom": production.product_uom_id.name,
			"state": workorder.state,
			# Read from the open time record itself: is_user_working is not refreshed within the request
			"working": bool(running.filtered(lambda line: line.user_id == self.env.user)),
			# Minutes done before the current run, and when the current run started
			"duration": workorder.duration - sum(running.mapped("duration")),
			"running_since": running[:1].date_start.isoformat() if running else False,
			"expected": workorder.duration_expected,
			"components": [
				{"product": m.product_id.display_name, "quantity": m.product_uom_qty, "uom": m.product_uom.name}
				for m in raw
			],
			"step": f"{list(siblings).index(workorder) + 1}/{len(siblings)}" if workorder in siblings else "",
		}

	@api.model
	def workorders(self, workcenter_id):
		return [self._data(w) for w in self._workorders([("workcenter_id", "=", workcenter_id)])]

	@api.model
	def act(self, workorder_id, what, quantity=None):
		"""start, pause or done; the answer: the work orders of its center again, a message, and the
		manufacturing order to finish when it was its last operation"""
		workorder = self.env["mrp.workorder"].browse(workorder_id).exists()
		if not workorder:
			raise UserError(_("This work order no longer exists."))
		center = workorder.workcenter_id
		message, finish = None, False
		if what == "start":
			workorder.button_start()
		elif what == "pause":
			workorder.button_pending()
		elif what == "done":
			if quantity is not None:
				if float(quantity) <= 0:
					raise UserError(_("The quantity produced must be more than zero."))
				workorder.qty_producing = float(quantity)
			workorder.button_finish()
			production = workorder.production_id
			if all(w.state in ("done", "cancel") for w in production.workorder_ids):
				finish = {"id": production.id, "name": production.name}
			message = _("%s is done.", workorder.name)
		else:
			raise UserError(_("Unknown action: %s", what))
		return {"workorders": self.workorders(center.id), "message": message, "finish": finish}

	@api.model
	def finish_production(self, production_id):
		"""Odoo's own «Produce»: done, or the question it asks first (components consumed differently...)"""
		production = self.env["mrp.production"].browse(production_id)
		result = production.button_mark_done()
		if isinstance(result, dict):
			return {"action": result}
		return {"message": _("%s is done.", production.name)}

	@api.model
	def scrap(self, workorder_id):
		return self.env["mrp.workorder"].browse(workorder_id).button_scrap()
