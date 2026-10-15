import base64
import json

import frappe
from frappe import _

from iran_erp.ai.files import get_file
from iran_erp.ai.openrouter import AIError, chat_completion, get_settings, list_models, transcribe_audio


@frappe.whitelist()
def ask(
	question: str,
	previous_request: str | None = None,
	files: str | list | None = None,
	force_ai: int = 0,
	wrong_request: str | None = None,
) -> str:
	"""Answer a known command right away, or queue the question for the AI model.

	Returns the request name to poll; a command's request is already Done.
	"""
	from iran_erp.ai.openrouter import has_api_key

	question = (question or "").strip()
	if not question:
		frappe.throw(_("Please write a question."))
	settings = frappe.get_cached_doc("Iran AI Settings")
	ai_on = bool(settings.enabled and has_api_key())
	if not settings.commands_enabled and not ai_on:
		frappe.throw(_("The AI assistant is disabled in Iran AI Settings."))
	previous = _get_own_request(previous_request) if previous_request else None
	if wrong_request:
		_mark_wrong(_get_own_request(wrong_request))
	if isinstance(files, str):
		files = json.loads(files or "[]")
	attachments = []
	for file_url in (files or [])[:5]:
		file = get_file(file_url)
		attachments.append({"file_url": file.file_url, "file_name": file.file_name})

	values = {
		"doctype": "Iran AI Request",
		"user": frappe.session.user,
		"question": question[:4000],
		"previous_request": previous_request,
		"attachments": json.dumps(attachments, ensure_ascii=False) if attachments else None,
	}
	# Files need the AI model to read them
	if settings.commands_enabled and not attachments and not (force_ai and ai_on):
		result = _run_command(question, previous, ai_on)
		if not result.get("delegate"):
			history = json.loads(previous.messages or "[]") if previous else []
			history += [
				{"role": "user", "content": question},
				{"role": "assistant", "content": result.get("answer") or ""},
			]
			failed = bool(result.get("error"))
			request = frappe.get_doc(
				{
					**values,
					"status": "Failed" if failed else "Done",
					"handled_by": "Not Understood" if result.get("unrecognized") else "Command",
					"intent": result.get("intent"),
					"score": result.get("score"),
					"answer": None if failed else result.get("answer"),
					"error": result.get("error"),
					"actions": json.dumps(result.get("actions") or [], ensure_ascii=False, default=str),
					"messages": json.dumps(history, ensure_ascii=False, default=str),
					"command_state": json.dumps(result["state"], ensure_ascii=False, default=str)
					if result.get("state")
					else None,
					"model": "commands",
				}
			).insert(ignore_permissions=True)
			return request.name
		values.update(intent=result.get("intent"), score=result.get("score"))

	if not ai_on:
		frappe.throw(_("The AI assistant is disabled in Iran AI Settings."))
	request = frappe.get_doc({**values, "status": "Queued", "handled_by": "AI"}).insert(
		ignore_permissions=True
	)
	frappe.enqueue(
		"iran_erp.ai.assistant.run_request",
		queue="long",
		timeout=900,
		request_name=request.name,
		enqueue_after_commit=True,
	)
	return request.name


def _run_command(question: str, previous, ai_on: bool) -> dict:
	from iran_erp.commands.engine import handle

	state = json.loads(previous.command_state or "{}") if previous else {}
	try:
		return handle(question, state, ai_available=ai_on)
	except Exception as e:
		frappe.db.rollback()
		if not isinstance(e, frappe.ValidationError):
			frappe.log_error(title="Iran chat command failed")
		message = frappe.utils.strip_html(str(e)) or _("Something went wrong.")
		frappe.clear_last_message()
		frappe.local.message_log = []
		return {"error": message, "answer": message, "intent": None}


@frappe.whitelist()
def get_result(request_name: str) -> dict:
	request = _get_own_request(request_name)
	return {
		"status": request.status,
		"handled_by": request.handled_by,
		"answer": request.answer,
		"error": request.error,
		"actions": json.loads(request.actions or "[]"),
	}


