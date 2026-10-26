from odoo import fields, models


class Cheque(models.Model):
	_inherit = "veron.cheque"

	veron_instalment_id = fields.Many2one("veron.instalment", "Instalment", index="btree_not_null", ondelete="set null")
	veron_investment_payment_id = fields.Many2one("veron.investment.payment", "Investment Payment", index="btree_not_null",
		ondelete="set null")

	def write(self, vals):
		res = super().write(vals)
		if "state" in vals:
			# The instalment or the payment is paid with its cheque; the contract is settled with the last one
			self.veron_instalment_id.sale_id._update_settled()
			self.veron_investment_payment_id.contract_id._update_settled()
		return res
