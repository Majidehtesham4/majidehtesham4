from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

RATINGS = [("0", "Not rated"), ("1", "Poor"), ("2", "Needs improvement"), ("3", "Meets expectations"),
	("4", "Exceeds expectations"), ("5", "Outstanding")]
MANAGER_FIELDS = {"manager_rating", "manager_comment"}
EMPLOYEE_FIELDS = {"employee_rating", "employee_comment"}


class AppraisalTemplate(models.Model):
	_name = "veron.appraisal.template"
	_description = "Appraisal Form"

	name = fields.Char(required=True, translate=True)
	line_ids = fields.One2many("veron.appraisal.template.line", "template_id", "Questions", copy=True)
	active = fields.Boolean(default=True)


class AppraisalTemplateLine(models.Model):
	_name = "veron.appraisal.template.line"
	_description = "Appraisal Form Question"
	_order = "sequence, id"

	template_id = fields.Many2one("veron.appraisal.template", required=True, ondelete="cascade")
	sequence = fields.Integer(default=10)
	name = fields.Char("Question", required=True, translate=True)
	kind = fields.Selection([("rating", "Rating"), ("text", "Written answer")], default="rating", required=True)
	weight = fields.Float(default=1.0)


class Appraisal(models.Model):
	_name = "veron.appraisal"
	_description = "Appraisal"
	_inherit = ["mail.thread", "mail.activity.mixin"]
	_order = "date_to desc, id desc"

	name = fields.Char(compute="_compute_name", store=True)
	employee_id = fields.Many2one("hr.employee", required=True, index=True, tracking=True)
	manager_id = fields.Many2one("hr.employee", "Manager", tracking=True,
		compute="_compute_manager_id", store=True, readonly=False)
	employee_user_id = fields.Many2one(related="employee_id.user_id", store=True, string="Employee User")
	manager_user_id = fields.Many2one(related="manager_id.user_id", store=True, string="Manager User")
	department_id = fields.Many2one(related="employee_id.department_id", store=True)
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
	template_id = fields.Many2one("veron.appraisal.template", "Form", required=True,
		default=lambda self: self.env["veron.appraisal.template"].search([], limit=1))
	date_from = fields.Date("Period From", required=True)
	date_to = fields.Date("Period To", required=True)
	deadline = fields.Date()
	state = fields.Selection([("new", "To Start"), ("pending", "In Progress"), ("done", "Done"), ("cancel", "Cancelled")],
		default="new", required=True, tracking=True)
	line_ids = fields.One2many("veron.appraisal.line", "appraisal_id", "Questions")
	employee_feedback = fields.Html("Employee's Comments")
	manager_feedback = fields.Html("Manager's Comments")
	score = fields.Float(compute="_compute_score", store=True, aggregator="avg", help="Weighted average of the manager's ratings, out of 5")
	result = fields.Selection(RATINGS[1:], compute="_compute_score", store=True)
	is_employee = fields.Boolean(compute="_compute_roles")
	is_manager = fields.Boolean(compute="_compute_roles")

	@api.depends("employee_id.name", "date_to")
	def _compute_name(self):
		for appraisal in self:
			appraisal.name = _("Appraisal of %(employee)s", employee=appraisal.employee_id.name or "")

	@api.depends("employee_id")
	def _compute_manager_id(self):
		for appraisal in self:
			appraisal.manager_id = appraisal.employee_id.parent_id

	@api.depends("line_ids.manager_rating", "line_ids.weight", "line_ids.kind")
	def _compute_score(self):
		for appraisal in self:
			rated = appraisal.line_ids.filtered(lambda l: l.kind == "rating" and l.manager_rating not in (False, "0"))
			weight = sum(rated.mapped("weight"))
			score = sum(int(l.manager_rating) * l.weight for l in rated) / weight if weight else 0.0
			appraisal.score = score
			appraisal.result = str(max(1, min(5, round(score)))) if score else False

	@api.depends_context("uid")
	@api.depends("employee_user_id", "manager_user_id")
	def _compute_roles(self):
		hr = self.env.user.has_group("hr.group_hr_user")
		for appraisal in self:
			appraisal.is_employee = appraisal.employee_user_id == self.env.user
			appraisal.is_manager = hr or appraisal.manager_user_id == self.env.user

	def write(self, vals):
		"""Outside HR: the employee writes their comments, the manager theirs; the rest is HR's"""
		if not self.env.su and not self.env.user.has_group("hr.group_hr_user"):
			for appraisal in self:
				if "manager_feedback" in vals and appraisal.manager_user_id != self.env.user:
					raise AccessError(_("Only the manager writes the manager's comments."))
				if "employee_feedback" in vals and appraisal.employee_user_id != self.env.user:
					raise AccessError(_("Only the employee writes the employee's comments."))
				if set(vals) & {"employee_id", "manager_id", "template_id", "date_from", "date_to", "deadline", "state", "company_id"}:
					raise AccessError(_("Only HR changes the appraisal itself."))
				if appraisal.state in ("done", "cancel") and set(vals) & {"employee_feedback", "manager_feedback", "line_ids"}:
					raise UserError(_("This appraisal is closed."))
		return super().write(vals)

	def action_start(self):
		if not self.env.user.has_group("hr.group_hr_user"):
			raise AccessError(_("Only HR starts appraisals."))
		for appraisal in self.filtered(lambda a: a.state == "new"):
			if not appraisal.line_ids:
				appraisal.line_ids = [
					(0, 0, {"sequence": q.sequence, "name": q.name, "kind": q.kind, "weight": q.weight})
					for q in appraisal.template_id.line_ids
				]
			appraisal.state = "pending"
			deadline = appraisal.deadline or fields.Date.context_today(appraisal)
			if appraisal.employee_user_id:
				appraisal.activity_schedule("mail.mail_activity_data_todo", date_deadline=deadline,
					summary=_("Your self-assessment"), user_id=appraisal.employee_user_id.id)
			if appraisal.manager_user_id:
				appraisal.activity_schedule("mail.mail_activity_data_todo", date_deadline=deadline,
					summary=_("Appraisal of %s", appraisal.employee_id.name), user_id=appraisal.manager_user_id.id)
		return True

	def action_done(self):
		for appraisal in self:
			if not appraisal.is_manager:
				raise AccessError(_("Only the manager or HR can close an appraisal."))
			missing = appraisal.line_ids.filtered(lambda l: l.kind == "rating" and l.manager_rating in (False, "0"))
			if missing:
				raise UserError(_("Rate every question first: %s", ", ".join(missing.mapped("name"))))
			# Checked above: the manager closes it, a field they cannot write themselves
			appraisal.sudo().state = "done"
			appraisal.sudo().activity_ids.action_feedback(feedback=_("Appraisal done"))
		return True

	def action_cancel(self):
		self.write({"state": "cancel"})
		self.activity_ids.unlink()

	def action_reset(self):
		self.write({"state": "new"})
		self.line_ids.unlink()


