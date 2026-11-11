"""Music made here (no one's rights): soft pads, a plucked arpeggio, a light beat; and the sounds of the clicks,
the typing and the transitions"""
import math
import wave

import numpy as np

SR = 44100
rng = np.random.default_rng(7)


def note(n):
	"""MIDI note to Hz"""
	return 440.0 * 2 ** ((n - 69) / 12)


def env_adsr(n, a, r, sr=SR):
	e = np.ones(n)
	na, nr = int(a * sr), int(r * sr)
	if na:
		e[:na] = np.linspace(0, 1, na)
	if nr:
		e[-nr:] *= np.linspace(1, 0, nr)
	return e


def pad_voice(freq, dur):
	n = int(dur * SR)
	t = np.arange(n) / SR
	out = np.zeros(n)
	for det in (-0.12, 0.0, 0.13):
		f = freq * 2 ** (det / 12)
		for h, amp in ((1, 1.0), (2, 0.35), (3, 0.16), (4, 0.07), (5, 0.03)):
			out += amp * np.sin(2 * math.pi * f * h * t + rng.uniform(0, 6.28))
	return out * env_adsr(n, 0.6, 0.9) / 6


def pluck(freq, dur=0.6):
	n = int(dur * SR)
	t = np.arange(n) / SR
	s = np.sin(2 * math.pi * freq * t) + 0.4 * np.sin(4 * math.pi * freq * t) + 0.15 * np.sin(6 * math.pi * freq * t)
	return s * np.exp(-t * 7) * env_adsr(n, 0.004, 0.05)


def kick():
	n = int(0.35 * SR)
	t = np.arange(n) / SR
	f = 45 + 80 * np.exp(-t * 30)
	ph = 2 * math.pi * np.cumsum(f) / SR
	return np.sin(ph) * np.exp(-t * 9)


def hat():
	n = int(0.06 * SR)
	x = rng.normal(0, 1, n)
	x = np.diff(np.diff(x, prepend=0), prepend=0)
	return x * np.exp(-np.arange(n) / SR * 70) * 0.25


def snare():
	n = int(0.2 * SR)
	t = np.arange(n) / SR
	x = rng.normal(0, 1, n)
	x = np.diff(x, prepend=0) * 0.6
	return (x * np.exp(-t * 22) + 0.4 * np.sin(2 * math.pi * 185 * t) * np.exp(-t * 30)) * 0.5


def add(buf, sig, at, gain=1.0, pan=0.0):
	i = int(at * SR)
	if i >= len(buf) or i < 0:
		return
	sig = sig[: len(buf) - i]
	l, r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
	buf[i:i + len(sig), 0] += sig * gain * l * 1.41
	buf[i:i + len(sig), 1] += sig * gain * r * 1.41


def music(duration, beat_from, beat_to):
	bpm = 104
	beat = 60 / bpm
	bar = beat * 4
	buf = np.zeros((int(duration * SR) + SR, 2))
	# Am  F  C  G
	chords = [(57, [57, 60, 64, 69]), (53, [53, 57, 60, 65]), (48, [55, 60, 64, 67]), (55, [55, 59, 62, 67])]
	t, i = 0.0, 0
	kicks = []
	while t < duration:
		root, tones = chords[i % 4]
		for n in tones:
			add(buf, pad_voice(note(n), bar + 0.9), t, 0.22, pan=rng.uniform(-0.5, 0.5))
		add(buf, pad_voice(note(root - 12), bar + 0.5), t, 0.28)
		arp = [tones[0] + 12, tones[1] + 12, tones[2] + 12, tones[3] + 12, tones[2] + 12, tones[1] + 12, tones[3] + 12, tones[2] + 24]
		for k in range(8):
			at = t + k * beat / 2
			if at > 2.0:
				add(buf, pluck(note(arp[k])), at, 0.10, pan=-0.35 if k % 2 else 0.35)
				add(buf, pluck(note(arp[k])) * 0.5, at + beat * 0.75, 0.05, pan=0.6 if k % 2 else -0.6)
		for k in range(4):
			at = t + k * beat
			if beat_from <= at < beat_to:
				add(buf, kick(), at, 0.55)
				kicks.append(at)
				if k in (1, 3):
					add(buf, snare(), at, 0.16)
				add(buf, hat(), at + beat / 2, 0.22, pan=0.3)
		t += bar
		i += 1
	# the pads give way to each kick
	duck = np.ones(len(buf))
	for at in kicks:
		j = int(at * SR)
		n = int(0.25 * SR)
		seg = 1 - 0.35 * np.exp(-np.arange(n) / SR * 12)
		duck[j:j + n] = np.minimum(duck[j:j + n], seg[: len(duck) - j])
	buf *= duck[:, None]
	return buf[: int(duration * SR)], beat


