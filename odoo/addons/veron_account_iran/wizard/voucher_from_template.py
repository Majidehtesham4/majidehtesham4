from odoo import _, fields, models
from odoo.exceptions import UserError


class VoucherFromTemplate(models.TransientModel):
	_name = "veron.voucher.from.template"
	_description = "Voucher From a Template"

	template_id = fields.Many2one("veron.voucher.template", required=True)
	amount = fields.Monetary(required=True)
	currency_id = fields.Many2one(related="template_id.company_id.currency_id")
	date = fields.Date(required=True, default=fields.Date.context_today)
	ref = fields.Char("Description")

	def action_make(self):
		self.ensure_one()
		if self.amount <= 0:
			raise UserError(_("The amount is more than zero."))
		move = self.template_id._make(self.amount, self.date, self.ref)
		return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": move.id, "view_mode": "form"}
