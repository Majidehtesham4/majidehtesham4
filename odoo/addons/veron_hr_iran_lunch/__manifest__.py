{
	"name": "ERP-VERON Lunch in Payroll",
	"summary": "The employee's share of the lunches ordered in the month, deducted in the payslip",
	"description": """
The lunches an employee ordered in the Lunch app in the month of a payslip (confirmed or sent, not
cancelled), at the share of the cost the company sets (100% when the employee pays all of it), go into
the payslip as the deduction «کسر هزینه غذا». Typed by hand on the payslip, the amount stays.
""",
	"version": "19.0.1.0.0",
	"category": "Human Resources/Payroll",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["veron_hr_iran", "lunch"],
	"data": ["data/payroll_rules.xml", "views/res_company_views.xml"],
	"auto_install": True,
	"installable": True,
}
