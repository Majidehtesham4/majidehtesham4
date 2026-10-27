"""The services an agent may use, behind one interface each, so a cloud service or a local one can be put
in its place from the settings: a language model, reading of photos and PDFs (vision/OCR), speech to text,
text to speech, image generation, web search and an antivirus. A module adds its own adapter with
`register`; nothing here needs a key to be installed, and a missing key gives a clear error at use."""

import base64
import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

import requests

from . import redact

_logger = logging.getLogger(__name__)

KINDS = [
	("llm", "Language Model"),
	("vision", "Reading Photos and PDFs"),
	("stt", "Speech to Text"),
	("tts", "Text to Speech"),
	("image", "Image Generation"),
	("search", "Web Search"),
	("antivirus", "Antivirus"),
]
ADAPTERS = {}


def register(code, kinds):
	"""Class decorator: the adapter `code` serves the provider kinds `kinds`"""

	def wrap(cls):
		cls.code = code
		cls.kinds = tuple(kinds)
		ADAPTERS[code] = cls
		return cls

	return wrap


class ProviderError(Exception):
	"""A failure of a provider, worded for the person; retryable when trying again later may help"""

	def __init__(self, message, retryable=False, kind="error"):
		super().__init__(redact.text(message, 500))
		self.retryable = retryable
		self.kind = kind


@dataclass
class ToolCall:
	id: str
	name: str
	input: dict


@dataclass
class LLMResult:
	text: str = ""
	tool_calls: list = field(default_factory=list)
	stop_reason: str = ""
	usage: dict = field(default_factory=dict)
	# The provider's own message, kept to continue the conversation
	assistant_message: object = None
	refused: bool = False


class Adapter:
	"""Base of every adapter: `config` is a dict of the provider's settings; the key is read through
	`secret()` and never logged"""

	code = ""
	kinds = ()

	def __init__(self, config):
		self.config = config

	def secret(self):
		key = self.config.get("api_key")
		if not key:
			raise ProviderError("The provider has no key. Enter it in AI Agents, Settings, Providers.", kind="config")
		return key

	def timeout(self):
		return float(self.config.get("timeout") or 60)

	def check(self):
		"""A light call that shows the provider works; returns a short description"""
		raise ProviderError("This provider has no check.", kind="config")

	# Language model
	def chat(self, system, messages, tools, max_tokens=4096):
		raise ProviderError("This provider is not a language model.", kind="config")

	def user_message(self, text, files=()):
		raise NotImplementedError

	def tool_results_message(self, results):
		raise NotImplementedError

	# Reading photos and PDFs
	def extract(self, files, schema, instructions):
		raise ProviderError("This provider does not read files.", kind="config")

	# Speech
	def transcribe(self, data, mimetype, language):
		raise ProviderError("This provider does not turn speech into text.", kind="config")

	def speak(self, text, language):
		raise ProviderError("This provider does not read text aloud.", kind="config")

	# Images and search
	def generate_image(self, prompt, size):
		raise ProviderError("This provider does not make images.", kind="config")

	def search(self, query, allowed_domains, max_results):
		raise ProviderError("This provider does not search the web.", kind="config")

	def scan(self, data):
		raise ProviderError("This provider does not scan files.", kind="config")


def _http_error(response, what):
	if response.status_code == 429:
		raise ProviderError(f"{what}: too many requests; it is tried again later.", retryable=True, kind="rate_limit")
	if response.status_code in (401, 403):
		raise ProviderError(f"{what}: the key was refused ({response.status_code}).", kind="config")
	if response.status_code >= 500:
		raise ProviderError(f"{what}: the service is unavailable ({response.status_code}).", retryable=True, kind="unavailable")
	raise ProviderError(f"{what}: {response.status_code} {redact.text(response.text, 300)}")


def _post(url, what, timeout, **kwargs):
	try:
		response = requests.post(url, timeout=timeout, **kwargs)
	except requests.Timeout as error:
		raise ProviderError(f"{what}: no answer in {timeout:.0f} seconds.", retryable=True, kind="timeout") from error
	except requests.RequestException as error:
		raise ProviderError(f"{what}: the service cannot be reached.", retryable=True, kind="unavailable") from error
	if response.status_code >= 400:
		_http_error(response, what)
	return response


