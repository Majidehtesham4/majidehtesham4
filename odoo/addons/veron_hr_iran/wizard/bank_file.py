"""The salaries of a payslip batch paid at once by the bank (پرداخت گروهی حقوق): each employee's IBAN and net
pay in Excel and as text, and the draft entry that pays them from the bank"""

import base64
import io
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .sso_disk import totals


def iban(account):
	"""«IR» and 24 digits of a bank account, or empty when it is not an Iranian IBAN"""
	digits = re.sub(r"\s", "", (account.acc_number or "").upper()) if account else ""
	if digits and not digits.startswith("IR") and len(digits) == 24 and digits.isdigit():
		digits = "IR" + digits
	return digits if re.fullmatch(r"IR\d{24}", digits) else ""


class BankFile(models.TransientModel):
	_name = "veron.salary.bank.file"
	_description = "Salary Bank File"

	run_id = fields.Many2one("hr.payslip.run", "Payslip Batch", required=True,
		default=lambda self: self.env.context.get("active_id") if self.env.context.get("active_model") == "hr.payslip.run" else False)
	journal_id = fields.Many2one("account.journal", "Paid From", required=True, domain="[('type', '=', 'bank')]")
	date = fields.Date(required=True, default=fields.Date.context_today)
	description = fields.Char(default="حقوق")
	missing = fields.Text("Without an IBAN", readonly=True)
	file = fields.Binary("Excel", readonly=True)
	filename = fields.Char()
	text_file = fields.Binary("Text", readonly=True)
	text_filename = fields.Char()
	move_id = fields.Many2one("account.move", "Payment Entry", readonly=True)

	@api.model
	def _slips(self, run):
		return run.slip_ids.filtered(lambda s: s.state in ("done", "paid"))

	def _rows(self):
		self.ensure_one()
		slips = self._slips(self.run_id)
		if not slips:
			raise UserError(_("No payslip of this batch is done."))
		rows, missing = [], []
		for slip in slips.sorted(lambda s: s.employee_id.name or ""):
			employee = slip.employee_id
			net = totals(slip).get("NET", 0.0)
			number = iban(employee.primary_bank_account_id)
			if not number:
				missing.append(employee.name)
				continue
			rows.append({"name": employee.name, "national": employee.identification_id or "", "iban": number,
				"amount": round(net), "partner": employee.work_contact_id})
		return rows, missing

	def action_make(self):
		import xlsxwriter

		self.ensure_one()
		rows, missing = self._rows()
		buffer = io.BytesIO()
		book = xlsxwriter.Workbook(buffer, {"in_memory": True})
		sheet = book.add_worksheet("salaries")
		sheet.right_to_left()
		head = book.add_format({"bold": True, "bg_color": "#DDDDDD", "border": 1})
		for column, title in enumerate(["ردیف", "نام", "کد ملی", "شماره شبا", "مبلغ (ریال)", "شرح"]):
			sheet.write(0, column, title, head)
			sheet.set_column(column, column, 26 if column == 3 else 16)
		lines = []
		for index, row in enumerate(rows, 1):
			sheet.write_row(index, 0, [index, row["name"], row["national"], row["iban"], row["amount"], self.description or ""])
			lines.append(f"{row['iban']},{row['amount']},{row['national']},{row['name']},{self.description or ''}")
		book.close()
		self.write({
			"file": base64.b64encode(buffer.getvalue()), "filename": f"salaries-{self.run_id.name}.xlsx",
			"text_file": base64.b64encode("\r\n".join(lines).encode("utf-8")), "text_filename": f"salaries-{self.run_id.name}.txt",
			"missing": "\n".join(missing) or False,
		})
		return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
			"target": "new"}

	def action_entry(self):
		"""The draft entry paying the salaries of the file from the bank: the salaries payable (211208) of each
		employee against the bank account"""
		self.ensure_one()
		rows, _missing = self._rows()
		company = self.journal_id.company_id
		payable = self.env["account.account"].search([("code", "=", "211208"), ("company_ids", "in", company.id)], limit=1)
		if not payable or not self.journal_id.default_account_id:
			raise UserError(_("The account of salaries payable (211208) or the bank's account is not set."))
		total = sum(row["amount"] for row in rows)
		lines = [(0, 0, {"account_id": payable.id, "partner_id": row["partner"].id or False, "debit": row["amount"],
			"name": f"{self.description or ''} {row['name']}"}) for row in rows if row["amount"]]
		lines.append((0, 0, {"account_id": self.journal_id.default_account_id.id, "credit": total,
			"name": f"{self.description or ''} {self.run_id.name}"}))
		self.move_id = self.env["account.move"].create({"move_type": "entry", "journal_id": self.journal_id.id,
			"date": self.date, "ref": f"{self.description or ''} {self.run_id.name}", "line_ids": lines})
		return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": self.move_id.id, "view_mode": "form"}
