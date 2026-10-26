from odoo import fields, models


class CrmLead(models.Model):
	_inherit = "crm.lead"

	veron_vehicle_id = fields.Many2one("veron.vehicle", "Car", index="btree_not_null")
