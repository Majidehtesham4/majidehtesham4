import logging

from odoo import api, models

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
		8 to 17 with an hour for lunch, Thursday 8 to 12. A schedule changed by hand is kept."""
		if "resource.calendar" not in self.env:
			return
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
	("website.default_website", "My Website", "وب‌سایت من"),
]

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
