from odoo import _, fields, models


class MrpBom(models.Model):
	_inherit = "mrp.bom"

	veron_version = fields.Integer("Version", default=1, copy=False)
	veron_previous_bom_id = fields.Many2one("mrp.bom", "Previous Version", copy=False)
	veron_eco_ids = fields.One2many("veron.plm.eco", "bom_id", "Engineering Changes")
	veron_eco_count = fields.Integer(compute="_compute_veron_eco_count")

	def _compute_display_name(self):
		super()._compute_display_name()
		for bom in self:
			if bom.veron_version > 1:
				bom.display_name = _("%(name)s (version %(version)s)", name=bom.display_name, version=bom.veron_version)

	def _compute_veron_eco_count(self):
		for bom in self:
			bom.veron_eco_count = len(bom.veron_eco_ids)

	def action_veron_ecos(self):
		self.ensure_one()
		return {
			"type": "ir.actions.act_window",
			"name": _("Engineering Changes"),
			"res_model": "veron.plm.eco",
			"view_mode": "list,form",
			"domain": [("bom_id", "=", self.id)],
			"context": {"default_bom_id": self.id, "default_product_tmpl_id": self.product_tmpl_id.id},
		}
