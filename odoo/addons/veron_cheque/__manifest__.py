{
	"name": "ERP-VERON Cheques",
	"summary": "Received and issued cheques: Sayad id, due dates, bank deposit, cashing, bounced cheques, with their accounting entries",
	"description": """
Cheques the Iranian way, each step with its accounting entry:

Received cheques (from customers):
  in hand -> deposited to the bank -> cashed, or bounced -> returned to the customer;
  or endorsed to a vendor
Issued cheques (to vendors), from cheque books:
  issued -> cashed, or cancelled

- Sayad id (16 digits), serial, bank, branch, due date (Shamsi), amount in words
- Accounts of the Iranian chart by default: cheques in hand 111203, in collection 111201, bounced
  111306, notes payable 211101; changeable in Accounting settings
- Due lists, overdue cheques, a to-do three days before each due date
""",
	"version": "19.0.1.0.0",
	"category": "Accounting/Accounting",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["account", "veron_accounting"],
	"data": [
		"security/cheque_security.xml",
		"security/ir.model.access.csv",
		"data/cheque_data.xml",
		"views/cheque_views.xml",
		"views/res_config_settings_views.xml",
	],
	"installable": True,
	"application": True,
}
