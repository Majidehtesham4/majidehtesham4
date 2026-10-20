"""A request the matcher is not sure of is read by the AI model into a capability, in the
background and without the user asking for the AI model; the capability runs on the ERP. What is
learned is a proposed example, approved only after it is checked."""

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from iran_erp.ai.openrouter import AIError
from iran_erp.commands import learning
from iran_erp.commands.engine import get_matcher, handle

UNKNOWN = "پول‌هایی که دست مردم داریم رو جمع بزن"
SETTINGS = frappe._dict(model="stub", max_steps=4, instructions="", provider="Stub", timeout=None)


def reply(content, tokens=10):
	return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": tokens}}


def reading(**values):
	data = {"capability": None, "parameters": {}, "confidence": 0.9, "alternatives": [], "conversation": False, "reason": ""}
	return reply("```json\n" + json.dumps({**data, **values}, ensure_ascii=False) + "\n```")


class TestUnderstand(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.local.lang = "fa"
		frappe.db.set_single_value("Iran AI Settings", {"enabled": 1, "commands_enabled": 1})
		frappe.clear_document_cache("Iran AI Settings", "Iran AI Settings")
		self.patches = [
			patch("iran_erp.ai.openrouter.has_api_key", return_value=True),
			patch("iran_erp.ai.openrouter.get_settings", return_value=SETTINGS),
			patch("iran_erp.ai.assistant.get_settings", return_value=SETTINGS),
			# The background job and its commits run here, inside the test's transaction
			patch("iran_erp.ai.api.frappe.enqueue"),
			patch.object(frappe.db, "commit"),
		]
		for p in self.patches:
			p.start()
		from iran_erp.commands.engine import reset_matcher

		reset_matcher()

	def tearDown(self):
		for p in self.patches:
			p.stop()
		frappe.db.rollback()
		frappe.clear_document_cache("Iran AI Settings", "Iran AI Settings")
		from iran_erp.commands.engine import reset_matcher

		reset_matcher()

	def ask(self, question, model, previous=None):
		"""The chat's request, then its background job, with the AI model answering `model`."""
		from iran_erp.ai.api import ask
		from iran_erp.ai.assistant import run_request

		name = ask(question, previous_request=previous)
		with patch("iran_erp.ai.openrouter.chat_completion", model), patch("iran_erp.ai.assistant.chat_completion", model):
			if frappe.db.get_value("Iran AI Request", name, "status") == "Queued":
				run_request(name)
		return frappe.get_doc("Iran AI Request", name)

	def test_unsure_request_is_read_by_the_ai_model_and_run_on_the_erp(self):
		self.assertTrue(handle(UNKNOWN, None, ai_available=True).get("understand"))
		model = MagicMock(return_value=reading(capability="receivables", confidence=0.92))
		request = self.ask(UNKNOWN, model)
		self.assertEqual(request.status, "Done")
		self.assertEqual(request.handled_by, "Command")
		self.assertEqual(request.understood_by, "AI Interpreter")
		self.assertEqual(request.intent, "receivables")
		trace = json.loads(request.trace)
		self.assertEqual(trace["capability"], "receivables")
		self.assertEqual(trace["handler"], "accounts.receivables")
		self.assertTrue(any("Accounts%20Receivable" in link for link in trace["links"]))
		# One call to read it; no tools, no answer written by the model
		self.assertEqual(model.call_count, 1)
		self.assertNotIn("tools", model.call_args.kwargs)
		self.assertIsNone(model.call_args.args[2] if len(model.call_args.args) > 2 else None)

		# Learned as a proposed example: checked on the ERP, not yet used
		example = frappe.get_doc("Iran Intent Example", {"capability": "receivables", "phrase": learning.general_form(UNKNOWN)})
		self.assertEqual(example.status, "Proposed")
		self.assertEqual(example.evaluation, "Passed")
		self.assertEqual(example.tool, "accounts.receivables → GL Entry balances of customers; report Accounts Receivable")
		# The answer and its figures are not kept
		for value in example.as_dict().values():
			self.assertNotIn(request.answer, str(value))

		# Read the same way again: approved, and then understood without the AI model
		self.ask(UNKNOWN, MagicMock(return_value=reading(capability="receivables", confidence=0.92)))
		self.assertEqual(frappe.db.get_value("Iran Intent Example", example.name, "status"), "Approved")
		model = MagicMock()
		request = self.ask(UNKNOWN, model)
		model.assert_not_called()
		self.assertEqual((request.understood_by, request.intent), ("Matcher", "receivables"))

		# «Not right» rejects it: the matcher forgets it
		learning.unlearn("receivables", UNKNOWN)
		self.assertEqual(frappe.db.get_value("Iran Intent Example", example.name, "status"), "Rejected")
		ranked = get_matcher().rank(learning.general_form(UNKNOWN))
		self.assertFalse(ranked and ranked[0][0] == "receivables" and ranked[0][1] > 0.9)

	def test_details_read_by_the_ai_model_become_records(self):
		customer = frappe.db.get_value("Customer", {"disabled": 0}, ["name", "customer_name"], as_dict=True)
		if not customer:
			self.skipTest("no customer")
		question = "یه نگاه به فاکتورای اون مشتریمون بنداز " + customer.customer_name
		model = MagicMock(
			return_value=reading(capability="last_sales_invoices", parameters={"customer": customer.customer_name}, confidence=0.9)
		)
		with patch("iran_erp.commands.engine._handle", return_value=handle(UNKNOWN, None, ai_available=True)):
			request = self.ask(question, model)
		trace = json.loads(request.trace)
		self.assertEqual(request.understood_by, "AI Interpreter")
		self.assertEqual(trace["parameters"].get("customer"), customer.name)
		self.assertEqual(trace["reading"]["parameters"], {"customer": customer.customer_name})

	def test_unsure_reading_asks_and_needs_review(self):
		model = MagicMock(
			return_value=reading(capability="receivables", confidence=0.5, alternatives=["cash_position"], reason="مردم؟")
		)
		request = self.ask(UNKNOWN, model)
		state = json.loads(request.command_state)
		self.assertEqual(state["choose"][:2], ["receivables", "cash_position"])
		example = frappe.get_doc("Iran Intent Example", {"capability": "receivables"})
		self.assertEqual(example.status, "Needs Review")
		self.assertIn("cash_position", example.alternatives)
		# The user's choice runs the capability; the example still waits for an administrator
		answer = self.ask("1", MagicMock(), previous=request.name)
		self.assertEqual((answer.intent, answer.understood_by), ("receivables", "User Choice"))
		self.assertEqual(frappe.db.get_value("Iran Intent Example", example.name, "status"), "Needs Review")

	def test_conversation_goes_to_the_ai_assistant(self):
		question = "چرا فروش این ماه کم شده"

		def model(settings, messages, tools=None):
			if tools:
				return reply("فروش این ماه را بررسی کردم.")
			return reading(conversation=True, reason="analysis")

		request = self.ask(question, MagicMock(side_effect=model))
		self.assertEqual((request.status, request.handled_by), ("Done", "AI"))
		self.assertEqual(json.loads(request.trace)["reading"]["conversation"], True)
		self.assertFalse(frappe.db.exists("Iran Intent Example", {"phrase": learning.general_form(question)}))

	def test_no_ai_model_gives_the_matchers_answer(self):
		request = self.ask(UNKNOWN, MagicMock(side_effect=AIError("down")))
		self.assertEqual(request.status, "Done")
		self.assertEqual(request.understood_by, "Matcher")
		self.assertTrue(json.loads(request.command_state).get("choose"))
		self.assertIn("down", json.loads(request.trace)["ai_error"])

	def test_drafts_and_rivals_are_never_approved_alone(self):
		phrase = "یه مشتری تازه برامون ثبت کن به اسم بهرام نیکان"
		for _time in range(3):
			name = learning.propose("create_customer", phrase, {"name": "بهرام نیکان"}, "AI Interpreter", 0.95)
		doc = frappe.get_doc("Iran Intent Example", name)
		self.assertEqual(doc.status, "Proposed")
		self.assertEqual(doc.times_seen, 3)
		self.assertIn("draft", doc.evaluation_notes)
		# A wording another capability already owns is not given to this one
		name = learning.propose("car_stock", "مانده حساب مشتری ها رو بده لطفا", {}, "AI Interpreter", 0.95)
		self.assertEqual(frappe.db.get_value("Iran Intent Example", name, "evaluation"), "Failed")
		# No capability fits: kept for an administrator
		name = learning.propose(None, "برای مشتری‌ها پیامک تبریک عید بفرست", review="no capability")
		self.assertEqual(frappe.db.get_value("Iran Intent Example", name, "status"), "Needs Review")

	def test_passwords_are_not_kept(self):
		learning.propose(
			"set_user_password",
			"میشه لطفا گذرواژه همکارمون sara.test رو بکنی Other-99999",
			{"user": "sara.test", "password": "Other-99999"},
		)
		learning.learn("create_user_login", "یه کاربر حسابدار جدید با یوزر ali.test و پسورد Ali-55555 بساز لطفا")
		for row in frappe.get_all("Iran Intent Example", fields=["phrase", "parameters"]):
			# The login a password is changed for is a detail; the password and a new username are not kept
			for secret in ("Other-99999", "Ali-55555", "ali.test"):
				self.assertNotIn(secret, f"{row.phrase} {row.parameters}")
		self.assertTrue(frappe.db.exists("Iran Intent Example", {"capability": "set_user_password"}))

	def test_reading_is_limited_to_the_catalog_and_continues_the_previous_answer(self):
		from iran_erp.commands.understand import _parse, answer

		# Unknown result values and tool names are dropped, never run
		parsed = _parse(json.dumps({"capability": "drop_table", "result": {"output": "sql", "group_by": "branch", "limit": 5000}}))
		self.assertEqual(parsed["result"], {"group_by": "branch"})
		self.assertIsNone(answer("هرچی", None, parsed))
		# «یه چند تای دیگه هم نشون بده» read as «more»: the next cars of the same ranking
		first = handle("کدوم ماشین‌ها بیشترین زمان رو تو پارکینگ موندن؟")
		if not first["state"].get("shown"):
			self.skipTest("no cars")
		reading = _parse(json.dumps({"capability": "car_aging", "refers_to_previous": "more", "confidence": 0.9}))
		reply = answer("یه چند تای دیگه هم نشون بده", first["state"], reading)
		self.assertEqual(reply["intent"], "car_aging")
		self.assertFalse(set(first["state"]["shown"]) & set(reply["state"]["shown"][len(first["state"]["shown"]) :]))
		self.assertGreaterEqual(len(reply["state"]["shown"]), len(first["state"]["shown"]))
