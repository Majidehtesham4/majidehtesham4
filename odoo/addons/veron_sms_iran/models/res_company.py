from odoo import fields, models

from ..tools.sms_api import SmsApiIran

PROVIDERS = [
	("kavenegar", "Kavenegar"), ("smsir", "SMS.ir"), ("melipayamak", "Melipayamak"), ("farapayamak", "Farapayamak"),
	("farazsms", "FarazSMS (IPPanel)"), ("ghasedak", "Ghasedak"),
]


class ResCompany(models.Model):
	_inherit = "res.company"

	veron_sms_provider = fields.Selection(PROVIDERS, string="Iranian SMS Panel",
		help="When set, every SMS goes through this panel instead of Odoo's paid service")
	veron_sms_key = fields.Char("SMS API Key", groups="base.group_system")
	veron_sms_username = fields.Char("SMS Username", groups="base.group_system")
	veron_sms_line = fields.Char("SMS Sender Line", help="The panel's line number the SMS are sent from")
	veron_sms_backup_ids = fields.One2many("veron.sms.panel", "company_id", "Backup SMS Panels",
		help="Tried in their order when the main panel is not reached, has no credit or refuses its account")

	def _get_sms_api_class(self):
		self.ensure_one()
		if self.veron_sms_provider:
			return SmsApiIran
		return super()._get_sms_api_class()

	def _veron_sms_backups(self):
		self.ensure_one()
		return self.sudo().veron_sms_backup_ids.filtered("active").sorted("sequence")


class SmsPanel(models.Model):
	"""A backup panel of the SMS hub"""

	_name = "veron.sms.panel"
	_description = "Backup SMS Panel"
	_order = "sequence, id"

	sequence = fields.Integer(default=10)
	active = fields.Boolean(default=True)
	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, ondelete="cascade")
	provider = fields.Selection(PROVIDERS, required=True)
	key = fields.Char("API Key or Password")
	username = fields.Char()
	line = fields.Char("Sender Line")
