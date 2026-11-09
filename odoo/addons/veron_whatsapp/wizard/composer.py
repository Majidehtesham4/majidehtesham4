from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.whatsapp import number


class WhatsappComposer(models.TransientModel):
	_name = "veron.whatsapp.composer"
	_description = "Send a WhatsApp Message"

	res_model = fields.Char(readonly=True)
	res_ids = fields.Char(readonly=True)
	account_id = fields.Many2one("veron.whatsapp.account", required=True,
		default=lambda self: self.env["veron.whatsapp.account"].search([("company_id", "in", self.env.companies.ids)], limit=1))
	template_id = fields.Many2one("veron.whatsapp.template", domain="[('account_id', '=', account_id)]")
	text = fields.Text(help="Free text: only within 24 hours of the customer's last message")
	preview = fields.Text(compute="_compute_preview")
	phones = fields.Char(compute="_compute_preview")

	@api.model
	def default_get(self, fields_list):
		values = super().default_get(fields_list)
		context = self.env.context
		if context.get("active_model") and context.get("active_ids") and "res_model" not in values:
			values.update(res_model=context["active_model"], res_ids=",".join(map(str, context["active_ids"])))
		return values

	@api.model
	def _open(self, records):
		return {"type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form", "target": "new",
			"name": _("Send WhatsApp"), "context": {"active_model": records._name, "active_ids": records.ids}}

	def _records(self):
		if not self.res_model:
			return self.env["res.partner"]
		return self.env[self.res_model].browse([int(i) for i in (self.res_ids or "").split(",") if i]).exists()

	@staticmethod
	def _phone(record):
		partner = record if record._name == "res.partner" else (record["partner_id"] if "partner_id" in record._fields
			else record.env["res.partner"])
		return number(partner.phone or (partner["mobile"] if "mobile" in partner._fields else ""))

	@api.depends("template_id", "text", "res_ids")
	def _compute_preview(self):
		for wizard in self:
			records = wizard._records()
			first = records[:1]
			wizard.phones = ", ".join(filter(None, (self._phone(r) for r in records))) or False
			if wizard.template_id and first:
				try:
					wizard.preview = wizard.template_id._text(wizard.template_id._values(first))
				except UserError as error:
					wizard.preview = str(error)
			else:
				wizard.preview = wizard.text or False

	def action_send(self):
		self.ensure_one()
		records = self._records()
		if not records:
			raise UserError(_("There is no one to send to."))
		if self.template_id.model and self.template_id.model != records._name:
			raise UserError(_("The template is for %s.", self.template_id.model_id.name))
		Message = self.env["veron.whatsapp.message"]
		sent, failed = Message, []
		for record in records:
			phone = self._phone(record)
			if not phone:
				failed.append(_("%s has no phone number", record.display_name))
				continue
			try:
				sent |= Message._send(self.account_id, phone, record, template=self.template_id or None, text=self.text)
			except UserError as error:
				if len(records) == 1:
					raise
				failed.append(f"{record.display_name}: {error}")
		message = _("%s WhatsApp messages sent.", len(sent)) + ("\n" + "\n".join(failed) if failed else "")
		return {"type": "ir.actions.client", "tag": "display_notification", "params": {"message": message,
			"type": "warning" if failed else "success", "sticky": bool(failed), "next": {"type": "ir.actions.act_window_close"}}}
