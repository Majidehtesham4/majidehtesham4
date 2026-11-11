"""The two choosers of the agent's form, as in Odoo's AI app: «Add Sources» (a file, a link, a page of the
Knowledge app, a file of the company) and «When should your agent be triggered?»"""

import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.ai_trigger import KINDS as TRIGGER_KINDS

PAGE_MODELS = [("document.page", "Knowledge Page"), ("knowledge.article", "Knowledge Article")]


class AiKnowledgeAdd(models.TransientModel):
	_name = "veron.ai.knowledge.add"
	_description = "Add Knowledge Sources to an Agent"

	agent_id = fields.Many2one("veron.ai.agent", required=True, ondelete="cascade")
	step = fields.Selection([("choose", "Choose"), ("file", "Upload a File"), ("link", "Add a Link"),
		("page", "Add From Knowledge"), ("document", "Add From Documents")], default="choose", required=True)
	file = fields.Binary()
	filename = fields.Char()
	links = fields.Text(help="One link a line")
	page_ref = fields.Reference(selection="_page_models", string="Page")
	attachment_ids = fields.Many2many("ir.attachment", string="Files", domain="[('res_model', '!=', 'veron.ai.knowledge')]")
	has_pages = fields.Boolean(compute="_compute_has_pages")

	@api.model
	def _page_models(self):
		return [(model, name) for model, name in PAGE_MODELS if model in self.env]

	def _compute_has_pages(self):
		for wizard in self:
			wizard.has_pages = bool(self._page_models())

	def _again(self):
		return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
			"target": "new", "name": _("Add Sources")}

	def action_choose_file(self):
		self.step = "file"
		return self._again()

	def action_choose_link(self):
		self.step = "link"
		return self._again()

	def action_choose_page(self):
		if not self.has_pages:
			raise UserError(_("The Knowledge app (document_page) is not installed."))
		self.step = "page"
		return self._again()

	def action_choose_document(self):
		self.step = "document"
		return self._again()

	def action_back(self):
		self.step = "choose"
		return self._again()

	def action_save(self):
		self.ensure_one()
		values = []
		agent = [(4, self.agent_id.id)]
		if self.step == "file":
			if not self.file:
				raise UserError(_("Choose a file."))
			values.append({"name": self.filename or _("File"), "kind": "file", "file": self.file, "filename": self.filename,
				"agent_ids": agent})
		elif self.step == "link":
			links = [line.strip() for line in (self.links or "").splitlines() if line.strip()]
			if not links:
				raise UserError(_("Paste a link."))
			values += [{"name": link[:120], "kind": "link", "url": link, "agent_ids": agent} for link in links[:20]]
		elif self.step == "page":
			if not self.page_ref:
				raise UserError(_("Choose a page."))
			values.append({"name": self.page_ref.display_name, "kind": "page",
				"page_ref": f"{self.page_ref._name},{self.page_ref.id}", "agent_ids": agent})
		elif self.step == "document":
			if not self.attachment_ids:
				raise UserError(_("Choose a file."))
			values += [{"name": a.name, "kind": "document", "page_ref": f"ir.attachment,{a.id}", "agent_ids": agent}
				for a in self.attachment_ids]
		self.env["veron.ai.knowledge"].create(values)
		return {"type": "ir.actions.act_window_close"}


class AiTriggerAdd(models.TransientModel):
	_name = "veron.ai.trigger.add"
	_description = "Add a Trigger to an Agent"

	agent_id = fields.Many2one("veron.ai.agent", required=True, ondelete="cascade")
	kind = fields.Selection(TRIGGER_KINDS)
	model_id = fields.Many2one("ir.model", "Records", domain=[("transient", "=", False), ("model", "not like", "veron.ai.%")])
	date_field_id = fields.Many2one("ir.model.fields", "Date Field",
		domain="[('model_id', '=', model_id), ('ttype', 'in', ('date', 'datetime'))]")
	delay = fields.Integer()
	delay_mode = fields.Selection([("after", "After"), ("before", "Before")], default="after")
	delay_unit = fields.Selection([("minutes", "Minutes"), ("hour", "Hours"), ("day", "Days"), ("month", "Months")],
		default="day")
	field_ids = fields.Many2many("ir.model.fields", string="When These Fields Change",
		domain="[('model_id', '=', model_id), ('store', '=', True)]")
	filter_domain = fields.Char("Only the Records", default="[]")
	interval = fields.Selection([("daily", "Every Day"), ("weekly", "Every Week"), ("monthly", "Every Month")],
		default="daily")
	hour = fields.Float("At", default=8.0)
	input_text = fields.Text("Request", help="What the agent is asked each time")

	def _again(self):
		return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
			"target": "new", "name": _("When Should Your Agent Be Triggered?")}

	def _choose(self, kind):
		self.kind = kind
		return self._again()

	def action_schedule(self):
		return self._choose("schedule")

	def action_date(self):
		return self._choose("date")

	def action_create(self):
		return self._choose("create")

	def action_update(self):
		return self._choose("update")

	def action_back(self):
		self.kind = False
		return self._again()

	def action_help(self):
		"""The assistant helps to choose"""
		assistant = self.env.ref("veron_ai_agent.agent_assistant", raise_if_not_found=False)
		if not assistant or not assistant.enabled:
			assistant = self.env["veron.ai.agent"].search([("enabled", "=", True), ("all_users", "=", True)], limit=1)
		if not assistant:
			raise UserError(_("No assistant is working."))
		return assistant.action_open_chat()

	def action_save(self):
		self.ensure_one()
		if not self.input_text:
			raise UserError(_("Write what the agent is asked each time."))
		trigger = self.env["veron.ai.trigger"].create({
			"agent_id": self.agent_id.id, "kind": self.kind, "model_id": self.model_id.id,
			"date_field_id": self.date_field_id.id, "delay": self.delay, "delay_mode": self.delay_mode,
			"delay_unit": self.delay_unit, "field_ids": [(6, 0, self.field_ids.ids)],
			"filter_domain": self.filter_domain or "[]", "input_text": self.input_text,
		})
		if trigger.schedule_id:
			trigger.schedule_id.sudo().write({"interval": self.interval, "hour": self.hour})
		return {"type": "ir.actions.act_window_close"}
