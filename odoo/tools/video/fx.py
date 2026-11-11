"""Building blocks of the video: easing, framed screens, camera, cursor, spotlight, lens, captions, cards"""
import json
import math
import os
from functools import lru_cache

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 30
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addons", "veron_fonts_iran", "static", "fonts", "")
ACCENT = (31, 181, 168)       # teal
BRAND = (113, 75, 160)        # purple
DEEP = (30, 24, 58)


def font(size, bold=True):
	return ImageFont.truetype(FONTS + ("Vazirmatn-Bold.ttf" if bold else "Vazirmatn-Regular.ttf"), size)


def fa(text):
	return str(text).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


# --- easing and tracks

def clamp(x, a=0.0, b=1.0):
	return max(a, min(b, x))


def in_out(x):
	x = clamp(x)
	return 4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def out_cubic(x):
	return 1 - (1 - clamp(x)) ** 3


def out_back(x, s=1.7):
	x = clamp(x)
	return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


def track(keys, t, ease=in_out):
	"""Values of keyframes [(t, (a, b, ...))] at t, eased between each two"""
	if t <= keys[0][0]:
		return keys[0][1]
	for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
		if t <= t1:
			k = ease((t - t0) / (t1 - t0)) if t1 > t0 else 1
			return tuple(a + (b - a) * k for a, b in zip(v0, v1))
	return keys[-1][1]


def window(t, t0, t1, fade=0.3):
	"""0..1: in from t0, out at t1"""
	if t < t0 or t > t1:
		return 0.0
	return min(out_cubic((t - t0) / fade), out_cubic((t1 - t) / fade))


# --- text

def text_image(text, size, color=(255, 255, 255), bold=True, rtl=True, shadow=False):
	f = font(size, bold)
	d = "rtl" if rtl else "ltr"
	box = f.getbbox(text, direction=d, language="fa" if rtl else None)
	w, h = box[2] - box[0] + 8, box[3] - box[1] + 12
	im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
	ImageDraw.Draw(im).text((4 - box[0], 6 - box[1]), text, font=f, fill=color, direction=d, language="fa" if rtl else None)
	if shadow:
		sh = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
		a = im.split()[3].point(lambda v: v * 0.5)
		sh.paste((0, 0, 0, 255), (20, 24), a)
		sh = sh.filter(ImageFilter.GaussianBlur(9))
		sh.alpha_composite(im, (20, 20))
		return sh
	return im


def rounded(size, radius, fill):
	im = Image.new("RGBA", size, (0, 0, 0, 0))
	ImageDraw.Draw(im).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=fill)
	return im


def soft_shadow(size, radius, margin, blur, alpha=110, offset=(0, 18)):
	sh = Image.new("RGBA", (size[0] + 2 * margin, size[1] + 2 * margin), (0, 0, 0, 0))
	ImageDraw.Draw(sh).rounded_rectangle((margin + offset[0], margin + offset[1], margin + size[0] + offset[0],
		margin + size[1] + offset[1]), radius, fill=(10, 8, 30, alpha))
	return sh.filter(ImageFilter.GaussianBlur(blur))


def paste_alpha(base, im, xy, alpha=1.0):
	if alpha <= 0:
		return
	if alpha < 1:
		im = im.copy()
		im.putalpha(im.split()[3].point(lambda v: int(v * alpha)))
	x, y = int(round(xy[0])), int(round(xy[1]))
	# clip
	if x >= base.width or y >= base.height or x + im.width <= 0 or y + im.height <= 0:
		return
	cx0, cy0 = max(0, -x), max(0, -y)
	cx1, cy1 = min(im.width, base.width - x), min(im.height, base.height - y)
	base.alpha_composite(im.crop((cx0, cy0, cx1, cy1)), (x + cx0, y + cy0))


# --- backgrounds

