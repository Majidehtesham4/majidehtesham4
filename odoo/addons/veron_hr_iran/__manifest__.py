{
	"name": "ERP-VERON Iranian HR",
	"summary": "Loans and advances by instalment, missions, supplementary and life insurance, job classification, "
		"attendance corrections, the social security disk, the salary tax list and the bank file of salaries",
	"description": """
What the payroll of an Iranian company needs beyond the payslip itself, each feeding the payslip by its
inputs, which stay open to change on the payslip before it is computed:

- Loans and advances (وام و مساعده): the amount, the number of instalments and the first month; each
  month's instalment goes into the payslip of that month and is marked paid when the payslip is done
- Missions (مأموریت): days, in the city, out of the city or abroad, with the rate of a day of each kind;
  the per-diem goes into the payslip («فوق‌العاده مأموریت», not insured)
- Unpaid absences (غیبت): recorded and approved, their days go into the payslip as days not worked
- Supplementary and life insurance (بیمه تکمیلی، بیمه عمر): plans with the employee's share of a month,
  and the people each employee insures; the share is deducted in the payslip
- Job classification (طبقه‌بندی مشاغل): the groups of the scheme, the base wage of each group for each
  year; a contract's wage under its group's base is refused, as under the minimum wage
- Attendance corrections (اصلاحیه حضور و غیاب): an employee asks, a manager approves, and the
  attendance is made or changed; the request is kept
- The social security disk (دیسکت بیمه): the workshop list and the workers' list of a month as the
  two DBF files of the Social Security Organization (DSKKAR00, DSKWOR00)
- The salary tax list (لیست مالیات حقوق) of a month, in Excel
- The bank file of a payslip batch (پرداخت گروهی حقوق): each employee's IBAN and net pay, in Excel and
  text, with the draft payment entry

The disk follows the published layout of the Social Security Organization's files; check the first one
with the organization's program before sending it.
""",
	"version": "19.0.1.0.0",
	"category": "Human Resources/Payroll",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["veron_payroll_iran", "hr_attendance"],
	"external_dependencies": {"python": ["xlsxwriter"]},
	"data": [
		"security/security.xml",
		"security/ir.model.access.csv",
		"data/payroll_rules.xml",
		"views/hr_employee_views.xml",
		"views/loan_views.xml",
		"views/mission_views.xml",
		"views/insurance_views.xml",
		"views/job_group_views.xml",
		"views/attendance_correction_views.xml",
		"views/res_company_views.xml",
		"wizard/wizard_views.xml",
		"views/menus.xml",
	],
	"installable": True,
}
