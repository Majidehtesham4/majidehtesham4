from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.veron_core.models import jalali


def add_shamsi_months(day, months):
	"""The same day of the Shamsi month, months later; the last day when the month is shorter"""
	jy, jm, jd = jalali.to_jalali(day)
	index = jy * 12 + jm - 1 + months
	jy, jm = divmod(index, 12)
	jm += 1
	return jalali.to_gregorian(jy, jm, min(jd, jalali.month_length(jy, jm)))


def schedule(financed, monthly_rate, months, interval=1):
	"""Equal instalments of a flat-rate loan: [(amount, principal, interest)], the rounding on the last"""
	interest = round(financed * monthly_rate / 100 * months * interval)
	total = financed + interest
	amount, principal_part, interest_part = round(total / months), round(financed / months), round(interest / months)
	rows = [(amount, principal_part, amount - principal_part) for _i in range(months - 1)]
	last_principal = financed - principal_part * (months - 1)
	last = total - amount * (months - 1)
	rows.append((last, last_principal, last - last_principal))
	return rows, interest


class InstalmentSale(models.Model):
	_name = "veron.instalment.sale"
	_description = "Instalment Sale"
	_inherit = ["mail.thread", "mail.activity.mixin"]
	_order = "date desc, id desc"

	name = fields.Char(required=True, readonly=True, copy=False, default="/")
	customer_id = fields.Many2one("res.partner", "Customer", required=True, tracking=True)
	vehicle_id = fields.Many2one("veron.vehicle", "Vehicle", tracking=True, domain=[("state", "in", ("ready", "reserved"))])
	description = fields.Char(help="What is sold, when it is not a car of the list")
	date = fields.Date(default=fields.Date.context_today, required=True)
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
	currency_id = fields.Many2one(related="company_id.currency_id")
	state = fields.Selection([("draft", "Draft"), ("active", "Active"), ("settled", "Settled"), ("cancelled", "Cancelled")],
		default="draft", required=True, tracking=True, copy=False)
	sale_price = fields.Monetary("Sale Price", required=True, tracking=True)
	down_payment = fields.Monetary("Down Payment", tracking=True)
	other_costs = fields.Monetary("Other Costs", help="Paperwork and the like, added to the amount paid by instalments")
	monthly_rate = fields.Float("Monthly Profit (%)", tracking=True)
	months = fields.Integer("Number of Instalments", default=12, required=True)
	interval_months = fields.Integer("Months Between Instalments", default=1, required=True)
	first_due_date = fields.Date("First Due Date")
	financed = fields.Monetary("Paid by Instalments", compute="_compute_amounts", store=True)
	total_interest = fields.Monetary("Profit of the Sale", compute="_compute_amounts", store=True)
	total_payable = fields.Monetary("Total of the Instalments", compute="_compute_amounts", store=True)
	instalment_amount = fields.Monetary("Each Instalment", compute="_compute_amounts", store=True)
	line_ids = fields.One2many("veron.instalment", "sale_id", "Instalments", copy=False)
	paid_total = fields.Monetary("Paid", compute="_compute_paid")
	outstanding = fields.Monetary("Left to Pay", compute="_compute_paid")
	overdue_count = fields.Integer("Overdue Instalments", compute="_compute_paid")
	invoice_id = fields.Many2one("account.move", "Invoice", readonly=True, copy=False)
	note = fields.Text()

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if vals.get("name", "/") == "/":
				vals["name"] = self.env["ir.sequence"].next_by_code("veron.instalment.sale") or "/"
		return super().create(vals_list)

	@api.constrains("months", "interval_months", "down_payment", "sale_price")
	def _check_terms(self):
		for sale in self:
			if sale.months < 1 or sale.interval_months < 1:
				raise ValidationError(_("There is at least one instalment, at least a month apart."))
			if sale.down_payment > sale.sale_price + sale.other_costs:
				raise ValidationError(_("The down payment is more than the price."))

	@api.onchange("vehicle_id")
	def _onchange_vehicle(self):
		if self.vehicle_id:
			self.sale_price = self.vehicle_id.asking_price
			if self.vehicle_id.customer_id and not self.customer_id:
				self.customer_id = self.vehicle_id.customer_id

	@api.depends("sale_price", "down_payment", "other_costs", "monthly_rate", "months", "interval_months")
	def _compute_amounts(self):
		for sale in self:
			financed = sale.sale_price + sale.other_costs - sale.down_payment
			if sale.months < 1 or sale.interval_months < 1 or financed <= 0:
				sale.financed, sale.total_interest, sale.total_payable, sale.instalment_amount = max(financed, 0), 0, max(financed, 0), 0
				continue
			rows, interest = schedule(financed, sale.monthly_rate, sale.months, sale.interval_months)
			sale.financed, sale.total_interest = financed, interest
			sale.total_payable, sale.instalment_amount = financed + interest, rows[0][0]

	@api.depends("line_ids.paid", "line_ids.amount", "line_ids.due_date")
	def _compute_paid(self):
		today = fields.Date.context_today(self)
		for sale in self:
			paid = sale.line_ids.filtered("paid")
			sale.paid_total = sum(paid.mapped("amount"))
			sale.outstanding = sum(sale.line_ids.mapped("amount")) - sale.paid_total
			sale.overdue_count = len(sale.line_ids.filtered(lambda l: not l.paid and l.due_date < today))

	def action_confirm(self):
		for sale in self:
			if sale.state != "draft":
				raise UserError(_("%s is already confirmed.", sale.name))
			if sale.financed <= 0:
				raise UserError(_("Nothing is left to pay by instalments."))
			rows, _interest = schedule(sale.financed, sale.monthly_rate, sale.months, sale.interval_months)
			first = sale.first_due_date or add_shamsi_months(sale.date, sale.interval_months)
			sale.line_ids = [(0, 0, {
				"sequence": i + 1,
				"due_date": add_shamsi_months(first, i * sale.interval_months),
				"amount": amount, "principal": principal, "interest": interest,
			}) for i, (amount, principal, interest) in enumerate(rows)]
			sale.state = "active"
			if sale.vehicle_id:
				sale.vehicle_id.write({"customer_id": sale.customer_id.id, "sale_price": sale.sale_price, "instalment_sale_id": sale.id})
				if sale.vehicle_id.state in ("ready", "reserved"):
					sale.vehicle_id.action_sell()
		return True

	def action_cancel(self):
		for sale in self:
			if sale.line_ids.filtered("paid"):
				raise UserError(_("Instalments of %s are paid; it cannot be cancelled.", sale.name))
			sale.line_ids.unlink()
			sale.state = "cancelled"
		return True

	def action_create_invoice(self):
		"""A draft invoice of the sale: the car, the other costs and the profit of the instalments"""
		self.ensure_one()
		if self.invoice_id:
			raise UserError(_("The invoice is already made."))
		vehicle = self.vehicle_id
		text = vehicle._invoice_text() if vehicle else (self.description or self.name)
		lines = [(0, 0, {"product_id": self.env.ref("veron_dealership.product_vehicle").id, "name": text, "quantity": 1,
			"price_unit": self.sale_price})]
		if self.other_costs:
			lines.append((0, 0, {"product_id": self.env.ref("veron_dealership.product_service").id, "name": _("Other costs"),
				"quantity": 1, "price_unit": self.other_costs}))
		if self.total_interest:
			lines.append((0, 0, {"product_id": self.env.ref("veron_dealership.product_instalment_profit").id,
				"name": _("Profit of the instalment sale %s", self.name), "quantity": 1, "price_unit": self.total_interest}))
		self.invoice_id = self.env["account.move"].create({
			"move_type": "out_invoice", "partner_id": self.customer_id.id, "invoice_origin": self.name,
			"invoice_date": self.date, "company_id": self.company_id.id, "invoice_line_ids": lines,
		})
		if vehicle:
			vehicle.sale_invoice_id = self.invoice_id
		return {"type": "ir.actions.act_window", "res_model": "account.move", "view_mode": "form", "res_id": self.invoice_id.id}

	def _update_settled(self):
		for sale in self.filtered(lambda s: s.state == "active"):
			if sale.line_ids and all(sale.line_ids.mapped("paid")):
				sale.state = "settled"

	@api.model
	def _cron_remind(self):
		"""A to-do for the salesperson on each overdue instalment, once"""
		today = fields.Date.context_today(self)
		lines = self.env["veron.instalment"].search([("paid", "=", False), ("due_date", "<", today), ("reminded", "=", False),
			("sale_id.state", "=", "active")])
		for line in lines:
			line.sale_id.activity_schedule("mail.mail_activity_data_todo", date_deadline=today,
				summary=_("Instalment %(n)s of %(sale)s is overdue", n=line.sequence, sale=line.sale_id.name),
				user_id=line.sale_id.create_uid.id or self.env.uid)
		lines.reminded = True


