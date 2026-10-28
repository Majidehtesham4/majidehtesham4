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

from odoo.tools.translate import LazyGettext, LazyTranslate

from . import redact

_lt = LazyTranslate(__name__)

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
	"""A failure of a provider, worded for the person; retryable when trying again later may help. The
	message is a lazy translation when it can be: `text(env)` gives it in the person's language."""

	def __init__(self, message, retryable=False, kind="error"):
		self.lazy = message if isinstance(message, LazyGettext) else None
		super().__init__(redact.text(message._translate("en_US") if self.lazy is not None else message, 500))
		self.retryable = retryable
		self.kind = kind

	def text(self, env):
		if self.lazy is not None:
			return redact.text(env._(self.lazy), 500)
		return self.args[0]


def message(error, env, limit=500):
	"""The message of an error for the person, in their language when it is a provider's error"""
	if isinstance(error, ProviderError):
		return error.text(env)[:limit]
	return redact.text(error, limit)


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
	# Works on the server itself, without any outside service: the built-in assistant may use it
	local = False

	def __init__(self, config):
		self.config = config

	def secret(self):
		key = self.config.get("api_key")
		if not key:
			raise ProviderError(_lt("The provider has no key. Enter it in AI Agents, Settings, Providers."), kind="config")
		return key

	def keys(self):
		"""The keys of the provider, in the order to try them for this call: several keys share the load and
		stand in for one another"""
		return [k for k in self.config.get("api_keys") or [] if k] or ([self.config["api_key"]] if self.config.get("api_key") else [])

	def with_keys(self, call, required=True):
		"""call(key) with each key in turn, while a key is at its limit or refused; a local service may need none"""
		keys = self.keys()
		if not keys:
			if required:
				self.secret()
			return call("")
		errors = []
		for key in keys:
			try:
				return call(key)
			except ProviderError as error:
				if error.kind not in ("rate_limit", "key"):
					raise
				errors.append(error)
		if all(error.kind == "rate_limit" for error in errors) and len(keys) > 1:
			raise ProviderError(_lt("All %s keys of the provider are at their limit; it is tried again later.", len(keys)),
				retryable=True, kind="rate_limit")
		raise errors[-1]

	def timeout(self):
		return float(self.config.get("timeout") or 60)

	def check(self):
		"""A light call that shows the provider works; returns a short description"""
		raise ProviderError(_lt("This provider has no check."), kind="config")

	# Language model
	def chat(self, system, messages, tools, max_tokens=4096):
		raise ProviderError(_lt("This provider is not a language model."), kind="config")

	def sees_images(self):
		"""Whether the model reads photos itself; a model that does not is given their text from the built-in OCR"""
		return True

	def history_message(self, role, text):
		"""An earlier message of the conversation, as plain text"""
		return {"role": role, "content": text}

	def user_message(self, text, files=()):
		raise NotImplementedError

	def tool_results_message(self, results):
		raise NotImplementedError

	# Reading photos and PDFs
	def extract(self, files, schema, instructions):
		raise ProviderError(_lt("This provider does not read files."), kind="config")

	# Speech
	def transcribe(self, data, mimetype, language):
		raise ProviderError(_lt("This provider does not turn speech into text."), kind="config")

	def speak(self, text, language):
		raise ProviderError(_lt("This provider does not read text aloud."), kind="config")

	# Images and search
	def generate_image(self, prompt, size):
		raise ProviderError(_lt("This provider does not make images."), kind="config")

	def search(self, query, allowed_domains, max_results):
		raise ProviderError(_lt("This provider does not search the web."), kind="config")

	def scan(self, data):
		raise ProviderError(_lt("This provider does not scan files."), kind="config")


def _http_error(response, what):
	if response.status_code == 429:
		raise ProviderError(_lt("%(what)s: too many requests; it is tried again later.", what=what), retryable=True, kind="rate_limit")
	if response.status_code in (401, 403):
		host = (getattr(response, "url", "") or "").split("/")[2:3]
		raise ProviderError(_lt("%(what)s: the key was refused (%(code)s) by %(host)s. Check that the key is of this service "
			"and still valid, or connect it with Connect AI, which finds the service from the key.", what=what,
			code=response.status_code, host=host[0] if host else "-"), kind="key")
	if response.status_code >= 500:
		raise ProviderError(_lt("%(what)s: the service is unavailable (%(code)s).", what=what, code=response.status_code), retryable=True,
			kind="unavailable")
	raise ProviderError(_lt("%(what)s: %(code)s %(text)s", what=what, code=response.status_code, text=redact.text(response.text, 300)))


