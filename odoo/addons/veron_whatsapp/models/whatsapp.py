import datetime
import hashlib
import hmac
import re

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

TIMEOUT = 30
WINDOW = datetime.timedelta(hours=24)


def number(phone):
	"""A phone number as WhatsApp writes it, with the country's code and no sign: «09121234567» → «989121234567»"""
	digits = re.sub(r"\D", "", (phone or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
	if digits.startswith("00"):
		digits = digits[2:]
	elif digits.startswith("0"):
		digits = "98" + digits[1:]
	elif len(digits) == 10 and digits.startswith("9"):
		digits = "98" + digits
	return digits


class WhatsappAccount(models.Model):
	_name = "veron.whatsapp.account"
	_description = "WhatsApp Business Number"

	name = fields.Char(required=True)
	active = fields.Boolean(default=True)
	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	phone_number_id = fields.Char("Phone Number ID", required=True, help="The id of the number in Meta's WhatsApp Manager")
	token = fields.Char("Access Token", groups="base.group_system", copy=False)
	app_secret = fields.Char("App Secret", groups="base.group_system", copy=False,
		help="Signs what the webhook receives; without it the webhook accepts nothing")
	verify_token = fields.Char("Webhook Verify Token", groups="base.group_system", copy=False,
		default=lambda self: hashlib.sha256(fields.Datetime.now().isoformat().encode() + self.env.cr.dbname.encode()).hexdigest()[:24])
	api_url = fields.Char("API Address", default="https://graph.facebook.com/v21.0/", required=True,
		help="Meta's Graph API, or a relay that passes to it from a server in Iran")
	webhook_url = fields.Char(compute="_compute_webhook_url")

	def _compute_webhook_url(self):
		for account in self:
			account.webhook_url = f"{account.get_base_url()}/veron/whatsapp/webhook"

	def _post(self, payload):
		self.ensure_one()
		token = self.sudo().token
		if not token:
			raise UserError(_("The access token of %s is not entered.", self.name))
		try:
			response = requests.post(f"{self.api_url.rstrip('/')}/{self.phone_number_id}/messages", json=payload,
				headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
		except requests.exceptions.RequestException as error:
			raise UserError(_("WhatsApp could not be reached (%s). A server in Iran reaches it only through a route "
				"out of the country, given as the API address.", error)) from error
		try:
			answer = response.json()
		except ValueError:
			answer = {}
		if response.status_code != 200 or not answer.get("messages"):
			error = answer.get("error") or {}
			raise UserError(_("WhatsApp refused the message: %s", error.get("message") or response.status_code))
		return answer["messages"][0]["id"]

	def _check_signature(self, body, signature):
		secret = self.sudo().app_secret
		if not secret or not signature:
			return False
		expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
		return hmac.compare_digest(expected, signature)


class WhatsappTemplate(models.Model):
	"""A template approved by WhatsApp, named as in the WhatsApp Manager; its values from the record"""

	_name = "veron.whatsapp.template"
	_description = "WhatsApp Template"

	name = fields.Char("Template Name", required=True, help="Exactly as approved in the WhatsApp Manager")
	language = fields.Char(default="fa", required=True)
	account_id = fields.Many2one("veron.whatsapp.account", required=True)
	model_id = fields.Many2one("ir.model", "For", ondelete="cascade", help="Empty: for contacts")
	model = fields.Char(related="model_id.model")
	body = fields.Text("Text", help="The text as approved, with {{1}}, {{2}}... where the values go")
	value_fields = fields.Char("Values", help="The fields of the record that give {{1}}, {{2}}..., separated by commas, "
		"e.g. «partner_id.name, name, amount_total»")

	def _values(self, record):
		values = []
		for path in filter(None, (p.strip() for p in (self.value_fields or "").split(","))):
			value = record.sudo()
			for name in path.split("."):
				if name not in value._fields:
					raise UserError(_("%(model)s has no field %(field)s.", model=value._name, field=name))
				value = value[name]
			if isinstance(value, models.BaseModel):
				value = value.display_name
			values.append("" if value is False or value is None else str(value))
		return values

	def action_add_to_menu(self):
		"""The composer in the action menu of the template's records"""
		for template in self:
			model = template.model_id or self.env["ir.model"]._get("res.partner")
			if not self.env["ir.actions.act_window"].search_count([("res_model", "=", "veron.whatsapp.composer"),
					("binding_model_id", "=", model.id)]):
				self.env["ir.actions.act_window"].create({"name": _("Send WhatsApp"), "res_model": "veron.whatsapp.composer",
					"view_mode": "form", "target": "new", "binding_model_id": model.id, "binding_view_types": "form,list"})

	def _text(self, values):
		text = self.body or self.name
		for index, value in enumerate(values, 1):
			text = text.replace("{{%s}}" % index, value)
		return text


class WhatsappMessage(models.Model):
	_name = "veron.whatsapp.message"
	_description = "WhatsApp Message"
	_order = "id desc"
	_rec_name = "phone"

	account_id = fields.Many2one("veron.whatsapp.account", required=True, index=True)
	company_id = fields.Many2one(related="account_id.company_id", store=True)
	direction = fields.Selection([("out", "Sent"), ("in", "Received")], required=True, default="out")
	phone = fields.Char(required=True, index=True)
	partner_id = fields.Many2one("res.partner", index=True)
	body = fields.Text()
	template_id = fields.Many2one("veron.whatsapp.template")
	res_model = fields.Char(index=True)
	res_id = fields.Many2oneReference(model_field="res_model")
	wa_id = fields.Char("WhatsApp ID", index=True, copy=False)
	state = fields.Selection([("sent", "Sent"), ("delivered", "Delivered"), ("read", "Read"), ("failed", "Failed"),
		("received", "Received")], required=True, default="sent")
	error = fields.Char()

	@api.model
	def _window_open(self, account, phone):
		"""Free text is allowed within 24 hours of the customer's last message"""
		return bool(self.search_count([("account_id", "=", account.id), ("phone", "=", phone), ("direction", "=", "in"),
			("create_date", ">=", fields.Datetime.now() - WINDOW)]))

	@api.model
	def _send(self, account, phone, record=None, template=None, text=None):
		phone = number(phone)
		if len(phone) < 10:
			raise UserError(_("«%s» is not a phone number.", phone))
		partner = record if record is not None and record._name == "res.partner" else \
			(record["partner_id"] if record is not None and "partner_id" in record._fields else self.env["res.partner"])
		if template:
			values = template._values(record) if record is not None else []
			payload = {"messaging_product": "whatsapp", "to": phone, "type": "template", "template": {
				"name": template.name, "language": {"code": template.language},
				"components": [{"type": "body", "parameters": [{"type": "text", "text": v} for v in values]}] if values else []}}
			body = template._text(values)
		else:
			if not text:
				raise UserError(_("The message has no text."))
			if not self._window_open(account, phone):
				raise UserError(_("WhatsApp allows a free text only within 24 hours of the customer's last message; "
					"send an approved template."))
			payload = {"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": text}}
			body = text
		message = self.create({"account_id": account.id, "phone": phone, "partner_id": partner.id or False, "body": body,
			"template_id": template.id if template else False, "res_model": record._name if record is not None else False,
			"res_id": record.id if record is not None else False})
		try:
			wa_id = account._post(payload)
		except UserError as error:
			message.sudo().write({"state": "failed", "error": str(error)[:250]})
			raise
		message.sudo().wa_id = wa_id
		if record is not None and hasattr(record, "message_post"):
			record.message_post(body=_("WhatsApp to %(phone)s: %(text)s", phone=phone, text=body), message_type="comment",
				subtype_xmlid="mail.mt_note")
		return message

	# --- what the webhook brings

	STATES = {"sent": 1, "delivered": 2, "read": 3, "failed": 4}

	@api.model
	def _receive(self, account, payload):
		for entry in payload.get("entry") or []:
			for change in entry.get("changes") or []:
				value = change.get("value") or {}
				for status in value.get("statuses") or []:
					message = self.search([("wa_id", "=", status.get("id")), ("account_id", "=", account.id)], limit=1)
					state = status.get("status")
					# Out of order deliveries do not take a message back
					if message and state in self.STATES and self.STATES[state] > self.STATES.get(message.state, 0):
						errors = status.get("errors") or [{}]
						message.write({"state": state, "error": errors[0].get("title") if state == "failed" else False})
				names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts") or []}
				for item in value.get("messages") or []:
					if self.search_count([("wa_id", "=", item.get("id"))]):
						continue
					self._incoming(account, item, names.get(item.get("from")))

	def _incoming(self, account, item, name):
		phone = number(item.get("from"))
		kind = item.get("type")
		text = (item.get("text") or {}).get("body") if kind == "text" else \
			(item.get(kind) or {}).get("caption") or _("(a %s message)", kind)
		Partner = self.env["res.partner"].sudo()
		names = [n for n in ("phone", "mobile") if n in Partner._fields]
		# The last seven digits find the few to compare, whatever way the number was written
		tail = "%".join(phone[-7:])
		domain = ["|"] * (len(names) - 1) + [(n, "=like", f"%{tail}%") for n in names]
		partner = Partner.search(domain, limit=50).filtered(lambda p: phone in {number(p[n]) for n in names})[:1]
		message = self.create({"account_id": account.id, "phone": phone, "partner_id": partner.id, "body": text,
			"direction": "in", "state": "received", "wa_id": item.get("id"), "res_model": "res.partner" if partner else False,
			"res_id": partner.id})
		if partner:
			partner.message_post(body=_("WhatsApp from %(name)s: %(text)s", name=name or phone, text=text),
				message_type="comment", subtype_xmlid="mail.mt_note")
		return message


class ResPartner(models.Model):
	_inherit = "res.partner"

	def action_veron_whatsapp(self):
		return self.env["veron.whatsapp.composer"]._open(self)
