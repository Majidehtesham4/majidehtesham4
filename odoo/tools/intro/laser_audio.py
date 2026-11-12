"""The sound of the laser intro, made here from sine waves and noise (no one's rights): a dark room, the aiming
beep, the laser's power-up whine and hum, the sizzle and crackle of the cut, more lasers and a rising drone, the
cut-off, a deep impact when the logo is seen whole, the ticks of cooling metal, the small laser, a shimmer."""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audio_intro import SR, chime, drone, finish, impact, lowpass, place, reverb, rng, shimmer, t_, whoosh  # noqa: E402

LEN = 12.0


def band(x, lo, hi):
	"""band of noise between two one-pole cut-offs"""
	return lowpass(x, hi) - lowpass(x, lo)


def sizzle(dur, density=1.0, seed=1):
	"""the cut: a hiss with a bubbling crackle, its loudness wavering"""
	r = np.random.default_rng(seed)
	n = int(dur * SR)
	t = t_(dur)
	hiss = band(r.normal(0, 1, n), 0.08, 0.7) * (0.6 + 0.4 * lowpass(np.abs(r.normal(0, 1, n)), 0.002) * 3)
	crack = np.zeros(n)
	k = int(dur * 180 * density)
	for i in r.integers(0, n - 400, k):
		crack[i:i + 400] += r.normal(0, 1, 400) * np.exp(-np.arange(400) / r.uniform(15, 70)) * r.uniform(0.2, 1.0)
	crack = band(crack, 0.05, 0.9)
	env = np.minimum(1, t / 0.03) * np.minimum(1, (dur - t) / 0.05)
	return (hiss * 0.5 + crack * 0.9) * env


def hum(dur, f=96.0):
	"""the laser's electric hum and its thin whine"""
	t = t_(dur)
	x = sum(np.sin(2 * math.pi * f * h * t) / h for h in range(1, 9)) * 0.35
	whine = np.sin(2 * math.pi * 3150 * t + 2 * np.sin(2 * math.pi * 6 * t)) * 0.05
	env = np.minimum(1, t / 0.04) * np.minimum(1, (dur - t) / 0.04)
	return lowpass(x, 0.15) * env + whine * env


def power_up(dur=0.18):
	t = t_(dur)
	f = 300 + 3200 * (t / dur) ** 2
	return np.sin(2 * math.pi * np.cumsum(f) / SR) * np.minimum(1, t / 0.01) * 0.5


def beep():
	t = t_(0.18)
	return (np.sin(2 * math.pi * 2093 * t) * 0.5 + np.sin(2 * math.pi * 4186 * t) * 0.15) * np.exp(-t * 12) * np.minimum(1, t / 0.003)


def tink(f, seed):
	r = np.random.default_rng(seed)
	t = t_(1.2)
	x = sum(np.sin(2 * math.pi * f * m * t + r.uniform(0, 6)) * a for m, a in ((1, 1), (2.71, 0.5), (5.2, 0.25)))
	return x * np.exp(-t * r.uniform(5, 9)) * np.minimum(1, t / 0.002) * 0.35


def burst():
	n = int(0.5 * SR)
	return band(rng.normal(0, 1, n), 0.03, 0.8) * np.exp(-t_(0.5) * 9) * 1.4


def build(path):
	buf = np.zeros((int(LEN * SR), 2))
	# the room: very low, almost silent, then the drone that rises while the lasers multiply
	room = lowpass(rng.normal(0, 1, len(buf)), 0.003) * 4
	place(buf, room, 0, 0.25)
	pad = drone(LEN, [36.7, 55, 73.4], lambda t: 0.1 + 0.25 * np.clip((t - 1.5) / 3.5, 0, 1) + 0.6 * np.clip((t - 5.0) / 3.3, 0, 1) ** 2
		- 0.55 * np.clip((t - 8.3) / 0.4, 0, 1) + 0.25 * np.clip((t - 8.7) / 0.4, 0, 1) * np.exp(-np.maximum(t - 9, 0) * 0.35))
	place(buf, reverb(pad, 0.35, 1.3), 0, 0.7)
	place(buf, reverb(beep(), 0.3), 0.58, 0.18)
	# the first laser: down, the touch, the long cut
	place(buf, reverb(power_up(), 0.25), 1.42, 0.35)
	place(buf, reverb(burst(), 0.35), 1.57, 0.55)
	place(buf, hum(5.2 - 1.45), 1.45, 0.28)
	place(buf, reverb(sizzle(5.2 - 1.57, 1.0, 3), 0.2), 1.57, 0.36)
	# the six lasers: each its own hiss, spread across
	for k in range(6):
		a = 5.15 + k * 0.1
		place(buf, reverb(sizzle(8.3 - a, 0.6, 10 + k), 0.25), a, 0.16, pan=-0.75 + k * 0.3)
		place(buf, hum(8.3 - a, 96 + k * 3.1), a, 0.12, pan=-0.75 + k * 0.3)
		place(buf, power_up(0.12), a - 0.1, 0.12, pan=-0.75 + k * 0.3)
	riser = whoosh(1.6, 0.92)
	place(buf, riser * np.linspace(0.2, 1, len(riser)) ** 2, 6.75, 0.35)
	# all cut: the logo whole, a deep impact
	place(buf, reverb(impact(), 0.4, 1.4), 8.62, 1.0)
	for k, (at, f) in enumerate(((8.95, 2637), (9.2, 3520), (9.45, 2960), (9.9, 4186), (10.3, 3136), (10.75, 3951))):
		place(buf, reverb(tink(f, k), 0.45, 1.2), at, 0.16, pan=((k * 53) % 7 - 3) / 4)
	# the small laser under ERP
	place(buf, power_up(0.1), 9.05, 0.15)
	place(buf, reverb(sizzle(0.7, 0.7, 40), 0.3), 9.1, 0.3)
	# the light across the words
	place(buf, reverb(whoosh(1.4, 0.5), 0.4), 9.5, 0.12)
	place(buf, reverb(shimmer(1.6, 1568), 0.5, 1.3), 9.6, 0.4, -0.3)
	place(buf, reverb(chime(1174.7), 0.55, 1.4), 10.1, 0.3)
	finish(buf, path, fade_in=0.3, fade_out=0.9)


if __name__ == "__main__":
	build(sys.argv[1])
