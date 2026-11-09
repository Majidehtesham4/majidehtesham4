from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class VoucherTemplate(models.Model):
	"""An entry made often (rent, salaries paid, a monthly fee), its accounts and their shares; filled with an
	amount it becomes a draft entry"""

	_name = "veron.voucher.template"
	_description = "Voucher Template"
	_order = "name"

	name = fields.Char(required=True)
	active = fields.Boolean(default=True)
	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	journal_id = fields.Many2one("account.journal", required=True, check_company=True,
		default=lambda self: self.env["account.journal"].search([("type", "=", "general"),
			("company_id", "=", self.env.company.id)], limit=1))
	label = fields.Char("Description", help="The description of the entry; its lines keep their own")
	line_ids = fields.One2many("veron.voucher.template.line", "template_id", "Lines", copy=True)

	@api.constrains("line_ids")
	def _check_shares(self):
		for template in self:
			for side in ("debit", "credit"):
				share = sum(template.line_ids.filtered(lambda l, s=side: l.side == s).mapped("share"))
				if template.line_ids and round(share, 2) != 100:
					raise ValidationError(_("The %(side)s shares of «%(name)s» add up to %(share)s%%, not 100%%.",
						side=dict(self.line_ids._fields["side"]._description_selection(self.env))[side],
						name=template.name, share=f"{share:g}"))

	def _make(self, amount, date, ref=None):
		"""The draft entry of the template for an amount; the rounding of the shares goes to the last line of
		each side, so the entry balances"""
		self.ensure_one()
		lines, currency = [], self.company_id.currency_id
		for side in ("debit", "credit"):
			parts = self.line_ids.filtered(lambda l, s=side: l.side == s)
			left = currency.round(amount)
			for index, part in enumerate(parts):
				value = left if index == len(parts) - 1 else currency.round(amount * part.share / 100)
				left -= value
				lines.append((0, 0, {"account_id": part.account_id.id, "partner_id": part.partner_id.id or False,
					"name": part.label or self.label or self.name, side: value}))
		return self.env["account.move"].create({"move_type": "entry", "journal_id": self.journal_id.id, "date": date,
			"ref": ref or self.label or self.name, "line_ids": lines})


class VoucherTemplateLine(models.Model):
	_name = "veron.voucher.template.line"
	_description = "Voucher Template Line"
	_order = "template_id, side desc, sequence, id"

	template_id = fields.Many2one("veron.voucher.template", required=True, ondelete="cascade")
	sequence = fields.Integer(default=10)
	side = fields.Selection([("debit", "Debit"), ("credit", "Credit")], required=True, default="debit")
	account_id = fields.Many2one("account.account", required=True)
	partner_id = fields.Many2one("res.partner")
	share = fields.Float("Share (%)", default=100.0)
	label = fields.Char("Description")
