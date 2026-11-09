from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrJobGroup(models.Model):
	"""A group of the job classification scheme (طرح طبقه‌بندی مشاغل): its number, and the base wage of a day
	of each Shamsi year"""

	_name = "veron.hr.job.group"
	_description = "Job Classification Group"
	_order = "number"

	number = fields.Integer("Group", required=True)
	name = fields.Char(compute="_compute_name", store=True)
	note = fields.Char()
	wage_ids = fields.One2many("veron.hr.job.group.wage", "group_id", "Base Wages")

	_number_unique = models.Constraint("unique(number)", "Each group once.")

	@api.depends("number")
	def _compute_name(self):
		for group in self:
			group.name = _("Group %s", group.number)

	def _base(self, year):
		self.ensure_one()
		wage = self.wage_ids.filtered(lambda w: w.year == year)[:1]
		return wage.daily * 30 if wage else 0.0


class HrJobGroupWage(models.Model):
	_name = "veron.hr.job.group.wage"
	_description = "Base Wage of a Job Group"
	_order = "year desc, group_id"

	group_id = fields.Many2one("veron.hr.job.group", required=True, ondelete="cascade")
	year = fields.Integer("Shamsi Year", required=True)
	daily = fields.Float("Base Wage of a Day", required=True)

	_year_unique = models.Constraint("unique(group_id, year)", "One base wage of a group a year.")


class HrJob(models.Model):
	_inherit = "hr.job"

	veron_job_group_id = fields.Many2one("veron.hr.job.group", "Job Group")


class HrVersion(models.Model):
	_inherit = "hr.version"

	veron_job_group_id = fields.Many2one("veron.hr.job.group", "Job Group", tracking=True,
		compute="_compute_veron_job_group", store=True, readonly=False)

	@api.depends("job_id")
	def _compute_veron_job_group(self):
		for version in self:
			if version.job_id.veron_job_group_id and not version.veron_job_group_id:
				version.veron_job_group_id = version.job_id.veron_job_group_id

	def _veron_check_group_wage(self, year):
		"""The wage of the contract is not under the base wage of its group in the year"""
		for version in self.filtered("veron_job_group_id"):
			base = version.veron_job_group_id._base(year)
			if base and version.wage < base:
				raise ValidationError(_("The wage of %(employee)s (%(wage)s) is under the base wage of %(group)s in %(year)s "
					"(%(base)s).", employee=version.employee_id.name, wage=f"{version.wage:,.0f}",
					group=version.veron_job_group_id.name, year=year, base=f"{base:,.0f}"))
