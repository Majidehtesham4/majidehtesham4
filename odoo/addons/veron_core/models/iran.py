import datetime
import logging

import pytz

from odoo import api, fields, models

from . import jalali

_logger = logging.getLogger(__name__)

LANG = {
	"week_start": "6",  # Saturday
	"date_format": "%Y/%m/%d",
	"time_format": "%H:%M:%S",
	"direction": "rtl",
	"decimal_point": ".",
	"thousands_sep": ",",
	"grouping": "[3,0]",
}


class VeronIran(models.AbstractModel):
	"""Iran as the setting of everything: Persian with the week from Saturday, rial, Tehran time. Run
	when ERP-VERON is installed and each time it is updated, so a database made before is set too."""

	_name = "veron.iran"
	_description = "Iranian settings"

	@api.model
	def _apply_later(self):
		"""From the data of an install or update: run once every module is loaded (a module loaded after
		this one, like website or the provinces, would not be there yet), as account defers its chart"""
		self.env.registry._veron_iran_pending = True

	def _register_hook(self):
		super()._register_hook()
		if getattr(self.env.registry, "_veron_iran_pending", False):
			del self.env.registry._veron_iran_pending
			self._apply()

	@api.model
	def _apply(self):
		self = self.sudo()
		lang = self._persian()
		installed = self.env["ir.module.module"].search([("state", "=", "installed")]).mapped("name")
		self.env["ir.module.module"]._veron_load_persian(installed, [lang.code])
		self.env["res.users"].with_context(active_test=False).search([("share", "=", False)]).write(
			{"lang": lang.code, "tz": "Asia/Tehran"}
		)
		self.env["ir.default"].set("res.partner", "lang", lang.code)
		self.env["ir.default"].set("res.partner", "tz", "Asia/Tehran")
		rial = self._rial()
		iran = self.env.ref("base.ir")
		for company in self.env["res.company"].search([]):
			if not company.country_id:
				company.country_id = iran
			if company.country_id == iran:
				self._company_currency(company, rial)
		self._pricelists()
		self._work_week()
		self._provinces()
		self._default_names()
		self._module_names(lang.code)
		self._holidays()
		self._location_names()

	def _persian(self):
		lang = self.env["res.lang"].with_context(active_test=False).search([("code", "=", "fa_IR")], limit=1)
		if not lang.active:
			self.env["res.lang"]._activate_lang("fa_IR")
			self.env["ir.module.module"].search([("state", "=", "installed")])._update_translations(["fa_IR"])
			lang = self.env["res.lang"].search([("code", "=", "fa_IR")], limit=1)
		lang.write(LANG)
		return lang

	def _rial(self):
		rial = self.env.ref("base.IRR")
		values = {"active": True, "symbol": "ریال", "position": "after"}
		# Rial has no decimals; Odoo refuses fewer decimals once a currency has accounting entries
		if rial.rounding != 1 and not self._has_entries(rial):
			values["rounding"] = 1.0
		rial.write(values)
		return rial

	def _has_entries(self, currency):
		if "account.move.line" not in self.env:
			return False
		return bool(self.env["account.move.line"].search_count([("currency_id", "=", currency.id)], limit=1))

	def _company_currency(self, company, rial):
		if company.currency_id == rial:
			return
		if "account.move.line" in self.env and self.env["account.move.line"].search_count(
			[("company_id", "=", company.id)], limit=1
		):
			_logger.warning("ERP-VERON: %s has entries in %s; its currency is kept", company.name, company.currency_id.name)
			return
		company.currency_id = rial

	def _pricelists(self):
		"""Price lists made in the company's earlier currency (Odoo's default one is made in dollars,
		before the Iranian chart sets rial): in the company's currency, unless sales were made with them"""
		if "product.pricelist" not in self.env:
			return
		for pricelist in self.env["product.pricelist"].with_context(active_test=False).search([]):
			company = pricelist.company_id or self.env.company
			if pricelist.currency_id == company.currency_id:
				continue
			if "sale.order" in self.env and self.env["sale.order"].search_count(
				[("pricelist_id", "=", pricelist.id), ("state", "=", "sale")], limit=1
			):
				continue
			pricelist.currency_id = company.currency_id
		# Quotations not yet confirmed follow their price list's currency
		if "sale.order" in self.env:
			quotations = self.env["sale.order"].search([("state", "in", ("draft", "sent"))]).filtered(
				lambda order: order.pricelist_id and order.currency_id != order.pricelist_id.currency_id
			)
			quotations._compute_currency_id()
			quotations.order_line._compute_amount()

	def _work_week(self):
		"""Odoo's default working week, Monday to Friday, as Iran's 44 hours: Saturday to Wednesday
		8 to 17 with an hour for lunch, Thursday 8 to 12. A schedule changed by hand is kept. Schedules
		and resources left in UTC are set in Tehran time."""
		if "resource.calendar" not in self.env:
			return
		# Work hours in Tehran time: in UTC, 8 o'clock would be 11:30 here
		self.env["resource.calendar"].search([("tz", "in", [False, "UTC"])]).write({"tz": "Asia/Tehran"})
		self.env["resource.resource"].with_context(active_test=False).search([("tz", "in", [False, "UTC"])]).write({"tz": "Asia/Tehran"})
		iranian = [(0, 0, line) for line in _iranian_week()]
		for calendar in self.env["resource.calendar"].search([]):
			days = set(calendar.attendance_ids.mapped("dayofweek"))
			if days != {"0", "1", "2", "3", "4"}:
				continue
			calendar.write({
				"name": "۴۴ ساعت در هفته (شنبه تا پنجشنبه)",
				"attendance_ids": [(5, 0, 0)] + iranian,
				"full_time_required_hours": 44,
				"hours_per_day": 8,
			})


	def _default_names(self):
		"""The English names Odoo gives a new database, while they are unchanged"""
		for xmlid, english, persian in DEFAULT_NAMES:
			record = self.env.ref(xmlid, raise_if_not_found=False)
			if record and record.name == english:
				record.name = persian

	def _module_names(self, lang):
		"""The apps with no Persian name of their own, mostly OCA's, named in Persian on the Apps page"""
		modules = self.env["ir.module.module"].with_context(lang=lang).search([("name", "in", list(MODULE_NAMES))])
		for module in modules:
			name, summary = MODULE_NAMES[module.name]
			if module.shortdesc != name:
				module.update_field_translations("shortdesc", {lang: name})
			if module.summary != summary:
				module.update_field_translations("summary", {lang: summary})

	def _location_names(self):
		"""The locations stock makes with English names (a plain field, not translated), while unchanged"""
		if "stock.location" not in self.env:
			return
		Locations = self.env["stock.location"].with_context(active_test=False)
		for english, persian in LOCATION_NAMES.items():
			Locations.search([("name", "=", english)]).write({"name": persian})

	def _holidays(self):
		"""Iran's official holidays as public time off of each company: the solar ones of this Shamsi year
		and the next, and the lunar ones whose official date is known (HOLIDAYS_LUNAR). The other lunar
		holidays follow the moon and are added by hand from the official calendar."""
		if "resource.calendar.leaves" not in self.env:
			return
		tehran = pytz.timezone("Asia/Tehran")
		this_year = jalali.to_jalali(fields.Date.context_today(self))[0]
		days = [(year, month, day, name) for year in (this_year, this_year + 1) for month, day, name in HOLIDAYS_SOLAR]
		days += HOLIDAYS_LUNAR
		Leaves = self.env["resource.calendar.leaves"]
		for company in self.env["res.company"].search([("partner_id.country_id.code", "=", "IR")]):
			for year, month, day, name in days:
				date = jalali.to_gregorian(year, month, day)
				start = tehran.localize(datetime.datetime.combine(date, datetime.time())).astimezone(pytz.utc)
				start = start.replace(tzinfo=None)
				end = start + datetime.timedelta(days=1, seconds=-1)
				exists = Leaves.search_count([
					("company_id", "=", company.id),
					("resource_id", "=", False),
					("date_from", "<=", end),
					("date_to", ">=", start),
				])
				if not exists:
					Leaves.create({
						"name": name,
						"company_id": company.id,
						"calendar_id": False,
						"date_from": start,
						"date_to": end,
					})

	def _provinces(self):
		"""OCA's provinces and cities of Iran are typed with Arabic letters (ي، ك) and some names are
		misspelt: the official names, and the cities in Persian letters."""
		if "res.city" not in self.env or not self.env.ref("l10n_ir_states.state_ir_10", raise_if_not_found=False):
			return
		for code, name in PROVINCES.items():
			state = self.env.ref(f"l10n_ir_states.state_ir_{code}", raise_if_not_found=False)
			if state and state.name != name:
				state.name = name
		self.env.cr.execute("""
			UPDATE res_city SET name = (
				SELECT jsonb_object_agg(lang, btrim(regexp_replace(translate(value, 'يك', 'یک'), '\\s+', ' ', 'g')))
				FROM jsonb_each_text(name) AS t(lang, value)
			)
			WHERE name::text ~ '[يك]|"\\s|\\s"|\\s\\s'
		""")
		self.env["res.city"].invalidate_model(["name"])


