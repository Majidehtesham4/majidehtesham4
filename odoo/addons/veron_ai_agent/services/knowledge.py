"""The text of a knowledge source, its passages, and the search among them.

The search is built in (BM25 on words written the Persian way), so it works with no AI service and in Persian.
A link is read only from the public internet: an address on the company's own network or on the server itself
is refused, so a source cannot be used to reach what the server alone can see."""

import io
import ipaddress
import math
import re
import socket
import zipfile
from collections import Counter
from urllib.parse import urlparse

from . import files

MAX_BYTES = 15 * 1024 * 1024
CHUNK = 900
OVERLAP = 150
ARABIC = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "أ": "ا", "إ": "ا", "آ": "ا", "ؤ": "و",
	"۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
	"٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9"})
DIACRITICS = re.compile(r"[ً-ٰٟـ]")
STOP = set("و در به از که این را با است برای آن یک تا هم بر یا اما شود می‌شود ها های the a an of to and in is for on are be".split())


class SourceError(ValueError):
	pass


def normalize(text):
	text = DIACRITICS.sub("", (text or "").translate(ARABIC)).lower()
	return text.replace("‌", " ")


def words(text):
	result = []
	for word in re.findall(r"[\w]+", normalize(text)):
		if word in STOP or len(word) < 2:
			continue
		# a light stemming of the plural and possessive endings of Persian, and the English plural
		for end in ("های", "ها", "ات", "ان", "ی"):
			if len(word) > len(end) + 2 and word.endswith(end):
				word = word[: -len(end)]
				break
		if len(word) > 4 and word.endswith("s") and word.isascii():
			word = word[:-1]
		result.append(word)
	return result


def html_text(html):
	html = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", html or "")
	html = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n", html)
	text = re.sub(r"<[^>]+>", " ", html)
	text = re.sub(r"&nbsp;", " ", text)
	text = re.sub(r"&amp;", "&", text)
	text = re.sub(r"[ \t\r\f\v]+", " ", text)
	return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def docx_text(data):
	with zipfile.ZipFile(io.BytesIO(data)) as archive:
		xml = archive.read("word/document.xml").decode("utf-8", "replace")
	xml = re.sub(r"</w:p>", "\n", xml)
	return html_text(xml)


def file_text(name, data, mimetype=""):
	"""The text of a file: PDF (its text layer), Word, text, HTML, Markdown, CSV"""
	if len(data) > MAX_BYTES:
		raise SourceError("The file is larger than 15 MB.")
	lower = (name or "").lower()
	if data[:4] == b"%PDF" or lower.endswith(".pdf"):
		text = files.pdf_text(data, max_pages=300)
		if not text:
			raise SourceError("The PDF has no text layer (a scan); give its text or a PDF with text.")
		return text
	if lower.endswith(".docx") or data[:2] == b"PK" and b"word/" in data[:2000]:
		return docx_text(data)
	text = data.decode("utf-8-sig", "replace")
	if lower.endswith((".html", ".htm")) or "<html" in text[:500].lower():
		return html_text(text)
	if "\x00" in text[:1000]:
		raise SourceError("This kind of file cannot be read; give a PDF, a Word file or a text file.")
	return text


def check_public(url):
	"""The address of a link, refused unless it is on the public internet"""
	parts = urlparse(url)
	if parts.scheme not in ("http", "https") or not parts.hostname:
		raise SourceError("Only http and https links are read.")
	try:
		addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, parts.port or None)}
	except socket.gaierror as error:
		raise SourceError(f"The address {parts.hostname} is not found.") from error
	for address in addresses:
		ip = ipaddress.ip_address(address.split("%")[0])
		if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
			raise SourceError("Links to the company's own network or to the server are not read.")
	return url


def fetch(url, timeout=20):
	import requests

	for _hop in range(4):
		check_public(url)
		response = requests.get(url, timeout=timeout, allow_redirects=False, stream=True,
			headers={"User-Agent": "ERP-VERON knowledge reader", "Accept": "text/html,text/plain,application/pdf"})
		if response.is_redirect or response.is_permanent_redirect:
			url = requests.compat.urljoin(url, response.headers.get("location", ""))
			continue
		response.raise_for_status()
		data = b""
		for piece in response.iter_content(65536):
			data += piece
			if len(data) > MAX_BYTES:
				raise SourceError("The page is larger than 15 MB.")
		kind = response.headers.get("content-type", "")
		if "pdf" in kind:
			return file_text("page.pdf", data)
		text = data.decode(response.encoding or "utf-8", "replace")
		return html_text(text) if "html" in kind or "<html" in text[:500].lower() else text
	raise SourceError("The link redirects too many times.")


def chunks(text):
	"""Passages of about CHUNK characters, cut at paragraphs and sentences, overlapping a little"""
	text = re.sub(r"[ \t]+", " ", text or "").strip()
	if not text:
		return []
	pieces, current = [], ""
	for paragraph in re.split(r"\n\s*\n|\n", text):
		paragraph = paragraph.strip()
		if not paragraph:
			continue
		while len(paragraph) > CHUNK:
			cut = max(paragraph.rfind(". ", 0, CHUNK), paragraph.rfind("، ", 0, CHUNK), paragraph.rfind(" ", 0, CHUNK))
			cut = cut if cut > CHUNK // 2 else CHUNK
			if current:
				pieces.append(current)
				current = ""
			pieces.append(paragraph[:cut + 1].strip())
			paragraph = paragraph[max(cut + 1 - OVERLAP, 1):].strip()
		if len(current) + len(paragraph) + 1 > CHUNK and current:
			pieces.append(current)
			current = current[-OVERLAP:] + " " + paragraph if OVERLAP else paragraph
		else:
			current = f"{current}\n{paragraph}" if current else paragraph
	if current:
		pieces.append(current)
	return pieces


def rank(query, passages, limit=5):
	"""BM25 over (key, text) passages; the best keys with their scores"""
	terms = words(query)
	if not terms or not passages:
		return []
	docs = [(key, Counter(words(text))) for key, text in passages]
	n = len(docs)
	avg = sum(sum(c.values()) for _k, c in docs) / n or 1
	df = Counter(term for _k, counts in docs for term in set(counts))
	scored = []
	for key, counts in docs:
		length = sum(counts.values()) or 1
		score = 0.0
		for term in set(terms):
			f = counts.get(term, 0)
			if not f:
				continue
			idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
			score += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * length / avg))
		if score > 0:
			scored.append((score, key))
	scored.sort(key=lambda item: -item[0])
	return [(key, score) for score, key in scored[:limit]]
