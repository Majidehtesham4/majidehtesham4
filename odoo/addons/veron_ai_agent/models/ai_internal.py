"""The built-in assistant: it answers without a language model. It finds what is asked in its library,
takes the period, the counts, the records and the files from the request, the page the person is on and
what was said before, asks for what is missing, runs the tool through the same gate as any agent (the
person's own rights, the agent's grants, approvals for what needs them) and writes the answer itself.

What it remembers of a conversation: the last command and its arguments, the records spoken of, and the
question it is waiting an answer to."""

import json
import re
from collections import Counter

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
# Records of people: looked for after the things (products) named in the same request
PEOPLE = {"res.partner", "hr.employee", "res.users"}
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
		# The words of the request that named a record already (the customer's name), left out of the next search
		self.taken = Counter()
		# The asked values given by the lines of several products said at once
		self.in_lines = set()
		# Words of things (products) not yet chosen, kept out of a search for a person
		self.not_people = Counter()
		# The records a search is kept to: the products of the draft being changed
		self.within = {}

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
		intent, score, ranked = self._by_what_is_named(text, intent, score, ranked)
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

	def _by_what_is_named(self, text, intent, score, ranked):
		"""Of commands about as likely as each other, the one whose records are named in the request goes first:
		«یک میز کار استیل ۳۰۱۰ برای معتمدی فاکتور کن» names a product and a customer, so it is an invoice, not the
		«کار» of the tasks"""
		close = [(i, s) for i, s in ranked[:4] if s >= max(UNSURE, score - 0.12)]
		if len(close) < 2:
			return intent, score, ranked
		def named(candidate):
			slots = [slot for slot in candidate._slots() if slot.get("model") and not slot.get("page")]
			return sum(1 for slot in slots if slot["model"] in self.env and self._search(slot["model"], text, candidate))
		rescored = sorted(((i, s + 0.08 * named(i)) for i, s in close), key=lambda item: -item[1])
		rest = [item for item in ranked if item[0] not in {i for i, _s in close}]
		ranked = rescored + rest
		return ranked[0][0], ranked[0][1], ranked

	def _say(self, message):
		return Markup("<p>%s</p>") % message

	def _match(self, text):
		message = nlu.tokens(text)
		ranked = []
		page = self.run.page_model or ""
		intents = self.env["veron.ai.intent"].sudo().search([]).filtered(lambda i: i._usable(self.user))
		vocabulary = {w for intent in intents for phrase in intent._phrase_tokens(self.user) for w in phrase}
		known = nlu.known_words(message, vocabulary)
		for intent in intents:
			needs = {slot["page"] for slot in intent._slots() if slot.get("page") and slot.get("required")}
			if "model" in needs and not page or "id" in needs and not self.run.page_res_id:
				continue
			score = max([nlu.similarity(message, phrase, known) for phrase in intent._phrase_tokens(self.user)] or [0.0])
			if page and page in (intent.page_models or "").split(","):
				score += 0.08
			tool = registry.get(intent.tool_code) if intent.tool_code else None
			if tool and not all(self.env[model].with_user(self.user).has_access("read") for model in tool.models):
				# A command on what the person may not see is a weaker guess; asked for plainly, it still says why not
				score -= 0.15
			remembered = self.memory.get("records") or {}
			if any(slot.get("remembered") and remembered.get(slot.get("model")) for slot in intent._slots()):
				# A change to what was just made: «براش تخفیف بده» after a draft invoice
				score += 0.1
			if not self.sources and any(slot.get("file") and slot.get("required") for slot in intent._slots()):
				score -= 0.1
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
		answer = self._do(intent, text)
		if text:
			# Learned without the names and numbers in it: «۲ تا فر برای حسن پور فاکتور کن» teaches «فاکتور کن»
			words = [w for w in nlu.normalize(text).split() if w not in self.taken and not w.isdigit()]
			self.env["veron.ai.intent.phrase"]._learn(intent, " ".join(words))
		return answer

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
		slot = next((s for s in intent._slots() if s.get("arg") == pending.get("arg")), None)
		# A reply naming what was asked is the answer, even when its words sound like another command
		# («میز کار استیل» is not the «کار» of the tasks)
		answers = bool(slot and slot.get("model") in self.env and (self._pick_option(text, pending.get("options") or [])
			or self._search(slot["model"], text, intent)))
		new_intent, score, _ranked = self._match(text)
		if not answers and new_intent and new_intent != intent and score >= SURE + 0.15:
			self.memory.pop("pending", None)
			return None
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
					return self._ask(intent, args, slot, found, pending.get("text") or "")
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
		lines = self._lines(intent, args, text)
		if isinstance(lines, Markup):
			return lines
		self._things_first(intent, args, text)
		for slot in intent._slots():
			if slot["arg"] in self.in_lines:
				continue
			given = args.get(slot["arg"])
			if slot["arg"] in args and not (isinstance(given, str) and given.startswith("$")):
				if slot.get("model") in self.env and isinstance(args[slot["arg"]], int):
					record = self.env[slot["model"]].browse(args[slot["arg"]]).exists()
					self._take(record)
					self._keep_within(intent, slot, record)
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
				values = self._numbers(text, money=slot.get("money"))
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
				self._keep_within(intent, slot, record)
			elif slot.get("required"):
				return self._wait(intent, args, slot, text, slot.get("question") or _("Which one?"), self._recent(slot))
		if self.run.page_filters and args.get("model") == self.run.page_model and "filters" in properties \
				and any(slot.get("page") for slot in intent._slots()):
			# «This section» is the list as the person sees it: the conditions of the page come along
			args["filters"] = list(args.get("filters") or []) + list(self.run.page_filters)
		return self._run(intent, _fill(args))

	# --- several products in one request, and things named before people

	def _line_slots(self, intent):
		"""The list argument made of lines (an invoice's), its line, and the asked product and count in it"""
		slots = {slot["arg"]: slot for slot in intent._slots()}
		for key, value in intent._args().items():
			if isinstance(value, list) and value and isinstance(value[0], dict):
				names = {v[1:] for v in value[0].values() if isinstance(v, str) and v.startswith("$")}
				product = next((slots[n] for n in names if n in slots and slots[n].get("model")), None)
				count = next((slots[n] for n in names if n in slots and slots[n].get("number")), None)
				if product:
					return key, value[0], product, count
		return None

	def _segments(self, text):
		"""The parts of a request joined by «و» or commas: «یک فر ۱۱۵۴ و دو فر ۱۴۵۶». «بیست و پنج» stays one number"""
		# Commas (not those of «۲,۰۰۰,۰۰۰») go before the text is made one form, which takes punctuation out
		words = nlu.normalize(re.sub(r"[،,](?!\d)|(?<!\d)[،,]|[+\n]", " و ", text or "")).split()
		numberish = set(nlu.UNITS) | set(nlu.SCALES)
		parts, current = [], []
		for index, word in enumerate(words):
			before = words[index - 1] if index else ""
			after = words[index + 1] if index + 1 < len(words) else ""
			# Only a number in words goes on after «و»: «۱۱۵۴ و یک عدد ۱۴۵۶» is two parts
			joins = word == "و" and before in numberish and after in numberish
			if word == "و" and not joins:
				if current:
					parts.append(" ".join(current))
				current = []
			else:
				current.append(word)
		if current:
			parts.append(" ".join(current))
		return parts

	def _count_in(self, text, record, default):
		"""The count said in a part of the request, leaving out the numbers of the record's own name"""
		name = list(nlu.name_words(record.display_name))
		left = []
		for word in nlu.normalize(text).split():
			if word in name:
				name.remove(word)
			else:
				left.append(word)
		values = [value for value, _unit in nlu.amounts(" ".join(left))]
		return values[0] if values else default

	def _lines(self, intent, args, text):
		"""Several products said at once become several lines; one that is not clear is asked, then the next"""
		found = self._line_slots(intent)
		if not found:
			return None
		key, line, product_slot, count_slot = found
		model, arg = product_slot["model"], product_slot["arg"]
		default = (count_slot or {}).get("default", 1)
		count_arg = count_slot["arg"] if count_slot else None
		if "_segments" in args:
			segments = list(args["_segments"])
			if isinstance(args.get(arg), int) and segments:
				# The answer to the part that was asked
				record = self.env[model].browse(args.pop(arg)).exists()
				args.pop(count_arg, None)
				args["_lines"] = args.get("_lines", []) + [{"id": record.id, "count": self._count_in(segments[0], record, default)}]
				segments = segments[1:]
		else:
			parts = self._segments(text)
			if len(parts) < 2 or not all(self._search(model, part, intent) for part in parts[:2]):
				return None
			segments, args["_lines"] = parts, []
		while segments:
			part = segments[0]
			records = self._search(model, part, intent)
			if len(records) == 1:
				args["_lines"].append({"id": records.id, "count": self._count_in(part, records, default)})
				segments = segments[1:]
				continue
			if not records:
				# A part with no product in it: the customer's name, «فاکتور کن»
				segments = segments[1:]
				continue
			args["_segments"] = segments
			options = [(record.id, record.display_name) for record in records[:6]]
			return self._wait(intent, args, product_slot, text, _("Which product for «%s»?", part) + self._more(records),
				options)
		args.pop("_segments", None)
		if not args.get("_lines"):
			return None
		# A name with «و» in it («نصب و راه اندازی») was cut in two: the two halves are one line
		merged = []
		for item in args["_lines"]:
			name = nlu.normalize(self.env[model].browse(item["id"]).display_name)
			if merged and merged[-1]["id"] == item["id"] and " و " in f" {name} ":
				continue
			merged.append(item)
		args["_lines"] = merged
		# The products' words are left out of the customer's search only now: «فر ریلی» of one line is still
		# looked for in the next
		for item in args["_lines"]:
			self._take(self.env[model].browse(item["id"]).exists())
		def made(item):
			return {k: (item["id"] if v == "$" + arg else item["count"] if count_arg and v == "$" + count_arg else v)
				for k, v in line.items()}
		args[key] = [made(item) for item in args["_lines"]]
		self.in_lines = {arg} | ({count_arg} if count_arg else set())
		return None

	def _things_first(self, intent, args, text):
		"""A product or a document named in the request is found before a person: the words of «فر پیتزا ریلی» are
		then not taken for the customer «پیتزا معتمدی». When it is not clear which one, the words they share are
		still left out of the person's search."""
		slots = [slot for slot in intent._slots() if slot.get("model") and slot["arg"] not in self.in_lines]
		if not any(slot["model"] in PEOPLE for slot in slots):
			return
		for slot in slots:
			given = args.get(slot["arg"])
			if slot["model"] in PEOPLE or slot["model"] not in self.env or slot["arg"] in args and not (
					isinstance(given, str) and given.startswith("$")):
				continue
			records = self._search(slot["model"], text, intent)
			if len(records) == 1:
				args[slot["arg"]] = records.id
				self._take(records)
			elif records:
				said = set(nlu.name_words(text))
				shared = set.intersection(*(set(nlu.name_words(r.display_name)) for r in records))
				self.not_people.update(shared & said)

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
		run, by = self.run, ""
		agent = run.agent_id
		if agent.is_supervisor and not agent._grant(intent.tool_code):
			# A supervisor gives the task to the agent of its team that has the tool, with the person's own rights
			delegate = agent.delegate_agent_ids.filtered(lambda a: a.enabled and a._grant(intent.tool_code))[:1]
			if delegate:
				run = self.env["veron.ai.run"].sudo()._enqueue(delegate, self.run.run_user_id or self.env.user,
					"supervisor", text=self.run.input_text, parent=self.run)
				by = delegate.name
		output = run._call_tool(intent.tool_code, args, origin="internal", env=self.env)
		if by:
			run.sudo().write({"state": "done", "finished_at": fields.Datetime.now(),
				"output_html": render.answer(intent.tool_code, output)})
		if isinstance(output, dict) and output.get("section") and self.run.page_title and not args.get("id"):
			output["section"] = self.run.page_title
		intent.sudo().use_count += 1
		self.memory["last"] = {"intent": intent.code, "args": args}
		head = Markup("<p class='text-muted small'>%s</p>") % (f"{intent.name} - {self.label}" if self.label else intent.name)
		if by:
			head += Markup("<p class='text-muted small'>%s</p>") % _("Done by «%s», of this supervisor's team.", by)
		self._remember(output)
		return head + render.answer(intent.tool_code, output)

	def _remember(self, output):
		if not isinstance(output, dict):
			return
		if output.get("draft_id"):
			self.memory.setdefault("records", {})["account.move"] = output["draft_id"]
			self.options = [{"label": _("Open the Draft"), "res_model": "account.move", "res_id": output["draft_id"]}]
			# The next step of a draft invoice: posting it, which waits for an approval
			post = self.env["veron.ai.intent"].sudo().search([("code", "=", "invoice_post")], limit=1)
			if post and post._usable(self.user) and self.agent.sudo()._grant(post.tool_code):
				self.options.append({"code": post.code, "label": post.name})

	def _wait(self, intent, args, slot, text, question, options=None):
		self.memory["pending"] = {"intent": intent.code, "args": args, "arg": slot["arg"], "text": text,
			"options": options or [], "question": question}
		if options:
			self.options = [{"choice": index + 1, "label": name} for index, (_id, name) in enumerate(options)]
		return self._say(question)

	def _recent(self, slot):
		"""The last records of the kind asked for, to choose with one click rather than typing a name"""
		model = slot.get("model")
		if model not in self.env:
			return []
		Model = self.env[model]
		try:
			domain = self.agent._scope_domain(model, self.env) & Domain(slot.get("recent") or [])
		except registry.ToolDenied:
			return []
		if model in self.within:
			# The lines of the draft being changed, to choose from
			domain &= Domain("id", "in", self.within[model])
		order = "write_date desc, id desc" if "write_date" in Model._fields else "id desc"
		return [(record.id, record.display_name) for record in Model.search(domain, order=order, limit=5)]

	def _ask(self, intent, args, slot, records, text=""):
		options = [(record.id, record.display_name) for record in records[:6]]
		# The request is kept: its count and its other names are read again once this one is chosen
		return self._wait(intent, args, slot, text, _("Which one? %s", slot.get("question") or "") + self._more(records),
			options)

	def _more(self, records):
		if len(records) <= 6:
			return ""
		return " " + _("%s fit; write a word more of the name (its code, its width...) to choose among them.", len(records))

	# --- records and files

	def _record(self, slot, text, intent, args):
		model = slot["model"]
		if model not in self.env:
			return None
		page = self.run.page_model == model and self.run.page_res_id
		remembered = (self.memory.get("records") or {}).get(model)
		if slot.get("remembered") and remembered and not nlu.refs(text):
			# The draft just made is the one to change: «براش ۱۰ درصد تخفیف بده»
			found = self.env[model].browse(remembered).exists()
			if found:
				return found
		if page and (nlu.refers_back(text) or not text):
			return self.env[model].browse(self.run.page_res_id).exists()
		if remembered and (nlu.refers_back(text) or not text):
			return self.env[model].browse(remembered).exists()
		found = self._search(model, text, intent)
		if len(found) == 1:
			self.memory.setdefault("records", {})[model] = found.id
			self._take(found)
			return found
		if len(found) > 1:
			return self._ask(intent, args, slot, found, text)
		if page and not slot.get("ask_on_page"):
			return self.env[model].browse(self.run.page_res_id).exists()
		return None

	def _keep_within(self, intent, slot, record):
		"""A slot «within» another («the product of this draft»): its search kept to the records of that one"""
		for other in intent._slots():
			within = other.get("within") or {}
			if within.get("of") == slot["arg"] and other.get("model") in self.env and record:
				self.within[other["model"]] = record.mapped(within.get("path", "id")).ids

	def _take(self, record):
		# As many times as the name has them: «پیتزا» of the product, and again of «پیتزا خبازیان» the customer
		self.taken.update(nlu.name_words(record.display_name))

	def _numbers(self, text, money=False):
		"""The numbers of the request that are not part of a name found in it («عرض ۵۰» of the product)"""
		taken, words = Counter(self.taken), []
		for word in nlu.normalize(text).split():
			# Each word of the name once: «۵۰ عدد فر عرض ۵۰» still has its count
			if taken[word] > 0:
				taken[word] -= 1
			else:
				words.append(word)
		left = " ".join(words)
		# Prices said in toman are kept in rial
		return [value * 10 if money and unit == "toman" else value for value, unit in nlu.amounts(left)]

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
		intent_words = intent._command_words() if intent else set()
		left_out = self.taken + (self.not_people if model in PEOPLE else Counter())
		words, commands = [], []
		for w in nlu.name_words(text):
			if left_out[w] > 0:
				# A word of a record found already, once for each time that record has it
				left_out[w] -= 1
			elif w in nlu.UNITS or w in nlu.SCALES:
				continue
			elif nlu.stem(w) in intent_words:
				# «مشتری» of the command may still be part of a name: «پیتزا معتمدی مشتری خبازیان»
				commands.append(w)
			else:
				words.append(w)
		if model in self.within:
			# A product of the draft spoken of: one of its lines
			domain &= Domain("id", "in", self.within[model])
		# The records with any word of the request, in any of the ways it may be written, then ranked by how many
		# of the words they have: «فر ریلی ۵۰» finds «فر پیتزا ریلی ۱۱۵۴ عرض ۵۰»
		look = [w for w in words if len(w) >= 3 or len(w) == 2 and not w.isdigit()]
		if not look:
			return Model.browse()
		candidates = Model.browse()
		for word in dict.fromkeys(look):
			if word.isdigit() and len(word) < 3:
				continue
			found = Domain.OR([Domain("display_name", "ilike", variant) for variant in nlu.variants(word)])
			pattern = nlu.like(word)
			if pattern:
				found = found | Domain(name_field, "=ilike", pattern)
				if "default_code" in Model._fields:
					found = found | Domain("default_code", "=ilike", pattern)
			candidates |= Model.search(domain & found, limit=80)
		ranked = []
		for record in candidates:
			score, hit, size = nlu.name_score(words, record.display_name)
			if score >= 1 or score >= 0.8 and size == 1:
				ranked.append((score, hit / size if size else 0, record))
		if not ranked:
			return Model.browse()
		ranked.sort(key=lambda item: (-item[0], -item[1], item[2].id))
		best = ranked[0][0]
		top = [item for item in ranked if item[0] >= best - 0.01]
		if len(top) > 1 and commands:
			# Equal without the command's words: the one that also has them in its name
			scored = [(nlu.name_score(words + commands, item[2].display_name)[0], item) for item in top]
			most = max(score for score, _item in scored)
			if most > best + 0.01:
				top = [item for score, item in scored if score >= most - 0.01]
		if len(top) > 1:
			top = self._preferred(model, intent, top)
		whole = [item for item in top if item[1] >= 0.999]
		if len(top) == 1 or len(whole) == 1:
			# The one whose whole name was said: «حسن پور», not «شرکت حسن‌پور و پسران»
			return (whole or top)[0][2]
		if model not in PEOPLE:
			base = self._base(words, [item[2] for item in top])
			if base:
				return base
		# Otherwise only those as good as the best: the others lack a word that was said
		return Model.browse([item[2].id for item in top[:30]])

	def _preferred(self, model, intent, top):
		"""Of records that fit equally, those the command is about: an invoice's customer is one who buys (not the
		employee or the supplier of the same name), its product one that is sold; a company and its own contacts are
		the company"""
		slot = next((s for s in (intent._slots() if intent else []) if s.get("model") == model), {})
		records = self.env[model].browse([item[2].id for item in top])
		if slot.get("prefer"):
			liked = records.filtered_domain(slot["prefer"])
			if liked:
				top = [item for item in top if item[2] in liked]
				records = liked
		if model == "res.partner" and len(records) > 1 and len(records.commercial_partner_id) == 1 \
				and records.commercial_partner_id in records:
			top = [item for item in top if item[2] == records.commercial_partner_id]
		return top

	def _base(self, words, records):
		"""Of things that fit the words equally, the one the others are variants of: «فر ۱۴۵۶ عرض ۸۰» rather than
		«فر ۱۴۵۶ عرض ۸۰ بدون پایه», whose «بدون پایه» was not said. «عرض ۵۰» and «عرض ۶۰» are not variants of each
		other, so they are asked."""
		said = set(words)
		extra = {record: set(nlu.name_words(record.display_name)) - said for record in records}
		for record, own in extra.items():
			if all(own < other for each, other in extra.items() if each != record):
				return record
		return None

	def _rest(self, text, intent):
		"""The words of the request beyond those of the command, e.g. the name to look for"""
		intent_words = intent._command_words()
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

	def used(item, found):
		if isinstance(item, dict):
			for v in item.values():
				used(v, found)
		elif isinstance(item, list):
			for v in item:
				used(v, found)
		elif isinstance(item, str) and item.startswith("$"):
			found.add(item[1:])
		return found

	# A value asked only to be put inside another argument (the product and quantity of a line) is not an argument
	inner = set()
	for v in args.values():
		if isinstance(v, (dict, list)):
			used(v, inner)
	filled = {k: value(v) for k, v in args.items() if k not in inner or isinstance(v, str) and v.startswith("$")}
	# A value not said and not needed (the product of «all the lines») is left out, not sent empty
	return {k: v for k, v in filled.items() if not (isinstance(k, str) and k.startswith("_")) and v is not None
		and not (isinstance(v, str) and v.startswith("$"))}


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
