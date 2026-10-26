from odoo import fields, models


class ResConfigSettings(models.TransientModel):
	_inherit = "res.config.settings"

	veron_sms_provider = fields.Selection(related="company_id.veron_sms_provider", readonly=False)
	veron_sms_key = fields.Char(related="company_id.veron_sms_key", readonly=False)
	veron_sms_username = fields.Char(related="company_id.veron_sms_username", readonly=False)
	veron_sms_line = fields.Char(related="company_id.veron_sms_line", readonly=False)
