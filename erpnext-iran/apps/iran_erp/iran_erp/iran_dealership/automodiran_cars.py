"""The cars of automodiran's showroom (شعبه نگین ظفر, prices of 28 Mehr 1405), loaded into the ERP
in place of whatever cars are there:

	bench --site frontend execute iran_erp.iran_dealership.automodiran_cars.load

Sample data is deleted first (with its contracts, cheques and entries); any other car without a
sale or contract is deleted too. Each car gets its model (made once per model), colour, branch and
owner: «امانی» cars belong to the customer «مالک خودروی امانی» until their real owner is entered.
Every car is shown on the website with its price. The photos the site already had are attached to
their cars, and the Hilux's inspection sheet is entered as its body marks.
"""

import frappe
from frappe import _
from frappe.utils import cint, nowdate

BRANCH = "شعبه نگین ظفر"
CONSIGNMENT_OWNER = "مالک خودروی امانی"
# model | year | colour | mileage | B (the showroom's own) or C (consignment) | price in toman | R (reserved)
CARS = """
تیگارد X35 پلاس 1.5 لیتر توربو|1405|سفید|98|C|4450000000
تیگارد X35 پلاس 1.5 لیتر توربو|1405|مشکی|98|C|4500000000
تیگارد X35 پلاس 1.5 لیتر توربو|1405|سفید|98|C|4450000000
تیگارد X35 پلاس 1.5 لیتر توربو|1405|مشکی|99|C|4500000000
بی وای دی سی لاین 06 DMi|2025|خاکستری|2402|C|12900000000
تیگارد X35 پلاس 1.5 لیتر توربو|1405|مشکی|99|C|4500000000
تیگارد X35 پلاس 1.5 لیتر توربو|1405|سفید|98|C|4450000000
جیلی آزکارا هیبرید 1.5 لیتر توربو|2023|قرمز|42000|C|7200000000
بی وای دی سانگ پلاس DMi 1.5 لیتر|2025|سفید|210|C|13200000000
لاماری اکو 1.5 لیتر توربو|1405|مشکی|98|C|5650000000
کی ام سی SR3 1.6 لیتر|1404|سفید|97|C|4400000000
میتسوبیشی اکلیپس کراس 1.5 لیتر توربو|2025|مشکی|98|C|9850000000
کی ام سی T9 2 لیتر توربو|1405|مشکی|99|C|9850000000
لاماری ایما|1402|مشکی|40000|B|5950000000
فونیکس تیگو 7 پرو مکس (F7) 1.6 لیتر توربو AWD|1405|مشکی|0|C|7950000000
فولکس آی دی یونیکس پیور|2025|سفید|0|C|11200000000
فولکس آی دی یونیکس پیور|2025|نوک‌مدادی|55|C|11200000000
فولکس آی دی یونیکس پیور|2025|سرمه‌ای|55|C|11200000000
تویوتا کرولا کراس هیبرید 2.0 لیتر|2026|سفید|55|C|9700000000
اینوی هیبرید 1.5 لیتر|1405|سفید|0|C|4550000000
ام وی ام X33 کراس|1405|سفید|25|C|4350000000
چانگان CS 55 پلاس 1.5 لیتر توربو|2025|مشکی|1300|B|8100000000
فیدلیتی پرایم تیپ 2 هفت نفره|1402|سفید|92000|B|4800000000
دنا پلاس EF7 اتوماتیک توربو آپشنال|1405|سفید|70|B|4100000000
ام وی ام X77 الیت|1405|سفید|10|B|6850000000
هیوندا کراس۲۰۲۶|2026|سفید|20|B|9700000000
فونیکس FX EV 150 کیلو وات|2026|سفید صدفی|153|B|6900000000
تویوتا لوین هیبرید 1.8 لیتر ساده|1403|سفید|12000|B|7500000000
بی وای دی چین پلاس DMi|1405|سفید|99|C|6400000000|R
پژو 207 پانوراما دنده ای TU5P|1402|سفید|60000|B|2100000000
جی ای سی GS8 GL 2WD|2025|سبز|55|C|13500000000
تویوتا هایلوکس دو کابین بلند اتوماتیک|2014|سفید|93686|C|9300000000
اکستریم LX (SX) 1.6 لیتر توربو|1404|مشکی|56|C|7950000000
فونیکس آریزو 6 جی تی (Z6 GT) اکسلنت|1404|مشکی|56|C|6350000000
اکستریم LX (SX) 1.6 لیتر توربو|1404|سفید|56|C|7950000000
اکستریم LX (SX) 1.6 لیتر توربو|1404|مشکی|56|C|7950000000
اکستریم TXL (TX) 2.0 لیتر توربو|1404|مشکی|55|C|12600000000
لوکانو L8 2.0 لیتر توربو|1404|مشکی|55|C|12900000000
لوکانو L8 2.0 لیتر توربو|1404|سفید|56|C|12900000000
ام وی ام X33 کراس اتوماتیک|1404|سفید|13000|B|3500000000
ب ام و X4 28|2015|قهوه‌ای|120000|C|17100000000
فونیکس تیگو 7 پرو هیبرید (F7) e پلاس|1405|مشکی|44|C|8000000000
فونیکس آریزو 6 پرو|1404|سفید|9071|C|5500000000
اس دبلیو ام G01|1399|خاکستری|119439|C|3400000000
کی ام سی K7|1401|مشکی|107942|C|4600000000
فونیکس FX پریمیوم FWD|1402|خاکستری|32230|C|6300000000
چری تیگو 5 اکسلنت|1397|سفید|96000|C|3150000000
سوزوکی گراند ویتارا (مونتاژ) 2.4 لیتر اتوماتیک|1396|مشکی|127759|C|5600000000
کی ام سی J7|1402|سفید|44000|C|5100000000
پژو 207 دنده ای TU5P|1405|سفید|52|C|2700000000
نیسان ترا لئو MX8|1404|خاکستری|7310|C|13600000000
فونیکس FX پریمیوم FWD|1403|مشکی|41420|C|6300000000
سمند سورن پلاس XU7P بنزینی|1402|سفید|220000|C|1600000000
ام وی ام X33 کراس اتوماتیک|1403|سفید|34000|C|3400000000
آرتابان (ای ام جی) توکا|1405|مشکی|62|B|6700000000
فردا 511|1405|سفید|28|C|3400000000
فردا 511|1405|سفید|18|C|3400000000
فونیکس تیگو 7 پرو پریمیوم|1404|مشکی|40000|B|6400000000
فونیکس آریزو 6 جی تی (Z6 GT)|||85000|B|5100000000
دنا پلاس EF7 اتوماتیک توربو آپشنال|1404|مشکی|319|C|3800000000
بنز کلاس A سدان A200L|1405|سفید|0|C|16500000000
کیا اسپورتیج 4 سیلندر GT لاین|2025|سفید|0|C|12000000000
رنو مگان (وارداتی) 2000|1385|نقره‌ای|227000|C|1700000000
اکستریم VX (QX)|||30000|C|10600000000
ام وی ام X77|||65|C|6900000000
چانگان ایدو EV460|2024|سفید|200|C|4200000000
فونیکس تیگو 7 پرو پریمیوم|1404|مشکی|40000|B|6500000000
جک S5 2.0 لیتر اتوماتیک|1398|سفید|150000|B|3500000000
هایما 7X 1.6 لیتر توربو|1403|مشکی|22000|C|5650000000
لاماری ایما|1404|سبز|21000|C|6600000000
هایما S7|1398|سفید|181000|C|3900000000
جک جی 4|1403|مشکی|51000|C|2600000000
فونیکس تیگو 7 پرو مکس (F7)|1405|سفید|90|C|7950000000
تویوتا وایلدلندر 2.0 لیتر AWD لاکچری پلاس|2025|سفید|90|C|14000000000
برلیانس H320 1.65 اتوماتیک|1400|سفید|117|C|2400000000
ام وی ام X5|1404|مشکی|5|C|6100000000
بی ای سی X3 PRO|||9000|C|3900000000
جی ای سی GS3 Emzoom 1.5 لیتر توربو|1404|آبی|0|C|6800000000
فولکس آی دی یونیکس اولترا|2025|سرمه‌ای|40|C|14500000000
فونیکس FX EV|2026|مشکی|32|C|7000000000
فونیکس FX پریمیوم AWD|1404|مشکی|45|C|7400000000
بنز کلاس A سدان A200L|2025|سفید|35|C|16500000000
فونیکس تیگو 8 پرو مکس (F8) IE|1404|مشکی|10500|C|8850000000
ب ام و سری 7 730li|2022|مشکی|69000|C|52000000000
هوندا HR-V eHEV|||1300|C|9550000000
تارا اتوماتیک V2|1402|خاکستری|42000|C|2500000000
فونیکس FX پریمیوم AWD|1404|مشکی|40|C|7770000000
فونیکس تیگو 7 پرو مکس (F7)|1405|سفید|0|C|8000000000
بی وای دی چین ال DMi|2025|سفید|15000|C|10100000000
"""

