"""The built-in OCR: the text of a photo or of a scanned PDF read on the server itself by Tesseract (Persian and
English), without any AI and without the file leaving the server. The image is straightened, made grey, enlarged
when small and its contrast stretched before it is read."""

import io
import logging
import os
import shutil
import subprocess
import tempfile

_logger = logging.getLogger(__name__)

LANGUAGES = "fas+eng"
MAX_PAGES = 3
TIMEOUT = 90


def available():
	return bool(shutil.which("tesseract"))


def _variants(data):
	"""PNG bytes of the image at a few sizes, upright and grey: Tesseract reads Persian digits differently at each
	size, and the reading whose amounts agree is kept"""
	from PIL import Image, ImageOps

	image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
	width = image.width
	widths = [width]
	if width < 2200:
		widths.append(int(width * 1.3))
	if width > 2600:
		widths = [2000, 1500]
	elif width > 2000:
		widths.append(1500)
	images = []
	for target in widths:
		scaled = image if target == width else image.resize((target, int(image.height * target / width)), Image.BICUBIC)
		images.append(scaled)
	# The larger size once more in black and white, for pale or uneven photos
	images.append(images[-1].point(lambda value: 255 if value > 160 else 0))
	result = []
	for scaled in images:
		buffer = io.BytesIO()
		scaled.save(buffer, "PNG")
		result.append(buffer.getvalue())
	return result


def _tesseract(png, languages=LANGUAGES, psm=6):
	with tempfile.NamedTemporaryFile(suffix=".png") as handle:
		handle.write(png)
		handle.flush()
		result = subprocess.run(["tesseract", handle.name, "stdout", "-l", languages, "--psm", str(psm)],
			capture_output=True, timeout=TIMEOUT, check=False)
	if result.returncode:
		_logger.warning("Tesseract could not read an image: %s", result.stderr.decode(errors="replace")[:300])
	return result.stdout.decode(errors="replace")


def quality(text):
	"""How clean a reading looks: letters and digits against the stray marks Tesseract leaves where it is unsure"""
	if not text.strip():
		return 0.0
	stray = sum(text.count(mark) for mark in "»«[]\\|{}~^`")
	return len(text.strip()) / (1 + 8 * stray)


def image_texts(data, languages=LANGUAGES):
	"""The readings of a photo at a few sizes; empty when the OCR is not installed"""
	if not available():
		return []
	try:
		variants = _variants(data)
	except Exception:  # noqa: BLE001 - an image Pillow cannot open has no text for us
		_logger.info("The image could not be prepared for the OCR")
		return []
	return [text.strip() for text in (_tesseract(png, languages) for png in variants) if text.strip()]


def pdf_page_texts(data, languages=LANGUAGES, pages=MAX_PAGES):
	"""The readings of the first pages of a scanned PDF, made images at two resolutions"""
	if not available() or not shutil.which("pdftoppm"):
		return []
	readings = []
	with tempfile.TemporaryDirectory() as folder:
		path = os.path.join(folder, "in.pdf")
		with open(path, "wb") as handle:
			handle.write(data)
		for dpi in (200, 300):
			prefix = os.path.join(folder, f"p{dpi}")
			subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png", "-f", "1", "-l", str(pages), path, prefix],
				capture_output=True, timeout=TIMEOUT, check=False)
			texts = []
			for name in sorted(n for n in os.listdir(folder) if n.startswith(f"p{dpi}")):
				with open(os.path.join(folder, name), "rb") as handle:
					texts.append(_tesseract(handle.read(), languages))
			if any(text.strip() for text in texts):
				readings.append("\n".join(texts).strip())
	return readings


def document_texts(data, mimetype, languages=LANGUAGES):
	"""The readings of a photo or a PDF: a PDF's own text when it has one, else what the OCR reads"""
	from . import files as filetools

	if mimetype == "application/pdf":
		text = filetools.pdf_text(data) or ""
		if len(text.strip()) >= 20:
			return [text]
		return pdf_page_texts(data, languages)
	if mimetype.startswith("image/"):
		return image_texts(data, languages)
	return []


def document_text(data, mimetype, languages=LANGUAGES):
	"""The cleanest reading of a photo or a PDF"""
	texts = document_texts(data, mimetype, languages)
	return max(texts, key=quality) if texts else ""
