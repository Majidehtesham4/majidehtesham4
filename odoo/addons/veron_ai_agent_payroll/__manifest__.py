{
	"name": "AI Agents: Payroll",
	"summary": "Payroll tools for the AI agents: inputs checked, payslips computed by the payroll engine, changes from last month, confidential payslip PDFs",
	"description": """
- The inputs of a Shamsi month checked: the year's rates confirmed, each employee's contract, structure,
  wage against the minimum, national code, insurance number and bank account
- Payslips computed only by the payroll engine (veron_payroll_iran); an agent gives no amount and no
  rate, and stops when the year's rates are not confirmed
- Changes from the last month as percentages; salary amounts are not sent to the language model
- The PDF of each payslip, kept so only the employee and payroll managers open it
- No payment: paying salaries stays with people in accounting
""",
	"version": "19.0.1.0.0",
	"category": "Human Resources/Payroll",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["veron_ai_agent", "veron_payroll_iran"],
	"data": [
		"security/security.xml",
		"security/ir.model.access.csv",
		"data/data.xml",
		"views/payslip_document_views.xml",
	],
	"installable": True,
	"application": False,
}
