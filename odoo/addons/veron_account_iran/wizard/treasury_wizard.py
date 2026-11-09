import datetime

from odoo import fields, models


class TreasuryWizard(models.TransientModel):
	"""Treasury (خزانه‌داری): each cash and bank journal with its balance, receipts and payments of the period;
	what customers and vendors owe in the coming days; the cheques due, when the Cheques module is there"""

	_name = "veron.treasury.wizard"
	_description = "Treasury Report"

	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	date_from = fields.Date(required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
	date_to = fields.Date(required=True, default=fields.Date.context_today)
	days_ahead = fields.Integer("Days Ahead", default=30)

	def _journals(self):
		self.ensure_one()
		Line = self.env["account.move.line"]
		rows = []
		for journal in self.env["account.journal"].search([("type", "in", ("cash", "bank")),
				("company_id", "=", self.company_id.id)]):
			account = journal.default_account_id
			if not account:
				continue
			domain = [("account_id", "=", account.id), ("parent_state", "=", "posted")]
			opening = sum(Line.search(domain + [("date", "<", self.date_from)]).mapped("balance"))
			period = Line.search(domain + [("date", ">=", self.date_from), ("date", "<=", self.date_to)])
			received, paid = sum(period.mapped("debit")), sum(period.mapped("credit"))
			rows.append({"name": journal.name, "kind": "صندوق" if journal.type == "cash" else "بانک", "opening": opening,
				"in": received, "out": paid, "closing": opening + received - paid})
		return rows

	def _due(self, kind):
		"""What customers (receivable) or vendors (payable) owe in the coming days, by partner"""
		self.ensure_one()
		until = self.date_to + datetime.timedelta(days=self.days_ahead or 0)
		account_type = "asset_receivable" if kind == "receivable" else "liability_payable"
		lines = self.env["account.move.line"].search([("company_id", "=", self.company_id.id),
			("account_id.account_type", "=", account_type), ("parent_state", "=", "posted"), ("reconciled", "=", False),
			("date_maturity", "<=", until), ("amount_residual", "!=", 0)])
		by_partner = {}
		for line in lines:
			name = line.partner_id.name or "-"
			by_partner[name] = by_partner.get(name, 0.0) + abs(line.amount_residual)
		return sorted(by_partner.items(), key=lambda item: -item[1])

	def _cheques(self):
		"""The cheques due in the period and the coming days, when the Cheques module is installed"""
		self.ensure_one()
		if "veron.cheque" not in self.env:
			return None
		until = self.date_to + datetime.timedelta(days=self.days_ahead or 0)
		Cheque = self.env["veron.cheque"]
		fields_ = Cheque._fields
		# Still to be cashed: in hand or in collection, or issued and not cancelled
		domain = [("company_id", "=", self.company_id.id), ("state", "in", ("hand", "collection", "issued"))]
		if "due_date" in fields_:
			domain += [("due_date", ">=", self.date_from), ("due_date", "<=", until)]
		rows = []
		for cheque in Cheque.search(domain, order="due_date" if "due_date" in fields_ else "id"):
			rows.append({"direction": cheque.direction if "direction" in fields_ else "",
				"partner": cheque.partner_id.name or "", "serial": cheque.serial or "",
				"due": cheque.due_date if "due_date" in fields_ else False, "amount": cheque.amount,
				"state": dict(fields_["state"]._description_selection(self.env)).get(cheque.state) if "state" in fields_ else ""})
		return rows

	def action_print(self):
		return self.env.ref("veron_account_iran.action_report_treasury").report_action(self)