DEFAULT_NAMES = [
	("base.main_company", "My Company", "شرکت من"),
	("base.partner_admin", "Administrator", "مدیر سیستم"),
	("hr.employee_admin", "Administrator", "مدیر سیستم"),
	("website.default_website", "My Website", "وب‌سایت من"),
]

LOCATION_NAMES = {
	"Vendors": "تأمین‌کنندگان",
	"Customers": "مشتریان",
	"Partners": "طرف‌حساب‌ها",
	"Inter-company transit": "ترانزیت بین شرکتی",
	"Inventory adjustment": "تعدیل موجودی",
	"Production": "تولید",
	"Scrap": "ضایعات",
	"Virtual Locations": "مکان‌های مجازی",
	"Physical Locations": "مکان‌های فیزیکی",
}

# The official holidays on a fixed Shamsi day: (month, day, name)
HOLIDAYS_SOLAR = [
	(1, 1, "عید نوروز"),
	(1, 2, "عید نوروز"),
	(1, 3, "عید نوروز"),
	(1, 4, "عید نوروز"),
	(1, 12, "روز جمهوری اسلامی"),
	(1, 13, "روز طبیعت"),
	(3, 14, "رحلت امام خمینی"),
	(3, 15, "قیام ۱۵ خرداد"),
	(11, 22, "پیروزی انقلاب اسلامی"),
	(12, 29, "روز ملی شدن صنعت نفت"),
]

