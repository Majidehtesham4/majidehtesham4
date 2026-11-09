"""The file of a device's software: a row a punch, with the person's device code and the time, as Excel or
text; the columns found by their titles («کد»، «شماره کارت»، «تاریخ»، «ساعت»، «No.», «Date/Time»...) or, with
no titles, the first two"""

import base64
import csv
import datetime
import io
import re

from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.veron_core.models import jalali

CODE_TITLES = ("کد", "شماره", "کارت", "پرسنلی", "ac-no", "no.", "id", "user", "enroll", "code")
DATE_TITLES = ("تاریخ", "date")
TIME_TITLES = ("ساعت", "زمان", "time")
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def moment(text):
	"""A time written as «1405/08/18 07:58», «2026-11-09 07:58:12», «18/08/1405 07:58» or the like"""
	if isinstance(text, datetime.datetime):
		return text
	text = str(text or "").translate(DIGITS).strip()
	found = re.search(r"(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{1,4})\D+(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
	if not found:
		return None
	a, b, c, hour, minute, second = (int(g) if g else 0 for g in found.groups())
	year, month, day = (a, b, c) if a > 31 else (c, b, a)
	if year < 1700:
		year, month, day = jalali.to_gregorian(year, month, day).timetuple()[:3]
	return datetime.datetime(year, month, day, hour, minute, second)


class PunchImport(models.TransientModel):
	_name = "veron.attendance.punch.import"
	_description = "Import Attendance Punches"

	device_id = fields.Many2one("veron.attendance.device", required=True)
	file = fields.Binary(required=True)
	filename = fields.Char()
	result = fields.Text(readonly=True)

	def _rows(self):
		data = base64.b64decode(self.file)
		if (self.filename or "").lower().endswith((".xlsx", ".xls")):
			from openpyxl import load_workbook

			sheet = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
			return [list(row) for row in sheet.iter_rows(values_only=True)]
		text = data.decode("utf-8-sig", errors="replace")
		dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t") if text.strip() else csv.excel
		return [row for row in csv.reader(io.StringIO(text), dialect)]

	def action_import(self):
		self.ensure_one()
		rows = [row for row in self._rows() if any(cell not in (None, "") for cell in row)]
		if not rows:
			raise UserError(_("The file has no rows."))
		titles = [str(cell or "").strip().lower() for cell in rows[0]]

		def column(names):
			return next((i for i, title in enumerate(titles) if any(name in title for name in names)), None)

		code, date, time = column(CODE_TITLES), column(DATE_TITLES), column(TIME_TITLES)
		if code is None or date is None:
			code, date, time, start = 0, 1, None, 0
		else:
			start = 1
		if time == date:
			time = None
		punches, skipped = [], 0
		for row in rows[start:]:
			value = row[date] if date < len(row) else None
			text = value if isinstance(value, datetime.datetime) else f"{value or ''} {row[time] if time is not None and time < len(row) else ''}"
			when = moment(text)
			raw = row[code] if code < len(row) else None
			person = str(int(raw) if isinstance(raw, float) else raw or "").translate(DIGITS).strip()
			if not when or not person:
				skipped += 1
				continue
			punches.append((person, when))
		made = self.device_id._record(punches)
		self.result = _("%(made)s punches recorded, %(known)s already there, %(skipped)s rows not read; %(unknown)s of codes "
			"no employee has.", made=len(made), known=len(punches) - len(made), skipped=skipped,
			unknown=len(made.filtered(lambda p: not p.employee_id)))
		return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form", "target": "new"}
