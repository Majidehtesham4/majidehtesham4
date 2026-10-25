{
	"name": "ERP-VERON Accounting",
	"summary": "Full accounting on Community: the menus, OCA financial reports, reconciliation, assets and the Iranian chart",
	"description": """
Odoo Community hides journal entries, the chart of accounts and the financial reports behind the
technical setting «Show Full Accounting Features». Here accounting managers have it, and the free OCA
modules give what the paid Accounting app does: general ledger, trial balance, open items, aged
balances and VAT report; bank reconciliation; fixed assets and depreciation; MIS reports; and OCA's
Iranian chart of accounts with the provinces and cities, loaded for a company that has recorded nothing yet.
""",
	"version": "19.0.1.0.0",
	"category": "Accounting",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": [
		"account",
		"account_financial_report",
		"account_reconcile_oca",
		"account_statement_import_file",
		"account_asset_management",
		"mis_builder",
		"l10n_ir_account",
		"l10n_ir_states",
	],
	"data": ["data/groups.xml"],
	"post_init_hook": "post_init_hook",
	"installable": True,
	"application": True,
}
