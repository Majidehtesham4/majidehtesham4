from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.veron_core.models import jalali
from odoo.addons.veron_payroll_iran.models.hr_payslip import shamsi_month


class HrLoan(models.Model):
	"""A loan or an advance to an employee, paid back by instalments deducted from the payslips"""

	_name = "veron.hr.loan"
	_description = "Employee Loan or Advance"
	_inherit = ["mail.thread"]
	_order = "date desc, id desc"

	name = fields.Char(compute="_compute_name", store=True)
	employee_id = fields.Many2one("hr.employee", required=True, tracking=True)
	company_id = fields.Many2one(related="employee_id.company_id", store=True)
	currency_id = fields.Many2one(related="company_id.currency_id")
	kind = fields.Selection([("loan", "Loan"), ("advance", "Advance")], required=True, default="loan", tracking=True)
	amount = fields.Monetary(required=True, tracking=True)
	date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
	installments = fields.Integer("Instalments", default=1, required=True, tracking=True)
	first_month = fields.Date("First Instalment In", required=True, default=fields.Date.context_today,
		help="Any day of the Shamsi month of the first instalment")
	state = fields.Selection([("draft", "Draft"), ("approved", "Approved"), ("paid", "Paid Back"),
		("cancelled", "Cancelled")], default="draft", required=True, tracking=True, copy=False)
	line_ids = fields.One2many("veron.hr.loan.line", "loan_id", "Instalments", copy=False)
	paid = fields.Monetary(compute="_compute_left", store=True)
	left = fields.Monetary("Left to Pay", compute="_compute_left", store=True)
	note = fields.Text()

	@api.depends("employee_id.name", "kind", "date")
	def _compute_name(self):
		for loan in self:
			kind = dict(self._fields["kind"]._description_selection(self.env)).get(loan.kind, "")
			loan.name = f"{kind} {loan.employee_id.name or ''} {jalali.to_jalali(loan.date)[0] if loan.date else ''}".strip()

	@api.depends("line_ids.paid", "line_ids.amount", "amount")
	def _compute_left(self):
		for loan in self:
			loan.paid = sum(loan.line_ids.filtered("paid").mapped("amount"))
			loan.left = loan.amount - loan.paid

	@api.constrains("amount", "installments")
	def _check_amount(self):
		for loan in self:
			if loan.amount <= 0 or loan.installments < 1:
				raise ValidationError(_("The amount is more than zero and there is one instalment at least."))

	def action_approve(self):
		"""The instalments, one a Shamsi month from the first; the rounding goes to the last"""
		for loan in self.filtered(lambda l: l.state == "draft"):
			currency = loan.currency_id
			each = currency.round(loan.amount / loan.installments)
			start = shamsi_month(loan.first_month)[0]
			lines = []
			for index in range(loan.installments):
				value = each if index < loan.installments - 1 else currency.round(loan.amount - each * (loan.installments - 1))
				lines.append((0, 0, {"date": start, "amount": value}))
				start = jalali.period_next(start, "month")
			loan.write({"line_ids": lines, "state": "approved"})

	def action_cancel(self):
		for loan in self:
			if loan.line_ids.filtered("paid"):
				raise UserError(_("%s has instalments already deducted; it is not cancelled.", loan.name))
			loan.line_ids.unlink()
			loan.state = "cancelled"

	def action_draft(self):
		self.filtered(lambda l: l.state == "cancelled").write({"state": "draft"})

	def _check_paid(self):
		for loan in self.filtered(lambda l: l.state in ("approved", "paid")):
			loan.state = "paid" if loan.line_ids and all(loan.line_ids.mapped("paid")) else "approved"


class HrLoanLine(models.Model):
	_name = "veron.hr.loan.line"
	_description = "Loan Instalment"
	_order = "date, id"

	loan_id = fields.Many2one("veron.hr.loan", required=True, ondelete="cascade")
	employee_id = fields.Many2one(related="loan_id.employee_id", store=True)
	kind = fields.Selection(related="loan_id.kind", store=True)
	currency_id = fields.Many2one(related="loan_id.currency_id")
	date = fields.Date("Month", required=True)
	month = fields.Char(compute="_compute_month")
	amount = fields.Monetary(required=True)
	payslip_id = fields.Many2one("hr.payslip", "Deducted In", readonly=True, copy=False)
	paid = fields.Boolean(compute="_compute_paid", store=True)

	@api.depends("date")
	def _compute_month(self):
		for line in self:
			if line.date:
				year, month, _day = jalali.to_jalali(line.date)
				line.month = f"{jalali.MONTHS[month - 1]} {year}"
			else:
				line.month = ""

	@api.depends("payslip_id.state")
	def _compute_paid(self):
		for line in self:
			line.paid = line.payslip_id.state in ("done", "paid")
