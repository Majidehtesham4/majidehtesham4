from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

FIELD_OPTIONS = [("no", "None"), ("optional", "Optional"), ("required", "Required")]


class ApprovalCategory(models.Model):
	_name = "veron.approval.category"
	_description = "Approval Category"
	_order = "sequence, name"

	name = fields.Char(required=True, translate=True)
	sequence = fields.Integer(default=10)
	description = fields.Text(translate=True)
	approver_ids = fields.Many2many("res.users", string="Approvers", domain="[('share', '=', False)]")
	minimum = fields.Integer("Approvals Needed", default=1,
		help="How many of the approvers must approve; 0 means all of them")
	has_amount = fields.Selection(FIELD_OPTIONS, "Amount", default="no", required=True)
	has_date = fields.Selection(FIELD_OPTIONS, "Date", default="no", required=True)
	has_product = fields.Selection(FIELD_OPTIONS, "Product", default="no", required=True)
	has_partner = fields.Selection(FIELD_OPTIONS, "Contact", default="no", required=True)
	active = fields.Boolean(default=True)
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
	request_to_approve_count = fields.Integer(compute="_compute_request_to_approve_count")

	def _compute_request_to_approve_count(self):
		groups = self.env["veron.approval.request"]._read_group(
			[("category_id", "in", self.ids), ("state", "=", "pending")], ["category_id"], ["__count"])
		counts = {category.id: count for category, count in groups}
		for category in self:
			category.request_to_approve_count = counts.get(category.id, 0)

	def action_new_request(self):
		self.ensure_one()
		return {
			"type": "ir.actions.act_window",
			"res_model": "veron.approval.request",
			"view_mode": "form",
			"context": {"default_category_id": self.id},
		}


