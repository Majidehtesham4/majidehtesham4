from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services import files as filetools
from ..services import providers, redact

PURPOSES = [("receipt", "Receipt"), ("invoice", "Invoice"), ("cheque", "Cheque"), ("purchase_doc", "Purchase Document"),
	("product_image", "Product Photo"), ("voice", "Voice Message"), ("other", "Other")]


class AiSource(models.Model):
	"""A file given to an agent: a photo, a PDF or a voice message, with what was read from it. The file is
	checked before it is kept; the original stays linked to what was read from it."""

	_name = "veron.ai.source"
	_description = "Agent File"
	_order = "id desc"

	name = fields.Char(required=True)
	kind = fields.Selection([("image", "Photo"), ("pdf", "PDF"), ("audio", "Voice")], required=True, readonly=True)
	purpose = fields.Selection(PURPOSES, default="other")
	mimetype = fields.Char(readonly=True)
	size = fields.Integer(readonly=True)
	sha256 = fields.Char(readonly=True, index=True)
	dhash = fields.Char("Image Hash", readonly=True, index=True)
	attachment_id = fields.Many2one("ir.attachment", readonly=True, ondelete="set null")
	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
	scan = fields.Char("Check", readonly=True, help="The result of the checks of the file")
	transcript = fields.Text(help="The text of a voice message; the person checks it before it is used")
	transcript_confirmed = fields.Boolean(readonly=True)
	extracted_text = fields.Text("Text Read", readonly=True)
	extracted_json = fields.Text("Fields Read", readonly=True)
	extraction_state = fields.Selection([("none", "Not Read"), ("done", "Read"), ("failed", "Could Not Be Read"),
		("no_provider", "No Reader Set")], default="none", readonly=True)
	ai_generated = fields.Boolean("Made by AI", readonly=True,
		help="An image made by a generator: it is not a photo of the real product")
	res_model = fields.Char(readonly=True)
	res_id = fields.Integer(readonly=True)
	retention_until = fields.Date("Kept Until", readonly=True)

	@api.model
	def _settings(self):
		param = self.env["ir.config_parameter"].sudo().get_param
		return {
			"max_bytes": int(param("veron_ai_agent.max_upload_mb", 10)) * 1024 * 1024,
			"audio_days": int(param("veron_ai_agent.audio_retention_days", 30)),
			"file_days": int(param("veron_ai_agent.file_retention_days", 0)),
			"keep_audio": param("veron_ai_agent.keep_audio", "False") == "True",
		}

	@api.model
	def _from_upload(self, name, data, purpose="other", kinds=("image", "pdf", "audio"), record=None):
		"""A checked file, or UserError with the reason it is refused"""
		settings = self._settings()
		try:
			mimetype, kind = filetools.check(data, kinds, settings["max_bytes"])
		except filetools.FileRefused as error:
			raise UserError(str(error)) from error
		scan = _("Type checked from the content")
		antivirus = self.env["veron.ai.provider"]._get("antivirus")
		if antivirus:
			try:
				clean, detail = antivirus._adapter().scan(data)
			except providers.ProviderError as error:
				scan += _("; antivirus not reachable: %s", error.text(self.env))
			else:
				if not clean:
					raise UserError(_("The antivirus refused the file: %s", redact.text(detail, 200)))
				scan += _("; antivirus: clean")
		else:
			scan += _("; no antivirus set")
		days = settings["audio_days"] if kind == "audio" else settings["file_days"]
		source = self.create({
			"name": (name or _("file"))[:200], "kind": kind, "purpose": "voice" if kind == "audio" else purpose,
			"mimetype": mimetype, "size": len(data), "sha256": filetools.sha256(data),
			"dhash": filetools.image_dhash(data) if kind == "image" else False, "scan": scan,
			"res_model": record._name if record else False, "res_id": record.id if record else False,
			"retention_until": fields.Date.context_today(self) + timedelta(days=days) if days else False,
		})
		source.sudo().attachment_id = self.env["ir.attachment"].sudo().create({
			"name": source.name, "raw": data, "mimetype": mimetype, "res_model": self._name, "res_id": source.id})
		if kind == "pdf":
			source.sudo().extracted_text = filetools.pdf_text(data)[:100000] or False
		return source

	def _data(self):
		self.ensure_one()
		self.check_access("read")
		return self.sudo().attachment_id.raw or b""

	def _transcribe(self, language=None):
		"""The text of a voice message, from the speech-to-text provider; kept for the person to check"""
		self.ensure_one()
		if self.kind != "audio":
			raise UserError(_("Only a voice message is turned into text."))
		provider = self.env["veron.ai.provider"]._get("stt", company=self.company_id)
		if not provider:
			raise UserError(_("No speech-to-text provider is set. Type the message, or set one in AI Agents, Settings, "
				"Providers."))
		try:
			text = provider._adapter().transcribe(self._data(), self.mimetype, language or provider.language or "fa")
		except providers.ProviderError as error:
			provider._mark(error)
			raise UserError(error.text(self.env)) from error
		provider._mark()
		self.sudo().write({"transcript": text})
		if not self._settings()["keep_audio"]:
			# The text is kept; the voice is removed once its text exists, unless the company keeps voices
			self.sudo().retention_until = fields.Date.context_today(self)
		return text

	def _confirm_transcript(self, text):
		self.ensure_one()
		self.sudo().write({"transcript": text, "transcript_confirmed": True})

	def _extract(self, schema, instructions, provider=None):
		"""Fields read from a photo or a PDF by the vision provider, kept with the file for a person to check"""
		self.ensure_one()
		provider = provider or self.env["veron.ai.provider"]._get("vision", company=self.company_id)
		if not provider:
			self.sudo().extraction_state = "no_provider"
			return None
		try:
			result = provider._adapter().extract([(self.mimetype, self._data())], schema, instructions)
		except providers.ProviderError as error:
			provider._mark(error)
			self.sudo().extraction_state = "failed"
			raise
		provider._mark()
		self.sudo().write({"extraction_state": "done", "extracted_json": providers.as_json(result.get("fields", {})),
			"extracted_text": result.get("text") or self.extracted_text})
		return result

	def action_download(self):
		self.ensure_one()
		self.check_access("read")
		return {"type": "ir.actions.act_url", "url": f"/veron_ai/source/{self.id}", "target": "new"}

	@api.model
	def _cron_cleanup(self):
		"""Files past their keeping date are removed; what was read from them stays"""
		today = fields.Date.context_today(self)
		expired = self.sudo().search([("retention_until", "!=", False), ("retention_until", "<=", today),
			("attachment_id", "!=", False)], limit=500)
		for source in expired:
			source.attachment_id.unlink()
		return True