# --- sound effects

def whoosh(dur=0.7, up=True):
	n = int(dur * SR)
	x = rng.normal(0, 1, n)
	# a moving low-pass: one pole, its cutoff rising then falling
	k = np.sin(np.linspace(0, math.pi, n)) ** 2
	alpha = 0.02 + 0.35 * k
	y = np.zeros(n)
	acc = 0.0
	for i in range(n):
		acc += alpha[i] * (x[i] - acc)
		y[i] = acc
	return y * k * 1.6


def click():
	n = int(0.05 * SR)
	t = np.arange(n) / SR
	return (np.sin(2 * math.pi * 2600 * t) * np.exp(-t * 160) + rng.normal(0, 1, n) * np.exp(-t * 400) * 0.4) * 0.6


def key():
	n = int(0.03 * SR)
	t = np.arange(n) / SR
	return (np.sin(2 * math.pi * 1800 * t) * np.exp(-t * 260) + rng.normal(0, 1, n) * np.exp(-t * 500) * 0.5) * 0.35


def pop():
	n = int(0.12 * SR)
	t = np.arange(n) / SR
	f = 520 + 500 * (1 - np.exp(-t * 40))
	return np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * 28) * 0.45


def impact():
	n = int(1.6 * SR)
	t = np.arange(n) / SR
	low = np.sin(2 * math.pi * (40 + 30 * np.exp(-t * 6)) * t) * np.exp(-t * 2.5)
	shimmer = sum(np.sin(2 * math.pi * f * t) for f in (880, 1320, 1760, 2640)) * np.exp(-t * 3) * 0.08
	return low * 0.9 + shimmer


def riser(dur=1.4):
	n = int(dur * SR)
	x = whoosh(dur)
	return x * np.linspace(0.1, 1, n) ** 2


SFX = {"whoosh": (whoosh, 0.28), "click": (click, 0.55), "key": (key, 0.35), "pop": (pop, 0.4), "impact": (impact, 0.6),
	"riser": (riser, 0.3)}


def build(duration, events, path, beat_from=4.3, beat_to=None):
	beat_to = beat_to or duration - 4.0
	buf, beat = music(duration, beat_from, beat_to)
	buf *= 0.55
	cache = {}
	for at, kind in events:
		fn, gain = SFX[kind]
		if kind not in cache or kind in ("whoosh", "key"):
			cache[kind] = fn()
		add(buf, cache[kind], at, gain, pan=rng.uniform(-0.2, 0.2))
	# the end fades
	n = len(buf)
	fade = int(2.5 * SR)
	buf[-fade:] *= np.linspace(1, 0, fade)[:, None]
	buf[: int(0.05 * SR)] *= np.linspace(0, 1, int(0.05 * SR))[:, None]
	buf = np.tanh(buf * 1.2) / np.tanh(1.2)
	buf /= max(1e-9, np.abs(buf).max()) / 0.89
	data = (buf * 32767).astype("<i2")
	with wave.open(path, "wb") as w:
		w.setnchannels(2)
		w.setsampwidth(2)
		w.setframerate(SR)
		w.writeframes(data.tobytes())
