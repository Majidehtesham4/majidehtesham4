from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..tools.identifiers import is_valid_legal_national_id, is_valid_national_code, normalize_digits


class ResPartner(models.Model):
	_inherit = "res.partner"

	veron_national_id = fields.Char("National ID",
		help="The 10-digit national code of a person, or the 11-digit national id of a company")

	@api.constrains("veron_national_id")
	def _check_veron_national_id(self):
		for partner in self:
			code = normalize_digits(partner.veron_national_id)
			if code and not (is_valid_national_code(code) or is_valid_legal_national_id(code)):
				raise ValidationError(_("%s is not a valid national code (10 digits) or national id (11 digits).", partner.veron_national_id))

	@api.onchange("veron_national_id")
	def _onchange_veron_national_id(self):
		if self.veron_national_id:
			self.veron_national_id = normalize_digits(self.veron_national_id)
