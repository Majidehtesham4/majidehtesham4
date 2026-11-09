from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrMission(models.Model):
	"""A mission of an employee; its per-diem goes into the payslip of the month it ends in"""

	_name = "veron.hr.mission"
	_description = "Employee Mission"
	_inherit = ["mail.thread"]
	_order = "date_from desc, id desc"

	name = fields.Char("Subject", required=True)
	employee_id = fields.Many2one("hr.employee", required=True, tracking=True)
	company_id = fields.Many2one(related="employee_id.company_id", store=True)
	currency_id = fields.Many2one(related="company_id.currency_id")
	kind = fields.Selection([("city", "In the City"), ("out", "Out of the City"), ("abroad", "Abroad")], required=True,
		default="out", tracking=True)
	destination = fields.Char()
	date_from = fields.Date(required=True, tracking=True)
	date_to = fields.Date(required=True, tracking=True)
	days = fields.Integer(compute="_compute_days", store=True)
	daily_rate = fields.Monetary("Rate of a Day", compute="_compute_rate", store=True, readonly=False)
	amount = fields.Monetary("Per-Diem", compute="_compute_amount", store=True)
	state = fields.Selection([("draft", "Draft"), ("approved", "Approved"), ("cancelled", "Cancelled")], default="draft",
		required=True, tracking=True)

	@api.depends("date_from", "date_to")
	def _compute_days(self):
		for mission in self:
			mission.days = (mission.date_to - mission.date_from).days + 1 if mission.date_from and mission.date_to else 0

	@api.depends("kind", "company_id")
	def _compute_rate(self):
		for mission in self:
			company = mission.company_id or self.env.company
			mission.daily_rate = {"city": company.veron_mission_rate_city, "out": company.veron_mission_rate_out,
				"abroad": company.veron_mission_rate_abroad}.get(mission.kind, 0.0)

	@api.depends("days", "daily_rate")
	def _compute_amount(self):
		for mission in self:
			mission.amount = mission.days * mission.daily_rate

	@api.constrains("date_from", "date_to")
	def _check_dates(self):
		for mission in self:
			if mission.date_from and mission.date_to and mission.date_to < mission.date_from:
				raise ValidationError(_("A mission ends after it starts."))

	def action_approve(self):
		self.write({"state": "approved"})

	def action_cancel(self):
		self.write({"state": "cancelled"})
