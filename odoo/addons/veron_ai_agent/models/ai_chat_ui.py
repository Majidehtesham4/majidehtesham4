"""What the agent's page and the chat window show: the person's conversations with an agent, the options of a
conversation (web search, the steps of each answer, a longer thought), and the agent's panel with its instructions,
skills, knowledge and triggers. Each method checks who calls it; changes to the agent go through the ORM with the
caller's own rights."""
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

PAGE = 40


class AiConversationList(models.Model):
	_inherit = "veron.ai.conversation"

	title = fields.Char(help="The first words of the person's first message")
	last_date = fields.Datetime("Last Message", index=True)
	seen_date = fields.Datetime("Seen")
	opt_web_search = fields.Boolean("Web Search", default=True)
	opt_show_steps = fields.Boolean("Show Steps")
	opt_think_longer = fields.Boolean("Think Longer")

	def _mine(self, conversation_id):
		conversation = self.browse(int(conversation_id)).exists()
		if not conversation or conversation.user_id != self.env.user:
			raise AccessError(_("This is someone else's conversation."))
		return conversation

	def _post(self, text, sources, engine=None, page=None):
		reply = super()._post(text, sources, engine=engine, page=page)
		# The time of the transaction, as the messages' own: a time cut to the second would leave the answer unread
		now = self.env.cr.now()
		values = {"last_date": now, "seen_date": now}
		if not self.title:
			first = self.message_ids.filtered(lambda m: m.role == "user")[:1]
			words = first.body or ", ".join(first.source_ids.mapped("name"))
			values["title"] = " ".join((words or "").split())[:70]
		self.write(values)
		return reply

	def _list_dict(self):
		self.ensure_one()
		last = self.message_ids[-1:]
		snippet = (last.body if last.role == "user" else Markup(last.body_html or "").striptags()) if last else ""
		unread = bool(last and last.role == "agent" and (not self.seen_date or last.create_date > self.seen_date))
		return {"id": self.id, "title": self.title or self.agent_id.name, "snippet": " ".join((snippet or "").split())[:110],
			"date": fields.Datetime.to_string(self.last_date or self.create_date), "unread": unread,
			"empty": not last}

	def _options(self):
		self.ensure_one()
		return {"web_search": self.opt_web_search, "show_steps": self.opt_show_steps, "think_longer": self.opt_think_longer}

	@api.model
	def veron_chat_conversations(self, agent_id, search="", unread=False):
		"""The person's conversations with the agent, the latest first; empty ones are not listed"""
		domain = [("agent_id", "=", int(agent_id)), ("user_id", "=", self.env.uid), ("message_ids", "!=", False)]
		if search:
			domain += ["|", ("title", "ilike", search), ("message_ids.body", "ilike", search)]
		conversations = self.search(domain, order="last_date desc, id desc", limit=PAGE)
		items = [c._list_dict() for c in conversations]
		return [i for i in items if i["unread"]] if unread else items

	@api.model
	def veron_chat_load(self, conversation_id):
		conversation = self._mine(conversation_id)
		conversation.seen_date = self.env.cr.now()
		return {"conversation_id": conversation.id, "agent_id": conversation.agent_id.id,
			"messages": [m._chat_dict() for m in conversation.message_ids[-60:]], "options": conversation._options()}

	@api.model
	def veron_chat_start(self, agent_id):
		"""A new chat with the agent: an empty conversation of the person is used again rather than made anew; the
		latest conversation that has messages is offered to be resumed"""
		agent = self.env["veron.ai.agent"].browse(int(agent_id)).exists()
		if not agent or not agent._may_use(self.env.user):
			raise AccessError(_("You may not use this agent."))
		mine = self.search([("agent_id", "=", agent.id), ("user_id", "=", self.env.uid)], order="id desc", limit=20)
		empty = mine.filtered(lambda c: not c.message_ids)[:1]
		previous = (mine - empty).sorted(lambda c: c.last_date or c.create_date, reverse=True)[:1]
		conversation = empty or self.create({"agent_id": agent.id})
		return {"conversation_id": conversation.id, "agent_id": agent.id, "messages": [],
			"options": conversation._options(), "previous_id": previous.id or False}

	@api.model
	def veron_chat_options(self, conversation_id, values):
		conversation = self._mine(conversation_id)
		allowed = {"web_search": "opt_web_search", "show_steps": "opt_show_steps", "think_longer": "opt_think_longer"}
		conversation.write({allowed[k]: bool(v) for k, v in (values or {}).items() if k in allowed})
		return conversation._options()



class AiMessageSteps(models.Model):
	_inherit = "veron.ai.message"

	def _chat_dict(self):
		result = super()._chat_dict()
		run = self.run_id
		decisions = dict(self.env["veron.ai.run.step"]._fields["decision"]._description_selection(self.env))
		result["steps"] = [{"id": s.id, "name": s.tool_id.name or s.tool_code or "", "decision": s.decision or "",
			"decision_label": decisions.get(s.decision, ""), "message": s.message or ""}
			for s in run.sudo().step_ids] if run else []
		return result


class AiRunChatOptions(models.Model):
	_inherit = "veron.ai.run"

	def _llm(self, env, provider, results):
		"""The options of the conversation: no web search when the person turned it off; a longer thought"""
		options = self.conversation_id._options() if self.conversation_id else {}
		run = self
		if options.get("web_search") is False:
			run = run.with_context(veron_ai_skip_tools=["web_search"])
		if options.get("think_longer"):
			provider = provider.with_context(veron_ai_think=True)
		return super(AiRunChatOptions, run)._llm(env, provider, results)


