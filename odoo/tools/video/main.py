"""The sample video: ERP-VERON's Iranian accounting, about a minute, 1080p"""
import json
import math
import os
import subprocess
import sys
from functools import lru_cache
from multiprocessing import Pool

from PIL import Image, ImageDraw

import audio
import fx
from fx import ACCENT, DEEP, FPS, H, W, clamp, fa, in_out, out_back, out_cubic, paste_alpha, text_image, window

SHOTS = sys.argv[1] if len(sys.argv) > 1 else "shots6"
BOXES = {s["name"]: s["boxes"] for s in json.load(open(os.path.join(SHOTS, "shots.json")))}


@lru_cache(maxsize=5)
def frame_of(name, kind):
	return fx.Frame(os.path.join(SHOTS, name + ".png"), kind)


def box(shot, key):
	return BOXES[shot][key]


def center(b):
	return b[0] + b[2] / 2, b[1] + b[3] / 2


# --- scenes

class Scene:
	duration = 3.0
	dark = False

	def events(self):
		return []


class Screen(Scene):
	"""A screen of the program: shots in turn, a camera, a cursor, clicks, spotlights, lenses, captions"""

	def __init__(self, duration, shots, cam, kind="app", cursor=None, clicks=(), spots=(), lenses=(), captions=(), keys=()):
		self.duration, self.shots, self.cam, self.kind = duration, shots, cam, kind
		self.cursor, self.clicks, self.spots, self.lenses, self.captions, self.keys = cursor, clicks, spots, lenses, captions, keys

	def shot_at(self, t):
		name = self.shots[0][1]
		for t0, n in self.shots:
			if t >= t0:
				name = n
		return name

	def render(self, t):
		base = fx.living_bg(t, dark=False)
		frame = frame_of(self.shot_at(t), self.kind)
		cx, cy, z = fx.track(self.cam, t)
		cam = fx.Camera(frame, cx, cy, z)
		cam.render(base)
		for t0, t1, b in self.spots:
			k = window(t, t0, t1, 0.35)
			if k > 0:
				fx.spotlight(base, cam.out_box(b, 8), k)
		for t0, t1, (x, y), off, zoom in self.lenses:
			k = clamp((t - t0) / 0.45) if t <= t1 - 0.3 else clamp((t1 - t) / 0.3)
			if t0 <= t <= t1:
				ox, oy = cam.out(x, y)
				at = (clamp(ox + off[0], 220, W - 220), clamp(oy + off[1], 220, H - 220))
				cam.lens(base, x, y, at, 175, zoom, k)
		if self.cursor:
			x, y = fx.track(self.cursor, t, ease=in_out)
			ox, oy = cam.out(x, y)
			press = 0.0
			for c in self.clicks:
				if c - 0.08 <= t <= c + 0.12:
					press = 1 - abs(t - c) / 0.12
				fx.ripple(base, ox, oy, (t - c) / 0.5)
			appear = clamp((t - self.cursor[0][0] + 0.2) / 0.3)
			if appear > 0:
				fx.draw_cursor(base, ox, oy, clamp(press))
		for t0, t1, title, sub in self.captions:
			k = window(t, t0, t1, 0.45)
			fx.draw_caption(base, title, sub, k)
		return base

	def events(self):
		ev = [(c, "click") for c in self.clicks]
		ev += [(k, "key") for k in self.keys]
		ev += [(t0 + 0.05, "pop") for t0, *_ in self.lenses]
		return ev


