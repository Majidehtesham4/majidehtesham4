from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AttendanceCorrection(models.Model):
	"""A correction of attendance an employee asks for (a check-in forgotten, a wrong time); approved by an
	attendance officer, the attendance is made or changed, and the request stays as the record of it"""

	_name = "veron.hr.attendance.correction"
	_description = "Attendance Correction"
	_inherit = ["mail.thread"]
	_order = "check_in desc, id desc"

	employee_id = fields.Many2one("hr.employee", required=True, tracking=True,
		default=lambda self: self.env.user.employee_id)
	company_id = fields.Many2one(related="employee_id.company_id", store=True)
	attendance_id = fields.Many2one("hr.attendance", "Attendance Changed",
		domain="[('employee_id', '=', employee_id)]", help="Empty to add an attendance")
	check_in = fields.Datetime(required=True, tracking=True)
	check_out = fields.Datetime(tracking=True)
	reason = fields.Text(required=True)
	state = fields.Selection([("draft", "Draft"), ("asked", "Asked"), ("approved", "Approved"), ("refused", "Refused")],
		default="draft", required=True, tracking=True)
	approved_by = fields.Many2one("res.users", readonly=True)
	before = fields.Char("Before the Correction", readonly=True)

	@api.constrains("check_in", "check_out")
	def _check_times(self):
		for correction in self:
			if correction.check_out and correction.check_out <= correction.check_in:
				raise ValidationError(_("The check-out is after the check-in."))

	def action_ask(self):
		self.filtered(lambda c: c.state == "draft").write({"state": "asked"})

	def action_approve(self):
		if not self.env.user.has_group("hr_attendance.group_hr_attendance_officer"):
			raise UserError(_("Only an attendance officer approves a correction."))
		for correction in self.filtered(lambda c: c.state in ("draft", "asked")):
			values = {"check_in": correction.check_in, "check_out": correction.check_out or False}
			if correction.attendance_id:
				attendance = correction.attendance_id
				before = f"{attendance.check_in or ''} - {attendance.check_out or ''}"
				attendance.write(values)
			else:
				before = ""
				attendance = self.env["hr.attendance"].create(dict(values, employee_id=correction.employee_id.id))
			correction.write({"state": "approved", "approved_by": self.env.uid, "attendance_id": attendance.id,
				"before": before})

	def action_refuse(self):
		self.filtered(lambda c: c.state in ("draft", "asked")).write({"state": "refused"})