def gradient(c0, c1, c2=None, angle=0.35):
	y, x = np.mgrid[0:H, 0:W].astype(np.float32)
	k = (x / W * math.cos(angle) + y / H * math.sin(angle)) / (math.cos(angle) + math.sin(angle))
	c0, c1 = np.array(c0, np.float32), np.array(c1, np.float32)
	if c2 is None:
		img = c0 + (c1 - c0) * k[..., None]
	else:
		c2 = np.array(c2, np.float32)
		k2 = k[..., None]
		img = np.where(k2 < 0.5, c0 + (c1 - c0) * (k2 * 2), c1 + (c2 - c1) * (k2 * 2 - 1))
	noise = np.random.default_rng(1).normal(0, 1.6, (H, W, 1)).astype(np.float32)
	return Image.fromarray(np.clip(img + noise, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


@lru_cache(None)
def blob(radius, color, alpha):
	size = radius * 2
	y, x = np.mgrid[0:size, 0:size].astype(np.float32)
	d = np.sqrt((x - radius) ** 2 + (y - radius) ** 2) / radius
	a = np.clip(1 - d, 0, 1) ** 2 * alpha
	arr = np.zeros((size, size, 4), np.uint8)
	arr[..., :3] = color
	arr[..., 3] = (a * 255).astype(np.uint8)
	return Image.fromarray(arr, "RGBA")


@lru_cache(None)
def stage_bg():
	return gradient((236, 233, 246), (246, 245, 250), (226, 242, 241))


@lru_cache(None)
def dark_bg():
	return gradient((24, 18, 52), (62, 38, 108), (14, 84, 92), angle=0.5)


def living_bg(t, dark=True):
	"""The background with soft lights drifting"""
	im = (dark_bg() if dark else stage_bg()).copy()
	lights = [(520, ACCENT, 0.35, 0.07, 0.0), (640, (150, 90, 220), 0.32, 0.05, 2.0), (420, (240, 120, 170), 0.18, 0.09, 4.0)] \
		if dark else [(600, (180, 160, 240), 0.35, 0.05, 0.0), (520, (150, 225, 215), 0.35, 0.06, 2.5)]
	for i, (r, c, a, sp, ph) in enumerate(lights):
		x = W * (0.5 + 0.38 * math.sin(t * sp * 2 * math.pi / 3 + ph + i))
		y = H * (0.5 + 0.30 * math.cos(t * sp * 2 * math.pi / 4 + ph * 1.3))
		paste_alpha(im, blob(r, c, a), (x - r, y - r))
	return im


# --- shots in frames

class Frame:
	"""A screenshot as a browser window (or a page of paper) with its shadow, at two resolutions"""

	TB = 46     # title bar of the window, CSS px
	M = 70      # margin for the shadow

	def __init__(self, path, kind="app", crop=None):
		src = Image.open(path).convert("RGBA")      # 2x
		self.kind = kind
		if kind == "paper":
			if crop is None:
				gray = np.asarray(src.convert("L"))
				ys, xs = np.where(gray < 245)
				pad = 60
				crop = (max(0, xs.min() - pad), max(0, ys.min() - pad), min(src.width, xs.max() + pad), min(src.height, ys.max() + pad))
			src = src.crop(crop)
			self.offset = (crop[0] / 2, crop[1] / 2)    # CSS px of the page cut away
			self.cw, self.ch = src.width / 2, src.height / 2
			top = 0
		else:
			self.offset = (0, 0)
			self.cw, self.ch = src.width / 2, src.height / 2 + self.TB
			top = self.TB
		M = self.M
		self.fw, self.fh = self.cw + 2 * M, self.ch + 2 * M
		big = Image.new("RGBA", (int(self.fw * 2), int(self.fh * 2)), (0, 0, 0, 0))
		sh = soft_shadow((int(self.cw * 2), int(self.ch * 2)), 28, M * 2, 36, alpha=120, offset=(0, 30))
		big.alpha_composite(sh, (0, 0))
		body = Image.new("RGBA", (int(self.cw * 2), int(self.ch * 2)), (255, 255, 255, 255))
		if kind == "app":
			bar = Image.new("RGBA", (body.width, top * 2), (241, 239, 246, 255))
			d = ImageDraw.Draw(bar)
			for i, c in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
				d.ellipse((36 + i * 44, 32, 36 + i * 44 + 26, 58), fill=c)
			d.rounded_rectangle((body.width // 2 - 520, 18, body.width // 2 + 520, 74), 26, fill=(255, 255, 255))
			url = text_image("erp-veron.ir/odoo/accounting", 26, (110, 104, 130), bold=False, rtl=False)
			bar.alpha_composite(url, (body.width // 2 - url.width // 2, 46 - url.height // 2))
			body.alpha_composite(bar, (0, 0))
		body.alpha_composite(src, (0, top * 2))
		mask = Image.new("L", body.size, 0)
		ImageDraw.Draw(mask).rounded_rectangle((0, 0, body.width - 1, body.height - 1), 28 if kind == "app" else 10, fill=255)
		body.putalpha(mask)
		big.alpha_composite(body, (M * 2, M * 2))
		self.l2 = big
		self.l1 = big.resize((int(self.fw), int(self.fh)), Image.LANCZOS)
		self.top = top

	def to_frame(self, x, y):
		"""CSS px of the screenshot (or page) to px of the frame at 1x"""
		return x - self.offset[0] + self.M, y - self.offset[1] + self.top + self.M

	def base_scale(self, fill=0.86):
		return min(W * fill / self.cw, H * fill / self.ch)


class Camera:
	def __init__(self, frame, cx, cy, z):
		self.f = frame
		self.s = frame.base_scale() * z
		fx, fy = frame.to_frame(cx, cy)
		s = self.s
		# keep the screen over the whole picture once it is larger than it
		cw, ch = frame.cw * s, frame.ch * s
		if cw >= W:
			lo, hi = frame.M + W / 2 / s, frame.M + frame.cw - W / 2 / s
			fx = clamp(fx, lo, hi)
		else:
			fx = frame.M + frame.cw / 2 if z <= 1.0001 else fx
		if ch >= H:
			lo, hi = frame.M + H / 2 / s, frame.M + frame.ch - H / 2 / s
			fy = clamp(fy, lo, hi)
		elif z <= 1.0001:
			fy = frame.M + frame.ch / 2
		self.fx, self.fy = fx, fy

	def out(self, x, y):
		"""CSS px of the screenshot to px of the picture"""
		fx, fy = self.f.to_frame(x, y)
		return (fx - self.fx) * self.s + W / 2, (fy - self.fy) * self.s + H / 2

	def out_box(self, b, pad=8):
		x0, y0 = self.out(b[0] - pad, b[1] - pad)
		x1, y1 = self.out(b[0] + b[2] + pad, b[1] + b[3] + pad)
		return x0, y0, x1, y1

	def render(self, base):
		s = self.s
		if s > 1.02:
			src, k = self.f.l2, 2.0
		else:
			src, k = self.f.l1, 1.0
		# picture px -> source px
		a = k / s
		data = (a, 0, (self.fx - W / 2 / s) * k, 0, a, (self.fy - H / 2 / s) * k)
		layer = src.transform((W, H), Image.AFFINE, data, resample=Image.BICUBIC if s > 1.02 else Image.BILINEAR)
		base.alpha_composite(layer)

	def lens(self, base, x, y, at, radius, zoom, appear):
		"""A round magnifier over the point (x, y) of the screen, shown at «at» of the picture"""
		if appear <= 0:
			return
		r = max(4, int(radius * out_back(appear, 1.4)))
		s = self.s * zoom
		fx, fy = self.f.to_frame(x, y)
		a = 2.0 / s
		data = (a, 0, (fx - r / s) * 2, 0, a, (fy - r / s) * 2)
		im = self.f.l2.transform((2 * r, 2 * r), Image.AFFINE, data, resample=Image.BICUBIC)
		bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
		bg.alpha_composite(im)
		mask = Image.new("L", im.size, 0)
		ImageDraw.Draw(mask).ellipse((0, 0, 2 * r - 1, 2 * r - 1), fill=255)
		bg.putalpha(mask)
		cx, cy = at
		paste_alpha(base, blob_shadow(r), (cx - r - 40, cy - r - 40 + 16), min(1, appear * 1.5))
		paste_alpha(base, bg, (cx - r, cy - r), min(1, appear * 1.5))
		ring = Image.new("RGBA", (2 * r + 16, 2 * r + 16), (0, 0, 0, 0))
		d = ImageDraw.Draw(ring)
		d.ellipse((2, 2, 2 * r + 13, 2 * r + 13), outline=ACCENT + (255,), width=5)
		d.ellipse((7, 7, 2 * r + 8, 2 * r + 8), outline=(255, 255, 255, 255), width=4)
		paste_alpha(base, ring, (cx - r - 8, cy - r - 8), min(1, appear * 1.5))


@lru_cache(None)
def blob_shadow(r):
	sh = Image.new("RGBA", (2 * r + 80, 2 * r + 80), (0, 0, 0, 0))
	ImageDraw.Draw(sh).ellipse((40, 40, 40 + 2 * r, 40 + 2 * r), fill=(10, 8, 30, 120))
	return sh.filter(ImageFilter.GaussianBlur(18))


def spotlight(base, box, amount, radius=14):
	"""The rest of the picture dimmed, the box ringed"""
	if amount <= 0:
		return
	x0, y0, x1, y1 = box
	dim = Image.new("RGBA", (W, H), (16, 10, 40, int(150 * amount)))
	hole = Image.new("L", (W, H), 255)
	ImageDraw.Draw(hole).rounded_rectangle((x0, y0, x1, y1), radius, fill=0)
	dim.putalpha(ImageChops.multiply(dim.split()[3], hole))
	base.alpha_composite(dim)
	ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
	d = ImageDraw.Draw(ring)
	grow = 6 * (1 - amount)
	d.rounded_rectangle((x0 - grow, y0 - grow, x1 + grow, y1 + grow), radius, outline=ACCENT + (int(255 * amount),), width=4)
	base.alpha_composite(ring)


# --- cursor

@lru_cache(None)
def cursor_image():
	k = 4
	pts = [(0, 0), (0, 34), (9, 26), (15, 40), (21, 37), (15, 24), (27, 24)]
	size = (34 * k, 46 * k)
	im = Image.new("RGBA", size, (0, 0, 0, 0))
	d = ImageDraw.Draw(im)
	P = [(4 * k + x * k, 3 * k + y * k) for x, y in pts]
	d.polygon(P, fill=(255, 255, 255, 255), outline=(20, 20, 30, 255), width=2 * k)
	im = im.resize((34, 46), Image.LANCZOS)
	sh = Image.new("RGBA", (34 + 20, 46 + 20), (0, 0, 0, 0))
	sh.paste((0, 0, 0, 255), (12, 14), im.split()[3].point(lambda v: v * 0.45))
	sh = sh.filter(ImageFilter.GaussianBlur(3))
	sh.alpha_composite(im, (10, 10))
	return sh


def draw_cursor(base, x, y, press=0.0, scale=1.0):
	im = cursor_image()
	sc = scale * (1 - 0.15 * press)
	if abs(sc - 1) > 0.01:
		im = im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS)
	paste_alpha(base, im, (x - 14 * sc, y - 13 * sc))


def ripple(base, x, y, k):
	"""A ring spreading from a click, k: 0..1"""
	if not 0 <= k <= 1:
		return
	r = 10 + 46 * out_cubic(k)
	a = int(200 * (1 - k))
	im = Image.new("RGBA", (int(2 * r + 12), int(2 * r + 12)), (0, 0, 0, 0))
	d = ImageDraw.Draw(im)
	d.ellipse((6, 6, 6 + 2 * r, 6 + 2 * r), fill=ACCENT + (int(a * 0.25),), outline=ACCENT + (a,), width=4)
	paste_alpha(base, im, (x - r - 6, y - r - 6))


# --- captions

@lru_cache(None)
def caption_image(title, sub=""):
	t = text_image(title, 46, DEEP)
	s = text_image(sub, 30, (95, 88, 120), bold=False) if sub else None
	w = max(t.width, s.width if s else 0) + 110
	h = t.height + (s.height + 6 if s else 0) + 48
	im = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
	im.alpha_composite(soft_shadow((w, h), 22, 30, 16, alpha=80, offset=(0, 10)), (0, 0))
	panel = rounded((w, h), 22, (255, 255, 255, 240))
	ImageDraw.Draw(panel).rounded_rectangle((w - 16, 18, w - 8, h - 18), 4, fill=ACCENT + (255,))
	panel.alpha_composite(t, (w - 40 - t.width, 22))
	if s:
		panel.alpha_composite(s, (w - 40 - s.width, 22 + t.height + 4))
	im.alpha_composite(panel, (30, 30))
	return im


def draw_caption(base, title, sub, k):
	"""Bottom right, sliding in from the right (the start of a Persian line)"""
	if k <= 0:
		return
	im = caption_image(title, sub)
	x = W - im.width - 50 + 80 * (1 - k)
	paste_alpha(base, im, (x, H - im.height - 50), k)


# --- the brand

@lru_cache(None)
def logo_mark(size=180):
	k = 4
	S = size * k
	im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
	y, x = np.mgrid[0:S, 0:S].astype(np.float32)
	g = ((x + y) / (2 * S))[..., None]
	c0, c1 = np.array((126, 72, 196), np.float32), np.array(ACCENT, np.float32)
	arr = np.zeros((S, S, 4), np.uint8)
	arr[..., :3] = (c0 + (c1 - c0) * g).astype(np.uint8)
	arr[..., 3] = 255
	grad = Image.fromarray(arr, "RGBA")
	mask = Image.new("L", (S, S), 0)
	ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), int(S * 0.24), fill=255)
	im.paste(grad, (0, 0), mask)
	d = ImageDraw.Draw(im)
	w = int(S * 0.11)
	d.line([(S * 0.26, S * 0.28), (S * 0.5, S * 0.74), (S * 0.74, S * 0.28)], fill=(255, 255, 255, 255), width=w, joint="curve")
	for px, py in [(S * 0.26, S * 0.28), (S * 0.74, S * 0.28), (S * 0.5, S * 0.74)]:
		d.ellipse((px - w / 2, py - w / 2, px + w / 2, py + w / 2), fill=(255, 255, 255, 255))
	d.ellipse((S * 0.70, S * 0.64, S * 0.80, S * 0.74), fill=(255, 255, 255, 230))
	return im.resize((size, size), Image.LANCZOS)


@lru_cache(None)
def wordmark(size=96):
	return text_image("ERP-VERON", size, (255, 255, 255), rtl=False)
