{
	"name": "ERP-VERON Apps",
	"summary": "Every app Odoo sells in Enterprise that has a free replacement, installed at once",
	"description": """
The free replacements for the paid apps of Odoo 19, from our modules and the Odoo Community
Association (OCA), with the free apps they build on (sales, inventory, manufacturing, project,
employees):

- Accounting: veron_accounting (full menus, reports, reconciliation, assets, MIS, Iranian chart) and budgets
- Documents: dms
- Sign: sign_oca
- Helpdesk: helpdesk_mgmt, with ticket types and SLA
- Field Service: fieldservice
- Subscriptions: subscription_oca and contract
- Knowledge: document_page
- Payroll: payroll (the base; Iranian rules come later)
- Quality: quality_control_oca
- Spreadsheet and dashboards: spreadsheet_oca, spreadsheet_dashboard_oca
- Planning: the project timeline
- Appointments: resource_booking, booked from the portal too
- VoIP: voip_oca, with a PBX of your own (Issabel, Asterisk...)
- Timesheets: hr_timesheet with the start/stop timer of hr_timesheet_time_control
- The full-screen apps menu: web_responsive

Not on OCA for Odoo 19: Rental, Approvals, Appraisals, Barcode, PLM, Studio, Marketing Automation,
Social Marketing, IoT and WhatsApp.
""",
	"version": "19.0.1.2.0",
	"category": "Productivity",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": [
		"veron_core",
		"web_responsive",
		"veron_accounting",
		"account_budget_oca",
		"dms",
		"sign_oca",
		"helpdesk_mgmt",
		"helpdesk_type",
		"helpdesk_mgmt_sla",
		"fieldservice",
		"subscription_oca",
		"contract",
		"document_page",
		"document_knowledge",
		"payroll",
		"quality_control_oca",
		"spreadsheet_oca",
		"spreadsheet_dashboard_oca",
		"project_timeline",
		# Appointments, phone calls from the program, work timers
		"resource_booking",
		"voip_oca",
		"hr_timesheet_time_control",
	],
	"data": ["data/groups.xml", "data/menus.xml", "data/users.xml", "views/resource_booking_portal.xml"],
	"assets": {
		"spreadsheet.o_spreadsheet": ["veron_apps/static/src/spreadsheet/shamsi.js"],
	},
	"installable": True,
	"application": True,
}
