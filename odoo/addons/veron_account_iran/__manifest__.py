{
	"name": "ERP-VERON Iranian Accounting",
	"summary": "Accounting the Iranian way: voucher numbers by Shamsi year, the official invoice and voucher, "
		"voucher templates, aggregated vouchers, insurance and good-performance deposits, the legal books, treasury",
	"description": """
What an Iranian accountant expects of the accounting, on top of ERP-VERON Accounting:

- Voucher numbers (شماره سند): one series for all the journals of a company in each Shamsi year, given
  when an entry is posted, put back in date order by a manager before the year is closed; the kind of
  each voucher (normal, opening, closing, adjusting). The entry's own number stays as the reference
- The voucher printed (سند حسابداری): accounts with their codes, debits and credits, the amount in
  words, the signatures
- The official invoice (صورتحساب فروش کالا و خدمات) and the proforma (پیش‌فاکتور), in the layout of
  the tax organization: seller and buyer with economic code, national id, registration number, postal
  code, each line with its discount and taxes, the total in words
- Voucher templates (الگوی سند): the accounts and shares of an entry made often, filled with an amount
- Aggregated vouchers (سند تجمیعی): several draft entries merged into one, the lines summed by account
  and partner
- Deposits withheld (کسورات قانونی): insurance deposit 5%, good-performance deposit 10% and withholding
  tax of vendor bills, and those withheld from us on our invoices, as taxes on their accounts of the
  Iranian chart; released to the partner by a wizard when the clearance comes
- The legal books: four-column trial balance at the group, ledger or sub-ledger level of the chart,
  the journal book (دفتر روزنامه) and the general ledger book (دفتر کل), in Shamsi
- Treasury (خزانه‌داری): the balance, receipts and payments of each cash and bank journal, what
  customers and vendors owe in the coming days, and the cheques due when the Cheques module is there

Nothing is posted by itself; the numbers and deposits follow what an accountant posts.
""",
	"version": "19.0.1.0.0",
	"category": "Accounting/Localizations",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["veron_accounting"],
	"data": [
		"security/ir.model.access.csv",
		"report/report_actions.xml",
		"report/report_voucher.xml",
		"report/report_invoice.xml",
		"report/report_books.xml",
		"report/report_treasury.xml",
		"views/account_move_views.xml",
		"views/voucher_template_views.xml",
		"wizard/wizard_views.xml",
		"views/menus.xml",
	],
	"post_init_hook": "post_init_hook",
	"installable": True,
}
