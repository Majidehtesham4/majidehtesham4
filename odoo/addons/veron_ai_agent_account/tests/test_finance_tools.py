import json
from datetime import timedelta

from odoo.tests import tagged

from odoo.addons.veron_ai_agent.services import registry
from odoo.addons.veron_ai_agent.tests.common import calls

from .common import FinanceCase


@tagged("post_install", "-at_install")
class TestFinanceTools(FinanceCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.customer = cls.env["res.partner"].create({"name": "مشتری بدهکار"})
		cls.product = cls.env["product.product"].create({"name": "خدمات", "lst_price": 1_000_000, "taxes_id": [(5, 0, 0)]})
		invoice = cls.env["account.move"].create({"move_type": "out_invoice", "partner_id": cls.customer.id,
			"invoice_date": cls.today() - timedelta(days=60), "invoice_date_due": cls.today() - timedelta(days=30),
			"invoice_line_ids": [(0, 0, {"product_id": cls.product.id, "quantity": 3, "price_unit": 1_000_000,
				"tax_ids": [(5, 0, 0)]})]})
		invoice.action_post()
		cls.invoice = invoice

	def output(self, run, index=0):
		return json.loads(run.step_ids[index].output_json)

	def test_reading_tools(self):
		models = ["account.move", "account.move.line", "account.journal", "account.bank.statement.line", "res.partner",
			"veron.petty.cash.fund"]
		codes = ["receivables_overdue", "payables_due", "expense_summary", "cash_position", "bank_unreconciled",
			"documents_quality", "month_end_checklist", "tax_summary"]
		agent = self.agent("1", codes, models)
		self.env["account.move"].search([("move_type", "=", "out_invoice"), ("id", "!=", self.invoice.id)]).write(
			{"invoice_date_due": self.today()})
		self.topup(5_000_000, self.today())
		run = self.start(agent, [calls(*[(code, {}) for code in codes])])
		decisions = dict(zip(run.step_ids.mapped("tool_code"), run.step_ids.mapped("decision")))
		self.assertEqual(set(decisions.values()), {"allowed"}, run.step_ids.mapped("output_json"))
		overdue = self.output(run, 0)
		row = next(r for r in overdue["customers"] if r["customer"] == "مشتری بدهکار")
		self.assertEqual(row["amount_due"], 3_000_000)
		self.assertGreaterEqual(row["oldest_days"], 30)
		cash = self.output(run, 3)
		self.assertIn({"fund": "تنخواه نمایشگاه", "custodian": self.custodian.name, "balance": 5_000_000.0}, cash["petty_cash"])
		checklist = self.output(run, 6)
		self.assertTrue(checklist["month"].startswith("140"))
		self.assertIn("Lock dates", [item["check"] for item in checklist["items"]])

	def test_draft_invoice(self):
		models = ["account.move", "res.partner", "product.product"]
		args = {"move_type": "out_invoice", "partner_id": self.customer.id, "lines": [{"product_id": self.product.id, "quantity": 2}]}
		# Taxes neither said nor set: refused, nothing made
		maker = self.agent("3", ["invoice_draft_create"], models, name="بی مالیات")
		before = self.env["account.move"].search_count([])
		run = self.start(maker, [calls(("invoice_draft_create", args))])
		self.assertEqual((run.step_ids.decision, self.env["account.move"].search_count([])), ("denied", before))
		self.assertTrue("taxes" in run.step_ids.output_json or "مالیات" in run.step_ids.output_json, run.step_ids.output_json)
		args["taxes"] = "product"
		reader = self.agent("1", ["invoice_draft_create"], models, name="خواننده")
		run = self.start(reader, [calls(("invoice_draft_create", args))])
		self.assertEqual(run.step_ids.decision, "denied")
		maker = self.agent("3", ["invoice_draft_create"], models, name="سازنده")
		run = self.start(maker, [calls(("invoice_draft_create", args))])
		result = self.output(run)
		move = self.env["account.move"].browse(result["draft_id"])
		self.assertEqual((move.state, move.amount_untaxed), ("draft", 2_000_000), "the price comes from Odoo")
		self.assertFalse(result["posted"])
		# A partner outside the agent's data is refused
		limited = self.agent("3", ["invoice_draft_create"], models, name="محدود")
		limited.scope_ids.filtered(lambda s: s.model == "res.partner").domain = "[('id', '=', 0)]"
		run = self.start(limited, [calls(("invoice_draft_create", args))])
		self.assertEqual(run.step_ids.decision, "denied")

	def test_optional_tools_follow_installed_modules(self):
		for code, model in (("budget_vs_actual", "crossovered.budget.lines"), ("asset_check", "account.asset")):
			self.assertEqual(registry.get(code).available(self.env), model in self.env)
