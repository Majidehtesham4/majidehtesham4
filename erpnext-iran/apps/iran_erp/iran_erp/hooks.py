app_name = "iran_erp"
app_title = "ERP-VERON"
app_publisher = "Majid Ehtesham"
app_description = "ERP-VERON: Persian business software built on ERPNext, with the Jalali calendar, Iranian accounting and taxes, cheques and a Persian assistant"
app_email = "ehteshammajid5@gmail.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["frappe/erpnext"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "iran_erp",
# 		"logo": "/assets/iran_erp/logo.png",
# 		"title": "Iran ERP",
# 		"route": "/iran_erp",
# 		"has_permission": "iran_erp.api.permission.has_app_permission",
# 	}
# ]

# The dock, the rail down the left of the desk, is a document rather than a hook. Author it in
# Manage Dock on a developer-mode site and press Export to App, and it is written to
# `iran_erp/dock/iran_erp/iran_erp.json` for git to carry. An app that ships none has no
# rail: its sidebar gets a switcher in the header instead.
#
# A companion app, one that extends a host app rather than standing on its own, says so with
# `mount_on` on that same record, and its entries are appended to the host's rail. Mounting keeps
# the companion off the apps screen, so it takes precedence over any add_to_apps_screen above.

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = ["/assets/iran_erp/css/persian_text.css", "/assets/iran_erp/css/iran_erp.css"]
app_include_js = [
	"/assets/iran_erp/js/jalaali_core.js",
	"/assets/iran_erp/js/jalali.js",
	"/assets/iran_erp/js/fields.js",
	"/assets/iran_erp/js/money.js",
	"/assets/iran_erp/js/brand.js",
	"/assets/iran_erp/js/charts.js",
	"/assets/iran_erp/js/tables.js",
	"/assets/iran_erp/js/ai_assistant.js",
	"/assets/iran_erp/js/inbox.js",
	"/assets/iran_erp/js/record_names.js",
	"/assets/iran_erp/js/help.js",
	"/assets/iran_erp/js/start.js",
]
doctype_js = {"Sales Invoice": "public/js/sales_invoice.js"}
# app_include_js = "/assets/iran_erp/js/iran_erp.js"

# include js, css files in header of web template
web_include_css = "/assets/iran_erp/css/persian_text.css"
# web_include_js = "/assets/iran_erp/js/iran_erp.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "iran_erp/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_kanban_js = {"doctype" : "public/js/doctype_kanban.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "iran_erp/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# The showroom website: one page for each car on it
website_route_rules = [{"from_route": "/cars/<name>", "to_route": "cars/car"}]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
jinja = {
	"methods": [
		"iran_erp.utils.jalali.format_jalali",
		"iran_erp.utils.jalali.to_persian_digits",
		"iran_erp.iran_dealership.printing.body_svg",
		"iran_erp.iran_dealership.printing.car_money",
		"iran_erp.iran_dealership.printing.car_specs",
		"iran_erp.iran_dealership.plate.plate_html",
		"iran_erp.business.trade_profile",
	],
}

# Installation
# ------------

# before_install = "iran_erp.install.before_install"
before_migrate = ["iran_erp.install.refresh_module_map"]
after_install = "iran_erp.install.after_install"
after_migrate = [
	"iran_erp.accounts.chart.install_chart_template",
	"iran_erp.desktop.add_iran_icons",
	"iran_erp.install.mark_translated_doctypes",
	"iran_erp.install.apply_branding",
	"iran_erp.install.no_update_notices",
	"iran_erp.install.setup_rial",
	"iran_erp.install.fix_upstream_reports",
	"iran_erp.install.jalali_fiscal_year_names",
	"iran_erp.install.translate_company_records",
	"iran_erp.accounts.categories.persian_descriptions",
	"iran_erp.business.after_migrate",
	"iran_erp.install.clear_translation_cache",
	# Last: the database now matches the code (the owner's panel shows who still needs the update)
	"iran_erp.owner.record_code_version",
]

# Uninstallation
# ------------

# before_uninstall = "iran_erp.uninstall.before_uninstall"
# after_uninstall = "iran_erp.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "iran_erp.utils.before_app_install"
# after_app_install = "iran_erp.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "iran_erp.utils.before_app_uninstall"
# after_app_uninstall = "iran_erp.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "iran_erp.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "iran_erp.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["iran_erp.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"User": {"on_update": "iran_erp.users.link_investor"},
	"Customer": {"validate": "iran_erp.validations.validate_iranian_ids"},
	"Supplier": {"validate": "iran_erp.validations.validate_iranian_ids"},
	"Company": {
		"validate": "iran_erp.validations.validate_iranian_ids",
		"on_update": [
			"iran_erp.accounts.chart.on_company_update",
			"iran_erp.install.on_company_update",
		],
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {"daily": ["iran_erp.business.jobs.daily"]}

# scheduler_events = {
# 	"all": [
# 		"iran_erp.tasks.all"
# 	],
# 	"daily": [
# 		"iran_erp.tasks.daily"
# 	],
# 	"hourly": [
# 		"iran_erp.tasks.hourly"
# 	],
# 	"weekly": [
# 		"iran_erp.tasks.weekly"
# 	],
# 	"monthly": [
# 		"iran_erp.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "iran_erp.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "iran_erp.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	# ERPNext's Banking page asks for a method this version of Frappe does not have
	"frappe.translate.get_boot_translations": "iran_erp.overrides.translations.get_boot_translations",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "iran_erp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# Jalali months in period reports (Sales Analytics, Trends, financial statements)
before_request = [
	"iran_erp.overrides.jalali_periods.apply",
	"iran_erp.overrides.money.apply",
	"iran_erp.overrides.translations.site_language_for_guests",
]
# after_request = ["iran_erp.utils.after_request"]

# Job Events
# ----------
before_job = ["iran_erp.overrides.jalali_periods.apply", "iran_erp.overrides.money.apply"]
# after_job = ["iran_erp.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"iran_erp.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

boot_session = "iran_erp.boot.boot_session"
