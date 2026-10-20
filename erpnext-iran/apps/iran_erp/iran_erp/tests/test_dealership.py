"""The car dealership pack: cars, instalment sales, investors, cheques and their entries."""

from unittest import TestCase

import frappe
from frappe.utils import add_days, add_months, flt, nowdate

from iran_erp.accounts.chart import CHART_NAME
from iran_erp.business import account, apply_pack, journal, set_branches
from iran_erp.business.investor_portal import get_my_account
from iran_erp.iran_dealership.doctype.iran_instalment_sale.iran_instalment_sale import calculate
from iran_erp.iran_dealership.doctype.iran_investment_contract.iran_investment_contract import daily_profit
from iran_erp.utils.words import amount_words, date_words, number_words

COMPANY = "Dealership Test Co"
ABBR = "DTC"
BILLION = 1_000_000_000


def number_account(number):
	return frappe.db.get_value("Account", {"company": COMPANY, "account_number": number, "is_group": 0})


def balance(account_name, party=None):
	condition, values = "account=%s", [account_name]
	if party:
		condition += " and party=%s"
		values.append(party)
	return flt(
		frappe.db.sql(
			f"select sum(debit - credit) from `tabGL Entry` where {condition} and is_cancelled=0", values
		)[0][0]
	)


# A plain TestCase: Frappe's test records would add a Gregorian fiscal year that clashes with a Jalali one
class TestDealership(TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Company", COMPANY):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": COMPANY,
					"abbr": ABBR,
					"default_currency": "IRR",
					"country": "Iran",
					"chart_of_accounts": CHART_NAME,
				}
			).insert()
		apply_pack("Car Dealership", COMPANY)
		for name in ("Dealership Buyer", "Remittance Car Buyer"):
			if not frappe.db.exists("Customer", name):
				frappe.get_doc({"doctype": "Customer", "customer_name": name}).insert()
		cls.cash = number_account("1101")
		cls.bank = number_account("110301")
		# The pack fills the lists of models, colours, body parts and services
		cls.car_model = frappe.db.get_value("Iran Car Model", {"disabled": 0, "made_in": "Made in Iran"})
		cls.imported_model = frappe.db.get_value("Iran Car Model", {"disabled": 0, "made_in": "Imported Car"})

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()

	def vehicle(self, **kwargs):
		return frappe.get_doc(
			{
				"doctype": "Iran Vehicle",
				"car_model": self.car_model,
				"year": "1404",
				"company": COMPANY,
				**kwargs,
			}
		).insert()

	def test_calculation_follows_the_dealers_arithmetic(self):
		# 2 billion toman car, 1 billion down, 6% a month for 10 months (here in rials)
		result = calculate(20 * BILLION, 10 * BILLION, 0, 6, 10)
		self.assertEqual(result["financed"], 10 * BILLION)
		self.assertEqual(result["interest"], 6 * BILLION)
		self.assertEqual(result["total"], 16 * BILLION)
		self.assertEqual({row["amount"] for row in result["rows"]}, {1_600_000_000})
		# Rounding leaves the remainder on the last instalment
		odd = calculate(1_000_000_000, 0, 1_234_567, 5, 7)
		self.assertEqual(sum(r["amount"] for r in odd["rows"]), odd["total"])
		self.assertTrue(all(r["amount"] % 1000 == 0 for r in odd["rows"][:-1]))

	def test_sale_in_instalments(self):
		car = self.vehicle(purchase_price=1_500_000_000, paid_from=self.cash, asking_price=2 * BILLION)
		# A car paid for from an account is in the books as soon as it is saved
		self.assertTrue(car.purchase_entry)
		car.append(
			"costs", {"date": nowdate(), "service": "صافکاری", "amount": 50_000_000, "paid_from": self.cash}
		)
		car.save()
		self.assertEqual(car.repair_total, 50_000_000)
		stock = account(COMPANY, "vehicle_stock")
		self.assertEqual(balance(stock), 1_550_000_000)

		sale = frappe.get_doc(
			{
				"doctype": "Iran Instalment Sale",
				"company": COMPANY,
				"customer": "Dealership Buyer",
				"vehicle": car.name,
				"posting_date": nowdate(),
				"sale_price": 2 * BILLION,
				"down_payment": BILLION,
				"down_payment_account": self.cash,
				"monthly_rate": 6,
				"months": 10,
				"first_due_date": add_months(nowdate(), 1),
				"late_fee_rate": 3,
			}
		).insert()
		self.assertEqual(sale.total_interest, 600_000_000)
		self.assertEqual(sale.instalment_amount, 160_000_000)
		self.assertEqual(len(sale.schedule), 10)
		sale.submit()

		receivable = number_account("1301")
		self.assertEqual(balance(receivable, "Dealership Buyer"), 1_600_000_000)
		self.assertEqual(balance(account(COMPANY, "deferred_interest")), -600_000_000)
		self.assertEqual(balance(stock), 0)
		self.assertEqual(frappe.db.get_value("Iran Vehicle", car.name, "status"), "Sold")
		self.assertEqual(frappe.db.get_value("Iran Vehicle", car.name, "profit"), 450_000_000)

		# A cheque for every instalment: the customer's debt moves to cheques receivable
		sale.reload()
		cheques = sale.make_cheques(bank="ملت", first_number="000101")
		self.assertEqual(len(cheques), 10)
		self.assertEqual(frappe.db.get_value("Iran Cheque", cheques[1], "cheque_number"), "000102")
		self.assertEqual(balance(receivable, "Dealership Buyer"), 0)

		# The first cheque clears: the instalment is paid; its profit becomes income on its date
		first = frappe.get_doc("Iran Cheque", cheques[0])
		first.take_action("clear", date=nowdate(), bank_account=self.bank)
		sale.reload()
		sale.update_status()
		self.assertEqual(sale.schedule[0].status, "Paid")
		sale.recognize_interest(sale.schedule[0].due_date)
		self.assertEqual(balance(account(COMPANY, "instalment_income")), -60_000_000)

		# Late fee day by day on an overdue instalment: 160m × 3% ÷ 30 × 10 days
		sale.reload()
		late = add_days(sale.schedule[1].due_date, 10)
		self.assertEqual(sale.late_fee_due(late), 1_600_000)

		# Settling early takes off the profit of the days not reached
		quote = sale.settlement_quote(nowdate())
		self.assertEqual(quote["principal"], 900_000_000)
		self.assertGreater(quote["discount"], 0)
		self.assertEqual(quote["payable"], quote["principal"] + quote["earned_interest"])

	def test_investor_contract_cheques_and_reinvestment(self):
		investor = frappe.get_doc({"doctype": "Iran Investor", "full_name": "سرمایه‌گذار آزمایشی"}).insert()
		self.assertEqual(frappe.db.get_value("Supplier", investor.supplier, "supplier_group"), "سرمایه‌گذاران")
		contract = frappe.get_doc(
			{
				"doctype": "Iran Investment Contract",
				"investor": investor.name,
				"company": COMPANY,
				"amount": BILLION,
				"received_to": self.bank,
				"start_date": nowdate(),
				"months": 6,
				"monthly_rate": 4,
				"profit_payment": "Monthly",
			}
		).insert()
		self.assertEqual(contract.monthly_profit, 40_000_000)
		self.assertEqual(contract.total_profit, 240_000_000)
		self.assertEqual([r.kind for r in contract.schedule], ["Profit"] * 6 + ["Principal"])
		contract.submit()
		payable = account(COMPANY, "investors")
		self.assertEqual(balance(payable, investor.supplier), -BILLION)

		# Profit day by day: 1 billion × 4% × 12 ÷ 365 a day
		self.assertAlmostEqual(daily_profit(BILLION, 4), 1_315_068.49, places=1)
		contract.set_summary(add_days(nowdate(), 10))
		self.assertEqual(contract.accrued_profit, 13_150_685)

		# Cheques for every payment at hand-over
		contract.reload()
		cheques = contract.issue_cheques(bank_account=self.bank, first_number="500001")
		self.assertEqual(len(cheques), 7)

		# The first profit falls due and is owed to the investor
		contract.reload()
		contract.accrue_profit(contract.schedule[0].due_date)
		self.assertEqual(balance(account(COMPANY, "investor_profit")), 40_000_000)

		# The second and third profits are put back in: their cheques come back
		new_name = contract.reinvest(rows=[2, 3], months=3, monthly_rate=4)
		new = frappe.get_doc("Iran Investment Contract", new_name)
		self.assertEqual(new.amount, 80_000_000)
		self.assertEqual(new.parent_contract, contract.name)
		contract.reload()
		self.assertEqual([r.status for r in contract.schedule[1:3]], ["Reinvested", "Reinvested"])
		self.assertEqual(
			frappe.db.get_value("Iran Cheque", contract.schedule[1].cheque, "status"), "Returned"
		)
		new.submit()
		self.assertEqual([c.name for c in new.chain()], [contract.name, new.name])

	def test_monthly_payments_return_the_money_with_its_profit(self):
		investor = frappe.get_doc({"doctype": "Iran Investor", "full_name": "سرمایه‌گذار ماهانه"}).insert()
		contract = frappe.get_doc(
			{
				"doctype": "Iran Investment Contract",
				"investor": investor.name,
				"company": COMPANY,
				"amount": 1_200_000_000,
				"received_to": self.bank,
				"start_date": nowdate(),
				"months": 12,
				"monthly_rate": 4,
			}
		).insert()
		self.assertEqual(contract.profit_payment, "Monthly with Principal")
		# (1.2 billion + 12 × 48 million) ÷ 12 every month, one cheque each
		self.assertEqual([r.kind for r in contract.schedule], ["Profit and Principal"] * 12)
		self.assertEqual({r.amount for r in contract.schedule}, {148_000_000})
		self.assertEqual(sum(r.profit_part for r in contract.schedule), 576_000_000)
		contract.submit()
		contract.reload()
		self.assertEqual(len(contract.issue_cheques(bank_account=self.bank, first_number="700001")), 12)
		# Only the profit share is the business's expense when a payment falls due
		contract.reload()
		before = balance(account(COMPANY, "investor_profit"))
		contract.accrue_profit(contract.schedule[0].due_date)
		self.assertEqual(balance(account(COMPANY, "investor_profit")) - before, 48_000_000)

	def test_car_remittance(self):
		investor = frappe.get_doc({"doctype": "Iran Investor", "full_name": "خریدار حواله"}).insert()
		car = self.vehicle(status="Awaiting Delivery")
		contract = frappe.get_doc(
			{
				"doctype": "Iran Investment Contract",
				"investor": investor.name,
				"company": COMPANY,
				"contract_type": "Car Remittance",
				"vehicle": car.name,
				"amount": 1_800_000_000,
				"start_date": nowdate(),
				"months": 2,
				"commission_rate": 2,
			}
		).insert()
		contract.submit()
		car.reload()
		self.assertEqual(car.ownership, "Investor")
		car.status = "Ready for Sale"
		car.save()

		sale = frappe.get_doc(
			{
				"doctype": "Iran Instalment Sale",
				"company": COMPANY,
				"customer": "Remittance Car Buyer",
				"vehicle": car.name,
				"posting_date": nowdate(),
				"sale_price": 2 * BILLION,
				"down_payment": 2 * BILLION - 100_000_000,
				"monthly_rate": 0,
				"months": 1,
				"first_due_date": add_months(nowdate(), 1),
			}
		).insert()
		sale.submit()
		contract.reload()
		self.assertEqual(contract.settlement_amount, 1_960_000_000)
		self.assertEqual(contract.schedule[-1].kind, "Principal")
		self.assertEqual(
			balance(
				account(COMPANY, "investors"), frappe.db.get_value("Iran Investor", investor.name, "supplier")
			),
			-1_960_000_000,
		)
		self.assertEqual(balance(account(COMPANY, "commission_income")), -40_000_000)

	def test_investor_sees_only_their_own_account(self):
		mine = frappe.get_doc({"doctype": "Iran Investor", "full_name": "سرمایه‌گذار با ورود"}).insert()
		other = frappe.get_doc({"doctype": "Iran Investor", "full_name": "سرمایه‌گذار دیگر"}).insert()
		email = "investor.test@example.com"
		if frappe.db.exists("User", email):
			frappe.db.set_value("Iran Investor", {"user": email}, "user", None)
			frappe.delete_doc("User", email, force=True)
		mine.create_login(email, "Strong-Pass-1405")
		frappe.set_user(email)
		try:
			data = get_my_account(investor=other.name)
			self.assertEqual(data["investors"][0]["name"], mine.name)
			self.assertFalse(data["staff"])
		finally:
			frappe.set_user("Administrator")

	def test_branches(self):
		set_branches(["شعبه آزمایشی کرج", ""])
		self.assertTrue(frappe.db.exists("Branch", "شعبه آزمایشی کرج"))
		# Branch is an accounting dimension: entries carry their branch
		self.assertTrue(frappe.get_meta("Journal Entry Account").has_field("branch"))
		entry = journal(
			COMPANY,
			nowdate(),
			[{"account": self.cash, "debit": 1000}, {"account": self.bank, "credit": 1000}],
			"branch test",
			branch="شعبه آزمایشی کرج",
		)
		self.assertEqual(
			set(frappe.get_all("GL Entry", filters={"voucher_no": entry}, pluck="branch")),
			{"شعبه آزمایشی کرج"},
		)

	def test_car_file(self):
		set_branches(["شعبه آزمایشی کرج", ""])
		frappe.db.set_value("User", "Administrator", "iran_branch", "شعبه آزمایشی کرج")
		try:
			car = self.vehicle(ownership="Customer", owner_customer="Dealership Buyer", commission_rate=3)
		finally:
			frappe.db.set_value("User", "Administrator", "iran_branch", None)
		# The car takes the branch of whoever registers it, and its file starts with its arrival
		self.assertEqual(car.branch, "شعبه آزمایشی کرج")
		self.assertTrue(car.name.startswith("CAR-"))
		self.assertEqual(len(car.log), 1)
		# Technical and interior items to score are laid out on a new car
		self.assertEqual(
			{row.item for row in car.inspection},
			set(frappe.get_all("Iran Inspection Item", pluck="name")),
		)

		hood = frappe.db.get_value("Iran Body Part", {"diagram_key": "hood"})
		car.append("body_marks", {"body_part": hood, "condition": "رنگ دارد", "description": "لکه‌ای"})
		car.append("costs", {"service": "پولیش بدنه", "amount": 8_000_000, "status": "Planned"})
		car.status = "In Preparation"
		car.save()
		self.assertIn(hood, car.body_summary)
		self.assertGreaterEqual(len(car.log), 4)
		# A planned service is not a cost yet; once done it adds to the car's preparation
		self.assertEqual(car.preparation_total, 0)
		car.costs[0].status = "Done"
		car.save()
		self.assertEqual(car.preparation_total, 8_000_000)
		# Without an account or a workshop to owe, it is not in the books
		self.assertFalse(car.costs[0].journal_entry)

		# Only an administrator moves a car to another branch
		set_branches(["شعبه آزمایشی کرج", "شعبه آزمایشی تهران"])
		user = "lot.staff@example.com"
		if not frappe.db.exists("User", user):
			staff = frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": "کارمند", "send_welcome_email": 0}
			).insert()
			staff.add_roles("Accounts Manager", "Stock Manager", "Sales Manager")
		frappe.set_user(user)
		try:
			car.reload()
			car.branch = "شعبه آزمایشی تهران"
			self.assertRaises(frappe.ValidationError, car.save)
		finally:
			frappe.set_user("Administrator")

	def test_model_year_follows_where_the_car_was_made(self):
		# An Iranian car has a Jalali year, written in either digits
		self.assertEqual(self.vehicle(year="۱۴۰۲").year, "1402")
		self.assertRaises(frappe.ValidationError, self.vehicle, year="2023")
		# An imported car has a Gregorian year
		car = self.vehicle(car_model=self.imported_model, year="2019")
		self.assertEqual(car.made_in, "Imported Car")
		self.assertRaises(frappe.ValidationError, self.vehicle, car_model=self.imported_model, year="1398")

	def test_dashboard(self):
		from iran_erp.iran_dealership.dashboard import SERIES, get_dashboard

		data = get_dashboard(months=6)
		self.assertEqual(len(data["months"]["labels"]), 6)
		self.assertEqual(set(data["months"]["series"]), set(SERIES))
		series = data["months"]["series"]
		for i in range(6):
			self.assertEqual(
				series["net"][i],
				series["car_profit"][i] + series["interest"][i] - series["investor_profit"][i],
			)
		self.assertEqual(sum(a["count"] for a in data["ages"]), data["in_lot"])

	def test_model_specifications(self):
		from iran_erp.iran_dealership.doctype.iran_car_model.iran_car_model import spec_rows

		frappe.db.set_value("Iran Car Model", self.car_model, {"engine": "TU5", "engine_volume": 1587})
		frappe.clear_document_cache("Iran Car Model", self.car_model)
		rows = {r["label"]: r["value"] for r in spec_rows(self.car_model)}
		self.assertEqual(rows[frappe._("Engine")], "TU5")
		self.assertIn("۱۵۸۷", rows[frappe._("Engine Volume")])

	def test_reception_sees_the_car_not_the_books(self):
		from iran_erp.business import RECEPTION_ROLE, add_reception_user

		user = add_reception_user("پذیرش آزمایشی", "reception.test@example.com", "Reception-Test-1405")
		self.assertIn(RECEPTION_ROLE, frappe.get_roles(user))
		car = self.vehicle(purchase_price=1_000_000_000, seller=None)
		frappe.set_user(user)
		try:
			doc = frappe.get_doc("Iran Vehicle", car.name)
			doc.apply_fieldlevel_read_permissions()
			self.assertFalse(doc.get("purchase_price"))
			# Reception registers a car of its own; it belongs to the business
			mine = frappe.get_doc(
				{"doctype": "Iran Vehicle", "car_model": self.car_model, "year": "1402", "company": COMPANY}
			).insert()
			self.assertEqual(mine.ownership, "Business")
			self.assertFalse(frappe.has_permission("Iran Instalment Sale", "read"))
		finally:
			frappe.set_user("Administrator")

	def test_words(self):
		self.assertEqual(number_words(1_250_000), "یک میلیون و دویست و پنجاه هزار")
		self.assertEqual(amount_words(160_000_000), "صد و شصت میلیون ریال")
		self.assertEqual(number_words(1405), "یک هزار و چهارصد و پنج")
		self.assertEqual(date_words("2026-11-06"), "پانزدهم آبان یک هزار و چهارصد و پنج")
		self.assertEqual(date_words("2026-10-24"), "دوم آبان یک هزار و چهارصد و پنج")
		self.assertEqual(date_words("2026-10-25"), "سوم آبان یک هزار و چهارصد و پنج")
		self.assertEqual(date_words("2026-11-21"), "سی‌ام آبان یک هزار و چهارصد و پنج")
