from odoo import fields, models

from odoo.addons.veron_fonts_iran.models.res_company import FONTS


class Website(models.Model):
	_inherit = "website"

	veron_font = fields.Selection(FONTS, "Persian Font", default="Vazirmatn")
	veron_otp_login = fields.Boolean("Login With a Mobile Number", default=True)
	veron_otp_internal = fields.Boolean("Internal Users Too",
		help="Off, only portal users log in with a code; internal users use their password (and two-factor authentication)")
	veron_neshan_key = fields.Char("Neshan API Key", groups="base.group_system",
		help="The service key of Neshan's static maps; kept on the server")
