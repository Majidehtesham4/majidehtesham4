"""A draft invoice made only from what is known: every customer and product found for certain or asked, nothing
carried over from an earlier request, no price, discount or tax made up, and nothing made when a line fails. The
errors met in use, each as a test, and the cases that must refuse."""

from odoo.tests import tagged

from ..tools.finance import PARAM_DISCOUNT, PARAM_TAXES
from .common import FinanceCase


@tagged("post_install", "-at_install")
class TestSafeInvoices(FinanceCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env["veron.ai.agent"]._setup_assistant()
		cls.env.ref("veron_ai_agent.agent_assistant").enabled = True
		Partner, Product = cls.env["res.partner"], cls.env["product.product"]
		cls.khabbazian = Partner.create({"name": "خبازیان", "customer_rank": 1})
		cls.farzami = Partner.create({"name": "فرزامی (هایدا تهران)", "customer_rank": 1})
		cls.fastfood = Partner.create({"name": "فست فود تیک", "customer_rank": 1})
		cls.laser = Partner.create({"name": "لیزر و پانچ سلینمی", "customer_rank": 1})
		cls.hasan_pour = Partner.create({"name": "حسن پور", "customer_rank": 1})
		cls.hasan_rezaei = Partner.create({"name": "حسن رضایی", "customer_rank": 1})
		cls.tax = cls.env["account.tax"].create({"name": "VAT 10 test", "amount": 10, "type_tax_use": "sale",
			"company_id": cls.company.id})

		def product(name, price):
			return Product.create({"name": name, "list_price": price, "taxes_id": [(6, 0, cls.tax.ids)]})

		cls.door = product("درب شیشه ای", 900_000)
		cls.nut = product("مهره M5", 20_000)
		cls.oven = product("فر پیتزا ریلی ۱۱۵۴ عرض ۵۰", 3_000_000)
		cls.roller = product("قلم و قلتک", 150_000)
		cls.paint = product("رنگ + قلم", 300_000)
		cls.finger = product("1456fingerup-04", 700_000)
		cls.terminal2 = product("ترمینال ۲ خانه", 30_000)
		cls.terminal3 = product("ترمینال ۳ خانه", 35_000)
		cls.socket = product("سوکت دوشاخه قرمز", 60_000)
		cls.unpriced = product("مهره سفید گالوانیزه M6", 0)
		cls.discount_item = product("تخفیف", 0)
		cls.Param = cls.env["ir.config_parameter"].sudo()
		cls.Param.set_param(PARAM_TAXES, "none")

	def chat(self):
		Chat = self.env["veron.ai.conversation"].with_user(self.accountant)
		return Chat, Chat.veron_chat_new(self.env.ref("veron_ai_agent.agent_assistant").id)["conversation_id"]

	def say(self, Chat, conversation, text):
		return Chat.veron_chat_send(conversation, text, [], {}, "internal")[-1]

	def last(self):
		return self.env["account.move"].search([("move_type", "=", "out_invoice"), ("state", "=", "draft")], order="id desc",
			limit=1)

	def lines(self, move):
		return [(line.product_id, line.quantity) for line in move.invoice_line_ids]

	def sold(self, partner, product, discount):
		past = self.env["account.move"].create({"move_type": "out_invoice", "partner_id": partner.id, "invoice_line_ids": [
			(0, 0, {"product_id": product.id, "quantity": 1, "price_unit": product.lst_price or 1000, "discount": discount,
				"tax_ids": [(6, 0, [])]})]})
		past.action_post()
		return past

	# --- what was asked before is not carried into a new request

	def test_a_new_request_drops_the_open_question(self):
		"""The invoice of خبازیان went to فرزامی, the one asked before: an open question is not the next request's"""
		Chat, conversation = self.chat()
		reply = self.say(Chat, conversation, "یک فاکتور برای فرزامی بزن ۲ عدد ترمینال")
		self.assertTrue(reply["options"], "two terminals are offered: " + reply["body_html"])
		self.say(Chat, conversation, "یک فاکتور برای اقای خبازیان بزن ۱ عدد درب شیشه ای و ۱۰ عدد مهره m5")
		move = self.last()
		self.assertEqual(move.partner_id, self.khabbazian)
		self.assertEqual(self.lines(move), [(self.door, 1), (self.nut, 10)], "nothing of the earlier request")
		# The next request of another customer is a new draft too, not a change of this one
		self.say(Chat, conversation, "۱ عدد سوکت دوشاخه قرمز برای فست فود تیک فاکتور کن بدون مالیات")
		self.assertEqual(self.last().partner_id, self.fastfood)
		self.assertEqual(self.lines(move), [(self.door, 1), (self.nut, 10)], "the draft of خبازیان is as it was")

	def test_a_number_answers_only_an_open_list(self):
		Chat, conversation = self.chat()
		reply = self.say(Chat, conversation, "یک فاکتور برای فرزامی بزن ۲ عدد ترمینال")
		self.assertTrue(reply["options"])
		self.say(Chat, conversation, "لیست مشتری ها رو بیار")
		before = self.env["account.move"].search_count([])
		reply = self.say(Chat, conversation, "1")
		self.assertEqual(self.env["account.move"].search_count([]), before, "«1» after another subject makes nothing")
		self.assertFalse(Chat.browse(conversation).memory.get("pending"), reply["body_html"])

	# --- names: «و» and «+» inside them, numbers of a name are not counts

	def test_names_with_and_plus_and_numbers(self):
		Chat, conversation = self.chat()
		self.say(Chat, conversation, "ده قلم و قلتک و ۲ عدد رنگ + قلم و ۳ عدد 1456fingerup-04 و ۱۰ عدد ترمینال ۲ خانه "
			"برای فرزامی فاکتور کن")
		move = self.last()
		self.assertEqual(move.partner_id, self.farzami)
		self.assertEqual(self.lines(move), [(self.roller, 10), (self.paint, 2), (self.finger, 3), (self.terminal2, 10)])

	def test_a_customer_with_and_in_the_name(self):
		Chat, conversation = self.chat()
		reply = self.say(Chat, conversation, "فاکتور فروش برای خانم ليزر و پانچ سلينمي 2 عدد سوکت دوشاخه قرمز، 3 تا ترمینال ۳ خانه")
		move = self.last()
		self.assertEqual(move.partner_id, self.laser, reply["body_html"])
		self.assertEqual(self.lines(move), [(self.socket, 2), (self.terminal3, 3)])

	def test_words_of_a_name_that_look_like_terms(self):
		"""«بدون پایه» of a name is not «بدون تخفیف»; «۱۴۵۶» inside a name is not the count; «نصب و راه» is one product
		said in part; «۲ عدد» may follow the name"""
		Product = self.env["product.product"]
		legless = Product.create({"name": "میز کار استیل ۱۴۵۶ عرض ۸۰ بدون پایه", "list_price": 4_000_000})
		Product.create({"name": "میز کار استیل ۱۴۵۶ عرض ۸۰", "list_price": 5_000_000})
		setup = Product.create({"name": "نصب و راه‌اندازی", "list_price": 2_000_000})
		Chat, conversation = self.chat()
		self.say(Chat, conversation, "۲ تا میز کار استیل ۱۴۵۶ عرض ۸۰ بدون پایه، ده نصب و راه و درب شیشه ای ۳ عدد برای خبازیان "
			"فاکتور کن")
		move = self.last()
		self.assertEqual(self.lines(move), [(legless, 2), (setup, 10), (self.door, 3)])
		reply = self.say(Chat, conversation, "روی میز کار استیل ۱۴۵۶ عرض ۸۰ بدون پایه ۵ درصد تخفیف بده")
		self.assertEqual(move.invoice_line_ids.filtered(lambda l: l.product_id == legless).discount, 5, reply["body_html"])
		self.say(Chat, conversation, "میز کار استیل ۱۴۵۶ عرض ۸۰ بدون پایه هم اضافه کن")
		self.assertEqual(sum(move.invoice_line_ids.filtered(lambda l: l.product_id == legless).mapped("quantity")), 3,
			"one more: the numbers of the name are not a count")

	# --- what is not found for certain is asked or refused, never replaced

	def test_a_product_not_there_makes_nothing(self):
		Chat, conversation = self.chat()
		before = self.env["account.move"].search_count([])
		reply = self.say(Chat, conversation, "۲ عدد درب شیشه ای و ۳ عدد گیربکس فضایی برای خبازیان فاکتور کن")
		self.assertEqual(self.env["account.move"].search_count([]), before, reply["body_html"])
		self.assertIn("گیربکس فضایی", reply["body_html"])

	def test_a_customer_of_several_is_asked(self):
		Chat, conversation = self.chat()
		before = self.env["account.move"].search_count([])
		reply = self.say(Chat, conversation, "۲ عدد درب شیشه ای برای حسن فاکتور کن")
		self.assertEqual(self.env["account.move"].search_count([]), before)
		labels = [option["label"] for option in reply["options"]]
		self.assertTrue(any("حسن پور" in label for label in labels) and any("حسن رضایی" in label for label in labels),
			reply["body_html"])
		self.say(Chat, conversation, str(next(i for i, label in enumerate(labels, 1) if "حسن رضایی" in label)))
		self.assertEqual(self.last().partner_id, self.hasan_rezaei)

	def test_no_price_makes_nothing(self):
		"""A product without a price is not invoiced at 1: nothing is made and the price is asked"""
		Chat, conversation = self.chat()
		before = self.env["account.move"].search_count([])
		reply = self.say(Chat, conversation, "۲ تا مهره سفید گالوانیزه و دو عدد درب شیشه ای برای فست فود تیک فاکتور کن")
		self.assertEqual(self.env["account.move"].search_count([]), before, "not even the priced line: " + reply["body_html"])
		self.assertIn("مهره سفید گالوانیزه M6", reply["body_html"])
		self.say(Chat, conversation, "۲ تا مهره سفید گالوانیزه به قیمت ۵۰۰۰ تومان برای فست فود تیک فاکتور کن")
		self.assertEqual(self.last().invoice_line_ids.price_unit, 50_000, "the price said, in rial")

	# --- taxes: said, set, or asked

	def test_taxes_are_asked_when_not_said_nor_set(self):
		self.Param.set_param(PARAM_TAXES, "ask")
		Chat, conversation = self.chat()
		before = self.env["account.move"].search_count([])
		reply = self.say(Chat, conversation, "۲ عدد درب شیشه ای برای خبازیان فاکتور کن")
		self.assertEqual(self.env["account.move"].search_count([]), before, "asked first: " + reply["body_html"])
		self.assertEqual(Chat.browse(conversation).memory["pending"]["arg"], "taxes")
		self.say(Chat, conversation, "خیر")
		self.assertFalse(self.last().invoice_line_ids.tax_ids, "no taxes, as answered")
		self.say(Chat, conversation, "۲ عدد درب شیشه ای برای خبازیان فاکتور کن با مالیات")
		self.assertEqual(self.last().invoice_line_ids.tax_ids, self.tax, "the taxes of the product, as said")

	def test_taxes_said_while_a_product_is_asked(self):
		self.Param.set_param(PARAM_TAXES, "ask")
		Chat, conversation = self.chat()
		reply = self.say(Chat, conversation, "۲ عدد ترمینال برای خبازیان فاکتور کن")
		labels = [option["label"] for option in reply["options"]]
		reply = self.say(Chat, conversation, "بدون مالیات")
		self.assertEqual([option["label"] for option in reply["options"]], labels, "the product is still asked")
		self.say(Chat, conversation, str(next(i for i, label in enumerate(labels, 1) if "۳" in label)))
		move = self.last()
		self.assertEqual((self.lines(move), move.invoice_line_ids.tax_ids.ids), ([(self.terminal3, 2)], []))

	# --- discounts: only the same customer and the same product, only when they agree

	def test_the_discount_of_the_same_product_only(self):
		self.sold(self.khabbazian, self.oven, 10)
		self.sold(self.khabbazian, self.oven, 10)
		self.sold(self.khabbazian, self.nut, 5)
		self.sold(self.khabbazian, self.nut, 8)
		self.sold(self.khabbazian, self.socket, 15)
		Chat, conversation = self.chat()
		reply = self.say(Chat, conversation, "یک فاکتور برای اقای خبازیان بزن ۱ عدد درب شیشه ای و ۱۰ عدد مهره m5 و ۲ عدد فر "
			"پیتزا ۱۱۵۴ با تخفیف همیشگی")
		discounts = {line.product_id: line.discount for line in self.last().invoice_line_ids}
		self.assertEqual(discounts[self.oven], 10, "the same 10% of its last sales: " + reply["body_html"])
		self.assertEqual(discounts[self.nut], 0, "5% then 8%: not applied, shown")
		self.assertEqual(discounts[self.door], 0, "the 15% of another product is not this one's")

	def test_the_discount_only_when_said(self):
		self.Param.set_param(PARAM_DISCOUNT, "said")
		self.sold(self.khabbazian, self.oven, 10)
		Chat, conversation = self.chat()
		self.say(Chat, conversation, "۱ عدد فر پیتزا ۱۱۵۴ برای خبازیان فاکتور کن")
		self.assertEqual(self.last().invoice_line_ids.discount, 0)
		self.say(Chat, conversation, "۱ عدد فر پیتزا ۱۱۵۴ برای خبازیان فاکتور کن با تخفیف همیشگی")
		self.assertEqual(self.last().invoice_line_ids.discount, 10, "the customer's discount of the product, as asked")

	def test_without_discount_said_of_a_line(self):
		self.sold(self.khabbazian, self.oven, 10)
		self.sold(self.khabbazian, self.nut, 10)
		Chat, conversation = self.chat()
		self.say(Chat, conversation, "۱۰ عدد مهره m5 بدون تخفیف و ۲ عدد فر پیتزا ۱۱۵۴ برای خبازیان فاکتور کن")
		discounts = {line.product_id: line.discount for line in self.last().invoice_line_ids}
		self.assertEqual((discounts[self.nut], discounts[self.oven]), (0, 10))

	# --- reading what there is

	def test_a_question_is_not_a_command(self):
		self.sold(self.farzami, self.door, 0)
		Chat, conversation = self.chat()
		before = self.env["account.move"].search_count([])
		reply = self.say(Chat, conversation, "برای فرزامی چی فاکتور شده")
		self.assertEqual(self.env["account.move"].search_count([]), before, reply["body_html"])
		self.assertIn("درب شیشه ای", reply["body_html"])

	def test_reads_of_customers_and_documents(self):
		Chat, conversation = self.chat()
		reply = self.say(Chat, conversation, "لیست مشتری ها رو بیار")
		self.assertIn("خبازیان", reply["body_html"])
		self.say(Chat, conversation, "۲ عدد درب شیشه ای برای خبازیان فاکتور کن")
		move = self.last()
		Chat2, conversation2 = self.chat()
		reply = self.say(Chat2, conversation2, "اخرین پیش نویس رو برام باز کن")
		self.assertTrue(any(option.get("res_id") == move.id and option.get("auto") for option in reply["options"]),
			reply["options"])
		posted = self.sold(self.farzami, self.roller, 0)
		reply = self.say(Chat2, conversation2, f"محتوای فاکتور {posted.name} رو بیار")
		self.assertIn("قلم و قلتک", reply["body_html"])
		before = reply["body_html"]
		reply = self.say(Chat2, conversation2, "محتوای فاکتور INV/1999/99999 رو بیار")
		self.assertNotIn("قلم و قلتک", reply["body_html"], "a number not found shows no other document")
		self.assertNotEqual(reply["body_html"], before)
