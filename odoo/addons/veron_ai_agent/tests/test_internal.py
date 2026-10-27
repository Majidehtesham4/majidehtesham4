"""The built-in assistant, without any AI: its Persian reading of a request, its memory of the conversation, the
choices it offers and learns, the person's own rights, and the files it reads"""

import io
from datetime import date

from odoo.tests import tagged

from ..services import nlu, render, sheets
from .common import AgentCase, FakeAdapter


def workbook(rows):
	from openpyxl import Workbook

	book = Workbook()
	for row in rows:
		book.active.append(row)
	buffer = io.BytesIO()
	book.save(buffer)
	return buffer.getvalue()


@tagged("post_install", "-at_install")
class TestNlu(AgentCase):
	def test_normalize_and_numbers(self):
		self.assertEqual(nlu.normalize("فاكتورهاي ۱۲ ماه‌ قبل؟"), nlu.normalize("فاکتورهای 12 ماه قبل"))
		self.assertEqual(nlu.words_number("سه میلیون و پانصد هزار".split()), 3_500_000)
		self.assertIn(2_000_000, [value for value, _unit in nlu.amounts("مبلغ ۲,۰۰۰,۰۰۰ ریال")])

	def test_periods(self):
		today = date(2026, 10, 27)  # 5 Aban 1405
		self.assertEqual(nlu.period("فروش دیروز", today)[:2], (date(2026, 10, 26), date(2026, 10, 26)))
		start, end = nlu.period("ماه قبل", today)[:2]
		self.assertEqual((start, end), (date(2026, 9, 23), date(2026, 10, 22)))  # Mehr 1405
		self.assertFalse(nlu.period("مشتری الف", today))

	def test_only_context(self):
		self.assertTrue(nlu.only_context("و ماه قبل؟"))
		self.assertTrue(nlu.only_context("پارسال چی"))
		self.assertFalse(nlu.only_context("هزینه‌های این ماه"))
		self.assertFalse(nlu.only_context(""))

	def test_render(self):
		html = str(render.answer("records_search", {"count": 0, "records": []}))
		self.assertIn("موردی پیدا نشد", html)
		self.assertIn("1405/08/05", render.shamsi("2026-10-27"))
		self.assertNotIn("draft_id", str(render.value_html({"draft_id": 7, "total": 1000})))


