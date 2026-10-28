"""The library of the built-in assistant: what a person may ask, in their own words, and what it does. An
intent runs one tool with fixed arguments, a period and the records it asks for (a customer, a product,
a file...), or answers with a fixed text. A manager adds phrases and intents; a person who picks the right
meaning when the assistant is unsure teaches it that phrase."""

import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..services import nlu, registry

SECTIONS = [
	("general", "General"),
	("sales", "Sales and Customers"),
	("purchase", "Purchases and Vendors"),
	("accounting", "Accounting"),
	("stock", "Inventory"),
	("hr", "Employees"),
	("payroll", "Payroll"),
	("petty_cash", "Petty Cash"),
	("website", "Website"),
	("files", "Files"),
]
PERIODS = [("none", "No Period"), ("days", "Number of Days"), ("range", "From and To Dates")]


class AiIntent(models.Model):
	_name = "veron.ai.intent"
	_description = "Built-in Assistant Command"
	_order = "section, sequence, id"

	name = fields.Char(required=True, translate=True)
	code = fields.Char(required=True, index=True)
	sequence = fields.Integer(default=10)
	active = fields.Boolean(default=True)
	section = fields.Selection(SECTIONS, required=True, default="general")
	phrases = fields.Text(help="Ways people ask this, one a line, e.g. «فروش دیروز چقدر بود»")
	phrase_ids = fields.One2many("veron.ai.intent.phrase", "intent_id", "Learned Phrases")
	tool_code = fields.Char("Tool", help="The tool it runs; empty for an intent that answers with its text")
	args = fields.Text("Fixed Arguments (JSON)", default="{}")
	period = fields.Selection(PERIODS, required=True, default="none",
		help="How a period said in the request is given to the tool")
	default_days = fields.Integer("Days When None Is Said", default=0)
	slots = fields.Text("Asked Records (JSON)", default="[]",
		help='Records the request names, e.g. [{"arg": "partner_id", "model": "res.partner", "question": "کدام مشتری؟", '
			'"required": true}]; a file is {"arg": "source_id", "file": true}')
	answer = fields.Html("Answer", sanitize=True, help="The answer of an intent without a tool")
	page_models = fields.Char("On the Pages Of", help="Models whose pages make this intent likelier, separated by commas")
	group_ids = fields.Many2many("res.groups", string="Only For", help="Empty: everyone who may use the assistant")
	example = fields.Char(compute="_compute_example")
	use_count = fields.Integer("Used", readonly=True)

	_code_unique = models.Constraint("unique (code)", "A command code is unique.")

	@api.depends("phrases")
	def _compute_example(self):
		for intent in self:
			intent.example = (intent.phrases or "").strip().splitlines()[0] if intent.phrases else ""

	@api.constrains("args", "slots", "tool_code")
	def _check(self):
		for intent in self:
			try:
				args = json.loads(intent.args or "{}")
				slots = json.loads(intent.slots or "[]")
			except ValueError as error:
				raise ValidationError(_("The arguments and the asked records are JSON.")) from error
			if not isinstance(args, dict) or not isinstance(slots, list):
				raise ValidationError(_("The arguments are a JSON object and the asked records a JSON list."))
			if intent.tool_code and not registry.get(intent.tool_code):
				raise ValidationError(_("No tool is named %s.", intent.tool_code))

	@api.model
	def _add_phrases(self, code, phrases, rename=None):
		"""Phrases a new version of the library brings to a command that is already there; the manager's own phrases
		and changes stay"""
		intent = self.sudo().with_context(active_test=False).search([("code", "=", code)], limit=1)
		if not intent:
			return False
		lines = [line for line in (intent.phrases or "").splitlines() if line.strip()]
		known = {nlu.normalize(line) for line in lines}
		added = [phrase for phrase in phrases if nlu.normalize(phrase) not in known]
		if added:
			intent.phrases = "\n".join(lines + added)
		if rename:
			for code, _name in self.env["res.lang"].get_installed():
				named = intent.with_context(lang=code)
				if named.name == rename[0]:
					# A name the library gave, not one a manager wrote
					named.name = rename[1]
		return True

	def _slots(self):
		self.ensure_one()
		return json.loads(self.slots or "[]")

	def _args(self):
		self.ensure_one()
		return json.loads(self.args or "{}")

	def _phrase_tokens(self, user):
		"""The phrases of the intent as words: the library's, the approved learned ones, and the person's own"""
		self.ensure_one()
		texts = [line for line in (self.phrases or "").splitlines() if line.strip()] + [self.with_context(lang="en_US").name]
		texts += self.phrase_ids.filtered(lambda p: p.approved or p.user_id == user).mapped("text")
		return [nlu.tokens(text) for text in texts if text]

	def _usable(self, user):
		self.ensure_one()
		if self.group_ids and not (self.group_ids & user.all_group_ids):
			return False
		tool = registry.get(self.tool_code) if self.tool_code else None
		return not self.tool_code or (tool and tool.available(self.env))


class AiIntentPhrase(models.Model):
	"""A phrase learned for an intent: from a person who picked its meaning, or proposed from an AI run"""

	_name = "veron.ai.intent.phrase"
	_description = "Learned Phrase"
	_order = "id desc"

	intent_id = fields.Many2one("veron.ai.intent", required=True, ondelete="cascade", index=True)
	text = fields.Char(required=True)
	user_id = fields.Many2one("res.users", "Taught By", default=lambda self: self.env.user)
	source = fields.Selection([("person", "A Person's Choice"), ("ai", "An AI Run"), ("manager", "A Manager")],
		default="person", required=True)
	approved = fields.Boolean(help="Used for everyone; an unapproved phrase is used only for the person who taught it")
	count = fields.Integer(default=1)

	@api.model
	def _learn(self, intent, text, source="person"):
		text = nlu.normalize(text)[:200]
		if not text or not nlu.tokens(text):
			return self.browse()
		phrase = self.sudo().search([("intent_id", "=", intent.id), ("text", "=", text)], limit=1)
		if phrase:
			phrase.count += 1
			return phrase
		return self.sudo().create({"intent_id": intent.id, "text": text, "source": source, "user_id": self.env.uid,
			"approved": source == "manager"})

	def action_approve(self):
		self.write({"approved": True})
