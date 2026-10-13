"""Minimal client for OpenRouter's OpenAI-compatible chat completions API."""

import time

import frappe
import requests
from frappe import _

TIMEOUT_SECONDS = 180
# Busy or rate-limited providers (common with free models) are retried after these pauses
RETRY_WAITS = (4, 12)
RETRY_STATUSES = {429, 502, 503}
# OpenRouter accepts at most this many models in a fallback list
MAX_MODELS = 3


class AIError(Exception):
	pass


def get_settings():
	settings = frappe.get_cached_doc("Iran AI Settings")
	if not settings.enabled:
		raise AIError(_("The AI assistant is disabled in Iran AI Settings."))
	api_key = settings.get_password("api_key", raise_exception=False)
	if not api_key:
		raise AIError(_("Set the OpenRouter API key in Iran AI Settings first."))
	return frappe._dict(
		api_key=api_key,
		model=settings.model or "anthropic/claude-opus-5.5",
		fallback_models=[m.strip() for m in (settings.fallback_models or "").splitlines() if m.strip()],
		base_url=(settings.base_url or "https://openrouter.ai/api/v1").rstrip("/"),
		max_steps=settings.max_steps or 20,
		instructions=settings.assistant_instructions or "",
		transcription_model=settings.transcription_model or settings.model or "anthropic/claude-opus-5.5",
	)


def chat_completion(settings, messages: list, tools: list | None = None) -> dict:
	"""Send one chat completion request and return the response JSON."""
	payload = {"model": settings.model, "messages": messages}
	fallbacks = [m for m in settings.get("fallback_models") or [] if m != settings.model]
	if fallbacks:
		# OpenRouter tries these in order when the first one fails or is rate limited
		payload["models"] = [settings.model, *fallbacks][:MAX_MODELS]
	if tools:
		payload["tools"] = tools
		payload["tool_choice"] = "auto"

	for wait in (*RETRY_WAITS, None):
		try:
			response = requests.post(
				f"{settings.base_url}/chat/completions",
				headers={
					"Authorization": f"Bearer {settings.api_key}",
					"Content-Type": "application/json",
					# Optional OpenRouter headers that label the traffic in the OpenRouter dashboard
					"HTTP-Referer": frappe.utils.get_url(),
					"X-Title": "Iran ERP",
				},
				json=payload,
				timeout=TIMEOUT_SECONDS,
			)
		except requests.RequestException as e:
			raise AIError(_("Could not reach the AI service: {0}").format(e)) from e
		if response.status_code not in RETRY_STATUSES or wait is None:
			break
		time.sleep(wait)

	try:
		data = response.json()
	except ValueError:
		data = {}

	if response.status_code != 200 or "error" in data:
		error = data.get("error") or {}
		message = error.get("message") if isinstance(error, dict) else str(error)
		if response.status_code == 429:
			raise AIError(
				_(
					"The AI model is busy or its free quota is used up (429): {0}. Wait a few minutes, add fallback models in AI Assistant Settings, or use a paid model."
				).format(message or "")
			)
		raise AIError(
			_("The AI service returned an error ({0}): {1}").format(
				response.status_code, message or response.text[:300]
			)
		)
	if not data.get("choices"):
		raise AIError(_("The AI service returned an empty response."))
	return data


def list_models(base_url: str) -> list[str]:
	response = requests.get(f"{base_url.rstrip('/')}/models", timeout=30)
	response.raise_for_status()
	return [m["id"] for m in response.json().get("data", [])]
