from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PlanningRole(models.Model):
	_name = "veron.planning.role"
	_description = "Planning Role"
	_order = "sequence, name"

	name = fields.Char(required=True, translate=True)
	color = fields.Integer()
	sequence = fields.Integer(default=10)
	active = fields.Boolean(default=True)


class PlanningShift(models.Model):
	_name = "veron.planning.shift"
	_description = "Shift"
	_inherit = ["mail.thread"]
	_order = "start_datetime, id"

	employee_id = fields.Many2one("hr.employee", required=True, index=True, tracking=True)
	user_id = fields.Many2one(related="employee_id.user_id", store=True)
	department_id = fields.Many2one(related="employee_id.department_id", store=True)
	role_id = fields.Many2one("veron.planning.role", tracking=True)
	color = fields.Integer(related="role_id.color")
	start_datetime = fields.Datetime("Start", required=True, tracking=True)
	end_datetime = fields.Datetime("End", required=True, tracking=True)
	allocated_hours = fields.Float("Hours", compute="_compute_allocated_hours", store=True)
	note = fields.Text()
	state = fields.Selection([("draft", "Draft"), ("published", "Published")], default="draft", required=True, tracking=True)
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
	conflict = fields.Boolean(compute="_compute_conflict", search="_search_conflict")
	conflict_reason = fields.Char(compute="_compute_conflict")

	@api.depends("start_datetime", "end_datetime")
	def _compute_allocated_hours(self):
		for shift in self:
			if shift.start_datetime and shift.end_datetime:
				shift.allocated_hours = max((shift.end_datetime - shift.start_datetime).total_seconds() / 3600, 0)
			else:
				shift.allocated_hours = 0

	@api.depends("employee_id.name", "role_id.name")
	def _compute_display_name(self):
		for shift in self:
			shift.display_name = " - ".join(filter(None, [shift.employee_id.name, shift.role_id.name]))

	@api.constrains("start_datetime", "end_datetime")
	def _check_dates(self):
		for shift in self:
			if shift.end_datetime <= shift.start_datetime:
				raise ValidationError(_("A shift must end after it starts."))

	def _overlapping_shifts(self):
		self.ensure_one()
		return self.search([
			("id", "!=", self.id or 0),
			("employee_id", "=", self.employee_id.id),
			("start_datetime", "<", self.end_datetime),
			("end_datetime", ">", self.start_datetime),
		])

	def _overlapping_leaves(self):
		self.ensure_one()
		return self.env["hr.leave"].sudo().search([
			("employee_id", "=", self.employee_id.id),
			("state", "=", "validate"),
			("date_from", "<", self.end_datetime),
			("date_to", ">", self.start_datetime),
		])

	@api.depends("employee_id", "start_datetime", "end_datetime")
	def _compute_conflict(self):
		for shift in self:
			reasons = []
			if shift.employee_id and shift.start_datetime and shift.end_datetime:
				if shift._overlapping_shifts():
					reasons.append(_("another shift at the same time"))
				leaves = shift._overlapping_leaves()
				if leaves:
					reasons.append(_("time off: %s", leaves[0].holiday_status_id.name))
			shift.conflict = bool(reasons)
			shift.conflict_reason = ", ".join(reasons)

	def _search_conflict(self, operator, value):
		if operator not in ("=", "!=") or not isinstance(value, bool):
			raise ValidationError(_("Unsupported search on conflicts."))
		ids = self.search([]).filtered("conflict").ids
		positive = (operator == "=") == value
		return [("id", "in" if positive else "not in", ids)]

	def action_publish(self):
		for shift in self.filtered(lambda s: s.state == "draft"):
			shift.state = "published"
			if shift.user_id:
				shift.message_subscribe(partner_ids=shift.user_id.partner_id.ids)
				shift.message_post(
					body=_("Your shift is planned: %(role)s, %(hours)s hours.", role=shift.role_id.name or "-",
						hours=round(shift.allocated_hours, 2)),
					partner_ids=shift.user_id.partner_id.ids,
					subtype_xmlid="mail.mt_comment",
				)
		return True

	def action_draft(self):
		self.write({"state": "draft"})

	@api.model
	def action_copy_previous_week(self):
		"""The shifts of the past seven days copied seven days later, as drafts; a shift already
		there for the same employee at the same time is not copied twice"""
		now = fields.Datetime.now()
		previous = self.search([("start_datetime", ">=", now - timedelta(days=7)), ("start_datetime", "<", now)])
		copied = self.browse()
		for shift in previous:
			start, end = shift.start_datetime + timedelta(days=7), shift.end_datetime + timedelta(days=7)
			if self.search_count([("employee_id", "=", shift.employee_id.id), ("start_datetime", "=", start)]):
				continue
			copied |= shift.copy({"start_datetime": start, "end_datetime": end, "state": "draft"})
		return {
			"type": "ir.actions.client",
			"tag": "display_notification",
			"params": {
				"message": _("%s shifts copied to the next week.", len(copied)),
				"type": "success",
				"next": {"type": "ir.actions.client", "tag": "soft_reload"},
			},
		}
