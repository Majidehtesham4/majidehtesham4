from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.veron_core.models import jalali

# The fields of the rates a confirmed year keeps as they were confirmed
RATE_FIELDS = (
	"min_monthly", "housing", "food", "child", "marriage", "seniority_base", "insurance_ceiling",
	"monthly_hours", "overtime_rate", "night_rate", "holiday_rate", "ins_employee", "ins_employer",
	"ins_unemployment", "tax_exempt_insurance", "eidi_months", "eidi_cap", "bracket_ids", "year", "company_id",
)


class PayrollYear(models.Model):
	_name = "veron.payroll.year"
	_description = "Payroll Rates of a Year"
	_inherit = ["mail.thread"]
	_order = "year desc"
	_rec_name = "year"

	year = fields.Integer("Shamsi Year", required=True, tracking=True)
	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	currency_id = fields.Many2one(related="company_id.currency_id")
	state = fields.Selection([("draft", "To Check"), ("confirmed", "Confirmed")], default="draft",
		required=True, readonly=True, tracking=True, copy=False)
	confirmed_uid = fields.Many2one("res.users", "Confirmed By", readonly=True, copy=False)
	confirmed_date = fields.Datetime("Confirmed On", readonly=True, copy=False)
	source = fields.Html("Sources", help="Where the rates come from: the resolution of the Supreme Labour Council, the budget law")

	min_monthly = fields.Monetary("Minimum Monthly Wage", required=True, tracking=True,
		help="The minimum wage of a month of 30 days")
	min_daily = fields.Monetary("Minimum Daily Wage", compute="_compute_min_daily")
	housing = fields.Monetary("Housing Allowance", tracking=True, help="A month's housing allowance (حق مسکن)")
	food = fields.Monetary("Food Allowance", tracking=True, help="A month's food allowance (بن خواربار)")
	child = fields.Monetary("Child Allowance", tracking=True,
		help="A month's allowance for each child; by law three times the minimum daily wage")
	marriage = fields.Monetary("Marriage Allowance", tracking=True, help="A month's allowance of a married employee (حق تأهل)")
	seniority_base = fields.Monetary("Seniority Base", tracking=True,
		help="The seniority wage (پایه سنوات) a month for a year of work, for reference; each contract has its own")
	insurance_ceiling = fields.Monetary("Insurance Ceiling", tracking=True,
		help="The most wage of a month social security is computed on; by law seven times the minimum wage")
	monthly_hours = fields.Float("Hours of a Month", default=220, tracking=True,
		help="The hourly wage is the monthly wage divided by these hours (44 hours a week)")
	overtime_rate = fields.Float("Overtime Rate", default=1.4, tracking=True, help="Article 59: 40% over the hourly wage")
	night_rate = fields.Float("Night Work Rate", default=0.35, tracking=True, help="Article 58: 35% over the hourly wage, added")
	holiday_rate = fields.Float("Holiday Work Rate", default=1.4, tracking=True, help="Work on Fridays and holidays")
	ins_employee = fields.Float("Employee Insurance", default=7, tracking=True, help="Percent")
	ins_employer = fields.Float("Employer Insurance", default=20, tracking=True, help="Percent")
	ins_unemployment = fields.Float("Unemployment Insurance", default=3, tracking=True, help="Percent, paid by the employer")
	tax_exempt_insurance = fields.Float("Tax Exempt Insurance", default=2, tracking=True,
		help="Percent of the insured wage deducted from the taxable salary: two sevenths of the employee's 7%")
	eidi_months = fields.Float("Eidi (Months of Wage)", default=2, tracking=True,
		help="The new-year bonus: months of the daily wage × 30")
	eidi_cap = fields.Float("Eidi Cap (Minimum Wages)", default=3, tracking=True,
		help="The bonus is at most this many minimum monthly wages")
	bracket_ids = fields.One2many("veron.payroll.tax.bracket", "year_id", "Tax Brackets", copy=True)

	_year_company = models.Constraint("unique (year, company_id)", "The rates of a year are entered once.")

	@api.depends("year")
	def _compute_display_name(self):
		for rec in self:
			rec.display_name = _("Payroll rates of %s", rec.year)

	@api.depends("min_monthly")
	def _compute_min_daily(self):
		for rec in self:
			rec.min_daily = rec.min_monthly / 30

	@api.constrains("year")
	def _check_year(self):
		for rec in self:
			if not 1390 <= rec.year <= 1500:
				raise ValidationError(_("The year is a Shamsi year, as 1405."))

	@api.onchange("min_monthly")
	def _onchange_min_monthly(self):
		self.child = round(3 * self.min_monthly / 30)
		self.insurance_ceiling = 7 * self.min_monthly

	def write(self, vals):
		if any(field in vals for field in RATE_FIELDS) and self.filtered(lambda r: r.state == "confirmed"):
			raise UserError(_("The rates are confirmed. Set them back to check before changing them."))
		return super().write(vals)

	def action_confirm(self):
		if not self.env.user.has_group("payroll.group_payroll_manager"):
			raise UserError(_("Only a payroll manager confirms the rates."))
		for rec in self:
			if not rec.min_monthly or not rec.bracket_ids:
				raise UserError(_("Enter the minimum wage and the tax brackets of %s first.", rec.year))
		self.write({"state": "confirmed", "confirmed_uid": self.env.uid, "confirmed_date": fields.Datetime.now()})
		return True

	def action_draft(self):
		if not self.env.user.has_group("payroll.group_payroll_manager"):
			raise UserError(_("Only a payroll manager changes the rates."))
		self.write({"state": "draft", "confirmed_uid": False, "confirmed_date": False})
		return True

	def tax(self, taxable):
		"""The salary tax of a month: each part of the salary taxed at the rate of its bracket"""
		self.ensure_one()
		tax, lower = 0.0, 0.0
		for bracket in self.bracket_ids.sorted(lambda b: b.upto or float("inf")):
			upper = bracket.upto or float("inf")
			if taxable > lower:
				tax += (min(taxable, upper) - lower) * bracket.rate / 100
			lower = upper
		return round(tax)

	@api.model
	def _for_date(self, date, company):
		"""The confirmed rates of the Shamsi year of a date"""
		year = jalali.to_jalali(date)[0]
		rates = self.search([("year", "=", year), ("company_id", "=", company.id)], limit=1)
		if not rates:
			raise UserError(_("Enter the payroll rates of %s in Payroll, Configuration, Yearly Rates.", year))
		if rates.state != "confirmed":
			raise UserError(_("The payroll rates of %s are not confirmed yet. Check them against the official "
				"resolution in Payroll, Configuration, Yearly Rates, and confirm them.", year))
		return rates


class PayrollTaxBracket(models.Model):
	_name = "veron.payroll.tax.bracket"
	_description = "Salary Tax Bracket"
	_order = "upto"

	year_id = fields.Many2one("veron.payroll.year", required=True, ondelete="cascade")
	currency_id = fields.Many2one(related="year_id.currency_id")
	upto = fields.Monetary("Up To", help="The top of the bracket in a month; empty for the last bracket")
	rate = fields.Float("Rate (%)")

	def write(self, vals):
		if self.year_id.filtered(lambda y: y.state == "confirmed"):
			raise UserError(_("The rates are confirmed. Set them back to check before changing them."))
		return super().write(vals)

	@api.model_create_multi
	def create(self, vals_list):
		years = self.env["veron.payroll.year"].browse([v.get("year_id") for v in vals_list])
		if years.filtered(lambda y: y.state == "confirmed"):
			raise UserError(_("The rates are confirmed. Set them back to check before changing them."))
		return super().create(vals_list)

	def unlink(self):
		if self.year_id.filtered(lambda y: y.state == "confirmed"):
			raise UserError(_("The rates are confirmed. Set them back to check before changing them."))
		return super().unlink()
