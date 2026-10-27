"""The petty cash closing from the documents asked of the custodian to the posted entry and the report,
driven by an agent whose model is a script"""

import base64
import json
from datetime import timedelta
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.veron_ai_agent.services import files as filetools
from odoo.addons.veron_ai_agent.tests.common import FakeAdapter, answer, calls

from ..models.petty_cash import _date, _number
from .common import FinanceCase, image

TOOLS = ["petty_cash_open", "petty_cash_review", "petty_cash_draft_entry", "petty_cash_post", "petty_cash_report",
	"request_human_input"]
MODELS = ["veron.petty.cash.fund", "veron.petty.cash.closing", "veron.petty.cash.receipt", "account.move"]


@tagged("post_install", "-at_install")
class TestPettyCash(FinanceCase):
	def upload(self, closing, name, data, user=None):
		Receipt = self.env["veron.petty.cash.receipt"].with_user(user or self.custodian)
		return Receipt.create({"closing_id": closing.id, "upload": base64.b64encode(data), "upload_name": name})

	def test_closing_workflow(self):
		today = self.today()
		start = today - timedelta(days=20)
		self.topup(50_000_000, start + timedelta(days=1))
		agent = self.agent("4", TOOLS, MODELS)

		# 1. The closing is opened and the custodian is asked for the documents
		run = self.start(agent, [calls(("petty_cash_open", {"fund_id": self.fund.id, "date_to": str(today)}))])
		closing = self.fund.closing_ids
		self.assertEqual(run.step_ids.decision, "allowed", run.step_ids.output_json)
		self.assertEqual((closing.state, closing.date_to), ("draft", today))
		self.assertTrue(closing.requested_at)
		self.assertIn(self.custodian, closing.activity_ids.user_id)
		closing.date_from = start

		# 2. The custodian gives the files; a file that is not a photo or a PDF is refused
		paper = image((200, 30, 30))
		receipts = {
			"ok": self.upload(closing, "خرید کاغذ.jpg", paper),
			"same": self.upload(closing, "دوباره.jpg", paper),
			"taxi": self.upload(closing, "تاکسی.jpg", image((10, 10, 220))),
			"blank": self.upload(closing, "ناخوانا.jpg", image((10, 200, 10))),
		}
		with self.assertRaises(UserError):
			self.upload(closing, "virus.exe", b"MZ\x90\x00 not a receipt")
		self.assertTrue(all(r.source_id and r.sha256 for r in receipts.values()))
		# Another custodian sees none of it
		with self.assertRaises(AccessError):
			closing.with_user(self.other_custodian).read(["name"])
		# The custodian cannot decide a receipt
		with self.assertRaises(AccessError):
			receipts["ok"].with_user(self.custodian).write({"state": "accepted"})
		with self.assertRaises(AccessError):
			receipts["ok"].with_user(self.custodian).action_accept()

		# 3. The agent reads the files into fields
		read = {
			receipts["ok"].sha256: {"date": str(start + timedelta(days=2)), "amount": "۱٬۲۰۰٬۰۰۰", "vendor": "لوازم‌التحریر نور",
				"receipt_number": "455", "currency": "IRR", "description": "کاغذ A4", "vendor_tax_id": "", "vat_amount": "",
				"confidence": "high"},
			receipts["taxi"].sha256: {"date": str(start + timedelta(days=3)), "amount": "3500000", "vendor": "تاکسی اینترنتی",
				"receipt_number": "", "currency": "IRR", "description": "رفت و برگشت", "vendor_tax_id": "", "vat_amount": "",
				"confidence": "medium"},
			receipts["blank"].sha256: {"date": "", "amount": "", "vendor": "", "receipt_number": "", "currency": "",
				"description": "", "vendor_tax_id": "", "vat_amount": "", "confidence": "low"},
		}

		def extract(adapter, files, schema, instructions):
			self.assertIn("never guess", instructions)
			return {"fields": read[filetools.sha256(files[0][1])], "text": ""}

		with patch.object(FakeAdapter, "extract", extract):
			run = self.start(agent, [calls(("petty_cash_review", {"closing_id": closing.id}))])
		output = json.loads(run.step_ids.output_json)
		self.assertEqual(len(output["read"]), 4)
		self.assertEqual(receipts["ok"].amount, 1_200_000, "Persian digits are read")
		self.assertEqual(receipts["ok"].state, "extracted")
		self.assertFalse(receipts["blank"].amount, "nothing is guessed for an unreadable receipt")

		# 4. The custodian checks and confirms; an empty receipt cannot be confirmed
		custodian = self.env["veron.petty.cash.receipt"].with_user(self.custodian)
		custodian.browse(receipts["ok"].id).write({"category_id": self.cat_office.id})
		custodian.browse(receipts["taxi"].id).write({"category_id": self.cat_taxi.id})
		custodian.browse(receipts["same"].id).write({"category_id": self.cat_office.id})
		with self.assertRaises(UserError):
			custodian.browse(receipts["blank"].id).action_confirm()
		custodian.browse(receipts["blank"].id).write({"amount": 300_000, "date": start + timedelta(days=4),
			"vendor_name": "نانوایی", "category_id": self.cat_office.id})
		for receipt in receipts.values():
			custodian.browse(receipt.id).action_confirm()
		self.assertEqual(receipts["ok"].confirmed_by, self.custodian)
		closing.with_user(self.custodian).action_submit()
		self.assertEqual(closing.state, "review")

		# 5-7. Duplicates and the policy; findings to review, written neutrally
		run = self.start(agent, [calls(("petty_cash_review", {"closing_id": closing.id}))])
		self.assertEqual(receipts["ok"].state, "review")
		self.assertEqual(receipts["same"].state, "review")
		self.assertIn("duplicate_file", receipts["same"].issue_ids.mapped("kind"))
		self.assertIn("limit", receipts["taxi"].issue_ids.mapped("kind"), "3.5M is over the taxi limit of 2M")
		self.assertIn("reading", receipts["blank"].issue_ids.mapped("kind"), "read with low confidence")
		messages = " ".join(run.finding_ids.mapped("message"))
		self.assertTrue(run.finding_ids)
		for word in ("fraud", "تقلب", "cheat", "fake"):
			self.assertNotIn(word, messages.lower())
		self.assertEqual(run.state, "done_warning")

		# The draft waits for a person's review
		run = self.start(agent, [calls(("petty_cash_draft_entry", {"closing_id": closing.id}))])
		self.assertEqual(run.step_ids.decision, "needs_info")
		self.assertEqual(run.state, "waiting_info")

		# A person decides
		Receipt = self.env["veron.petty.cash.receipt"].with_user(self.accountant)
		Receipt.browse(receipts["same"].id).write({"decision_note": "همان رسید خرید کاغذ"})
		Receipt.browse(receipts["same"].id).action_reject()
		Receipt.browse((receipts["ok"] | receipts["taxi"] | receipts["blank"]).ids).action_accept()
		self.assertEqual(receipts["same"].decided_by, self.accountant)
		self.assertTrue(all(receipts["same"].issue_ids.mapped("resolved")))
		# An agent never decides a receipt
		with self.assertRaises(AccessError):
			Receipt.browse(receipts["same"].id).with_context(veron_ai_run_id=run.id).action_accept()

		# 8. The draft entry
		run = self.start(agent, [calls(("petty_cash_draft_entry", {"closing_id": closing.id}))])
		self.assertEqual(run.step_ids.decision, "allowed", run.step_ids.output_json)
		move = closing.move_id
		accepted = 1_200_000 + 3_500_000 + 300_000
		self.assertEqual(closing.state, "to_approve")
		self.assertEqual(move.state, "draft")
		credit = move.line_ids.filtered(lambda l: l.account_id == self.cash_account)
		self.assertEqual((credit.credit, credit.partner_id), (accepted, self.custodian.partner_id))
		self.assertEqual(sum(move.line_ids.mapped("debit")), accepted)
		self.assertEqual(len(self.env["ir.attachment"].search([("res_model", "=", "account.move"), ("res_id", "=", move.id)])), 3)

		# 9. Posting always waits for a person, even at authority 4
		run = self.start(agent, [calls(("petty_cash_post", {"closing_id": closing.id}))])
		self.assertEqual(run.step_ids.decision, "approval")
		self.assertEqual(run.state, "waiting_approval")
		self.assertEqual(move.state, "draft")
		approval = run.approval_ids
		with self.assertRaises(AccessError):
			approval.with_user(self.custodian).action_approve()

		# 10. Posted with the rights of the person who approves
		approval.with_user(self.accountant).action_approve()
		self.assertEqual(approval.state, "executed", approval.result_json)
		self.assertEqual(move.state, "posted")
		self.assertEqual((closing.state, closing.posted_by), ("posted", self.accountant))
		self.assertEqual(run.state, "done")

		# 11. The settlement report
		run = self.start(agent, [calls(("petty_cash_report", {"closing_id": closing.id})), answer("گزارش تسویه آماده است.")])
		figures = json.loads(run.step_ids.output_json)
		self.assertEqual(figures["opening_balance"], 0)
		self.assertEqual(figures["given_in_period"], 50_000_000)
		self.assertEqual(figures["accepted_amount"], accepted)
		self.assertEqual(figures["not_accepted_amount"], 1_200_000)
		self.assertEqual(figures["closing_balance"], 50_000_000 - accepted)
		self.assertEqual(self.fund.balance, 50_000_000 - accepted, "the balance comes from the posted items")
		self.assertTrue(closing.report_attachment_id)
		self.assertEqual(closing.report_attachment_id.mimetype, "application/pdf")

	def test_level_two_only_suggests(self):
		agent = self.agent("2", TOOLS, MODELS)
		run = self.start(agent, [calls(("petty_cash_open", {"fund_id": self.fund.id}))])
		self.assertEqual(run.step_ids.decision, "suggestion")
		self.assertFalse(self.fund.closing_ids, "a suggestion changes nothing")

	def _ready_closing(self):
		closing = self.env["veron.petty.cash.closing"].create({"fund_id": self.fund.id, "date_from": self.today() - timedelta(days=10),
			"date_to": self.today()})
		receipt = self.env["veron.petty.cash.receipt"].create({"closing_id": closing.id, "amount": 500_000, "date": self.today(),
			"vendor_name": "کافه", "category_id": self.cat_office.id})
		receipt.with_user(self.custodian).action_confirm()
		closing.with_user(self.custodian).action_submit()
		closing.with_user(self.accountant).action_review()
		return closing, receipt

	def test_changed_receipts_are_not_posted(self):
		closing, receipt = self._ready_closing()
		self.assertEqual(receipt.state, "accepted")
		closing.with_user(self.accountant).action_draft_move()
		receipt.with_user(self.accountant).write({"amount": 900_000})
		with self.assertRaisesRegex(UserError, "changed"):
			closing.with_user(self.accountant).action_post()
		self.assertEqual(closing.move_id.state, "draft")

	def test_custodian_cannot_post(self):
		closing, _receipt = self._ready_closing()
		closing.with_user(self.accountant).action_draft_move()
		with self.assertRaises(AccessError):
			closing.with_user(self.custodian).action_post()
		with self.assertRaises(AccessError):
			closing.with_user(self.custodian).write({"state": "posted"})

	def test_similar_photos(self):
		closing = self.env["veron.petty.cash.closing"].create({"fund_id": self.fund.id, "date_from": self.today() - timedelta(days=5),
			"date_to": self.today()})
		first = self.upload(closing, "a.jpg", image((120, 60, 30), (64, 48)))
		second = self.upload(closing, "b.jpg", image((121, 60, 30), (64, 48)))
		self.assertNotEqual(first.sha256, second.sha256)
		second.write({"amount": 100, "date": self.today(), "category_id": self.cat_office.id})
		kinds = [issue["kind"] for issue in second._check()]
		self.assertIn("duplicate_image", kinds)

	def test_same_vendor_and_number(self):
		closing = self.env["veron.petty.cash.closing"].create({"fund_id": self.fund.id, "date_from": self.today() - timedelta(days=5),
			"date_to": self.today()})
		Receipt = self.env["veron.petty.cash.receipt"]
		values = {"closing_id": closing.id, "vendor_name": "فروشگاه  كتاب", "receipt_number": "77", "amount": 1000,
			"date": self.today(), "category_id": self.cat_office.id}
		Receipt.create(values)
		other = Receipt.create({**values, "vendor_name": "فروشگاه کتاب", "amount": 2000})
		self.assertIn("duplicate_number", [issue["kind"] for issue in other._check()],
			"Arabic and Persian letters and spaces do not hide a duplicate")

	def test_reading_helpers(self):
		self.assertEqual(_number("۱٬۲۰۰٬۰۰۰ ریال"), 1_200_000)
		self.assertEqual(_number("12,500"), 12_500)
		self.assertIsNone(_number("ناخوانا"))
		self.assertEqual(str(_date("1405/08/05")), "2026-10-27")
		self.assertEqual(str(_date("2026-10-01")), "2026-10-01")
		self.assertIsNone(_date("دیروز"))
