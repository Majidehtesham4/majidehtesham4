{
	"name": "ERP-VERON Migration",
	"summary": "A company of Odoo 17 or 18 (Community or Enterprise) brought into this program with its history",
	"description": """
Brings a company from a backup of Odoo 17 or 18, also of Odoo Enterprise, into a database of this program:

- users (archived, without their passwords), contacts, bank accounts, products with their variants, units,
  price lists and vendor prices, employees and departments;
- the chart of accounts, taxes, journals, payment terms, fiscal positions and analytic accounts;
- every journal entry and invoice with its lines as it was, its number and date, the payments and the bank
  statements, the sale and purchase orders;
- the stock on hand in each location and lot, the attached files, the notes and messages, the fields added by
  Studio.

Nothing is posted or applied by the import: on the record of the migration (Settings), a person compares the
balances with the old system and confirms: the entries are posted with their old numbers, the reconciliations are
redone and the stock counted is applied. What has no place in this program is listed with its count.

Run by «odoo.ps1 import18 <backup> <database>» or «./veron import18 <backup> <address>».
""",
	"version": "19.0.1.0.0",
	"category": "Hidden",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["account", "product", "veron_core"],
	"data": [
		"security/ir.model.access.csv",
		"data/cron.xml",
		"views/migration_views.xml",
	],
	"installable": True,
	"auto_install": False,
}
