from odoo import _, fields, models


class HrEmployee(models.Model):
	_inherit = "hr.employee"

	veron_appraisal_ids = fields.One2many("veron.appraisal", "employee_id", groups="hr.group_hr_user")
	veron_appraisal_count = fields.Integer(compute="_compute_veron_appraisal_count", groups="hr.group_hr_user")
	veron_last_appraisal = fields.Date("Last Appraisal", compute="_compute_veron_appraisal_count", groups="hr.group_hr_user")

	def _compute_veron_appraisal_count(self):
		for employee in self:
			appraisals = employee.veron_appraisal_ids
			employee.veron_appraisal_count = len(appraisals)
			done = appraisals.filtered(lambda a: a.state == "done")
			employee.veron_last_appraisal = max(done.mapped("date_to")) if done else False

	def action_veron_appraisals(self):
		return {
			"type": "ir.actions.act_window",
			"name": _("Appraisals"),
			"res_model": "veron.appraisal",
			"view_mode": "list,form",
			"domain": [("employee_id", "in", self.ids)],
			"context": {"default_employee_id": self[:1].id},
		}

	def action_veron_start_appraisals(self):
		"""An appraisal started for each selected employee, for the past six months"""
		today = fields.Date.context_today(self)
		appraisals = self.env["veron.appraisal"].create([
			{"employee_id": employee.id, "date_from": fields.Date.subtract(today, months=6), "date_to": today,
			 "deadline": fields.Date.add(today, days=14)}
			for employee in self
		])
		appraisals.action_start()
		return {
			"type": "ir.actions.act_window",
			"name": _("Appraisals"),
			"res_model": "veron.appraisal",
			"view_mode": "list,form",
			"domain": [("id", "in", appraisals.ids)],
		}
