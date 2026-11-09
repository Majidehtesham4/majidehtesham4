from collections import OrderedDict

from odoo import _, fields, models
from odoo.exceptions import UserError


class AggregateVouchers(models.TransientModel):
	"""Several draft entries merged into one aggregated voucher (سند تجمیعی): their lines summed by account,
	partner and analytic distribution, the drafts removed and named in the new one. Posted entries and
	invoices are never merged"""

	_name = "veron.aggregate.vouchers"
	_description = "Aggregate Vouchers"

	move_ids = fields.Many2many("account.move", string="Entries", required=True,
		default=lambda self: self.env.context.get("active_ids"))
	journal_id = fields.Many2one("account.journal", required=True)
	date = fields.Date(required=True, default=fields.Date.context_today)
	ref = fields.Char("Description", required=True, default="سند تجمیعی")
	by_partner = fields.Boolean("Keep the Partners", default=True)
	net = fields.Boolean("Net Debit and Credit of an Account",
		help="One line per account (and partner) with what is left, instead of its debits and credits apart")

	def default_get(self, fields_list):
		values = super().default_get(fields_list)
		moves = self.env["account.move"].browse(self.env.context.get("active_ids") or [])
		if moves and "journal_id" in fields_list:
			values["journal_id"] = moves[0].journal_id.id
		if moves and "date" in fields_list:
			values["date"] = max(moves.mapped("date"))
		return values

	def action_aggregate(self):
		self.ensure_one()
		moves = self.move_ids
		if len(moves) < 2:
			raise UserError(_("Choose two entries or more to aggregate."))
		if any(move.state != "draft" for move in moves):
			raise UserError(_("Only draft entries are aggregated; a posted entry stays as it is."))
		if any(move.move_type != "entry" for move in moves):
			raise UserError(_("Invoices and bills are not aggregated; only journal entries are."))
		if len(moves.company_id) > 1:
			raise UserError(_("The entries are of different companies."))
		groups = OrderedDict()
		for line in moves.line_ids:
			key = (line.account_id.id, line.partner_id.id if self.by_partner else False, line.currency_id.id,
				tuple(sorted((line.analytic_distribution or {}).items())))
			group = groups.setdefault(key, {"debit": 0.0, "credit": 0.0, "amount_currency": 0.0, "line": line})
			group["debit"] += line.debit
			group["credit"] += line.credit
			group["amount_currency"] += line.amount_currency
		lines = []
		for (account, partner, currency, analytic), group in groups.items():
			sides = [(group["debit"], 0.0), (0.0, group["credit"])]
			if self.net:
				left = group["debit"] - group["credit"]
				sides = [(max(left, 0.0), max(-left, 0.0))]
			for debit, credit in sides:
				if not round(debit, 2) and not round(credit, 2):
					continue
				values = {"account_id": account, "partner_id": partner or False, "debit": debit, "credit": credit,
					"name": group["line"].account_id.name, "analytic_distribution": dict(analytic) or False}
				if currency != moves.company_id.currency_id.id and (self.net or len(sides) == 1):
					values.update(currency_id=currency, amount_currency=group["amount_currency"])
				lines.append((0, 0, values))
		names = ", ".join(moves.mapped(lambda m: m.ref or m.name or str(m.id)))
		aggregated = self.env["account.move"].create({"move_type": "entry", "journal_id": self.journal_id.id,
			"date": self.date, "ref": self.ref, "line_ids": lines, "veron_aggregated_from": names})
		aggregated.message_post(body=_("Aggregated from %(count)s draft entries: %(names)s", count=len(moves), names=names))
		moves.unlink()
		return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": aggregated.id, "view_mode": "form"}