class Card(Scene):
	"""A chapter: its number, a line growing, the words rising one after the other"""
	dark = True

	def __init__(self, number, title, sub, duration=2.4):
		self.number, self.title, self.sub, self.duration = number, title, sub, duration

	def render(self, t):
		base = fx.living_bg(t + 3)
		num = big_text("بخش " + fa(f"{self.number:02d}"), 44, ACCENT + (255,))
		k = out_cubic(t / 0.6)
		paste_alpha(base, num, (W / 2 + 300 - num.width + 40 * (1 - k), H / 2 - 170), k)
		title = big_text(self.title, 108, (255, 255, 255, 255), True)
		k1 = out_cubic((t - 0.15) / 0.6)
		paste_alpha(base, title, (W / 2 + 300 - title.width, H / 2 - 95 + 50 * (1 - k1)), k1)
		line_w = 260 * out_cubic((t - 0.35) / 0.6)
		if line_w > 1:
			bar = Image.new("RGBA", (int(line_w), 8), ACCENT + (255,))
			paste_alpha(base, bar, (W / 2 + 300 - line_w, H / 2 + 60))
		sub = big_text(self.sub, 54, (225, 220, 240, 255), False)
		k2 = out_cubic((t - 0.45) / 0.6)
		paste_alpha(base, sub, (W / 2 + 300 - sub.width, H / 2 + 95 + 40 * (1 - k2)), k2)
		return base


@lru_cache(None)
def big_text(text, size, color, shadow=False):
	return text_image(text, size, color, bold=size > 60, rtl=True, shadow=shadow)


class Intro(Scene):
	dark = True
	duration = 4.8

	def render(self, t):
		base = fx.living_bg(t)
		k = out_back((t - 0.5) / 0.8, 1.6)
		if k > 0:
			size = int(240 * max(0.01, k))
			mark = fx.logo_mark(240).resize((size, size), Image.LANCZOS)
			glow = fx.blob(320, ACCENT, 0.35 * clamp((t - 0.6) / 0.6))
			paste_alpha(base, glow, (W / 2 - 320, H / 2 - 150 - 320))
			paste_alpha(base, mark, (W / 2 - size / 2, H / 2 - 150 - size / 2), clamp((t - 0.5) / 0.3))
			# light sweeping over the mark
			s = (t - 1.6) / 0.6
			if 0 < s < 1:
				sweep = Image.new("RGBA", (size, size), (0, 0, 0, 0))
				d = ImageDraw.Draw(sweep)
				x = -size + 2 * size * s
				d.polygon([(x, 0), (x + 60, 0), (x + 60 + size * 0.5, size), (x + size * 0.5, size)], fill=(255, 255, 255, 90))
				mask = fx.logo_mark(240).resize((size, size)).split()[3]
				sweep.putalpha(Image.composite(sweep.split()[3], Image.new("L", sweep.size, 0), mask))
				paste_alpha(base, sweep, (W / 2 - size / 2, H / 2 - 150 - size / 2))
		wm = fx.wordmark(110)
		k2 = out_cubic((t - 1.1) / 0.7)
		paste_alpha(base, wm, (W / 2 - wm.width / 2, H / 2 + 20 + 40 * (1 - k2)), k2)
		tag = big_text("نرم‌افزار یکپارچه مدیریت کسب‌وکار ایرانی", 50, (220, 214, 240, 255))
		k3 = out_cubic((t - 1.7) / 0.7)
		paste_alpha(base, tag, (W / 2 - tag.width / 2, H / 2 + 170 + 30 * (1 - k3)), k3)
		return base

	def events(self):
		return [(0.0, "riser"), (0.5, "impact")]


