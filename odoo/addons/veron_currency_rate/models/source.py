import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
TIMEOUT = 20
NAVASAN = "https://api.navasan.tech/latest/"


def dig(data, path):
	"""The value at a dotted path of a JSON answer: «usd.value», «data.0.price»"""
	for part in (path or "").split("."):
		if isinstance(data, list):
			data = data[int(part)] if part.isdigit() and int(part) < len(data) else None
		elif isinstance(data, dict):
			data = data.get(part)
		else:
			return None
	return data


def number(value):
	"""A rate as a number, whatever digits and separators it is written with"""
	if isinstance(value, (int, float)):
		return float(value)
	text = str(value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
	text = text.replace(",", "").replace("٬", "").strip()
	try:
		return float(text)
	except ValueError:
		return None


class CurrencySource(models.Model):
	_name = "veron.currency.source"
	_description = "Source of Exchange Rates"
	_inherit = ["mail.thread"]

	name = fields.Char(required=True)
	active = fields.Boolean(default=True)
	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	kind = fields.Selection([("navasan", "Navasan"), ("json", "Any JSON Address")], required=True, default="navasan")
	url = fields.Char("Address", help="For any JSON address: the address that answers with the rates")
	api_key = fields.Char("API Key", groups="base.group_system", copy=False)
	unit = fields.Selection([("toman", "Toman"), ("rial", "Rial")], required=True, default="toman",
		help="What the source's numbers are in; Navasan's are in toman")
	max_change = fields.Float("Largest Change Accepted (%)", default=20.0,
		help="A rate that moved more than this since the last one is not used, as a wrong answer may")
	line_ids = fields.One2many("veron.currency.source.line", "source_id", "Currencies")
	last_update = fields.Datetime(readonly=True)
	last_error = fields.Text(readonly=True)

	def _answer(self):
		self.ensure_one()
		if self.kind == "navasan":
			key = self.sudo().api_key
			if not key:
				raise UserError(_("Set Navasan's API key on the source."))
			response = requests.get(NAVASAN, params={"api_key": key}, timeout=TIMEOUT)
		else:
			if not self.url:
				raise UserError(_("Set the address of the source."))
			headers = {"Accept": "application/json"}
			if self.sudo().api_key:
				headers["Authorization"] = f"Bearer {self.sudo().api_key}"
			response = requests.get(self.url, headers=headers, timeout=TIMEOUT)
		response.raise_for_status()
		return response.json()

	def action_fetch(self):
		"""The rates of today from the source; a currency whose rate is unreadable or moved too much is said, not used"""
		Rate = self.env["res.currency.rate"].sudo()
		for source in self:
			company = source.company_id
			if company.currency_id.name != "IRR":
				source.last_error = _("The currency of %s is not the rial.", company.name)
				continue
			try:
				answer = source._answer()
			except (requests.exceptions.RequestException, ValueError, UserError) as error:
				source.last_error = _("The source could not be read: %s", error)
				_logger.warning("Exchange rates of %s not fetched: %s", source.name, error)
				continue
			problems, today = [], fields.Date.context_today(source)
			for line in source.line_ids:
				value = number(dig(answer, line._path()))
				if not value or value <= 0:
					problems.append(_("%s: no rate in the answer.", line.currency_id.name))
					continue
				rials = value * (10 if source.unit == "toman" else 1) * (line.factor or 1)
				last = Rate.search([("currency_id", "=", line.currency_id.id), ("company_id", "=", company.id),
					("name", "<", today)], order="name desc", limit=1)
				if last and last.inverse_company_rate and source.max_change:
					change = abs(rials - last.inverse_company_rate) / last.inverse_company_rate * 100
					if change > source.max_change:
						problems.append(_("%(currency)s: %(new)s rials is %(change).0f%% from the last rate; not used.",
							currency=line.currency_id.name, new=f"{rials:,.0f}", change=change))
						continue
				rate = Rate.search([("currency_id", "=", line.currency_id.id), ("company_id", "=", company.id),
					("name", "=", today)], limit=1)
				values = {"inverse_company_rate": rials}
				if rate:
					rate.write(values)
				else:
					line.currency_id.sudo().active = True
					Rate.create(dict(values, currency_id=line.currency_id.id, company_id=company.id, name=today))
				line.last_rate = rials
			source.write({"last_update": fields.Datetime.now(), "last_error": "\n".join(problems) or False})

	@api.model
	def _cron_fetch(self):
		self.search([]).action_fetch()


class CurrencySourceLine(models.Model):
	_name = "veron.currency.source.line"
	_description = "Currency of a Rate Source"

	source_id = fields.Many2one("veron.currency.source", required=True, ondelete="cascade")
	currency_id = fields.Many2one("res.currency", required=True)
	key = fields.Char("Field in the Answer", help="Navasan: its item, as «usd», «eur», «aed»; another address: the "
		"dotted path to the number, as «rates.USD.sell». Empty: the currency's code in lowercase")
	factor = fields.Float(default=1.0, help="When the source gives the rate of several units, as 1/10 for 10 units")
	last_rate = fields.Float("Last Rate (Rial)", readonly=True)

	def _path(self):
		self.ensure_one()
		key = self.key or self.currency_id.name.lower()
		return f"{key}.value" if self.source_id.kind == "navasan" and "." not in key else key
