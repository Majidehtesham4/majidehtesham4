{
	"name": "AI Agents: Finance and Petty Cash",
	"summary": "Finance tools for the AI agents and the closing of petty cash funds with receipts read, checked and settled",
	"description": """
- Petty cash funds, their closings and receipts: documents asked of the custodian, photos and PDFs read
  into fields, confirmed by the custodian, duplicates and policy limits checked, findings for review,
  a draft entry, posted only after a person approves it, and the settlement report
- Finance tools of the agents: draft invoices, overdue receivables, payables due, expenses, cash
  position, unreconciled bank lines, document quality, month-end checklist, VAT summary, budget
  against actual, fixed assets
""",
	"version": "19.0.1.0.0",
	"category": "Accounting",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["veron_ai_agent", "account"],
	"data": [
		"security/security.xml",
		"security/ir.model.access.csv",
		"data/data.xml",
		"data/intents.xml",
		"data/intent_phrases.xml",
		"report/settlement_report.xml",
		"views/petty_cash_views.xml",
		"views/settings_views.xml",
	],
	"installable": True,
	"application": False,
}
