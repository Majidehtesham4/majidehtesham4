import json
import logging
import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.translate import LazyGettext

from ..services import providers, redact

_logger = logging.getLogger(__name__)


class AiProvider(models.Model):
	_name = "veron.ai.provider"
	_description = "AI Provider"
	_order = "kind, sequence, id"

	name = fields.Char(required=True)
	kind = fields.Selection(providers.KINDS, required=True, default="llm")
	adapter = fields.Selection(selection="_adapter_selection", required=True)
	sequence = fields.Integer(default=10)
	active = fields.Boolean(default=True)
	is_default = fields.Boolean("Default of Its Kind", help="Used when an agent names no provider of this kind")
	company_id = fields.Many2one("res.company", help="Empty: for every company")
	base_url = fields.Char("Address", help="The address of the service; empty for the provider's own")
	model_name = fields.Char("Model", help="The model of the service, e.g. claude-opus-5-5 or whisper-1")
	api_key = fields.Char("Key", groups="base.group_system", copy=False,
		help="Kept in the database, readable by administrators only and never written to logs")
	api_key_env = fields.Char("Key from Environment Variable", groups="base.group_system",
		help="The name of a server environment variable holding the key, instead of keeping it in the database")
	extra_keys = fields.Char("Other Keys", groups="base.group_system", copy=False,
		help="More keys of the same service, separated by commas or spaces: each call starts from the next key, and a key "
			"at its limit or refused is replaced by the next one")
	key_set = fields.Boolean("Key Set", compute="_compute_key_set")
	key_count = fields.Integer("Keys", compute="_compute_key_set")
	key_cursor = fields.Integer(readonly=True, copy=False)
	language = fields.Char(default="fa", help="The language of speech and text, e.g. fa")
	timeout = fields.Integer("Timeout (seconds)", default=60)
	max_tokens = fields.Integer("Most Tokens of an Answer", default=8000)
	effort = fields.Selection([("low", "Low"), ("medium", "Medium"), ("high", "High"), ("xhigh", "Very High")],
		default="high", help="How much the model reasons before answering; more is slower and costs more")
	allowed_domains = fields.Text("Allowed Sites", help="One site a line; the web search reads only these. Empty: any site")
	options = fields.Text("Other Options (JSON)", help='e.g. {"voice": "alloy"}')
	state = fields.Selection([("unknown", "Not Checked"), ("ok", "Working"), ("error", "Error")], default="unknown",
		readonly=True, copy=False)
	last_check = fields.Datetime(readonly=True, copy=False)
	last_error = fields.Char(readonly=True, copy=False)
	note = fields.Html("Notes", sanitize=True)

	@api.model
	def _adapter_selection(self):
		names = {"http_openai": _("HTTP (OpenAI-compatible format)"), "searxng": _("SearXNG (self-hosted search)"),
			"tesseract": _("Tesseract OCR on the server"), "clamd": _("ClamAV antivirus")}
		return [(code, names.get(code, getattr(cls, "label", code))) for code, cls in sorted(providers.ADAPTERS.items())]

	@api.depends("adapter")
	def _compute_key_set(self):
		for provider in self:
			count = len(provider.sudo()._keys())
			provider.key_set = bool(count)
			provider.key_count = count

	def _keys(self):
		"""Every key of the provider: the key, the other keys, and those of the environment variable (one a line or
		separated by commas or spaces); never logged"""
		self.ensure_one()
		sudo = self.sudo()
		values = [sudo.api_key or "", sudo.extra_keys or "", (sudo.api_key_env and os.environ.get(sudo.api_key_env)) or ""]
		keys = []
		for value in values:
			for key in value.replace(",", " ").split():
				if key not in keys:
					keys.append(key)
		return keys

	@api.constrains("adapter", "kind")
	def _check_adapter(self):
		for provider in self:
			cls = providers.ADAPTERS.get(provider.adapter)
			if cls and provider.kind not in cls.kinds:
				raise ValidationError(_("This adapter does not serve that kind of provider."))

	@api.constrains("options")
	def _check_options(self):
		for provider in self:
			if provider.options:
				try:
					value = json.loads(provider.options)
				except ValueError as error:
					raise ValidationError(_("The other options are not valid JSON.")) from error
				if not isinstance(value, dict):
					raise ValidationError(_("The other options are a JSON object."))

	def _config(self):
		"""The settings the adapter reads, with the key; never logged"""
		self.ensure_one()
		sudo = self.sudo()
		keys = self._keys()
		if len(keys) > 1:
			# Each call starts from the next key, so the keys share the load
			self.env.cr.execute("UPDATE veron_ai_provider SET key_cursor = COALESCE(key_cursor, 0) + 1 WHERE id = %s "
				"RETURNING key_cursor - 1", (self.id,))
			start = self.env.cr.fetchone()[0] % len(keys)
			keys = keys[start:] + keys[:start]
			self.invalidate_recordset(["key_cursor"])
		config = json.loads(sudo.options or "{}")
		config.update({
			"api_key": keys[0] if keys else "", "api_keys": keys, "base_url": sudo.base_url or "", "model": sudo.model_name or "", "language": sudo.language or "fa",
			"timeout": sudo.timeout or 60, "max_tokens": sudo.max_tokens or 8000, "effort": sudo.effort or "high",
			"allowed_domains": [d.strip() for d in (sudo.allowed_domains or "").splitlines() if d.strip()],
		})
		return config

	def _adapter(self):
		self.ensure_one()
		cls = providers.ADAPTERS.get(self.adapter)
		if not cls:
			raise providers.ProviderError(_("The adapter %s is not installed.", self.adapter), kind="config")
		return cls(self._config())

	@api.model
	def _get(self, kind, provider=None, company=None):
		"""The provider to use: the one given, else the default of its kind for the company; None when there is none"""
		if provider:
			return provider
		company = company or self.env.company
		domain = [("kind", "=", kind), ("active", "=", True), ("company_id", "in", [False, company.id])]
		found = self.sudo().search(domain, order="is_default desc, company_id, sequence, id", limit=1)
		return found.with_env(self.env) if found else None

	def action_check(self):
		for provider in self:
			try:
				message = provider._adapter().check()
				if isinstance(message, LazyGettext):
					message = self.env._(message)
				provider.sudo().write({"state": "ok", "last_check": fields.Datetime.now(), "last_error": False})
			except providers.ProviderError as error:
				provider.sudo().write({"state": "error", "last_check": fields.Datetime.now(), "last_error": error.text(self.env)})
				raise UserError(error.text(self.env)) from error
			except Exception as error:
				_logger.warning("AI provider check failed: %s", redact.text(error))
				provider.sudo().write({"state": "error", "last_check": fields.Datetime.now(),
					"last_error": redact.text(error, 300)})
				raise UserError(_("The check failed: %s", redact.text(error, 300))) from error
		return {"type": "ir.actions.client", "tag": "display_notification",
			"params": {"type": "success", "message": message, "sticky": False}}

	def _mark(self, error=None):
		"""Records the last result of a real call, without the key"""
		values = {"last_check": fields.Datetime.now(), "state": "error" if error else "ok",
			"last_error": providers.message(error, self.env, 300) if error else False}
		self.sudo().write(values)
