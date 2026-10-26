import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
	_inherit = "product.template"

	veron_sstid = fields.Char("Moadian Product ID", help="The 13-digit id of the goods or the service (شناسه کالا/خدمت) in the tax organization's list")

	@api.constrains("veron_sstid")
	def _check_veron_sstid(self):
		for product in self:
			if product.veron_sstid and not re.fullmatch(r"\d{13}", product.veron_sstid):
				raise ValidationError(_("The Moadian product id has 13 digits."))


class UomUom(models.Model):
	_inherit = "uom.uom"

	veron_moadian_unit = fields.Char("Moadian Unit Code", help="The code of the unit in the tax organization's list, as 1627 for a piece")