@register("http_openai", ["stt", "tts", "image"])
class OpenAICompatibleHttp(Adapter):
	"""The common HTTP form of speech-to-text (/audio/transcriptions), text-to-speech (/audio/speech) and
	image generation (/images/generations), served by many cloud services and by local servers such as a
	Whisper server inside the company. The address, the model and the key come from the settings."""

	def _url(self, path):
		base = (self.config.get("base_url") or "").rstrip("/")
		if not base:
			raise ProviderError("Enter the address of the service in the provider.", kind="config")
		return f"{base}/{path}"

	def _headers(self):
		key = self.config.get("api_key")
		return {"Authorization": f"Bearer {key}"} if key else {}

	def check(self):
		self._url("")
		return "The address is set; send a voice message or make an image to try it."

	def transcribe(self, data, mimetype, language):
		extension = mimetype.split("/")[-1].replace("mpeg", "mp3")
		response = _post(self._url("audio/transcriptions"), "Speech to text", self.timeout(), headers=self._headers(),
			files={"file": (f"voice.{extension}", data, mimetype)},
			data={"model": self.config.get("model") or "whisper-1", "language": language or "fa", "response_format": "json"})
		try:
			return (response.json().get("text") or "").strip()
		except ValueError as error:
			raise ProviderError("Speech to text: the answer is not JSON.") from error

	def speak(self, text, language):
		response = _post(self._url("audio/speech"), "Text to speech", self.timeout(), headers=self._headers(),
			json={"model": self.config.get("model") or "tts-1", "input": text[:4000], "voice": self.config.get("voice") or "alloy",
				"response_format": "mp3"})
		return response.content, "audio/mpeg"

	def generate_image(self, prompt, size):
		response = _post(self._url("images/generations"), "Image generation", self.timeout(), headers=self._headers(),
			json={"model": self.config.get("model") or "", "prompt": prompt[:3000], "size": size, "n": 1,
				"response_format": "b64_json"})
		try:
			item = response.json()["data"][0]
		except (ValueError, KeyError, IndexError) as error:
			raise ProviderError("Image generation: the answer has no image.") from error
		if item.get("b64_json"):
			return base64.b64decode(item["b64_json"])
		raise ProviderError("Image generation: the answer has no image data.")


@register("searxng", ["search"])
class SearxngSearch(Adapter):
	"""A SearXNG search server of the company itself (its JSON format must be enabled)"""

	def search(self, query, allowed_domains, max_results):
		base = (self.config.get("base_url") or "").rstrip("/")
		if not base:
			raise ProviderError("Enter the address of the SearXNG server.", kind="config")
		terms = query + "".join(f" site:{d}" for d in allowed_domains[:1]) if allowed_domains else query
		try:
			response = requests.get(f"{base}/search", params={"q": terms, "format": "json"}, timeout=self.timeout())
		except requests.RequestException as error:
			raise ProviderError("Web search: the server cannot be reached.", retryable=True, kind="unavailable") from error
		if response.status_code >= 400:
			_http_error(response, "Web search")
		results = []
		for item in response.json().get("results", []):
			url = item.get("url") or ""
			if allowed_domains and not any(url.split("/")[2:3] and url.split("/")[2].endswith(d) for d in allowed_domains):
				continue
			results.append({"title": item.get("title"), "url": url, "snippet": (item.get("content") or "")[:500]})
			if len(results) >= max_results:
				break
		return {"text": "", "results": results}

	def check(self):
		self.search("test", [], 1)
		return "The search server answers."


@register("tesseract", ["vision"])
class TesseractOcr(Adapter):
	"""Tesseract on the server itself, for the text of photos; it reads text only and fills no fields"""

	def check(self):
		if not shutil.which("tesseract"):
			raise ProviderError("Tesseract is not installed on the server (apt install tesseract-ocr tesseract-ocr-fas).",
				kind="config")
		return "Tesseract is installed."

	def extract(self, files, schema, instructions):
		self.check()
		texts = []
		for mimetype, data in files:
			if not mimetype.startswith("image/"):
				continue
			with tempfile.NamedTemporaryFile(suffix=".img") as handle:
				handle.write(data)
				handle.flush()
				result = subprocess.run(["tesseract", handle.name, "stdout", "-l", self.config.get("language_codes") or "fas+eng"],
					capture_output=True, timeout=self.timeout(), check=False)
				texts.append(result.stdout.decode(errors="replace"))
		return {"text": "\n".join(texts).strip(), "fields": {}}


@register("clamd", ["antivirus"])
class ClamdScanner(Adapter):
	"""A ClamAV daemon; the address is host:port, e.g. clamav:3310"""

	def scan(self, data):
		from .files import clamd_scan

		host, _sep, port = (self.config.get("base_url") or "").replace("tcp://", "").partition(":")
		if not host:
			raise ProviderError("Enter the address of ClamAV as host:port.", kind="config")
		try:
			return clamd_scan(host, port or 3310, data, timeout=self.timeout())
		except OSError as error:
			raise ProviderError("The antivirus cannot be reached.", retryable=True, kind="unavailable") from error

	def check(self):
		clean, detail = self.scan(b"veron")
		return f"ClamAV answers: {detail}"


def as_json(value):
	return json.dumps(value, ensure_ascii=False, default=str)
