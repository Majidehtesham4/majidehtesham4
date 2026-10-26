from odoo import api, fields, models


class ResCompany(models.Model):
	_inherit = "res.company"

	veron_payroll_journal_id = fields.Many2one("account.journal", "Payroll Journal")

	def _veron_payroll_journal(self):
		"""The journal of the payslips' entries, made when missing"""
		self.ensure_one()
		if not self.veron_payroll_journal_id:
			journal = self.env["account.journal"].search([("company_id", "=", self.id), ("code", "=", "حقوق")], limit=1)
			self.veron_payroll_journal_id = journal or self.env["account.journal"].create({
				"name": "حقوق و دستمزد", "code": "حقوق", "type": "general", "company_id": self.id})
		return self.veron_payroll_journal_id

	@api.model
	def _veron_payroll_year_all(self):
		"""The rates of 1405 for each company, from the template record, to be checked and confirmed"""
		template = self.env.ref("veron_payroll_iran.payroll_year_1405", raise_if_not_found=False)
		if not template:
			return
		Year = self.env["veron.payroll.year"]
		for company in self.search([("id", "!=", template.company_id.id)]):
			if not Year.search_count([("year", "=", template.year), ("company_id", "=", company.id)]):
				template.copy({"company_id": company.id})
