"""Persian sample data for trying the system: an office furniture and IT equipment company.

    bench --site <site> execute iran_erp.demo.create_demo_data
    bench --site <site> execute iran_erp.demo.delete_demo_data

Every record created is logged, so delete_demo_data removes exactly what was added.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from iran_erp.utils.national_id import is_valid_legal_national_id, is_valid_national_code

LOG_KEY = "iran_demo_records"

ITEM_GROUPS = ["مبلمان اداری", "تجهیزات رایانه‌ای", "مواد اولیه تولید", "خدمات"]

# code, name, group, unit, stock item, buying price, selling price (rial)
ITEMS = [
	("DESK-01", "میز مدیریتی چوبی", "مبلمان اداری", "Nos", 1, 0, 420_000_000),
	("DESK-02", "میز کارمندی", "مبلمان اداری", "Nos", 1, 0, 180_000_000),
	("CHAIR-01", "صندلی اداری ارگونومیک", "مبلمان اداری", "Nos", 1, 95_000_000, 135_000_000),
	("CAB-01", "کمد بایگانی فلزی", "مبلمان اداری", "Nos", 1, 110_000_000, 150_000_000),
	("LAPTOP-01", "لپ‌تاپ اداری ۱۵ اینچ", "تجهیزات رایانه‌ای", "Nos", 1, 520_000_000, 610_000_000),
	("MON-01", "مانیتور ۲۴ اینچ", "تجهیزات رایانه‌ای", "Nos", 1, 95_000_000, 118_000_000),
	("PRN-01", "پرینتر لیزری", "تجهیزات رایانه‌ای", "Nos", 1, 140_000_000, 172_000_000),
	("RM-MDF", "ورق MDF ۱۶ میل", "مواد اولیه تولید", "Nos", 1, 38_000_000, 0),
	("RM-LEG", "پایه فلزی میز", "مواد اولیه تولید", "Nos", 1, 12_000_000, 0),
	("RM-SCREW", "بسته پیچ و اتصالات", "مواد اولیه تولید", "Nos", 1, 1_500_000, 0),
	("RM-EDGE", "نوار لبه PVC", "مواد اولیه تولید", "Meter", 1, 150_000, 0),
	("SRV-INST", "نصب و راه‌اندازی", "خدمات", "Hour", 0, 0, 6_000_000),
	("SRV-SUP", "قرارداد پشتیبانی سالانه", "خدمات", "Nos", 0, 0, 90_000_000),
]

# name, type, group, city, mobile, email
CUSTOMERS = [
	("شرکت فن‌آوران پارس", "Company", "Commercial", "تهران", "09121000001", "info@fanavaran.example"),
	(
		"شرکت بازرگانی آریا تجارت",
		"Company",
		"Commercial",
		"اصفهان",
		"09131000002",
		"sales@ariatejarat.example",
	),
	(
		"هلدینگ ساختمانی نوین سازه",
		"Company",
		"Commercial",
		"تهران",
		"09121000003",
		"office@novinsaze.example",
	),
	("مؤسسه آموزشی اندیشه نو", "Company", "Non Profit", "مشهد", "09151000004", "admin@andisheno.example"),
	("شرکت پخش البرز", "Company", "Commercial", "کرج", "09121000005", "buy@alborzpakhsh.example"),
	("فروشگاه لوازم اداری کیان", "Company", "Commercial", "شیراز", "09171000006", "kian@kianstore.example"),
	("علی محمدی", "Individual", "Individual", "تبریز", "09141000007", "ali.mohammadi@mail.example"),
	("مریم احمدی", "Individual", "Individual", "تهران", "09121000008", "maryam.ahmadi@mail.example"),
]

# name, group, city
SUPPLIERS = [
	("شرکت تولیدی چوب‌ساز", "Raw Material", "قم"),
	("صنایع فلزی پویا", "Raw Material", "تهران"),
	("شرکت رایان سیستم", "Distributor", "تهران"),
	("فروشگاه ابزار و یراق امین", "Hardware", "تهران"),
	("شرکت حمل‌ونقل سریع‌السیر", "Services", "تهران"),
]


SELLING_PRICE = {code: selling for code, _name, _group, _uom, _stock, _buying, selling in ITEMS}


def lines(items):
	"""Selling lines at list price; code-created documents do not look prices up themselves."""
	return [{"item_code": code, "qty": qty, "rate": SELLING_PRICE[code]} for code, qty in items]


class Demo:
	def __init__(self, company: str):
		self.company = company
		self.abbr = frappe.get_cached_value("Company", company, "abbr")
		self.cost_center = frappe.get_cached_value("Company", company, "cost_center")
		self.stores = self.warehouse("Stores")
		self.wip = self.warehouse("Work In Progress") or self.stores
		self.finished = self.warehouse("Finished Goods") or self.stores
		self.log = []
		fiscal_start = frappe.db.get_value(
			"Fiscal Year",
			{"year_start_date": ("<=", nowdate()), "year_end_date": (">=", nowdate()), "disabled": 0},
			"year_start_date",
			order_by="year_start_date desc",
		)
		self.first_day = getdate(fiscal_start or nowdate())

	def warehouse(self, name):
		return frappe.db.get_value(
			"Warehouse", {"company": self.company, "warehouse_name": name, "is_group": 0}
		) or frappe.db.get_value("Warehouse", {"company": self.company, "is_group": 0})

	def day(self, days_ago: int) -> str:
		"""A date some days back, but never before the current fiscal year."""
		return str(max(getdate(add_days(nowdate(), -days_ago)), self.first_day))

	def add(self, data: dict, submit: bool = False):
		doc = frappe.get_doc(data)
		# Code-created documents do not pull tax rows from their template on their own
		if doc.get("taxes_and_charges") and not doc.get("taxes"):
			doc.append_taxes_from_master()
		doc.flags.ignore_permissions = True
		doc.insert()
		if submit:
			doc.submit()
		self.log.append([doc.doctype, doc.name])
		return doc

	def add_existing(self, doc, submit: bool = True):
		"""Insert a document built by an ERPNext mapper (make_delivery_note and the like)."""
		doc.flags.ignore_permissions = True
		doc.insert()
		if submit:
			doc.submit()
		self.log.append([doc.doctype, doc.name])
		return doc

	def ensure(self, doctype: str, name: str, data: dict):
		"""Create a master record only if it is missing; existing ones are left alone and not logged."""
		if frappe.db.exists(doctype, name):
			return name
		return self.add({"doctype": doctype, **data}).name

	def vat_template(self, doctype):
		return frappe.db.get_value(doctype, {"company": self.company, "is_default": 1, "disabled": 0})

	# --- masters ---------------------------------------------------------

	def masters(self):
		for group in ITEM_GROUPS:
			self.ensure(
				"Item Group", group, {"item_group_name": group, "parent_item_group": "All Item Groups"}
			)
		for designation in ("مدیر فروش", "حسابدار", "کارشناس انبار", "سرپرست تولید"):
			self.ensure("Designation", designation, {"designation_name": designation})

		for code, name, group, uom, is_stock, buying, selling in ITEMS:
			if frappe.db.exists("Item", code):
				continue
			self.add(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": name,
					"description": name,
					"item_group": group,
					"stock_uom": uom,
					"is_stock_item": is_stock,
					"include_item_in_manufacturing": 1 if group == "مواد اولیه تولید" else 0,
					"valuation_rate": buying or selling * 0.6,
					"item_defaults": [{"company": self.company, "default_warehouse": self.stores}],
				}
			)
			for price_list, rate in (("Standard Selling", selling), ("Standard Buying", buying)):
				if rate and frappe.db.exists("Price List", price_list):
					self.add(
						{
							"doctype": "Item Price",
							"item_code": code,
							"price_list": price_list,
							"price_list_rate": rate,
						}
					)

		territory = "Iran" if frappe.db.exists("Territory", "Iran") else "All Territories"
		for index, (name, kind, group, city, mobile, email) in enumerate(CUSTOMERS):
			if frappe.db.exists("Customer", {"customer_name": name}):
				continue
			ids = (
				{"iran_national_id": national_code(f"00{index}1234{index}5")}
				if kind == "Individual"
				else {"iran_national_id": legal_id(f"1010{index}2345{index}"), "iran_economic_code": None}
			)
			if kind != "Individual":
				ids["iran_economic_code"] = ids["iran_national_id"]
			customer = self.add(
				{
					"doctype": "Customer",
					"customer_name": name,
					"customer_type": kind,
					"customer_group": group
					if frappe.db.exists("Customer Group", group)
					else "All Customer Groups",
					"territory": territory,
					**ids,
				}
			)
			self.contact_and_address("Customer", customer.name, name, city, mobile, email)

		for index, (name, group, city) in enumerate(SUPPLIERS):
			if frappe.db.exists("Supplier", {"supplier_name": name}):
				continue
			national_id = legal_id(f"1020{index}3456{index}")
			supplier = self.add(
				{
					"doctype": "Supplier",
					"supplier_name": name,
					"supplier_type": "Company",
					"supplier_group": group
					if frappe.db.exists("Supplier Group", group)
					else "All Supplier Groups",
					"iran_national_id": national_id,
					"iran_economic_code": national_id,
				}
			)
			self.contact_and_address("Supplier", supplier.name, name, city, f"0912200000{index}", None)

	def contact_and_address(self, doctype, docname, title, city, mobile, email):
		link = [{"link_doctype": doctype, "link_name": docname}]
		self.add(
			{
				"doctype": "Address",
				"address_title": title,
				"address_type": "Billing",
				"address_line1": f"{city}، خیابان آزادی، پلاک ۱۲",
				"city": city,
				"country": "Iran",
				"pincode": "1234567890",
				"links": link,
			}
		)
		contact = {
			"doctype": "Contact",
			"first_name": title,
			"links": link,
			"phone_nos": [{"phone": mobile, "is_primary_mobile_no": 1}],
		}
		if email:
			contact["email_ids"] = [{"email_id": email, "is_primary": 1}]
		self.add(contact)

	def customer(self, index):
		return frappe.db.get_value("Customer", {"customer_name": CUSTOMERS[index][0]})

	def supplier(self, index):
		return frappe.db.get_value("Supplier", {"supplier_name": SUPPLIERS[index][0]})

	# --- stock and manufacturing ------------------------------------------

	def stock(self):
		items = [
			("RM-MDF", 60, 38_000_000),
			("RM-LEG", 200, 12_000_000),
			("RM-SCREW", 80, 1_500_000),
			("RM-EDGE", 500, 150_000),
			("CHAIR-01", 40, 95_000_000),
			("CAB-01", 15, 110_000_000),
			("LAPTOP-01", 12, 520_000_000),
			("MON-01", 25, 95_000_000),
			("PRN-01", 8, 140_000_000),
			("DESK-01", 6, 250_000_000),
		]
		# Opening stock is balanced against the temporary opening account, not booked as a gain
		opening = opening_account(self.company)
		self.add(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": self.company,
				"posting_date": self.day(40),
				"set_posting_time": 1,
				"remarks": "موجودی اول دوره (داده‌ی نمونه)",
				"items": [
					{
						"item_code": code,
						"qty": qty,
						"basic_rate": rate,
						"t_warehouse": self.stores,
						"expense_account": opening,
					}
					for code, qty, rate in items
				],
			},
			submit=True,
		)

	def manufacturing(self):
		from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

		boms = {}
		for item, materials in (
			("DESK-02", [("RM-MDF", 2), ("RM-LEG", 4), ("RM-SCREW", 1), ("RM-EDGE", 6)]),
			("DESK-01", [("RM-MDF", 4), ("RM-LEG", 4), ("RM-SCREW", 2), ("RM-EDGE", 10)]),
		):
			boms[item] = self.add(
				{
					"doctype": "BOM",
					"item": item,
					"company": self.company,
					"quantity": 1,
					"is_active": 1,
					"is_default": 1,
					"rm_cost_as_per": "Valuation Rate",
					"items": [{"item_code": code, "qty": qty} for code, qty in materials],
				},
				submit=True,
			).name

		def work_order(item, qty, days_ago):
			return self.add(
				{
					"doctype": "Work Order",
					"production_item": item,
					"bom_no": boms[item],
					"qty": qty,
					"company": self.company,
					"source_warehouse": self.stores,
					"wip_warehouse": self.wip,
					"fg_warehouse": self.finished,
					"planned_start_date": f"{self.day(days_ago)} 08:00:00",
				},
				submit=True,
			)

		# One order half produced, one not started
		started = work_order("DESK-02", 10, 20)
		for purpose in ("Material Transfer for Manufacture", "Manufacture"):
			entry = frappe.get_doc(make_stock_entry(started.name, purpose, 6))
			entry.posting_date = self.day(15)
			entry.set_posting_time = 1
			self.add_existing(entry)
		work_order("DESK-01", 4, 3)

	# --- buying ---------------------------------------------------------

	def buying(self):
		purchase_vat = self.vat_template("Purchase Taxes and Charges Template")
		self.add(
			{
				"doctype": "Purchase Order",
				"company": self.company,
				"supplier": self.supplier(0),
				"transaction_date": self.day(10),
				"schedule_date": add_days(nowdate(), 10),
				"set_warehouse": self.stores,
				"taxes_and_charges": purchase_vat,
				"items": [
					{"item_code": "RM-MDF", "qty": 40, "rate": 38_000_000},
					{"item_code": "RM-EDGE", "qty": 300, "rate": 150_000},
				],
			},
			submit=True,
		)
		invoice = self.purchase_invoice(
			self.supplier(2),
			self.day(25),
			[("LAPTOP-01", 5, 520_000_000), ("MON-01", 10, 95_000_000)],
			purchase_vat,
			bill_no="RS-14051",
		)
		self.pay("Purchase Invoice", invoice.name, self.day(20))
		self.purchase_invoice(
			self.supplier(1), self.day(8), [("RM-LEG", 100, 12_000_000)], purchase_vat, bill_no="PF-882"
		)

	def purchase_invoice(self, supplier, date, items, taxes, bill_no):
		return self.add(
			{
				"doctype": "Purchase Invoice",
				"company": self.company,
				"supplier": supplier,
				"posting_date": date,
				"set_posting_time": 1,
				"bill_no": bill_no,
				"bill_date": date,
				"update_stock": 1,
				"set_warehouse": self.stores,
				"taxes_and_charges": taxes,
				"items": [{"item_code": code, "qty": qty, "rate": rate} for code, qty, rate in items],
			},
			submit=True,
		)

	# --- selling ----------------------------------------------------------

	def selling(self):
		from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

		sales_vat = self.vat_template("Sales Taxes and Charges Template")
		self.add(
			{
				"doctype": "Quotation",
				"company": self.company,
				"quotation_to": "Customer",
				"party_name": self.customer(2),
				"transaction_date": self.day(5),
				"valid_till": add_days(nowdate(), 25),
				"taxes_and_charges": sales_vat,
				"items": lines([("DESK-01", 3), ("DESK-02", 20), ("CHAIR-01", 23)]),
			},
			submit=True,
		)
		order = self.add(
			{
				"doctype": "Sales Order",
				"company": self.company,
				"customer": self.customer(3),
				"transaction_date": self.day(12),
				"delivery_date": add_days(nowdate(), 7),
				"set_warehouse": self.stores,
				"taxes_and_charges": sales_vat,
				"items": lines([("CHAIR-01", 15), ("CAB-01", 4), ("SRV-INST", 8)]),
			},
			submit=True,
		)
		delivery = make_delivery_note(order.name)
		delivery.posting_date = self.day(4)
		delivery.set_posting_time = 1
		for row in delivery.items:
			if row.item_code == "CHAIR-01":
				row.qty = 10
		delivery.items = [row for row in delivery.items if row.item_code != "SRV-INST"]
		self.add_existing(delivery)

		paid = self.sales_invoice(
			self.customer(0),
			self.day(30),
			[("LAPTOP-01", 4), ("MON-01", 4), ("SRV-INST", 6), ("SRV-SUP", 1)],
			sales_vat,
		)
		self.pay("Sales Invoice", paid.name, self.day(26))
		self.sales_invoice(
			self.customer(1), self.day(35), [("CHAIR-01", 8), ("CAB-01", 3)], sales_vat, due_days=10
		)
		self.sales_invoice(self.customer(6), self.day(6), [("PRN-01", 1), ("SRV-INST", 2)], sales_vat)
		self.sales_invoice(self.customer(4), self.day(2), [("DESK-01", 1), ("CHAIR-01", 2)], sales_vat)
		# A draft waiting for review
		self.sales_invoice(self.customer(7), self.day(0), [("MON-01", 2)], sales_vat, submit=False)

	def sales_invoice(self, customer, date, items, taxes, due_days=30, submit=True):
		return self.add(
			{
				"doctype": "Sales Invoice",
				"company": self.company,
				"customer": customer,
				"posting_date": date,
				"set_posting_time": 1,
				"due_date": add_days(date, due_days),
				"update_stock": 1,
				"set_warehouse": self.stores,
				"taxes_and_charges": taxes,
				"items": lines(items),
			},
			submit=submit,
		)

	def pay(self, doctype, name, date):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		entry = get_payment_entry(doctype, name)
		entry.posting_date = date
		entry.reference_no = f"DEMO-{name}"
		entry.reference_date = date
		return self.add_existing(entry)

	# --- crm, projects, support, people, website --------------------------

	def crm(self):
		campaign = "نمایشگاه مبلمان اداری ۱۴۰۵"
		self.ensure("UTM Campaign", campaign, {"name": campaign, "campaign_description": campaign})
		leads = [
			("رضا", "کریمی", "شرکت داده‌پردازان شرق", "Open"),
			("سارا", "رحیمی", "کلینیک دندانپزشکی لبخند", "Replied"),
			("حسین", "نوری", "دفتر حقوقی عدالت", "Interested"),
			("نیلوفر", "صادقی", "آژانس تبلیغاتی نگاه", "Lead"),
			("مهدی", "جعفری", "کارخانه قطعات خودرو پیشرو", "Opportunity"),
			("زهرا", "حسینی", "مدرسه غیرانتفاعی فردا", "Do Not Contact"),
		]
		names = []
		for index, (first, last, company_name, status) in enumerate(leads):
			names.append(
				self.add(
					{
						"doctype": "Lead",
						"first_name": first,
						"last_name": last,
						"company_name": company_name,
						"status": status,
						"mobile_no": f"0935100000{index}",
						"email_id": f"lead{index}@example.com",
						"utm_campaign": campaign,
						"utm_source": "Exhibition" if frappe.db.exists("UTM Source", "Exhibition") else None,
						"city": "تهران",
					}
				).name
			)

		def opportunity(source, party, items, probability, closing_days):
			self.add(
				{
					"doctype": "Opportunity",
					"opportunity_from": source,
					"party_name": party,
					"opportunity_type": "Sales" if frappe.db.exists("Opportunity Type", "Sales") else None,
					"company": self.company,
					"probability": probability,
					"expected_closing": add_days(nowdate(), closing_days),
					"items": lines(items),
				}
			)

		opportunity("Lead", names[4], [("DESK-02", 30), ("CHAIR-01", 30)], 60, 20)
		opportunity("Customer", self.customer(5), [("CAB-01", 10)], 40, 35)
		opportunity("Customer", self.customer(2), [("LAPTOP-01", 8), ("SRV-SUP", 1)], 75, 10)

	def projects(self):
		project = self.add(
			{
				"doctype": "Project",
				"project_name": "تجهیز دفتر مرکزی فن‌آوران پارس",
				"company": self.company,
				"customer": self.customer(0),
				"status": "Open",
				"expected_start_date": self.day(20),
				"expected_end_date": add_days(nowdate(), 30),
			}
		)
		tasks = [
			("بازدید و نقشه‌برداری از محل", "Completed", 20, 15),
			("طراحی چیدمان و تأیید کارفرما", "Completed", 14, 8),
			("تولید میزها", "Working", 7, -10),
			("حمل و نصب", "Open", -10, -20),
			("تحویل نهایی و آموزش", "Open", -20, -25),
		]
		for subject, status, start, end in tasks:
			self.add(
				{
					"doctype": "Task",
					"subject": subject,
					"project": project.name,
					"status": status,
					"exp_start_date": add_days(nowdate(), -start),
					"exp_end_date": add_days(nowdate(), -end),
				}
			)

	def support(self):
		issues = [
			("لق بودن پایه‌ی صندلی تحویلی", 0, "Open"),
			("درخواست نصب درایور پرینتر", 6, "Replied"),
			("تأخیر در ارسال کمدها", 1, "Resolved"),
		]
		for subject, customer, status in issues:
			self.add(
				{
					"doctype": "Issue",
					"subject": subject,
					"customer": self.customer(customer),
					"status": status,
					"raised_by": CUSTOMERS[customer][5],
					"description": subject,
				}
			)

	def people(self):
		employees = [
			("امیر", "رستمی", "Male", "مدیر فروش", "1360-05-12"),
			("فاطمه", "اکبری", "Female", "حسابدار", "1368-11-02"),
			("محمد", "قاسمی", "Male", "کارشناس انبار", "1372-02-20"),
			("الهام", "مرادی", "Female", "سرپرست تولید", "1365-08-15"),
		]
		from iran_erp.utils.jalali import to_gregorian

		for first, last, gender, designation, birth in employees:
			year, month, day = (int(x) for x in birth.split("-"))
			self.add(
				{
					"doctype": "Employee",
					"first_name": first,
					"last_name": last,
					"gender": gender,
					"date_of_birth": to_gregorian(year, month, day),
					"date_of_joining": self.day(300),
					"company": self.company,
					"designation": designation,
					"status": "Active",
				}
			)

		for subject, days in (("جلسه‌ی بررسی فروش ماهانه", 2), ("بازدید از نمایشگاه مبلمان", 9)):
			self.add(
				{
					"doctype": "Event",
					"subject": subject,
					"starts_on": f"{add_days(nowdate(), days)} 10:00:00",
					"ends_on": f"{add_days(nowdate(), days)} 12:00:00",
					"event_type": "Public",
				}
			)

	def website(self):
		company = frappe.get_doc("Company", self.company)
		pages = [
			(
				"درباره ما",
				"about-us",
				f"<h2>{company.company_name}</h2><p>ما از سال ۱۳۹۰ در زمینه‌ی تولید مبلمان اداری و "
				"تأمین تجهیزات رایانه‌ای فعالیت می‌کنیم و بیش از ۳۰۰ سازمان را تجهیز کرده‌ایم.</p>"
				"<ul><li>تولید میز و کمد اداری در کارگاه اختصاصی</li><li>فروش و نصب تجهیزات رایانه‌ای</li>"
				"<li>پشتیبانی و خدمات پس از فروش</li></ul>",
			),
			(
				"محصولات و خدمات",
				"services",
				"<h2>محصولات و خدمات</h2><p>میز مدیریتی و کارمندی، صندلی ارگونومیک، کمد بایگانی، "
				"لپ‌تاپ، مانیتور و پرینتر؛ همراه با نصب و قرارداد پشتیبانی سالانه.</p>",
			),
			(
				"تماس با ما",
				"contact-us",
				f"<h2>تماس با ما</h2><p>تلفن: {company.phone_no or '۰۲۱-۱۲۳۴۵۶۷۸'}</p>"
				f"<p>ایمیل: {company.email or 'info@example.com'}</p><p>نشانی: تهران، خیابان آزادی، پلاک ۱۲</p>",
			),
		]
		menu = []
		for title, route, html in pages:
			existing = frappe.db.get_value("Web Page", {"route": route}, "route") or frappe.db.get_value(
				"Web Page", {"title": title}, "route"
			)
			if existing:
				# A page by that name is already there; link the menu to it instead
				menu.append((title, existing))
				continue
			self.add(
				{
					"doctype": "Web Page",
					"title": title,
					"route": route,
					"published": 1,
					"content_type": "HTML",
					"main_section_html": f'<div dir="rtl" class="iran-ai-page">{html}</div>',
				}
			)
			menu.append((title, route))
		settings = frappe.get_single("Website Settings")
		existing_urls = {row.url for row in settings.top_bar_items}
		for title, route in menu:
			if f"/{route}" not in existing_urls:
				settings.append("top_bar_items", {"label": title, "url": f"/{route}"})
		settings.save(ignore_permissions=True)

	def cheques(self):
		if not frappe.db.exists("Account", {"company": self.company, "account_number": "1302"}):
			return  # cheque accounts come with the Iranian chart of accounts
		bank = frappe.get_cached_value("Company", self.company, "default_bank_account")

		def cheque(kind, party_type, party, number, amount, days_ago, due_in, sayad):
			return self.add(
				{
					"doctype": "Iran Cheque",
					"cheque_type": kind,
					"company": self.company,
					"party_type": party_type,
					"party": party,
					"cheque_number": number,
					"sayad_id": sayad,
					"amount": amount,
					"posting_date": self.day(days_ago),
					"due_date": add_days(nowdate(), due_in),
					"drawer_bank": "بانک ملت" if kind == "Received" else None,
					"bank_account": bank if kind == "Issued" else None,
				},
				submit=True,
			)

		cheque("Received", "Customer", self.customer(1), "۴۵۸۲۱۰", 500_000_000, 20, 25, "1234567890123401")
		deposited = cheque(
			"Received", "Customer", self.customer(4), "۷۷۱۲۰۳", 300_000_000, 10, -1, "1234567890123402"
		)
		if bank:
			deposited.take_action("deposit", date=self.day(1), bank_account=bank)
		cheque("Issued", "Supplier", self.supplier(1), "۹۹۰۱۲۵", 800_000_000, 5, 30, "1234567890123403")


def national_code(prefix: str) -> str:
	"""A valid 10-digit national code starting with the given 9 digits."""
	return next(prefix + str(d) for d in range(10) if is_valid_national_code(prefix + str(d)))


def legal_id(prefix: str) -> str:
	"""A valid 11-digit legal national ID starting with the given 10 digits."""
	return next(prefix + str(d) for d in range(10) if is_valid_legal_national_id(prefix + str(d)))


def default_company():
	return frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {})


@frappe.whitelist()
def create_demo_data(company: str | None = None):
	frappe.only_for("System Manager")
	if frappe.db.get_default(LOG_KEY):
		frappe.throw(_("Demo data was already created. Delete it first to create it again."))
	company = company or default_company()
	if not company:
		frappe.throw(_("Finish the setup wizard first"))

	demo = Demo(company)
	steps = [
		"masters",
		"stock",
		"manufacturing",
		"buying",
		"selling",
		"crm",
		"projects",
		"support",
		"people",
		"website",
		"cheques",
	]
	done = []
	try:
		for step in steps:
			getattr(demo, step)()
			done.append(step)
	finally:
		# Keep the log even when a step fails, so what was created can still be deleted
		frappe.db.set_default(
			LOG_KEY, json.dumps({"company": company, "records": demo.log}, ensure_ascii=False)
		)
		frappe.db.commit()
	return {"company": company, "records": len(demo.log), "steps": done}


@frappe.whitelist()
def delete_demo_data():
	frappe.only_for("System Manager")
	saved = frappe.db.get_default(LOG_KEY)
	if not saved:
		frappe.throw(_("No demo data to delete"))
	records = json.loads(saved)["records"]
	vouchers = [name for _doctype, name in records]

	for doctype, name in reversed(records):
		if not frappe.db.exists(doctype, name):
			continue
		doc = frappe.get_doc(doctype, name)
		if doc.docstatus == 1:
			doc.flags.ignore_permissions = True
			doc.cancel()
	for doctype, name in reversed(records):
		if frappe.db.exists(doctype, name):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True, ignore_on_trash=True)

	# Ledger rows of the cancelled demo documents, so the company looks untouched again
	if vouchers:
		for table in ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry", "Repost Item Valuation"):
			frappe.db.delete(table, {"voucher_no": ("in", vouchers)})
	items = [name for doctype, name in records if doctype == "Item"]
	if items:
		frappe.db.delete("Bin", {"item_code": ("in", items)})

	settings = frappe.get_single("Website Settings")
	demo_titles = ("درباره ما", "محصولات و خدمات", "تماس با ما")
	settings.top_bar_items = [row for row in settings.top_bar_items if row.label not in demo_titles]
	settings.save(ignore_permissions=True)

	frappe.db.set_default(LOG_KEY, "")
	frappe.db.commit()
	return {"deleted": len(records)}


JOB_KEY = "iran_demo_job"


@frappe.whitelist()
def start(action: str):
	"""Run create or delete in the background; the page polls job_status for the outcome."""
	frappe.only_for("System Manager")
	if action not in ("create", "delete"):
		frappe.throw(_("Unknown action {0}").format(action))
	set_job_status({"running": True})
	frappe.enqueue(
		"iran_erp.demo.run_job",
		queue="long",
		timeout=1800,
		action=action,
		enqueue_after_commit=True,
	)
	# frappe.xcall only resolves when the response carries a value
	return {"started": action}


@frappe.whitelist()
def job_status() -> dict:
	frappe.only_for("System Manager")
	return json.loads(frappe.db.get_default(JOB_KEY) or '{"running": false}')


def run_job(action: str):
	# The page writes the message in the user's language from these fields
	status = {"running": False, "action": action}
	try:
		if action == "create":
			status["count"] = create_demo_data()["records"]
		else:
			status["count"] = delete_demo_data()["deleted"]
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title="Iran ERP demo data")
		status["error"] = frappe.utils.strip_html(str(e))
	set_job_status(status)


def set_job_status(status: dict):
	# Kept in the database: saving Website Settings clears the whole Redis cache
	frappe.db.set_default(JOB_KEY, json.dumps(status, ensure_ascii=False))
	frappe.db.commit()


def opening_account(company: str) -> str | None:
	"""The account opening balances are booked against (افتتاحیه موقت)."""
	return frappe.db.get_value(
		"Account", {"company": company, "account_type": "Temporary", "is_group": 0, "disabled": 0}
	)
