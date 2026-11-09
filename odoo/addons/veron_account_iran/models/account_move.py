import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.veron_core.models import jalali


def shamsi(value):
	"""«1405/08/18» of a date, whatever the language of the report"""
	if not value:
		return ""
	year, month, day = jalali.to_jalali(fields.Date.to_date(value))
	return f"{year}/{month:02d}/{day:02d}"


class AccountMove(models.Model):
	_inherit = "account.move"

	veron_voucher_number = fields.Integer("Voucher Number", copy=False, readonly=True, index=True,
		help="One series for all the journals of the company in the Shamsi year, given when the entry is posted")
	veron_voucher_year = fields.Integer("Voucher Year", copy=False, readonly=True, index=True)
	veron_voucher_kind = fields.Selection([
		("normal", "Normal"), ("opening", "Opening"), ("closing", "Closing"), ("adjusting", "Adjusting"),
	], "Voucher Kind", default="normal", copy=False)
	veron_voucher = fields.Char("Voucher", compute="_compute_veron_voucher")
	veron_aggregated_from = fields.Text("Aggregated From", readonly=True, copy=False,
		help="The entries this voucher was made of")

	@api.depends("veron_voucher_number", "veron_voucher_year")
	def _compute_veron_voucher(self):
		for move in self:
			move.veron_voucher = f"{move.veron_voucher_year}-{move.veron_voucher_number}" \
				if move.veron_voucher_number else ""

	def _post(self, soft=True):
		posted = super()._post(soft)
		for move in posted.filtered(lambda m: not m.veron_voucher_number).sorted(lambda m: (m.date, m.id)):
			move._veron_give_number()
		return posted

	def _veron_give_number(self):
		"""The next voucher number of the company and Shamsi year; two posts at once wait for each other"""
		self.ensure_one()
		year = jalali.to_jalali(self.date)[0]
		# The numbers given in this transaction are written first, so the next one follows them
		self.flush_model(["veron_voucher_number", "veron_voucher_year"])
		self.env.cr.execute("SELECT pg_advisory_xact_lock(%s, %s)", [7_310_405, self.company_id.id * 10_000 + year])
		self.env.cr.execute("SELECT COALESCE(MAX(veron_voucher_number), 0) FROM account_move "
			"WHERE company_id = %s AND veron_voucher_year = %s", [self.company_id.id, year])
		self.write({"veron_voucher_number": self.env.cr.fetchone()[0] + 1, "veron_voucher_year": year})

	def _veron_renumber(self, company, year):
		"""The posted vouchers of a Shamsi year numbered again in the order of their dates, from 1. Refused when
		the year is closed by a lock date: the numbers of a closed year are its legal record"""
		start = jalali.to_gregorian(year, 1, 1)
		end = jalali.to_gregorian(year + 1, 1, 1) - datetime.timedelta(days=1)
		locks = [company[name] for name in ("fiscalyear_lock_date", "hard_lock_date") if name in company._fields]
		lock = max(filter(None, locks), default=None)
		if lock and lock >= start:
			raise UserError(_("The year %s is locked; its voucher numbers are not changed.", year))
		self.env.flush_all()
		moves = self.search([("company_id", "=", company.id), ("state", "=", "posted"), ("date", ">=", start),
			("date", "<=", end)])
		# The opening voucher first and the closing one last, the rest by date
		rank = {"opening": 0, "normal": 1, "adjusting": 1, "closing": 2}
		ordered = moves.sorted(lambda m: (rank.get(m.veron_voucher_kind or "normal", 1), m.date, m.id))
		self.env.cr.execute("UPDATE account_move SET veron_voucher_number = NULL WHERE id = ANY(%s)", [moves.ids])
		for number, move in enumerate(ordered, 1):
			self.env.cr.execute("UPDATE account_move SET veron_voucher_number = %s, veron_voucher_year = %s WHERE id = %s",
				[number, year, move.id])
		moves.invalidate_recordset(["veron_voucher_number", "veron_voucher_year", "veron_voucher"])
		return len(ordered)

	# --- what the printed documents show

	def _veron_shamsi_date(self, value):
		return shamsi(value)

	def _veron_words(self, amount):
		currency = self.currency_id or self.company_id.currency_id
		return currency.with_context(lang="fa_IR").amount_to_text(abs(amount or 0.0))

	def _veron_party(self, partner):
		"""What the official invoice shows of a seller or a buyer"""
		partner = partner.commercial_partner_id
		address = "، ".join(filter(None, [partner.state_id.name, partner.city, partner.street, partner.street2]))
		return {
			"name": partner.name or "",
			"economic": partner.vat or "",
			"national": partner["veron_national_id"] if "veron_national_id" in partner._fields else "",
			"registry": partner.company_registry if "company_registry" in partner._fields else "",
			"zip": partner.zip or "",
			"phone": partner.phone or "",
			"address": address,
		}

	def _veron_invoice_lines(self):
		"""The lines of the official invoice: the amount before the discount, the discount, the taxes"""
		rows = []
		for line in self.invoice_line_ids.filtered(lambda l: l.display_type == "product"):
			gross = line.quantity * line.price_unit
			sign = -1 if self.move_type in ("out_refund", "in_refund") else 1
			rows.append({
				"code": line.product_id.default_code or "",
				"name": line.name or line.product_id.display_name or "",
				"quantity": line.quantity,
				"uom": line.product_uom_id.name or "",
				"price": line.price_unit,
				"gross": gross,
				"discount": gross - line.price_subtotal,
				"net": line.price_subtotal,
				"tax": line.price_total - line.price_subtotal,
				"total": line.price_total,
				"sign": sign,
			})
		return rows

	def _veron_title(self):
		if self.move_type in ("out_refund", "in_refund"):
			return "صورتحساب برگشت از فروش"
		if self.state == "draft":
			return "پیش‌فاکتور"
		return "صورتحساب فروش کالا و خدمات"
