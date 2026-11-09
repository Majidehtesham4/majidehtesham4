{
	"name": "ERP-VERON Rotating Shifts",
	"summary": "Rotating shift patterns (morning, evening, night, rest...) turned into the planning's shifts for each person",
	"description": """
- A pattern is a cycle of days: each day a shift (its start and hours, its role) or a rest; e.g. two mornings,
  two evenings, two nights, two rests for the 24-hour work of a factory or a hospital
- Each person on the pattern starts at a day of the cycle, so the groups follow each other
- The shifts of a period made as drafts of the planning, never over one the person already has; then
  checked, changed and published in the planning as any other
- A floating shift is the working schedule's «flexible hours»: the hours a day without a set start
""",
	"version": "19.0.1.0.0",
	"category": "Human Resources/Planning",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["veron_planning"],
	"data": [
		"security/ir.model.access.csv",
		"wizard/generate_views.xml",
		"views/rotation_views.xml",
	],
	"installable": True,
}
