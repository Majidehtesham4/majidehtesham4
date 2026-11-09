"""The monthly insurance list of the Social Security Organization (لیست بیمه) as its two DBF files: the
workshop's totals (DSKKAR00) and each worker (DSKWOR00), from the payslips done of a Shamsi month"""

import base64
import io
import zipfile

from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.veron_core.models import jalali

from ..tools import dbf

WORKSHOP = [("DSK_ID", "C", 10), ("DSK_NAME", "C", 100), ("DSK_FARM", "C", 100), ("DSK_ADRS", "C", 100),
	("DSK_KIND", "N", 1), ("DSK_YY", "N", 2), ("DSK_MM", "N", 2), ("DSK_LISTNO", "C", 12), ("DSK_DISC", "C", 100),
	("DSK_NUM", "N", 5), ("DSK_TDD", "N", 6), ("DSK_TROOZ", "N", 12), ("DSK_TMAH", "N", 12), ("DSK_TMAZ", "N", 12),
	("DSK_TMASH", "N", 12), ("DSK_TTOTL", "N", 12), ("DSK_TBIME", "N", 12), ("DSK_TKOSO", "N", 12), ("DSK_BIC", "N", 12),
	("DSK_RATE", "N", 5), ("DSK_PRATE", "N", 2), ("DSK_BIMH", "N", 12), ("MON_PYM", "C", 3)]
WORKERS = [("DSW_ID", "C", 10), ("DSW_YY", "N", 2), ("DSW_MM", "N", 2), ("DSW_LISTNO", "C", 12), ("DSW_ID1", "C", 10),
	("DSW_FNAME", "C", 100), ("DSW_LNAME", "C", 100), ("DSW_DNAME", "C", 100), ("DSW_IDNO", "C", 15),
	("DSW_IDPLC", "C", 100), ("DSW_IDATE", "C", 8), ("DSW_BDATE", "C", 8), ("DSW_SEX", "C", 3), ("DSW_NAT", "C", 10),
	("DSW_OCP", "C", 100), ("DSW_SDATE", "C", 8), ("DSW_EDATE", "C", 8), ("DSW_DD", "N", 2), ("DSW_ROOZ", "N", 12),
	("DSW_MAH", "N", 12), ("DSW_MAZ", "N", 12), ("DSW_MASH", "N", 12), ("DSW_TOTL", "N", 12), ("DSW_BIME", "N", 12),
	("DSW_PRATE", "N", 2), ("DSW_JOB", "C", 6), ("PER_NATCOD", "C", 10)]


def ymd(value):
	"""«14050715» of a date, as the files write Shamsi dates; empty for none"""
	if not value:
		return ""
	year, month, day = jalali.to_jalali(value)
	return f"{year:04d}{month:02d}{day:02d}"


def names(employee):
	"""The first and the last name: the first word and the rest"""
	parts = (employee.name or "").split(None, 1)
	return (parts[0], parts[1]) if len(parts) == 2 else (employee.name or "", "")


def totals(slip):
	return {line.code: line.total for line in slip.line_ids}


