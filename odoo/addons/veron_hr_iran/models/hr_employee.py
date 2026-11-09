from odoo import fields, models


class HrEmployee(models.Model):
	_inherit = "hr.employee"

	veron_father_name = fields.Char("Father's Name", groups="hr.group_hr_user")
	veron_id_number = fields.Char("Birth Certificate Number", groups="hr.group_hr_user", help="شماره شناسنامه")
	veron_id_place = fields.Char("Place of Issue", groups="hr.group_hr_user")
	veron_id_date = fields.Date("Date of Issue", groups="hr.group_hr_user")
	veron_sso_job_code = fields.Char("Social Security Job Code", groups="hr.group_hr_user", help="کد شغل, of six digits")
	veron_loan_ids = fields.One2many("veron.hr.loan", "employee_id", "Loans and Advances", groups="hr.group_hr_user")
	veron_insurance_ids = fields.One2many("veron.hr.insurance.member", "employee_id", "Supplementary and Life Insurance",
		groups="hr.group_hr_user")
