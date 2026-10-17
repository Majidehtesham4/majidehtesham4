"""Sample data of a car dealership, to see the dealership pack at work.

	bench --site <site> execute iran_erp.iran_dealership.demo.create_dealership_demo
	bench --site <site> execute iran_erp.iran_dealership.demo.delete_dealership_demo

Two branches with three parkings; twenty cars of different models bought over the last four
months: the business's own cars, cars left by customers to be sold, and investors' cars (one
remittance still awaiting delivery); body marks, expert scores, preparation and repair services;
five instalment sales with their cheques, some paid and one overdue, one car already gone; and
five investors with different contracts: monthly profit with cheques, profit at the end paid by
transfer, a contract for one branch, a remittance, and a reinvested chain.

Every record made is logged, so delete_dealership_demo removes exactly what was added.
"""

import json
import random

import frappe
from frappe.utils import add_days, add_months, getdate, nowdate

from iran_erp.business import PACKS, apply_pack, set_branches, set_parkings
from iran_erp.demo import national_code

LOG_KEY = "iran_dealership_demo_records"
MILLION = 1_000_000

BRANCHES = ["شعبه مرکزی", "شعبه کرج"]
PARKINGS = [
	("پارکینگ اصلی", "شعبه مرکزی"),
	("پارکینگ طبقه منفی یک", "شعبه مرکزی"),
	("پارکینگ کرج", "شعبه کرج"),
]
SELLERS = ["نمایندگی ایران‌خودرو کد ۱۲۴", "نمایندگی سایپا کد ۸۸۰", "آقای مرادی (فروشنده خودرو)"]
WORKSHOPS = ["صافکاری استاد حسینی", "کارواش برتر"]
BUYERS = [
	("آقای کریمی", "09121110001"),
	("خانم رستمی", "09121110002"),
	("آقای جعفری", "09121110003"),
	("آقای موسوی", "09121110004"),
	("خانم شریفی", "09121110005"),
]
OWNERS = [
	("آقای حیدری", "09122220001", national_code("001234561")),
	("خانم نوروزی", "09122220002", national_code("001234562")),
	("آقای باقری", "09122220003", national_code("001234563")),
	("آقای عباسی", "09122220004", national_code("001234564")),
]
INVESTORS = [
	("آقای رضایی", "09123330001", national_code("007654322")),
	("خانم کاظمی", "09123330002", national_code("007654323")),
	("آقای نوری", "09123330003", national_code("007654324")),
	("آقای صادقی", "09123330004", national_code("007654325")),
	("خانم احمدی", "09123330005", national_code("007654321")),
]

# model, year, colour, mileage, purchase price (million rial), asking price (million rial)
CARS = [
	("ایران‌خودرو پژو ۲۰۷ اتوماتیک", "1403", "سفید", 18_000, 14_500, 16_800),
	("ایران‌خودرو دنا پلاس", "1402", "مشکی", 42_000, 13_200, 15_200),
	("سایپا شاهین اتوماتیک", "1404", "نقره‌ای", 3_000, 12_800, 14_600),
	("ایران‌خودرو تارا اتوماتیک", "1404", "سفید صدفی", 0, 17_500, 19_900),
	("مدیران‌خودرو چری تیگو ۷", "1402", "خاکستری", 35_000, 31_000, 35_500),
	("مدیران‌خودرو ام‌وی‌ام X55", "1401", "سفید", 61_000, 18_400, 21_000),
	("سایپا کوییک اتوماتیک", "1403", "قرمز", 22_000, 7_900, 9_200),
	("ایران‌خودرو سورن", "1400", "نوک‌مدادی", 98_000, 8_600, 9_900),
	("کرمان‌موتور کی‌ام‌سی K7", "1403", "مشکی", 15_000, 27_000, 30_500),
	("پارس‌خودرو ال۹۰", "1399", "دلفینی", 120_000, 6_200, 7_300),
	("هیوندای توسان", "2017", "سفید", 140_000, 34_000, 38_500),
	("تویوتا کمری", "2016", "مشکی", 165_000, 39_000, 44_000),
	("ایران‌خودرو پژو پارس", "1402", "سفید", 51_000, 9_800, 11_300),
	("سایپا ساینا", "1401", "نقره‌ای", 70_000, 5_400, 6_300),
	("کیا سراتو", "2018", "سرمه‌ای", 110_000, 22_500, 25_800),
	("مدیران‌خودرو چری آریزو ۶", "1403", "سفید", 9_000, 21_000, 23_900),
	("کرمان‌موتور جک S5", "1402", "آبی", 47_000, 16_300, 18_700),
	("ایران‌خودرو ری‌را", "1404", "سفید", 0, 15_800, 17_900),
	("نیسان قشقایی", "2017", "خاکستری", 132_000, 26_000, 29_800),
	("بهمن‌موتور فیدلیتی", "1403", "مشکی", 19_000, 24_000, 27_400),
]

