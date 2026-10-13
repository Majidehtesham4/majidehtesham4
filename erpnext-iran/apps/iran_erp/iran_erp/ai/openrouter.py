"""Client for the AI providers: OpenRouter, AgentRouter or any OpenAI-compatible service.

Requests are always built in OpenAI's chat completions shape. Providers that only speak Anthropic's
Messages API ("claude_native", as AgentRouter's Claude models do) are reached through the adapter in
iran_erp.ai.anthropic, which converts the request and the response.
"""

import time

import frappe
import requests
from frappe import _

TIMEOUT_SECONDS = 180
# Busy or rate-limited providers (common with free models) are retried after these pauses
RETRY_WAITS = (4, 12)
RETRY_STATUSES = {429, 502, 503, 529}
# OpenRouter accepts at most this many models in a fallback list
MAX_MODELS = 3

OPENAI_FORMAT = "OpenAI Chat"
ANTHROPIC_FORMAT = "Anthropic Messages"

# provider: (key field, model field, default base URL for the OpenAI format, for the Anthropic format)
PROVIDERS = {
	"OpenRouter": ("api_key", "model", "https://openrouter.ai/api/v1", None),
	"AgentRouter": (
		"agentrouter_api_key",
		"agentrouter_model",
		"https://agentrouter.org/v1",
		"https://agentrouter.org",
	),
	"Custom": ("custom_api_key", "custom_model", None, None),
}


class AIError(Exception):
	pass


def provider_of(doc) -> str:
	return doc.get("provider") if doc.get("provider") in PROVIDERS else "OpenRouter"


def has_api_key() -> bool:
	"""Whether the selected provider has a key, without decrypting it."""
	doc = frappe.get_cached_doc("Iran AI Settings")
	key_field = PROVIDERS[provider_of(doc)][0]
	return bool(doc.get(key_field))


def get_settings():
	settings = frappe.get_cached_doc("Iran AI Settings")
	if not settings.enabled:
		raise AIError(_("The AI assistant is disabled in Iran AI Settings."))
	provider = provider_of(settings)
	key_field, model_field, openai_url, anthropic_url = PROVIDERS[provider]
	api_key = settings.get_password(key_field, raise_exception=False)
	if not api_key:
		raise AIError(_("Set the {0} API key in Iran AI Settings first.").format(provider))
	api_format = (
		ANTHROPIC_FORMAT
		if provider != "OpenRouter" and settings.get("api_format") == ANTHROPIC_FORMAT
		else OPENAI_FORMAT
	)
	default_url = anthropic_url if api_format == ANTHROPIC_FORMAT else openai_url
	base_url = (settings.base_url if provider == "Custom" else None) or default_url
	if not base_url:
		raise AIError(_("Set the API base URL of the custom provider in Iran AI Settings."))
	model = settings.get(model_field) or ("anthropic/claude-opus-5.5" if provider == "OpenRouter" else "")
	if not model:
		raise AIError(_("Set the model name for {0} in Iran AI Settings.").format(provider))
	return frappe._dict(
		provider=provider,
		api_format=api_format,
		api_key=api_key,
		model=model,
		# OpenRouter's "models" list is its own feature; other providers would reject it
		fallback_models=[m.strip() for m in (settings.fallback_models or "").splitlines() if m.strip()]
		if provider == "OpenRouter"
		else [],
		base_url=base_url.rstrip("/"),
		max_steps=settings.max_steps or 20,
		instructions=settings.assistant_instructions or "",
		transcription_model=settings.transcription_model or model,
	)


def chat_completion(settings, messages: list, tools: list | None = None) -> dict:
	"""Send one chat request and return the response in OpenAI's chat completions shape."""
	if settings.api_format == ANTHROPIC_FORMAT:
		from iran_erp.ai.anthropic import from_anthropic_response, to_anthropic_request

		url = f"{settings.base_url}/v1/messages"
		payload = to_anthropic_request(settings.model, messages, tools)
		headers = {
			"x-api-key": settings.api_key,
			# Some relays read the key from here instead
			"Authorization": f"Bearer {settings.api_key}",
			"anthropic-version": "2023-06-01",
			"Content-Type": "application/json",
		}
	else:
		url = f"{settings.base_url}/chat/completions"
		payload = {"model": settings.model, "messages": messages}
		fallbacks = [m for m in settings.get("fallback_models") or [] if m != settings.model]
		if fallbacks:
			# OpenRouter tries these in order when the first one fails or is rate limited
			payload["models"] = [settings.model, *fallbacks][:MAX_MODELS]
		if tools:
			payload["tools"] = tools
			payload["tool_choice"] = "auto"
		headers = {
			"Authorization": f"Bearer {settings.api_key}",
			"Content-Type": "application/json",
			# Optional OpenRouter headers that label the traffic in the OpenRouter dashboard
			"HTTP-Referer": frappe.utils.get_url(),
			"X-Title": "Iran ERP",
		}

	for wait in (*RETRY_WAITS, None):
		try:
			response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT_SECONDS)
		except requests.RequestException as e:
			raise AIError(_("Could not reach the AI service: {0}").format(e)) from e
		if response.status_code not in RETRY_STATUSES or wait is None:
			break
		time.sleep(wait)

	try:
		data = response.json()
	except ValueError:
		data = {}
	if not isinstance(data, dict):
		data = {}

	if response.status_code != 200 or "error" in data:
		error = data.get("error") or {}
		message = error.get("message") if isinstance(error, dict) else str(error)
		if response.status_code == 401 and "unauthorized client" in (message or response.text).lower():
			raise AIError(
				_(
					"{0} rejected this system as a client (401): its keys only work inside the coding tools it supports, such as Claude Code or Codex, not from other software. Use OpenRouter or another provider with a regular API key."
				).format(settings.provider)
			)
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
	if settings.api_format == ANTHROPIC_FORMAT:
		data = from_anthropic_response(data)
	if not data.get("choices"):
		raise AIError(_("The AI service returned an empty response."))
	return data


def list_models(settings) -> list[str]:
	"""Model IDs offered by the provider, or [] when it does not publish a list we can read."""
	if settings.provider != "OpenRouter":
		return []
	response = requests.get(f"{settings.base_url}/models", timeout=30)
	response.raise_for_status()
	return [m["id"] for m in response.json().get("data", [])]
