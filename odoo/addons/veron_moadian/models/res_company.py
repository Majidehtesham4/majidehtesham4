from odoo import fields, models

from ..tools.client import DEFAULT_URL


class ResCompany(models.Model):
	_inherit = "res.company"

	veron_moadian_memory_id = fields.Char("Tax Memory ID", help="The 6-character id of the tax memory (شناسه یکتای حافظه مالیاتی)")
	veron_moadian_private_key = fields.Text("Moadian Private Key", groups="base.group_system", copy=False)
	veron_moadian_certificate = fields.Text("Moadian Certificate", groups="base.group_system", copy=False,
		help="The certificate (PEM) the tax organization issued for the key")
	veron_moadian_url = fields.Char("Moadian Address", default=DEFAULT_URL)
	veron_moadian_active = fields.Boolean("Send to Moadian",
		help="Invoices are sent only when this is on, the key and the certificate are set, and someone sends each one")