class AppraisalLine(models.Model):
	_name = "veron.appraisal.line"
	_description = "Appraisal Answer"
	_order = "sequence, id"

	appraisal_id = fields.Many2one("veron.appraisal", required=True, ondelete="cascade", index=True)
	sequence = fields.Integer(default=10)
	name = fields.Char("Question", required=True)
	kind = fields.Selection([("rating", "Rating"), ("text", "Written answer")], default="rating", required=True)
	weight = fields.Float(default=1.0)
	employee_rating = fields.Selection(RATINGS, "Self-Assessment", default="0")
	manager_rating = fields.Selection(RATINGS, "Manager's Rating", default="0")
	employee_comment = fields.Text("Employee's Answer")
	manager_comment = fields.Text("Manager's Answer")

	def write(self, vals):
		"""The employee fills in their own side, the manager theirs; a closed appraisal stays as it is"""
		if not self.env.su and not self.env.user.has_group("hr.group_hr_user"):
			for line in self:
				appraisal = line.appraisal_id
				if appraisal.state in ("done", "cancel"):
					raise UserError(_("This appraisal is closed."))
				own = appraisal.employee_user_id == self.env.user
				manager = appraisal.manager_user_id == self.env.user
				if MANAGER_FIELDS & set(vals) and not manager:
					raise AccessError(_("Only the manager rates the employee."))
				if EMPLOYEE_FIELDS & set(vals) and not own:
					raise AccessError(_("Only the employee fills in the self-assessment."))
				if set(vals) - MANAGER_FIELDS - EMPLOYEE_FIELDS:
					raise AccessError(_("The questions of an appraisal are set by HR."))
		return super().write(vals)