# index of the car → who owns it
CUSTOMER_CARS = {8: 0, 10: 1, 11: 2, 18: 3}
INVESTOR_CARS = {3: 2, 17: 2}  # remittances of «آقای نوری»
SOLD = {0: 0, 1: 1, 6: 2, 9: 3, 12: 4}  # car → buyer
EXITED = {9}

SERVICES = [
	("کارواش VIP", 4),
	("پولیش بدنه", 25),
	("واکس", 6),
	("تمیز کردن چراغ‌ها", 3),
	("کارشناسی", 5),
	("صافکاری", 60),
	("PDR (صافکاری بدون رنگ)", 35),
	("رنگ", 90),
	("تعویض لاستیک", 120),
	("روکش صندلی", 45),
	("سرویس و تعویض روغن", 18),
	("انتقال سند", 12),
]


def _records() -> list:
	"""The sample records made so far, read from the database: the cached defaults can lag behind
	a delete made by another process."""
	value = frappe.db.get_value("DefaultValue", {"parent": "__default", "defkey": LOG_KEY}, "defvalue")
	return json.loads(value or "[]")


def _log(doctype, name):
	records = _records()
	records.append([doctype, name])
	frappe.db.set_default(LOG_KEY, json.dumps(records))


def _new(doctype, values, submit=False):
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.flags.ignore_permissions = True
	doc.insert()
	if submit:
		doc.submit()
	_log(doctype, doc.name)
	return doc


def _party(doctype, name, extra=None):
	field = {"Customer": "customer_name", "Supplier": "supplier_name"}[doctype]
	existing = frappe.db.get_value(doctype, {field: name})
	if existing:
		return existing
	return _new(doctype, {field: name, **(extra or {})}).name


def _account(company, number=None, account_type=None):
	filters = {"company": company, "is_group": 0}
	if number:
		filters["account_number"] = number
	if account_type:
		filters["account_type"] = account_type
	return frappe.db.get_value("Account", filters, "name", order_by="account_number asc")


