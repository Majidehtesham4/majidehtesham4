from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ReleaseDeposit(models.TransientModel):
	"""A deposit held (insurance, good performance) given back to the partner when its clearance comes: what is
	held on the deposit account goes to the partner's payable, or from our receivable when it was held from us"""

	_name = "veron.release.deposit"
	_description = "Release a Deposit"

	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	partner_id = fields.Many2one("res.partner", required=True)
	account_id = fields.Many2one("account.account", "Deposit Account", required=True,
		domain="[('code', 'in', ('211205', '211302', '111104'))]")
	held = fields.Monetary("Held Now", compute="_compute_held")
	amount = fields.Monetary(required=True)
	currency_id = fields.Many2one(related="company_id.currency_id")
	journal_id = fields.Many2one("account.journal", required=True, domain="[('type', '=', 'general')]",
		default=lambda self: self.env["account.journal"].search([("type", "=", "general"),
			("company_id", "=", self.env.company.id)], limit=1))
	date = fields.Date(required=True, default=fields.Date.context_today)
	ref = fields.Char("Description", default="آزادسازی سپرده")

	@api.depends("partner_id", "account_id")
	def _compute_held(self):
		for wizard in self:
			lines = self.env["account.move.line"].search([("partner_id", "=", wizard.partner_id.commercial_partner_id.id),
				("account_id", "=", wizard.account_id.id), ("parent_state", "=", "posted")]) if wizard.partner_id and wizard.account_id else []
			wizard.held = abs(sum(line.balance for line in lines))

	@api.onchange("partner_id", "account_id")
	def _onchange_amount(self):
		self.amount = self.held

	def action_release(self):
		self.ensure_one()
		if self.amount <= 0 or round(self.amount, 2) > round(self.held, 2):
			raise UserError(_("The amount released is more than zero and at most what is held (%s).", f"{self.held:,.0f}"))
		partner = self.partner_id.commercial_partner_id
		liability = self.account_id.account_type.startswith("liability")
		other = partner.property_account_payable_id if liability else partner.property_account_receivable_id
		# Held from the vendor: the deposit (a liability) is debited and the vendor is owed it; held from us: the
		# receivable from the customer comes back
		deposit = {"account_id": self.account_id.id, "partner_id": partner.id, "name": self.ref,
			"debit" if liability else "credit": self.amount}
		back = {"account_id": other.id, "partner_id": partner.id, "name": self.ref,
			"credit" if liability else "debit": self.amount}
		move = self.env["account.move"].create({"move_type": "entry", "journal_id": self.journal_id.id, "date": self.date,
			"ref": self.ref, "line_ids": [(0, 0, deposit), (0, 0, back)]})
		return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": move.id, "view_mode": "form"}
