from odoo import api, models

from odoo.addons.account.models.chart_template import template

# OCA's Iranian chart gives the default income and expense accounts the way of Odoo 17 and 18
# (property_account_*_categ_id), which Odoo 19 ignores: the company had none, and an invoice could not
# even be made («accountable required fields»). Odoo 19 reads them from the company.
COMPANY_ACCOUNTS = {
	"income_account_id": "l10n_ir_chart_411003",  # فروش
	"expense_account_id": "l10n_ir_chart_621309",  # هزینه متفرقه, as OCA's expense default
	"income_currency_exchange_account_id": "l10n_ir_chart_621501",  # سود و زیان ناشی از تسعیر ارز
	"expense_currency_exchange_account_id": "l10n_ir_chart_621501",
	"default_cash_difference_income_account_id": "l10n_ir_chart_621509",  # سود و زیان ناشی از سایر اقلام
	"default_cash_difference_expense_account_id": "l10n_ir_chart_621509",
	"account_journal_early_pay_discount_loss_account_id": "l10n_ir_chart_411113",  # تخفیفات محصولات
	"account_journal_early_pay_discount_gain_account_id": "l10n_ir_chart_411209",  # سایر درآمدها
	"account_stock_valuation_id": "l10n_ir_chart_111604",  # موجودی محصولات
	"account_production_wip_account_id": "l10n_ir_chart_111701",  # کالای در جریان ساخت
	"account_production_wip_overhead_account_id": "l10n_ir_chart_811002",  # جذب هزینه‌های سربار
}


JOURNAL_CODES = {
	"sale": "فروش",
	"purchase": "خرید",
	"general": "عمومی",
	"exch": "تسعیر",
	"caba": "نقدی",
	"bank": "بانک",
	"cash": "صندوق",
}


class AccountChartTemplate(models.AbstractModel):
	_inherit = "account.chart.template"

	@template("ir", "res.company")
	def _get_ir_res_company_veron(self):
		company = self.env.company
		return {company.id: {field: xmlid for field, xmlid in COMPANY_ACCOUNTS.items() if field in company._fields}}

	@api.model
	def _veron_ir_accounts(self):
		"""Companies on the Iranian chart loaded before this: the accounts they lack"""
		for company in self.env["res.company"].search([("chart_template", "=", "ir")]):
			values = {}
			for field, xmlid in COMPANY_ACCOUNTS.items():
				if field in company._fields and not company[field]:
					account = self.with_company(company).ref(xmlid, raise_if_not_found=False)
					if account:
						values[field] = account.id
			if values:
				company.write(values)

	@api.model
	def _veron_journal_codes(self):
		"""Odoo makes the journals' codes from their translated names cut to 5 letters («صورتح»,
		«متفرق»): short Persian codes, which begin the documents' numbers. A journal with entries keeps
		its code, so that its numbers go on."""
		for company in self.env["res.company"].search([("chart_template", "=", "ir")]):
			chart = self.with_company(company)
			for xmlid, code in JOURNAL_CODES.items():
				journal = chart.ref(xmlid, raise_if_not_found=False)
				if journal and journal.code != code and not self.env["account.move"].search_count(
					[("journal_id", "=", journal.id)], limit=1
				):
					journal.code = code

	@api.model
	def _veron_fiscal_year(self):
		"""The fiscal year of a company in Iran ends with Esfand: 20 March (19 in some years)"""
		self.env["res.company"].search([("partner_id.country_id.code", "=", "IR")]).write(
			{"fiscalyear_last_month": "3", "fiscalyear_last_day": 20}
		)
