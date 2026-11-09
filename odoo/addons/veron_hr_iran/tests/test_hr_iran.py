import base64
import io
import zipfile

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..tools import dbf

# Mehr and Aban 1405
MEHR = ("2026-09-23", "2026-10-22")
ABAN = ("2026-10-23", "2026-11-21")


@tagged("post_install", "-at_install")
class TestHrIran(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env.user.group_ids |= cls.env.ref("payroll.group_payroll_manager") | cls.env.ref("account.group_account_invoice") \
			| cls.env.ref("hr_attendance.group_hr_attendance_officer")
		rates = cls.env.ref("veron_payroll_iran.payroll_year_1405")
		if rates.state == "draft":
			rates.action_confirm()
		cls.structure = cls.env.ref("veron_payroll_iran.structure_iran")
		cls.employee = cls.env["hr.employee"].create({"name": "علی رضایی", "marital": "married", "children": 1,
			"identification_id": "0012345678", "veron_father_name": "حسن", "birthday": "1990-03-21"})
		cls.employee.version_id.write({"date_version": "2026-01-01", "contract_date_start": "2026-01-01",
			"wage": 600000000, "struct_id": cls.structure.id, "veron_insurance_number": "1234567890"})
		cls.company = cls.env.company
		cls.company.write({"veron_sso_workshop": "1234567890", "veron_mission_rate_out": 3_000_000})

	def payslip(self, period=MEHR):
		slip = self.env["hr.payslip"].create({"employee_id": self.employee.id, "date_from": period[0], "date_to": period[1]})
		slip.onchange_employee()
		slip.date_from, slip.date_to = period
		return slip

	def lines(self, slip):
		return {line.code: line.total for line in slip.line_ids}

	def done(self, slip):
		slip.compute_sheet()
		slip.action_payslip_done()
		return slip

	def test_loan_by_instalments(self):
		loan = self.env["veron.hr.loan"].create({"employee_id": self.employee.id, "amount": 100_000_000, "installments": 3,
			"first_month": MEHR[0]})
		loan.action_approve()
		self.assertEqual(loan.line_ids.mapped("amount"), [33_333_333, 33_333_333, 33_333_334], "the rest on the last")
		slip = self.done(self.payslip())
		self.assertEqual(self.lines(slip)["LOAN"], -33_333_333)
		self.assertTrue(loan.line_ids[0].paid)
		self.assertEqual(loan.left, 66_666_667)
		second = self.payslip(ABAN)
		second.compute_sheet()
		self.assertEqual(self.lines(second)["LOAN"], -33_333_333, "the next month's instalment, not the paid one again")
		with self.assertRaises(UserError):
			loan.action_cancel()

	def test_typed_by_hand_stays(self):
		self.env["veron.hr.loan"].create({"employee_id": self.employee.id, "kind": "advance", "amount": 20_000_000,
			"first_month": MEHR[0]}).action_approve()
		slip = self.payslip()
		slip.compute_sheet()
		advance = slip.input_line_ids.filtered(lambda l: l.code == "ADVANCE")
		self.assertEqual((advance.amount, advance.veron_auto), (20_000_000, True))
		advance.amount = 5_000_000
		slip.compute_sheet()
		self.assertEqual(self.lines(slip)["ADVANCE"], -5_000_000, "what the payroll officer typed is kept")

	def test_mission_absence_insurance(self):
		plain = self.payslip()
		plain.compute_sheet()
		base = self.lines(plain)
		self.env["veron.hr.absence"].create({"employee_id": self.employee.id, "date": "2026-10-10", "days": 2}).action_approve()
		plan = self.env["veron.hr.insurance.plan"].create({"name": "تکمیلی دانا", "employee_share": 1_500_000})
		self.env["veron.hr.insurance.member"].create({"employee_id": self.employee.id, "plan_id": plan.id, "dependants": 2})
		absent = self.payslip()
		absent.compute_sheet()
		before = self.lines(absent)
		self.assertLess(before["BASE"], base["BASE"], "two days not worked")
		self.assertEqual({line.code: line.amount for line in absent.input_line_ids}["ABSENCE"], 2)
		self.assertEqual(before["INS_SUPP"], -4_500_000, "the employee and two family members")
		self.env["veron.hr.mission"].create({"employee_id": self.employee.id, "name": "بازدید اصفهان", "kind": "out",
			"date_from": "2026-10-01", "date_to": "2026-10-03"}).action_approve()
		slip = self.payslip()
		slip.compute_sheet()
		lines = self.lines(slip)
		self.assertEqual(lines["MISSION"], 9_000_000, "three days at the rate of a day out of the city")
		self.assertEqual(lines["GROSS"], before["GROSS"] + 9_000_000)
		self.assertEqual(lines["INSB"], before["INSB"], "the mission is not insured")

	def test_job_group_wage(self):
		group = self.env["veron.hr.job.group"].create({"number": 12, "wage_ids": [(0, 0, {"year": 1405, "daily": 25_000_000})]})
		self.employee.version_id.veron_job_group_id = group
		with self.assertRaises(ValidationError):
			self.payslip().compute_sheet()
		group.wage_ids.daily = 15_000_000
		self.payslip().compute_sheet()

	def test_attendance_correction(self):
		correction = self.env["veron.hr.attendance.correction"].create({"employee_id": self.employee.id,
			"check_in": "2026-10-05 05:00:00", "check_out": "2026-10-05 13:30:00", "reason": "کارت فراموش شد"})
		correction.action_ask()
		clerk = self.env["res.users"].create({"name": "کارمند", "login": "veron_clerk",
			"group_ids": [(6, 0, self.env.ref("base.group_user").ids)]})
		with self.assertRaises(UserError):
			correction.with_user(clerk).sudo(False).action_approve()
		correction.action_approve()
		self.assertEqual(correction.state, "approved")
		self.assertEqual(correction.attendance_id.employee_id, self.employee)
		self.assertEqual(str(correction.attendance_id.check_out), "2026-10-05 13:30:00")

	def test_sso_disk_tax_list_bank_file(self):
		slip = self.done(self.payslip())
		lines = self.lines(slip)
		wizard = self.env["veron.sso.disk"].create({"year": 1405, "month": 7})
		wizard.action_make()
		archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(wizard.file)))
		self.assertEqual(sorted(archive.namelist()), ["DSKKAR00.DBF", "DSKWOR00.DBF"])
		_fields, workers = dbf.read(archive.read("DSKWOR00.DBF"))
		worker = next(w for w in workers if w["PER_NATCOD"] == "0012345678")
		self.assertEqual((worker["DSW_ID1"], worker["DSW_FNAME"], worker["DSW_LNAME"], worker["DSW_DNAME"]),
			("1234567890", "علی", "رضایی", "حسن"))
		self.assertEqual(worker["DSW_MASH"], round(lines["INSB"]))
		self.assertEqual(worker["DSW_BIME"], round(-lines["INS_EMP"]))
		self.assertEqual(worker["DSW_BDATE"], "13690101")
		_fields, workshop = dbf.read(archive.read("DSKKAR00.DBF"))
		self.assertEqual(workshop[0]["DSK_ID"], "1234567890")
		self.assertEqual(workshop[0]["DSK_TBIME"], sum(w["DSW_BIME"] for w in workers))
		tax = self.env["veron.salary.tax.list"].create({"year": 1405, "month": 7})
		tax.action_make()
		self.assertTrue(tax.file)
		run = self.env["hr.payslip.run"].create({"name": "مهر ۱۴۰۵", "date_start": MEHR[0], "date_end": MEHR[1],
			"slip_ids": [(4, slip.id)]})
		bank = self.env["account.journal"].search([("type", "=", "bank"), ("company_id", "=", self.company.id)], limit=1)
		wizard = self.env["veron.salary.bank.file"].create({"run_id": run.id, "journal_id": bank.id})
		wizard.action_make()
		self.assertIn("علی رضایی", wizard.missing, "no IBAN: said, not paid")
		account = self.env["res.partner.bank"].create({"partner_id": self.employee.work_contact_id.id,
			"acc_number": "IR820540102680020817909002"})
		self.employee.primary_bank_account_id = account
		wizard.action_make()
		self.assertFalse(wizard.missing)
		self.assertIn("IR820540102680020817909002", base64.b64decode(wizard.text_file).decode())
		move = self.env["account.move"].browse(wizard.action_entry()["res_id"])
		self.assertEqual((move.state, sum(move.line_ids.mapped("debit"))), ("draft", round(lines["NET"])))
		with self.assertRaises(UserError):
			self.env["veron.sso.disk"].create({"year": 1405, "month": 1}).action_make()