class ApprovalRequest(models.Model):
	_name = "veron.approval.request"
	_description = "Approval Request"
	_inherit = ["mail.thread", "mail.activity.mixin"]
	_order = "id desc"

	name = fields.Char("Subject", required=True, tracking=True)
	reference = fields.Char(readonly=True, copy=False, default=lambda self: _("New"))
	category_id = fields.Many2one("veron.approval.category", required=True, tracking=True)
	requester_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True, readonly=True, tracking=True)
	description = fields.Html()
	amount = fields.Monetary(tracking=True)
	currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)
	date = fields.Date(tracking=True)
	product_id = fields.Many2one("product.product")
	quantity = fields.Float(default=1.0)
	partner_id = fields.Many2one("res.partner", "Contact")
	has_amount = fields.Selection(related="category_id.has_amount", string="Has Amount")
	has_date = fields.Selection(related="category_id.has_date", string="Has Date")
	has_product = fields.Selection(related="category_id.has_product", string="Has Product")
	has_partner = fields.Selection(related="category_id.has_partner", string="Has Partner")
	state = fields.Selection([("new", "New"), ("pending", "To Approve"), ("approved", "Approved"),
		("refused", "Refused"), ("cancel", "Cancelled")], default="new", required=True, tracking=True, copy=False)
	approver_line_ids = fields.One2many("veron.approval.approver", "request_id", "Approvers", copy=False)
	approver_user_ids = fields.Many2many("res.users", compute="_compute_approver_user_ids", store=True)
	user_status = fields.Selection([("waiting", "To Approve"), ("approved", "Approved"), ("refused", "Refused")],
		compute="_compute_user_status")
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if vals.get("reference", _("New")) == _("New"):
				vals["reference"] = self.env["ir.sequence"].next_by_code("veron.approval.request") or _("New")
		return super().create(vals_list)

	@api.depends("approver_line_ids.user_id")
	def _compute_approver_user_ids(self):
		for request in self:
			request.approver_user_ids = request.approver_line_ids.user_id

	@api.depends_context("uid")
	@api.depends("approver_line_ids.status")
	def _compute_user_status(self):
		for request in self:
			line = request.approver_line_ids.filtered(lambda l: l.user_id == self.env.user)[:1]
			request.user_status = line.status or False

	def _check_fields(self):
		for request in self:
			category = request.category_id
			missing = [label for option, value, label in (
				(category.has_amount, request.amount, _("Amount")),
				(category.has_date, request.date, _("Date")),
				(category.has_product, request.product_id, _("Product")),
				(category.has_partner, request.partner_id, _("Contact")),
			) if option == "required" and not value]
			if missing:
				raise UserError(_("Fill in first: %s", ", ".join(missing)))

	def action_submit(self):
		for request in self:
			if request.state != "new":
				continue
			if request.requester_id != self.env.user and not self.env.user.has_group("veron_approval.group_approval_manager"):
				raise AccessError(_("Only the requester submits the request."))
			request._check_fields()
			approvers = request.category_id.approver_ids
			if not approvers:
				raise UserError(_("The category %s has no approvers.", request.category_id.name))
			request.sudo().write({
				"approver_line_ids": [(5, 0, 0)] + [(0, 0, {"user_id": user.id}) for user in approvers],
				"state": "pending",
			})
			for user in approvers:
				request.sudo().activity_schedule("mail.mail_activity_data_todo", summary=_("Approve: %s", request.name), user_id=user.id)
		return True

	def _needed(self):
		self.ensure_one()
		count = len(self.approver_line_ids)
		minimum = self.category_id.minimum
		return count if minimum <= 0 else min(minimum, count)

	def _my_line(self):
		line = self.approver_line_ids.filtered(lambda l: l.user_id == self.env.user and l.status == "waiting")
		if self.state != "pending" or not line:
			raise AccessError(_("This request is not waiting for your approval."))
		return line

	def action_approve(self):
		for request in self:
			line = request._my_line()
			line.sudo().write({"status": "approved", "date": fields.Datetime.now()})
			request.sudo().activity_ids.filtered(lambda a: a.user_id == self.env.user).action_feedback(feedback=_("Approved"))
			if len(request.approver_line_ids.filtered(lambda l: l.status == "approved")) >= request._needed():
				request.sudo().state = "approved"
				request.sudo().activity_ids.unlink()
				request.sudo().message_post(body=_("The request is approved."), partner_ids=request.requester_id.partner_id.ids,
					subtype_xmlid="mail.mt_comment")
		return True

	def action_refuse(self, reason=None):
		for request in self:
			line = request._my_line()
			line.sudo().write({"status": "refused", "date": fields.Datetime.now(), "comment": reason})
			request.sudo().write({"state": "refused"})
			request.sudo().activity_ids.unlink()
			request.sudo().message_post(
				body=_("Refused by %(user)s: %(reason)s", user=self.env.user.name, reason=reason or "-"),
				partner_ids=request.requester_id.partner_id.ids, subtype_xmlid="mail.mt_comment")
		return True

	def action_open_refuse(self):
		self.ensure_one()
		return {
			"type": "ir.actions.act_window",
			"res_model": "veron.approval.refuse",
			"view_mode": "form",
			"target": "new",
			"context": {"default_request_id": self.id},
		}

	def action_cancel(self):
		for request in self:
			if request.requester_id != self.env.user and not self.env.user.has_group("veron_approval.group_approval_manager"):
				raise AccessError(_("Only the requester cancels the request."))
		self.sudo().write({"state": "cancel"})
		self.sudo().activity_ids.unlink()

	def action_draft(self):
		self.action_cancel()
		self.sudo().write({"state": "new", "approver_line_ids": [(5, 0, 0)]})


class ApprovalApprover(models.Model):
	_name = "veron.approval.approver"
	_description = "Approver of a Request"

	request_id = fields.Many2one("veron.approval.request", required=True, ondelete="cascade")
	user_id = fields.Many2one("res.users", "Approver", required=True)
	status = fields.Selection([("waiting", "To Approve"), ("approved", "Approved"), ("refused", "Refused")], default="waiting", required=True)
	date = fields.Datetime()
	comment = fields.Char("Reason")


class ApprovalRefuse(models.TransientModel):
	_name = "veron.approval.refuse"
	_description = "Refuse a Request"

	request_id = fields.Many2one("veron.approval.request", required=True)
	reason = fields.Char(required=True)

	def action_refuse(self):
		self.request_id.action_refuse(self.reason)
		return {"type": "ir.actions.act_window_close"}
