from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .instalment import add_shamsi_months

PAYMENTS = [
	("equal", "Equal Monthly (Principal and Profit)"),
	("monthly", "Profit Monthly, Principal at the End"),
	("end", "All at the End"),
]


class InvestmentContract(models.Model):
	_name = "veron.investment.contract"
	_description = "Investment Contract"
	_inherit = ["mail.thread", "mail.activity.mixin"]
	_order = "start_date desc, id desc"

	name = fields.Char(required=True, readonly=True, copy=False, default="/")
	investor_id = fields.Many2one("res.partner", "Investor", required=True, tracking=True)
	start_date = fields.Date("Start Date", required=True, default=fields.Date.context_today, tracking=True)
	end_date = fields.Date("End Date", compute="_compute_end_date", store=True)
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
	currency_id = fields.Many2one(related="company_id.currency_id")
	state = fields.Selection([("draft", "Draft"), ("active", "Active"), ("settled", "Settled"), ("cancelled", "Cancelled")],
		default="draft", required=True, tracking=True, copy=False)
	scope = fields.Selection([("business", "The Whole Business"), ("vehicle", "Certain Cars")], default="business", required=True)
	vehicle_ids = fields.One2many("veron.vehicle", "investment_contract_id", "Cars")
	amount = fields.Monetary("Invested Amount", required=True, tracking=True)
	months = fields.Integer("Months", default=12, required=True)
	monthly_rate = fields.Float("Monthly Profit (%)", tracking=True)
	payment_mode = fields.Selection(PAYMENTS, "Payment Plan", default="equal", required=True)
	monthly_profit = fields.Monetary("Profit of a Month", compute="_compute_profit", store=True)
	total_profit = fields.Monetary("Total Profit", compute="_compute_profit", store=True)
	payment_amount = fields.Monetary("Each Monthly Payment", compute="_compute_profit", store=True,
		help="Equal monthly payments: (the amount + the total profit) / the months")
	line_ids = fields.One2many("veron.investment.payment", "contract_id", "Payments", copy=False)
	paid_total = fields.Monetary("Paid", compute="_compute_paid")
	outstanding = fields.Monetary("Left to Pay", compute="_compute_paid")
	received_journal_id = fields.Many2one("account.journal", "Received To", domain=[("type", "in", ("bank", "cash"))])
	receipt_move_id = fields.Many2one("account.move", "Receipt Entry", readonly=True, copy=False)
	note = fields.Text()

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if vals.get("name", "/") == "/":
				vals["name"] = self.env["ir.sequence"].next_by_code("veron.investment.contract") or "/"
		return super().create(vals_list)

	@api.constrains("months", "amount")
	def _check_terms(self):
		for contract in self:
			if contract.months < 1 or contract.amount <= 0:
				raise ValidationError(_("The amount and the months of a contract are more than zero."))

	@api.depends("start_date", "months")
	def _compute_end_date(self):
		for contract in self:
			contract.end_date = add_shamsi_months(contract.start_date, contract.months) if contract.start_date and contract.months else False

	@api.depends("amount", "monthly_rate", "months", "payment_mode")
	def _compute_profit(self):
		for contract in self:
			contract.monthly_profit = round(contract.amount * contract.monthly_rate / 100)
			contract.total_profit = contract.monthly_profit * contract.months
			contract.payment_amount = round((contract.amount + contract.total_profit) / contract.months) if contract.months else 0

	@api.depends("line_ids.paid", "line_ids.amount")
	def _compute_paid(self):
		for contract in self:
			contract.paid_total = sum(contract.line_ids.filtered("paid").mapped("amount"))
			contract.outstanding = sum(contract.line_ids.mapped("amount")) - contract.paid_total

	def _rows(self):
		"""[(amount, principal, profit)] month by month"""
		self.ensure_one()
		months, amount, profit = self.months, self.amount, self.monthly_profit
		if self.payment_mode == "equal":
			total = amount + self.total_profit
			principal = round(amount / months)
			rows = [(self.payment_amount, principal, self.payment_amount - principal) for _i in range(months - 1)]
			last = total - self.payment_amount * (months - 1)
			last_principal = amount - principal * (months - 1)
			return rows + [(last, last_principal, last - last_principal)]
		if self.payment_mode == "monthly":
			return [(profit, 0, profit) for _i in range(months - 1)] + [(profit + amount, amount, profit)]
		return [(0, 0, 0)] * (months - 1) + [(amount + self.total_profit, amount, self.total_profit)]

	def action_confirm(self):
		for contract in self:
			if contract.state != "draft":
				raise UserError(_("%s is already confirmed.", contract.name))
			contract.line_ids = [(0, 0, {
				"sequence": i + 1, "due_date": add_shamsi_months(contract.start_date, i + 1),
				"amount": amount, "principal": principal, "profit": profit,
			}) for i, (amount, principal, profit) in enumerate(contract._rows()) if amount]
			contract.state = "active"
		return True

	def action_cancel(self):
		for contract in self:
			if contract.line_ids.filtered("paid"):
				raise UserError(_("Payments of %s are made; it cannot be cancelled.", contract.name))
			contract.line_ids.unlink()
			contract.state = "cancelled"
		return True

	def action_receipt_entry(self):
		"""A draft entry of the money received from the investor, owed back to them"""
		self.ensure_one()
		if self.receipt_move_id:
			raise UserError(_("The entry is already made."))
		if not self.received_journal_id.default_account_id:
			raise UserError(_("Choose the bank or cash the money was received to."))
		payable = self.investor_id.with_company(self.company_id).property_account_payable_id
		self.receipt_move_id = self.env["account.move"].create({
			"move_type": "entry", "journal_id": self.received_journal_id.id, "date": self.start_date, "ref": self.name,
			"company_id": self.company_id.id,
			"line_ids": [
				(0, 0, {"account_id": self.received_journal_id.default_account_id.id, "debit": self.amount, "name": self.name}),
				(0, 0, {"account_id": payable.id, "partner_id": self.investor_id.id, "credit": self.amount,
					"name": _("Investment %s", self.name)}),
			],
		})
		return {"type": "ir.actions.act_window", "res_model": "account.move", "view_mode": "form", "res_id": self.receipt_move_id.id}

	def _update_settled(self):
		for contract in self.filtered(lambda c: c.state == "active"):
			if contract.line_ids and all(contract.line_ids.mapped("paid")):
				contract.state = "settled"


