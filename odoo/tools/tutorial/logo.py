"""The network V of the logo in a black square with sharp corners: its lines and nodes with a soft red glow, the
nodes lighting up one by one when it first appears, and now and then a random node that flares"""
import json
import math
import os
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
GRAPH = json.load(open(os.path.join(HERE, "..", "intro", "net_graph.json")))
NODES, EDGES = GRAPH["nodes"], GRAPH["edges"]
# the V's own box in the traced design, and the square around it
VX0, VX1, VY0, VY1 = 323, 700, 297, 648
CXV, CYV = (VX0 + VX1) / 2, (VY0 + VY1) / 2
RED = (255, 46, 52)


def _order():
	"""the order the nodes light up in: from the tip of the V upward"""
	return sorted(range(len(NODES)), key=lambda i: -NODES[i][1])


ORDER = _order()
RANK = {n: k for k, n in enumerate(ORDER)}


def _place(size):
	"""node positions inside a square of side size, the V filling 62 % of it"""
	k = size * 0.62 / max(VX1 - VX0, VY1 - VY0)
	return [(size / 2 + (x - CXV) * k, size / 2 + (y - CYV) * k + size * 0.01) for x, y in NODES], k


def render(size, built=1.0, glow=1.0):
	"""the logo at size x size; built 0..1 lights the nodes and lines up from the tip"""
	S = 3  # drawn larger, then reduced: smooth lines
	pts, k = _place(size * S)
	n_on = built * len(NODES)
	lines = Image.new("L", (size * S, size * S), 0)
	dots = Image.new("L", (size * S, size * S), 0)
	dl, dd = ImageDraw.Draw(lines), ImageDraw.Draw(dots)
	lw = max(1, round(size * S * 0.0034))
	for i, j in EDGES:
		a = min(1, max(0, n_on - max(RANK[i], RANK[j])))
		if a > 0:
			(x0, y0), (x1, y1) = pts[i], pts[j]
			dl.line([(x0, y0), (x0 + (x1 - x0) * a, y0 + (y1 - y0) * a)], fill=int(200 * a), width=lw)
	r = size * S * 0.0105
	for n, (x, y) in enumerate(pts):
		a = min(1, max(0, n_on - RANK[n]))
		if a > 0:
			rr = r * (0.6 + 0.4 * a)
			dd.ellipse((x - rr, y - rr, x + rr, y + rr), fill=int(255 * a))
	lines = lines.resize((size, size), Image.LANCZOS)
	dots = dots.resize((size, size), Image.LANCZOS)
	glow_l = Image.fromarray(np.clip(np.asarray(lines, np.float32) * 0.6 + np.asarray(dots, np.float32), 0, 255).astype(np.uint8))
	glow_l = glow_l.filter(ImageFilter.GaussianBlur(size * 0.012))
	g = np.asarray(glow_l, np.float32) / 255 * 0.9 * glow
	ln = np.asarray(lines, np.float32) / 255
	dt = np.asarray(dots, np.float32) / 255
	out = np.zeros((size, size, 3), np.float32)
	out += g[..., None] * np.array([230, 30, 36], np.float32)
	out += ln[..., None] * np.array([255, 70, 72], np.float32)
	out += dt[..., None] * np.array([255, 205, 198], np.float32)
	return np.clip(out, 0, 255)


@lru_cache(maxsize=8)
def base(size):
	return render(size)


def box(size, t=0.0, built=1.0, border=True):
	"""the black square with the logo; t drives the random flares of the nodes"""
	if built >= 1:
		arr = base(size).copy()
	else:
		arr = render(size, built)
	bg = np.zeros((size, size, 3), np.float32)
	bg[:] = (10, 10, 12)
	# a faint red light in the middle of the square
	yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
	d = np.hypot(xx - size / 2, yy - size * 0.48) / size
	bg += np.clip(0.55 - d, 0, 1)[..., None] * np.array([40, 4, 6], np.float32) * built
	arr = np.clip(bg + arr, 0, 255)
	img = Image.fromarray(arr.astype(np.uint8)).convert("RGBA")
	# the flares: each node now and then, at its own rhythm
	if built >= 1:
		pts, _ = _place(size)
		over = Image.new("RGBA", (size, size), (0, 0, 0, 0))
		od = ImageDraw.Draw(over)
		for n, (x, y) in enumerate(pts):
			ph = (n * 0.6180339) % 1
			sp = 0.23 + ((n * 0.3819) % 1) * 0.25
			v = max(0.0, math.sin((t * sp + ph) * 2 * math.pi)) ** 40
			if v > 0.02:
				r = size * (0.010 + 0.016 * v)
				for k, a in ((3.0, 40), (1.8, 90), (1.0, 220)):
					rr = r * k
					od.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(255, 120 if k > 1 else 235, 110 if k > 1 else 225, int(a * v)))
		over = over.filter(ImageFilter.GaussianBlur(size * 0.006))
		img.alpha_composite(over)
	if border:
		ImageDraw.Draw(img).rectangle((0, 0, size - 1, size - 1), outline=(46, 46, 52, 255), width=max(1, size // 150))
	return img


if __name__ == "__main__":
	box(300, 1.3).save("/tmp/logo_box.png")