@frappe.whitelist()
def create_dealership_demo(company: str | None = None):
	frappe.only_for("System Manager")
	if _records():
		return "Dealership sample data is already there; delete it first."
	company = company or frappe.defaults.get_global_default("company")
	# Car files keep their summaries and log lines as text, so write them in Persian even when this
	# runs from the command line
	frappe.local.lang = "fa"
	random.seed(1405)
	today = getdate(nowdate())

	features = [key for key, *_rest in PACKS["Car Dealership"]["features"]]
	frappe.db.set_single_value(
		"Iran Setup",
		{
			"business_type": "Car Dealership",
			"business_features": json.dumps(features),
			"branches": "\n".join(BRANCHES),
			"parkings": "\n".join(name for name, _branch in PARKINGS),
		},
	)
	if not frappe.db.get_single_value("Iran ERP Settings", "trade_name"):
		frappe.db.set_single_value(
			"Iran ERP Settings", {"trade_name": "نمایشگاه خودرو ورون", "trade_phone": "021-88776655"}
		)
	set_branches(BRANCHES, company)
	apply_pack("Car Dealership", company, features)
	for name, branch in PARKINGS:
		set_parkings([name], branch)
	frappe.db.set_value("User", "Administrator", "iran_branch", BRANCHES[0])

	cash = _account(company, "1101")
	bank = _account(company, account_type="Bank")
	sellers = [_party("Supplier", name) for name in SELLERS]
	workshops = [_party("Supplier", name) for name in WORKSHOPS]
	buyers = [_party("Customer", name, {"mobile_no": mobile}) for name, mobile in BUYERS]
	owners = [
		_party("Customer", name, {"mobile_no": mobile, "iran_national_id": national_id})
		for name, mobile, national_id in OWNERS
	]
	investors = []
	for name, mobile, national_id in INVESTORS:
		existing = frappe.db.get_value("Iran Investor", {"full_name": name})
		investors.append(
			existing
			or _new("Iran Investor", {"full_name": name, "mobile": mobile, "national_id": national_id}).name
		)

	# ---------------------------------------------------------- investors' contracts
	contract = _new(
		"Iran Investment Contract",
		{
			"investor": investors[0],
			"company": company,
			"amount": 10_000 * MILLION,
			"received_to": bank,
			"start_date": add_months(today, -3),
			"months": 6,
			"monthly_rate": 4,
			"profit_payment": "Monthly",
		},
		submit=True,
	)
	contract.reload()
	for name in contract.issue_cheques(
		bank_account=bank, first_number="880101", posting_date=contract.start_date
	):
		_log("Iran Cheque", name)
	contract.reload()
	contract.accrue_profit(today)
	for row in contract.schedule:
		if row.kind == "Profit" and getdate(row.due_date) <= today:
			frappe.get_doc("Iran Cheque", row.cheque).take_action("clear", date=row.due_date)
	contract.reload()
	contract.update_status()

	_new(
		"Iran Investment Contract",
		{
			"investor": investors[1],
			"company": company,
			"amount": 5_000 * MILLION,
			"received_to": bank,
			"start_date": add_months(today, -1),
			"months": 12,
			"monthly_rate": 3.5,
			"profit_payment": "At the End",
		},
		submit=True,
	)
	_new(
		"Iran Investment Contract",
		{
			"investor": investors[4],
			"company": company,
			"amount": 3_000 * MILLION,
			"received_to": bank,
			"scope": "Branch",
			"branch": BRANCHES[1],
			"start_date": add_months(today, -2),
			"months": 6,
			"monthly_rate": 4,
			"profit_payment": "Monthly",
		},
		submit=True,
	)
	# A chain: profits put back in after two months
	first = _new(
		"Iran Investment Contract",
		{
			"investor": investors[3],
			"company": company,
			"amount": 4_000 * MILLION,
			"received_to": bank,
			"start_date": add_months(today, -4),
			"months": 6,
			"monthly_rate": 4.5,
			"profit_payment": "Monthly",
		},
		submit=True,
	)
	first.reload()
	for name in first.issue_cheques(bank_account=bank, first_number="880301", posting_date=first.start_date):
		_log("Iran Cheque", name)
	first.reload()
	for row in first.schedule[:2]:
		first.accrue_profit(row.due_date, rows=[row])
		frappe.get_doc("Iran Cheque", row.cheque).take_action("clear", date=row.due_date)
	first.reload()
	second = first.reinvest(rows=[3, 4], months=4, monthly_rate=4.5)
	_log("Iran Investment Contract", second)
	frappe.get_doc("Iran Investment Contract", second).submit()

	# ---------------------------------------------------------- cars
	cars = []
	for i, (model, year, color, mileage, buy, ask) in enumerate(CARS):
		entry = add_days(today, -random.randint(5, 110))
		branch = BRANCHES[1] if i % 4 == 3 else BRANCHES[0]
		parking = PARKINGS[2][0] if branch == BRANCHES[1] else PARKINGS[i % 2][0]
		values = {
			"car_model": model,
			"year": year,
			"color": color,
			"mileage": mileage,
			"company": company,
			"plate": f"{random.randint(11, 99)} {random.choice('بجدسصطقلمنوهی')} {random.randint(111, 999)} ایران {random.randint(10, 99)}",
			"chassis_number": f"NA{random.randint(10**12, 10**13 - 1)}",
			"entry_date": entry,
			"branch": branch,
			"parking": parking,
			"parking_spot": str(random.randint(1, 40)),
			"asking_price": ask * MILLION,
			"minimum_price": int(ask * 0.96) * MILLION,
			"status": "Ready for Sale",
			"doc_ownership": 1,
			"doc_card": 1,
			"doc_insurance": 1,
			"doc_spare_key": i % 3 != 0,
			"doc_fines_clear": 1,
			"doc_tax_clear": i % 5 != 0,
		}
		if i in CUSTOMER_CARS:
			values.update(
				{
					"ownership": "Customer",
					"owner_customer": owners[CUSTOMER_CARS[i]],
					"commission_rate": 2,
					"charge_costs_to_owner": 1,
					"owner_mobile": OWNERS[CUSTOMER_CARS[i]][1],
				}
			)
		elif i in INVESTOR_CARS:
			values.update(
				{
					"ownership": "Business",
					"status": "Awaiting Delivery" if i == 17 else "Ready for Sale",
					"expected_delivery": add_days(today, 40) if i == 17 else None,
				}
			)
		else:
			values.update(
				{
					"ownership": "Business",
					"purchase_date": entry,
					"purchase_price": buy * MILLION,
					"seller": sellers[i % len(sellers)] if i % 2 else None,
					"paid_from": None if i % 2 else bank,
				}
			)
		car = _new("Iran Vehicle", values)
		cars.append(car)

	# Body marks, scores and services on most cars
	parts = frappe.get_all("Iran Body Part", pluck="name")
	conditions = frappe.get_all("Iran Body Condition", pluck="name")
	for i, car in enumerate(cars):
		car.reload()
		if i % 3 != 2:
			for _n in range(random.randint(1, 3)):
				car.append(
					"body_marks",
					{
						"body_part": random.choice(parts),
						"condition": random.choice(conditions),
						"description": random.choice(["", "جزئی", "در حد یک قلم", "کارشناسی تأیید شد"]),
					},
				)
		for row in car.inspection:
			row.score = random.randint(55, 100) if row.measure == "Percent" else random.randint(6, 10)
		car.inspection_note = random.choice(
			["فنی سالم", "موتور و گیربکس سالم؛ لاستیک‌ها نیاز به تعویض", "بدون ایراد فنی"]
		)
		if i not in INVESTOR_CARS or i == 3:
			for service, cost in random.sample(SERVICES, random.randint(2, 4)):
				outside = cost >= 35
				car.append(
					"costs",
					{
						"date": add_days(car.entry_date, random.randint(1, 4)),
						"service": service,
						"scope": "Some Parts"
						if service in ("پولیش بدنه", "رنگ", "صافکاری", "PDR (صافکاری بدون رنگ)")
						else "Whole Car",
						"body_parts": "درب جلو راست، گلگیر جلو راست" if service in ("رنگ", "صافکاری") else "",
						"done_by": "Outside" if outside else "Own Workshop",
						"vendor": workshops[0] if outside else None,
						"paid_from": None if outside else cash,
						"amount": cost * MILLION,
						"status": "Done",
					},
				)
		if i in (2, 13):
			car.status = "In Preparation"
			car.append(
				"costs",
				{
					"date": today,
					"service": "پولیش بدنه",
					"scope": "Whole Car",
					"amount": 25 * MILLION,
					"status": "Planned",
				},
			)
		car.flags.ignore_permissions = True
		car.save()

	# Remittances of «آقای نوری»: one delivered, one awaiting delivery
	for i in INVESTOR_CARS:
		_new(
			"Iran Investment Contract",
			{
				"investor": investors[2],
				"company": company,
				"contract_type": "Car Remittance",
				"vehicle": cars[i].name,
				"amount": CARS[i][4] * MILLION,
				"start_date": add_days(cars[i].entry_date, -60),
				"months": 3,
				"commission_rate": 2,
				"remittance_number": f"H-{random.randint(100000, 999999)}",
				"expected_delivery": add_days(today, 40) if i == 17 else cars[i].entry_date,
			},
			submit=True,
		)
		frappe.db.set_value("Iran Vehicle", cars[i].name, "commission_rate", 2)

	# One car reserved
	cars[15].reload()
	cars[15].reserve(customer=buyers[0], note="بیعانه ۲۰۰ میلیون ریال")

	# ---------------------------------------------------------- instalment sales
	plans = [(0.5, 6, 6), (0.4, 5, 10), (0.6, 4, 8), (1.0, 0, 1), (0.5, 5.5, 12)]
	for n, (i, buyer) in enumerate(SOLD.items()):
		car = frappe.get_doc("Iran Vehicle", cars[i].name)
		share, rate, months = plans[n]
		posting = add_days(car.entry_date, random.randint(8, 20))
		posting = min(getdate(posting), add_days(today, -1))
		price = car.asking_price
		down = round(price * share / MILLION) * MILLION
		sale = _new(
			"Iran Instalment Sale",
			{
				"company": company,
				"customer": buyers[buyer],
				"vehicle": car.name,
				"branch": car.branch,
				"posting_date": posting,
				"sale_price": price,
				"down_payment": down if share < 1 else price - 100 * MILLION,
				"down_payment_account": bank,
				"monthly_rate": rate,
				"months": months,
				"first_due_date": add_months(posting, 1),
				"late_fee_rate": 3,
			},
			submit=True,
		)
		sale.reload()
		if n != 2:  # the third buyer pays in cash, without cheques
			for name in sale.make_cheques(
				bank=random.choice(["بانک ملت", "بانک صادرات", "بانک ملی"]),
				first_number=str(452101 + n * 100),
			):
				_log("Iran Cheque", name)
			sale.reload()
			# The cheques that fell due cleared, except the last one of the second buyer
			due = [r for r in sale.schedule if getdate(r.due_date) <= today]
			for k, row in enumerate(due):
				if n == 1 and k == len(due) - 1:
					continue
				frappe.get_doc("Iran Cheque", row.cheque).take_action(
					"clear", date=row.due_date, bank_account=bank
				)
		sale.reload()
		sale.recognize_interest(today)
		sale.update_status(today)
		if i in EXITED:
			car.reload()
			car.record_exit(date=add_days(posting, 3), delivered_to=BUYERS[buyer][0])

	_website(cars)
	frappe.db.commit()
	return "Dealership sample data created: 20 cars, 5 investors, 5 instalment sales."


