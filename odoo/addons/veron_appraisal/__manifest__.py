{
	"name": "ERP-VERON Appraisal",
	"summary": "Employee appraisals: self-assessment, the manager's rating and a weighted score",
	"description": """
Periodic employee appraisals:

- Forms of questions (rated 1 to 5 stars, or written answers) with a weight each
- Start an appraisal for one employee or many: the employee rates themself, the manager rates them;
  both get a to-do
- The score is the weighted average of the manager's ratings; the appraisal is closed by the manager
- Each employee sees their own appraisals, a manager those of their team, HR all of them
""",
	"version": "19.0.1.0.0",
	"category": "Human Resources/Appraisals",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["hr", "veron_core"],
	"data": [
		"security/appraisal_security.xml",
		"security/ir.model.access.csv",
		"data/appraisal_data.xml",
		"views/appraisal_views.xml",
	],
	"installable": True,
	"application": True,
}
