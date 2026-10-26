from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import jose


class ResConfigSettings(models.TransientModel):
	_inherit = "res.config.settings"

	veron_moadian_memory_id = fields.Char(related="company_id.veron_moadian_memory_id", readonly=False)
	veron_moadian_url = fields.Char(related="company_id.veron_moadian_url", readonly=False)
	veron_moadian_active = fields.Boolean(related="company_id.veron_moadian_active", readonly=False)
	veron_moadian_key_set = fields.Boolean("Key Set", compute="_compute_veron_moadian_key")
	veron_moadian_certificate_set = fields.Boolean("Certificate Set", compute="_compute_veron_moadian_key")
	# Written only: a key or a certificate given here is stored and never shown again
	veron_moadian_new_key = fields.Text("New Private Key")
	veron_moadian_new_certificate = fields.Text("New Certificate")

	@api.depends("company_id")
	def _compute_veron_moadian_key(self):
		for settings in self:
			company = settings.company_id.sudo()
			settings.veron_moadian_key_set = bool(company.veron_moadian_private_key)
			settings.veron_moadian_certificate_set = bool(company.veron_moadian_certificate)

	def set_values(self):
		super().set_values()
		values = {}
		if self.veron_moadian_new_key:
			try:
				jose.load_private_key(self.veron_moadian_new_key.strip())
			except ValueError as error:
				raise UserError(_("The private key is not a PEM key without a password.")) from error
			values["veron_moadian_private_key"] = self.veron_moadian_new_key.strip()
		if self.veron_moadian_new_certificate:
			try:
				jose.certificate_x5c(self.veron_moadian_new_certificate.strip())
			except ValueError as error:
				raise UserError(_("The certificate is not a PEM certificate.")) from error
			values["veron_moadian_certificate"] = self.veron_moadian_new_certificate.strip()
		if values:
			self.company_id.sudo().write(values)
		self.veron_moadian_new_key = self.veron_moadian_new_certificate = False

	def action_veron_moadian_new_key(self):
		"""A new key, kept in the database; the request for its certificate is given to download"""
		self.ensure_one()
		if not self.env.user.has_group("base.group_system"):
			raise UserError(_("Only an administrator makes the key."))
		company = self.company_id.sudo()
		if company.veron_moadian_private_key and not self.env.context.get("veron_replace"):
			raise UserError(_("A key is already set. Making a new one needs a new certificate from the tax organization."))
		national_id = company.partner_id.veron_national_id or company.vat or ""
		key_pem, request_pem, public_pem = jose.new_key_and_request(company.name, national_id, company.name)
		company.write({"veron_moadian_private_key": key_pem, "veron_moadian_certificate": False})
		attachment = self.env["ir.attachment"].create({
			"name": "moadian-request.csr",
			"raw": (request_pem + "\n" + public_pem).encode(),
			"mimetype": "text/plain",
			"res_model": "res.company",
			"res_id": company.id,
		})
		return {"type": "ir.actions.act_url", "url": f"/web/content/{attachment.id}?download=true", "target": "self"}