# The brand at the start of each model's name (longest first, so «بی وای دی» before «بی»)
BRANDS = sorted(
	(
		"تیگارد", "بی وای دی", "جیلی", "لاماری", "کی ام سی", "میتسوبیشی", "فونیکس", "فولکس", "تویوتا",
		"اینوی", "ام وی ام", "چانگان", "فیدلیتی", "دنا", "هیوندا", "پژو", "جی ای سی", "اکستریم", "لوکانو",
		"ب ام و", "اس دبلیو ام", "چری", "سوزوکی", "نیسان", "سمند", "آرتابان", "فردا", "جک", "هایما", "بنز",
		"کیا", "رنو", "بی ای سی", "برلیانس", "هوندا", "تارا",
	),
	key=len,
	reverse=True,
)  # fmt: skip
COLORS = {
	"سفید": "#f5f5f4",
	"مشکی": "#111827",
	"خاکستری": "#6b7280",
	"قرمز": "#dc2626",
	"نوک‌مدادی": "#374151",
	"سرمه‌ای": "#1e3a8a",
	"سفید صدفی": "#f8f5ee",
	"سبز": "#15803d",
	"قهوه‌ای": "#78350f",
	"نقره‌ای": "#c0c0c0",
	"آبی": "#2563eb",
}
# Photos the website already has (its public/cars folders), by the car they show:
# model, colour, year → folder and files
PHOTOS = {
	("بنز کلاس A سدان A200L", "سفید", "1405"): ("benz-a200l-01", ("front.jpg", "back.jpg", "front-cap.jpg", "front-dor.jpg")),
	("چانگان CS 55 پلاس 1.5 لیتر توربو", "مشکی", "2025"): ("changan-cs55-01", ("front.jpg", "back.jpg")),
	("فونیکس FX EV 150 کیلو وات", "سفید صدفی", "2026"): ("fownix-fxev-01", ("front.jpg", "back.jpg")),
	("لوکانو L8 2.0 لیتر توربو", "مشکی", "1404"): ("lucano-l8-01", ("front.jpg",)),
	("ام وی ام X33 کراس", "سفید", "1405"): ("mvm-x33-01", ("front.jpg",)),
	("تویوتا کرولا کراس هیبرید 2.0 لیتر", "سفید", "2026"): ("toyota-crolla-01", ("front.jpg", "back.jpg")),
	("تویوتا هایلوکس دو کابین بلند اتوماتیک", "سفید", "2014"): ("toyota-hailux-01", ("front.jpg", "front2.jpg", "dakhel1.jpg")),
	("فولکس آی دی یونیکس پیور", "سفید", "2025"): ("vw-idunix-01", ("back.jpg",)),
}  # fmt: skip
# The Hilux's inspection sheet: part, what was found, note
HILUX_MARKS = (
	("کاپوت", "تعویضی", ""),
	("گلگیر جلو چپ", "تعویضی", ""),
	("گلگیر عقب چپ", "رنگ دارد", ""),
	("گلگیر جلو راست", "تعویضی", ""),
	("شاسی جلو", "تصادفی", "دو طرف جوش و ضربه دارد"),
	("سینی جلو", "تصادفی", "دو طرف جوش و ضربه دارد"),
)


