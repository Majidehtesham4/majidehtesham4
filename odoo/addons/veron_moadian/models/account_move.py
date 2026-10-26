import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import payload as moadian_payload
from ..tools.client import Client, MoadianError
from ..tools.tax_id import generate_tax_id

_logger = logging.getLogger(__name__)

STATES = [
	("problems", "Needs Fixes"),
	("prepared", "Ready to Send"),
	("sent", "Sent, Awaiting the Result"),
	("accepted", "Accepted"),
	("rejected", "Rejected"),
]


class AccountMove(models.Model):
	_inherit = "account.move"

	veron_tax_id = fields.Char("Tax Number", readonly=True, copy=False, index="btree_not_null",
		help="The 22-character unique tax number of the invoice (شماره منحصر به فرد مالیاتی)")
	veron_moadian_serial = fields.Integer("Moadian Serial", readonly=True, copy=False)
	veron_moadian_state = fields.Selection(STATES, "Moadian", readonly=True, copy=False, tracking=True)
	veron_moadian_problems = fields.Text("Moadian Problems", readonly=True, copy=False)
	veron_moadian_payload = fields.Text("Moadian Invoice", readonly=True, copy=False)
	veron_moadian_reference = fields.Char("Moadian Reference", readonly=True, copy=False)
	veron_moadian_uid = fields.Char("Moadian Request ID", readonly=True, copy=False)
	veron_moadian_sent = fields.Datetime("Sent to Moadian", readonly=True, copy=False)
	veron_moadian_result = fields.Text("Moadian Result", readonly=True, copy=False)

	def _veron_moadian_messages(self, problems):
		words = {
			"currency": lambda v: self.env._("Only rial invoices are sent; this one is in %(currency)s.", **v),
			"memory": lambda v: self.env._("Set the tax memory ID in Accounting settings, Moadian."),
			"seller": lambda v: self.env._("Set the economic code (Tax ID) of the company."),
			"sstid": lambda v: self.env._("Row %(row)s: set the 13-digit Moadian product ID of %(product)s.", **v),
			"unit": lambda v: self.env._("Row %(row)s: set the Moadian unit code of the unit %(unit)s.", **v),
			"total": lambda v: self.env._("The computed total %(computed)s differs from the invoice total %(total)s; check the taxes that are not VAT.", **v),
			"original": lambda v: self.env._("The invoice this credit note reverses has no tax number yet."),
		}
		return [words[code](values) for code, values in problems]

	def _veron_moadian_values(self):
		self.ensure_one()
		lines = []
		for row, line in enumerate(self.invoice_line_ids.filtered(lambda l: l.display_type == "product"), 1):
			rate = sum(line.tax_ids.filtered(lambda t: t.amount_type == "percent").mapped("amount"))
			lines.append({
				"row": row,
				"name": line.product_id.display_name or line.name,
				"quantity": line.quantity,
				"price_unit": line.price_unit,
				"discount": line.discount,
				"subtotal": line.price_subtotal,
				"total": line.price_total,
				"vat_rate": rate,
				"sstid": line.product_id.product_tmpl_id.veron_sstid,
				"unit": line.product_uom_id.veron_moadian_unit,
				"unit_name": line.product_uom_id.name,
			})
		invoice = {
			"currency": self.currency_id.name,
			"invoice_date": self.invoice_date or self.date,
			"create_date": self.create_date,
			"amount_total": self.amount_total,
			"amount_residual": self.amount_residual,
			"is_return": self.move_type == "out_refund",
			"lines": lines,
		}
		buyer = self.commercial_partner_id
		seller = {"economic_code": self.company_id.vat}
		buyer = {"national_id": buyer.veron_national_id, "economic_code": buyer.vat, "zip": buyer.zip}
		settings = {
			"memory_id": (self.company_id.veron_moadian_memory_id or "").strip().upper(),
			"tax_id": self.veron_tax_id,
			"serial": self.veron_moadian_serial,
		}
		if self.move_type == "out_refund":
			settings["original_tax_id"] = self.reversed_entry_id.veron_tax_id
		return invoice, seller, buyer, settings

	def action_veron_moadian_prepare(self):
		"""The tax number (once) and the Moadian invoice; nothing is sent"""
		for move in self:
			if move.move_type not in ("out_invoice", "out_refund") or move.state != "posted":
				raise UserError(_("Only a posted customer invoice or credit note goes to Moadian."))
			if move.veron_moadian_state in ("sent", "accepted"):
				raise UserError(_("%s is already sent to Moadian.", move.name))
			payload, problems = moadian_payload.build(*move._veron_moadian_values())
			if not problems and not move.veron_tax_id:
				memory_id = move.company_id.veron_moadian_memory_id.strip().upper()
				serial = int(self.env["ir.sequence"].with_company(move.company_id).next_by_code("veron.moadian.serial"))
				try:
					tax_id = generate_tax_id(memory_id, move.invoice_date or move.date, serial)
				except ValueError as error:
					raise UserError(_("The tax memory ID is 6 letters or digits.")) from error
				move.write({"veron_tax_id": tax_id, "veron_moadian_serial": serial})
				payload, problems = moadian_payload.build(*move._veron_moadian_values())
			messages = move._veron_moadian_messages(problems)
			move.write({
				"veron_moadian_payload": json.dumps(payload, ensure_ascii=False, indent=1),
				"veron_moadian_problems": "\n".join(messages) or False,
				"veron_moadian_state": "problems" if messages else "prepared",
			})
		return True

	def _veron_moadian_client(self):
		company = self.company_id.sudo()
		if not company.veron_moadian_active:
			raise UserError(_("Sending to Moadian is off. Turn it on in Accounting settings, Moadian."))
		if not (company.veron_moadian_private_key and company.veron_moadian_certificate):
			raise UserError(_("Set the private key and the certificate of Moadian in Accounting settings."))
		return Client(company.veron_moadian_url, company.veron_moadian_memory_id.strip().upper(),
			company.veron_moadian_private_key, company.veron_moadian_certificate)

	def action_veron_moadian_send(self):
		"""Send prepared invoices, each on a person's request"""
		if not self.env.user.has_group("account.group_account_manager"):
			raise UserError(_("Only an accounting manager sends invoices to Moadian."))
		for move in self:
			move.action_veron_moadian_prepare()
			if move.veron_moadian_state != "prepared":
				raise UserError(_("Fix the problems of %s first:\n%s", move.name, move.veron_moadian_problems))
			try:
				result = move._veron_moadian_client().send(json.loads(move.veron_moadian_payload))
			except (MoadianError, OSError) as error:
				_logger.warning("Moadian: %s was not sent: %s", move.name, error)
				raise UserError(_("Moadian did not take %(invoice)s: %(error)s", invoice=move.name, error=error)) from error
			move.write({
				"veron_moadian_state": "sent",
				"veron_moadian_reference": result.get("referenceNumber"),
				"veron_moadian_uid": result.get("uid"),
				"veron_moadian_sent": fields.Datetime.now(),
			})
			move.message_post(body=_("Sent to Moadian; reference %s. The result comes with the next inquiry.", result.get("referenceNumber")))
		return True

	def action_veron_moadian_inquire(self):
		sent = self.filtered(lambda m: m.veron_moadian_state == "sent" and m.veron_moadian_reference)
		for company, moves in sent.grouped("company_id").items():
			try:
				results = moves[:1]._veron_moadian_client().inquire(moves.mapped("veron_moadian_reference"))
			except (MoadianError, OSError, UserError) as error:
				_logger.warning("Moadian inquiry of %s failed: %s", company.name, error)
				if len(self) == 1:
					raise UserError(_("The inquiry did not go through: %s", error)) from error
				continue
			by_reference = {item.get("referenceNumber"): item for item in results if isinstance(item, dict)}
			for move in moves:
				item = by_reference.get(move.veron_moadian_reference)
				status = (item or {}).get("status")
				if status == "SUCCESS":
					move.write({"veron_moadian_state": "accepted", "veron_moadian_result": json.dumps(item.get("data"), ensure_ascii=False)})
					move.message_post(body=_("Moadian accepted the invoice."))
				elif status == "FAILED":
					data = item.get("data") or {}
					errors = "\n".join(f"{e.get('code')}: {e.get('message')}" for e in data.get("error") or [])
					move.write({"veron_moadian_state": "rejected", "veron_moadian_result": errors or json.dumps(data, ensure_ascii=False)})
					move.message_post(body=_("Moadian rejected the invoice: %s", errors))
		return True

	@api.model
	def _cron_veron_moadian_inquire(self):
		self.search([("veron_moadian_state", "=", "sent")], limit=200).action_veron_moadian_inquire()

	def button_draft(self):
		if self.filtered(lambda m: m.veron_moadian_state in ("sent", "accepted")):
			raise UserError(_("The invoice is sent to Moadian. Correct it with a credit note instead."))
		return super().button_draft()

	def action_veron_moadian_retry(self):
		"""A rejected invoice is prepared again, with the same tax number, after its fixes"""
		self.filtered(lambda m: m.veron_moadian_state == "rejected").write({"veron_moadian_state": "problems"})
		return self.action_veron_moadian_prepare()
