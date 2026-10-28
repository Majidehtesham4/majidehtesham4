"""The built-in assistant: it answers without a language model. It finds what is asked in its library,
takes the period, the counts, the records and the files from the request, the page the person is on and
what was said before, asks for what is missing, runs the tool through the same gate as any agent (the
person's own rights, the agent's grants, approvals for what needs them) and writes the answer itself.

What it remembers of a conversation: the last command and its arguments, the records spoken of, and the
question it is waiting an answer to."""

import json
import re

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.fields import Domain

from ..services import nlu, registry, render

SURE = 0.5
UNSURE = 0.28
GREETING = re.compile(r"^(سلام|درود|سلام علیکم|صبح بخیر|عصر بخیر|وقت بخیر|hi|hello)\b")
THANKS = re.compile(r"\b(ممنون|مرسی|متشکر|سپاس|دستت درد نکنه|thanks)\b")
HELP = re.compile(r"\b(چه کار|چکار|چیکار|چه کارهایی|کمک|راهنما|راهنمایی|بلدی|میتونی|می تونی|help)\b")
# A question about the assistant itself, not about work
ABOUT = re.compile(r"\b(بلدی|راهنما|راهنمایی|help)\b|(چه|چی) کار(ها)?(یی)? (می|می )?(تونی|توانی|کنی|بلدی)|چیکار (میتونی|می تونی|می کنی)")
NUMBER_WORDS = {"اولی": 1, "اول": 1, "دومی": 2, "دوم": 2, "سومی": 3, "سوم": 3, "چهارمی": 4, "چهارم": 4, "پنجمی": 5, "پنجم": 5}


