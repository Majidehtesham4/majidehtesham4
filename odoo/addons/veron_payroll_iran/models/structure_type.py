from odoo import api, models

# Odoo's own kinds of pay, named in English in a plain field (not translatable)
PERSIAN = {"hr.structure_type_employee": ("Employee", "کارمند"), "hr.structure_type_worker": ("Worker", "کارگر")}


class StructureType(models.Model):
	_inherit = "hr.payroll.structure.type"

	@api.model
	def _veron_persian_names(self):
		"""The kinds of pay Odoo makes, named in Persian while they keep Odoo's English name"""
		for xmlid, (english, persian) in PERSIAN.items():
			kind = self.env.ref(xmlid, raise_if_not_found=False)
			if kind and kind.name == english:
				kind.name = persian