@tagged("post_install", "-at_install")
class TestBuiltInAssistant(AgentCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.assistant = cls.env.ref("veron_ai_agent.agent_assistant")
		cls.env["veron.ai.agent"]._setup_assistant()
		cls.assistant.write({"enabled": True, "company_ids": [(4, cls.company_b.id)]})

	def chat(self, user=None):
		Chat = self.env["veron.ai.conversation"].with_user(user or self.user)
		opened = Chat.veron_chat_assistant()
		self.assertTrue(opened, "every internal user with the AI user group has the assistant")
		return Chat, opened["conversation_id"]

	def say(self, Chat, conversation, text, sources=(), page=None):
		replies = Chat.veron_chat_send(conversation, text, list(sources), {}, "internal", page)
		self.assertEqual(replies[0]["role"], "user")
		return replies[-1]

	def test_no_ai_is_called(self):
		Chat, conversation = self.chat()
		reply = self.say(Chat, conversation, "سلام")
		self.assertEqual(reply["engine"], "internal")
		self.assertFalse(FakeAdapter.calls, "the built-in assistant never calls a language model")
		reply = self.say(Chat, conversation, "چه کارهایی بلدی؟")
		self.assertIn("فروش", reply["body_html"])

	def test_contact_search_with_the_persons_rights(self):
		Chat, conversation = self.chat()
		reply = self.say(Chat, conversation, "مخاطب «مشتری الف» را پیدا کن")
		self.assertIn("مشتری الف", reply["body_html"])
		# A contact of a company the person does not have is not found for them, though the assistant has that company
		reply = self.say(Chat, conversation, "مخاطب «مشتری ب» را پیدا کن")
		self.assertNotIn("مشتری ب<", reply["body_html"])
		run = self.env["veron.ai.run"].browse(reply["run"]["id"])
		self.assertEqual(run.initiator_user_id, self.user)
		self.assertEqual(run.step_ids.mapped("origin"), ["internal"])

	def test_asks_for_what_is_missing_then_remembers(self):
		Chat, conversation = self.chat()
		reply = self.say(Chat, conversation, "مخاطب را پیدا کن")
		self.assertIn("جست‌وجو", reply["body_html"], "it asks what to look for")
		reply = self.say(Chat, conversation, "مشتری الف")
		self.assertIn("مشتری الف", reply["body_html"])
		memory = self.env["veron.ai.conversation"].browse(conversation).memory
		self.assertEqual(memory["last"]["intent"], "contact_find")
		self.assertFalse(memory.get("pending"))

	def test_follow_up_keeps_the_subject(self):
		Chat, conversation = self.chat(self.manager)
		reply = self.say(Chat, conversation, "فروش ماه قبل چقدر بود")
		first = self.env["veron.ai.run"].browse(reply["run"]["id"])
		self.assertEqual(first.step_ids.tool_code, "sales_summary")
		reply = self.say(Chat, conversation, "و این ماه؟")
		second = self.env["veron.ai.run"].browse(reply["run"]["id"])
		self.assertEqual(second.step_ids.tool_code, "sales_summary", "«و این ماه؟» asks the same again for this month")
		self.assertNotEqual(first.step_ids.args_json, second.step_ids.args_json)

	def test_unsure_offers_choices_and_learns_the_choice(self):
		Intent = self.env["veron.ai.intent"]
		Intent.create({"code": "test_report_a", "name": "گزارش آزمایشی الف", "phrases": "گزارش ویژه شعبه",
			"answer": "<p>پاسخ الف</p>"})
		Intent.create({"code": "test_report_b", "name": "گزارش آزمایشی ب", "phrases": "گزارش ویژه انبار",
			"answer": "<p>پاسخ ب</p>"})
		Chat, conversation = self.chat()
		reply = self.say(Chat, conversation, "گزارش ویژه")
		codes = [option.get("code") for option in reply["options"]]
		self.assertIn("test_report_a", codes, "two meanings as likely: it asks")
		self.assertIn("test_report_b", codes)
		option = next(o for o in reply["options"] if o["code"] == "test_report_b")
		reply = self.say(Chat, conversation, f"#intent:{option['code']}")
		self.assertIn("پاسخ ب", reply["body_html"])
		phrase = self.env["veron.ai.intent.phrase"].search([("intent_id.code", "=", "test_report_b"), ("text", "=", "گزارش ویژه")])
		self.assertTrue(phrase, "the meaning picked is learned for this person")
		self.assertFalse(phrase.approved)
		reply = self.say(Chat, conversation, "گزارش ویژه")
		self.assertIn("پاسخ ب", reply["body_html"], "next time the learned phrase decides")
		other_chat, other_conversation = self.chat(self.other)
		reply = self.say(other_chat, other_conversation, "گزارش ویژه")
		self.assertTrue(reply["options"], "an unapproved phrase is only for the person who taught it")
		message = self.env["veron.ai.message"].search([("conversation_id", "=", conversation), ("role", "=", "user")],
			order="id desc", limit=1)
		self.assertFalse(message.body.startswith("#intent"), "the choice is kept in words")

	def test_not_for_people_outside_the_group(self):
		outsider = self.env["res.users"].create({"name": "بیرونی", "login": "outsider_ai",
			"group_ids": [(6, 0, self.env.ref("base.group_user").ids)]})
		Chat = self.env["veron.ai.conversation"]
		self.assertFalse(Chat.with_user(outsider)._assistant_shown())
		self.assertTrue(Chat.with_user(self.user)._assistant_shown())

	def test_spreadsheet_read_and_import_with_approval(self):
		data = workbook([["نام", "تلفن", "شهر"], ["شرکت البرز", "02144556677", "تهران"], ["فروشگاه کاوه", "03133445566", "اصفهان"]])
		rows = sheets.read(data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")["Sheet"]
		self.assertEqual(rows[1], ["شرکت البرز", "02144556677", "تهران"], "a phone keeps its leading zero; no empty columns")
		Source = self.env["veron.ai.source"].with_user(self.user)
		Chat, conversation = self.chat()
		source = Source._from_upload("contacts.xlsx", data)
		self.assertEqual(source.kind, "sheet")
		reply = self.say(Chat, conversation, "این فایل اکسل را بخوان", [source.id])
		self.assertIn("شرکت البرز", reply["body_html"])
		self.assertNotIn("col4", reply["body_html"])
		source = Source._from_upload("contacts.xlsx", data)
		reply = self.say(Chat, conversation, "مخاطبان این فایل را وارد کن", [source.id])
		self.assertTrue(reply["pending"], "adding records waits for an approval")
		approval = reply["pending"][0]
		self.assertTrue(approval["can_decide"], "the person who asked may approve a tool that allows it")
		self.assertFalse(self.env["res.partner"].search([("name", "=", "شرکت البرز")]))
		decided = Chat.veron_chat_decide(conversation, approval["id"], True)
		self.assertIn("فروشگاه کاوه", decided[0]["body_html"])
		self.assertFalse(decided[0]["pending"])
		partner = self.env["res.partner"].search([("name", "=", "شرکت البرز")])
		self.assertEqual(partner.phone, "02144556677")
		self.assertEqual(partner.create_uid, self.user, "done with the rights of the person who approved")

	def test_conversation_belongs_to_its_person(self):
		Chat, conversation = self.chat()
		Other = self.env["veron.ai.conversation"].with_user(self.other)
		with self.assertRaises(Exception):
			Other.veron_chat_send(conversation, "سلام", [], {}, "internal")
		new = Chat.veron_chat_new(self.assistant.id)
		self.assertNotEqual(new["conversation_id"], conversation)
		self.assertEqual(Chat.veron_chat_assistant()["conversation_id"], new["conversation_id"])