# Lunar holidays of the published calendars of the year, which agree with each other and with the
# lengths of the lunar months: (year, month, day, name)
HOLIDAYS_LUNAR = [
	(1405, 1, 25, "شهادت امام جعفر صادق"),
	(1405, 3, 6, "عید قربان"),
	(1405, 3, 14, "عید غدیر"),
	(1405, 4, 3, "تاسوعا"),
	(1405, 4, 4, "عاشورا"),
	(1405, 5, 13, "اربعین"),
	(1405, 5, 21, "رحلت پیامبر و شهادت امام حسن"),
	(1405, 5, 22, "شهادت امام رضا"),
	(1405, 5, 30, "شهادت امام حسن عسکری"),
	(1405, 6, 8, "میلاد پیامبر و امام جعفر صادق"),
	(1405, 8, 22, "شهادت حضرت فاطمه"),
	(1405, 10, 2, "ولادت امام علی"),
	(1405, 10, 16, "مبعث"),
	# 15 Sha'ban: 3 or 4 Bahman, as Rajab has 29 or 30 days; added by hand once announced
	(1405, 12, 9, "شهادت امام علی"),
	(1405, 12, 19, "عید فطر"),
	(1405, 12, 20, "عید فطر"),
]

MODULE_NAMES = {
	"payroll": ("حقوق و دستمزد", "فیش حقوقی، قراردادها و محاسبه‌ی حقوق کارکنان"),
	"account_financial_report": ("گزارش‌های مالی", "دفتر کل، تراز آزمایشی، صورت‌حساب طرف حساب و گزارش سنی"),
	"base_territory": ("مناطق و شعبه‌ها", "تعریف منطقه، شعبه و ناحیه برای فروش و خدمات"),
	"dms": ("مدیریت اسناد", "پوشه‌ها و فایل‌ها با دسترسی برای هر گروه"),
	"document_knowledge": ("دانشنامه", "صفحه‌های دانش و راهنمای سازمان"),
	"fieldservice": ("خدمات در محل", "محل‌ها، کارشناسان و سفارش‌های خدمت در محل مشتری"),
	"helpdesk_mgmt": ("میز خدمت", "تیکت‌های پشتیبانی مشتری‌ها"),
	"mis_builder": ("گزارش‌ساز مدیریتی", "گزارش‌ها و داشبوردهای مدیریتی با قالب دلخواه"),
	"mrp_multi_level": ("برنامه‌ریزی مواد چندسطحی", "برنامه‌ریزی نیاز مواد (MRP) برای چند سطح ساخت"),
	"project_forecast_line": ("پیش‌بینی پروژه", "پیش‌بینی ظرفیت و نیاز نیروی پروژه‌ها"),
	"subscription_oca": ("اشتراک‌ها", "فاکتورهای دوره‌ای اشتراک‌ها"),
	"resource_booking": ("نوبت‌دهی", "رزرو نوبت مشتری با تقویم و زمان‌های آزاد کارکنان و امکانات"),
	"voip_oca": ("تلفن اینترنتی", "تماس تلفنی از داخل برنامه با مرکز تلفن اینترنتی (VoIP)"),
	"veron_barcode": ("بارکد", "دریافت، ارسال و انبارگردانی با بارکدخوان یا دوربین گوشی"),
	"veron_planning": ("برنامه‌ریزی نیرو", "شیفت کارکنان بر اساس نقش روی خط زمانی، با هشدار تداخل با مرخصی"),
	"veron_appraisal": ("ارزیابی کارکنان", "خودارزیابی کارمند، امتیاز مدیر و نمره‌ی وزنی"),
	"veron_shopfloor": ("کارگاه", "صفحه‌ی تبلت کارگاه: شروع، توقف و پایان دستورهای کار با ثبت زمان"),
	"veron_plm": ("چرخه‌ی عمر محصول (PLM)", "تغییرات مهندسی روی نسخه‌ی جدید فرمول ساخت، با تأیید مدیر"),
	"veron_social": ("انتشار در شبکه‌ها", "پست در کانال‌های بله، ایتا و تلگرام، الان یا زمان‌بندی‌شده"),
	"veron_marketing_automation": ("بازاریابی خودکار", "کمپین‌های خودکار: ایمیل، پیامک، کار و عملیات در چند مرحله با تأخیر"),
	"veron_approval": ("تأییدیه‌ها", "درخواست‌هایی که باید تأیید شوند: خرید، پرداخت، مرخصی و ..."),
	"veron_dealership": ("نمایشگاه خودرو", "پرونده‌ی هر خودرو، امانی و سرمایه‌گذاران، فروش اقساطی، قراردادهای سرمایه‌گذاری و نمایشگاه روی سایت"),
	"veron_pack_showroom": ("بسته‌ی نمایشگاه خودرو", "همه‌ی برنامه‌های یک نمایشگاه خودرو با هم: نمایشگاه، حسابداری، چک، مودیان، حقوق، پیامک و سایت"),
	"veron_moadian": ("سامانه مودیان", "صورتحساب الکترونیکی فروش برای سازمان امور مالیاتی: شماره مالیاتی، امضا، ارسال با تأیید کاربر و استعلام نتیجه"),
	"veron_payroll_iran": ("حقوق و دستمزد ایران", "فیش حقوق بر اساس قانون کار: مزد، مسکن، بن، اولاد، اضافه‌کاری، بیمه تأمین اجتماعی و مالیات حقوق، با نرخ‌های تأییدشده‌ی هر سال و سند حسابداری"),
	"veron_cheque": ("چک", "چک دریافتنی و پرداختنی با شناسه صیاد: خواباندن به حساب، وصول، برگشت، خرج کردن، دسته‌چک و سند خودکار هر مرحله"),
	"veron_rental": ("اجاره", "اجاره‌ی کالا و خودرو: رزرو بدون تداخل، تحویل، بازگشت، جریمه‌ی تأخیر و فاکتور"),
	"veron_accounting": ("حسابداری ERP-VERON", "حسابداری کامل: منوها، گزارش‌های مالی و سرفصل حساب‌های ایران"),
	"veron_apps": ("همه‌ی برنامه‌های ERP-VERON", "همه‌ی برنامه‌ها، با جایگزین رایگان برنامه‌های پولی"),
	"veron_base": ("یادداشت‌های ERP-VERON", "نمونه‌ی یک ماژول: یادداشت‌ها با منو، فهرست و فرم"),
	"veron_core": ("پایه‌ی ERP-VERON", "فارسی، تاریخ شمسی، ریال و تنظیمات ایران"),
}

