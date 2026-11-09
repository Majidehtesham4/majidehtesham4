"""The salary tax list of a Shamsi month (لیست مالیات حقوق): each employee's taxable pay and tax, in Excel"""

import base64
import io

from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.veron_core.models import jalali

from .sso_disk import names, totals

COLUMNS = ["ردیف", "نام", "نام خانوادگی", "کد ملی", "حقوق و مزایای ناخالص", "سهم معاف بیمه", "درآمد مشمول مالیات",
	"مالیات", "خالص پرداختی"]


class TaxList(models.TransientModel):
	_name = "veron.salary.tax.list"
	_description = "Salary Tax List"

	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	year = fields.Integer("Shamsi Year", required=True,
		default=lambda self: jalali.to_jalali(fields.Date.context_today(self))[0])
	month = fields.Integer("Shamsi Month", required=True,
		default=lambda self: jalali.to_jalali(fields.Date.context_today(self))[1])
	file = fields.Binary(readonly=True)
	filename = fields.Char()

	def _rows(self):
		start = jalali.to_gregorian(self.year, self.month, 1)
		end = jalali.to_gregorian(self.year, self.month, jalali.month_length(self.year, self.month))
		slips = self.env["hr.payslip"].search([("company_id", "=", self.company_id.id), ("state", "in", ("done", "paid")),
			("date_from", ">=", start), ("date_to", "<=", end)])
		if not slips:
			raise UserError(_("No payslip done in %(month)s %(year)s.", month=jalali.MONTHS[self.month - 1], year=self.year))
		rows = []
		for index, slip in enumerate(slips.sorted(lambda s: s.employee_id.name or ""), 1):
			line = totals(slip)
			first, last = names(slip.employee_id)
			gross, taxable = line.get("GROSS", 0.0), line.get("TAXB", 0.0)
			rows.append([index, first, last, slip.employee_id.identification_id or "", gross, gross - taxable, taxable,
				abs(line.get("TAX", 0.0)), line.get("NET", 0.0)])
		return rows

	def action_make(self):
		import xlsxwriter

		self.ensure_one()
		rows = self._rows()
		buffer = io.BytesIO()
		book = xlsxwriter.Workbook(buffer, {"in_memory": True})
		sheet = book.add_worksheet(f"{self.year}-{self.month:02d}")
		sheet.right_to_left()
		head = book.add_format({"bold": True, "bg_color": "#DDDDDD", "border": 1})
		number = book.add_format({"num_format": "#,##0", "border": 1})
		text = book.add_format({"border": 1})
		for column, title in enumerate(COLUMNS):
			sheet.write(0, column, title, head)
			sheet.set_column(column, column, 18)
		for row_index, row in enumerate(rows, 1):
			for column, value in enumerate(row):
				sheet.write(row_index, column, value, number if isinstance(value, float) else text)
		last = len(rows) + 1
		sheet.write(last, 0, "جمع", head)
		for column in range(4, len(COLUMNS)):
			sheet.write(last, column, sum(row[column] for row in rows), number)
		book.close()
		self.write({"file": base64.b64encode(buffer.getvalue()), "filename": f"salary-tax-{self.year}-{self.month:02d}.xlsx"})
		return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
			"target": "new"}
