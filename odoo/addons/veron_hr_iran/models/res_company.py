from odoo import fields, models


class ResCompany(models.Model):
	_inherit = "res.company"

	veron_sso_workshop = fields.Char("Social Security Workshop Code", help="کد کارگاه, of ten digits")
	veron_sso_employer = fields.Char("Employer Name", help="The name of the employer as the Social Security Organization has it")
	veron_sso_contract_row = fields.Char("Contract Row", help="ردیف پیمان; 000 for a workshop without a contract")
	veron_mission_rate_city = fields.Monetary("Mission Rate, in the City", help="The per-diem of a day of mission in the city")
	veron_mission_rate_out = fields.Monetary("Mission Rate, out of the City")
	veron_mission_rate_abroad = fields.Monetary("Mission Rate, Abroad")
