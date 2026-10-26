{
	"name": "ERP-VERON Marketing Automation",
	"summary": "Automatic campaigns: emails, SMS, to-dos and actions in steps, each after a delay",
	"description": """
A campaign follows the records of a list (customers, leads, sales orders...) that match its filter:

- Steps: an email from a template, an SMS (through the company's SMS panel), a to-do for a
  salesperson, or an action of the system
- Each step after a delay: from the start, or after the step before it (3 days after the email...)
- A step can have its own condition: only the customers who have not ordered yet...
- Records that later match the filter join the campaign; every step done is kept, with its error if any
""",
	"version": "19.0.1.0.0",
	"category": "Marketing/Marketing Automation",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["mail", "sms", "veron_core"],
	"data": [
		"security/automation_security.xml",
		"security/ir.model.access.csv",
		"data/automation_cron.xml",
		"views/automation_views.xml",
	],
	"installable": True,
	"application": True,
}
