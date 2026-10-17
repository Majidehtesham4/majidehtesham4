"""The lists a car dealership starts with: car models, colours, body parts and conditions, the
items an expert scores, and the usual preparation, repair and paperwork services. Every list can
be changed afterwards; only rows that are missing are added."""

import frappe

MODELS = {
	"ایران‌خودرو": [
		"پژو ۲۰۶",
		"پژو ۲۰۶ صندوق‌دار",
		"پژو ۲۰۷",
		"پژو ۲۰۷ اتوماتیک",
		"پژو پارس",
		"پژو ۴۰۵",
		"سمند",
		"سورن",
		"دنا",
		"دنا پلاس",
		"رانا",
		"تارا",
		"تارا اتوماتیک",
		"ری‌را",
		"هایما S7",
		"هایما S5",
	],
	"سایپا": [
		"پراید",
		"تیبا",
		"ساینا",
		"کوییک",
		"کوییک اتوماتیک",
		"شاهین",
		"شاهین اتوماتیک",
		"آریا",
		"اطلس",
		"چانگان CS35",
	],
	"پارس‌خودرو": ["ال۹۰", "برلیانس H320", "برلیانس H330", "چری تیگو ۵", "رنو ساندرو"],
	"مدیران‌خودرو": [
		"ام‌وی‌ام X22",
		"ام‌وی‌ام X33",
		"ام‌وی‌ام X55",
		"ام‌وی‌ام 315",
		"چری آریزو ۵",
		"چری آریزو ۶",
		"چری تیگو ۷",
		"چری تیگو ۸",
	],
	"کرمان‌موتور": ["جک J4", "جک S3", "جک S5", "کی‌ام‌سی K7", "کی‌ام‌سی T8", "کی‌ام‌سی J7"],
	"بهمن‌موتور": ["فیدلیتی", "دیگنیتی", "کاپرا"],
	"تویوتا": ["کرولا", "کمری", "راوفور", "لندکروزر", "هایلوکس"],
	"هیوندای": ["النترا", "سوناتا", "توسان", "سانتافه", "اکسنت", "i20"],
	"کیا": ["سراتو", "اسپورتیج", "سورنتو", "ریو", "اپتیما"],
	"نیسان": ["قشقایی", "ایکس‌تریل", "پاترول", "جوک"],
	"مزدا": ["مزدا ۳", "مزدا ۶", "CX-5"],
	"بی‌ام‌و": ["سری ۳", "سری ۵", "X3", "X5"],
	"مرسدس‌بنز": ["کلاس C", "کلاس E", "GLC"],
}

# Brands whose cars come from abroad: their model year is Gregorian
IMPORTED_BRANDS = ("تویوتا", "هیوندای", "کیا", "نیسان", "مزدا", "بی‌ام‌و", "مرسدس‌بنز")

COLORS = [
	("سفید", "#ffffff"),
	("سفید صدفی", "#f5f1e6"),
	("مشکی", "#111111"),
	("نقره‌ای", "#c0c0c0"),
	("خاکستری", "#808080"),
	("نوک‌مدادی", "#4a4a4a"),
	("دلفینی", "#7b8a96"),
	("قرمز", "#c0392b"),
	("آلبالویی", "#7b1e2b"),
	("آبی", "#2457a6"),
	("سرمه‌ای", "#1f2a44"),
	("سبز", "#2e7d32"),
	("بژ", "#d9c7a1"),
	("طلایی", "#c9a227"),
	("قهوه‌ای", "#6d4c41"),
	("زرد", "#f2c200"),
	("نارنجی", "#e67e22"),
]

# name, key on the diagram (empty: in the list only), order
BODY_PARTS = [
	("سپر جلو", "front_bumper"),
	("کاپوت", "hood"),
	("گلگیر جلو چپ", "front_left_fender"),
	("گلگیر جلو راست", "front_right_fender"),
	("شیشه جلو", "windshield"),
	("درب جلو چپ", "front_left_door"),
	("درب جلو راست", "front_right_door"),
	("درب عقب چپ", "rear_left_door"),
	("درب عقب راست", "rear_right_door"),
	("رکاب چپ", "left_sill"),
	("رکاب راست", "right_sill"),
	("سقف", "roof"),
	("شیشه عقب", "rear_glass"),
	("گلگیر عقب چپ", "rear_left_fender"),
	("گلگیر عقب راست", "rear_right_fender"),
	("درب صندوق", "trunk"),
	("سپر عقب", "rear_bumper"),
	("ستون‌ها", ""),
	("سینی جلو", ""),
	("شاسی جلو", ""),
	("شاسی عقب", ""),
	("کف صندوق", ""),
	("اتاق", ""),
]

