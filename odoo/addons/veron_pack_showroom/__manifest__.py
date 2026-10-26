{
	"name": "ERP-VERON Pack: Car Showroom",
	"summary": "Everything a car showroom uses, installed at once: the showroom, sales, accounting, cheques, Moadian, payroll, SMS, payment and the website",
	"description": """
The business pack of a car showroom. It installs, in Persian and Shamsi:

- veron_dealership: the cars, consignment and investors, instalment sales, investment contracts,
  the showroom on the website
- Accounting with the Iranian chart, cheques, Moadian invoices
- CRM for the inquiries, contacts and documents
- Employees, Iranian payroll, time off
- Iranian SMS panels and payment gateways, the website

On a server: ./veron new erp.example.ir veron_pack_showroom "نام نمایشگاه"
On Windows: .\\odoo.ps1 install veron_pack_showroom <database>
""",
	"version": "19.0.1.0.0",
	"category": "Sales",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": [
		"veron_core",
		"veron_accounting",
		"veron_dealership",
		"veron_cheque",
		"veron_moadian",
		"veron_payroll_iran",
		"veron_sms_iran",
		"veron_payment_iran",
		"veron_approval",
		"crm",
		"hr_holidays",
		"contacts",
		"website",
		"web_responsive",
	],
	"installable": True,
	"application": False,
}
