"""Each choice of the draft invoice policy takes its own path: where the taxes of a line come from (and when they are
asked), the discount of a line (only the same customer and product, said first), the price, and what is done when
stock is short (reported; a purchase draft only after a yes, or as the policy says, never confirmed). A policy of an
assistant overrides its company's, only an AI manager changes it, every change is in the audit, and drafts already
made are not changed by it."""

import importlib.util
import json
import os

from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.veron_ai_agent.tests.common import calls

from .common import FinanceCase, policy


class PolicyCase(FinanceCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env["veron.ai.agent"]._setup_assistant()
		cls.assistant = cls.env.ref("veron_ai_agent.agent_assistant")
		cls.assistant.enabled = True
		Partner, Product, Tax = cls.env["res.partner"], cls.env["product.product"], cls.env["account.tax"]
		cls.customer = Partner.create({"name": "خبازیان", "customer_rank": 1})
		cls.other = Partner.create({"name": "فرزامی", "customer_rank": 1})
		cls.tax10 = Tax.create({"name": "VAT 10 policy", "amount": 10, "type_tax_use": "sale", "company_id": cls.company.id})
		cls.tax5 = Tax.create({"name": "VAT 5 policy", "amount": 5, "type_tax_use": "sale", "company_id": cls.company.id})

		def product(name, price, taxes):
			return Product.create({"name": name, "list_price": price, "taxes_id": [(6, 0, taxes.ids)]})

		cls.oven = product("فر پیتزا ریلی ۱۱۵۴ عرض ۵۰", 3_000_000, cls.tax10)
		cls.nut = product("مهره M5", 20_000, cls.tax10)
		cls.door = product("درب شیشه ای", 900_000, cls.tax10)
		cls.felt = product("نمد ماشین پوست", 80_000, Tax)
		policy(cls.env, taxes_mode="system", price_mode="pricelist", discount_mode="last", stock_mode="report")

	def chat(self):
		Chat = self.env["veron.ai.conversation"].with_user(self.accountant)
		return Chat, Chat.veron_chat_new(self.assistant.id)["conversation_id"]

	def say(self, Chat, conversation, text):
		return Chat.veron_chat_send(conversation, text, [], {}, "internal")[-1]

	def says(self, reply, *texts):
		"""Whether the answer says one of the texts: the English one, or its Persian translation when it is loaded"""
		return any(text in reply["body_html"] for text in texts)

	def pending(self, Chat, conversation):
		return (Chat.browse(conversation).memory or {}).get("pending") or {}

	def count(self, model="account.move"):
		return self.env[model].search_count([])

	def last(self):
		return self.env["account.move"].search([("move_type", "=", "out_invoice"), ("state", "=", "draft")],
			order="id desc", limit=1)

	def line(self, move, product):
		return move.invoice_line_ids.filtered(lambda l: l.product_id == product)

	def sold(self, partner, product, discount=0, taxes=None, price=1000, state="posted", move_type="out_invoice"):
		"""A past sale; its taxes are the product's unless said (an empty recordset: none)"""
		move = self.env["account.move"].create({"move_type": move_type, "partner_id": partner.id, "invoice_line_ids": [
			(0, 0, {"product_id": product.id, "quantity": 1, "price_unit": price, "discount": discount,
				"tax_ids": [(6, 0, (product.taxes_id if taxes is None else taxes).ids)]})]})
		if state in ("posted", "cancel"):
			move.action_post()
		if state == "cancel":
			move.button_draft()
			move.button_cancel()
		return move



@tagged("post_install", "-at_install")
class TestInvoicePolicies(PolicyCase):
	# --- taxes

	def test_taxes_of_one_product_are_not_another_s(self):
		"""The customer's last invoice of the oven had no taxes: that says nothing of the door nor of the felt"""
		self.sold(self.customer, self.oven, taxes=self.env["account.tax"])
		Chat, conversation = self.chat()
		before = self.count()
		reply = self.say(Chat, conversation, "۱ عدد درب شیشه ای و ۲ عدد نمد ماشین پوست برای خبازیان فاکتور کن")
		self.assertEqual(self.count(), before, "the felt has no tax set nor a history of its own: asked first")
		self.assertEqual(self.pending(Chat, conversation).get("arg"), "taxes_unclear", reply["body_html"])
		self.assertIn("نمد ماشین پوست", reply["body_html"])
		self.assertNotIn("درب شیشه ای", reply["body_html"], "the door's taxes are clear: not asked")
		reply = self.say(Chat, conversation, "خیر")
		move = self.last()
		self.assertEqual(self.line(move, self.door).tax_ids, self.tax10, "the door keeps the system's taxes")
		self.assertFalse(self.line(move, self.felt).tax_ids, "the felt as answered")

	def test_system_setting_used_and_shown(self):
		Chat, conversation = self.chat()
		reply = self.say(Chat, conversation, "۱ عدد درب شیشه ای برای خبازیان فاکتور کن")
		move = self.last()
		self.assertEqual(self.line(move, self.door).tax_ids, self.tax10, reply["body_html"])
		self.assertIn("VAT 10 policy", reply["body_html"])
		self.assertTrue(self.says(reply, "the current setting", "تنظیم فعلی سامانه"), "where the taxes came from is shown")

	def test_setting_and_history_differ_asked(self):
		self.sold(self.customer, self.door, taxes=self.tax5)
		Chat, conversation = self.chat()
		before = self.count()
		reply = self.say(Chat, conversation, "۱ عدد درب شیشه ای برای خبازیان فاکتور کن")
		self.assertEqual(self.count(), before, reply["body_html"])
		self.assertIn("VAT 5 policy", reply["body_html"], "the question says what differs")
		self.say(Chat, conversation, "بله")
		self.assertEqual(self.line(self.last(), self.door).tax_ids, self.tax10, "as set in the system, as answered")

	def test_taxes_from_history_only(self):
		policy(self.env, taxes_mode="history")
		self.sold(self.customer, self.door, taxes=self.tax5)
		self.sold(self.other, self.nut, taxes=self.tax5)
		Chat, conversation = self.chat()
		self.say(Chat, conversation, "۱ عدد درب شیشه ای برای خبازیان فاکتور کن")
		self.assertEqual(self.line(self.last(), self.door).tax_ids, self.tax5, "the last invoice of the same product")
		before = self.count()
		self.say(Chat, conversation, "۱ عدد مهره m5 برای خبازیان فاکتور کن")
		self.assertEqual(self.count(), before, "the nut was sold to another customer only: asked")
		# A draft, a cancelled invoice and a credit note are no history
		self.sold(self.customer, self.nut, taxes=self.tax5, state="draft")
		self.sold(self.customer, self.nut, taxes=self.tax5, state="cancel")
		self.sold(self.customer, self.nut, taxes=self.tax5, move_type="out_refund")
		Chat, conversation = self.chat()
		before = self.count()
		self.say(Chat, conversation, "۱ عدد مهره m5 برای خبازیان فاکتور کن")
		self.assertEqual(self.count(), before)

	def test_taxes_asked_or_none_by_policy_and_said_first(self):
		policy(self.env, taxes_mode="ask")
		Chat, conversation = self.chat()
		before = self.count()
		self.say(Chat, conversation, "۱ عدد درب شیشه ای برای خبازیان فاکتور کن")
		self.assertEqual(self.count(), before, "asked each time")
		self.say(Chat, conversation, "۱ عدد درب شیشه ای برای خبازیان فاکتور کن بدون مالیات")
		self.assertFalse(self.line(self.last(), self.door).tax_ids, "said: no question")
		policy(self.env, taxes_mode="none")
		Chat, conversation = self.chat()
		self.say(Chat, conversation, "۱ عدد درب شیشه ای برای خبازیان فاکتور کن")
		self.assertFalse(self.line(self.last(), self.door).tax_ids)
		self.say(Chat, conversation, "۱ عدد درب شیشه ای برای خبازیان فاکتور کن با مالیات")
		self.assertEqual(self.line(self.last(), self.door).tax_ids, self.tax10)

	def test_an_agent_asks_its_person(self):
		"""An agent's run does not guess either: the taxes are asked of its responsible person"""
		self.sold(self.customer, self.door, taxes=self.tax5)
		models = ["account.move", "res.partner", "product.product"]
		agent = self.agent("3", ["invoice_draft_create"], models, name="سازنده")
		before = self.count()
		run = self.start(agent, [calls(("invoice_draft_create", {"move_type": "out_invoice", "partner_id": self.customer.id,
			"lines": [{"product_id": self.door.id, "quantity": 1}]}))])
		self.assertEqual((run.step_ids.decision, self.count()), ("needs_info", before))
		self.assertTrue(run.approval_ids.filtered(lambda a: a.kind == "info"))

	# --- discount and price

	def test_last_discount_of_the_same_customer_and_product(self):
		self.sold(self.customer, self.oven, 10)
		self.sold(self.customer, self.oven, 12)
		self.sold(self.customer, self.oven, 30, state="draft")
		self.sold(self.customer, self.oven, 40, state="cancel")
		self.sold(self.customer, self.nut, 5)
		self.sold(self.other, self.door, 20)
		Chat, conversation = self.chat()
		reply = self.say(Chat, conversation, "۱ عدد فر پیتزا ریلی ۱۱۵۴ عرض ۵۰ و ۱۰ عدد مهره m5 و ۱ عدد درب شیشه ای برای "
			"خبازیان فاکتور کن")
		move = self.last()
		self.assertEqual([self.line(move, p).discount for p in (self.oven, self.nut, self.door)], [12, 5, 0],
			reply["body_html"])
		self.assertEqual(self.line(move, self.oven).price_unit, 3_000_000, "the price of now, not the old one")
		self.assertTrue(self.says(reply, "no posted sale to this customer of: درب شیشه ای",
			"فروش قطعی‌شده‌ای به این مشتری نیست برای: درب شیشه ای"), reply["body_html"])

	def test_said_discount_comes_first(self):
		self.sold(self.customer, self.oven, 12)
		self.sold(self.customer, self.nut, 5)
		Chat, conversation = self.chat()
		self.say(Chat, conversation, "۱ عدد فر پیتزا ریلی ۱۱۵۴ عرض ۵۰ با ۷ درصد تخفیف و ۱۰ عدد مهره m5 بدون تخفیف برای "
			"خبازیان فاکتور کن")
		move = self.last()
		self.assertEqual((self.line(move, self.oven).discount, self.line(move, self.nut).discount), (7, 0))

	def test_each_discount_choice(self):
		self.sold(self.customer, self.oven, 12, price=2_500_000)
		text = "۱ عدد فر پیتزا ریلی ۱۱۵۴ عرض ۵۰ برای خبازیان فاکتور کن"
		results = {}
		for mode in ("none", "last", "consistent"):
			policy(self.env, discount_mode=mode, history_count=2)
			Chat, conversation = self.chat()
			self.say(Chat, conversation, text)
			results[mode] = self.line(self.last(), self.oven).discount
		self.assertEqual(results, {"none": 0, "last": 12, "consistent": 12})
		# The list's percentage shown as a discount of the product's price
		pricelist = self.env["product.pricelist"].create({"name": "قرارداد خبازیان", "item_ids": [(0, 0, {
			"applied_on": "0_product_variant", "product_id": self.oven.id, "compute_price": "percentage",
			"percent_price": 15})]})
		self.customer.property_product_pricelist = pricelist
		policy(self.env, discount_mode="pricelist")
		Chat, conversation = self.chat()
		self.say(Chat, conversation, text)
		line = self.line(self.last(), self.oven)
		self.assertEqual((line.price_unit, line.discount), (3_000_000, 15))
		# Asked: nothing made, then the answer
		self.customer.property_product_pricelist = False
		policy(self.env, discount_mode="ask")
		Chat, conversation = self.chat()
		before = self.count()
		self.say(Chat, conversation, text)
		self.assertEqual((self.count(), self.pending(Chat, conversation).get("arg")), (before, "discount_rule"))
		self.say(Chat, conversation, "2")
		self.assertEqual(self.line(self.last(), self.oven).discount, 12, "the last sale's, as chosen")

	def test_each_price_choice(self):
		self.sold(self.customer, self.oven, price=2_500_000)
		text = "۱ عدد فر پیتزا ریلی ۱۱۵۴ عرض ۵۰ برای خبازیان فاکتور کن"
		Chat, conversation = self.chat()
		self.say(Chat, conversation, text)
		self.assertEqual(self.line(self.last(), self.oven).price_unit, 3_000_000)
		policy(self.env, price_mode="pricelist_history")
		Chat, conversation = self.chat()
		self.say(Chat, conversation, text)
		self.assertEqual(self.line(self.last(), self.oven).price_unit, 2_500_000)

	# --- the policy itself

	def test_a_policy_of_the_assistant_and_of_the_company(self):
		policy(self.env, taxes_mode="none")
		own = policy(self.env, agent=self.assistant, taxes_mode="ask")
		Chat, conversation = self.chat()
		before = self.count()
		self.say(Chat, conversation, "۱ عدد درب شیشه ای برای خبازیان فاکتور کن")
		self.assertEqual(self.count(), before, "the assistant's own policy asks")
		own.unlink()
		Chat, conversation = self.chat()
		self.say(Chat, conversation, "۱ عدد درب شیشه ای برای خبازیان فاکتور کن")
		self.assertFalse(self.line(self.last(), self.door).tax_ids, "the company's: no taxes")

	def test_only_a_manager_changes_it_and_it_is_audited(self):
		record = policy(self.env)
		with self.assertRaises(AccessError):
			record.with_user(self.accountant).write({"taxes_mode": "none"})
		self.assertEqual(record.with_user(self.accountant).taxes_mode, "system", "read by the people who use it")
		Chat, conversation = self.chat()
		self.say(Chat, conversation, "۱ عدد درب شیشه ای برای خبازیان فاکتور کن")
		made = self.last()
		Audit = self.env["veron.ai.audit"].sudo()
		before = Audit.search_count([("event", "=", "invoice_policy_changed")])
		record.write({"taxes_mode": "none", "discount_mode": "none"})
		event = Audit.search([("event", "=", "invoice_policy_changed")], order="id desc", limit=1)
		self.assertEqual(Audit.search_count([("event", "=", "invoice_policy_changed")]), before + 1)
		data = json.loads(event.data_json)
		self.assertEqual((data["before"]["taxes_mode"], data["after"]["taxes_mode"]), ("system", "none"))
		self.assertEqual(self.line(made, self.door).tax_ids, self.tax10, "a draft already made is not changed")

	def test_defaults_and_the_update(self):
		Policy = self.env["veron.ai.invoice.policy"]
		Policy.search([("company_id", "=", self.company.id)]).unlink()
		self.assertEqual({k: v for k, v in Policy._for(self.company).items() if k != "policy"}, {"taxes_mode": "system",
			"price_mode": "pricelist", "discount_mode": "last", "history_count": 3, "stock_mode": "report"})
		# An update writes each company's policy from what it had: nothing decided differently without a choice
		Param = self.env["ir.config_parameter"].sudo()
		Param.set_param("veron_ai_agent_account.invoice_taxes", "product")
		Param.set_param("veron_ai_agent_account.invoice_discount", "said")
		path = os.path.join(os.path.dirname(__file__), "..", "migrations", "19.0.1.1.0", "post-migrate.py")
		spec = importlib.util.spec_from_file_location("veron_policy_migration", path)
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)
		module.migrate(self.env.cr, "19.0.1.0.0")
		record = Policy.search([("company_id", "=", self.company.id), ("agent_id", "=", False)])
		self.assertEqual((record.taxes_mode, record.discount_mode, record.price_mode, record.stock_mode),
			("system", "none", "pricelist", "report"))
		self.assertFalse(Param.get_param("veron_ai_agent_account.invoice_taxes"))
		record.unlink()
		module.migrate(self.env.cr, "19.0.1.0.0")
		record = Policy.search([("company_id", "=", self.company.id), ("agent_id", "=", False)])
		self.assertEqual((record.taxes_mode, record.discount_mode), ("ask", "last"), "not set before: asked, as before")


