from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.payroll.models.base_browsable import BrowsableObject
from odoo.addons.veron_core.models import jalali


def shamsi_month(day):
	"""The first and the last day of the Shamsi month of a day"""
	jy, jm, _jd = jalali.to_jalali(day)
	start = jalali.to_gregorian(jy, jm, 1)
	return start, jalali.to_gregorian(jy, jm, jalali.month_length(jy, jm))


def _today(record):
	return fields.Date.context_today(record)


class HrPayslip(models.Model):
	_inherit = "hr.payslip"

	date_from = fields.Date(default=lambda self: shamsi_month(_today(self))[0])
	date_to = fields.Date(default=lambda self: shamsi_month(_today(self))[1])
	veron_move_id = fields.Many2one("account.move", "Accounting Entry", readonly=True, copy=False)

	@api.depends("employee_id", "date_from")
	def _compute_name(self):
		for record in self:
			if not record.date_from:
				super(HrPayslip, record)._compute_name()
				continue
			jy, jm, _jd = jalali.to_jalali(record.date_from)
			record.name = _("Payslip of %(name)s for %(month)s %(year)s",
				name=record.employee_id.name or "", month=jalali.MONTHS[jm - 1], year=jy)

	def _veron_iranian(self):
		"""The payslip is computed by rules of the Iranian labour law"""
		return any("iran." in (rule.amount_python_compute or "") + (rule.condition_python or "")
			for rule in self._get_salary_rules())

	def _get_baselocaldict(self, contracts):
		localdict = super()._get_baselocaldict(contracts)
		values = {}
		if self._veron_iranian():
			rates = self.env["veron.payroll.year"]._for_date(self.date_from, self.company_id or self.env.company)
			jy, jm, _jd = jalali.to_jalali(self.date_from)
			absence = sum(self.input_line_ids.filtered(lambda line: line.code == "ABSENCE").mapped("amount"))
			days = max((self.date_to - self.date_from).days + 1 - absence, 0)
			month_days = jalali.month_length(jy, jm)
			for contract in contracts:
				if contract.wage < rates.min_monthly:
					raise UserError(_("The wage of %(employee)s (%(wage)s) is below the minimum wage of %(year)s (%(min)s).",
						employee=contract.employee_id.name, wage=f"{contract.wage:,.0f}", year=rates.year, min=f"{rates.min_monthly:,.0f}"))
			values = {name: rates[name] for name in (
				"min_monthly", "min_daily", "housing", "food", "child", "marriage", "insurance_ceiling", "monthly_hours",
				"overtime_rate", "night_rate", "holiday_rate", "eidi_months", "eidi_cap")}
			values.update({
				"ins_employee": rates.ins_employee / 100,
				"ins_employer": rates.ins_employer / 100,
				"ins_unemployment": rates.ins_unemployment / 100,
				"tax_exempt_insurance": rates.tax_exempt_insurance / 100,
				"days": days,
				"month_days": month_days,
				# The share of a month the allowances of a month are paid for
				"ratio": min(days / month_days, 1) if month_days else 0,
				"tax": lambda taxable: rates.tax(taxable),
				"year": rates.year,
			})
		localdict["iran"] = BrowsableObject(self.employee_id.id, values, self.env)
		return localdict

	def action_payslip_done(self):
		res = super().action_payslip_done()
		for payslip in self.filtered(lambda p: p.state == "done" and not p.veron_move_id):
			payslip._veron_create_move()
		return res

	def action_payslip_cancel(self):
		posted = self.veron_move_id.filtered(lambda m: m.state == "posted")
		if posted:
			raise UserError(_("The entry of the payslip is posted. Reverse it in accounting first."))
		res = super().action_payslip_cancel()
		moves = self.veron_move_id
		self.veron_move_id = False
		moves.unlink()
		return res

	def _veron_create_move(self):
		"""A draft entry of the payslip: the earnings and the employer's costs on the expense accounts,
		the net, the insurance and the tax on what is owed"""
		self.ensure_one()
		company = self.company_id or self.env.company
		Account = self.env["account.account"].with_company(company)
		accounts = {}

		def account(code):
			if code not in accounts:
				accounts[code] = Account.search([("code", "=", code), ("company_ids", "in", company.id)], limit=1)
				if not accounts[code]:
					raise UserError(_("The account %s of the payroll rules is not in the chart of accounts.", code))
			return accounts[code]

		partner = self.employee_id.work_contact_id
		sums = defaultdict(float)
		for line in self.line_ids:
			rule, amount = line.salary_rule_id, abs(line.total)
			if not amount or not (rule.veron_debit_code or rule.veron_credit_code):
				continue
			line_partner = partner.id if rule.veron_partner else False
			if rule.veron_debit_code:
				sums[(account(rule.veron_debit_code).id, line_partner, line.name)] += amount
			if rule.veron_credit_code:
				sums[(account(rule.veron_credit_code).id, line_partner, line.name)] -= amount
		if not sums:
			return
		move = self.env["account.move"].create({
			"move_type": "entry",
			"journal_id": company._veron_payroll_journal().id,
			"date": self.date_to,
			"ref": self.number or self.name,
			"company_id": company.id,
			"line_ids": [(0, 0, {
				"account_id": account_id,
				"partner_id": partner_id,
				"name": name,
				"debit": amount if amount > 0 else 0,
				"credit": -amount if amount < 0 else 0,
			}) for (account_id, partner_id, name), amount in sums.items() if round(amount, 2)],
		})
		self.veron_move_id = move

	def action_veron_open_move(self):
		self.ensure_one()
		return {
			"type": "ir.actions.act_window",
			"res_model": "account.move",
			"res_id": self.veron_move_id.id,
			"view_mode": "form",
		}


class HrPayslipRun(models.Model):
	_inherit = "hr.payslip.run"

	date_start = fields.Date(default=lambda self: shamsi_month(_today(self))[0])
	date_end = fields.Date(default=lambda self: shamsi_month(_today(self))[1])
