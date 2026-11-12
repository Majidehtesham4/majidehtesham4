"""The sound of the two VERON ERP intros, made here from sine waves and noise (no one's rights):
signal: a radar ping, rising blips for the arcs, swooshes for the lines, a riser and an impact, a shimmer for the words
metal:  a deep drone, the clicks and hum of neon tubes coming on, metallic «shing» for the reflections, a low swell"""
import math
import os
import sys
import wave

import numpy as np

SR = 48000
rng = np.random.default_rng(11)


def t_(dur):
	return np.arange(int(dur * SR)) / SR


def lowpass(x, alpha):
	"""one-pole low-pass; alpha a number or an array (0..1)"""
	y = np.empty_like(x)
	acc = 0.0
	a = np.broadcast_to(alpha, x.shape)
	for i in range(len(x)):
		acc += a[i] * (x[i] - acc)
		y[i] = acc
	return y


def comb(x, delay, g):
	"""y[n] = x[n] + g y[n-D], block by block"""
	y = x.copy()
	for k in range(delay, len(x), delay):
		end = min(k + delay, len(x))
		y[k:end] += g * y[k - delay:end - delay]
	return y


def reverb(x, mix=0.35, size=1.0):
	wet = np.zeros_like(x)
	for d, g in ((1557, 0.84), (1617, 0.83), (1491, 0.82), (1422, 0.81), (1277, 0.8), (1356, 0.8)):
		wet += comb(x, int(d * size * SR / 44100), g)
	wet = lowpass(wet / 6, 0.35)
	return x * (1 - mix) + wet * mix


def stereo(x, pan=0.0):
	l, r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
	return np.stack([x * l, x * r], 1)


def place(buf, sig, at, gain=1.0, pan=0.0):
	s = stereo(sig, pan) if sig.ndim == 1 else sig
	i = int(at * SR)
	n = min(len(s), len(buf) - i)
	if n > 0:
		buf[i:i + n] += s[:n] * gain


def ping(f=1318.5):
	t = t_(1.8)
	x = (np.sin(2 * math.pi * f * t) + 0.3 * np.sin(2 * math.pi * f * 2.01 * t)) * np.exp(-t * 4.5)
	x[: int(0.003 * SR)] *= np.linspace(0, 1, int(0.003 * SR))
	return x


def blip(f):
	t = t_(0.5)
	x = np.sin(2 * math.pi * f * t + 0.5 * np.sin(2 * math.pi * f * 2 * t)) * np.exp(-t * 11)
	x[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))
	return x


def whoosh(dur=0.9, peak=0.55):
	n = int(dur * SR)
	x = rng.normal(0, 1, n)
	k = np.sin(np.linspace(0, math.pi, n)) ** 2
	k = np.where(np.linspace(0, 1, n) < peak, np.sin(np.linspace(0, 1, n) / peak * math.pi / 2) ** 2,
		np.cos((np.linspace(0, 1, n) - peak) / (1 - peak) * math.pi / 2) ** 2)
	return lowpass(x, 0.02 + 0.3 * k) * k * 2.2


def riser(dur=1.3):
	n = int(dur * SR)
	x = rng.normal(0, 1, n)
	k = np.linspace(0, 1, n) ** 2.2
	y = lowpass(x, 0.01 + 0.4 * k) * k * 2.0
	t = t_(dur)
	tone = np.sin(2 * math.pi * np.cumsum(220 + 660 * k) / SR) * k * 0.15
	return y + tone


def impact():
	t = t_(3.0)
	low = np.sin(2 * math.pi * np.cumsum(38 + 70 * np.exp(-t * 7)) / SR) * np.exp(-t * 1.6)
	body = lowpass(rng.normal(0, 1, len(t)), 0.08) * np.exp(-t * 6) * 1.2
	shimmer = sum(np.sin(2 * math.pi * f * t + i) for i, f in enumerate((1046.5, 1568, 2093, 3136))) * np.exp(-t * 1.4) * 0.05
	return low * 1.0 + body * 0.5 + shimmer


def shimmer(dur=1.4, base=2093):
	t = t_(dur)
	x = sum(np.sin(2 * math.pi * base * r * t + i) * (0.6 ** i) for i, r in enumerate((1, 1.5, 2.0, 2.52, 3.01)))
	env = np.sin(np.clip(t / dur, 0, 1) * math.pi) ** 1.5
	return x * env * 0.2


