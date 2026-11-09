from odoo import _, fields, models

from odoo.addons.veron_core.models import jalali


class RenumberVouchers(models.TransientModel):
	"""The voucher numbers of a Shamsi year put in the order of the dates (مرتب‌سازی شماره اسناد), before the
	year is closed"""

	_name = "veron.renumber.vouchers"
	_description = "Put Voucher Numbers in Date Order"

	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	year = fields.Integer("Shamsi Year", required=True,
		default=lambda self: jalali.to_jalali(fields.Date.context_today(self))[0])

	def action_renumber(self):
		self.ensure_one()
		count = self.env["account.move"]._veron_renumber(self.company_id, self.year)
		return {"type": "ir.actions.client", "tag": "display_notification", "params": {"type": "success",
			"message": _("%(count)s vouchers of %(year)s numbered in date order.", count=count, year=self.year)}}
