"""The operations of the built-in assistant, from the code: every tool has a contract and a way to reach it, every
command is understood however it is written, and a conversation goes on where it should and nowhere else. No AI is
called: everything here is the assistant's own reading."""

from odoo.tests import tagged

from ..services import contracts, nlu, registry
from .common import AgentCase, FakeAdapter


def variants(phrase):
	"""The ways a person may write a phrase of the library"""
	words = phrase.split()
	longest = max(range(len(words)), key=lambda i: len(words[i]))
	typo = list(words)
	if len(typo[longest]) > 4:
		typo[longest] = typo[longest][:-2] + typo[longest][-1] + typo[longest][-2]
	return {
		"as written": phrase,
		"Arabic letters": phrase.replace("ی", "ي").replace("ک", "ك"),
		"polite and colloquial": f"لطفا {phrase} رو بگو",
		"half-spaces": phrase.replace(" ", "‌", 1) if len(words) > 2 else phrase,
		"one typo": " ".join(typo),
		"other order": " ".join(words[1:] + words[:1]) if len(words) > 2 else phrase,
	}


@tagged("post_install", "-at_install")
class TestContracts(AgentCase):
	def test_every_tool_has_a_contract(self):
		missing = sorted(set(registry.TOOLS) - set(contracts.CONTRACTS))
		self.assertFalse(missing, "tools without a contract")
		stale = sorted(set(contracts.CONTRACTS) - set(registry.TOOLS))
		self.assertFalse(stale, "contracts of tools that are gone")
		for code, item in contracts.CONTRACTS.items():
			self.assertIn(item[0], contracts.DOMAINS, code)
			self.assertIn(item[1], contracts.RESULTS, code)

	def test_the_contract_follows_the_tool(self):
		for code, tool in registry.TOOLS.items():
			result = contracts.contract(code)["result"]
			if tool.sensitive and result != "agent":
				self.assertEqual(result, "approval", f"{code} is sensitive: it waits for a person")
			if tool.action == "draft" and result != "agent":
				self.assertEqual(result, "form", f"{code} makes a draft: its form is opened")
			properties = dict((tool.schema or {}).get("properties") or {})
			for value in list(properties.values()):
				# The arguments of a line of a list (the products of an invoice)
				properties.update(((value.get("items") or {}).get("properties") or {}) if isinstance(value, dict) else {})
			for name in contracts.contract(code)["never_guessed"]:
				if name in properties:
					continue
				self.assertIn(name, ("amounts", "rates"), f"{code}: «{name}» is not an argument of the tool")

	def test_every_tool_for_people_has_a_command(self):
		catalog = contracts.catalog(self.env)
		self.assertFalse(catalog["commands_without_tool"])
		gaps = [row["code"] for row in catalog["tools"] if "no command of the assistant reaches it" in row["gaps"]]
		self.assertFalse(gaps, "tools for people that no command reaches")