class Instalment(models.Model):
	_name = "veron.instalment"
	_description = "Instalment"
	_order = "sale_id, sequence"

	sale_id = fields.Many2one("veron.instalment.sale", required=True, ondelete="cascade")
	sequence = fields.Integer("No.")
	due_date = fields.Date("Due Date", required=True)
	amount = fields.Monetary(required=True)
	principal = fields.Monetary()
	interest = fields.Monetary("Profit")
	currency_id = fields.Many2one(related="sale_id.currency_id")
	partner_id = fields.Many2one(related="sale_id.customer_id")
	cheque_ids = fields.One2many("veron.cheque", "veron_instalment_id", "Cheques")
	paid_manually = fields.Boolean("Paid in Cash")
	paid = fields.Boolean(compute="_compute_paid", store=True)
	reminded = fields.Boolean(copy=False)

	@api.depends("paid_manually", "cheque_ids.state")
	def _compute_paid(self):
		for line in self:
			line.paid = line.paid_manually or any(state in ("cashed", "endorsed") for state in line.cheque_ids.mapped("state"))

	def write(self, vals):
		res = super().write(vals)
		self.sale_id._update_settled()
		return res

	def action_register_cheque(self):
		self.ensure_one()
		return {
			"type": "ir.actions.act_window", "res_model": "veron.cheque", "view_mode": "form", "target": "new",
			"name": _("Cheque of instalment %s", self.sequence),
			"context": {"default_direction": "in", "default_partner_id": self.partner_id.id, "default_amount": self.amount,
				"default_due_date": self.due_date, "default_veron_instalment_id": self.id},
		}