class Features(Scene):
	dark = True
	duration = 6.4
	ITEMS = ["تاریخ شمسی و تقویم رسمی ایران", "کدینگ استاندارد حساب‌های ایران", "ارسال صورتحساب به سامانه مؤدیان",
		"چک صیادی و خزانه‌داری", "دفاتر قانونی و گزارش‌های فارسی", "فاکتور رسمی و پیش‌فاکتور"]

	def render(self, t):
		base = fx.living_bg(t + 7)
		title = big_text("حسابداری کامل، به زبان کسب‌وکار ایرانی", 74, (255, 255, 255, 255), True)
		k = out_cubic(t / 0.6)
		paste_alpha(base, title, (W / 2 - title.width / 2, 170 + 30 * (1 - k)), k)
		for i, item in enumerate(self.ITEMS):
			col, row = i % 2, i // 2
			x_right = W / 2 + 700 - col * 720
			y = 400 + row * 160
			start = 0.6 + i * 0.32
			k = out_cubic((t - start) / 0.5)
			if k <= 0:
				continue
			card = item_card(item)
			paste_alpha(base, card, (x_right - card.width + 60 * (1 - k), y), k)
			kc = out_back((t - start - 0.15) / 0.4)
			if kc > 0:
				r = int(30 * kc)
				c = Image.new("RGBA", (2 * r + 2, 2 * r + 2), (0, 0, 0, 0))
				d = ImageDraw.Draw(c)
				d.ellipse((0, 0, 2 * r, 2 * r), fill=ACCENT + (255,))
				if kc > 0.6:
					d.line([(r * 0.5, r * 1.0), (r * 0.85, r * 1.35), (r * 1.5, r * 0.65)], fill=(255, 255, 255, 255), width=max(2, r // 5))
				paste_alpha(base, c, (x_right - 62 - r + 60 * (1 - k), y + 48 - r))
		return base

	def events(self):
		return [(0.6 + i * 0.32 + 0.15, "pop") for i in range(len(self.ITEMS))]


@lru_cache(None)
def item_card(text):
	t = text_image(text, 38, (255, 255, 255))
	w, h = 680, 96
	im = fx.rounded((w, h), 24, (255, 255, 255, 30))
	ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), 24, outline=(255, 255, 255, 60), width=2)
	im.alpha_composite(t, (w - 110 - t.width, (h - t.height) // 2))
	return im


class Outro(Scene):
	dark = True
	duration = 5.2

	def render(self, t):
		base = fx.living_bg(t + 11)
		k = out_back(t / 0.8, 1.4)
		size = int(170 * max(0.01, k))
		mark = fx.logo_mark(240).resize((size, size), Image.LANCZOS)
		paste_alpha(base, mark, (W / 2 - size / 2, 250 - size / 2 + 40), clamp(t / 0.3))
		wm = fx.wordmark(100)
		k1 = out_cubic((t - 0.4) / 0.6)
		paste_alpha(base, wm, (W / 2 - wm.width / 2, 400 + 30 * (1 - k1)), k1)
		line = big_text("حسابداری، فروش، انبار، حقوق و دستمزد؛ همه در یک سامانه", 46, (225, 220, 240, 255))
		k2 = out_cubic((t - 0.8) / 0.6)
		paste_alpha(base, line, (W / 2 - line.width / 2, 560 + 30 * (1 - k2)), k2)
		btn = demo_button()
		k3 = out_back((t - 1.3) / 0.6)
		if k3 > 0:
			pulse = 1 + 0.03 * math.sin(max(0, t - 2) * 5)
			sc = max(0.01, k3) * pulse
			b = btn.resize((int(btn.width * sc), int(btn.height * sc)), Image.LANCZOS)
			paste_alpha(base, b, (W / 2 - b.width / 2, 720 - b.height / 2 + 30), clamp((t - 1.3) / 0.3))
		return base

	def events(self):
		return [(1.4, "pop")]


@lru_cache(None)
def demo_button():
	t = text_image("درخواست دموی رایگان", 50, (255, 255, 255))
	w, h = t.width + 140, 120
	im = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
	im.alpha_composite(fx.soft_shadow((w, h), 60, 30, 14, alpha=120, offset=(0, 10)))
	body = fx.rounded((w, h), 60, ACCENT + (255,))
	body.alpha_composite(t, ((w - t.width) // 2, (h - t.height) // 2))
	im.alpha_composite(body, (30, 30))
	return im


# --- the storyboard

def storyboard():
	b = BOXES
	invoice_cam_start = (1700, 150, 1.6)
	scenes = [
		(Intro(), "fade"),
		(Card(1, "صدور فاکتور فروش", "در چند ثانیه، با مالیات و شماره‌گذاری خودکار"), "wipe"),
		(Screen(4.2, [(0, "dash")], [(0, (960, 540, 1.0)), (0.4, (960, 540, 1.0)), (2.4, (1430, 250, 1.45)), (4.2, (1440, 255, 1.5))],
			spots=[(1.9, 3.9, box("dash", "sales"))],
			captions=[(0.7, 4.0, "داشبورد مالی", "فروش، خرید، بانک و چک‌ها در یک نگاه")]), "fade"),
		(Screen(4.0, [(0, "list")], [(0, (960, 540, 1.0)), (0.2, (960, 540, 1.0)), (2.0, (1250, 330, 1.25)), (2.8, (1250, 330, 1.25)), (3.9, invoice_cam_start)],
			cursor=[(1.9, (1300, 640)), (3.1, center(box("list", "new")))], clicks=[3.35],
			captions=[(0.4, 3.0, "فهرست فاکتورها", "تاریخ شمسی، مبلغ ریالی و وضعیت سامانه مؤدیان")]), "fade"),
		(invoice_scene(invoice_cam_start), "fade"),
		(Card(2, "صورتحساب رسمی", "مطابق نمونه سازمان امور مالیاتی"), "wipe"),
		(Screen(7.4, [(0, "official")], [(0, (960, 240, 1.0)), (0.6, (960, 240, 1.0)), (1.6, (1250, 120, 1.5)), (2.8, (1250, 125, 1.5)),
			(3.8, (1150, 340, 1.35)), (4.8, (1150, 345, 1.35)), (5.6, (1500, 426, 2.1)), (7.4, (1490, 426, 2.15))], kind="paper",
			spots=[(1.6, 3.0, [81, 78, 1757, 170]), (3.9, 5.0, box("official", "lines")), (5.7, 7.3, [1265, 410, 575, 34])],
			captions=[(0.6, 3.4, "صورتحساب فروش کالا و خدمات", "مشخصات فروشنده و خریدار، کامل و خودکار"),
				(3.7, 5.1, "تخفیف، مالیات و جمع کل", "برای هر ردیف، جدا و دقیق"),
				(5.5, 7.3, "مبلغ به حروف", "بدون نیاز به نوشتن دستی")]), "fade"),
		(Card(3, "مدیریت چک", "از دریافت تا وصول، با یادآوری سررسید"), "wipe"),
		(Screen(3.8, [(0, "cheques")], [(0, (960, 540, 1.0)), (0.2, (960, 540, 1.0)), (1.2, (1480, 260, 1.45)), (3.8, (1470, 262, 1.5))],
			cursor=[(2.3, (1300, 420)), (3.2, (1700, 165))], clicks=[3.45],
			spots=[(1.2, 2.6, [1744, 106, 136, 280])],
			captions=[(0.4, 3.5, "سررسید چک‌ها به تاریخ شمسی", "یادآوری خودکار پیش از سررسید")]), "fade"),
		(Screen(5.8, [(0, "cheque")], [(0, (1470, 262, 1.5)), (0.2, (1470, 262, 1.5)), (1.2, (1280, 260, 1.45)), (5.8, (1280, 262, 1.5))],
			spots=[(0.9, 2.3, box("cheque", "status"))],
			lenses=[(2.6, 4.6, (1105, 236), (-60, 300), 1.7)],
			captions=[(0.8, 2.5, "وضعیت چک", "نزد صندوق، در جریان وصول، وصول‌شده یا برگشتی"),
				(2.7, 5.6, "شناسه صیاد و مبلغ به حروف", "ثبت کامل مشخصات هر چک")]), "fade"),
		(Card(4, "دفاتر قانونی", "تراز آزمایشی، دفتر روزنامه و دفتر کل"), "wipe"),
		(Screen(5.2, [(0, "trial")], [(0, (960, 160, 1.0)), (0.4, (960, 160, 1.0)), (1.6, (1100, 190, 1.35)), (5.2, (1100, 192, 1.4))], kind="paper",
			spots=[(2.2, 4.8, [81, 283, 1757, 32])],
			captions=[(0.5, 4.9, "تراز آزمایشی چهارستونی", "گردش و مانده هر حساب، آماده چاپ")]), "fade"),
		(Features(), "wipe"),
		(Outro(), "fade"),
	]
	return scenes


def invoice_scene(start):
	b = BOXES
	cust = center(box("f0", "cust"))
	cust = (cust[0] + 150, cust[1])
	opt = center(box("fcdd", "opt"))
	addline = center(box("f0", "addline"))
	opt_a = center(box("ladd", "opt"))
	qty_a = center(box("lasel", "qty"))
	addline_b = (addline[0], addline[1] + 40)
	opt_b = center(box("lbdd", "opt"))
	qty_b = center(box("lbsel", "qty"))
	post = center(box("f0", "post"))
	price_tax = [box("lasel", "tax")[0], box("lasel", "row")[1], box("lasel", "price")[0] + box("lasel", "price")[2] - box("lasel", "tax")[0], box("lasel", "row")[3]]
	shots = [(0, "f0"), (1.6, "fc1"), (1.8, "fc2"), (2.0, "fc3"), (2.2, "fc4"), (2.5, "fcdd"), (3.2, "fcsel"),
		(4.5, "la0"), (4.7, "lat1"), (4.9, "lat2"), (5.2, "ladd"), (5.8, "lasel"), (6.9, "laqty"),
		(7.6, "lb0"), (7.75, "lbt1"), (7.9, "lbt2"), (8.05, "lbt3"), (8.2, "lbt4"), (8.4, "lbdd"), (9.0, "lbsel"), (9.6, "lbqty"),
		(10.0, "flines"), (13.9, "fposted")]
	cam = [(0, start), (0.3, start), (1.2, (1450, 300, 1.9)), (3.5, (1450, 300, 1.9)), (4.3, (1450, 500, 1.7)), (9.8, (1430, 505, 1.7)),
		(10.6, (900, 668, 1.9)), (12.7, (900, 668, 1.9)), (13.5, (1650, 230, 1.6)), (14.0, (1650, 230, 1.6)), (14.7, (1550, 320, 1.5)),
		(17.5, (1550, 322, 1.55))]
	cursor = [(0.3, (1250, 420)), (1.3, cust), (2.6, cust), (3.0, opt), (3.6, opt), (4.3, addline), (5.3, addline), (5.6, opt_a),
		(6.2, opt_a), (6.6, qty_a), (7.0, qty_a), (7.4, addline_b), (8.4, addline_b), (8.8, opt_b), (9.0, opt_b), (9.4, qty_b),
		(10.2, qty_b), (11.0, (1000, 760)), (13.0, (1100, 400)), (13.6, post), (16.0, post), (17.0, (1500, 600))]
	clicks = [1.4, 3.1, 4.4, 5.7, 6.7, 7.5, 8.9, 9.5, 13.75]
	keys = [1.6, 1.8, 2.0, 2.2, 4.7, 4.9, 6.9, 7.75, 7.9, 8.05, 8.2, 9.6]
	return Screen(17.5, shots, cam, cursor=cursor, clicks=clicks, keys=keys,
		spots=[(5.9, 7.1, price_tax), (10.8, 12.7, [680, 628, 400, 84]), (14.6, 15.8, [1560, 232, 345, 70]), (15.9, 17.4, [1630, 388, 278, 34])],
		lenses=[(11.3, 12.7, (802, 668), (380, -230), 2.0)],
		captions=[(1.4, 4.3, "انتخاب سریع مشتری", "نشانی و شماره اقتصادی خودکار پر می‌شود"),
			(5.9, 9.8, "قیمت و مالیات از روی کالا", "فقط تعداد را وارد کنید"),
			(10.9, 13.2, "محاسبه خودکار مالیات بر ارزش افزوده", "جمع کل به ریال، بدون خطای دستی"),
			(14.5, 17.3, "شماره‌گذاری خودکار", "شماره فاکتور و شماره سند در سال شمسی")])


# --- the timeline

OVERLAP = 0.5


def timeline():
	out, t = [], 0.0
	for scene, trans in storyboard():
		out.append((t, scene, trans))
		t += scene.duration - OVERLAP
	return out, t + OVERLAP


TL, TOTAL = timeline()


def wipe_panel(base, k):
	"""A band of the brand's colors crossing from right to left"""
	x = W * 1.3 - (W * 1.9) * in_out(k)
	band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
	d = ImageDraw.Draw(band)
	d.polygon([(x, 0), (x + 700, 0), (x + 500, H), (x - 200, H)], fill=(126, 72, 196, 255))
	d.polygon([(x + 640, 0), (x + 760, 0), (x + 560, H), (x + 440, H)], fill=ACCENT + (255,))
	base.alpha_composite(band)


def render_frame(n):
	t = n / FPS
	active = [(t0, s, tr) for t0, s, tr in TL if t0 <= t < t0 + s.duration]
	if len(active) == 1:
		t0, s, _ = active[0]
		img = s.render(t - t0)
	else:
		(ta, a, _), (tb, b, trans) = active[-2], active[-1]
		k = clamp((t - tb) / OVERLAP)
		if trans == "wipe":
			img = (a.render(t - ta) if k < 0.5 else b.render(t - tb))
			wipe_panel(img, k)
		else:
			A = a.render(t - ta)
			B = b.render(t - tb)
			sc = 1 + 0.04 * (1 - out_cubic(k))
			if sc > 1.001:
				Bs = B.resize((int(W * sc), int(H * sc)), Image.BILINEAR)
				B = Bs.crop(((Bs.width - W) // 2, (Bs.height - H) // 2, (Bs.width - W) // 2 + W, (Bs.height - H) // 2 + H))
			img = Image.blend(A, B, in_out(k))
	# the progress of the video, and the brand while the program is shown
	bar = Image.new("RGBA", (int(W * t / TOTAL) + 1, 5), ACCENT + (230,))
	img.alpha_composite(bar, (0, H - 5))
	if any(isinstance(s, Screen) for _, s, _ in active):
		img.alpha_composite(brand_bug(), (36, H - 86))
	return img.convert("RGB").tobytes()


@lru_cache(None)
def brand_bug():
	mark = fx.logo_mark(44)
	wm = text_image("ERP-VERON", 30, (40, 30, 70), rtl=False)
	im = Image.new("RGBA", (mark.width + wm.width + 14, 50), (0, 0, 0, 0))
	im.alpha_composite(mark, (0, 3))
	im.alpha_composite(wm, (mark.width + 10, (50 - wm.height) // 2))
	im.putalpha(im.split()[3].point(lambda v: int(v * 0.85)))
	return im


def sound_events():
	ev = []
	for t0, s, trans in TL:
		ev += [(t0 + e, k) for e, k in s.events()]
		if t0 > 0:
			ev.append((t0 - 0.1, "whoosh"))
	return ev


if __name__ == "__main__":
	os.makedirs("build", exist_ok=True)
	only = os.environ.get("FRAMES")
	if only:
		for n in map(int, only.split(",")):
			Image.frombytes("RGB", (W, H), render_frame(n)).save(f"build/frame_{n:05d}.jpg", quality=88)
		sys.exit()
	total = int(TOTAL * FPS)
	print("frames", total, "seconds", round(TOTAL, 1), flush=True)
	audio.build(TOTAL, sound_events(), "build/sound.wav", beat_from=TL[1][0], beat_to=TL[-1][0] + 0.5)
	ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
		"-i", "-", "-i", "build/sound.wav", "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
		"-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", "build/erp-veron-accounting.mp4"], stdin=subprocess.PIPE)
	with Pool(4) as pool:
		for i, data in enumerate(pool.imap(render_frame, range(total), chunksize=12)):
			ff.stdin.write(data)
			if i % 150 == 0:
				print("frame", i, flush=True)
	ff.stdin.close()
	ff.wait()
	print("done")
