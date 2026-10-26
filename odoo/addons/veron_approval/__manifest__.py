{
	"name": "ERP-VERON Approvals",
	"summary": "Requests that need approval: purchases, payments, leave of absence, anything; approvers and how many must agree",
	"description": """
Requests approved by the right people before anything is done:

- Categories (purchase request, payment, mission, loan...) with their approvers, and how many of them
  must approve (one, several, or all); a category may ask for an amount, a date, a product
- The approvers get a to-do; each approves or refuses with a reason; the requester is told
- Each user sees their own requests and those they must approve; approval managers see all
""",
	"version": "19.0.1.0.0",
	"category": "Productivity/Approvals",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["mail", "product", "veron_core"],
	"data": [
		"security/approval_security.xml",
		"security/ir.model.access.csv",
		"data/approval_data.xml",
		"views/approval_views.xml",
	],
	"installable": True,
	"application": True,
}
