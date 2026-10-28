import json

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class AiConversation(models.Model):
	_name = "veron.ai.conversation"
	_description = "Agent Conversation"
	_order = "write_date desc"

	name = fields.Char(compute="_compute_name", store=True)
	agent_id = fields.Many2one("veron.ai.agent", required=True, ondelete="cascade", index=True)
	user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, index=True)
	company_id = fields.Many2one(related="agent_id.company_id", store=True)
	message_ids = fields.One2many("veron.ai.message", "conversation_id")

	@api.depends("agent_id", "create_date")
	def _compute_name(self):
		for conversation in self:
			conversation.name = f"{conversation.agent_id.name} - {conversation.create_date or ''}"[:120]

	@api.model
	def _for(self, agent):
		if not agent._may_use(self.env.user):
			raise AccessError(_("You may not use %s.", agent.name))
		conversation = self.search([("agent_id", "=", agent.id), ("user_id", "=", self.env.uid)], order="id desc", limit=1)
		return conversation or self.create({"agent_id": agent.id})

	def _post(self, text, sources, engine=None, page=None):
		"""A person's message: its run happens now, with the person's own rights"""
		self.ensure_one()
		if self.user_id != self.env.user:
			raise AccessError(_("This is someone else's conversation."))
		unconfirmed = sources.filtered(lambda s: s.kind == "audio" and not s.transcript_confirmed)
		if unconfirmed:
			raise UserError(_("Check the text of the voice message and send it again."))
		if not (text or "").strip() and not sources:
			raise UserError(_("Write a message, or add a photo, a PDF or a voice message."))
		Message = self.env["veron.ai.message"]
		shown = text
		if (text or "").startswith("#intent:"):
			# A meaning the person picked from the offered buttons: kept in the conversation in words
			intent = self.env["veron.ai.intent"].search([("code", "=", text[8:].strip())], limit=1)
			shown = intent.name or text
		Message.create({"conversation_id": self.id, "role": "user", "body": shown, "source_ids": [(6, 0, sources.ids)]})
		Run = self.env["veron.ai.run"].with_context(veron_ai_engine=engine) if engine in ("ai", "internal") else \
			self.env["veron.ai.run"]
		carried = self._recent_files() if not sources else self.env["veron.ai.source"]
		run = Run._start(self.agent_id, self.env.user, "chat", text=text, sources=sources or carried, conversation=self,
			page=page, carried=bool(carried))
		body = run.output_html or Markup("")
		if not body and run.state in ("failed", "queued"):
			# The person sees why nothing came back, not an empty answer
			reason = run.sudo().error or _("an unknown error")
			body = Markup("<p>%s</p>") % (_("It could not be done: %s", reason) if run.state == "failed" else
				_("The service did not answer (%s); it is tried again by itself in a few minutes.", reason))
		reply = Message.create({"conversation_id": self.id, "role": "agent", "body_html": body,
			"run_id": run.id, "options": json.loads(run.sudo().options_json or "[]")})
		return reply

	def _recent_files(self, within=8):
		"""The files of the person's last message that had any, among the last messages: «this invoice» in a later
		message is that file"""
		for message in reversed(self.message_ids[-within:]):
			if message.role == "user" and message.source_ids:
				return message.source_ids.filtered(lambda s: s.kind != "audio")
		return self.env["veron.ai.source"]


class AiMessage(models.Model):
	_name = "veron.ai.message"
	_description = "Agent Conversation Message"
	_order = "id"

	conversation_id = fields.Many2one("veron.ai.conversation", required=True, ondelete="cascade", index=True)
	role = fields.Selection([("user", "Person"), ("agent", "Agent")], required=True)
	body = fields.Text()
	body_html = fields.Html(sanitize=True)
	source_ids = fields.Many2many("veron.ai.source", string="Files")
	run_id = fields.Many2one("veron.ai.run", ondelete="set null")
	run_state = fields.Selection(related="run_id.state")
	options = fields.Json(help="Choices offered to the person, as buttons")


class AiAgentChat(models.Model):
	_inherit = "veron.ai.agent"

	def _has_ai(self):
		"""Whether a person may choose the AI for this agent: a working language model, and the agent not built-in only"""
		self.ensure_one()
		return self.engine != "internal" and bool(self.env["veron.ai.provider"]._get("llm", self.llm_provider_id,
			self.company_id))


