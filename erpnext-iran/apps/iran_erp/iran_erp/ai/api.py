import json

import frappe
from frappe import _

from iran_erp.ai.files import get_file
from iran_erp.ai.openrouter import AIError, chat_completion, get_settings, list_models


@frappe.whitelist()
def ask(question: str, previous_request: str | None = None, files: str | list | None = None) -> str:
	"""Queue a question for the assistant and return the request name to poll."""
	question = (question or "").strip()
	if not question:
		frappe.throw(_("Please write a question."))
	if not frappe.db.get_single_value("Iran AI Settings", "enabled"):
		frappe.throw(_("The AI assistant is disabled in Iran AI Settings."))
	if previous_request:
		_get_own_request(previous_request)
	if isinstance(files, str):
		files = json.loads(files or "[]")
	attachments = []
	for file_url in (files or [])[:5]:
		file = get_file(file_url)
		attachments.append({"file_url": file.file_url, "file_name": file.file_name})

	request = frappe.get_doc(
		{
			"doctype": "Iran AI Request",
			"user": frappe.session.user,
			"question": question[:4000],
			"previous_request": previous_request,
			"attachments": json.dumps(attachments, ensure_ascii=False) if attachments else None,
			"status": "Queued",
		}
	).insert(ignore_permissions=True)

	frappe.enqueue(
		"iran_erp.ai.assistant.run_request",
		queue="long",
		timeout=900,
		request_name=request.name,
		enqueue_after_commit=True,
	)
	return request.name


@frappe.whitelist()
def get_result(request_name: str) -> dict:
	request = _get_own_request(request_name)
	return {
		"status": request.status,
		"answer": request.answer,
		"error": request.error,
		"actions": json.loads(request.actions or "[]"),
	}


def _get_own_request(name: str):
	request = frappe.get_doc("Iran AI Request", name)
	if request.user != frappe.session.user and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return request


@frappe.whitelist()
def test_connection() -> str:
	"""Check the API key and model from Iran AI Settings with a tiny request."""
	frappe.only_for("System Manager")
	try:
		settings = get_settings()
		try:
			models = list_models(settings.base_url)
		except Exception:
			models = []
		missing = [m for m in [settings.model, *settings.fallback_models] if models and m not in models]
		if missing:
			suggestions = [m for m in models if m.endswith(":free")][:6] + [
				m for m in models if m.startswith("anthropic/")
			][:4]
			return _("Model {0} was not found on OpenRouter. Some available models: {1}").format(
				", ".join(missing), ", ".join(suggestions)
			)
		response = chat_completion(settings, [{"role": "user", "content": "Reply with the single word: OK"}])
		reply = (response["choices"][0]["message"].get("content") or "").strip()
		# With fallbacks, OpenRouter reports which model actually answered
		return _("Connection works. Model {0} replied: {1}").format(
			response.get("model") or settings.model, reply[:100]
		)
	except AIError as e:
		return str(e)
