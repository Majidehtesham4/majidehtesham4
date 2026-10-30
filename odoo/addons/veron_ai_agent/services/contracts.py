"""The contract of every tool: the area of work it belongs to, what the person gets back (an answer, a report with
its records to open, a draft form, an approval), the records it is about, what is never guessed for it, and whether
the built-in assistant reaches it or only the agents do.

What a tool does, its arguments, models and level are read from the tool itself (services/registry.py); what is
here is what the code of the tool does not say. A test checks that every registered tool has a contract."""

from . import registry

# The areas of work of the assistants; an assistant of an area takes the tools of several modules
DOMAINS = {
	"system": "عمومی سیستم و راهبری",
	"sales": "فروش، CRM و مشتری",
	"purchase": "خرید و تأمین‌کننده",
	"stock": "انبار و لجستیک",
	"manufacturing": "تولید، PLM، کیفیت و نگهداری",
	"service": "خدمات پس از فروش، پشتیبانی و تعمیر",
	"project": "پروژه، برنامه‌ریزی، تایم‌شیت و نوبت‌دهی",
	"finance": "مالی، حسابداری و خزانه",
	"hr": "منابع انسانی و حقوق",
	"website": "وب‌سایت، فروشگاه آنلاین و بازاریابی",
	"documents": "اسناد، دانش، امضا، تأییدها و کارهای اداری",
	"industry": "قالب‌های صنفی",
}
# What the person gets back
RESULTS = {
	"answer": "پاسخ کوتاه در گفت‌وگو، با پیوند رکوردها",
	"report": "خلاصه در گفت‌وگو و دکمه‌ی باز کردن همان رکوردها در برنامه",
	"form": "پیش‌نویس واقعی در برنامه، با دکمه‌ی باز کردن فرم آن",
	"suggestion": "پیشنهاد؛ چیزی تغییر نمی‌کند",
	"approval": "درخواست تأیید؛ تا یک شخص تأیید نکند انجام نمی‌شود",
	"agent": "فقط برای ایجنت‌ها و سوپروایزر؛ از گفت‌وگوی دستیار داخلی خوانده نمی‌شود",
}

# code: (domain, result, entities, never guessed, note)
CONTRACTS = {
	"activity_create": ("documents", "form", ("mail.activity",), ("summary", "user_id"),
		"A follow-up on a record the person names; the summary is the person's words"),
	"asset_check": ("finance", "report", ("account.asset",), (), ""),
	"attachment_read": ("documents", "agent", ("ir.attachment",), (), "Reads the files of a record for an agent"),
	"attendance_leave_review": ("hr", "report", ("hr.leave",), (), ""),
	"bank_unreconciled": ("finance", "report", ("account.bank.statement.line",), (), ""),
	"bill_from_document": ("finance", "form", ("account.move", "res.partner"), ("source_id", "amounts"),
		"Read from the file sent; a vendor or an amount not found in the file is asked, not made up"),
	"budget_vs_actual": ("finance", "report", ("crossovered.budget.lines",), (), ""),
	"cash_position": ("finance", "report", ("account.journal",), (), ""),
	"content_draft": ("website", "agent", ("veron.ai.content",), (), "Text drafts of the marketing agents"),
	"content_publish": ("website", "agent", ("veron.ai.content",), ("draft_id",), "Publishing waits for a person"),
	"customer_summary": ("sales", "answer", ("res.partner",), ("partner_id",), ""),
	"delegate_task": ("system", "agent", ("veron.ai.task",), (), "A supervisor's task to an agent of its team"),
	"document_extract": ("documents", "answer", ("veron.ai.source",), ("source_id",), "Reads the file sent"),
	"documents_quality": ("finance", "report", ("account.move",), (), ""),
	"employee_missing_info": ("hr", "report", ("hr.employee",), (), ""),
	"escalate_to_human": ("system", "agent", (), (), "An agent hands the run to a person"),
	"expense_summary": ("finance", "report", ("account.move.line",), (), ""),
	"image_draft": ("website", "agent", ("veron.ai.content",), (), "Needs an image service; off without one"),
	"invoice_draft_create": ("finance", "form", ("account.move", "res.partner", "product.product"),
		("partner_id", "product_id", "price_unit", "taxes"),
		"Every line checked first, nothing made if one fails. Price: said, the customer's price list, the customer's "
		"last posted sale of the product (when the settings allow), the product's price; none of them: nothing is "
		"made and the price is asked. Discount: said, or the same one of the customer's last sales of the same "
		"product. Taxes: said, as set in the AI settings, or asked"),
	"invoice_draft_update": ("finance", "form", ("account.move", "product.product"),
		("move_id", "product_id", "discount", "quantity", "price_unit"),
		"Only a draft; a product named is one of its lines"),
	"invoice_post": ("finance", "approval", ("account.move",), ("move_id",), "Posting always waits for a person"),
	"knowledge_search": ("documents", "answer", ("document.page",), ("query",), ""),
	"month_end_checklist": ("finance", "report", ("account.move",), (), ""),
	"notify_external": ("system", "agent", ("res.partner",), ("partner_id", "body"), "Contacting outside waits for a person"),
	"notify_internal": ("system", "agent", ("res.users",), (), ""),
	"order_receipt_bill_check": ("purchase", "report", ("purchase.order.line",), (), ""),
	"page_overview": ("system", "answer", (), (), "The page the person has open"),
	"payables_due": ("finance", "report", ("account.move",), (), ""),
	"payroll_compare_previous": ("hr", "report", ("hr.payslip",), (), ""),
	"payroll_inputs_check": ("hr", "report", ("hr.employee",), (), ""),
	"payslip_drafts_compute": ("hr", "form", ("hr.payslip",), ("rates",),
		"The year's rates are confirmed by a person; the tool stops and asks when they are not"),
	"payslip_pdf_prepare": ("hr", "report", ("hr.payslip",), (), ""),
	"petty_cash_draft_entry": ("finance", "form", ("veron.petty.cash.closing", "account.move"), ("closing_id",), ""),
	"petty_cash_open": ("finance", "form", ("veron.petty.cash.closing",), ("fund_id",), ""),
	"petty_cash_post": ("finance", "approval", ("veron.petty.cash.closing", "account.move"), ("closing_id",),
		"Posting always waits for a person"),
	"petty_cash_report": ("finance", "report", ("veron.petty.cash.closing",), ("closing_id",), ""),
	"petty_cash_review": ("finance", "form", ("veron.petty.cash.closing",), ("closing_id",), ""),
	"product_quality": ("stock", "report", ("product.template",), (), ""),
	"purchase_compare": ("purchase", "report", ("purchase.order.line",), ("product_id",), ""),
	"purchase_late": ("purchase", "report", ("purchase.order.line",), (), ""),
	"purchase_summary": ("purchase", "report", ("purchase.order",), (), ""),
	"quotes_pending": ("sales", "report", ("sale.order",), (), ""),
	"receivables_overdue": ("finance", "report", ("account.move",), (), ""),
	"record_read": ("system", "agent", (), ("id",), "One record, for the agents; the assistant reads the record a person has open with page_overview"),
	"records_aggregate": ("system", "agent", (), (), "Totals grouped by any field; the agents choose the fields"),
	"records_import": ("documents", "approval", ("res.partner", "product.template"), ("source_id", "target"),
		"Rows of a spreadsheet sent; made only after a person approves"),
	"records_search": ("system", "answer", (), ("model",), "Search in a section of the program"),
	"report_pdf": ("system", "agent", (), (), "The PDF of an agent's report"),
	"request_human_input": ("system", "agent", (), (), "An agent asks a person"),
	"review_task": ("system", "agent", ("veron.ai.task",), (), "A supervisor reviews a task"),
	"sales_documents_read": ("sales", "answer", ("sale.order", "account.move"), ("ref", "partner_id"),
		"A document by its number or its customer; a number not found is said, no other document is shown in its place"),
	"sales_summary": ("sales", "report", ("sale.order",), (), ""),
	"spreadsheet_read": ("documents", "answer", ("veron.ai.source",), ("source_id",), ""),
	"stock_alerts": ("stock", "report", ("stock.quant",), (), ""),
	"stock_transfer_draft": ("stock", "form", ("stock.picking", "stock.warehouse", "product.product"),
		("product_id", "quantity", "from_warehouse_id", "to_warehouse_id"), "A draft transfer; not confirmed or done"),
	"stock_transfer_suggest": ("stock", "suggestion", ("stock.warehouse.orderpoint",), (), ""),
	"tasks_followup": ("project", "report", ("mail.activity",), (), ""),
	"tax_summary": ("finance", "report", ("account.move.line",), (), ""),
	"units_status": ("hr", "report", ("hr.department",), (), ""),
	"web_search": ("system", "agent", (), ("query",), "Needs an outside search service; off on the built-in route"),
	"website_report": ("website", "report", ("website.visitor",), (), "Needs the website module"),
}