class Brain:
	def __init__(self, run, env):
		self.run = run
		self.env = env
		self.user = env.user
		self.agent = run.agent_id
		self.conversation = run.conversation_id
		self.memory = dict(self.conversation.memory or {}) if self.conversation else {}
		self.today = fields.Date.context_today(env.user)
		self.sources = run.source_ids
		self.options = []
		self.label = ""

	# --- the answer

	def respond(self, text):
		text = (text or "").strip()
		words = nlu.normalize(text)
		if text.startswith("#intent:"):
			return self._chosen(text.split(":", 1)[1].strip())
		if not words and self.sources and not self.run.sources_carried:
			return self._files_only()
		if self.memory.get("pending") and not GREETING.match(words):
			answer = self._answer_pending(text)
			if answer is not None:
				return answer
		if ABOUT.search(words) and len(nlu.tokens(text)) <= 5:
			return self._help()
		if self.memory.get("last") and (words.startswith("و ") or nlu.only_context(text)):
			# «و این ماه؟» asks the last question again for another period, before any other meaning
			follow = self._follow_up(text)
			if follow is not None:
				return follow
		intent, score, ranked = self._match(text)
		if score < SURE:
			if GREETING.match(words) and len(nlu.tokens(text)) <= 2:
				return self._say(_("Hello! Ask me about sales, customers, invoices, purchases, stock, petty cash or payroll, "
					"or send a photo, a PDF or an Excel file. Type «what can you do» for examples."))
			if THANKS.search(words) and len(nlu.tokens(text)) <= 3:
				return self._say(_("You are welcome."))
			if HELP.search(words):
				return self._help()
			follow = self._follow_up(text)
			if follow is not None:
				return follow
		# Two meanings as likely as each other: the person chooses rather than the assistant guessing
		tied = score >= SURE and len(ranked) > 1 and ranked[1][1] >= score - 0.02
		if score >= SURE and not tied:
			return self._do(intent, text)
		candidates = [(i, s) for i, s in ranked if s >= UNSURE * 0.7][:3]
		if score >= UNSURE and candidates:
			self.memory["unclear"] = text
			self.options = [{"code": i.code, "label": i.name} for i, _s in candidates]
			return self._say(_("Which one do you mean? Choose below; I will remember it for next time."))
		return self._not_understood(ranked)

	def _say(self, message):
		return Markup("<p>%s</p>") % message

	def _match(self, text):
		message = nlu.tokens(text)
		ranked = []
		page = self.run.page_model or ""
		for intent in self.env["veron.ai.intent"].sudo().search([]):
			if not intent._usable(self.user):
				continue
			needs = {slot["page"] for slot in intent._slots() if slot.get("page") and slot.get("required")}
			if "model" in needs and not page or "id" in needs and not self.run.page_res_id:
				continue
			score = max([nlu.similarity(message, phrase) for phrase in intent._phrase_tokens(self.user)] or [0.0])
			if page and page in (intent.page_models or "").split(","):
				score += 0.08
			tool = registry.get(intent.tool_code) if intent.tool_code else None
			if tool and not all(self.env[model].with_user(self.user).has_access("read") for model in tool.models):
				# A command on what the person may not see is a weaker guess; asked for plainly, it still says why not
				score -= 0.15
			if self.sources and any(slot.get("file") for slot in intent._slots()):
				# A file sent now makes its commands likelier; the file of an earlier message a little
				score += 0.04 if self.run.sources_carried else 0.1
			ranked.append((intent, score))
		ranked.sort(key=lambda item: -item[1])
		return (ranked[0][0], ranked[0][1], ranked) if ranked else (None, 0.0, [])

	def _not_understood(self, ranked):
		examples = [i.name for i, _s in ranked[:4] if i.example]
		body = _("I did not understand this. You can ask, for example:")
		items = Markup("").join(Markup("<li>%s</li>") % example for example in examples)
		hint = ""
		if self.env["veron.ai.provider"]._get("llm", self.agent.llm_provider_id, self.agent.company_id):
			hint = Markup("<p class='text-muted small'>%s</p>") % _("Or send it to the AI with the switch above the box.")
		return Markup("<p>%s</p><ul>%s</ul>%s") % (body, items, hint)

	def _help(self):
		sections = dict(self.env["veron.ai.intent"]._fields["section"]._description_selection(self.env))
		by_section = {}
		page = self.run.page_model or ""
		for intent in self.env["veron.ai.intent"].sudo().search([]):
			if intent._usable(self.user) and intent.example:
				by_section.setdefault(intent.section, []).append(intent)
		parts = [Markup("<p>%s</p>") % _("I work with the program's tools and your own access. For example:")]
		order = sorted(by_section, key=lambda s: 0 if any(page in (i.page_models or "") for i in by_section[s] if page) else 1)
		for section in order:
			examples = Markup("").join(Markup("<li>%s</li>") % i.name for i in by_section[section][:4])
			parts.append(Markup("<p><b>%s</b></p><ul>%s</ul>") % (sections.get(section, section), examples))
		return Markup("").join(parts)

	def _files_only(self):
		kinds = set(self.sources.mapped("kind"))
		candidates = []
		for intent in self.env["veron.ai.intent"].sudo().search([]):
			slot = next((s for s in intent._slots() if s.get("file")), None)
			if slot and intent._usable(self.user) and kinds & set(slot.get("kinds") or ["image", "pdf", "sheet"]):
				candidates.append(intent)
		if len(candidates) == 1:
			return self._do(candidates[0], "")
		self.memory["unclear"] = ""
		self.options = [{"code": i.code, "label": i.name} for i in candidates[:4]]
		return self._say(_("What should I do with this file?"))

	def _chosen(self, code):
		intent = self.env["veron.ai.intent"].sudo().search([("code", "=", code)], limit=1)
		if not intent or not intent._usable(self.user):
			return self._say(_("This command is not available to you."))
		text = self.memory.pop("unclear", "") or ""
		if text:
			self.env["veron.ai.intent.phrase"]._learn(intent, text)
		return self._do(intent, text)

	# --- what was said before

	def _follow_up(self, text):
		"""A short request about the last answer: another period, the next page, another record"""
		last = self.memory.get("last") or {}
		intent = self.env["veron.ai.intent"].sudo().search([("code", "=", last.get("intent"))], limit=1) if last else None
		if not intent or not intent._usable(self.user):
			return None
		args = dict(last.get("args") or {})
		tool = registry.get(intent.tool_code) if intent.tool_code else None
		properties = (tool.schema.get("properties") or {}) if tool else {}
		changed = False
		if nlu.is_more(text) and "limit" in properties:
			args["limit"] = min((args.get("limit") or 20) * 2, properties["limit"].get("maximum", 100))
			changed = True
		said = nlu.period(text, self.today)
		if said and intent.period != "none":
			self._put_period(intent, args, said)
			changed = True
		for slot in intent._slots():
			if slot.get("file") or slot.get("number") or not slot.get("model"):
				continue
			found = self._search(slot["model"], text, intent)
			if len(found) == 1:
				args[slot["arg"]] = found.id
				changed = True
		if not changed:
			return None
		return self._run(intent, args)

	def _answer_pending(self, text):
		pending = self.memory.get("pending") or {}
		intent = self.env["veron.ai.intent"].sudo().search([("code", "=", pending.get("intent"))], limit=1)
		if not intent:
			self.memory.pop("pending", None)
			return None
		new_intent, score, _ranked = self._match(text)
		if new_intent and new_intent != intent and score >= SURE + 0.15:
			self.memory.pop("pending", None)
			return None
		slot = next((s for s in intent._slots() if s.get("arg") == pending.get("arg")), None)
		args = dict(pending.get("args") or {})
		if not slot:
			self.memory.pop("pending", None)
			return None
		if slot.get("file"):
			source = self._file(slot)
			if not source:
				return self._say(slot.get("question") or _("Send the file, please."))
			args[slot["arg"]] = source.id
		elif slot.get("text"):
			args[slot["arg"]] = text.strip()[:100]
		elif slot.get("number"):
			values = nlu.amounts(text)
			if not values:
				return self._say(slot.get("question") or _("How many?"))
			args[slot["arg"]] = values[0][0]
		else:
			choice = self._pick_option(text, pending.get("options") or [])
			if not choice:
				found = self._search(slot["model"], text, intent)
				if len(found) == 1:
					choice = found.id
				elif found:
					return self._ask(intent, args, slot, found)
				else:
					return self._say(_("I did not find it. %s", slot.get("question") or ""))
			args[slot["arg"]] = choice
		self.memory.pop("pending", None)
		return self._do(intent, pending.get("text") or "", args)

	def _pick_option(self, text, options):
		if not options:
			return None
		words = nlu.normalize(text)
		index = NUMBER_WORDS.get(words) or (int(words) if words.isdigit() else None)
		if index and 1 <= index <= len(options):
			return options[index - 1][0]
		for record_id, name in options:
			if nlu.normalize(name) == words or words in nlu.normalize(name):
				return record_id
		return None

	# --- doing it

	def _do(self, intent, text, args=None):
		if not intent.tool_code:
			intent.sudo().use_count += 1
			return intent.answer or self._say(intent.name)
		tool = registry.get(intent.tool_code)
		properties = tool.schema.get("properties") or {}
		args = dict(intent._args(), **(args or {}))
		if intent.period != "none" and not ({"date_from", "days", "month"} & set(args)):
			said = nlu.period(text, self.today)
			if said:
				self._put_period(intent, args, said)
			elif intent.default_days and "days" in properties:
				args["days"] = intent.default_days
		wanted = nlu.count(text)
		if wanted and "limit" in properties and "limit" not in args:
			args["limit"] = min(wanted, properties["limit"].get("maximum", 100))
		for slot in intent._slots():
			if slot["arg"] in args:
				continue
			if slot.get("file"):
				source = self._file(slot)
				if source:
					args[slot["arg"]] = source.id
				elif slot.get("required"):
					return self._wait(intent, args, slot, text, slot.get("question") or _("Send the file, please."))
				continue
			if slot.get("text"):
				value = self._rest(text, intent)
				if value:
					args[slot["arg"]] = value
				elif slot.get("required"):
					return self._wait(intent, args, slot, text, slot.get("question") or _("What should I look for?"))
				continue
			if slot.get("page"):
				# The section or the record the person has open
				value = self.run.page_model if slot["page"] == "model" else self.run.page_res_id
				if value:
					args[slot["arg"]] = value
				elif slot.get("required"):
					return self._say(_("Open the page of the section or of the record first, then ask here."))
				continue
			if slot.get("number"):
				values = [value for value, _unit in nlu.amounts(text)]
				if values:
					args[slot["arg"]] = values[0]
				elif "default" in slot:
					args[slot["arg"]] = slot["default"]
				elif slot.get("required"):
					return self._wait(intent, args, slot, text, slot.get("question") or _("How many?"))
				continue
			record = self._record(slot, text, intent, args)
			if isinstance(record, Markup):
				return record
			if record:
				args[slot["arg"]] = record.id
			elif slot.get("required"):
				return self._wait(intent, args, slot, text, slot.get("question") or _("Which one?"))
		if self.run.page_filters and args.get("model") == self.run.page_model and "filters" in properties \
				and any(slot.get("page") for slot in intent._slots()):
			# «This section» is the list as the person sees it: the conditions of the page come along
			args["filters"] = list(args.get("filters") or []) + list(self.run.page_filters)
		return self._run(intent, _fill(args))

	def _put_period(self, intent, args, said):
		date_from, date_to, self.label = said
		tool = registry.get(intent.tool_code)
		properties = (tool.schema.get("properties") or {}) if tool else {}
		for key in ("days", "date_from", "date_to", "month"):
			args.pop(key, None)
		if "date_from" in properties:
			args.update({"date_from": str(date_from), "date_to": str(date_to)})
		elif "month" in properties:
			from odoo.addons.veron_core.models import jalali

			year, month, _day = jalali.to_jalali(date_from)
			args["month"] = f"{year}/{month:02d}"
		elif "days" in properties:
			args["days"] = max((self.today - date_from).days + 1, 1)

	def _run(self, intent, args):
		output = self.run._call_tool(intent.tool_code, args, origin="internal", env=self.env)
		if isinstance(output, dict) and output.get("section") and self.run.page_title and not args.get("id"):
			output["section"] = self.run.page_title
		intent.sudo().use_count += 1
		self.memory["last"] = {"intent": intent.code, "args": args}
		head = Markup("<p class='text-muted small'>%s</p>") % (f"{intent.name} - {self.label}" if self.label else intent.name)
		self._remember(output)
		return head + render.answer(intent.tool_code, output)

	def _remember(self, output):
		if not isinstance(output, dict):
			return
		if output.get("draft_id"):
			self.memory.setdefault("records", {})["account.move"] = output["draft_id"]
			# The next step of a draft invoice: posting it, which waits for an approval
			post = self.env["veron.ai.intent"].sudo().search([("code", "=", "invoice_post")], limit=1)
			if post and post._usable(self.user) and self.agent.sudo()._grant(post.tool_code):
				self.options = [{"code": post.code, "label": post.name}]

	def _wait(self, intent, args, slot, text, question, options=None):
		self.memory["pending"] = {"intent": intent.code, "args": args, "arg": slot["arg"], "text": text,
			"options": options or []}
		if options:
			self.options = [{"choice": index + 1, "label": name} for index, (_id, name) in enumerate(options)]
		return self._say(question)

	def _ask(self, intent, args, slot, records):
		options = [(record.id, record.display_name) for record in records[:6]]
		return self._wait(intent, args, slot, "", _("Which one? %s", slot.get("question") or ""), options)

	# --- records and files

	def _record(self, slot, text, intent, args):
		model = slot["model"]
		if model not in self.env:
			return None
		page = self.run.page_model == model and self.run.page_res_id
		remembered = (self.memory.get("records") or {}).get(model)
		if page and (nlu.refers_back(text) or not text):
			return self.env[model].browse(self.run.page_res_id).exists()
		if remembered and (nlu.refers_back(text) or not text):
			return self.env[model].browse(remembered).exists()
		found = self._search(model, text, intent)
		if len(found) == 1:
			self.memory.setdefault("records", {})[model] = found.id
			return found
		if len(found) > 1:
			return self._ask(intent, args, slot, found)
		if page and not slot.get("ask_on_page"):
			return self.env[model].browse(self.run.page_res_id).exists()
		return None

	def _search(self, model, text, intent):
		"""Records of a model named in the text: a quoted name, a document number, or the longest run of words that
		names a record the person may see"""
		Model = self.env[model]
		try:
			domain = self.agent._scope_domain(model, self.env)
		except registry.ToolDenied:
			return Model.browse()
		name_field = Model._rec_name or "name"
		for ref in nlu.refs(text):
			found = Model.search(domain & Domain(name_field, "=ilike", ref), limit=2)
			if found:
				return found
		for name in nlu.quoted(text):
			found = Model.search(domain & Domain(name_field, "ilike", name), limit=6)
			if found:
				return found
		intent_words = {w for phrase in intent._phrase_tokens(self.user) for w in phrase} if intent else set()
		words = [w for w in nlu.normalize(text).split() if w not in nlu.STOP and nlu.stem(w) not in intent_words
			and not w.isdigit() and w not in nlu.UNITS and w not in nlu.SCALES]
		for size in (4, 3, 2, 1):
			for start in range(len(words) - size + 1):
				phrase = " ".join(words[start:start + size])
				if len(phrase) < 2:
					continue
				found = Model.search(domain & Domain(name_field, "ilike", phrase), limit=6)
				if found:
					exact = found.filtered(lambda r: nlu.normalize(r.display_name) == phrase)
					return exact[:1] or found
		return Model.browse()

	def _rest(self, text, intent):
		"""The words of the request beyond those of the command, e.g. the name to look for"""
		intent_words = {w for phrase in intent._phrase_tokens(self.user) for w in phrase}
		words = [w for w in nlu.normalize(text).split() if w not in nlu.STOP and nlu.stem(w) not in intent_words]
		return " ".join(words)[:100]

	def _file(self, slot):
		kinds = slot.get("kinds") or ["image", "pdf", "sheet"]
		return self.sources.filtered(lambda s: s.kind in kinds)[:1]


