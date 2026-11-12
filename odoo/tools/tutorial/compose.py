"""The film of one section, from the screenshots capture.js took (steps.json) and the section's description
(sections.py): the logo first, then the panel on the right that slides in toward the left, the program on the left
in a browser frame, subtitles below; a gentle camera, the cursor and its clicks, the typing; the panel slides out
to the right at the end, the browser to the left, and the logo comes with VERON ERP under it and stays to the last
frame. No fade at the end: the sections are cut one after another.

	python3 compose.py <section number> <folder of the screenshots> <out.mp4>
	FRAMES=0,300 python3 compose.py ...      only those frames (to check), as PNGs in the folder
"""
import json
import math
import os
import subprocess
import sys
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import logo  # noqa: E402
from sections import SECTIONS  # noqa: E402

W, H, FPS = 1920, 1080, 30
VW, VH = 1440, 810                         # the browser's page, in css px
FONTS = os.path.join(HERE, "..", "..", "addons", "veron_fonts_iran", "static", "fonts", "")
RED = (232, 34, 44)
WHITE = (240, 240, 244)
MUTED = (150, 152, 162)

# the layout: the browser on the left, its address bar, the subtitles under it, the panel on the right
FX, FY, FW = 40, 30, 1340
BAR = 40
PW, PH = FW, round(FW * VH / VW)           # the page, 1340 x 754
SUB_Y = FY + BAR + PH + 20                 # the subtitles
PANEL_X, PANEL_Y, PANEL_W, PANEL_H = 1410, 30, 476, 1020
SRC_K = 1.45                               # the screenshots are kept at 1.45 px a css px (the camera's highest zoom)
MAX_ZOOM = 1.45


def font(size, bold=True):
	return ImageFont.truetype(FONTS + ("Vazirmatn-Bold.ttf" if bold else "Vazirmatn-Regular.ttf"), size)


def font_latin(size):
	return ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Medium.otf", size)


def fa(text):
	return str(text).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def clamp(x, a=0.0, b=1.0):
	return max(a, min(b, x))


def ease(x):
	x = clamp(x)
	return 4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_inv(y):
	"""the time at which ease() reaches y: the pictures of a scroll spaced so it starts and ends slowly"""
	lo, hi = 0.0, 1.0
	for _ in range(30):
		mid = (lo + hi) / 2
		lo, hi = (mid, hi) if ease(mid) < y else (lo, mid)
	return (lo + hi) / 2


def out3(x):
	return 1 - (1 - clamp(x)) ** 3


def in3(x):
	return clamp(x) ** 3


# ---------------------------------------------------------------- text

def text_img(text, size, color=WHITE, bold=True, rtl=True, f=None):
	f = f or font(size, bold)
	d = "rtl" if rtl else "ltr"
	box = f.getbbox(text, direction=d, language="fa" if rtl else None)
	w, h = box[2] - box[0] + 6, box[3] - box[1] + 14
	im = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
	ImageDraw.Draw(im).text((3 - box[0], 7 - box[1]), text, font=f, fill=color, direction=d, language="fa" if rtl else None)
	return im


def wrap(text, size, width, bold=True):
	f = font(size, bold)
	lines, cur = [], ""
	for word in text.split():
		trial = (cur + " " + word).strip()
		if f.getlength(trial, direction="rtl", language="fa") > width and cur:
			lines.append(cur)
			cur = word
		else:
			cur = trial
	if cur:
		lines.append(cur)
	return lines


def text_block(text, size, width, color=WHITE, bold=True, gap=1.55, align="right"):
	lines = wrap(text, size, width, bold)
	ims = [text_img(l, size, color, bold) for l in lines]
	lh = round(size * gap)
	out = Image.new("RGBA", (width, lh * len(ims) + 8), (0, 0, 0, 0))
	for k, im in enumerate(ims):
		x = width - im.width if align == "right" else (width - im.width) // 2
		out.alpha_composite(im, (max(0, x), k * lh))
	return out


def shadowed(im, blur=8, alpha=0.75, off=(0, 3)):
	pad = blur * 3
	out = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
	sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
	sh.paste((0, 0, 0, int(255 * alpha)), (pad + off[0], pad + off[1]), im.split()[3])
	out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
	out.alpha_composite(im, (pad, pad))
	return out