class SsoDisk(models.TransientModel):
	_name = "veron.sso.disk"
	_description = "Social Security Disk"

	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	year = fields.Integer("Shamsi Year", required=True,
		default=lambda self: jalali.to_jalali(fields.Date.context_today(self))[0])
	month = fields.Integer("Shamsi Month", required=True,
		default=lambda self: jalali.to_jalali(fields.Date.context_today(self))[1])
	list_number = fields.Char("List Number", default="01", required=True)
	description = fields.Char(default="لیست حقوق و دستمزد")
	file = fields.Binary(readonly=True)
	filename = fields.Char()

	def _slips(self):
		start = jalali.to_gregorian(self.year, self.month, 1)
		end = jalali.to_gregorian(self.year, self.month, jalali.month_length(self.year, self.month))
		return self.env["hr.payslip"].search([("company_id", "=", self.company_id.id), ("state", "in", ("done", "paid")),
			("date_from", ">=", start), ("date_to", "<=", end)])

	def _rows(self):
		"""The worker rows and the workshop row of the month"""
		self.ensure_one()
		company = self.company_id
		if not company.veron_sso_workshop:
			raise UserError(_("Set the workshop code of the Social Security Organization in the company first."))
		slips = self._slips().filtered(lambda s: s.contract_id.veron_insured if "contract_id" in s._fields and s.contract_id
			else s.employee_id.version_id.veron_insured)
		if not slips:
			raise UserError(_("No payslip done of an insured employee in %(month)s %(year)s.",
				month=jalali.MONTHS[self.month - 1], year=self.year))
		common = {"DSW_ID": company.veron_sso_workshop, "DSW_YY": self.year % 100, "DSW_MM": self.month,
			"DSW_LISTNO": self.list_number}
		workers = []
		for slip in slips.sorted(lambda s: s.employee_id.name or ""):
			employee, version = slip.employee_id, slip.employee_id.version_id
			line = totals(slip)
			absence = sum(slip.input_line_ids.filtered(lambda l: l.code == "ABSENCE").mapped("amount"))
			days = max(min((slip.date_to - slip.date_from).days + 1 - int(absence), 31), 0)
			wage = line.get("BASE", 0.0)
			insured = line.get("INSB", 0.0)
			first, last = names(employee)
			start = version.contract_date_start
			end = version.contract_date_end
			workers.append(dict(common, **{
				"DSW_ID1": version.veron_insurance_number or "", "DSW_FNAME": first, "DSW_LNAME": last,
				"DSW_DNAME": employee.veron_father_name or "", "DSW_IDNO": employee.veron_id_number or "",
				"DSW_IDPLC": employee.veron_id_place or "", "DSW_IDATE": ymd(employee.veron_id_date),
				"DSW_BDATE": ymd(employee.birthday), "DSW_SEX": "زن" if employee.sex == "female" else "مرد",
				"DSW_NAT": "ایرانی" if (employee.country_id.code or "IR") == "IR" else (employee.country_id.name or ""),
				"DSW_OCP": employee.job_title or employee.job_id.name or "",
				"DSW_SDATE": ymd(start) if start and start >= slip.date_from else "",
				"DSW_EDATE": ymd(end) if end and end <= slip.date_to else "",
				"DSW_DD": days, "DSW_ROOZ": round(wage / days) if days else 0, "DSW_MAH": wage,
				"DSW_MAZ": max(insured - wage, 0), "DSW_MASH": insured, "DSW_TOTL": line.get("GROSS", 0.0),
				"DSW_BIME": abs(line.get("INS_EMP", 0.0)), "DSW_PRATE": 0, "DSW_JOB": employee.veron_sso_job_code or "",
				"PER_NATCOD": employee.identification_id or "",
				"_employer": line.get("INS_ER", 0.0), "_unemployment": line.get("INS_UN", 0.0),
			}))
		address = "، ".join(filter(None, [company.state_id.name, company.city, company.street]))
		workshop = {"DSK_ID": company.veron_sso_workshop, "DSK_NAME": company.name, "DSK_FARM": company.veron_sso_employer
			or company.name, "DSK_ADRS": address, "DSK_KIND": 0, "DSK_YY": self.year % 100, "DSK_MM": self.month,
			"DSK_LISTNO": self.list_number, "DSK_DISC": self.description or "", "DSK_NUM": len(workers),
			"DSK_TDD": sum(w["DSW_DD"] for w in workers), "DSK_TROOZ": sum(w["DSW_ROOZ"] for w in workers),
			"DSK_TMAH": sum(w["DSW_MAH"] for w in workers), "DSK_TMAZ": sum(w["DSW_MAZ"] for w in workers),
			"DSK_TMASH": sum(w["DSW_MASH"] for w in workers), "DSK_TTOTL": sum(w["DSW_TOTL"] for w in workers),
			"DSK_TBIME": sum(w["DSW_BIME"] for w in workers), "DSK_TKOSO": sum(w["_employer"] for w in workers),
			"DSK_BIC": sum(w["_unemployment"] for w in workers), "DSK_RATE": 23, "DSK_PRATE": 0, "DSK_BIMH": 0,
			"MON_PYM": company.veron_sso_contract_row or "000"}
		return workshop, workers

	def action_make(self):
		self.ensure_one()
		workshop, workers = self._rows()
		buffer = io.BytesIO()
		with zipfile.ZipFile(buffer, "w") as archive:
			archive.writestr("DSKKAR00.DBF", dbf.write(WORKSHOP, [workshop]))
			archive.writestr("DSKWOR00.DBF", dbf.write(WORKERS, workers))
		self.write({"file": base64.b64encode(buffer.getvalue()),
			"filename": f"sso-{self.year}-{self.month:02d}-{self.list_number}.zip"})
		return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
			"target": "new"}