@tagged("post_install", "-at_install")
class TestShortStock(PolicyCase):
	"""Stock read and reported with the draft; a purchase draft of its own for what is short. Needs the stock and
	purchase apps"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if "stock.quant" not in cls.env or "purchase.order" not in cls.env:
			return
		cls.buyer = cls.env.ref("purchase.group_purchase_user")
		cls.accountant.group_ids |= cls.buyer
		cls.vendor = cls.env["res.partner"].create({"name": "بازرگانی نور", "supplier_rank": 1})
		cls.door.write({"is_storable": True, "seller_ids": [(0, 0, {"partner_id": cls.vendor.id, "price": 500_000})]})
		warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
		cls.env["stock.quant"]._update_available_quantity(cls.door, warehouse.lot_stock_id, 2)

	def setUp(self):
		super().setUp()
		if "stock.quant" not in self.env or "purchase.order" not in self.env:
			self.skipTest("the stock and purchase apps are not installed")

	def test_short_stock_is_only_reported(self):
		Chat, conversation = self.chat()
		before = self.count("purchase.order")
		reply = self.say(Chat, conversation, "۵ عدد درب شیشه ای برای خبازیان فاکتور کن")
		self.assertEqual(self.line(self.last(), self.door).quantity, 5, "the invoice as asked")
		self.assertTrue(self.says(reply, "Not enough in stock", "موجودی کافی نیست"), reply["body_html"])
		self.assertEqual(self.count("purchase.order"), before)
		self.assertFalse(self.pending(Chat, conversation), "nothing is offered with «report only»")

	def test_a_purchase_draft_only_after_yes(self):
		policy(self.env, stock_mode="ask")
		Chat, conversation = self.chat()
		before = self.count("purchase.order")
		reply = self.say(Chat, conversation, "۵ عدد درب شیشه ای برای خبازیان فاکتور کن")
		move = self.last()
		self.assertEqual(self.pending(Chat, conversation).get("arg"), "_confirm", reply["body_html"])
		self.assertEqual(self.count("purchase.order"), before, "not before the person says yes")
		self.say(Chat, conversation, "خیر")
		self.assertEqual(self.count("purchase.order"), before)
		Chat, conversation = self.chat()
		self.say(Chat, conversation, "۵ عدد درب شیشه ای برای خبازیان فاکتور کن")
		move = self.last()
		reply = self.say(Chat, conversation, "بله")
		order = self.env["purchase.order"].search([], order="id desc", limit=1)
		self.assertEqual(self.count("purchase.order"), before + 1, reply["body_html"])
		self.assertEqual((order.state, order.partner_id), ("draft", self.vendor))
		self.assertIn(f"#{move.id}", order.origin, "linked to the sale draft it is for")
		self.assertEqual(order.order_line.product_qty, 3, "what is short: 5 asked, 2 free")
		self.assertEqual(self.line(move, self.door).quantity, 5, "the sale draft is not changed")

	def test_a_vendor_not_clear_is_asked(self):
		policy(self.env, stock_mode="ask")
		second = self.env["res.partner"].create({"name": "تأمین البرز", "supplier_rank": 1})
		self.door.seller_ids = [(0, 0, {"partner_id": second.id, "price": 450_000})]
		Chat, conversation = self.chat()
		self.say(Chat, conversation, "۵ عدد درب شیشه ای برای خبازیان فاکتور کن")
		before = self.count("purchase.order")
		reply = self.say(Chat, conversation, "بله")
		self.assertEqual(self.count("purchase.order"), before, "two vendors: asked, not guessed")
		labels = [option["label"] for option in reply["options"]]
		self.assertTrue(any("تأمین البرز" in label for label in labels), reply["body_html"])
		self.say(Chat, conversation, str(next(i for i, label in enumerate(labels, 1) if "تأمین البرز" in label)))
		order = self.env["purchase.order"].search([], order="id desc", limit=1)
		self.assertEqual((order.partner_id, order.state), (second, "draft"))

	def test_a_purchase_draft_made_by_the_policy(self):
		policy(self.env, stock_mode="draft")
		Chat, conversation = self.chat()
		before = self.count("purchase.order")
		self.say(Chat, conversation, "۵ عدد درب شیشه ای برای خبازیان فاکتور کن")
		order = self.env["purchase.order"].search([], order="id desc", limit=1)
		self.assertEqual(self.count("purchase.order"), before + 1)
		self.assertEqual(order.state, "draft", "made, never confirmed")

	def test_no_purchase_rights_no_purchase(self):
		"""The purchase is made with the person's own rights: without them it is refused, the sale draft stays"""
		self.accountant.group_ids -= self.buyer
		policy(self.env, stock_mode="draft")
		Chat, conversation = self.chat()
		before = self.count("purchase.order")
		self.say(Chat, conversation, "۵ عدد درب شیشه ای برای خبازیان فاکتور کن")
		self.assertEqual(self.count("purchase.order"), before)
		self.assertEqual(self.line(self.last(), self.door).quantity, 5)
