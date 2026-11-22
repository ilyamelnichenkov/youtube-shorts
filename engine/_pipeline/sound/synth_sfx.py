"""Synthesise the "case-file" SFX library into sfx/*.wav (48 kHz mono, 24-bit, peak-normalised to -3 dBFS).

Run:  $SHORTS_HOME/venv/bin/python synth_sfx.py [--seed N]
Palette: tactile and investigative (camera shutter, paper, rubber stamp, red marker, typewriter, soft air, tight sub).
Everything is generated from noise and sines; nothing comes from a game, trailer or sample pack.
Each sample has a clear onset near t=0 (mix.py aligns the onset, the peak or the end to the cue time).
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
HERE = Path(__file__).parent
OUT = HERE / "sfx"
rng = np.random.default_rng(7)


def t_(d): return np.arange(int(d * SR)) / SR
def noise(d): return rng.standard_normal(int(d * SR))
def bp(x, lo, hi, o=2): return sosfilt(butter(o, [lo, hi], "band", fs=SR, output="sos"), x)
def lp(x, f, o=2): return sosfilt(butter(o, f, "low", fs=SR, output="sos"), x)
def hp(x, f, o=2): return sosfilt(butter(o, f, "high", fs=SR, output="sos"), x)
def dec(d, tau, atk=0.001):
    t = t_(d); e = np.exp(-t / tau); n = max(1, int(atk * SR)); e[:n] *= np.linspace(0, 1, n); return e
def pad(x, d):
    out = np.zeros(int(d * SR)); out[:min(len(x), len(out))] = x[:len(out)]; return out
def at(buf, x, t):
    s = int(t * SR); e = min(len(buf), s + len(x))
    if e > s: buf[s:e] += x[:e - s]
    return buf
def sine_sweep(d, f0, f1, curve=3.0):
    t = t_(d); f = f1 + (f0 - f1) * np.exp(-t * curve / d); return np.sin(2 * np.pi * np.cumsum(f) / SR)
def room(x, tail=0.35, wet=0.25):
    """Very small synthetic room: decaying-noise impulse response."""
    n = int(tail * SR); ir = noise(tail) * np.exp(-np.arange(n) / (0.09 * SR)); ir = lp(ir, 5000)
    ir /= np.abs(ir).sum() ** 0.5 * 8
    return x + wet * fftconvolve(x, ir)[:len(x)]
def swell(d, peak):
    t = t_(d); x = (t / (peak * d)) ** 2; y = ((1 - t / d) / (1 - peak)) ** 1.5
    return np.where(t < peak * d, x, y)


def click(d=0.03, lo=1500, hi=6000, tau=0.006):
    return bp(noise(d), lo, hi) * dec(d, tau, 0.0004)


def shutter():
    # two blade clicks (open, close) with a small mechanical thunk
    b = np.zeros(int(0.22 * SR))
    at(b, click(0.04, 2000, 7000, 0.007), 0.0)
    at(b, 0.5 * np.sin(2 * np.pi * 220 * t_(0.05)) * dec(0.05, 0.012), 0.0)
    at(b, 0.8 * click(0.05, 1200, 5000, 0.01), 0.075)
    at(b, 0.4 * np.sin(2 * np.pi * 160 * t_(0.06)) * dec(0.06, 0.015), 0.075)
    return room(b, 0.2, 0.15)


def shutter_clack():
    # heavier shutter used as a transition: clack + low thump + short paper-like tail
    b = np.zeros(int(0.4 * SR))
    at(b, click(0.06, 1000, 6500, 0.012), 0.0)
    at(b, 0.9 * sine_sweep(0.22, 140, 55) * dec(0.22, 0.07), 0.0)
    at(b, 0.6 * click(0.06, 1500, 5500, 0.01), 0.09)
    at(b, 0.18 * bp(noise(0.2), 2500, 7000) * dec(0.2, 0.05), 0.12)
    return room(b, 0.25, 0.2)


def paper_slide():
    d = 0.42; n = bp(noise(d), 900, 7000) * swell(d, 0.45)
    n *= 0.6 + 0.4 * np.abs(lp(noise(d), 40, 1)) / (np.abs(lp(noise(d), 40, 1)).max() + 1e-9)
    return n


def paper_flip():
    d = 0.22; n = bp(noise(d), 1500, 8000) * dec(d, 0.05, 0.004)
    return n * (1 + 0.5 * np.sin(2 * np.pi * 38 * t_(d)))


def stamp():
    # rubber stamp on a desk: muffled low thud, short body knock, faint paper rattle
    b = np.zeros(int(0.5 * SR))
    at(b, sine_sweep(0.3, 120, 48, 4) * dec(0.3, 0.09, 0.0008), 0.0)
    at(b, 0.7 * lp(noise(0.08), 1800) * dec(0.08, 0.018, 0.0005), 0.0)
    at(b, 0.25 * bp(noise(0.25), 2500, 7000) * dec(0.25, 0.06), 0.02)
    return room(b, 0.3, 0.2)


def marker_scratch():
    # red marker drawing a circle: bandpassed noise with stroke-speed modulation, ~0.9 s
    d = 0.9; t = t_(d)
    stroke = 0.55 + 0.45 * np.abs(np.sin(2 * np.pi * 7 * t + 0.6 * np.sin(2 * np.pi * 1.1 * t)))
    n = bp(noise(d), 1800, 6500, 3) * stroke
    n += 0.4 * bp(noise(d), 600, 1400) * stroke
    env = np.minimum(1, t / 0.05) * np.minimum(1, (d - t) / 0.12)
    return n * env


def marker_swipe():
    # fast marker bar (redact wipe): rising noise band + dry felt-tip tick at the end
    d = 0.3; t = t_(d); n = noise(d); out = np.zeros_like(t)
    for i, (lo, hi) in enumerate([(700, 1800), (1500, 3500), (2800, 6500)]):
        seg = bp(n, lo, hi); w = np.exp(-((t - (0.04 + 0.07 * i)) / 0.06) ** 2); out += seg * w
    out *= np.minimum(1, t / 0.01) * np.minimum(1, (d - t) / 0.08)
    at(out, 0.7 * lp(noise(0.05), 2500) * dec(0.05, 0.01), 0.17)
    return out


def type_tick(f=2600):
    b = np.zeros(int(0.09 * SR))
    at(b, click(0.03, 1800, 7500, 0.005), 0.0)
    at(b, 0.5 * np.sin(2 * np.pi * f * t_(0.02)) * dec(0.02, 0.004), 0.0)
    at(b, 0.35 * lp(noise(0.04), 900) * dec(0.04, 0.01), 0.0)
    return b


def type_burst():
    b = np.zeros(int(0.5 * SR))
    for i, t in enumerate([0.0, 0.07, 0.13, 0.215, 0.29, 0.34]):
        at(b, (0.7 + 0.3 * rng.random()) * type_tick(2300 + 500 * rng.random()), t)
    at(b, 0.8 * click(0.05, 900, 4000, 0.012), 0.4)  # carriage bell-less return clack
    return b


def whoosh(d=0.45, lo=300, hi=3500, peak=0.4):
    """Band of noise whose centre rises from lo to hi while the swell envelope opens and closes."""
    n = noise(d); t = t_(d); out = np.zeros_like(t); steps = 6
    for i in range(steps):
        c = lo * (hi / lo) ** ((i + 0.5) / steps)
        w = np.exp(-((t - d * (0.2 + 0.6 * (i + 0.5) / steps)) / (0.2 * d)) ** 2)
        out += bp(n, c * 0.6, min(c * 1.7, 20000)) * w
    return out * swell(d, peak)


def whoosh_soft(): return lp(whoosh(0.36, 400, 2600, 0.45), 4500)
def whoosh_zoom():
    d = 0.5; n = noise(d); t = t_(d); out = np.zeros_like(t)
    for i, c in enumerate([500, 900, 1600, 2800, 4800]):
        out += bp(n, c * 0.7, c * 1.5) * np.exp(-((t - 0.08 * i - 0.06) / 0.1) ** 2)
    return out * swell(d, 0.7)


def sub_hit():
    b = np.zeros(int(0.7 * SR))
    at(b, sine_sweep(0.6, 85, 38, 5) * dec(0.6, 0.2, 0.002), 0.0)
    at(b, 0.5 * lp(noise(0.05), 600) * dec(0.05, 0.01, 0.0005), 0.0)
    return b


def flash_hit():
    b = np.zeros(int(0.35 * SR))
    at(b, sine_sweep(0.3, 110, 50, 5) * dec(0.3, 0.09), 0.0)
    at(b, 0.5 * bp(noise(0.12), 2000, 9000) * dec(0.12, 0.025, 0.0003), 0.0)
    return b


def impact():
    # tight hook hit: sub + dry knock + a short metallic ring, room tail
    b = np.zeros(int(1.2 * SR)); t = t_(1.2)
    at(b, sub_hit()[:int(0.7 * SR)], 0.0)
    at(b, 0.6 * lp(noise(0.09), 3500) * dec(0.09, 0.02, 0.0004), 0.0)
    ring = sum(a * np.sin(2 * np.pi * f * t) for f, a in [(420, 0.5), (667, 0.35), (1053, 0.2)]) * dec(1.2, 0.25, 0.002)
    b += 0.12 * ring
    return room(b, 0.6, 0.25)


def star_tick():
    d = 0.18; t = t_(d)
    tone = np.sin(2 * np.pi * 1760 * t) * dec(d, 0.035, 0.0006) + 0.4 * np.sin(2 * np.pi * 3520 * t) * dec(d, 0.02, 0.0006)
    return tone + pad(0.5 * click(0.015, 3000, 9000, 0.003), d)


def star_slam():
    d = 1.3; t = t_(d); b = np.zeros(len(t))
    at(b, sub_hit()[:int(0.7 * SR)] * 1.0, 0.0)
    at(b, 0.7 * stamp()[:int(0.4 * SR)], 0.0)
    ring = sum(a * np.sin(2 * np.pi * f * t) for f, a in [(880, 0.5), (1320, 0.4), (1760, 0.5), (2637, 0.25), (3520, 0.2)]) * dec(d, 0.28, 0.0008)
    b += 0.22 * ring
    return room(b, 0.6, 0.3)


def final_hit():
    d = 2.4; t = t_(d); b = np.zeros(len(t))
    at(b, 1.1 * sine_sweep(1.2, 80, 34, 4) * dec(1.2, 0.45, 0.002), 0.0)
    at(b, 0.8 * stamp()[:int(0.4 * SR)], 0.0)
    at(b, 0.5 * lp(noise(0.12), 2800) * dec(0.12, 0.03, 0.0005), 0.0)
    ring = sum(a * np.sin(2 * np.pi * f * t) for f, a in [(330, 0.5), (495, 0.35), (742, 0.3), (1180, 0.2)]) * dec(d, 0.6, 0.003)
    b += 0.14 * ring
    return room(b, 1.0, 0.4)


def pop():
    d = 0.14
    return sine_sweep(d, 1100, 320, 5) * dec(d, 0.03, 0.0005) + 0.3 * pad(click(0.02, 1500, 6000, 0.004), d)


def alarm_blip():
    d = 0.26; t = t_(d); y = np.zeros(len(t))
    for i, f in enumerate([1250, 940]):
        s = int(i * 0.1 * SR); seg = t_(0.1)
        w = np.sign(np.sin(2 * np.pi * f * seg)) * 0.5 + np.sin(2 * np.pi * f * seg)
        y[s:s + len(seg)] += lp(w, 4000) * np.minimum(1, seg / 0.004) * np.minimum(1, (0.1 - seg) / 0.02)
    return y


def siren_swell():
    # police-like two-tone wail, deliberately thin and filtered so it stays out of the speech range
    d = 3.4; t = t_(d); lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 1.3 * t)
    f = 620 + 330 * lfo; ph = 2 * np.pi * np.cumsum(f) / SR
    w = np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.15 * np.sin(3 * ph)
    env = swell(d, 0.38) ** 0.8
    return room(lp(w, 3200) * env, 0.5, 0.35)


def tab_slide():
    d = 0.3; return bp(noise(d), 800, 5000) * swell(d, 0.3) * 0.8 + pad(0.5 * click(0.03, 1000, 4000, 0.008), d)


def glitch_tick():
    d = 0.06; return bp(noise(d), 3000, 12000) * dec(d, 0.01, 0.0003) * np.sign(np.sin(2 * np.pi * 900 * t_(d)))


def shimmer_swell():
    d = 0.7; t = t_(d); x = sum(np.sin(2 * np.pi * f * t) * np.sin(np.pi * np.clip(t / d, 0, 1)) ** 2 for f in (1400, 2100, 3150, 4200)) * 0.2
    return x + 0.2 * bp(noise(d), 4000, 10000) * swell(d, 0.6)


SAMPLES = {
    "shutter": shutter, "shutter_clack": shutter_clack, "paper_slide": paper_slide, "paper_flip": paper_flip,
    "stamp": stamp, "marker_scratch": marker_scratch, "marker_swipe": marker_swipe, "type_tick": type_tick,
    "type_burst": type_burst, "whoosh_soft": whoosh_soft, "whoosh": whoosh, "whoosh_zoom": whoosh_zoom,
    "sub_hit": sub_hit, "flash_hit": flash_hit, "impact": impact, "star_tick": star_tick, "star_slam": star_slam,
    "final_hit": final_hit, "pop": pop, "alarm_blip": alarm_blip, "siren_swell": siren_swell, "tab_slide": tab_slide,
    "glitch_tick": glitch_tick, "shimmer_swell": shimmer_swell,
}


def main():
    global rng
    if "--seed" in sys.argv: rng = np.random.default_rng(int(sys.argv[sys.argv.index("--seed") + 1]))
    OUT.mkdir(exist_ok=True)
    for name, fn in SAMPLES.items():
        y = np.asarray(fn(), dtype=np.float64)
        y = hp(y, 25, 1)                      # remove DC / rumble below the sub band
        y[-int(0.004 * SR):] *= np.linspace(1, 0, int(0.004 * SR))  # no end click
        y = y / (np.abs(y).max() + 1e-12) * 10 ** (-3 / 20)
        sf.write(OUT / f"{name}.wav", y.astype(np.float32), SR, subtype="PCM_24")
        print(f"{name:14s} {len(y) / SR:5.2f} s")


if __name__ == "__main__":
    main()
