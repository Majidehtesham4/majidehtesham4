"""Persian digits read by their shape, without any AI. Tesseract reads Persian words well but often not the
digits of invoice fonts (zeros as «ه», commas lost), so the numbers of a page are read again here: the lines of
the tables are taken out, each number is cut into its glyphs, and each glyph is matched with templates of the
digits drawn from free Persian fonts (digit_templates.py)."""

import csv
import io
import re
import subprocess
import tempfile

from .digit_templates import TEMPLATES

SIZE = 16
DARK = 128
# A word of a number as Tesseract wrote it: digits, look-alike letters, separators
NUMERIC = re.compile(r"[0-9۰-۹٠-٩]|ه{2,}|^[\(\)%٪/,،٬.\-ههoO]+$")


def unlined(image, run=100):
	"""The page without the lines of its tables and boxes: dark runs longer than any letter, across and down"""
	from PIL import Image

	def clear(page):
		width, height = page.size
		data = bytearray(page.tobytes())
		dark = re.compile(rb"[\x00-\x8f]{%d,}" % run)
		for y in range(height):
			row = bytes(data[y * width:(y + 1) * width])
			for match in dark.finditer(row):
				data[y * width + match.start():y * width + match.end()] = b"\xff" * (match.end() - match.start())
		return Image.frombytes("L", (width, height), bytes(data))

	page = clear(image.convert("L"))
	return clear(page.transpose(Image.Transpose.ROTATE_90)).transpose(Image.Transpose.ROTATE_270)


def _components(crop):
	"""The separate marks of a small black-and-white crop: (left, top, right, bottom, pixels)"""
	width, height = crop.size
	data = crop.tobytes()
	dark = [value < DARK for value in data]
	seen = bytearray(width * height)
	found = []
	for start in range(width * height):
		if not dark[start] or seen[start]:
			continue
		stack, points = [start], []
		seen[start] = 1
		while stack:
			index = stack.pop()
			points.append(index)
			x, y = index % width, index // width
			for dy in (-1, 0, 1):
				for dx in (-1, 0, 1):
					nx, ny = x + dx, y + dy
					if 0 <= nx < width and 0 <= ny < height:
						other = ny * width + nx
						if dark[other] and not seen[other]:
							seen[other] = 1
							stack.append(other)
		xs = [p % width for p in points]
		ys = [p // width for p in points]
		found.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1, points))
	return found


