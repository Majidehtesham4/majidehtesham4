from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrAbsence(models.Model):
	"""An absence without pay or leave (غیبت غیرموجه); approved, its days are days not worked in the payslip"""

	_name = "veron.hr.absence"
	_description = "Unpaid Absence"
	_inherit = ["mail.thread"]
	_order = "date desc"

	employee_id = fields.Many2one("hr.employee", required=True, tracking=True)
	company_id = fields.Many2one(related="employee_id.company_id", store=True)
	date = fields.Date(required=True, tracking=True)
	days = fields.Float(default=1.0, required=True, tracking=True)
	reason = fields.Char()
	state = fields.Selection([("draft", "Draft"), ("approved", "Approved"), ("cancelled", "Cancelled")], default="draft",
		required=True, tracking=True)

	@api.constrains("days")
	def _check_days(self):
		for absence in self:
			if absence.days <= 0:
				raise ValidationError(_("An absence is of more than zero days."))

	def action_approve(self):
		self.write({"state": "approved"})

	def action_cancel(self):
		self.write({"state": "cancelled"})
