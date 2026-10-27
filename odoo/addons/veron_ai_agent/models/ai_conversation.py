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
		conversation = self.search([("agent_id", "=", agent.id), ("user_id", "=", self.env.uid)], limit=1)
		return conversation or self.create({"agent_id": agent.id})

	def _post(self, text, sources):
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
		Message.create({"conversation_id": self.id, "role": "user", "body": text, "source_ids": [(6, 0, sources.ids)]})
		run = self.env["veron.ai.run"]._start(self.agent_id, self.env.user, "chat", text=text, sources=sources,
			conversation=self)
		reply = Message.create({"conversation_id": self.id, "role": "agent", "body_html": run.output_html or Markup(""),
			"run_id": run.id})
		return reply


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


class AiChatApi(models.Model):
	"""What the chat page calls; each method checks who calls it"""

	_inherit = "veron.ai.conversation"

	@api.model
	def veron_chat_agents(self):
		agents = self.env["veron.ai.agent"].search([("enabled", "=", True), ("trigger_manual", "=", True)])
		return [{"id": a.id, "name": a.name, "role": a.template_id.name or "", "description": a.description or a.goal or "",
			"level": dict(a._fields["authority_level"]._description_selection(self.env)).get(a.authority_level)}
			for a in agents if a._may_use(self.env.user)]

	@api.model
	def veron_chat_open(self, agent_id):
		agent = self.env["veron.ai.agent"].browse(int(agent_id)).exists()
		if not agent:
			raise UserError(_("No such agent."))
		conversation = self._for(agent)
		return {"conversation_id": conversation.id, "messages": [m._chat_dict() for m in conversation.message_ids[-60:]]}

	@api.model
	def veron_chat_send(self, conversation_id, text, source_ids=None, transcripts=None):
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
		conversation._post(text, sources)
		return [m._chat_dict() for m in conversation.message_ids - before]


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
			"pending": [{"id": a.id, "name": a.name, "summary": a.summary or "", "kind": a.kind} for a in pending],
			"date": str(self.create_date),
		}