class InvestmentPayment(models.Model):
	_name = "veron.investment.payment"
	_description = "Investment Payment"
	_order = "contract_id, sequence"

	contract_id = fields.Many2one("veron.investment.contract", required=True, ondelete="cascade")
	sequence = fields.Integer("No.")
	due_date = fields.Date("Due Date", required=True)
	amount = fields.Monetary(required=True)
	principal = fields.Monetary()
	profit = fields.Monetary()
	currency_id = fields.Many2one(related="contract_id.currency_id")
	partner_id = fields.Many2one(related="contract_id.investor_id")
	cheque_ids = fields.One2many("veron.cheque", "veron_investment_payment_id", "Cheques")
	paid_manually = fields.Boolean("Paid in Cash")
	paid = fields.Boolean(compute="_compute_paid", store=True)

	@api.depends("paid_manually", "cheque_ids.state")
	def _compute_paid(self):
		for line in self:
			# An issued cheque is paid when the bank cashes it
			line.paid = line.paid_manually or "cashed" in line.cheque_ids.mapped("state")

	def write(self, vals):
		res = super().write(vals)
		self.contract_id._update_settled()
		return res

	def action_register_cheque(self):
		self.ensure_one()
		return {
			"type": "ir.actions.act_window", "res_model": "veron.cheque", "view_mode": "form", "target": "new",
			"name": _("Cheque of payment %s", self.sequence),
			"context": {"default_direction": "out", "default_partner_id": self.partner_id.id, "default_amount": self.amount,
				"default_due_date": self.due_date, "default_veron_investment_payment_id": self.id},
		}
