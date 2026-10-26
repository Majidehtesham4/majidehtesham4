from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

def _n(value):
	"""4 rather than 4.0; an empty cell stays empty"""
	if value == "" or value is None:
		return ""
	return f"{value:.4f}".rstrip("0").rstrip(".")


STATES = [("new", "New"), ("progress", "In Progress"), ("approval", "To Approve"), ("approved", "Approved"),
	("done", "Applied"), ("cancel", "Cancelled")]


class PlmEco(models.Model):
	_name = "veron.plm.eco"
	_description = "Engineering Change Order"
	_inherit = ["mail.thread", "mail.activity.mixin"]
	_order = "id desc"

	name = fields.Char("Reference", default=lambda self: _("New"), copy=False, readonly=True)
	title = fields.Char("Change", required=True, tracking=True)
	product_tmpl_id = fields.Many2one("product.template", "Product", required=True, tracking=True)
	bom_id = fields.Many2one("mrp.bom", "Current Bill of Materials", tracking=True,
		domain="[('product_tmpl_id', '=', product_tmpl_id)]")
	new_bom_id = fields.Many2one("mrp.bom", "New Version", copy=False, readonly=True)
	reason = fields.Selection([
		("improvement", "Product improvement"), ("cost", "Cost reduction"), ("supplier", "Supplier change"),
		("defect", "Defect correction"), ("customer", "Customer request"), ("regulation", "Regulation"),
	], tracking=True)
	description = fields.Html()
	user_id = fields.Many2one("res.users", "Responsible", default=lambda self: self.env.user, tracking=True)
	approver_id = fields.Many2one("res.users", "Approved By", readonly=True, copy=False, tracking=True)
	approval_date = fields.Datetime(readonly=True, copy=False)
	state = fields.Selection(STATES, default="new", required=True, tracking=True, copy=False)
	changes = fields.Html(compute="_compute_changes", sanitize=False)
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if vals.get("name", _("New")) == _("New"):
				vals["name"] = self.env["ir.sequence"].next_by_code("veron.plm.eco") or _("New")
		return super().create(vals_list)

	@api.onchange("product_tmpl_id")
	def _onchange_product(self):
		if self.bom_id.product_tmpl_id != self.product_tmpl_id:
			self.bom_id = self.env["mrp.bom"].search([("product_tmpl_id", "=", self.product_tmpl_id.id)], limit=1)

	# --- the differences

	@api.depends("bom_id.bom_line_ids.product_qty", "new_bom_id.bom_line_ids.product_qty",
		"new_bom_id.operation_ids.time_cycle_manual", "new_bom_id.product_qty")
	def _compute_changes(self):
		for eco in self:
			rows = eco._diff() if eco.new_bom_id else []
			if not rows:
				eco.changes = False
				continue
			body = Markup("").join(
				Markup('<tr class="%s"><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>') % (cls, kind, what, _n(old), _n(new))
				for cls, kind, what, old, new in rows
			)
			eco.changes = Markup('<table class="table table-sm"><thead><tr><th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr></thead><tbody>%s</tbody></table>') % (
				_("Change"), _("Item"), _("Before"), _("After"), body)

	def _diff(self):
		"""(class, kind, item, before, after) for what differs between the current and the new version"""
		self.ensure_one()
		old, new = self.bom_id, self.new_bom_id
		rows = []
		if old and old.product_qty != new.product_qty:
			rows.append(("table-info", _("Quantity made"), new.product_tmpl_id.display_name, old.product_qty, new.product_qty))
		before = {}
		for line in old.bom_line_ids:
			before[line.product_id] = before.get(line.product_id, 0) + line.product_qty
		after = {}
		for line in new.bom_line_ids:
			after[line.product_id] = after.get(line.product_id, 0) + line.product_qty
		for product in after.keys() - before.keys():
			rows.append(("table-success", _("Component added"), product.display_name, "", after[product]))
		for product in before.keys() - after.keys():
			rows.append(("table-danger", _("Component removed"), product.display_name, before[product], ""))
		for product in before.keys() & after.keys():
			if before[product] != after[product]:
				rows.append(("table-warning", _("Quantity changed"), product.display_name, before[product], after[product]))
		ops_before = {op.name: op.time_cycle_manual for op in old.operation_ids}
		ops_after = {op.name: op.time_cycle_manual for op in new.operation_ids}
		for name in ops_after.keys() - ops_before.keys():
			rows.append(("table-success", _("Operation added"), name, "", ops_after[name]))
		for name in ops_before.keys() - ops_after.keys():
			rows.append(("table-danger", _("Operation removed"), name, ops_before[name], ""))
		for name in ops_before.keys() & ops_after.keys():
			if ops_before[name] != ops_after[name]:
				rows.append(("table-warning", _("Operation time changed (minutes)"), name, ops_before[name], ops_after[name]))
		return rows

	# --- the steps

	def _check_state(self, *states):
		for eco in self:
			if eco.state not in states:
				raise UserError(_("%(eco)s is %(state)s.", eco=eco.name, state=dict(STATES)[eco.state]))

	def action_start(self):
		"""The new version: a copy of the current bill of materials, kept archived until applied"""
		self._check_state("new")
		for eco in self:
			if eco.bom_id:
				new = eco.bom_id.copy({
					"active": False,
					"veron_version": eco.bom_id.veron_version + 1,
					"veron_previous_bom_id": eco.bom_id.id,
				})
			else:
				new = self.env["mrp.bom"].create({"product_tmpl_id": eco.product_tmpl_id.id, "active": False})
			eco.write({"new_bom_id": new.id, "state": "progress"})
		return self.action_open_new_bom() if len(self) == 1 else True

	def action_open_new_bom(self):
		self.ensure_one()
		return {
			"type": "ir.actions.act_window",
			"name": _("New Version"),
			"res_model": "mrp.bom",
			"res_id": self.new_bom_id.id,
			"view_mode": "form",
			"context": {"active_test": False},
		}

	def action_request_approval(self):
		self._check_state("progress")
		managers = self.env.ref("mrp.group_mrp_manager").all_user_ids.filtered(lambda u: not u.share)
		for eco in self:
			if not eco._diff():
				raise UserError(_("The new version is the same as the current one."))
			eco.state = "approval"
			for manager in managers[:3]:
				eco.activity_schedule("mail.mail_activity_data_todo", summary=_("Approve %s", eco.name), user_id=manager.id)
		return True

	def action_approve(self):
		self._check_state("approval")
		if not self.env.user.has_group("mrp.group_mrp_manager"):
			raise AccessError(_("Only a manufacturing manager approves engineering changes."))
		self.write({"state": "approved", "approver_id": self.env.user.id, "approval_date": fields.Datetime.now()})
		self.activity_ids.action_feedback(feedback=_("Approved"))
		return True

	def action_reject(self):
		self._check_state("approval")
		if not self.env.user.has_group("mrp.group_mrp_manager"):
			raise AccessError(_("Only a manufacturing manager rejects engineering changes."))
		self.write({"state": "progress"})
		self.activity_ids.action_feedback(feedback=_("Sent back for changes"))
		return True

	def action_apply(self):
		"""The new version in use, the current one archived"""
		self._check_state("approved")
		for eco in self:
			# Approved by a manager: the versions swapped by the system, engineers cannot touch the one in use
			eco.new_bom_id.sudo().active = True
			if eco.bom_id:
				eco.bom_id.sudo().active = False
			eco.message_post(body=_("Version %(version)s of the bill of materials is now in use.", version=eco.new_bom_id.veron_version))
			eco.write({"state": "done"})
		return True

	def action_cancel(self):
		self._check_state("new", "progress", "approval", "approved")
		for eco in self:
			if eco.new_bom_id and not eco.new_bom_id.active:
				eco.new_bom_id.unlink()
		self.write({"state": "cancel"})
		self.activity_ids.unlink()
		return True