def shing(f=2637):
	"""metal: a struck, slightly detuned bell, with a breath of noise"""
	t = t_(2.2)
	x = sum(np.sin(2 * math.pi * f * r * t + i) * a for i, (r, a) in
		enumerate(((1, 1), (1.003, 0.8), (2.76, 0.35), (5.4, 0.15), (0.5, 0.25))))
	n = lowpass(rng.normal(0, 1, len(t)), 0.6) * np.exp(-t * 18) * 0.4
	env = np.exp(-t * 2.4) * np.minimum(1, t / 0.02)
	return (x * env + n) * 0.35


def neon_on(seed):
	"""a neon tube starting: a click, a few crackles and a short hum at 100 Hz"""
	r = np.random.default_rng(seed)
	t = t_(0.7)
	click = r.normal(0, 1, len(t)) * np.exp(-t * 120) * 0.6
	crack = np.zeros(len(t))
	for _ in range(4):
		i = int(r.uniform(0.02, 0.3) * SR)
		crack[i:i + 300] += r.normal(0, 1, 300) * np.exp(-np.arange(300) / 60) * 0.4
	hum = (np.sin(2 * math.pi * 100 * t) + 0.4 * np.sin(2 * math.pi * 200 * t) + 0.15 * np.sin(2 * math.pi * 300 * t))
	hum *= np.minimum(1, t / 0.05) * np.exp(-t * 4) * 0.35
	return lowpass(click + crack, 0.5) + hum


def drone(dur, notes, swell):
	"""a dark pad: detuned saws (as sums of harmonics), low-passed; swell gives its loudness over time"""
	t = t_(dur)
	out = np.zeros(len(t))
	for f in notes:
		for det in (-0.08, 0.0, 0.07):
			ff = f * 2 ** (det / 12)
			for h in range(1, 9):
				out += np.sin(2 * math.pi * ff * h * t + rng.uniform(0, 6.3)) / h
	out = lowpass(out / (len(notes) * 12), 0.05)
	return out * swell(t)


def finish(buf, path, fade_in=0.05, fade_out=0.6):
	n = len(buf)
	buf[: int(fade_in * SR)] *= np.linspace(0, 1, int(fade_in * SR))[:, None]
	buf[n - int(fade_out * SR):] *= np.linspace(1, 0, int(fade_out * SR))[:, None]
	buf = np.tanh(buf * 1.15) / np.tanh(1.15)
	buf /= max(1e-9, np.abs(buf).max()) / 0.9
	with wave.open(path, "wb") as w:
		w.setnchannels(2)
		w.setsampwidth(2)
		w.setframerate(SR)
		w.writeframes((buf * 32767).astype("<i2").tobytes())


def signal(path):
	dur = 8.0
	buf = np.zeros((int(dur * SR), 2))
	A = 55.0
	pad = drone(dur, [A, A * 1.5, A * 2], lambda t: np.clip(t / 4.3, 0, 1) ** 2 * 0.5 + np.where(t > 4.35, 0.6 * np.exp(-(t - 4.35) * 0.5), 0))
	place(buf, reverb(pad, 0.3), 0, 0.55)
	place(buf, reverb(ping(), 0.45, 1.3), 0.35, 0.55)
	place(buf, reverb(ping(1318.5) * 0.6, 0.5, 1.3), 1.0, 0.35, 0.2)
	for k, f in enumerate((659.3, 740, 830.6, 880, 987.8, 1108.7)):
		place(buf, reverb(blip(f), 0.4), 0.75 + k * 0.24, 0.3, pan=-0.3 + k * 0.12)
	place(buf, reverb(whoosh(1.0, 0.7), 0.25), 2.15, 0.26, -0.1)
	w = whoosh(1.1, 0.6)
	place(buf, np.stack([w, np.roll(w, 900)], 1), 3.0, 0.24)
	place(buf, riser(1.3), 3.05, 0.35)
	place(buf, reverb(impact(), 0.35, 1.4), 4.35, 1.0)
	place(buf, reverb(whoosh(0.9, 0.4), 0.3), 5.0, 0.22, 0.2)
	place(buf, reverb(shimmer(1.4, 1568), 0.5), 5.7, 0.5, -0.4)
	place(buf, reverb(shimmer(1.2, 2093), 0.5), 5.95, 0.4, 0.4)
	finish(buf, path)


