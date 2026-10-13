"""Client for the AI providers: OpenRouter, AgentRouter, Groq or any OpenAI-compatible service.

Requests are always built in OpenAI's chat completions shape. Providers that only speak Anthropic's
Messages API ("claude_native", as AgentRouter's Claude models do) are reached through the adapter in
iran_erp.ai.anthropic, which converts the request and the response.
"""

import hashlib
import re
import time

import frappe
import requests
from frappe import _

TIMEOUT_SECONDS = 180
# Busy or rate-limited providers (common with free models) are retried after these pauses
RETRY_WAITS = (4, 12)
RETRY_STATUSES = {429, 502, 503, 529}
# Longest pause taken when the provider names its own (Groq does, in a Retry-After header)
MAX_RETRY_WAIT = 30
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
	"Groq": ("groq_api_key", "groq_model", "https://api.groq.com/openai/v1", None),
	"Custom": ("custom_api_key", "custom_model", None, None),
}
# Providers that offer more than one request format
MULTI_FORMAT = ("AgentRouter", "Custom")
DEFAULT_MODELS = {"OpenRouter": "anthropic/claude-opus-5.5", "Groq": "openai/gpt-oss-120b"}
DEFAULT_TRANSCRIPTION_MODELS = {"Groq": "whisper-large-v3"}

# A key field may hold several keys; when one is refused or rate limited the next one is used
MAX_KEYS = 30
KEY_SWITCH_STATUSES = {401, 402, 403, 429}
# How long a key is left alone after each kind of failure, in seconds
KEY_COOL_DOWN = {401: 6 * 3600, 403: 6 * 3600, 402: 3600, 429: 60}


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
	api_keys = split_keys(settings.get_password(key_field, raise_exception=False))
	if not api_keys:
		raise AIError(_("Set the {0} API key in Iran AI Settings first.").format(provider))
	api_format = (
		ANTHROPIC_FORMAT
		if provider in MULTI_FORMAT and settings.get("api_format") == ANTHROPIC_FORMAT
		else OPENAI_FORMAT
	)
	default_url = anthropic_url if api_format == ANTHROPIC_FORMAT else openai_url
	base_url = (settings.base_url if provider == "Custom" else None) or default_url
	if not base_url:
		raise AIError(_("Set the API base URL of the custom provider in Iran AI Settings."))
	model = settings.get(model_field) or DEFAULT_MODELS.get(provider, "")
	if not model:
		raise AIError(_("Set the model name for {0} in Iran AI Settings.").format(provider))
	return frappe._dict(
		provider=provider,
		api_format=api_format,
		api_key=api_keys[0],
		api_keys=api_keys,
		model=model,
		# OpenRouter's "models" list is its own feature; other providers would reject it
		fallback_models=[m.strip() for m in (settings.fallback_models or "").splitlines() if m.strip()]
		if provider == "OpenRouter"
		else [],
		base_url=base_url.rstrip("/"),
		max_steps=settings.max_steps or 20,
		instructions=settings.assistant_instructions or "",
		transcription_model=settings.transcription_model
		or DEFAULT_TRANSCRIPTION_MODELS.get(provider)
		or model,
	)