def put(base, im, xy, alpha=1.0):
	if alpha <= 0.003 or im is None:
		return
	if alpha < 0.997:
		im = im.copy()
		a = np.asarray(im.split()[3], np.float32) * alpha
		im.putalpha(Image.fromarray(a.astype(np.uint8)))
	x, y = int(round(xy[0])), int(round(xy[1]))
	if x >= base.width or y >= base.height or x + im.width <= 0 or y + im.height <= 0:
		return
	cx0, cy0 = max(0, -x), max(0, -y)
	cx1, cy1 = min(im.width, base.width - x), min(im.height, base.height - y)
	base.alpha_composite(im.crop((cx0, cy0, cx1, cy1)), (x + cx0, y + cy0))


# ---------------------------------------------------------------- the static layers

@lru_cache(maxsize=1)
def background():
	y, x = np.mgrid[0:H, 0:W].astype(np.float32)
	d = np.hypot((x - W * 0.42) / W, (y - H * 0.45) / H)
	c = np.clip(1 - d * 1.3, 0, 1)[..., None]
	img = np.array([11, 11, 14], np.float32) + c * np.array([12, 11, 15], np.float32)
	g = np.clip(1 - np.hypot((x - W * 0.85) / W, (y - H * 0.2) / H) * 2.2, 0, 1)[..., None]
	img = img + g * np.array([26, 3, 6], np.float32)
	return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")


@lru_cache(maxsize=1)
def frame_shadow():
	pad = 60
	sh = Image.new("RGBA", (FW + 2 * pad, BAR + PH + 2 * pad), (0, 0, 0, 0))
	ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 14, pad + FW, pad + BAR + PH + 14), 14, fill=(0, 0, 0, 170))
	return sh.filter(ImageFilter.GaussianBlur(26)), pad


@lru_cache(maxsize=1)
def frame_mask():
	m = Image.new("L", (FW, BAR + PH), 0)
	ImageDraw.Draw(m).rounded_rectangle((0, 0, FW - 1, BAR + PH - 1), 14, fill=255)
	return m


def address_bar(url, caret=False):
	bar = Image.new("RGBA", (FW, BAR), (30, 31, 36, 255))
	d = ImageDraw.Draw(bar)
	for k, c in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
		d.ellipse((18 + k * 22, 14, 30 + k * 22, 26), fill=c)
	d.rounded_rectangle((110, 7, FW - 110, BAR - 7), 13, fill=(18, 19, 22))
	f = font_latin(17)
	d.text((132, 10), "\U0001F512", font=f, fill=(120, 124, 132)) if False else d.text((130, 11), "https://", font=f, fill=(110, 113, 122))
	x = 130 + f.getlength("https://")
	d.text((x, 11), url, font=f, fill=(225, 226, 230))
	if caret:
		cx = x + f.getlength(url) + 2
		d.line((cx, 12, cx, BAR - 12), fill=(225, 226, 230), width=2)
	return bar


@lru_cache(maxsize=1)
def cursor_img():
	S = 3
	im = Image.new("RGBA", (34 * S, 46 * S), (0, 0, 0, 0))
	pts = [(2, 2), (2, 34), (10, 26), (16, 40), (22, 37), (16, 24), (27, 24)]
	pts = [(x * S, y * S) for x, y in pts]
	d = ImageDraw.Draw(im)
	sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
	ImageDraw.Draw(sh).polygon([(x + 3 * S, y + 4 * S) for x, y in pts], fill=(0, 0, 0, 120))
	im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(3 * S)))
	d.polygon(pts, fill=(20, 20, 24), outline=(255, 255, 255))
	d.line(pts + [pts[0]], fill=(255, 255, 255), width=2 * S)
	return im.resize((34, 46), Image.LANCZOS)


@lru_cache(maxsize=None)
def page_image(path):
	"""a screenshot at SRC_K px a css px"""
	im = Image.open(path).convert("RGB")
	return im.resize((round(VW * SRC_K), round(VH * SRC_K)), Image.LANCZOS)


# ---------------------------------------------------------------- the panel