PROVINCES = {
	"10": "تهران", "12": "مازندران", "13": "آذربایجان شرقی", "14": "آذربایجان غربی", "15": "کرمانشاه",
	"16": "خوزستان", "17": "فارس", "18": "کرمان", "19": "خراسان رضوی", "20": "اصفهان", "21": "خراسان شمالی",
	"22": "کردستان", "23": "هرمزگان", "24": "همدان", "25": "چهارمحال و بختیاری", "26": "لرستان", "27": "ایلام",
	"28": "کهگیلویه و بویراحمد", "29": "زنجان", "31": "خراسان جنوبی", "44": "مرکزی", "49": "البرز", "55": "گیلان",
	"61": "اردبیل", "62": "قم", "63": "قزوین", "64": "گلستان", "66": "سیستان و بلوچستان", "77": "یزد",
	"88": "بوشهر", "99": "سمنان",
}


def _iranian_week():
	saturday_to_wednesday = ("5", "6", "0", "1", "2")
	lines = []
	for day in saturday_to_wednesday:
		lines += [
			{"dayofweek": day, "hour_from": 8, "hour_to": 12, "day_period": "morning", "name": "صبح"},
			{"dayofweek": day, "hour_from": 12, "hour_to": 13, "day_period": "lunch", "name": "ناهار"},
			{"dayofweek": day, "hour_from": 13, "hour_to": 17, "day_period": "afternoon", "name": "عصر"},
		]
	lines.append({"dayofweek": "3", "hour_from": 8, "hour_to": 12, "day_period": "morning", "name": "صبح"})
	return lines
