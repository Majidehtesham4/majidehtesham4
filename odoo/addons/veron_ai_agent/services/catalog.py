"""The AI services a company connects with a key, and how a key shows which service it is from: the address,
the models and the providers each one fills, so a person only pastes keys."""

import re

SERVICES = {
	"groq": {
		"label": "Groq", "prefix": "gsk_", "base": "https://api.groq.com/openai/v1", "adapter": "openai_chat",
		"keys_at": "https://console.groq.com/keys",
		"providers": [
			("veron_ai_agent.provider_groq", "llm", "openai_chat", "llama-3.3-70b-versatile"),
			("veron_ai_agent.provider_groq_vision", "vision", "openai_chat", "meta-llama/llama-4-scout-17b-16e-instruct"),
			("veron_ai_agent.provider_groq_stt", "stt", "http_openai", "whisper-large-v3"),
		],
	},
	"openrouter": {
		"label": "OpenRouter", "prefix": "sk-or-", "base": "https://openrouter.ai/api/v1", "adapter": "openai_chat",
		"keys_at": "https://openrouter.ai/keys",
		"providers": [
			("veron_ai_agent.provider_openrouter", "llm", "openai_chat", "meta-llama/llama-3.3-70b-instruct:free"),
		],
	},
	"anthropic": {
		"label": "Claude (Anthropic)", "prefix": "sk-ant-", "base": "", "adapter": "anthropic",
		"keys_at": "https://console.anthropic.com/settings/keys",
		"providers": [
			("ai_claude_anthropic.provider_claude", "llm", "anthropic", "claude-opus-5-5"),
			("ai_claude_anthropic.provider_claude_vision", "vision", "anthropic", "claude-opus-5-5"),
		],
	},
	"openai": {
		"label": "ChatGPT (OpenAI)", "prefix": "sk-", "base": "https://api.openai.com/v1", "adapter": "openai_chat",
		"keys_at": "https://platform.openai.com/api-keys",
		"providers": [
			("veron_ai_agent.provider_chatgpt", "llm", "openai_chat", "gpt-4.1-mini"),
		],
	},
}
# The longer prefixes first: «sk-or-» and «sk-ant-» are not ChatGPT keys
ORDER = ("anthropic", "openrouter", "groq", "openai")
_KEY_START = re.compile(r"(?=gsk_|sk-(?!or-|ant-)|sk-or-|sk-ant-)")


def detect(key):
	"""The service a key is from, by how it begins; None when it is not known"""
	for code in ORDER:
		if (key or "").startswith(SERVICES[code]["prefix"]):
			return code
	return None


def base_for(key):
	"""The address of the service of a key, for a provider whose address was left empty"""
	code = detect(key)
	return SERVICES[code]["base"] if code else ""


def split_keys(text):
	"""Keys pasted one a line, with commas or spaces, or run together (a pasted list loses its line breaks)"""
	keys = []
	for part in re.split(r"[\s,;،]+", text or ""):
		for key in _KEY_START.split(part):
			key = key.strip().strip("\"'")
			if len(key) >= 8 and key not in keys:
				keys.append(key)
	return keys


def masked(key):
	return f"{key[:4]}…{key[-4:]}" if len(key) > 10 else "…"