def rows() -> list[dict]:
	out = []
	for line in CARS.strip().splitlines():
		parts = line.split("|") + [""]
		title, year, color, mileage, owner, price, reserved = parts[:7]
		brand = next((b for b in BRANDS if title.startswith(b + " ") or title == b), title.split()[0])
		out.append(
			{
				"title": title,
				"brand": brand,
				"model": title[len(brand) :].strip() or title,
				"year": year,
				"color": color,
				"mileage": cint(mileage),
				"business": owner == "B",
				"price": cint(price) * 10,
				"reserved": reserved == "R",
			}
		)
	return out


def _jalali(year: str) -> bool:
	return bool(year) and int(year) < 1500


def _model(row, gregorian_models) -> str:
	name = f"{row['brand']} {row['model']}".strip()
	if not frappe.db.exists("Iran Car Model", name):
		doc = frappe.get_doc(
			{
				"doctype": "Iran Car Model",
				"brand": row["brand"],
				"model": row["model"],
				# A model whose cars carry Gregorian years is imported
				"made_in": "Imported Car" if name in gregorian_models else "Made in Iran",
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		name = doc.name
	return name


def _remove_cars():
	"""Sample data first, with everything it made; then any car without a sale or contract."""
	from iran_erp.iran_dealership import demo

	if demo._records():
		demo.delete_dealership_demo()
	kept = []
	for name in frappe.get_all("Iran Vehicle", pluck="name"):
		car = frappe.get_doc("Iran Vehicle", name)
		linked = car.sale_contract or frappe.db.exists(
			"Iran Instalment Sale", {"vehicle": name, "docstatus": 1}
		) or frappe.db.exists("Iran Investment Contract", {"vehicle": name, "docstatus": 1})
		if linked:
			kept.append(name)
			continue
		demo._cancel_vehicle_entries(car)
		for inquiry in frappe.get_all("Iran Car Inquiry", filters={"vehicle": name}, pluck="name"):
			frappe.delete_doc("Iran Car Inquiry", inquiry, force=True, ignore_permissions=True)
		frappe.delete_doc("Iran Vehicle", name, force=True, ignore_permissions=True)
	return kept


@frappe.whitelist()
def load(replace: int = 1) -> dict:
	frappe.only_for("System Manager")
	frappe.local.lang = "fa"
	kept = _remove_cars() if cint(replace) else []
	company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
	if not frappe.db.exists("Branch", BRANCH):
		frappe.get_doc({"doctype": "Branch", "branch": BRANCH}).insert(ignore_permissions=True)
	for color, code in COLORS.items():
		if not frappe.db.exists("Iran Car Color", color):
			frappe.get_doc({"doctype": "Iran Car Color", "color_name": color, "color_code": code}).insert(
				ignore_permissions=True
			)
	owner = frappe.db.get_value("Customer", {"customer_name": CONSIGNMENT_OWNER})
	if not owner:
		owner = (
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": CONSIGNMENT_OWNER,
					"customer_type": "Individual",
					"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}) or "All Customer Groups",
					"territory": "Iran" if frappe.db.exists("Territory", "Iran") else "All Territories",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	cars = rows()
	gregorian = {f"{r['brand']} {r['model']}".strip() for r in cars if r["year"] and not _jalali(r["year"])}
	made = []
	for row in cars:
		model = _model(row, gregorian)
		year = row["year"]
		# A Jalali year on an imported model is written as its Gregorian year (1405 → 2026)
		if year and model in gregorian and _jalali(year):
			year = str(int(year) + 621)
		car = frappe.get_doc(
			{
				"doctype": "Iran Vehicle",
				"company": company,
				"car_model": model,
				"year": year,
				"color": row["color"] or None,
				"mileage": row["mileage"],
				"branch": BRANCH,
				"entry_date": nowdate(),
				"status": "Reserved" if row["reserved"] else "Ready for Sale",
				"ownership": "Business" if row["business"] else "Customer",
				"owner_customer": None if row["business"] else owner,
				"asking_price": row["price"],
				"show_on_website": 1,
				"website_show_price": 1,
				"website_show_report": 1,
			}
		)
		photos = PHOTOS.pop((row["title"], row["color"], row["year"]), None)
		if photos:
			folder, files = photos
			for file in files:
				car.append("photos", {"image": f"/cars/{folder}/{file}"})
			if folder == "toyota-hailux-01":
				for part, condition, note in HILUX_MARKS:
					if frappe.db.exists("Iran Body Part", part) and frappe.db.exists("Iran Body Condition", condition):
						car.append("body_marks", {"body_part": part, "condition": condition, "description": note})
		car.flags.ignore_permissions = True
		car.insert()
		made.append(car.name)
	frappe.db.commit()
	return {
		"cars": len(made),
		"kept": kept,
		"message": _("{0} cars were loaded.").format(len(made))
		+ (" " + _("Kept, since they have a sale or contract: {0}").format(", ".join(kept)) if kept else ""),
	}