def _post(url, what, timeout, method="post", **kwargs):
	try:
		response = requests.request(method, url, timeout=timeout, **kwargs)
	except requests.Timeout as error:
		raise ProviderError(_lt("%(what)s: no answer in %(seconds)s seconds.", what=what, seconds=round(timeout)), retryable=True,
			kind="timeout") from error
	except requests.RequestException as error:
		raise ProviderError(_lt("%(what)s: the service cannot be reached.", what=what), retryable=True, kind="unavailable") from error
	if response.status_code >= 400:
		_http_error(response, what)
	return response


@register("http_openai", ["stt", "tts", "image"])
class OpenAICompatibleHttp(Adapter):
	"""The common HTTP form of speech-to-text (/audio/transcriptions), text-to-speech (/audio/speech) and
	image generation (/images/generations), served by many cloud services and by local servers such as a
	Whisper server inside the company. The address, the model and the key come from the settings."""

	def _url(self, path):
		from .catalog import base_for

		base = (self.config.get("base_url") or base_for(self.config.get("api_key"))).rstrip("/")
		if not base:
			raise ProviderError(_lt("Enter the address of the service in the provider."), kind="config")
		return f"{base}/{path}"

	@staticmethod
	def _headers(key):
		return {"Authorization": f"Bearer {key}"} if key else {}

	def check(self):
		self._url("")
		return _lt("The address is set; send a voice message or make an image to try it.")

	def transcribe(self, data, mimetype, language):
		extension = mimetype.split("/")[-1].replace("mpeg", "mp3").replace("x-wav", "wav")
		response = self.with_keys(lambda key: _post(self._url("audio/transcriptions"), _lt("Speech to text"), self.timeout(),
			headers=self._headers(key), files={"file": (f"voice.{extension}", data, mimetype)},
			data={"model": self.config.get("model") or "whisper-1", "language": language or "fa", "response_format": "json"}),
			required=False)
		try:
			return (response.json().get("text") or "").strip()
		except ValueError as error:
			raise ProviderError(_lt("Speech to text: the answer is not JSON.")) from error

	def speak(self, text, language):
		response = self.with_keys(lambda key: _post(self._url("audio/speech"), _lt("Text to speech"), self.timeout(),
			headers=self._headers(key), json={"model": self.config.get("model") or "tts-1", "input": text[:4000],
				"voice": self.config.get("voice") or "alloy", "response_format": "mp3"}), required=False)
		return response.content, "audio/mpeg"

	def generate_image(self, prompt, size):
		response = self.with_keys(lambda key: _post(self._url("images/generations"), _lt("Image generation"), self.timeout(),
			headers=self._headers(key), json={"model": self.config.get("model") or "", "prompt": prompt[:3000], "size": size,
				"n": 1, "response_format": "b64_json"}), required=False)
		try:
			item = response.json()["data"][0]
		except (ValueError, KeyError, IndexError) as error:
			raise ProviderError(_lt("Image generation: the answer has no image.")) from error
		if item.get("b64_json"):
			return base64.b64decode(item["b64_json"])
		raise ProviderError(_lt("Image generation: the answer has no image data."))


@register("searxng", ["search"])
class SearxngSearch(Adapter):
	"""A SearXNG search server of the company itself (its JSON format must be enabled)"""

	def search(self, query, allowed_domains, max_results):
		from .catalog import base_for

		base = (self.config.get("base_url") or base_for(self.config.get("api_key"))).rstrip("/")
		if not base:
			raise ProviderError(_lt("Enter the address of the SearXNG server."), kind="config")
		terms = query + "".join(f" site:{d}" for d in allowed_domains[:1]) if allowed_domains else query
		try:
			response = requests.get(f"{base}/search", params={"q": terms, "format": "json"}, timeout=self.timeout())
		except requests.RequestException as error:
			raise ProviderError(_lt("Web search: the server cannot be reached."), retryable=True, kind="unavailable") from error
		if response.status_code >= 400:
			_http_error(response, _lt("Web search"))
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
		return _lt("The search server answers.")


