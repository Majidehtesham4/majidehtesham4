"""A vendor bill from its PDF without any AI: read from the text of the file, the vendor found by its name, a
draft made with the file attached; a second time is refused, and posting waits for a person"""

import io
import json

from odoo.tests import tagged

from odoo.addons.veron_ai_agent.tests.common import FakeAdapter, calls

from ..tools.bills import text_fields
from .common import FinanceCase


def pdf(lines):
	from reportlab.pdfgen import canvas

	buffer = io.BytesIO()
	page = canvas.Canvas(buffer)
	for index, line in enumerate(lines):
		page.drawString(60, 800 - 24 * index, line)
	page.save()
	return buffer.getvalue()


BILL = ["Pars Test Supply Co", "Seller: Pars Test Supply Co", "Invoice No: PS-7781", "Date: 2026-10-20", "Subtotal: 10,000,000",
	"VAT 10%: 1,000,000", "Total: 11,000,000"]


@tagged("post_install", "-at_install")
class TestBills(FinanceCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.vendor = cls.env["res.partner"].create({"name": "Pars Test Supply Co", "supplier_rank": 1})
		cls.env["account.tax"].create({"name": "VAT 10% test", "amount": 10, "amount_type": "percent",
			"type_tax_use": "purchase", "company_id": cls.company.id})

	def test_text_fields(self):
		fields = text_fields("\n".join(BILL))
		self.assertEqual((fields["invoice_number"], fields["vendor"], fields["date"]), ("PS-7781", "Pars Test Supply Co", "2026-10-20"))
		self.assertEqual((fields["total_amount"], fields["vat_amount"], fields["untaxed_amount"]),
			(11_000_000, 1_000_000, 10_000_000))
		persian = text_fields("فروشنده: بازرگانی نور\nشماره فاکتور: ۱۲۳۴\nکد اقتصادی: ۴۱۱۱۱۱۱۱۱۱۱۱\nجمع کل: ۵,۵۰۰,۰۰۰")
		self.assertEqual((persian["vendor"], persian["invoice_number"], persian["vendor_tax_id"], persian["total_amount"]),
			("بازرگانی نور", "1234", "411111111111", 5_500_000))

	def test_draft_bill_from_pdf_without_ai(self):
		self.vision.active = False
		agent = self.agent("3", ["bill_from_document", "invoice_post"], ["account.move", "res.partner"],
			vision_provider_id=False)
		source = self.env["veron.ai.source"].with_user(self.accountant)._from_upload("bill.pdf", pdf(BILL))

		def run_with(*items):
			FakeAdapter.script = [calls(*items)]
			return self.env["veron.ai.run"].with_user(self.accountant)._start(agent, self.accountant, "user",
				text="ثبتش کن", sources=source)

		run = run_with(("bill_from_document", {"source_id": source.id}))
		output = json.loads(run.step_ids[:1].output_json or "{}")
		self.assertEqual(run.step_ids[:1].decision, "allowed", run.step_ids[:1].message)
		move = self.env["account.move"].browse(output["draft_id"])
		self.assertEqual((move.state, move.partner_id, move.ref), ("draft", self.vendor, "PS-7781"))
		self.assertEqual((move.amount_untaxed, move.amount_total), (10_000_000, 11_000_000))
		self.assertTrue(self.env["ir.attachment"].search([("res_model", "=", "account.move"), ("res_id", "=", move.id)]))
		# The same invoice again is refused
		run = run_with(("bill_from_document", {"source_id": source.id}))
		self.assertNotEqual(run.step_ids[:1].decision, "allowed")
		self.assertEqual(self.env["account.move"].search_count([("ref", "=", "PS-7781"), ("partner_id", "=", self.vendor.id)]), 1)
		# Posting waits for a person, whatever the agent's level
		run = run_with(("invoice_post", {"move_id": move.id}))
		self.assertEqual(run.step_ids[:1].decision, "approval")
		self.assertEqual(move.state, "draft")

	def test_bill_from_chat_without_ai(self):
		"""A photo or a PDF given in the chat box with «make it a draft»: the built-in assistant makes the bill"""
		self.env["veron.ai.agent"]._setup_assistant()
		self.env.ref("veron_ai_agent.agent_assistant").enabled = True
		Chat = self.env["veron.ai.conversation"].with_user(self.accountant)
		conversation = Chat.veron_chat_assistant()["conversation_id"]
		source = self.env["veron.ai.source"].with_user(self.accountant)._from_upload("bill.pdf", pdf(BILL))
		reply = Chat.veron_chat_send(conversation, "این فاکتور رو برام پیشنویس کن", [source.id], {}, "internal")[-1]
		self.assertEqual(reply["engine"], "internal")
		bill = self.env["account.move"].search([("ref", "=", "PS-7781"), ("partner_id", "=", self.vendor.id)])
		self.assertEqual((bill.state, bill.amount_total), ("draft", 11_000_000), reply["body_html"])
		self.assertTrue(any(option.get("code") == "invoice_post" for option in reply["options"]),
			"posting it is offered next, as a button")

	def test_our_invoice_is_a_sale(self):
		self.env.company.name = "شرکت من"
		customer = self.env["res.partner"].create({"name": "فروشگاه پاسارگاد", "customer_rank": 1})
		text = ("صورتحساب فروش کالا و خدمات\nشماره فاکتور: 5027\nتاریخ: 1405/05/16\nمشخصات فروشنده\n"
			"نام شخص حقیقی / حقوقی: شرکت من\nمشخصات خریدار\nنام شخص حقیقی / حقوقی: فروشگاه پاسارگاد\n"
			"جمع کل پس از تخفیف: 1,700,000\nجمع مالیات و عوارض: 170,000\nجمع کل با احتساب مالیات و عوارض: 1,870,000")
		fields = text_fields(text)
		self.assertEqual((fields["vendor"], fields["buyer"]), ("شرکت من", "فروشگاه پاسارگاد"))
		from types import SimpleNamespace

		from ..tools.bills import BillFromDocument

		tool = BillFromDocument()
		ctx = SimpleNamespace(env=self.env, run=SimpleNamespace(input_text="ثبت کن"))
		self.assertEqual(tool._direction(ctx, {}, fields), "sale", "the company is the seller: a customer invoice")
		swapped = dict(fields, vendor="فروشگاه پاسارگاد", buyer="شرکت من")
		self.assertEqual(tool._direction(ctx, {}, swapped), "purchase")
		self.assertEqual(tool._direction(ctx, {"direction": "purchase"}, fields), "purchase", "what the person says wins")
		self.assertTrue(customer)
