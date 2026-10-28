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
MAX_PAGES = 6
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


def _sized(data, low=1600, high=2600):
	"""The image upright and grey, between 1600 and 2600 pixels wide: the size the shapes of digits are read at"""
	from PIL import Image, ImageOps

	image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
	if not low <= image.width <= high:
		width = 1800 if image.width < low else 2200
		image = image.resize((width, int(image.height * width / image.width)), Image.BICUBIC)
	buffer = io.BytesIO()
	image.save(buffer, "PNG")
	return buffer.getvalue()


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
	from . import digits

	larger = variants[1 if len(variants) > 2 else 0]
	# First the page without its table lines and with its numbers read by their shape: Tesseract reads Persian
	# words well, but often not the digits of invoice fonts
	try:
		readings = [digits.page_text(_sized(data), languages)]
	except Exception:  # noqa: BLE001 - the plain readings below still come
		_logger.exception("The numbers of a page could not be read by their shape")
		readings = []
	readings += [_tesseract(png, languages) for png in variants]
	# The larger size once more column by column (rows of a table) and as scattered text (boxes of a form)
	readings += [_tesseract(larger, languages, psm=psm) for psm in (4, 11)]
	return [text.strip() for text in readings if text.strip()]


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
			if dpi == 300 and len(readings) and readings[0].count("\f") >= 2:
				break
			prefix = os.path.join(folder, f"p{dpi}")
			subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png", "-f", "1", "-l", str(pages), path, prefix],
				capture_output=True, timeout=TIMEOUT, check=False)
			texts = []
			pages_png = []
			for name in sorted(n for n in os.listdir(folder) if n.startswith(f"p{dpi}")):
				with open(os.path.join(folder, name), "rb") as handle:
					pages_png.append(handle.read())
			if len(pages_png) == 1:
				# A one-page PDF (most invoices) is read like a photo, in all its ways, at 300 dpi
				subprocess.run(["pdftoppm", "-r", "300", "-gray", "-png", "-f", "1", "-l", "1", path,
					os.path.join(folder, "fine")], capture_output=True, timeout=TIMEOUT, check=False)
				fine = [n for n in os.listdir(folder) if n.startswith("fine")]
				if fine:
					with open(os.path.join(folder, fine[0]), "rb") as handle:
						return image_texts(handle.read(), languages)
				return image_texts(pages_png[0], languages)
			texts = [_tesseract(png, languages) for png in pages_png]
			if any(text.strip() for text in texts):
				readings.append("\f".join(texts).strip())
			if len(texts) > 2:
				# A long PDF is read once, at 200 dpi
				break
	return readings


def document_texts(data, mimetype, languages=LANGUAGES):
	"""The readings of a photo or a PDF: a PDF's own text when it has one, else what the OCR reads"""
	from . import files as filetools

	if mimetype == "application/pdf":
		# A PDF's own text first; Persian PDFs often keep their letters in drawing order or with odd digits, so the
		# pages are also read as images and the reading that agrees best is kept
		text = filetools.pdf_text(data) or ""
		texts = [text] if len(text.strip()) >= 20 else []
		return texts + pdf_page_texts(data, languages)
	if mimetype.startswith("image/"):
		return image_texts(data, languages)
	return []


def document_text(data, mimetype, languages=LANGUAGES):
	"""The cleanest reading of a photo or a PDF"""
	texts = document_texts(data, mimetype, languages)
	return max(texts, key=quality) if texts else ""
