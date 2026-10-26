{
	"name": "ERP-VERON Planning",
	"summary": "Staff shifts on a timeline: who works when, in which role; conflicts with time off shown",
	"description": """
Shifts of the employees by role (cashier, driver, technician...), on a timeline grouped by employee,
in a calendar and in lists:

- A shift that overlaps another shift of the same employee, or the employee's approved time off, is
  marked as a conflict with the reason
- Publish: the employees see their shifts (Planning > My Shifts) and get a message
- Copy the previous week's shifts to the next week in one go
""",
	"version": "19.0.1.0.0",
	"category": "Human Resources/Planning",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["hr", "hr_holidays", "web_timeline", "veron_core"],
	"data": [
		"security/planning_security.xml",
		"security/ir.model.access.csv",
		"data/planning_data.xml",
		"views/planning_views.xml",
	],
	"installable": True,
	"application": True,
}