class AiChatApi(models.Model):
	"""What the chat page calls; each method checks who calls it"""

	_inherit = "veron.ai.conversation"

	@api.model
	def veron_chat_agents(self):
		agents = self.env["veron.ai.agent"].search([("enabled", "=", True), ("trigger_manual", "=", True)])
		return [{"id": a.id, "name": a.name, "role": a.template_id.name or "", "description": a.description or a.goal or "",
			"level": dict(a._fields["authority_level"]._description_selection(self.env)).get(a.authority_level),
			"ai": a._has_ai(), "engine": a.engine}
			for a in agents if a._may_use(self.env.user)]

	@api.model
	def veron_chat_open(self, agent_id):
		agent = self.env["veron.ai.agent"].browse(int(agent_id)).exists()
		if not agent:
			raise UserError(_("No such agent."))
		conversation = self._for(agent)
		return {"conversation_id": conversation.id, "messages": [m._chat_dict() for m in conversation.message_ids[-60:]]}

	@api.model
	def _assistant_shown(self):
		"""Whether the chat box is shown on every page: an assistant everyone may use is working, for a person of the
		AI user group"""
		user = self.env.user
		if not user._is_internal() or not user.has_group("veron_ai_agent.group_ai_user"):
			return False
		agent = self.env["veron.ai.agent"].sudo().search([("enabled", "=", True), ("all_users", "=", True)], limit=1)
		return bool(agent and agent.with_env(self.env)._may_use(user))

	@api.model
	def veron_chat_assistant(self):
		"""The assistant of the chat box on every page: the first working agent everyone may use"""
		agent = self.env["veron.ai.agent"].search([("enabled", "=", True), ("all_users", "=", True)], limit=1)
		if not agent or not agent._may_use(self.env.user):
			return False
		result = self.veron_chat_open(agent.id)
		result.update({"agent_id": agent.id, "name": agent.name, "ai": agent._has_ai(), "engine": agent.engine})
		return result

	@api.model
	def veron_chat_send(self, conversation_id, text, source_ids=None, transcripts=None, engine=None, page=None):
		conversation = self.browse(int(conversation_id)).exists()
		if not conversation or conversation.user_id != self.env.user:
			raise AccessError(_("This is someone else's conversation."))
		sources = self.env["veron.ai.source"].browse([int(i) for i in source_ids or []]).exists()
		if sources.filtered(lambda s: s.create_uid != self.env.user):
			raise AccessError(_("Only your own files are sent."))
		for source_id, transcript in (transcripts or {}).items():
			source = sources.filtered(lambda s: s.id == int(source_id))
			if source:
				source._confirm_transcript(transcript)
		before = conversation.message_ids
		page = self._page(page)
		conversation._post(text, sources, engine=engine, page=page)
		return [m._chat_dict() for m in conversation.message_ids - before]

	@api.model
	def veron_chat_new(self, agent_id):
		"""A new conversation with the agent: what was said before is no longer remembered"""
		agent = self.env["veron.ai.agent"].browse(int(agent_id)).exists()
		if not agent or not agent._may_use(self.env.user):
			raise AccessError(_("You may not use this agent."))
		conversation = self.create({"agent_id": agent.id})
		return {"conversation_id": conversation.id, "messages": []}

	@api.model
	def veron_chat_decide(self, conversation_id, approval_id, approve):
		"""An approval decided from the chat, with the rights of the person deciding; its result is the agent's reply"""
		conversation = self.browse(int(conversation_id)).exists()
		if not conversation or conversation.user_id != self.env.user:
			raise AccessError(_("This is someone else's conversation."))
		approval = self.env["veron.ai.approval"].browse(int(approval_id)).exists()
		if not approval or approval.run_id.sudo().conversation_id != conversation:
			raise AccessError(_("This approval is not of this conversation."))
		if approve:
			approval.action_approve()
		else:
			approval.action_reject()
		from ..services import render

		if approval.state == "executed":
			body = Markup("<p>%s</p>") % _("Done: %s", approval.summary) + render.answer(
				approval.tool_code, json.loads(approval.result_json or "{}"))
		elif approval.state == "failed":
			body = Markup("<p>%s</p>") % _("Approved, but it could not be done: %s",
				json.loads(approval.result_json or "{}").get("error", ""))
		else:
			body = Markup("<p>%s</p>") % _("Rejected: %s. Nothing was changed.", approval.summary)
		message = self.env["veron.ai.message"].create({"conversation_id": conversation.id, "role": "agent",
			"body_html": body, "run_id": approval.run_id.id})
		return [message._chat_dict()]


OPERATORS = {"=", "!=", ">", "<", ">=", "<=", "ilike", "not ilike", "in", "not in"}


def _scalar(value):
	return value is None or isinstance(value, (bool, int, float)) or isinstance(value, str) and len(value) <= 200


class AiChatPage(models.Model):
	_inherit = "veron.ai.conversation"

	@api.model
	def _page(self, page):
		"""The page the person has open: its model, record, title and the simple conditions of its list. Anything
		else the browser sends is dropped; the tools check the model and the fields again."""
		page = page or {}
		model = str(page.get("model") or "")[:64]
		if not model or model not in self.env:
			return None
		filters = []
		for item in page.get("domain") or []:
			if isinstance(item, (list, tuple)) and len(item) == 3 and isinstance(item[0], str) and item[1] in OPERATORS:
				value = item[2]
				if _scalar(value) or isinstance(value, list) and len(value) <= 50 and all(_scalar(v) for v in value):
					filters.append([item[0][:64], item[1], value])
			elif item not in ("&",):
				# An «or» or a «not» makes the list's conditions more than simple ones: none are used
				filters = []
				break
		return {"model": model, "res_id": int(page.get("res_id") or 0), "title": str(page.get("title") or "")[:80],
			"filters": filters[:10]}


class AiMessageChat(models.Model):
	_inherit = "veron.ai.message"

	def _chat_dict(self):
		self.ensure_one()
		run = self.run_id
		pending = run.approval_ids.filtered(lambda a: a.state == "pending") if run else self.env["veron.ai.approval"]
		return {
			"id": self.id, "role": self.role, "body": self.body or "", "body_html": str(self.body_html or ""),
			"sources": [{"id": s.id, "name": s.name, "kind": s.kind, "transcript": s.transcript or ""} for s in self.source_ids],
			"run": {"id": run.id, "name": run.name, "state": run.state,
				"state_label": dict(run._fields["state"]._description_selection(self.env)).get(run.state)} if run else False,
			"pending": [{"id": a.id, "name": a.name, "summary": a.summary or "", "kind": a.kind,
				"can_decide": a.with_env(self.env).can_decide} for a in pending],
			"options": self.options or [],
			"engine": run.engine_used if run else False,
			"date": str(self.create_date),
		}
