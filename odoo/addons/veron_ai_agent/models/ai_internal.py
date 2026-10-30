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
from odoo.exceptions import AccessError
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
		# The words that name the party of an order («برای خبازیان»): the only words a search for it reads
		self.party = None
		# Understanding only, nothing done: what «analyze» gives back
		self.dry = False
		self.frame = {}

	# --- what is understood, without doing it

	def analyze(self, text):
		"""The structured reading of a request, nothing done or remembered: the command, the action and the subjects
		said, the records found (or the candidates when several fit), the values, the period, what is still missing, the
		tool and its arguments, and the kind of answer. The same steps as an answer, stopped before the tool runs."""
		from ..services import contracts

		self.dry = True
		self.memory = dict(self.memory)
		self.frame = {"text": text, "action": nlu.action(text), "subjects": nlu.subjects(text), "intent": None,
			"tool": None, "score": 0.0, "candidates": [], "entities": {}, "values": {}, "period": None, "missing": [],
			"choices": {}, "args": None, "response": None}
		intent, score, ranked = self._match(text)
		intent, score, ranked = self._by_what_is_named(text, intent, score, ranked)
		self.frame["candidates"] = [(i.code, round(s, 3)) for i, s in ranked[:3]]
		self.frame["score"] = round(score, 3)
		intent, tied = self._untie(text, intent, score, ranked)
		if not intent or score < UNSURE or tied or score < SURE:
			# Not sure: the person would be asked which one
			self.frame["missing"].append("intent")
			return self.frame
		self.frame.update(intent=intent.code, tool=intent.tool_code or None)
		tool = registry.get(intent.tool_code) if intent.tool_code else None
		if not self.frame["action"] and tool:
			# Not said in words: the action of the command's tool
			self.frame["action"] = {"draft": "create", "execute": "approve", "suggest": "suggest"}.get(tool.action, "report"
				if tool.category in ("analyze", "report") else "view")
			self.frame["action_said"] = False
		else:
			self.frame["action_said"] = bool(self.frame["action"])
		said = nlu.period(text, self.today)
		if said:
			self.frame["period"] = {"from": str(said[0]), "to": str(said[1]), "label": said[2]}
		item = contracts.contract(intent.tool_code) if intent.tool_code else None
		self.frame["response"] = item["result"] if item else "answer"
		if intent.tool_code:
			self._do(intent, text)
		return self.frame

	def _note_missing(self, slot, options=None):
		if slot["arg"] not in self.frame["missing"]:
			self.frame["missing"].append(slot["arg"])
		if options:
			self.frame["choices"][slot["arg"]] = [record_id for record_id, _name in options]

	def _note_args(self, intent, args):
		"""The records and values the tool would be given"""
		self.frame["args"] = args
		for slot in intent._slots():
			value = args.get(slot["arg"])
			if slot.get("model") in self.env and isinstance(value, int):
				record = self.env[slot["model"]].browse(value).exists()
				self.frame["entities"][slot["arg"]] = {"model": slot["model"], "id": value, "name": record.display_name}
			elif slot.get("number") and isinstance(value, (int, float)):
				self.frame["values"][slot["arg"]] = value
			elif (slot.get("text") or slot.get("ahead")) and value not in (None, ""):
				self.frame["values"][slot["arg"]] = value
		found = self._line_slots(intent)
		if found and isinstance(args.get(found[0]), list):
			key, _line, product_slot, count_slot = found
			lines = []
			for item in args[key]:
				product_id = item.get(product_slot["arg"])
				if isinstance(product_id, int):
					lines.append({"product_id": product_id, "quantity": item.get(count_slot["arg"]) if count_slot else None})
			if lines:
				self.frame["lines"] = lines

	# --- the answer

	def respond(self, text):
		text = (text or "").strip()
		words = nlu.normalize(text)
		if text.startswith("#intent:"):
			return self._chosen(text.split(":", 1)[1].strip())
		codes = self.memory.pop("unclear_codes", None)
		code = self._pick_option(text, codes) if codes and len(nlu.tokens(text)) <= 3 else None
		if code:
			return self._chosen(code)
		if (words.isdigit() or words in NUMBER_WORDS) and not self.memory.get("pending"):
			# A number alone answers a list of choices; with none open it is not taken for anything else
			return self._say(_("No question is open for «%s» to answer. Write the whole request, please.", text))
		if not words and self.sources and not self.run.sources_carried:
			return self._files_only()
		if self.memory.get("pending") and ABOUT.search(words) and len(nlu.tokens(text)) <= 5:
			# Help asked in the middle of a question: given, and the question still waits for its answer
			return self._help()
		if self.memory.get("pending") and not GREETING.match(words):
			answer = self._answer_pending(text)
			if answer is not None:
				return answer
		if nlu.opens(text) and len(nlu.tokens(text)) <= 3:
			opened = self._open_last()
			if opened is not None:
				return opened
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
		intent, tied = self._untie(text, intent, score, ranked)
		if score >= SURE and not tied:
			return self._do(intent, text)
		candidates = [(i, s) for i, s in ranked if s >= UNSURE * 0.7][:3]
		if score >= UNSURE and candidates:
			self.memory["unclear"] = text
			self.options = [{"code": i.code, "label": i.name} for i, _s in candidates]
			# «۱» or «اولی» typed instead of a click is the same choice
			self.memory["unclear_codes"] = [[i.code, i.name] for i, _s in candidates]
			return self._say(_("Which one do you mean? Choose below; I will remember it for next time."))
		return self._not_understood(ranked)

	def _untie(self, text, intent, score, ranked):
		"""The command and whether another is as likely; of two, the one whose words stand together in the request
		wins: «۵ درصد تخفیف» on «... بدون پایه» is a discount, though «بدون» and «تخفیف» are both in it"""
		tied = score >= SURE and len(ranked) > 1 and ranked[1][1] >= score - 0.02
		if tied:
			together = [i for i, _s in ranked[:2] if self._said_together(i, text)]
			if len(together) == 1:
				return together[0], False
		return intent, tied

	def _said_together(self, intent, text):
		"""Whether a phrase of two words or more of the command is in the request with its words side by side"""
		words = nlu.tokens(text)
		for phrase in intent._phrase_tokens(self.user):
			size = len(phrase)
			if size >= 2 and any(words[i:i + size] == list(phrase) for i in range(len(words) - size + 1)):
				return True
		return False

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
		# «برای فرزامی چی فاکتور شده»، «محتوای فاکتور ... رو بیار» ask what there is: not a command that makes or changes
		asks = nlu.asks_what_is(text) or nlu.action(text) in ("view", "report", "search")
		# A whole order («۲ عدد X برای عباسی ...») is a new request, not a change to what was just made
		order = nlu.order_parts(text)
		ordered = bool(order["party"] and any(line["count"] for line in order["lines"]))
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
			if tool and tool.action != "read" and asks:
				score -= 0.15
			elif tool and tool.action == "read" and ordered and not asks:
				# Counts of things for a customer, with no word of a question: an order, not a report
				score -= 0.1
			remembered = self.memory.get("records") or {}
			changes = any(slot.get("remembered") for slot in intent._slots())
			if changes and ordered and nlu.action(text) not in ("edit", "delete"):
				# A whole order with its customer and counts is a new one, whatever is said of it («بدون مالیات»)
				score -= 0.1
			elif changes and any(slot.get("remembered") and remembered.get(slot.get("model")) for slot in intent._slots()):
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
		self.memory["unclear_codes"] = [[i.code, i.name] for i in candidates[:4]]
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
		if nlu.is_more(text) and "offset" in properties:
			# «بعدی»: the next page, not the same list again
			args["offset"] = (args.get("offset") or 0) + (args.get("limit") or 20)
			changed = True
		elif nlu.is_more(text) and "limit" in properties:
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
		if slot and len(nlu.tokens(text)) <= 3 and not self._pick_option(text, pending.get("options") or []):
			# What is said in the reply of another choice of the request («بدون مالیات» while a product is asked):
			# kept, and the question asked still waits
			said = {other["arg"]: self._choice(other, text, said_only=True, detect_only=True) for other in intent._slots()
				if other.get("choices") and other is not slot}
			said = {key: value for key, value in said.items() if value}
			if said:
				args = dict(pending.get("args") or {}, **said)
				asked = self._wait(intent, args, slot, pending.get("text") or "", pending.get("question") or "",
					[tuple(option) for option in pending.get("options") or []])
				return self._say(_("Noted.")) + asked
		if self._new_request(text, intent, slot, pending):
			# A request of its own («یک فاکتور برای خبازیان بزن ...»), not the answer to the question still open:
			# the question is dropped, nothing of it is carried over
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
		elif slot.get("choices"):
			choice = self._pick_option(text, pending.get("options") or []) or self._choice(slot, text, said_only=True)
			if not choice:
				return self._wait(intent, args, slot, pending.get("text") or "", slot.get("question") or _("Which one?"),
					[(key, label) for key, label in slot["choices"]])
			args[slot["arg"]] = choice
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

	def _new_request(self, text, intent, slot, pending):
		"""Whether a reply to a question is a request of its own: it still asks a command once the words of the
		record it names are taken out. «میز کار استیل ۱۴۵۶» names a product (its «کار» is not the tasks); «یک
		فاکتور برای خبازیان بزن ۱ عدد درب» asks an invoice of its own."""
		if self._pick_option(text, pending.get("options") or []):
			return False
		if slot and slot.get("text") and not nlu.action(text):
			# Words asked for («مشتری الف» to look for) are the answer, unless they ask something to be done
			return False
		new_intent, score, _ranked = self._match(text)
		if not new_intent or score < SURE:
			return False
		rest = nlu.normalize(text)
		if slot and slot.get("model") in self.env:
			found = self._search(slot["model"], text, intent)
			if found:
				name = Counter(nlu.name_words(found[0].display_name))
				kept = []
				for word in rest.split():
					if name[word] > 0:
						name[word] -= 1
					else:
						kept.append(word)
				rest = " ".join(kept)
		if not nlu.tokens(rest):
			return False
		again, score_again, _ranked = self._match(rest)
		return bool(again) and score_again >= SURE

	def _choice(self, slot, text, said_only=False, detect_only=False):
		"""The value of a choice said in the text («بدون مالیات»), else the one set for it (a setting, the page)"""
		words = f" {nlu.normalize(text)} "
		# Short answers («بله»، «نه») only as the reply to the question: in a request «نه» is nine
		answers = (slot.get("answers") or {}) if said_only and not detect_only else {}
		phrases = dict(slot.get("detect") or {}, **answers)
		for phrase, value in sorted(phrases.items(), key=lambda item: -len(item[0])):
			if f" {nlu.normalize(phrase)} " in words:
				return value
		if said_only:
			return None
		keys = {key for key, _label in slot["choices"]}
		if slot.get("param"):
			value = self.env["ir.config_parameter"].sudo().get_param(slot["param"])
			if value in keys:
				return value
		value = (slot.get("page_default") or {}).get(self.run.page_model or "")
		return value if value in keys else slot.get("default")

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
		for key, value in list(args.items()):
			if value == "$_me":
				# The person asking: a follow-up for themselves
				args[key] = self.user.id
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
					if self.dry:
						self._note_missing(slot)
						continue
					return self._wait(intent, args, slot, text, slot.get("question") or _("Send the file, please."))
				continue
			if slot.get("text"):
				value = self._rest(text, intent)
				if value:
					args[slot["arg"]] = value
				elif slot.get("required"):
					if self.dry:
						self._note_missing(slot)
						continue
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
			if slot.get("choices"):
				value = self._choice(slot, text)
				if value:
					args[slot["arg"]] = value
				elif slot.get("required"):
					if self.dry:
						self._note_missing(slot, [(key, label) for key, label in slot["choices"]])
						continue
					return self._wait(intent, args, slot, text, slot.get("question") or _("Which one?"),
						[(key, label) for key, label in slot["choices"]])
				continue
			if slot.get("ref"):
				# A document's number said in the request: «S00051»
				refs = nlu.refs(text)
				if refs:
					args[slot["arg"]] = refs[0]
				continue
			if slot.get("ahead"):
				# «فردا»، «سه روز دیگه»: in how many days
				days = nlu.days_ahead(text)
				if days is not None:
					args[slot["arg"]] = days
				continue
			if slot.get("number"):
				values = self._numbers(text, money=slot.get("money"))
				if values:
					args[slot["arg"]] = values[0]
				elif "default" in slot:
					args[slot["arg"]] = slot["default"]
				elif slot.get("required"):
					if self.dry:
						self._note_missing(slot)
						continue
					return self._wait(intent, args, slot, text, slot.get("question") or _("How many?"))
				continue
			record = self._record(slot, text, intent, args)
			if isinstance(record, Markup):
				return record
			other = args.get(slot.get("unless") or "")
			if record:
				args[slot["arg"]] = record.id
				self._keep_within(intent, slot, record)
			elif slot.get("required") and not (other and not (isinstance(other, str) and other.startswith("$"))):
				if self.dry:
					self._note_missing(slot)
					continue
				return self._wait(intent, args, slot, text, slot.get("question") or _("Which one?"), self._recent(slot))
		if self.dry and self.frame.get("missing"):
			self._note_args(intent, {k: v for k, v in args.items() if not (isinstance(v, str) and v.startswith("$"))})
			return Markup("")
		if self.run.page_filters and args.get("model") == self.run.page_model and "filters" in properties \
				and any(slot.get("page") for slot in intent._slots()):
			# «This section» is the list as the person sees it: the conditions of the page come along
			args["filters"] = list(args.get("filters") or []) + list(self.run.page_filters)
		if self.dry:
			self._note_args(intent, args)
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

	def _joined_names(self, text):
		"""Names of products and contacts with «و» or «+» in them that the request says («قلم و قلتک»، «لیزر و پانچ
		سلینمی»، «نصب و راه» of «نصب و راه‌اندازی»): those are not where one line ends and the next begins"""
		words = nlu.normalize(re.sub(r"\+", " + ", text or "")).split()
		names = []
		for index, word in enumerate(words):
			if word not in ("و", "+") or not 0 < index < len(words) - 1:
				continue
			pattern = nlu.like(f"{words[index - 1]} {word} {words[index + 1]}")
			for model in ("product.product", "res.partner"):
				if not pattern or model not in self.env:
					continue
				try:
					domain = self.agent._scope_domain(model, self.env)
				except registry.ToolDenied:
					continue
				field = self.env[model]._rec_name or "name"
				said = f"{words[index - 1]} {word} {words[index + 1]}"
				for record in self.env[model].search(domain & Domain(field, "=ilike", pattern), limit=20):
					name = nlu.normalize(record[field].replace("+", " + "))
					if f" {name} " in f" {' '.join(words)} ":
						names.append(name)
					elif f" {said}" in f" {name}":
						# The name said in part, up to a word after its «و» begun or whole
						names.append(said)
		# A contact's whole name after «برای» with words of the command in it («پیتزا معتمدی مشتری خبازیان»)
		for index, word in enumerate(words):
			if word not in nlu.PARTY_MARKERS or "res.partner" not in self.env:
				continue
			first = [w for w in words[index + 1:index + 4] if w not in nlu.NAME_STOP][:2]
			pattern = nlu.like(" ".join(first)) if first else None
			if not pattern:
				continue
			try:
				domain = self.agent._scope_domain("res.partner", self.env)
			except registry.ToolDenied:
				continue
			for record in self.env["res.partner"].search(domain & Domain("name", "=ilike", pattern), limit=50):
				name = nlu.normalize(record.name or "")
				if len(name.split()) > len(first) and f" {name} " in f" {' '.join(words)} ":
					names.append(name)
		return names

	def _line_said(self, said, properties):
		"""What is said of a line, as arguments its tool takes: «بدون تخفیف»، «با تخفیف همیشگی»، «۵ درصد تخفیف»،
		«به قیمت ۲ میلیون»"""
		values, text = {}, nlu.normalize(said)
		if not text:
			return values
		if "discount" in properties:
			percent = re.search(r"(\d+(?:\.\d+)?)\s*(?:درصد|%)", text)
			if re.search(r"\bبدون تخفیف\b", text):
				values["discount"] = 0.0
			elif percent and "تخفیف" in text:
				values["discount"] = float(percent.group(1))
			elif "discount_from_history" in properties and re.search(r"\bتخفیف\b.*\b(همیشگی|همیشه|قبلی|معمول|همیشگیش)\b", text):
				values["discount_from_history"] = True
		price = re.search(r"\b(?:قیمت|فی)\b(.*)", text)
		if "price_unit" in properties and price:
			amounts = nlu.amounts(price.group(1))
			if amounts:
				value, unit = amounts[0]
				values["price_unit"] = value * 10 if unit == "toman" else value
		return values

	def _lines(self, intent, args, text):
		"""The lines of an order said in one sentence («یک فاکتور برای خبازیان بزن ۱ عدد درب شیشه ای و ۱۰ عدد مهره
		m5 بدون تخفیف»), each found among the products; one that fits several is asked, one that is not a product is
		said so. Nothing goes to the tool until every line is found."""
		found = self._line_slots(intent)
		if not found:
			return None
		key, line, product_slot, count_slot = found
		model, arg = product_slot["model"], product_slot["arg"]
		default = (count_slot or {}).get("default", 1)
		count_arg = count_slot["arg"] if count_slot else None
		tool = registry.get(intent.tool_code)
		items = (((tool.schema or {}).get("properties") or {}).get(key) or {}).get("items") or {}
		properties = set((items.get("properties") or {}))
		made_before = args.get(key)
		if isinstance(made_before, list) and made_before and not any(isinstance(v, str) and v.startswith("$")
				for item in made_before for v in item.values()):
			# The lines were found before another question (the customer, the taxes): kept as they are
			self.party = args.get("_party")
			for item in made_before:
				self._take(self.env[model].browse(item.get(arg)).exists())
			self.in_lines = {arg} | ({count_arg} if count_arg else set())
			return None
		if "_parts" in args:
			parts, done = list(args["_parts"]), list(args.get("_lines") or [])
			self.party = args.get("_party")
			if isinstance(args.get(arg), int) and parts:
				# The answer to the line that was asked
				done.append(dict(parts[0], id=args.pop(arg)))
				args.pop(count_arg, None)
				parts = parts[1:]
		else:
			parsed = nlu.order_parts(text, intent._command_words(), self._joined_names(text))
			self.party = parsed["party"]
			parts = [part for part in parsed["lines"] if part["name"]]
			if not parts:
				return None
			done = []
		args["_party"] = self.party
		while parts:
			part = parts[0]
			records = self._search(model, part["name"], intent)
			if len(records) == 1:
				done.append(dict(part, id=records.id))
				parts = parts[1:]
				continue
			args.update(_parts=parts, _lines=done)
			if self.dry:
				self._note_missing(product_slot, [(record.id, record.display_name) for record in records[:6]])
				return Markup("")
			if records:
				options = [(record.id, record.display_name) for record in records[:6]]
				return self._wait(intent, args, product_slot, text, _("Which product for «%s»?", part["name"]) +
					self._more(records), options)
			# Not a product of the program: the nearest ones if any, never one put in its place
			near = self._search(model, part["name"], intent, loose=True)
			if near:
				options = [(record.id, record.display_name) for record in near[:6]]
				return self._wait(intent, args, product_slot, text, _("«%s» is not among the products. Is it one of "
					"these? If not, write its name or code as it is in the products.", part["name"]), options)
			return self._wait(intent, args, product_slot, text, _("«%s» was not found among the products of the "
				"program. Write its name or code as it is in the products; no invoice is made until then.", part["name"]))
		for key_ in ("_parts", "_lines"):
			args.pop(key_, None)
		if not done:
			return None
		for item in done:
			self._take(self.env[model].browse(item["id"]).exists())

		def made(item):
			values = {k: (item["id"] if v == "$" + arg else (item["count"] or default) if count_arg and v == "$" + count_arg
				else v) for k, v in line.items()}
			values.update(self._line_said(item.get("said") or "", properties))
			return values

		args[key] = [made(item) for item in done]
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
			records = self._search(slot["model"], nlu.after(text, slot["after"]) if slot.get("after") else text, intent)
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
		if self.dry:
			self.frame["args"] = args
			return Markup("")
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
		self._offer_open(intent, run)
		if intent._args().get("_open"):
			# «باز کن»: what was found is opened at once
			for option in self.options:
				if option.get("res_model"):
					option["auto"] = True
					break
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

	def _offer_open(self, intent, run):
		"""The records an answer is about, to open as a list (or a form) in the program; remembered for «بازش کن»"""
		from ..services import contracts

		links = run.sudo().link_ids
		if not links:
			return
		model = links[0].res_model
		ids = links.filtered(lambda link: link.res_model == model).mapped("res_id")[:80]
		self.memory["opened"] = {"model": model, "ids": ids}
		item = contracts.contract(intent.tool_code) or {}
		if item.get("result") in ("answer", "report"):
			label = _("Open in the Program") if len(ids) > 1 else _("Open It")
			option = {"label": label, "res_model": model}
			option.update({"ids": ids} if len(ids) > 1 else {"res_id": ids[0]})
			self.options.append(option)

	def _open_last(self):
		"""«بازش کن»: the records of the last answer opened in the program"""
		opened = self.memory.get("opened") or {}
		if not opened.get("ids") or opened.get("model") not in self.env:
			return None
		ids = self.env[opened["model"]].browse(opened["ids"]).exists().ids
		if not ids:
			return None
		option = {"label": _("Open in the Program") if len(ids) > 1 else _("Open It"), "res_model": opened["model"],
			"auto": True}
		option.update({"ids": ids} if len(ids) > 1 else {"res_id": ids[0]})
		self.options = [option]
		return self._say(_("Opened in the program."))

	def _remember(self, output):
		if not isinstance(output, dict):
			return
		if output.get("draft_id"):
			self.memory.setdefault("records", {})["account.move"] = output["draft_id"]
			self.options = [{"label": _("Open the Draft"), "res_model": "account.move", "res_id": output["draft_id"]}] + [
				option for option in self.options if option.get("res_model") != "account.move"]
			# The next step of a draft invoice: posting it, which waits for an approval
			post = self.env["veron.ai.intent"].sudo().search([("code", "=", "invoice_post")], limit=1)
			if post and post._usable(self.user) and self.agent.sudo()._grant(post.tool_code):
				self.options.append({"code": post.code, "label": post.name})

	def _wait(self, intent, args, slot, text, question, options=None):
		if self.dry:
			self._note_missing(slot, options)
			self._note_args(intent, {k: v for k, v in args.items() if not (isinstance(v, str) and v.startswith("$"))})
			return Markup("")
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
		if slot.get("after"):
			# A record of a role in the request: «از انبار مرکزی» is the source, «به شعبه» the destination
			text = nlu.after(text, slot["after"])
		if model in PEOPLE and self.party:
			# The party of an order said apart: only its words are read, and all of them
			found = self._search(model, self.party, intent, untaken=True)
			if len(found) == 1:
				self.memory.setdefault("records", {})[model] = found.id
				return found
			if found:
				if self.dry:
					self._note_missing(slot, [(record.id, record.display_name) for record in found[:6]])
					return None
				return self._ask(intent, args, slot, found, text)
			near = self._search(model, self.party, intent, loose=True, untaken=True)
			if near and not self.dry:
				return self._wait(intent, args, slot, text, _("«%s» is not among the contacts. Is it one of these?",
					self.party), [(record.id, record.display_name) for record in near[:6]])
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
			if self.dry:
				self._note_missing(slot, [(record.id, record.display_name) for record in found[:6]])
				return None
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

	def _search(self, model, text, intent, loose=False, untaken=False):
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
		# The words of a party said apart («برای پیتزا خبازیان») are all its own, even those a product also has
		left_out = Counter() if untaken else self.taken + (self.not_people if model in PEOPLE else Counter())
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
			if score >= 1 or score >= 0.8 and size == 1 or loose and score >= 0.5:
				ranked.append((score, hit / size if size else 0, record))
		if not ranked:
			return Model.browse()
		if loose:
			# The nearest, to choose from; none is taken in place of what was said
			ranked.sort(key=lambda item: (-item[0], -item[1], item[2].id))
			return Model.browse([item[2].id for item in ranked[:6]])
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
		taken = Counter(self.taken)
		words = []
		for w in nlu.normalize(text).split():
			if taken[w] > 0:
				# The name of the record it is about is not part of the text: «برای حسن پور» of «تماس بگیرم»
				taken[w] -= 1
			elif w not in nlu.STOP and nlu.stem(w) not in intent_words and w not in nlu.MARKERS:
				words.append(w)
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

	# A value asked only to be put inside another argument (the product and quantity of a line, the contact of «id»)
	# is not an argument of its own
	inner = set()
	for k, v in args.items():
		if isinstance(v, (dict, list)):
			used(v, inner)
		elif isinstance(v, str) and v.startswith("$") and v[1:] != k:
			inner.add(v[1:])
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
	def _analyze(self, text, agent=None, page=None, conversation=None):
		"""How the built-in assistant reads a request for the current person, without doing it (see Brain.analyze):
		for tests, and to see why a request was understood the way it was"""
		agent = agent or self.env.ref("veron_ai_agent.agent_assistant")
		if not agent._may_use(self.env.user):
			raise AccessError(_("You may not use %s.", agent.name))
		page = self.env["veron.ai.conversation"]._page(page) or {}
		run = self.sudo().new({"agent_id": agent.id, "conversation_id": conversation.id if conversation else False,
			"page_model": page.get("model") or False, "page_res_id": page.get("res_id") or 0,
			"page_title": page.get("title") or False, "page_filters": page.get("filters") or False})
		return Brain(run, self.env).analyze(text or "")

	@api.model
	def _render_results(self, results):
		parts = []
		for key, output in results.items():
			code = key.split(". ", 1)[-1]
			tool = registry.get(code)
			title = tool.label(self.env) if tool else code
			parts.append(Markup("<h5>%s</h5>%s") % (title, render.answer(code, output)))
		return Markup("").join(parts)