# Areas of the program with modules in this project and no tool of the assistant yet: said, not made up
NO_TOOLS = {
	"manufacturing": "mrp, veron_plm, veron_shopfloor, quality_control_oca",
	"service": "helpdesk_mgmt, fieldservice",
	"project": "project, hr_timesheet, veron_planning, resource_booking (only follow-up activities are read)",
	"industry": "veron_dealership, veron_pack_showroom, veron_rental",
	"documents": "dms, sign_oca, veron_approval (only files sent in the chat and the knowledge pages are read)",
}


def contract(code):
	"""The contract of a tool as a dict, or None when it has none"""
	item = CONTRACTS.get(code)
	if not item:
		return None
	domain, result, entities, never, note = item
	return {"domain": domain, "result": result, "entities": list(entities), "never_guessed": list(never), "note": note}


def catalog(env):
	"""Every registered tool with its contract, the commands of the library that reach it and what is missing"""
	intents = env["veron.ai.intent"].sudo().with_context(active_test=False).search([])
	routes = {}
	for intent in intents:
		if intent.tool_code:
			routes.setdefault(intent.tool_code, []).append(intent.code)
	rows = []
	for code, tool in sorted(registry.TOOLS.items()):
		item = contract(code) or {}
		schema = tool.schema or {}
		gaps = []
		if not item:
			gaps.append("no contract")
		elif item["result"] != "agent" and not routes.get(code):
			gaps.append("no command of the assistant reaches it")
		if not tool.available(env):
			gaps.append("its models are not installed")
		rows.append(dict(item, code=code, name=tool.label(env), module=tool.module, category=tool.category,
			action=tool.action, level=tool.level, risk=tool.risk, sensitive=tool.sensitive, models=list(tool.models),
			required=list(schema.get("required") or []), optional=sorted(set(schema.get("properties") or {}) -
			set(schema.get("required") or [])), available=tool.available(env), commands=routes.get(code, []), gaps=gaps))
	orphans = [intent.code for intent in intents if intent.tool_code and intent.tool_code not in registry.TOOLS]
	return {"tools": rows, "commands_without_tool": orphans, "areas_without_tools": NO_TOOLS}
