{
	"name": "ERP-VERON Iranian Payroll",
	"summary": "Payslips by the Iranian labour law: wage, housing, food, child and marriage allowances, overtime, social security and salary tax, with the entry in accounting",
	"description": """
Payroll by the Iranian labour law, on the OCA payroll:

- The rates of each Shamsi year (minimum wage, housing, food, child and marriage allowances, the
  insurance ceiling, overtime and night work, the tax exemption and its brackets) in one table,
  with their sources. A year's rates are filled as a draft; no payslip is computed until a
  payroll manager checks them against the official resolution and confirms them.
- The structure «قانون کار ایران»: base wage by the days of the Shamsi month, allowances, overtime
  1.4, night work 0.35, holiday work, the social security of the employee (7%) and of the employer
  (20% + 3% unemployment), up to the ceiling, the salary tax by brackets, loans and advances;
  the provisions for the new-year bonus (Eidi) and the severance (Sanavat)
- Payslips of a Shamsi month by default, named in Shamsi
- A draft accounting entry for each payslip done, on the accounts of the Iranian chart; it is
  posted by the accountant
- Every rule is a salary rule of payroll, open to change
""",
	"version": "19.0.1.0.0",
	"category": "Human Resources/Payroll",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["payroll", "account", "veron_accounting"],
	"data": [
		"security/ir.model.access.csv",
		"security/payroll_security.xml",
		"data/payroll_structure.xml",
		"data/payroll_year_data.xml",
		"views/payroll_year_views.xml",
		"views/hr_version_views.xml",
		"views/hr_payslip_views.xml",
		"views/hr_salary_rule_views.xml",
	],
	"installable": True,
	"application": False,
}