def metal(path):
	dur = 9.0
	buf = np.zeros((int(dur * SR), 2))
	pad = drone(dur, [41.2, 61.7, 82.4], lambda t: 0.25 + 0.55 * np.clip((t - 1.0) / 3.0, 0, 1) + 0.25 * np.clip((t - 5.5) / 2.0, 0, 1))
	place(buf, reverb(pad, 0.4, 1.3), 0, 0.7)
	rumble = lowpass(rng.normal(0, 1, int(dur * SR)), 0.004) * 6
	place(buf, rumble * np.clip(t_(dur) / 3.5, 0, 1), 0, 0.35)
	swell = impact()[: int(2.5 * SR)] * 0.6
	place(buf, reverb(swell, 0.5, 1.4), 1.9, 0.6)
	for k in range(14):
		place(buf, reverb(neon_on(k), 0.3), 2.0 + k * 0.17, 0.16, pan=((k * 37) % 9 - 4) / 6)
	place(buf, reverb(shing(2637), 0.55, 1.4), 4.25, 0.5, -0.3)
	place(buf, reverb(shing(3136), 0.55, 1.4), 5.25, 0.42, 0.3)
	place(buf, reverb(impact() * 0.7, 0.45, 1.4), 6.0, 0.5)
	finish(buf, path, fade_in=0.4, fade_out=0.8)


def pen(dur):
	"""the hiss of a pen of light: filtered noise with a light tremble"""
	n = int(dur * SR)
	t = t_(dur)
	x = lowpass(rng.normal(0, 1, n), 0.25) - lowpass(rng.normal(0, 1, n), 0.02)
	trem = 0.7 + 0.3 * np.sin(2 * math.pi * 13 * t) * np.sin(2 * math.pi * 0.7 * t)
	env = np.minimum(1, t / 0.15) * np.minimum(1, (dur - t) / 0.3)
	return x * trem * env * 0.5


def thump(f=55, decay=9):
	t = t_(0.8)
	x = np.sin(2 * math.pi * np.cumsum(f + 70 * np.exp(-t * 35)) / SR) * np.exp(-t * decay)
	return x + lowpass(rng.normal(0, 1, len(t)), 0.15) * np.exp(-t * 60) * 0.4


def chime(f=1760):
	t = t_(2.4)
	x = sum(np.sin(2 * math.pi * f * r * t + i) * a for i, (r, a) in enumerate(((1, 1), (2.0, 0.4), (3.0, 0.2), (4.2, 0.1))))
	return x * np.exp(-t * 2.2) * np.minimum(1, t / 0.005) * 0.4


def draw(path):
	dur = 8.5
	buf = np.zeros((int(dur * SR), 2))
	pad = drone(dur, [49, 73.4, 98], lambda t: 0.25 + 0.35 * np.clip(t / 5, 0, 1) + 0.3 * np.clip((t - 5) / 1.5, 0, 1))
	place(buf, reverb(pad, 0.35), 0, 0.6)
	for i in range(5):
		at = 0.4 + i * 0.32
		place(buf, pen(1.0), at, 0.22, pan=-0.5)
		place(buf, pen(1.0), at, 0.22, pan=0.5)
		place(buf, reverb(blip(880 + i * 110) * 0.5, 0.4), at, 0.15)
	for k in range(3):
		place(buf, pen(0.8), 2.5 + k * 0.3, 0.3)
	for i in range(6):
		place(buf, pen(0.5), 3.7 + i * 0.18, 0.2, pan=-0.3 + i * 0.12)
		place(buf, reverb(blip(1320 + i * 90) * 0.4, 0.4), 3.7 + i * 0.18, 0.12)
	place(buf, reverb(thump(48, 5), 0.4), 5.0, 0.7)
	place(buf, pen(0.7), 5.8, 0.22, 0.3)
	place(buf, reverb(shing(2349), 0.5, 1.3), 6.0, 0.45)
	place(buf, reverb(chime(1174.7), 0.5, 1.3), 6.1, 0.35)
	finish(buf, path, fade_in=0.3)


def energy(path):
	dur = 7.5
	buf = np.zeros((int(dur * SR), 2))
	hit = 1.4
	for k in range(5):
		w = whoosh(0.9, 0.85)
		place(buf, w, hit - 0.9 + (k - 2) * 0.03, 0.22, pan=-0.8 + k * 0.4)
	place(buf, riser(1.2), hit - 1.2, 0.45)
	place(buf, reverb(impact(), 0.35, 1.4), hit, 1.0)
	burst = lowpass(rng.normal(0, 1, int(0.8 * SR)), 0.5) * np.exp(-t_(0.8) * 7)
	place(buf, reverb(burst, 0.4), hit, 0.45)
	pad = drone(dur, [55, 82.4, 110], lambda t: np.where(t < hit, 0.15 * t / hit, 0.65 * np.exp(-(t - hit) * 0.25) + 0.25))
	place(buf, reverb(pad, 0.35), 0, 0.6)
	place(buf, reverb(thump(40, 3.5) * 1.2, 0.4, 1.4), 3.3, 0.8)
	place(buf, reverb(shimmer(1.5, 1760), 0.5), 3.6, 0.45, -0.4)
	place(buf, reverb(shimmer(1.2, 2349), 0.5), 4.2, 0.35, 0.4)
	finish(buf, path)