# Options a buyer looks for, by how premium the car is
FEATURES = [
	["ایربگ دوگانه", "ترمز ABS", "سیستم صوتی بلوتوث"],
	["دوربین دنده عقب", "سنسور پارک", "کروز کنترل", "ایربگ دوگانه"],
	["سانروف", "صندلی برقی", "دوربین ۳۶۰ درجه", "استارت دکمه‌ای", "نمایشگر لمسی"],
]
HEADLINES = ["بدون رنگ، کم‌کار", "تک‌مالک، سرویس‌های شرکتی", "بیمه کامل، آماده تحویل", "فول، کارشناسی شده"]
REQUESTS = [
	("آقای جعفری", "09121110001", "Test Drive", "شنبه صبح می‌توانم بیایم؟"),
	("خانم مرادی", "09351110002", "Instalment Plan", "با ۴۰ درصد پیش‌پرداخت و ۱۲ ماه"),
	("آقای کریمی", "09191110003", "Call Me Back", ""),
	("خانم نوروزی", "09021110004", "Question", "خودرو تصادفی است؟"),
]


def _website(cars):
	"""The showroom website: most cars on it with options and a headline, two experts, and a few
	requests from customers."""
	settings = frappe.get_single("Iran Showroom Settings")
	if not settings.experts:
		settings.update(
			{
				"enabled": 1,
				"tagline": "خرید نقد و اقساط، با کارشناسی شفاف",
				"phone": "02188776655",
				"whatsapp": "989121234567",
				"working_hours": "شنبه تا پنجشنبه ۹ تا ۲۰",
				"address": "تهران، بزرگراه شهید همت، نمایشگاه خودرو ورون",
			}
		)
		settings.append(
			"experts",
			{
				"full_name": "مهندس رضا امیری",
				"job_title": "کارشناس فروش",
				"user": "Administrator",
				"mobile": "09121234501",
				"whatsapp": "989121234501",
			},
		)
		settings.append(
			"experts",
			{
				"full_name": "سارا محمدی",
				"job_title": "کارشناس فروش اقساطی",
				"mobile": "09121234502",
				"branch": BRANCHES[1],
			},
		)
		settings.flags.ignore_permissions = True
		settings.save()
	shown = []
	for i, car in enumerate(cars):
		car.reload()
		if car.status not in ("Ready for Sale", "Reserved", "In Preparation"):
			continue
		price = car.asking_price or 0
		car.update(
			{
				"show_on_website": 1,
				"featured": i in (2, 4, 11),
				"website_headline": HEADLINES[i % len(HEADLINES)],
				"website_features": "\n".join(
					FEATURES[0 if price < 15_000 * MILLION else 1 if price < 30_000 * MILLION else 2]
				),
			}
		)
		car.flags.ignore_permissions = True
		car.save()
		shown.append(car)
	for (name, mobile, kind, message), car in zip(REQUESTS, shown, strict=False):
		_new(
			"Iran Car Inquiry",
			{
				"full_name": name,
				"mobile": mobile,
				"kind": kind,
				"vehicle": car.name,
				"message": message,
				"source": "Website",
			},
		)


