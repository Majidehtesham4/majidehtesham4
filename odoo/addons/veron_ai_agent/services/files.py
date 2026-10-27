"""Files given to an agent: the type read from the content (not from the name), the checks that refuse
active or disguised content, the hashes that find the same receipt twice, and the text of a PDF."""

import hashlib
import io
import re
import socket
import struct

KINDS = {
	"image/jpeg": "image",
	"image/png": "image",
	"image/webp": "image",
	"image/gif": "image",
	"application/pdf": "pdf",
	"audio/webm": "audio",
	"audio/ogg": "audio",
	"audio/mpeg": "audio",
	"audio/mp4": "audio",
	"audio/wav": "audio",
}


class FileRefused(ValueError):
	pass


def sniff(data: bytes):
	"""The media type of the content, from its first bytes; None when it is none of ours"""
	head = data[:64]
	if head.startswith(b"\xff\xd8\xff"):
		return "image/jpeg"
	if head.startswith(b"\x89PNG\r\n\x1a\n"):
		return "image/png"
	if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
		return "image/webp"
	if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
		return "audio/wav"
	if head[:6] in (b"GIF87a", b"GIF89a"):
		return "image/gif"
	if head.lstrip()[:5] == b"%PDF-":
		return "application/pdf"
	if head.startswith(b"\x1a\x45\xdf\xa3"):
		return "audio/webm"
	if head.startswith(b"OggS"):
		return "audio/ogg"
	if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
		return "audio/mpeg"
	if head[4:8] == b"ftyp":
		return "audio/mp4"
	return None


# Content a receipt or an invoice never needs, and that runs code or hides files in a PDF
PDF_ACTIVE = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile|RichMedia|XFA|OpenAction\s*<<[^>]*/JS)\b")


def check(data: bytes, allowed_kinds, max_bytes):
	"""(mimetype, kind) of an acceptable file, or FileRefused with the reason"""
	if not data:
		raise FileRefused("The file is empty.")
	if len(data) > max_bytes:
		raise FileRefused(f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
	mimetype = sniff(data)
	if not mimetype:
		raise FileRefused("This type of file is not accepted; send a photo (JPEG, PNG, WebP), a PDF or a voice message.")
	kind = KINDS[mimetype]
	if kind not in allowed_kinds:
		raise FileRefused(f"A file of type {kind} is not accepted here.")
	if kind == "pdf" and PDF_ACTIVE.search(data):
		raise FileRefused("The PDF holds active content (scripts or embedded files) and is refused.")
	if kind == "image":
		try:
			from PIL import Image

			with Image.open(io.BytesIO(data)) as image:
				image.verify()
		except Exception as error:
			raise FileRefused("The image cannot be read.") from error
	return mimetype, kind


def sha256(data: bytes):
	return hashlib.sha256(data).hexdigest()


def image_dhash(data: bytes):
	"""A 64-bit difference hash: two photos of the same paper have hashes a few bits apart"""
	try:
		from PIL import Image, ImageOps

		with Image.open(io.BytesIO(data)) as image:
			image = ImageOps.exif_transpose(image).convert("L").resize((9, 8))
			pixels = list(image.getdata())
	except Exception:
		return False
	bits = 0
	for row in range(8):
		for col in range(8):
			bits = (bits << 1) | (pixels[row * 9 + col] > pixels[row * 9 + col + 1])
	return f"{bits:016x}"


def hamming(a, b):
	if not a or not b:
		return 64
	return bin(int(a, 16) ^ int(b, 16)).count("1")


def pdf_text(data: bytes, max_pages=30):
	"""The text layer of a PDF; empty for a scanned one, which needs OCR"""
	try:
		from PyPDF2 import PdfReader
	except ImportError:
		try:
			from pypdf import PdfReader
		except ImportError:
			return ""
	try:
		reader = PdfReader(io.BytesIO(data))
		return "\n".join((page.extract_text() or "") for page in reader.pages[:max_pages]).strip()
	except Exception:
		return ""


def clamd_scan(host, port, data: bytes, timeout=20):
	"""(clean, detail) from a ClamAV daemon, by its INSTREAM command"""
	with socket.create_connection((host, int(port)), timeout=timeout) as sock:
		sock.sendall(b"zINSTREAM\0")
		for start in range(0, len(data), 8192):
			chunk = data[start:start + 8192]
			sock.sendall(struct.pack("!L", len(chunk)) + chunk)
		sock.sendall(struct.pack("!L", 0))
		answer = sock.recv(4096).decode(errors="replace").strip("\0\n ")
	return answer.endswith("OK") and "FOUND" not in answer, answer
