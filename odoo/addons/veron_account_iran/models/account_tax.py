"""The deposits and the tax withheld from an invoice (کسورات قانونی), as taxes of a negative rate on their
accounts of the Iranian chart: the vendor is owed that much less, and what is held is on its account, by
partner, until it is released"""

from odoo import api, models

# name, use, rate, account code of the Iranian chart
RETENTIONS = [
	("سپرده بیمه ۵٪", "purchase", -5.0, "211205"),
	("سپرده حسن انجام کار ۱۰٪", "purchase", -10.0, "211302"),
	("مالیات تکلیفی ۳٪", "purchase", -3.0, "211203"),
	("سپرده بیمه کسرشده توسط کارفرما ۵٪", "sale", -5.0, "111104"),
	("سپرده حسن انجام کار کسرشده توسط کارفرما ۱۰٪", "sale", -10.0, "111104"),
]
GROUP = "کسورات قانونی"


class AccountTax(models.Model):
	_inherit = "account.tax"

	@api.model
	def _veron_retentions(self, company):
		"""The deposit taxes of a company on the Iranian chart, made once; those of a company whose accounts are
		not there are not made"""
		Account = self.env["account.account"].sudo().with_company(company)
		Tax = self.sudo().with_context(active_test=False)
		group = self.env["account.tax.group"].sudo().search([("name", "=", GROUP), ("company_id", "=", company.id)], limit=1)
		made = Tax.browse()
		for name, use, rate, code in RETENTIONS:
			if Tax.search_count([("name", "=", name), ("company_id", "=", company.id), ("type_tax_use", "=", use)]):
				continue
			account = Account.search([("code", "=", code), ("company_ids", "in", company.id)], limit=1)
			if not account:
				continue
			if not group:
				group = self.env["account.tax.group"].sudo().create({"name": GROUP, "company_id": company.id,
					"country_id": company.account_fiscal_country_id.id or company.country_id.id})
			lines = [(0, 0, {"repartition_type": "base"}), (0, 0, {"repartition_type": "tax", "account_id": account.id})]
			made |= Tax.create({
				"name": name, "type_tax_use": use, "amount_type": "percent", "amount": rate, "company_id": company.id,
				"tax_group_id": group.id, "description": name, "country_id": group.country_id.id,
				"invoice_repartition_line_ids": lines, "refund_repartition_line_ids": lines,
			})
		return made
