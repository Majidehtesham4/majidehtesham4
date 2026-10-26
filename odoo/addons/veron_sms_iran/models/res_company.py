from odoo import fields, models

from ..tools.sms_api import SmsApiIran


class ResCompany(models.Model):
	_inherit = "res.company"

	veron_sms_provider = fields.Selection(
		[("kavenegar", "Kavenegar"), ("smsir", "SMS.ir"), ("melipayamak", "Melipayamak")],
		string="Iranian SMS Panel",
		help="When set, every SMS goes through this panel instead of Odoo's paid service",
	)
	veron_sms_key = fields.Char("SMS API Key", groups="base.group_system")
	veron_sms_username = fields.Char("SMS Username", groups="base.group_system")
	veron_sms_line = fields.Char("SMS Sender Line", help="The panel's line number the SMS are sent from")

	def _get_sms_api_class(self):
		self.ensure_one()
		if self.veron_sms_provider:
			return SmsApiIran
		return super()._get_sms_api_class()