class AiProviderThink(models.Model):
	_inherit = "veron.ai.provider"

	def _answer_tokens(self):
		tokens = self.sudo().max_tokens or 8000
		return max(tokens * 2, 16000) if self.env.context.get("veron_ai_think") else tokens

	def _config(self):
		config = super()._config()
		if self.env.context.get("veron_ai_think"):
			config.update({"effort": "xhigh", "max_tokens": self._answer_tokens()})
		return config


class AiAgentPanel(models.Model):
	_inherit = "veron.ai.agent"

	def _image_url(self):
		self.ensure_one()
		if self.image_128:
			return f"/web/image/veron.ai.agent/{self.id}/image_128?unique={fields.Datetime.to_string(self.write_date)}"
		return "/veron_ai_agent/static/description/icon.svg"

	def _can_edit(self):
		self.ensure_one()
		return self.env.user.has_group("veron_ai_agent.group_ai_manager") and self.has_access("write")

	@api.model
	def veron_chat_agents_list(self):
		"""The agents the person may talk to, for the chooser of the chat window"""
		agents = self.search([("enabled", "=", True), ("trigger_manual", "=", True)])
		return [{"id": a.id, "name": a.name, "image": a._image_url(), "description": a.description or a.goal or ""}
			for a in agents if a._may_use(self.env.user)]

	@api.model
	def veron_agent_panel(self, agent_id):
		agent = self.browse(int(agent_id)).exists()
		if not agent or not agent._may_use(self.env.user):
			raise AccessError(_("You may not use this agent."))
		kinds = dict(self.env["veron.ai.knowledge"]._fields["kind"]._description_selection(self.env))
		states = dict(self.env["veron.ai.knowledge"]._fields["state"]._description_selection(self.env))
		trigger_kinds = dict(self.env["veron.ai.trigger"]._fields["kind"]._description_selection(self.env))
		styles = self._fields["response_style"]._description_selection(self.env)
		return {
			"id": agent.id, "name": agent.name, "description": agent.description or agent.goal or "",
			"image": agent._image_url(), "enabled": agent.enabled, "can_edit": agent._can_edit(),
			"ai": agent._has_ai(), "engine": agent.engine, "instructions": agent.instructions or "",
			"instructions_html": str(agent._instructions_html()),
			"is_supervisor": agent.is_supervisor,
			"tools": [{"field": name, "label": self._fields[name]._description_string(self.env), "value": agent[name]}
				for name in ("use_image", "use_web_search", "self_update")],
			"skills": [{"id": s.id, "name": s.name, "icon": s.icon or "fa-magic", "description": s.description or ""}
				for s in agent.skill_ids],
			"subagents": [{"id": a.id, "name": a.name, "image": a._image_url()} for a in agent.delegate_agent_ids],
			"knowledge": [{"id": k.id, "name": k.name, "kind": k.kind, "kind_label": kinds.get(k.kind, ""), "state": k.state,
				"state_label": states.get(k.state, ""), "error": k.error or ""} for k in agent.knowledge_ids],
			"restrict_to_sources": agent.restrict_to_sources,
			"response_style": agent.response_style, "styles": [[k, v] for k, v in styles],
			"triggers": [{"id": t.id, "name": t.name, "kind": t.kind, "kind_label": trigger_kinds.get(t.kind, ""),
				"active": t.active} for t in agent.with_context(active_test=False).trigger_ids],
		}

	@api.model
	def veron_agent_panel_write(self, agent_id, values):
		"""A change made in the agent's panel: only these fields, by a manager of the agents"""
		agent = self.browse(int(agent_id)).exists()
		if not agent or not agent._can_edit():
			raise AccessError(_("Only a manager of the agents changes an agent."))
		allowed = {"instructions", "use_image", "use_web_search", "self_update", "restrict_to_sources", "response_style"}
		vals = {k: v for k, v in (values or {}).items() if k in allowed}
		for key, command in (("add_skill", 4), ("remove_skill", 3)):
			if values.get(key):
				vals.setdefault("skill_ids", []).append((command, int(values[key])))
		if values.get("remove_knowledge"):
			vals["knowledge_ids"] = [(3, int(values["remove_knowledge"]))]
		if values.get("add_subagent"):
			sub = self.browse(int(values["add_subagent"])).exists()
			if not sub or sub == agent:
				raise UserError(_("An agent does not supervise itself."))
			vals.update({"is_supervisor": True, "delegate_agent_ids": [(4, sub.id)]})
		if values.get("remove_subagent"):
			vals["delegate_agent_ids"] = [(3, int(values["remove_subagent"]))]
		if vals:
			agent.write(vals)
		return self.veron_agent_panel(agent.id)

	def _instructions_html(self):
		"""Instructions as written, with «# » headings and «- » lists, for reading"""
		self.ensure_one()
		html, items = [], []
		for line in (self.instructions or "").splitlines():
			stripped = line.strip()
			if stripped[:2] in ("- ", "* "):
				items.append(Markup("<li>%s</li>") % stripped[2:])
				continue
			if items:
				html.append(Markup("<ul>%s</ul>") % Markup("").join(items))
				items = []
			if stripped.startswith("#"):
				html.append(Markup("<h5>%s</h5>") % stripped.lstrip("#").strip())
			elif stripped:
				html.append(Markup("<p>%s</p>") % stripped)
		if items:
			html.append(Markup("<ul>%s</ul>") % Markup("").join(items))
		return Markup("").join(html)