# name, colour on the diagram, effect on price
BODY_CONDITIONS = [
	("رنگ دارد", "#f59e0b", "Medium"),
	("تصادفی", "#dc2626", "High"),
	("خط و خش", "#a3a3a3", "Low"),
	("لیسه", "#eab308", "Low"),
	("تعویضی", "#7c3aed", "High"),
	("رنگ‌سوختگی", "#ea580c", "Low"),
	("صافکاری بدون رنگ", "#0ea5e9", "Low"),
	("فرورفتگی", "#64748b", "Low"),
	("ترک یا شکستگی", "#be123c", "Medium"),
]

INSPECTION = [
	("موتور", "Technical", "Score"),
	("گیربکس", "Technical", "Score"),
	("لاستیک‌ها", "Technical", "Percent"),
	("کمک‌فنرها", "Technical", "Score"),
	("جلوبندی و فرمان", "Technical", "Score"),
	("ترمزها", "Technical", "Score"),
	("کولر", "Technical", "Score"),
	("بخاری", "Technical", "Score"),
	("تسمه تایم", "Technical", "Percent"),
	("باتری", "Technical", "Score"),
	("سیستم برق", "Technical", "Score"),
	("صندلی‌ها", "Interior", "Score"),
	("فرمان", "Interior", "Score"),
	("داشبورد", "Interior", "Score"),
	("سقف داخلی", "Interior", "Score"),
	("کف و موکت", "Interior", "Score"),
	("سیستم صوتی و تصویری", "Interior", "Score"),
]

# name, category, whole or part asked
SERVICES = [
	("کارواش معمولی", "Preparation", 0),
	("کارواش VIP", "Preparation", 0),
	("صفرشویی", "Preparation", 0),
	("پولیش بدنه", "Preparation", 1),
	("واکس", "Preparation", 0),
	("تمیز کردن چراغ‌ها", "Preparation", 0),
	("روکش فرمان", "Preparation", 0),
	("روکش صندلی", "Preparation", 0),
	("زیرپایی", "Preparation", 0),
	("صافکاری", "Repair", 1),
	("PDR (صافکاری بدون رنگ)", "Repair", 1),
	("رنگ", "Repair", 1),
	("تودوزی", "Repair", 0),
	("تعویض قطعه", "Repair", 0),
	("تراشکاری", "Repair", 0),
	("تعویض لاستیک", "Repair", 0),
	("تعمیر مکانیکی", "Repair", 0),
	("سرویس و تعویض روغن", "Repair", 0),
	("کارشناسی", "Paperwork", 0),
	("انتقال سند", "Paperwork", 0),
	("بیمه", "Paperwork", 0),
	("خلافی و عوارض", "Paperwork", 0),
	("معاینه فنی", "Paperwork", 0),
	("سایر هزینه‌ها", "Other", 0),
]


def _insert(doctype, values):
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.flags.ignore_permissions = True
	doc.insert()


def seed():
	for brand, models in MODELS.items():
		for model in models:
			if not frappe.db.exists("Iran Car Model", f"{brand} {model}"):
				made_in = "Imported Car" if brand in IMPORTED_BRANDS else "Made in Iran"
				_insert("Iran Car Model", {"brand": brand, "model": model, "made_in": made_in})
	for name, code in COLORS:
		if not frappe.db.exists("Iran Car Color", name):
			_insert("Iran Car Color", {"color_name": name, "color_code": code})
	for i, (name, key) in enumerate(BODY_PARTS):
		if not frappe.db.exists("Iran Body Part", name):
			_insert("Iran Body Part", {"part_name": name, "diagram_key": key, "sort_order": i + 1})
	for name, code, severity in BODY_CONDITIONS:
		if not frappe.db.exists("Iran Body Condition", name):
			_insert("Iran Body Condition", {"condition_name": name, "color_code": code, "severity": severity})
	for i, (name, section, measure) in enumerate(INSPECTION):
		if not frappe.db.exists("Iran Inspection Item", name):
			_insert(
				"Iran Inspection Item",
				{"item_name": name, "section": section, "measure": measure, "sort_order": i + 1},
			)
	for name, category, asks_scope in SERVICES:
		if not frappe.db.exists("Iran Vehicle Service", name):
			_insert(
				"Iran Vehicle Service", {"service_name": name, "category": category, "asks_scope": asks_scope}
			)
