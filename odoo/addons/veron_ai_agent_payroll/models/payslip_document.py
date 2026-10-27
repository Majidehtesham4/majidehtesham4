"""The PDF of a payslip, kept so that only the employee it belongs to and payroll managers open it. The
file is an attachment of this record, so opening it follows this record's access rules."""

from odoo import _, fields, models
from odoo.exceptions import AccessError


class PayslipDocument(models.Model):
	_name = "veron.payslip.document"
	_description = "Payslip PDF"
	_order = "date_from desc, employee_id"

	name = fields.Char(required=True, readonly=True)
	payslip_id = fields.Many2one("hr.payslip", required=True, readonly=True, ondelete="cascade", index=True)
	employee_id = fields.Many2one(related="payslip_id.employee_id", store=True, index=True)
	user_id = fields.Many2one(related="employee_id.user_id", store=True, string="Employee's User")
	company_id = fields.Many2one(related="payslip_id.company_id", store=True, index=True)
	date_from = fields.Date(related="payslip_id.date_from", store=True)
	month = fields.Char(readonly=True)
	attachment_id = fields.Many2one("ir.attachment", readonly=True, ondelete="set null")
	prepared_at = fields.Datetime(readonly=True)

	_payslip_unique = models.Constraint("unique (payslip_id)", "A payslip has one PDF.")

	def _prepare(self, payslip, month):
		"""The PDF rendered by the payroll report, replacing an older one of the same payslip"""
		document = self.sudo().search([("payslip_id", "=", payslip.id)], limit=1) or self.sudo().create(
			{"payslip_id": payslip.id, "name": payslip.name, "month": month})
		pdf, _type = self.env["ir.actions.report"].sudo()._render_qweb_pdf("payroll.action_report_payslip", payslip.ids)
		old = document.attachment_id
		document.write({"name": payslip.name, "month": month, "prepared_at": fields.Datetime.now(),
			"attachment_id": self.env["ir.attachment"].sudo().create({
				"name": f"{payslip.name}.pdf", "raw": pdf, "mimetype": "application/pdf", "public": False,
				"res_model": self._name, "res_id": document.id}).id})
		old.unlink()
		return document

	def action_download(self):
		self.ensure_one()
		self.check_access("read")
		if not self.attachment_id:
			raise AccessError(_("The PDF of this payslip is not ready."))
		return {"type": "ir.actions.act_url", "url": f"/web/content/{self.attachment_id.id}?download=true", "target": "self"}