@register("tesseract", ["vision"])
class TesseractOcr(Adapter):
	"""The built-in OCR: Tesseract on the server itself reads the text of photos and scanned PDFs, without any AI;
	the fields are then read from that text by the built-in readers"""

	label = "Veron OCR (Tesseract)"
	local = True

	def check(self):
		from . import ocr

		if not ocr.available():
			raise ProviderError(_lt("Tesseract is not installed on the server (apt install tesseract-ocr tesseract-ocr-fas)."),
				kind="config")
		return _lt("Tesseract is installed.")

	def extract(self, files, schema, instructions):
		from . import ocr

		self.check()
		languages = self.config.get("language_codes") or ocr.LANGUAGES
		texts = [ocr.document_text(data, mimetype, languages) for mimetype, data in files]
		return {"text": "\n".join(text for text in texts if text).strip(), "fields": {}}


@register("vosk", ["stt"])
class VoskSpeech(Adapter):
	"""Speech to text on the server itself, without any AI: ffmpeg turns the voice into 16 kHz sound and Vosk reads
	it with its Persian model (fetched once by «odoo.ps1 voice» into python/voice/fa)"""

	label = "Veron Voice (Vosk)"
	local = True
	MODELS = {}

	def _path(self):
		import os

		return self.config.get("base_url") or os.environ.get("VERON_VOSK_MODEL") or "/mnt/python/voice/fa"

	def _model(self):
		import os

		try:
			import vosk
		except ImportError as error:
			raise ProviderError(_lt("Vosk is not installed on the server; it comes with the program's image (odoo.ps1 "
				"start). Until then, type the message or connect an AI for voices."), kind="config") from error
		path = self._path()
		if not os.path.isdir(os.path.join(path, "am")) and not os.path.isfile(os.path.join(path, "conf", "model.conf")):
			raise ProviderError(_lt("The Persian voice model is not on the server. Fetch it once with: odoo.ps1 voice "
				"(Windows) or ./veron voice (server)."), kind="config")
		if not shutil.which("ffmpeg"):
			raise ProviderError(_lt("ffmpeg is not installed on the server; it comes with the program's image."), kind="config")
		if path not in VoskSpeech.MODELS:
			vosk.SetLogLevel(-1)
			VoskSpeech.MODELS[path] = vosk.Model(path)
		return vosk, VoskSpeech.MODELS[path]

	def check(self):
		self._model()
		return _lt("The voice model is installed.")

	def transcribe(self, data, mimetype, language):
		vosk, model = self._model()
		result = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-ar", "16000", "-ac", "1", "-f", "s16le",
			"pipe:1"], input=data, capture_output=True, timeout=self.timeout(), check=False)
		if result.returncode or not result.stdout:
			raise ProviderError(_lt("The voice message could not be opened."), kind="config")
		recognizer = vosk.KaldiRecognizer(model, 16000)
		words = []
		pcm = result.stdout
		for start in range(0, len(pcm), 32000):
			if recognizer.AcceptWaveform(pcm[start:start + 32000]):
				words.append(json.loads(recognizer.Result()).get("text", ""))
		words.append(json.loads(recognizer.FinalResult()).get("text", ""))
		return " ".join(word for word in words if word).strip()


@register("clamd", ["antivirus"])
class ClamdScanner(Adapter):
	"""A ClamAV daemon; the address is host:port, e.g. clamav:3310"""

	def scan(self, data):
		from .files import clamd_scan

		host, _sep, port = (self.config.get("base_url") or "").replace("tcp://", "").partition(":")
		if not host:
			raise ProviderError(_lt("Enter the address of ClamAV as host:port."), kind="config")
		try:
			return clamd_scan(host, port or 3310, data, timeout=self.timeout())
		except OSError as error:
			raise ProviderError(_lt("The antivirus cannot be reached."), retryable=True, kind="unavailable") from error

	def check(self):
		clean, detail = self.scan(b"veron")
		return _lt("ClamAV answers: %s", detail)


def as_json(value):
	return json.dumps(value, ensure_ascii=False, default=str)