@tagged("post_install", "-at_install")
class TestUnderstanding(AgentCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env["veron.ai.agent"]._setup_assistant()
		cls.assistant = cls.env.ref("veron_ai_agent.agent_assistant")
		cls.assistant.write({"enabled": True})
		cls.admin = cls.env.ref("base.user_admin")
		cls.Run = cls.env["veron.ai.run"].with_user(cls.admin)

	def analyze(self, text, page=None):
		return self.Run._analyze(text, self.assistant, page)

	def test_every_command_however_written(self):
		"""Each phrase of the library, written in other ways, is the same command, or a question between it and
		another; never another command taken for sure"""
		wrong, asked, checked = [], [], 0
		for intent in self.env["veron.ai.intent"].search([]):
			if not intent.tool_code or not intent._usable(self.admin):
				continue
			if any(slot.get("page") and slot.get("required") for slot in intent._slots()):
				continue
			phrase = next((p for p in (intent.phrases or "").splitlines() if p.strip()), None)
			if not phrase:
				continue
			for way, text in variants(phrase).items():
				checked += 1
				frame = self.analyze(text)
				if frame["intent"] == intent.code:
					continue
				codes = [code for code, _score in frame["candidates"]]
				if frame["intent"] is None and intent.code in codes:
					asked.append((intent.code, way))
				else:
					wrong.append((intent.code, way, text, frame["intent"], codes))
		self.assertFalse([w for w in wrong if w[1] in ("as written", "Arabic letters", "half-spaces")], wrong)
		# A typo or another order may be asked about; taken for another command only rarely
		self.assertLessEqual(len(wrong), checked // 20, wrong)

	def test_the_parts_of_a_request(self):
		frame = self.analyze("فروش ماه قبل چقدر بود")
		if "sale.order" in self.env:
			self.assertEqual((frame["intent"], frame["action"], frame["response"]), ("sales_summary", "report", "report"))
			self.assertEqual(frame["period"]["label"], "ماه گذشته")
		frame = self.analyze("قورباغه آبی پرواز کرد")
		self.assertIsNone(frame["intent"])
		self.assertIn("intent", frame["missing"])
		self.assertEqual(nlu.action("این ردیف را حذف کن"), "delete")
		self.assertEqual(nlu.action("قیمتش را عوض کن"), "edit")
		self.assertIn("customer", nlu.subjects("مطالبات مشتری حسن"))
		self.assertEqual(nlu.after("۵ عدد از انبار مرکزی به انبار شعبه منتقل کن", ["از"]), "انبار مرکزی")
		self.assertEqual(nlu.after("۵ عدد از انبار مرکزی به انبار شعبه منتقل کن", ["به"]), "انبار شعبه منتقل کن")
		self.assertEqual(nlu.days_ahead("فردا تماس بگیر"), 1)
		self.assertEqual(nlu.days_ahead("۳ روز دیگه"), 3)

	def test_a_name_that_is_not_there(self):
		frame = self.analyze("خلاصه مشتری زرافه‌ی ناموجود")
		self.assertEqual(frame["intent"], "customer_summary")
		self.assertIn("partner_id", frame["missing"])
		self.assertFalse(frame["entities"])


@tagged("post_install", "-at_install")
class TestConversation(AgentCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env["veron.ai.agent"]._setup_assistant()
		cls.env.ref("veron_ai_agent.agent_assistant").write({"enabled": True, "company_ids": [(4, cls.env.company.id)]})
		cls.env["res.partner"].create([{"name": f"مشتری صفحه {n:02d}"} for n in range(1, 31)])

	def setUp(self):
		super().setUp()
		FakeAdapter.calls = []

	def chat(self, user=None):
		Chat = self.env["veron.ai.conversation"].with_user(user or self.user)
		return Chat, Chat.veron_chat_new(self.env.ref("veron_ai_agent.agent_assistant").id)["conversation_id"]

	def say(self, Chat, conversation, text):
		return Chat.veron_chat_send(conversation, text, [], {}, "internal")[-1]

	def test_next_page_and_open(self):
		Chat, conversation = self.chat()
		reply = self.say(Chat, conversation, "مخاطب «مشتری صفحه» را پیدا کن")
		first = self.env["veron.ai.run"].browse(reply["run"]["id"]).link_ids.mapped("res_id")
		self.assertEqual(len(first), 10, reply["body_html"])
		self.assertTrue(any(option.get("ids") for option in reply["options"]), "the records open as a list")
		reply = self.say(Chat, conversation, "بعدی")
		second = self.env["veron.ai.run"].browse(reply["run"]["id"]).link_ids.mapped("res_id")
		self.assertTrue(second and not set(first) & set(second), "the next page, not the same records again")
		reply = self.say(Chat, conversation, "بازش کن")
		auto = [option for option in reply["options"] if option.get("auto")]
		self.assertTrue(auto and set(auto[0]["ids"]) == set(second), reply["body_html"])
		self.assertFalse(FakeAdapter.calls, "no AI is called")

	def test_a_new_request_in_the_middle(self):
		Chat, conversation = self.chat()
		self.say(Chat, conversation, "مخاطب را پیدا کن")
		memory = self.env["veron.ai.conversation"].browse(conversation).memory
		self.assertEqual(memory["pending"]["intent"], "contact_find")
		reply = self.say(Chat, conversation, "چه کارهایی بلدی؟")
		self.assertNotIn("مخاطب", reply["body_html"][:40])
		self.say(Chat, conversation, "مشتری صفحه ۰۳")
		memory = self.env["veron.ai.conversation"].browse(conversation).memory
		self.assertEqual(memory["last"]["intent"], "contact_find", "the answer goes back to the question asked")

	def test_open_with_nothing_before(self):
		Chat, conversation = self.chat()
		reply = self.say(Chat, conversation, "بازش کن")
		self.assertFalse([option for option in reply["options"] if option.get("auto")])

	def test_follow_up_activity(self):
		partner = self.env["res.partner"].search([("name", "=", "مشتری صفحه 07")])
		# Someone who may not change contacts may not put a follow-up on one either: Odoo's rights decide
		Chat, conversation = self.chat(self.other)
		reply = self.say(Chat, conversation, "برای مشتری صفحه 07 یادآوری بساز که فردا تماس بگیرم")
		self.assertFalse(self.env["mail.activity"].search([("res_model", "=", "res.partner"), ("res_id", "=", partner.id)]))
		Chat, conversation = self.chat(self.user)
		reply = self.say(Chat, conversation, "برای مشتری صفحه 07 یادآوری بساز که فردا تماس بگیرم")
		activity = self.env["mail.activity"].search([("res_model", "=", "res.partner"), ("res_id", "=", partner.id)])
		self.assertEqual(len(activity), 1, reply["body_html"])
		self.assertEqual(activity.user_id, self.user, "for the person who asked")
		self.assertIn("تماس", activity.summary)
		self.assertNotIn("صفحه", activity.summary, "the name of the contact is not the summary")

	def test_transfer_between_warehouses(self):
		if "stock.picking" not in self.env:
			self.skipTest("Inventory is not installed here")
		Warehouse = self.env["stock.warehouse"]
		main = Warehouse.search([("company_id", "=", self.env.company.id)], limit=1)
		branch = Warehouse.create({"name": "انبار شعبه آزمون", "code": "TSB", "company_id": self.env.company.id})
		product = self.env["product.product"].create({"name": "کالای انتقالی آزمون", "is_storable": True})
		frame = self.env["veron.ai.run"]._analyze(f"۵ عدد کالای انتقالی آزمون از انبار {main.name} به انبار شعبه آزمون منتقل کن")
		self.assertEqual(frame["intent"], "stock_transfer_draft")
		self.assertEqual((frame["entities"]["from_warehouse_id"]["id"], frame["entities"]["to_warehouse_id"]["id"]),
			(main.id, branch.id), "«از» is the source and «به» the destination")
		self.assertEqual((frame["entities"]["product_id"]["id"], frame["values"]["quantity"]), (product.id, 5))
		self.assertEqual(frame["response"], "form")
		frame = self.env["veron.ai.run"]._analyze("کالای انتقالی آزمون را منتقل کن")
		self.assertIn("quantity", frame["missing"], "a count is never guessed")