def _levels(points, box, width):
	"""The glyph drawn as the templates are: fitted in 16x16, a little blurred, ink 0-15"""
	from PIL import Image, ImageFilter

	left, top, right, bottom = box
	w, h = right - left, bottom - top
	glyph = Image.new("L", (w, h), 255)
	pixels = glyph.load()
	for index in points:
		pixels[index % width - left, index // width - top] = 0
	scale = (SIZE - 2) / max(w, h)
	glyph = glyph.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.BILINEAR)
	canvas = Image.new("L", (SIZE, SIZE), 255)
	canvas.paste(glyph, ((SIZE - glyph.width) // 2, (SIZE - glyph.height) // 2))
	canvas = canvas.filter(ImageFilter.GaussianBlur(0.8))
	return bytes(15 - level // 16 for level in canvas.tobytes())


_TEMPLATES = [(char, bytes(int(c, 16) for c in levels), aspect, relative) for char, levels, aspect, relative in TEMPLATES]


def _classify(levels, aspect, relative):
	"""The character a glyph is, and how far it is from it (0 the same). Its size against the digits decides
	what it may be: a zero, a comma or a point is small; the other digits are not; a slash is taller."""
	best, score = None, 9.0
	for char, template, t_aspect, t_relative in _TEMPLATES:
		if char in "0.," and relative > 0.7 or char not in "0.,/" and relative < 0.55 or char == "/" and relative < 0.9:
			continue
		distance = sum(abs(a - b) for a, b in zip(levels, template)) / (SIZE * SIZE * 15)
		distance += 0.15 * abs(aspect - t_aspect) / max(aspect, t_aspect) + 0.4 * abs(relative - t_relative)
		if distance < score:
			best, score = char, distance
	return best, score


GOOD = 0.16


def read_number(page, box, debug=False):
	"""The number at a box of the page, as ASCII digits with «,» «/» «.»; empty when it does not look like one.
	The box grows to the glyphs next to it on its line that look like digits: Tesseract's box of a number it
	misread is often short."""
	left, top, right, bottom = box
	pad = max(4, (bottom - top) // 3)
	band = page.crop((0, max(top - pad, 0), page.width, bottom + pad))
	marks = [m for m in _components(band) if len(m[4]) >= 3 and m[3] - m[1] <= (bottom - top) * 2.5]
	inside = [m for m in marks if m[2] > left and m[0] < right]
	if not inside:
		return ""

	def stacked(mark):
		# A small mark with another small one above or below it (a colon, the dots of a letter) is not a digit
		size = mark[3] - mark[1]
		return any(other is not mark and other[0] < mark[2] and mark[0] < other[2] and other[3] - other[1] <= size * 1.5
			and (other[3] <= mark[1] or other[1] >= mark[3]) and min(abs(other[3] - mark[1]), abs(mark[3] - other[1])) <= size * 2
			for other in marks)

	def reading(group, height, cache):
		result = []
		for mark in sorted(group, key=lambda m: m[0]):
			key = (id(mark), height)
			if key not in cache:
				mleft, mtop, mright, mbottom, points = mark
				cache[key] = _classify(_levels(points, mark[:4], band.width), (mright - mleft) / (mbottom - mtop),
					(mbottom - mtop) / height)
			result.append(cache[key])
		return result

	cache = {}
	# The height of a digit: tried among the taller marks (a slash is taller than digits, zeros smaller), and the
	# one under which the glyphs match the templates best is kept
	heights = sorted({m[3] - m[1] for m in inside}, reverse=True)[:4]
	start = [m for m in inside if not stacked(m)]
	if not start:
		return ""
	digit_height = min(heights, key=lambda h: sum(score for _c, score in reading(
		[m for m in start if m[3] - m[1] <= h * 1.7], h, cache)) / max(1, len([m for m in start if m[3] - m[1] <= h * 1.7])))
	group = [m for m in start if m[3] - m[1] <= digit_height * 1.7]
	grown = True
	while grown:
		grown = False
		low, high = min(m[0] for m in group), max(m[2] for m in group)
		for mark in marks:
			if mark in group:
				continue
			gap = low - mark[2] if mark[2] <= low else mark[0] - high
			if 0 <= gap <= 0.7 * digit_height and mark[3] - mark[1] <= digit_height * 1.7 and not stacked(mark) \
					and reading([mark], digit_height, cache)[0][1] <= GOOD:
				group.append(mark)
				grown = True
	# The longest run of glyphs that match well is the number; a letter or a sign next to it ends the run
	runs, current = [], ""
	for char, score in reading(group, digit_height, cache):
		if debug:
			print(char, round(score, 3))
		if char and score <= GOOD * 1.25:
			current += char
		else:
			runs.append(current)
			current = ""
	runs.append(current)
	text = max(runs, key=lambda run: len(re.findall(r"\d", run))).strip(".,/")
	return text if len(re.findall(r"\d", text)) >= 1 else ""


def _numeric(word):
	"""A word worth reading again: Persian digits or what Tesseract made of them; not Latin digits (read well), not
	a percent in parentheses (its sign is not a digit)"""
	word = re.sub(r"[\u200e\u200f\u202a-\u202e]", "", word)
	if re.fullmatch(r"[0-9\-/.,:]+", word) or re.search(r"[()%٪]", word):
		return False
	return bool(NUMERIC.search(word))


def page_text(png, languages="fas+eng", psm=6):
	"""The text of a page, with its numbers read again by their shape"""
	from PIL import Image

	page = unlined(Image.open(io.BytesIO(png)))
	with tempfile.NamedTemporaryFile(suffix=".png") as handle:
		page.save(handle, "PNG")
		handle.flush()
		result = subprocess.run(["tesseract", handle.name, "stdout", "-l", languages, "--psm", str(psm), "tsv"],
			capture_output=True, timeout=120, check=False)
	lines = {}
	for row in csv.DictReader(io.StringIO(result.stdout.decode(errors="replace")), delimiter="\t"):
		word = (row.get("text") or "").strip()
		if not word:
			continue
		key = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
		box = (int(row["left"]), int(row["top"]), int(row["left"]) + int(row["width"]), int(row["top"]) + int(row["height"]))
		lines.setdefault(key, []).append([word, box])
	texts = []
	for _key, words in sorted(lines.items()):
		# Pieces of one number Tesseract cut apart are joined first: numeric words close to each other
		groups, current = [], []
		for entry in sorted((w for w in words if _numeric(w[0])), key=lambda w: w[1][0]):
			if current:
				last = current[-1][1]
				height = max(last[3] - last[1], entry[1][3] - entry[1][1])
				if entry[1][0] - last[2] > 0.8 * height:
					groups.append(current)
					current = []
			current.append(entry)
		if current:
			groups.append(current)
		for group in groups:
			box = (min(w[1][0] for w in group), min(w[1][1] for w in group), max(w[1][2] for w in group),
				max(w[1][3] for w in group))
			read = read_number(page, box)
			if not read:
				continue
			group[0][0] = read
			for entry in group[1:]:
				entry[0] = ""
		texts.append(" ".join(word for word, _box in words if word))
	return "\n".join(texts)
