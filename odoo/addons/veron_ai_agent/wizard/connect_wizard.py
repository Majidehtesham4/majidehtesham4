from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services import catalog, providers


class ConnectWizard(models.TransientModel):
	"""Connecting an AI service in one step: the keys are pasted, the service is found from them, each key is
	checked, and the providers of that service are filled with the keys that work and made active"""

	_name = "veron.ai.connect.wizard"
	_inherit = ["veron.ai.guide.mixin"]
	_description = "Connect AI"

	service = fields.Selection([("auto", "Find It From the Key"), ("groq", "Groq"), ("openai", "ChatGPT (OpenAI)"),
		("openrouter", "OpenRouter"), ("anthropic", "Claude (Anthropic)")], default="auto", required=True)
	keys = fields.Text(help="One key a line, or separated by commas; they are not shown again once connected")
	use_stt = fields.Boolean("Also for Voice Messages", default=True)
	use_vision = fields.Boolean("Also for Reading Photos", default=False,
		help="Photos are first read by the built-in OCR without any AI; turn this on to have the AI read them instead")
	result = fields.Html(readonly=True, sanitize=False)
	done = fields.Boolean()

	@api.model
	def _check_key(self, code, key):
		"""'ok', 'busy' (at its limit now), 'refused' or 'unknown' (the service could not be reached)"""
		spec = catalog.SERVICES[code]
		_xmlid, _kind, adapter, model = spec["providers"][0]
		cls = providers.ADAPTERS.get(adapter)
		if not cls:
			return "missing"
		try:
			cls({"api_key": key, "api_keys": [key], "base_url": spec["base"], "model": model, "timeout": 25,
				"max_tokens": 100}).check()
		except providers.ProviderError as error:
			if error.kind == "rate_limit":
				return "busy"
			if error.kind == "key":
				return "refused"
			if error.kind == "config":
				return "ok"  # The key was accepted; only the model name differs
			return "unknown"
		return "ok"

	def _fill(self, code, keys, checked=True):
		spec = catalog.SERVICES[code]
		Provider = self.env["veron.ai.provider"].sudo().with_context(active_test=False)
		filled = []
		for xmlid, kind, adapter, model in spec["providers"]:
			if kind == "stt" and not self.use_stt or kind == "vision" and not self.use_vision:
				continue
			if adapter not in providers.ADAPTERS:
				continue
			provider = self.env.ref(xmlid, raise_if_not_found=False)
			values = {"api_key": keys[0], "extra_keys": " ".join(keys[1:]) or False, "active": True, "is_default": True,
				"state": "ok" if checked else "unknown", "last_error": False,
				"last_check": fields.Datetime.now() if checked else False}
			if provider:
				provider = provider.sudo()
				if not provider.base_url and spec["base"]:
					values["base_url"] = spec["base"]
				provider.write(values)
			else:
				provider = Provider.create({"name": f"{spec['label']} ({kind})", "kind": kind, "adapter": adapter,
					"model_name": model, "base_url": spec["base"] or False, **values})
			# The service connected now is the one used for this kind
			Provider.search([("kind", "=", kind), ("is_default", "=", True), ("id", "!=", provider.id)]).write(
				{"is_default": False})
			filled.append(provider)
		return filled

	def action_connect(self):
		self.ensure_one()
		keys = catalog.split_keys(self.keys)
		if not keys:
			raise UserError(_("Paste at least one key."))
		groups = {}
		for key in keys:
			code = self.service if self.service != "auto" else catalog.detect(key)
			if not code:
				raise UserError(_("The service of the key %s is not known; choose the service above.", catalog.masked(key)))
			groups.setdefault(code, []).append(key)
		labels = {"ok": _("works"), "busy": _("works, at its limit now"), "refused": _("refused: wrong or expired"),
			"unknown": _("not checked: the service could not be reached"), "missing": _("the module of this service is not installed")}
		parts = []
		for code, group in groups.items():
			spec = catalog.SERVICES[code]
			states = [(key, self._check_key(code, key)) for key in group]
			usable = [key for key, state in states if state in ("ok", "busy", "unknown")]
			rows = Markup("").join(Markup("<li><code>%s</code>: %s</li>") % (catalog.masked(key), labels[state])
				for key, state in states)
			checked = any(state in ("ok", "busy") for _key, state in states)
			if usable and checked:
				filled = self._fill(code, usable)
				summary = _("%(service)s is connected with %(count)s key(s): %(providers)s.", service=spec["label"],
					count=len(usable), providers="، ".join(provider.name for provider in filled))
				parts.append(Markup("<div class='alert alert-success'><b>%s</b><ul>%s</ul></div>") % (summary, rows))
			elif usable:
				# The service did not answer at all: the keys are kept, but nothing says they work yet
				filled = self._fill(code, usable, checked=False)
				summary = _("%(service)s could not be reached from the server, so the keys were saved without being "
					"checked. Check the internet of the server, then press Check on %(provider)s.", service=spec["label"],
					provider=filled[0].name if filled else spec["label"])
				parts.append(Markup("<div class='alert alert-warning'><b>%s</b><ul>%s</ul></div>") % (summary, rows))
			else:
				summary = _("%s was not connected: no key works.", spec["label"])
				parts.append(Markup("<div class='alert alert-danger'><b>%s</b><ul>%s</ul><p>%s</p></div>") % (
					summary, rows, _("New keys are made at %s", spec["keys_at"])))
		self.write({"keys": False, "result": Markup("").join(parts), "done": True})
		return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
			"target": "new", "name": _("Connect AI")}