@frappe.whitelist()
def delete_dealership_demo():
	"""Cancels and deletes what create_dealership_demo made, newest first."""
	frappe.only_for("System Manager")
	records = _records()

	def each(doctype):
		for kind, name in reversed(records):
			if kind == doctype and frappe.db.exists(doctype, name):
				doc = frappe.get_doc(doctype, name)
				doc.flags.ignore_permissions = doc.flags.ignore_links = True
				yield doc

	# Contracts first (their entries go with them), then the cheques they hold, then the rest
	for doctype in ("Iran Instalment Sale", "Iran Investment Contract", "Iran Cheque"):
		for doc in each(doctype):
			if doc.docstatus == 1:
				doc.cancel()
	for doc in each("Iran Vehicle"):
		_cancel_vehicle_entries(doc)
	for doctype in (
		"Iran Car Inquiry",
		"Iran Instalment Sale",
		"Iran Investment Contract",
		"Iran Cheque",
		"Iran Vehicle",
		"Iran Investor",
		"Customer",
		"Supplier",
	):
		for doc in each(doctype):
			frappe.delete_doc(doctype, doc.name, force=True, ignore_permissions=True)
			if doctype == "Iran Investor" and doc.supplier and frappe.db.exists("Supplier", doc.supplier):
				frappe.delete_doc("Supplier", doc.supplier, force=True, ignore_permissions=True)
	frappe.db.set_default(LOG_KEY, "[]")
	frappe.db.commit()
	return "Dealership sample data deleted."


def _cancel_vehicle_entries(car):
	for name in [car.purchase_entry, *[row.journal_entry for row in car.costs]]:
		if name and frappe.db.get_value("Journal Entry", name, "docstatus") == 1:
			entry = frappe.get_doc("Journal Entry", name)
			entry.flags.ignore_permissions = True
			entry.cancel()
	frappe.db.set_value("Iran Vehicle", car.name, {"purchase_entry": None, "sale_contract": None})
	frappe.db.sql("update `tabIran Vehicle Cost` set journal_entry = null where parent = %s", car.name)
