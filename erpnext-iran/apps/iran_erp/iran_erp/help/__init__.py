"""The «آموزش» (help) panel: what a page is for and what each of its parts does."""

import frappe
from frappe import _

from iran_erp.help.guides import DOCTYPES, FIELD_TYPES, REPORTS, WORKSPACES

KINDS = ("doctype", "report", "workspace")


def saved_guide(kind: str, name: str) -> dict | None:
	"""The guide the AI model wrote earlier (or an administrator edited), if any."""
	row = frappe.db.get_value(
		"Iran Page Guide",
		{"page_kind": kind, "page_name": name},
		["name", "status", "content", "source", "modified", "error"],
		as_dict=True,
	)
	return row


@frappe.whitelist()
def get_guide(kind: str, name: str) -> dict:
	"""kind: "doctype", "report" or "workspace"."""
	guide = _builtin_guide(kind, name)
	saved = saved_guide(kind, name)
	if saved:
		guide["saved"] = {
			"status": saved.status,
			"content": saved.content,
			"source": saved.source,
			"modified": str(saved.modified),
			"error": saved.error,
		}
	guide["can_regenerate"] = "System Manager" in frappe.get_roles()
	return guide


def _builtin_guide(kind: str, name: str) -> dict:
	if kind == "doctype":
		guide = dict(DOCTYPES.get(name) or {})
		if frappe.db.exists("DocType", name):
			meta = frappe.get_meta(name)
			if not guide.get("about") and meta.description:
				guide["about"] = _(meta.description)
			guide["module"] = _(meta.module)
			guide["module_about"] = WORKSPACES.get(meta.module)
			guide["is_submittable"] = meta.is_submittable
		return guide
	if kind == "report":
		guide = dict(REPORTS.get(name) or {})
		if not guide.get("about") and frappe.db.exists("Report", name):
			ref = frappe.db.get_value("Report", name, "ref_doctype")
			if ref:
				guide["about"] = _("This report is based on {0} documents.").format(_(ref))
		return guide
	if kind == "workspace":
		return {"about": WORKSPACES.get(name) or WORKSPACES.get(name.title())}
	return {}


@frappe.whitelist()
def get_field_types() -> dict:
	return FIELD_TYPES


@frappe.whitelist(methods=["POST"])
def generate(kind: str, name: str) -> dict:
	"""Have the AI model write a full guide for a page, once; it is saved and shown from then on."""
	from iran_erp.ai.openrouter import has_api_key

	if kind not in KINDS:
		frappe.throw(_("Unknown page kind"))
	if not (frappe.db.get_single_value("Iran AI Settings", "enabled") and has_api_key()):
		frappe.throw(_("The AI assistant is disabled in Iran AI Settings."))
	saved = saved_guide(kind, name)
	if saved and saved.status == "Generating":
		return {"status": "Generating"}
	if saved and saved.status == "Ready":
		# Writing over a guide everyone already sees is for administrators, and never over a manual one
		if "System Manager" not in frappe.get_roles() or saved.source == "Manual":
			return {"status": "Ready"}
	doc = frappe.get_doc("Iran Page Guide", saved.name) if saved else frappe.new_doc("Iran Page Guide")
	doc.update({"page_kind": kind, "page_name": name, "status": "Generating", "source": "AI", "error": None})
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.enqueue(
		"iran_erp.help.write_guide",
		queue="long",
		timeout=600,
		guide=doc.name,
		lang=frappe.local.lang,
		enqueue_after_commit=True,
	)
	return {"status": "Generating"}


def page_facts(kind: str, name: str) -> str:
	"""What the system knows about a page, for the AI model to explain."""
	guide = _builtin_guide(kind, name)
	lines = [f"Page kind: {kind}", f"Page: {name} (shown to users as «{_(name)}»)"]
	if guide.get("about"):
		lines.append(f"What it is: {guide['about']}")
	for step in guide.get("steps") or []:
		lines.append(f"Step: {step}")
	if kind == "doctype" and frappe.db.exists("DocType", name):
		meta = frappe.get_meta(name)
		lines.append(f"Module: {meta.module}; submittable: {bool(meta.is_submittable)}")
		explanations = guide.get("fields") or {}
		count = 0
		for df in meta.fields:
			if df.fieldtype in ("Column Break", "HTML", "Button", "Fold") or df.hidden:
				continue
			if df.fieldtype in ("Section Break", "Tab Break"):
				if df.label:
					lines.append(f"-- {df.fieldtype}: {_(df.label)}")
				continue
			if not df.label or count >= 90:
				continue
			count += 1
			parts = [f"field «{_(df.label)}» ({df.fieldname}, {df.fieldtype}"]
			if df.options and df.fieldtype in ("Link", "Select", "Table"):
				parts.append(f", options: {str(df.options)[:120]}")
			parts.append(", required" if df.reqd else "")
			parts.append(")")
			text = explanations.get(df.fieldname) or (_(df.description) if df.description else "")
			lines.append("".join(parts) + (f": {text}" if text else ""))
	if kind == "report" and frappe.db.exists("Report", name):
		ref = frappe.db.get_value("Report", name, ["ref_doctype", "report_type"], as_dict=True)
		lines.append(f"Based on: {ref.ref_doctype}; type: {ref.report_type}")
	return "\n".join(lines)


PROMPT = """Write a guide in Persian for a complete beginner who has never used accounting or business
software, about one page of ERP-VERON (business software built on ERPNext, used by Iranian
companies, with Jalali dates and rials). Use simple everyday words and explain any accounting term
the first time it appears. Use markdown with these sections:

### این صفحه برای چیست؟
### پیش از شروع
### قدم‌به‌قدم
### هر بخش و فیلد مهم چه می‌کند
### اشتباه‌های رایج
### نکته‌ها

Keep it practical and specific to this page, with a short realistic example (Iranian names, amounts
in rials). Do not invent buttons or fields that are not listed below; for the field section, explain
the important fields only, using their Persian labels. Call the software ERP-VERON. About 400-700 words.

Facts about the page:
{facts}"""


def write_guide(guide: str, lang: str = "fa"):
	"""Background job: ask the AI model for the guide and save it."""
	from iran_erp.ai.openrouter import AIError, chat_completion, get_settings

	frappe.local.lang = lang
	doc = frappe.get_doc("Iran Page Guide", guide)
	try:
		settings = get_settings()
		prompt = PROMPT.format(facts=page_facts(doc.page_kind, doc.page_name))
		response = chat_completion(settings, [{"role": "user", "content": prompt}])
		content = (response["choices"][0]["message"].get("content") or "").strip()
		if not content:
			raise AIError(_("The AI service returned an empty response."))
		doc.db_set({"content": content, "status": "Ready", "error": None}, commit=True)
	except Exception as e:
		frappe.db.rollback()
		doc.db_set({"status": "Failed", "error": str(e)[:1000]}, commit=True)
		if not isinstance(e, AIError):
			frappe.log_error(title="Iran page guide failed")