def _fill(args):
	"""Placeholders like "$product_id" in the fixed arguments, replaced by the asked values"""
	def value(item):
		if isinstance(item, str) and item.startswith("$"):
			return args.get(item[1:])
		if isinstance(item, dict):
			return {k: value(v) for k, v in item.items()}
		if isinstance(item, list):
			return [value(v) for v in item]
		return item

	filled = {k: value(v) for k, v in args.items()}
	return {k: v for k, v in filled.items() if not (isinstance(k, str) and k.startswith("_"))}


class AiConversationMemory(models.Model):
	_inherit = "veron.ai.conversation"

	memory = fields.Json(help="What the built-in assistant remembers of this conversation")


class AiRunInternal(models.Model):
	_inherit = "veron.ai.run"

	def _internal(self, env):
		"""The built-in assistant's answer to the request; the playbook's results, written out, when nothing is asked"""
		self.ensure_one()
		self.provider_name = _("Built-in Assistant")
		brain = Brain(self.sudo(), env)
		html = brain.respond(self.input_text or "")
		if brain.conversation:
			brain.conversation.sudo().memory = brain.memory
		self.sudo().options_json = json.dumps(brain.options, ensure_ascii=False) if brain.options else False
		return html

	@api.model
	def _render_results(self, results):
		parts = []
		for key, output in results.items():
			code = key.split(". ", 1)[-1]
			tool = registry.get(code)
			title = tool.label(self.env) if tool else code
			parts.append(Markup("<h5>%s</h5>%s") % (title, render.answer(code, output)))
		return Markup("").join(parts)