def chat_completion(settings, messages: list, tools: list | None = None) -> dict:
	"""Send one chat request and return the response in OpenAI's chat completions shape."""
	if settings.api_format == ANTHROPIC_FORMAT:
		from iran_erp.ai.anthropic import from_anthropic_response, to_anthropic_request

		url = f"{settings.base_url}/v1/messages"
		payload = to_anthropic_request(settings.model, messages, tools)

		def headers(key):
			return {
				"x-api-key": key,
				# Some relays read the key from here instead
				"Authorization": f"Bearer {key}",
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

		def headers(key):
			return {
				"Authorization": f"Bearer {key}",
				"Content-Type": "application/json",
				# Optional OpenRouter headers that label the traffic in the OpenRouter dashboard
				"HTTP-Referer": frappe.utils.get_url(),
				"X-Title": "Iran ERP",
			}

	response = post_with_retries(settings, url, lambda key: {"headers": headers(key), "json": payload})
	data = check_response(settings, response)
	if settings.api_format == ANTHROPIC_FORMAT:
		data = from_anthropic_response(data)
	if not data.get("choices"):
		raise AIError(_("The AI service returned an empty response."))
	return data


def split_keys(value: str | None) -> list[str]:
	"""The keys in a key field: one, or several separated by commas, spaces or new lines."""
	return list(dict.fromkeys(k for k in re.split(r"[\s,;]+", value or "") if k))[:MAX_KEYS]


def _key_id(key: str) -> str:
	# Only a fingerprint of the key goes into the cache
	return hashlib.sha256(key.encode()).hexdigest()[:16]


def usable_keys(settings) -> list[str]:
	"""The keys in the order to try them: the last one that worked first, resting keys left out."""
	keys = settings.get("api_keys") or [settings.api_key]
	current = frappe.cache.get_value(f"iran_ai_key_current:{settings.provider}")
	ids = [_key_id(k) for k in keys]
	if current in ids:
		start = ids.index(current)
		keys = keys[start:] + keys[:start]
	ready = [k for k in keys if not frappe.cache.get_value(f"iran_ai_key_rest:{_key_id(k)}")]
	# When every key is resting, try them anyway rather than fail without asking
	return ready or keys


def _rest_key(key: str, response):
	seconds = KEY_COOL_DOWN.get(response.status_code, 60)
	try:
		seconds = max(seconds, min(int(float(response.headers.get("retry-after"))), 3600))
	except TypeError, ValueError:
		pass
	frappe.cache.set_value(f"iran_ai_key_rest:{_key_id(key)}", 1, expires_in_sec=seconds)


def post_with_retries(settings, url: str, request_for_key):
	"""POST with each usable key in turn, then retry busy responses after a pause.

	`request_for_key(key)` returns the keyword arguments of `requests.post` for that key.
	"""
	keys = usable_keys(settings)
	for wait in (*RETRY_WAITS, None):
		while True:
			try:
				response = requests.post(url, timeout=TIMEOUT_SECONDS, **request_for_key(keys[0]))
			except requests.RequestException as e:
				raise AIError(_("Could not reach the AI service: {0}").format(e)) from e
			if response.status_code in KEY_SWITCH_STATUSES and len(keys) > 1:
				_rest_key(keys[0], response)
				keys = keys[1:]
				continue
			break
		if response.ok:
			frappe.cache.set_value(f"iran_ai_key_current:{settings.provider}", _key_id(keys[0]))
		if response.status_code not in RETRY_STATUSES or wait is None:
			return response
		try:
			wait = min(max(float(response.headers.get("retry-after")), wait), MAX_RETRY_WAIT)
		except TypeError, ValueError:
			pass
		time.sleep(wait)


def check_response(settings, response) -> dict:
	"""The response's JSON, or an AIError that explains what went wrong."""
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
		if response.status_code == 402:
			raise AIError(
				_(
					"Your {0} account has no credit left (402): {1}. Top up the account on the provider's website and try again."
				).format(settings.provider, message or "")
			)
		if response.status_code == 429:
			raise AIError(
				_(
					"The AI model is busy or its free quota is used up (429): {0}. Wait a few minutes, add fallback models in AI Assistant Settings, or use a paid model."
				).format(message or "")
			)
		if response.status_code == 413:
			raise AIError(
				_(
					"The request is larger than the model or your plan allows (413): {0}. Choose a model with a larger limit, or upgrade the plan with the provider."
				).format(message or "")
			)
		raise AIError(
			_("The AI service returned an error ({0}): {1}").format(
				response.status_code, message or response.text[:300]
			)
		)
	return data


def transcribe_audio(settings, wav: bytes, prompt: str = "") -> str:
	"""Speech to text through the OpenAI-style /audio/transcriptions endpoint (Whisper models)."""
	response = post_with_retries(
		settings,
		f"{settings.base_url}/audio/transcriptions",
		lambda key: {
			"headers": {"Authorization": f"Bearer {key}"},
			"files": {"file": ("speech.wav", wav, "audio/wav")},
			"data": {
				"model": settings.transcription_model,
				"language": "fa",
				"prompt": prompt,
				"response_format": "json",
			},
		},
	)
	return (check_response(settings, response).get("text") or "").strip()


def list_models(settings) -> list[str]:
	"""Model IDs offered by the provider, or [] when it does not publish a list we can read."""
	if settings.provider not in ("OpenRouter", "Groq"):
		return []
	response = requests.get(
		f"{settings.base_url}/models", headers={"Authorization": f"Bearer {settings.api_key}"}, timeout=30
	)
	response.raise_for_status()
	return [m["id"] for m in response.json().get("data", [])]
