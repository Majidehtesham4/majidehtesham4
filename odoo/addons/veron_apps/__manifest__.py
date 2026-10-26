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
- Payroll: payroll with veron_payroll_iran, the Iranian labour law, social security and salary tax
- Quality: quality_control_oca
- Spreadsheet and dashboards: spreadsheet_oca, spreadsheet_dashboard_oca
- Planning: the project timeline
- Appointments: resource_booking, booked from the portal too
- VoIP: voip_oca, with a PBX of your own (Issabel, Asterisk...)
- Timesheets: hr_timesheet with the start/stop timer of hr_timesheet_time_control
- Online payment: veron_payment_iran (Zarinpal, Zibal)
- SMS: veron_sms_iran (Kavenegar, SMS.ir, Melipayamak) instead of Odoo's paid SMS
- Barcode: veron_barcode, receipts, deliveries and stock counts with a scanner or the phone's camera
- Planning: veron_planning, staff shifts by role on a timeline, with conflicts against time off
- Appraisals: veron_appraisal, self-assessment, the manager's rating and a weighted score
- MRP II: veron_shopfloor, a tablet screen to start, pause and finish work orders
- PLM: veron_plm, engineering changes on new versions of bills of materials, approved before use
- Social Marketing: veron_social, posts to Bale, Eitaa and Telegram channels, now or scheduled
- Marketing Automation: veron_marketing_automation, emails, SMS, to-dos and actions in steps
- Android and iPhone: the web client installs as an app (PWA), as ERP-VERON
- Approvals: veron_approval, requests approved by the right people, as many as needed
- Rental: veron_rental, reservations without double booking, pickup, return, late fees, invoices
- Moadian: veron_moadian, electronic invoices to the tax organization, sent on request
- Cheques: veron_cheque, received and issued cheques with Sayad ids, cheque books and their entries
- The full-screen apps menu: web_responsive

Not built: Studio, IoT and WhatsApp.
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
		# Iranian online payment and SMS, in place of the foreign gateways and Odoo's paid SMS
		"veron_payment_iran",
		"veron_sms_iran",
		# Our own replacements of the paid apps
		"veron_barcode",
		"veron_planning",
		"veron_appraisal",
		"veron_shopfloor",
		"veron_plm",
		"veron_social",
		"veron_marketing_automation",
		"veron_approval",
		"veron_rental",
		"veron_cheque",
		"veron_payroll_iran",
		"veron_moadian",
	],
	"data": ["data/groups.xml", "data/menus.xml", "data/users.xml", "views/resource_booking_portal.xml"],
	"assets": {
		"spreadsheet.o_spreadsheet": ["veron_apps/static/src/spreadsheet/shamsi.js"],
		"web.assets_backend": ["veron_apps/static/src/timeline/shamsi.js"],
	},
	"installable": True,
	"application": True,
}