class Panel:
	LOGO = 124

	def __init__(self, meta):
		self.meta = meta
		w = PANEL_W - 56
		self.items = []                 # (image, y) — the parts that come in one after another
		y = 30 + self.LOGO + 18
		num = text_img(f"بخش {fa(meta['n'])}", 26, RED)
		self.items.append((num, y)); y += num.height + 4
		title = text_block(meta["title"], 34, w, WHITE, True, 1.38)
		self.items.append((title, y)); y += title.height + 8
		goal = text_block(meta["goal"], 22, w, (186, 188, 196), False, 1.55)
		self.items.append((goal, y)); y += goal.height + 10
		self.div1 = y; y += 16
		lab = text_img("ماژول‌ها", 22, MUTED)
		self.items.append((lab, y)); y += lab.height + 6
		chips = self.chips(meta["modules"], w)
		self.items.append((chips, y)); y += chips.height + 14
		self.div2 = y; y += 16
		lab2 = text_img("مراحل", 22, MUTED)
		self.items.append((lab2, y)); y += lab2.height + 8
		self.steps_y = y
		self.steps = [text_block(s, 25, w - 60, WHITE, False, 1.45) for s in meta["steps"]]
		self.steps_bold = [text_block(s, 25, w - 60, WHITE, True, 1.45) for s in meta["steps"]]
		self.step_h = [max(50, s.height + 10) for s in self.steps]
		self.box_cache = {}

	def chips(self, modules, width):
		chips = []
		for name, icon in modules:
			t = text_img(name, 21, (220, 221, 226))
			ic = Image.open(icon).convert("RGBA").resize((34, 34), Image.LANCZOS) if icon and os.path.exists(icon) else None
			cw = t.width + 18 + (40 if ic else 0)
			c = Image.new("RGBA", (cw, 46), (0, 0, 0, 0))
			ImageDraw.Draw(c).rounded_rectangle((0, 0, cw - 1, 45), 10, fill=(30, 31, 37), outline=(48, 49, 56))
			c.alpha_composite(t, (cw - t.width - 9 - (40 if ic else 0), (46 - t.height) // 2 + 1))
			if ic:
				c.alpha_composite(ic, (cw - 42, 6))
			chips.append(c)
		rows, row, rw = [], [], 0
		for c in chips:
			if rw + c.width > width and row:
				rows.append(row); row, rw = [], 0
			row.append(c); rw += c.width + 8
		if row:
			rows.append(row)
		out = Image.new("RGBA", (width, len(rows) * 54), (0, 0, 0, 0))
		for k, r in enumerate(rows):
			x = width
			for c in r:
				x -= c.width
				out.alpha_composite(c, (x, k * 54))
				x -= 8
		return out

	@lru_cache(maxsize=64)
	def body(self, current, done):
		"""the panel's surface with the step list for the current step (and how many are done)"""
		im = Image.new("RGBA", (PANEL_W, PANEL_H), (0, 0, 0, 0))
		d = ImageDraw.Draw(im)
		d.rectangle((0, 0, PANEL_W - 1, PANEL_H - 1), fill=(17, 18, 22, 246), outline=(40, 41, 48))
		d.rectangle((PANEL_W - 4, 0, PANEL_W - 1, PANEL_H - 1), fill=RED)
		for y in (self.div1, self.div2):
			d.line((28, y, PANEL_W - 28, y), fill=(40, 41, 48), width=1)
		y = self.steps_y
		for k, (s, sb, h) in enumerate(zip(self.steps, self.steps_bold, self.step_h)):
			cx = PANEL_W - 28 - 18
			if k == current:
				d.rectangle((14, y - 4, PANEL_W - 14, y + h - 10), fill=(36, 22, 26))
				d.rectangle((PANEL_W - 18, y - 4, PANEL_W - 14, y + h - 10), fill=RED)
			if k < done:
				d.ellipse((cx - 15, y + 4, cx + 15, y + 34), fill=(44, 28, 32), outline=RED, width=2)
				d.line((cx - 7, y + 19, cx - 2, y + 25, cx + 8, y + 12), fill=(255, 120, 120), width=3)
				tcol = 0.55
			else:
				d.ellipse((cx - 15, y + 4, cx + 15, y + 34), fill=RED if k == current else (32, 33, 39))
				n = text_img(fa(k + 1), 19, WHITE if k == current else MUTED)
				im.alpha_composite(n, (cx - n.width // 2, y + 19 - n.height // 2))
				tcol = 1.0 if k == current else 0.5
			src = sb if k == current else s
			src = src.copy()
			src.putalpha(src.split()[3].point(lambda v, a=tcol: int(v * a)))
			im.alpha_composite(src, (PANEL_W - 28 - 46 - src.width, y + 2))
			y += h
		return im

	def logo_box(self, t):
		return logo.box(self.LOGO, t)


# ---------------------------------------------------------------- the timeline

INTRO = 3.4          # the logo alone, then it goes to the panel
PANEL_IN = 0.9
OUTRO = 4.2          # the logo and the wordmark at the end


def build(steps, meta):
	"""seconds for every record: the camera, the cursor, the pictures, the subtitles, the sounds"""
	T = INTRO + PANEL_IN + 0.3
	segs, sounds = [], []
	cam = (VW / 2, VH / 2, 1.0)
	cur = (VW * 0.62, VH * 0.55)
	cam_keys, cur_keys, clicks = [(0, cam)], [(0, cur)], []
	subs = []
	done = 0
	for r in steps:
		kind = r["kind"]
		t0 = T
		tgt = r.get("target")
		c = r.get("cam")
		if c == "full" or r.get("newpage"):
			cam = (VW / 2, VH / 2, 1.0)
		elif isinstance(c, dict) and c.get("focus"):
			cam = focus_cam(c["focus"], c.get("zoom"))
		elif kind == "type" and tgt and c is None:
			cam = focus_cam([tgt[0] - 300, tgt[1] - 160, tgt[2] + 600, tgt[3] + 320])
		cam_keys.append((t0, cam))
		pics = []
		if kind in ("click", "type", "hover") and tgt:
			dest = (tgt[0] + tgt[2] / 2, tgt[1] + tgt[3] / 2)
			move = 0.55 if math.dist(dest, cur) > 4 else 0.1
			cur_keys.append((t0 + 0.12, cur))
			cur_keys.append((t0 + 0.12 + move, dest))
			cur = dest
			tc = t0 + 0.12 + move + 0.08
			if kind != "hover":
				clicks.append(tc)
				sounds.append((tc, "click"))
			if kind == "type":
				files = r["files"]
				pics.append((t0, r["file"]))
				step = min(0.085, 2.4 / max(1, len(files)))
				tt = tc + 0.25
				for f in files:
					pics.append((tt, f))
					sounds.append((tt, "key"))
					tt += step
				T = tt + 0.45
			else:
				pics.append((t0, r["file"]))
				T = tc + (0.45 if kind == "click" else 0.6)
		elif kind == "scroll":
			# the page going down (or up): its pictures one after another, no dissolve between them
			files = r["files"]
			pics.append((t0, r["file"]))
			step = r.get("dur", 2.2) / max(1, len(files))
			tt = t0 + 0.2
			for k, f in enumerate(files):
				# eased: slow to start and to stop
				pics.append((t0 + 0.2 + r.get("dur", 2.2) * ease_inv(k / max(1, len(files) - 1)), f))
			T = t0 + 0.2 + r.get("dur", 2.2) + 0.3
		elif kind == "url":
			pics.append((t0, r["file"]))
			url = r["url_typed"]
			step = 0.075
			for k in range(1, len(url) + 1):
				sounds.append((t0 + 0.4 + k * step, "key"))
			T = t0 + 0.4 + len(url) * step + 0.6
			sounds.append((T - 0.3, "click"))
		else:
			pics.append((t0, r["file"]))
			T = t0 + r.get("hold", 1.4)
		if r.get("hold") and kind != "view":
			T += r["hold"]
		if r.get("done"):
			done = max(done, r["done"])
			sounds.append((T - 0.2, "tick"))
		segs.append({"t0": t0, "t1": T, "rec": r, "pics": pics, "step": r.get("step", 0), "done": done})
		# a subtitle comes in once, when its text changes; the records under the same text keep it still
		if r.get("sub") and (not subs or subs[-1][1] != r["sub"]):
			subs.append([t0, r["sub"]])
	# each subtitle long enough to be read: the time it needs is added after its last record
	k = 0
	while k < len(subs):
		t0, text = subs[k]
		t1 = subs[k + 1][0] if k + 1 < len(subs) else T
		need = 1.2 + len(text) * 0.06
		if t1 - t0 < need:
			extra = need - (t1 - t0)
			for s in segs:
				if s["t0"] >= t1:
					s["t0"] += extra; s["t1"] += extra
					s["pics"] = [(a + extra, f) for a, f in s["pics"]]
			for j in range(k + 1, len(subs)):
				subs[j][0] += extra
			cam_keys = [(a + extra if a >= t1 else a, v) for a, v in cam_keys]
			cur_keys = [(a + extra if a >= t1 else a, v) for a, v in cur_keys]
			clicks = [a + extra if a >= t1 else a for a in clicks]
			sounds = [(a + extra if a >= t1 else a, s) for a, s in sounds]
			T += extra
		k += 1
	end_hold = 1.4
	t_out = T + end_hold                   # the panel goes out to the right,
	t_away = t_out + 0.55                  # then the browser to the left,
	t_end = t_away + 0.75                  # then the logo with VERON ERP, held to the last frame (no fade)
	total = t_end + OUTRO
	return {"segs": segs, "cam": cam_keys, "cur": cur_keys, "clicks": clicks, "subs": subs, "sounds": sounds,
		"t_out": t_out, "t_away": t_away, "t_end": t_end, "total": total, "start": INTRO + PANEL_IN + 0.3}


def focus_cam(rect, zoom=None):
	x, y, w, h = rect
	# never closer than what keeps the whole of the focused thing in the picture
	fit = min(VW / max(w, 1), VH / max(h, 1))
	z = clamp(min(zoom or fit, fit), 1.0, MAX_ZOOM)
	return (x + w / 2, y + h / 2, z)


def keyed(keys, t, dur=0.75):
	"""the value at t: each key reached over dur seconds, eased"""
	prev = keys[0][1]
	for k, (tk, v) in enumerate(keys):
		if t < tk:
			break
		p = ease((t - tk) / dur)
		prev = tuple(a + (b - a) * p for a, b in zip(prev, v)) if p < 1 else v
	return prev


def keyed_cursor(keys, t):
	for (t0, a), (t1, b) in zip(keys, keys[1:]):
		if t0 <= t <= t1:
			p = ease((t - t0) / max(1e-6, t1 - t0))
			# a slight arc
			mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - math.dist(a, b) * 0.08
			x = (1 - p) ** 2 * a[0] + 2 * (1 - p) * p * mx + p * p * b[0]
			y = (1 - p) ** 2 * a[1] + 2 * (1 - p) * p * my + p * p * b[1]
			return (x, y)
		if t < t0:
			return a
	return keys[-1][1]


# ---------------------------------------------------------------- one frame

G = {}


def setup(n, folder):
	meta = SECTIONS[n]
	steps = json.load(open(os.path.join(folder, "steps.json")))
	G.update(meta=meta, folder=folder, tl=build(steps, meta), panel=Panel(meta))
	return G["tl"]


def pic_at(t):
	"""the screenshot shown at t, and the one before it with how much of it still shows (a short dissolve)"""
	tl = G["tl"]
	seq = [p for s in tl["segs"] for p in s["pics"]]
	cur, prev, tc = seq[0][1], None, 0
	for a, f in seq:
		if a <= t:
			if f != cur:
				prev, cur, tc = cur, f, a
		else:
			break
	mix = 0.0
	if prev is not None and t - tc < 0.18 and not os.path.basename(cur).startswith(os.path.basename(prev).split("_t")[0] + "_t"):
		mix = 1 - (t - tc) / 0.18
	return cur, prev, mix


def page_view(t):
	cx, cy, z = keyed(G["tl"]["cam"], t)
	vw, vh = VW / z, VH / z
	x0 = clamp(cx - vw / 2, 0, VW - vw)
	y0 = clamp(cy - vh / 2, 0, VH - vh)
	cur, prev, m = pic_at(t)
	mw, mh = round(VW * SRC_K), round(VH * SRC_K)
	box = (max(0.0, x0 * SRC_K), max(0.0, y0 * SRC_K), min(mw, (x0 + vw) * SRC_K), min(mh, (y0 + vh) * SRC_K))
	im = page_image(os.path.join(G["folder"], cur)).resize((PW, PH), Image.BICUBIC, box=box)
	if m > 0 and prev:
		im2 = page_image(os.path.join(G["folder"], prev)).resize((PW, PH), Image.BICUBIC, box=box)
		im = Image.blend(im, im2, m)
	return im, (x0, y0, z)


def current_seg(t):
	segs = G["tl"]["segs"]
	s0 = segs[0]
	for s in segs:
		if s["t0"] <= t:
			s0 = s
	return s0


def render(i):
	t = i / FPS
	tl, meta, panel = G["tl"], G["meta"], G["panel"]
	img = background().copy()
	start = tl["start"]
	# --- the logo alone, then to the panel
	p_in = out3((t - INTRO) / PANEL_IN)                       # the panel coming in
	p_out = in3((t - tl["t_out"]) / 0.8)                       # and going out
	px = PANEL_X + (W - PANEL_X + 20) * (1 - p_in) + (W - PANEL_X + 20) * p_out
	big = 320
	if t < INTRO + PANEL_IN:
		built = clamp((t - 0.35) / 1.5)
		k = ease((t - INTRO) / PANEL_IN)
		size = round(big + (Panel.LOGO - big) * k)
		lx = (W - big) / 2 + ((px + (PANEL_W - Panel.LOGO) / 2) - (W - big) / 2) * k
		ly = (H - big) / 2 - 90 + ((PANEL_Y + 30) - ((H - big) / 2 - 90)) * k
		a = out3(t / 0.45)
		lb = logo.box(big, t, built) if built < 1 else logo.box(big, t)
		if size != big:
			lb = lb.resize((size, size), Image.LANCZOS)
		if k <= 0:
			put(img, shadowed(lb, 18, 0.7, (0, 10)), (lx - 54, ly - 54), a)
			# the section's name under the logo, with the same entrance as the panel's text
			for j, (im, dy) in enumerate(intro_texts()):
				q = out3((t - 1.25 - j * 0.12) / 0.5) * (1 - out3((t - INTRO + 0.25) / 0.3))
				put(img, im, ((W - im.width) / 2, (H + big) / 2 - 60 + dy + 18 * (1 - q)), q)
		else:
			# the panel arrives under the moving logo
			draw_panel(img, t, px, -1, 0, p_in, logo_shown=False)
			put(img, lb, (lx, ly))
	else:
		draw_panel(img, t, px, *step_state(t), p_in)
	# --- the browser
	fa_in = out3((t - (INTRO + 0.45)) / 0.7)
	away = in3((t - tl["t_away"]) / 0.75)                     # the browser leaving to the left at the end
	if fa_in > 0 and away < 1:
		seg = current_seg(t)
		page, (x0, y0, z) = page_view(max(t, start))
		frame = Image.new("RGBA", (FW, BAR + PH), (0, 0, 0, 255))
		url, caret = seg["rec"].get("url", ""), False
		if seg["rec"]["kind"] == "url" and t >= seg["t0"]:
			typed = seg["rec"]["url_typed"]
			n = int(clamp((t - seg["t0"] - 0.4) / 0.075, 0, len(typed)))
			url, caret = typed[:n], (t * 2) % 1 < 0.6
		frame.paste(address_bar(url, caret), (0, 0))
		frame.paste(page, (0, BAR))
		# the cursor and its clicks
		if t >= start:
			cx, cy = keyed_cursor(tl["cur"], t)
			sx = (cx - x0) * z * PW / VW
			sy = (cy - y0) * z * PH / VH + BAR
			for tc in tl["clicks"]:
				q = (t - tc) / 0.45
				if 0 <= q <= 1:
					r = 8 + 24 * out3(q)
					ov = Image.new("RGBA", frame.size, (0, 0, 0, 0))
					ImageDraw.Draw(ov).ellipse((sx - r, sy - r, sx + r, sy + r), outline=(232, 40, 50, int(220 * (1 - q))), width=3)
					frame.alpha_composite(ov)
			mark(frame, seg, t, x0, y0, z)
			frame.alpha_composite(cursor_img(), (int(sx - 3), int(sy - 3)))
		dx = -30 * (1 - fa_in) - (FX + FW + 90) * away
		sh, pad = frame_shadow()
		put(img, sh, (FX - pad + dx, FY - pad), fa_in)
		mask = frame_mask()
		fr = Image.new("RGBA", frame.size, (0, 0, 0, 0))
		fr.paste(frame, (0, 0), mask)
		put(img, fr, (FX + dx, FY), fa_in)
	# --- the subtitles
	draw_sub(img, t)
	# --- the end: the logo and VERON ERP
	if t >= tl["t_end"]:
		outro(img, t - tl["t_end"])
	return img.convert("RGB")


def mark(frame, seg, t, x0, y0, z):
	"""a red frame round the thing the cursor points at, when the record asks for it (a small button)"""
	r = seg["rec"]
	if not r.get("mark") or not r.get("target"):
		return
	q = out3((t - seg["t0"] - 0.6) / 0.3)
	if q <= 0:
		return
	x, y, w, h = r["target"]
	k = z * PW / VW
	pad = 7 + 3 * math.sin(t * 6)
	a0, b0 = (x - x0) * k - pad, (y - y0) * k + BAR - pad
	a1, b1 = (x + w - x0) * k + pad, (y + h - y0) * k + BAR + pad
	ov = Image.new("RGBA", frame.size, (0, 0, 0, 0))
	d = ImageDraw.Draw(ov)
	d.rounded_rectangle((a0 - 4, b0 - 4, a1 + 4, b1 + 4), 12, outline=(232, 34, 44, int(70 * q)), width=6)
	d.rounded_rectangle((a0, b0, a1, b1), 9, outline=(240, 50, 60, int(235 * q)), width=3)
	frame.alpha_composite(ov)


WORD = os.path.join(HERE, "..", "intro", "wordmark_mask.png")
UNDER = (1298, 258, 1740, 258)      # the red line under ERP, in the mask's space


@lru_cache(maxsize=2)
def word_layers(w):
	"""the wordmark at width w: its letters (brushed metal), their thin red outline (not drawn now), the line under ERP"""
	m = Image.open(WORD).split()[3]
	k = w / m.width
	h = round(m.height * k)
	pad = 30
	a = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
	a.paste(m.resize((w, h), Image.LANCZOS), (pad, pad))
	A = np.asarray(a, np.float32) / 255
	# brushed metal: light above, a dark band in the middle, lighter again below (over the letters' own height)
	yy = np.clip((np.arange(a.height) - pad) / max(1, h), 0, 1)
	tone = np.interp(yy, [0, 0.42, 0.5, 1], [214, 150, 92, 172])[:, None]
	face = np.zeros((a.height, a.width, 4), np.float32)
	face[..., 0] = tone; face[..., 1] = tone + 4; face[..., 2] = tone + 12
	face[..., 3] = A * 255
	grown = np.asarray(a.filter(ImageFilter.MaxFilter(5)), np.float32) / 255
	rim = np.clip(grown - A, 0, 1)
	rim_im = np.zeros_like(face)
	rim_im[..., 0], rim_im[..., 1], rim_im[..., 2], rim_im[..., 3] = 255, 52, 58, rim * 255
	rim_img = Image.fromarray(rim_im.astype(np.uint8), "RGBA")
	glow = rim_img.filter(ImageFilter.GaussianBlur(6))
	x0, y0, x1, y1 = (v * k for v in UNDER)
	return (Image.fromarray(np.clip(face, 0, 255).astype(np.uint8), "RGBA"), rim_img, glow, A,
		(x0 + pad, y0 + pad, x1 + pad), pad)


def outro(img, u):
	"""the logo grows in the middle, VERON ERP comes up under it, a light runs over the letters; it stays"""
	big = 300
	q = out3(u / 0.7)
	size = round(big * (0.86 + 0.14 * q))
	lb = logo.box(size, 3.0 + u)
	ly = (H - big) / 2 - 110
	put(img, shadowed(lb, 18, 0.7, (0, 10)), ((W - size) / 2 - 54, ly + (big - size) / 2 - 54), q)
	ww = 560
	face, rim, glow, A, (ux0, uy, ux1), pad = word_layers(ww)
	p = out3((u - 0.55) / 0.8)
	if p <= 0:
		return
	wx = (W - face.width) / 2
	wy = ly + big + 40 + 16 * (1 - p)
	letters = face.copy()
	s = (u - 1.0) / 1.1                                       # one bright band across the letters
	if -0.2 < s < 1.2:
		xx = np.arange(face.width)[None, :]
		band = np.exp(-((xx - (-120 + (face.width + 240) * s)) / 70) ** 2)
		L = np.asarray(letters, np.float32)
		L[..., :3] = np.clip(L[..., :3] + band[..., None] * 90, 0, 255)
		letters = Image.fromarray(L.astype(np.uint8), "RGBA")
	put(img, letters, (wx, wy), p)
	# the red line under ERP draws itself
	r = out3((u - 1.0) / 0.6)
	if r > 0:
		line = Image.new("RGBA", (face.width, face.height), (0, 0, 0, 0))
		d = ImageDraw.Draw(line)
		d.line((ux1 - (ux1 - ux0) * r, uy, ux1, uy), fill=(232, 34, 44, 255), width=4)
		put(img, line.filter(ImageFilter.GaussianBlur(5)), (wx, wy), 0.9)
		put(img, line, (wx, wy))


@lru_cache(maxsize=1)
def intro_texts():
	meta = G["meta"]
	return [(text_img(f"بخش {fa(meta['n'])}", 30, RED), 0), (shadowed(text_img(meta["title"], 52, WHITE), 10, 0.8), 46)]


def step_state(t):
	if t < G["tl"]["start"]:
		return (-1, 0)
	s = current_seg(t)
	return (s["step"], s["done"])


def draw_panel(img, t, px, current, done, p_in, logo_shown=True):
	panel = G["panel"]
	body = panel.body(current, done).copy() if current >= 0 else panel.body(-1, 0).copy()
	# the texts: each slides in from the right and fades in, one after another (the same for every section)
	surf = Image.new("RGBA", body.size, (0, 0, 0, 0))
	for j, (im, y) in enumerate(panel.items):
		q = out3((t - INTRO - 0.35 - j * 0.08) / 0.45)
		put(surf, im, (PANEL_W - 28 - im.width + 30 * (1 - q), y), q)
	q = out3((t - INTRO - 0.35 - len(panel.items) * 0.08) / 0.45)
	if q < 1:
		# the steps come in last, together
		steps = body.crop((0, panel.steps_y - 10, PANEL_W, PANEL_H))
		body.paste((0, 0, 0, 0), (0, panel.steps_y - 10, PANEL_W, PANEL_H))
		base = Image.new("RGBA", body.size, (0, 0, 0, 0))
		ImageDraw.Draw(base).rectangle((0, panel.steps_y - 10, PANEL_W - 5, PANEL_H - 2), fill=(17, 18, 22, 246))
		body.alpha_composite(base)
		put(body, steps, (30 * (1 - q), panel.steps_y - 10), q)
	body.alpha_composite(surf)
	if logo_shown:
		put(body, panel.logo_box(t), ((PANEL_W - Panel.LOGO) / 2, 30))
	put(img, body, (px, PANEL_Y))


@lru_cache(maxsize=64)
def sub_img(text):
	block = text_block(text, 38, FW - 140, WHITE, True, 1.5, "center")
	return shadowed(block, 10, 0.85)


def draw_sub(img, t):
	subs = G["tl"]["subs"]
	for k, (t0, text) in enumerate(subs):
		t1 = subs[k + 1][0] if k + 1 < len(subs) else G["tl"]["t_away"] + 0.3
		if t0 - 0.05 <= t <= t1:
			q = out3((t - t0) / 0.3) * (1 - out3((t - (t1 - 0.22)) / 0.22))
			im = sub_img(text)
			put(img, im, (FX + (FW - im.width) / 2, SUB_Y + 4 + 14 * (1 - q)), q)
			# a short red line above it
			line = Image.new("RGBA", (int(90 * q) + 1, 4), RED + (255,))
			put(img, line, (FX + FW / 2 - line.width / 2, SUB_Y - 6), q)


# ---------------------------------------------------------------- sound and the file

def sound(tl, path):
	sys.path.insert(0, os.path.join(HERE, "..", "video"))
	sys.path.insert(0, os.path.join(HERE, "..", "intro"))
	import audio as A
	import audio_intro as AI
	SR = A.SR
	dur = tl["total"]
	buf, _ = A.music(dur, 999, 999)
	buf *= 0.32
	def add(sig, at, gain, pan=0.0):
		A.add(buf, sig, at, gain, pan)
	add(A.whoosh(0.8), INTRO - 0.1, 0.18, 0.3)
	add(AI.chime(1174.7) if hasattr(AI, "chime") else A.pop(), 1.6, 0.18)
	add(A.whoosh(0.7), tl["t_out"] - 0.1, 0.15, 0.4)
	add(A.whoosh(0.8), tl["t_away"] - 0.05, 0.15, -0.4)
	add(AI.chime(880.0) if hasattr(AI, "chime") else A.pop(), tl["t_end"] + 0.5, 0.16)
	key = A.key()
	for t, kind in tl["sounds"]:
		if kind == "click":
			add(A.click(), t, 0.28)
		elif kind == "key":
			add(key, t, 0.07, (hash(t) % 7 - 3) / 20)
		elif kind == "tick":
			add(A.pop(), t, 0.16)
	n = len(buf)
	buf[: int(0.05 * SR)] *= np.linspace(0, 1, int(0.05 * SR))[:, None]
	fade = int(0.25 * SR)
	buf[-fade:] *= np.linspace(1, 0, fade)[:, None]
	buf = np.tanh(buf * 1.1) / np.tanh(1.1)
	buf /= max(1e-9, np.abs(buf).max()) / 0.85
	import wave
	with wave.open(path, "wb") as w:
		w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
		w.writeframes((buf * 32767).astype("<i2").tobytes())


def _frame(i):
	return render(i).tobytes()


def main():
	n, folder, out = int(sys.argv[1]), sys.argv[2], sys.argv[3]
	tl = setup(n, folder)
	frames = int(tl["total"] * FPS)
	only = os.environ.get("FRAMES")
	if only:
		for i in [int(x) for x in only.split(",")]:
			render(i).save(os.path.join(folder, f"frame_{i:05d}.png"))
		print("frames saved")
		return
	wav = out[:-4] + ".wav"
	sound(tl, wav)
	ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
		"-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
		"-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
	with Pool(4) as pool:
		for k, b in enumerate(pool.imap(_frame, range(frames), chunksize=6)):
			ff.stdin.write(b)
			if k % 300 == 0:
				print(f"frame {k}/{frames}", flush=True)
	ff.stdin.close()
	ff.wait()
	print("done", out, round(tl["total"], 1), "s")


if __name__ == "__main__":
	main()