def _mark_wrong(request):
	"""The user said a command's answer was wrong: note it, and forget the learned sentence or
	recipe behind it."""
	from iran_erp.commands.learning import unlearn

	request.db_set("feedback", "Wrong")
	if request.handled_by == "Command" and (request.intent or "").startswith("recipe:"):
		from iran_erp.commands.recipes import disable

		disable(request.intent[7:])
	elif request.handled_by == "Command" and request.intent:
		unlearn(request.intent, request.question)


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
			models = list_models(settings)
		except Exception:
			models = []
		missing = [m for m in [settings.model, *settings.fallback_models] if models and m not in models]
		if missing:
			if settings.provider == "OpenRouter":
				suggestions = [m for m in models if m.endswith(":free")][:6] + [
					m for m in models if m.startswith("anthropic/")
				][:4]
			else:
				suggestions = [m for m in models if "whisper" not in m and "guard" not in m][:10]
			return _("Model {0} was not found on {1}. Some available models: {2}").format(
				", ".join(missing), settings.provider, ", ".join(suggestions)
			)
		response = chat_completion(settings, [{"role": "user", "content": "Reply with the single word: OK"}])
		reply = (response["choices"][0]["message"].get("content") or "").strip()
		# With fallbacks, OpenRouter reports which model actually answered
		return _("Connection works. {0} model {1} replied: {2}").format(
			settings.provider, response.get("model") or settings.model, reply[:100]
		)
	except AIError as e:
		return str(e)


# About 4 minutes of 16 kHz mono 16-bit WAV
MAX_AUDIO_BASE64 = 11 * 1024 * 1024
WHISPER_PROMPT_CHARS = 400


@frappe.whitelist(methods=["POST"])
def transcribe(audio: str) -> str:
	"""Turn a recorded WAV (base64) into Persian text with an audio-capable model."""
	if not audio or len(audio) > MAX_AUDIO_BASE64:
		frappe.throw(_("The recording is empty or too long."))
	try:
		settings = get_settings()
	except AIError as e:
		frappe.throw(str(e))
	if settings.api_format != "OpenAI Chat":
		frappe.throw(_("Voice transcription needs a provider in the OpenAI Chat format with an audio model."))
	if "whisper" in settings.transcription_model.lower():
		# Whisper takes a short prompt (about 224 tokens) that only steers spelling
		hint = "، ".join(_vocabulary(30))[:WHISPER_PROMPT_CHARS]
		try:
			return transcribe_audio(settings, base64.b64decode(audio), hint)
		except AIError as e:
			frappe.throw(str(e))
	settings = frappe._dict(settings, model=settings.transcription_model, fallback_models=[])
	prompt = (
		"Transcribe this Persian speech exactly as spoken, in Persian script. It is an instruction to an "
		"accounting system. Write numbers as digits and keep product codes as said. Output only the text, "
		"with no explanation."
	)
	vocabulary = _vocabulary()
	if vocabulary:
		prompt += " Names that may appear: " + "، ".join(vocabulary)
	try:
		response = chat_completion(
			settings,
			[
				{
					"role": "user",
					"content": [
						{"type": "text", "text": prompt},
						{"type": "input_audio", "input_audio": {"data": audio, "format": "wav"}},
					],
				}
			],
		)
	except AIError as e:
		frappe.throw(str(e))
	return (response["choices"][0]["message"].get("content") or "").strip()


def _vocabulary(limit: int = 60) -> list[str]:
	"""Recent item and customer names, so the model spells them the way they are stored."""
	names = []
	for doctype, field in (("Item", "item_name"), ("Customer", "customer_name")):
		if frappe.has_permission(doctype, "read"):
			names += frappe.get_list(doctype, pluck=field, order_by="modified desc", limit=limit // 2)
	return [n for n in dict.fromkeys(names) if n]