def pulse(path):
	dur = 3.6
	buf = np.zeros((int(dur * SR), 2))
	pad = drone(dur, [55, 82.4], lambda t: 0.2 + 0.4 * np.clip(t / 1.5, 0, 1))
	place(buf, reverb(pad, 0.3), 0, 0.5)
	place(buf, reverb(thump(52, 8), 0.3), 0.35, 0.75)
	place(buf, reverb(thump(48, 6) * 1.2, 0.35), 0.8, 0.9)
	place(buf, reverb(whoosh(0.6, 0.5), 0.3), 1.2, 0.18)
	place(buf, reverb(chime(1318.5), 0.5, 1.3), 1.6, 0.4)
	finish(buf, path, fade_in=0.05, fade_out=0.35)


def pluck(f, dur=1.6):
	"""a soft plucked note with a little shimmer"""
	t = t_(dur)
	x = sum(np.sin(2 * math.pi * f * h * t + h) * a * np.exp(-t * (2.5 + h * 1.5)) for h, a in ((1, 1), (2, 0.45), (3, 0.2), (4, 0.08)))
	return x * np.minimum(1, t / 0.004) * 0.45


def glass(f):
	t = t_(0.5)
	return (np.sin(2 * math.pi * f * t) + 0.3 * np.sin(2 * math.pi * f * 2.76 * t)) * np.exp(-t * 14) * np.minimum(1, t / 0.002) * 0.2


def network(path):
	import json
	dur = 7.9
	buf = np.zeros((int(dur * SR), 2))
	note = lambda n: 440.0 * 2 ** ((n - 69) / 12)
	pad = drone(dur, [note(45), note(52), note(57), note(60)], lambda t: 0.15 + 0.35 * np.clip(t / 4.5, 0, 1) + 0.35 * np.clip((t - 5.0) / 1.0, 0, 1))
	place(buf, reverb(pad, 0.4, 1.3), 0, 0.55)
	# the named modules: each falls with a soft breath and lands on a note; the AI, last, on the highest
	names = [(1.25 + i * 0.4, n) for i, n in enumerate((69, 72, 74, 76, 79, 81, 84))] + [(4.65, 88)]
	for k, (at, n) in enumerate(names):
		place(buf, reverb(whoosh(0.8, 0.85), 0.3), at - 0.8, 0.07, pan=(k % 2) * 0.6 - 0.3)
		place(buf, reverb(pluck(note(n)), 0.45, 1.3), at, 0.42 if k < 7 else 0.6, pan=((k * 37) % 7 - 3) / 6)
		place(buf, reverb(thump(55 if k < 7 else 45, 9), 0.3), at, 0.28)
	place(buf, reverb(chime(note(88)), 0.5, 1.4), 4.65, 0.35)
	# the other nodes falling like rain: glassy ticks
	G = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "net_graph.json")))
	named = {7, 21, 1, 27, 17, 4, 2, 30}
	rest = sorted([i for i in range(len(G["nodes"])) if i not in named], key=lambda i: (G["nodes"][i][1], G["nodes"][i][0]))
	scale = [81, 84, 86, 88, 91, 93, 96]
	for k, i in enumerate(rest):
		f = math.sin(i * 91.3) * 0.5 + 0.5
		at = 2.55 + (k / len(rest)) * 1.7 + f * 0.25
		place(buf, reverb(glass(note(scale[(i * 5) % len(scale)])), 0.5), at, 0.22, pan=(G["nodes"][i][0] - 511) / 200)
	# the wave up the V, the whole logo
	place(buf, riser(0.5), 4.6, 0.3)
	place(buf, reverb(impact() * 0.8, 0.45, 1.4), 5.15, 0.75)
	place(buf, reverb(shimmer(1.4, 1760), 0.5), 5.2, 0.35)
	place(buf, reverb(whoosh(0.8, 0.4), 0.35), 5.7, 0.12)
	place(buf, reverb(shimmer(1.4, 2349), 0.5, 1.3), 6.1, 0.35, 0.3)
	place(buf, reverb(chime(note(81)), 0.55, 1.4), 6.2, 0.3)
	finish(buf, path, fade_in=0.2, fade_out=0.6)


if __name__ == "__main__":
	{"signal": signal, "metal": metal, "draw": draw, "energy": energy, "pulse": pulse, "network": network}[sys.argv[1]](sys.argv[2])
