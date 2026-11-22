"""Reusable sound step for the clip-based Shorts (voice, music bed, synthesised sfx, -14 LUFS).

  $SHORTS_HOME/venv/bin/python _pipeline/sound/mix.py <short-folder> [--theme case-file]
        [--music trip-hop|the-chase|trap-suspense|<file>] [--music-offset S] [--no-whisper] [--strict]

Reads   <folder>/vo/vo.wav, <folder>/vo/words.json, <folder>/sfx-cues-<theme>.json, <folder>/*-<theme>-silent.mp4
        (+ optional <silent>.mp4.overlay.json and <folder>/edl.json for cues the editor did not list, see cue_map.json "derive")
Writes  <folder>/<name>-<theme>-final.mp4   (video stream copied, AAC 48 kHz stereo 192k)
        <folder>/sound-report.txt           (LUFS, true peak, masking check, whisper transcript, cue map, music credit)

Cue kind -> sound table: cue_map.json (edit it to add kinds; unknown kinds are listed under UNMAPPED, never dropped silently).
SFX: sfx/*.wav from synth_sfx.py (all synthesised). Music: music/music.json (3 CC0 tracks, rotated by folder number).
Needs numpy, scipy, soundfile, pyloudnorm, faster-whisper (the $SHORTS_HOME/venv made by scripts/setup.sh) and ffmpeg.
"""
import argparse, json, os, re, subprocess, sys, tempfile
from math import gcd
from pathlib import Path

import numpy as np, soundfile as sf, pyloudnorm as pyln
from scipy.signal import butter, resample_poly, sosfilt

HERE = Path(__file__).parent
SR = 48000
SHORTS_HOME = os.environ.get("SHORTS_HOME") or os.path.expanduser("~/.shorts-studio")
KOKORO_PY = os.environ.get("KOKORO_PY") or os.path.join(SHORTS_HOME, "venv", "bin", "python")  # needs faster-whisper

TARGET_LUFS = -14.0
TP_LIMIT = -1.0
VO_PEAK_DB = -3.0          # voice peak before the final gain
MUSIC_SPEECH_DB = -18      # music RMS under speech, relative to voice speech RMS
MUSIC_GAP_DB = -10         # in gaps and in the last TAIL_S seconds
TAIL_S = 2.0
MUSIC_WIDEN = 2.5          # side-channel gain for the music
SFX_DUCK_DB = -6           # SFX bus under speech
MASK_MARGIN_DB = -12       # SFX bus may be at most this far under the voice in the 300-4000 Hz band inside a word
KEY_BAND = (300, 4000)


def db(x): return 10 ** (x / 20)
def tdb(x): return 20 * np.log10(max(x, 1e-12))


def load(path, mono=True):
    y, sr = sf.read(path, dtype="float32", always_2d=True)
    y = y.mean(1) if mono else y
    if sr != SR:
        g = gcd(SR, sr); y = resample_poly(y, SR // g, sr // g, axis=0)
    return y.astype(np.float32)


def band(x, lo=KEY_BAND[0], hi=KEY_BAND[1]):
    return sosfilt(butter(4, [lo, hi], "band", fs=SR, output="sos"), x)


def envelope(mask, atk, rel):
    out = np.zeros(len(mask)); v = 0.0
    ka, kr = np.exp(-1 / (atk * SR)), np.exp(-1 / (rel * SR))
    for i, m in enumerate(mask):
        k = ka if m > v else kr
        v = k * v + (1 - k) * m; out[i] = v
    return out


def speech_intervals(vo):
    h = SR // 100; n = len(vo) // h
    rms = np.sqrt((vo[:n * h].reshape(n, h) ** 2).mean(1)); on = rms > np.abs(vo).max() * db(-42)
    iv = []
    for i in np.flatnonzero(on):
        s, e = i / 100, (i + 1) / 100
        if iv and s - iv[-1][1] < 0.3: iv[-1][1] = e
        else: iv.append([s, e])
    return iv


def ffprobe_dur(p):
    return round(float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                      capture_output=True, text=True, check=True).stdout.strip()), 3)


# ---------------------------------------------------------------- cues
def derive_cues(folder, silent, cues, cmap):
    """Overlay-element first appearances and the hook circle from edl.json become extra cues."""
    out = []; d = cmap.get("derive", {})
    ov = Path(str(silent) + ".overlay.json")
    if not ov.exists():  # without it the mix misses the sounds of the red circle, file tab, stamps (about 1 dB of true peak)
        print(f"warning: {ov.name} is missing next to the silent mp4: overlay-derived sound cues are skipped (copy it from the render folder)", file=sys.stderr)
    if ov.exists() and d.get("overlay"):
        j = json.load(open(ov)); fps = j["fps"]; frames = j["frames"]
        for i, f in enumerate(frames):
            names = {e[0] for e in f}
            for n in names:
                kind = d["overlay"].get(n)
                if not kind: continue
                if any(n in {e[0] for e in frames[k]} for k in range(max(0, i - 10), i)): continue
                out.append({"t": round(i / fps, 3), "kind": kind, "note": f"overlay '{n}' appears", "derived": True})
    edl = Path(folder) / "edl.json"
    if edl.exists() and d.get("edl_circles"):
        try:
            circ = json.load(open(edl)).get("hook", {}).get("circle")
            if circ: out.append({"t": 0.0, "kind": d["edl_circles"], "dur": float(circ[2][-1][0]), "note": "hook red circle draws", "derived": True})
        except (KeyError, IndexError, TypeError):
            pass
    keep = []
    for q in out:   # skip if the editor already listed this kind nearby
        if not any(c["kind"] == q["kind"] and abs(c["t"] - q["t"]) < 0.3 for c in cues): keep.append(q)
    return keep


def build_layers(cues, cmap):
    """-> (layers, unmapped). Each layer: dict(t, sample, gain_db, pitch, align, pan, duck, dur, kind, note)."""
    layers, unmapped = [], []
    cues = sorted(cues, key=lambda c: c["t"]); last = {}; alt = {}
    for q in cues:
        spec = cmap["kinds"].get(q["kind"])
        if not spec:
            unmapped.append(q); continue
        idx = 0
        if spec.get("ladder_st"):
            idx = last[q["kind"]][1] + 1 if q["kind"] in last and q["t"] - last[q["kind"]][0] < 0.6 else 0
            last[q["kind"]] = (q["t"], idx)
        pan_alt = 0.0
        if spec.get("pan_alt"):   # alternate left/right so repeated cues (cuts) move across the picture
            alt[q["kind"]] = -alt.get(q["kind"], -1); pan_alt = spec["pan_alt"] * alt[q["kind"]]
        for L in spec["layers"]:
            layers.append(dict(t=q["t"] + L.get("dt", 0.0), sample=L["sample"], gain_db=L["gain_db"],
                               pitch=L.get("pitch", 0) + spec.get("ladder_st", 0) * idx, align=L.get("align", "onset"),
                               pan=L.get("pan", 0.0) + pan_alt, duck=L.get("duck", True), dur=q.get("dur") if spec.get("fit_dur") else None,
                               kind=q["kind"], note=q.get("note", "")))
    return layers, unmapped


def render_layer(y, L, N):
    """Place one layer on a stereo float buffer of length N. Returns (buf, start, end) in samples."""
    if L["dur"]:
        up, down = int(round(L["dur"] * 1000)), int(round(len(y) / SR * 1000))
        y = resample_poly(y, up, down)
    if L["pitch"]:
        r = 2 ** (L["pitch"] / 12); y = resample_poly(y, 1000, int(round(1000 * r)))
    y = y / (np.abs(y).max() + 1e-9) * db(L["gain_db"])
    k = int(np.argmax(np.abs(y))); on = int(np.argmax(np.abs(y) > 0.05 * np.abs(y).max()))
    s = int(round(L["t"] * SR)) - {"onset": on, "peak": k, "end": len(y) - 1}[L["align"]]
    buf = np.zeros((N, 2), np.float32); a, b = max(s, 0), min(s + len(y), N)
    if b > a:
        th = (L["pan"] + 1) * np.pi / 4; seg = y[a - s:b - s]
        buf[a:b, 0] = seg * np.cos(th) * 1.414; buf[a:b, 1] = seg * np.sin(th) * 1.414
    return buf, a, b


# ---------------------------------------------------------------- music
def pick_music(folder, arg):
    lib = json.load(open(HERE / "music/music.json"))["tracks"]
    if arg:
        for t in lib:
            if arg in (t["key"], t["file"]): return t
        p = Path(arg)
        if p.exists(): return dict(key=p.stem, file=str(p), title=p.stem, author="?", url="?", license="?", bpm=0, start_s=0.0, mood="custom file")
        sys.exit(f"unknown --music '{arg}' (keys: {[t['key'] for t in lib]})")
    m = re.match(r"(\d+)", Path(folder).resolve().name)
    return lib[(int(m.group(1)) - 1) % len(lib)] if m else lib[0]


def load_music(track, start, N):
    path = Path(track["file"]) if Path(track["file"]).is_absolute() else HERE / "music" / track["file"]
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "m.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-ar", str(SR), "-ac", "2", str(tmp)], check=True)
        m = sf.read(tmp, dtype="float32", always_2d=True)[0]
    m = m[int(start * SR):]
    if len(m) < N:   # loop with a 0.4 s equal-power crossfade
        xf = int(0.4 * SR); out = m.copy()
        while len(out) < N + xf:
            a, b = out[-xf:], m[:xf]; w = np.linspace(0, 1, xf)[:, None]
            out = np.concatenate([out[:-xf], a * np.cos(w * np.pi / 2) + b * np.sin(w * np.pi / 2), m[xf:]])
        m = out
    m = m[:N]
    return sosfilt(butter(2, 35, "high", fs=SR, output="sos"), m, axis=0).astype(np.float32)


# ---------------------------------------------------------------- measuring
def ffmpeg_ebur128(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    s = r[r.rindex("Summary:"):]
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", s).group(1)), float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", s).group(1)), float(re.search(r"LRA:\s+([\d.]+) LU", s).group(1))


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder"); ap.add_argument("--theme", default="case-file")
    ap.add_argument("--music"); ap.add_argument("--music-offset", type=float)
    ap.add_argument("--no-whisper", action="store_true"); ap.add_argument("--strict", action="store_true", help="exit 1 if a cue kind is unmapped")
    a = ap.parse_args()
    F = Path(a.folder).resolve(); theme = a.theme
    silents = sorted(F.glob(f"*-{theme}-silent.mp4"))
    if len(silents) != 1: sys.exit(f"need exactly one *-{theme}-silent.mp4 in {F}, found {len(silents)}")
    silent = silents[0]; name = silent.name[:-len(f"-{theme}-silent.mp4")]
    final = F / f"{name}-{theme}-final.mp4"
    cmap = json.load(open(HERE / "cue_map.json"))
    cues = json.load(open(F / f"sfx-cues-{theme}.json"))
    cues_all = cues + derive_cues(F, silent, cues, cmap)
    layers, unmapped = build_layers(cues_all, cmap)
    words = json.load(open(F / "vo/words.json"))

    DUR = ffprobe_dur(silent); N = int(SR * DUR)
    vo = load(F / "vo/vo.wav"); vo = vo / np.abs(vo).max() * db(VO_PEAK_DB)
    voN = np.zeros(N, np.float32); voN[:min(N, len(vo))] = vo[:N]
    iv = speech_intervals(voN)
    mask = np.zeros(N)
    for s, e in iv: mask[int(max(s - 0.14, 0) * SR):int((e + 0.1) * SR)] = 1  # look-ahead so the bed is already down when a word starts after a pause
    on = mask > 0
    rms = lambda x: float(np.sqrt(np.mean(np.square(x))))

    # --- music
    track = pick_music(F, a.music)
    mus = load_music(track, a.music_offset if a.music_offset is not None else track.get("start_s", 0.0), N)
    mmask = mask.copy(); mmask[-int(TAIL_S * SR):] = 0
    gain_env = db(MUSIC_GAP_DB - MUSIC_SPEECH_DB) ** (1 - envelope(mmask, 0.04, 0.35))
    mid_, side_ = (mus[:, 0] + mus[:, 1]) / 2, (mus[:, 0] - mus[:, 1]) / 2     # previews are near-mono: widen the side channel
    mus = np.stack([mid_ + MUSIC_WIDEN * side_, mid_ - MUSIC_WIDEN * side_], 1).astype(np.float32)
    mus = mus * (rms(voN[on]) * db(MUSIC_SPEECH_DB) / rms(mus.mean(1)[on]))
    fade = np.ones(N); fi, fo = int(0.4 * SR), int(1.5 * SR)
    fade[:fi] = np.linspace(0, 1, fi); fade[-fo:] = np.linspace(1, 0, fo) ** 1.5
    mus = (mus * (gain_env * fade)[:, None]).astype(np.float32)

    # --- sfx bus, one cue layer at a time so masking can be fixed per cue
    duck = db(SFX_DUCK_DB) ** envelope(mask, 0.03, 0.25)
    samples = {}
    for L in layers:
        if L["sample"] not in samples:
            p = HERE / f"sfx/{L['sample']}.wav"
            if not p.exists(): sys.exit(f"missing sample {p} (run synth_sfx.py)")
            samples[L["sample"]] = load(p)
    voB = band(voN)
    h = SR // 100; r10 = np.sqrt((voN[:N // h * h].reshape(-1, h) ** 2).mean(1))
    voiced = np.repeat(r10 > np.abs(voN).max() * db(-42), h); voiced = np.pad(voiced, (0, N - len(voiced)))  # word timings are approximate: judge only voiced samples
    wins = [(int(w["s"] * SR), int(w["e"] * SR), w["w"]) for w in words]
    sfx = np.zeros((N, 2), np.float32)
    for L in layers:
        for _ in range(4):
            buf, s0, e0 = render_layer(samples[L["sample"]], L, N)
            if L["duck"]: buf *= duck[:, None]
            worst = -99.0
            for ws, we, w in wins:
                lo, hi = max(ws, s0), min(we, e0)
                if hi - lo < int(0.02 * SR) or voiced[lo:hi].sum() < int(0.02 * SR): continue
                vm = voiced[lo:hi]
                lvl = tdb(rms(band(buf[lo:hi].mean(1))[vm])); ref = tdb(rms(voB[ws:we][voiced[ws:we]]))
                worst = max(worst, lvl - ref)
            L["masking_db"] = round(worst, 1)
            if worst <= MASK_MARGIN_DB: break
            L["gain_db"] -= worst - MASK_MARGIN_DB + 0.5; L["cut"] = round(L.get("cut", 0) + worst - MASK_MARGIN_DB + 0.5, 1)
        sfx += buf

    # --- per-word band-energy margin of the whole non-voice bed (music + sfx) vs voice
    bed = (mus + sfx).mean(1); bedB = band(bed)
    musB, sfxB = band(mus.mean(1)), band(sfx.mean(1))
    margins = sorted(((tdb(rms(bedB[ws:we][vm])) - tdb(rms(voB[ws:we][vm])), w, ws / SR, tdb(rms(musB[ws:we][vm])) - tdb(rms(voB[ws:we][vm])), tdb(rms(sfxB[ws:we][vm])) - tdb(rms(voB[ws:we][vm]))) for ws, we, w in wins if voiced[ws:we].sum() > int(0.06 * SR) for vm in [voiced[ws:we]]), reverse=True)

    mix = np.stack([voN, voN], 1) + mus + sfx

    # --- loudness loop on the DECODED final mp4
    meter = pyln.Meter(SR); g = TARGET_LUFS - meter.integrated_loudness(mix); limit = 0.84
    with tempfile.TemporaryDirectory() as td:
        raw, lim = Path(td) / "pre.wav", Path(td) / "lim.wav"
        for it in range(12):
            sf.write(raw, (mix * db(g)).astype(np.float32), SR, subtype="FLOAT")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", f"alimiter=limit={limit}:attack=3:release=60:level=disabled",
                            "-ar", str(SR), "-c:a", "pcm_f32le", str(lim)], check=True)
            out = sf.read(lim, dtype="float32")[0][:N]
            wav = Path(td) / "mix.wav"; sf.write(wav, out, SR, subtype="PCM_24")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(wav), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                            "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-ac", "2", "-t", f"{DUR:.3f}", "-movflags", "+faststart", str(final)], check=True)
            lufs, tp, lra = ffmpeg_ebur128(final)
            print(f"iter {it}: gain {g:+.2f} dB limit {limit:.2f} -> {lufs:.2f} LUFS, TP {tp:.2f} dBTP")
            ok_l, ok_t = abs(lufs - TARGET_LUFS) <= 0.3, tp <= TP_LIMIT - 0.05
            if ok_l and ok_t: break
            if tp > TP_LIMIT - 0.05: limit = max(0.3, limit - 0.04)
            g += TARGET_LUFS - lufs

    dec = decode(final); clipped = int((np.abs(dec) >= 0.999).sum())
    voice_peak_db = tdb(np.abs(voN).max())

    # --- whisper
    wh = None
    if not a.no_whisper:
        with tempfile.TemporaryDirectory() as td:
            wp = Path(td) / "dec.wav"; sf.write(wp, dec, SR)
            r = subprocess.run([KOKORO_PY, str(HERE / "check_transcript.py"), str(wp), str(F / "vo/words.json")], capture_output=True, text=True)
            try: wh = json.loads(r.stdout.strip().splitlines()[-1])
            except Exception: wh = {"error": (r.stderr or r.stdout)[-400:]}

    # --- report
    L_ = []
    L_.append(f"SOUND REPORT  {final.name}   theme {theme}   duration {DUR:.3f} s")
    L_.append(f"Measured on the decoded final mp4 (ffmpeg ebur128): integrated {lufs:.2f} LUFS (target {TARGET_LUFS} +/-0.5), true peak {tp:.2f} dBTP (limit {TP_LIMIT}), LRA {lra:.1f} LU, clipped samples {clipped}")
    L_.append(f"Voice peak before the final gain {voice_peak_db:.1f} dBFS; final gain {g:+.2f} dB; limiter ceiling {limit:.2f}")
    L_.append(f"Music: {track['title']} by {track['author']} - {track['url']} - {track['license']} ({track.get('mood', '')}); start {a.music_offset if a.music_offset is not None else track.get('start_s', 0.0)} s; "
              f"{MUSIC_SPEECH_DB} dB under speech RMS, {MUSIC_GAP_DB} dB in gaps and in the last {TAIL_S:.0f} s")
    L_.append(f"SFX bus ducked {SFX_DUCK_DB} dB under speech; masking rule: bus at most {MASK_MARGIN_DB} dB under the voice in {KEY_BAND[0]}-{KEY_BAND[1]} Hz inside any word (cue gain is cut automatically otherwise)")
    L_.append("")
    L_.append("UNMAPPED cue kinds: " + (", ".join(sorted({q['kind'] for q in unmapped})) + f"  ({len(unmapped)} cues NOT sounded; add them to cue_map.json)" if unmapped else "none"))
    L_.append(f"Cues in file {len(cues)}, derived from picture {len(cues_all) - len(cues)}, sound layers {len(layers)}")
    L_.append("")
    L_.append("t(s)   kind           -> sample (gain dBFS, pitch st, masking margin dB)   note")
    for L in sorted(layers, key=lambda x: x["t"]):
        L_.append(f"{L['t']:6.2f} {L['kind']:14s} -> {L['sample']:14s} ({L['gain_db']:6.1f}, {L['pitch']:+d}, {L['masking_db']:6.1f}{', cut ' + str(L['cut']) + ' dB' if L.get('cut') else ''})  {'[derived] ' if any(c.get('derived') and abs(c['t'] - L['t']) < 0.05 and c['kind'] == L['kind'] for c in cues_all) else ''}{L['note'][:60]}")
    L_.append("")
    L_.append("Words with the smallest voice-to-bed margin (music+sfx minus voice, 300-4000 Hz, dB; more negative is safer):")
    for m, w, t, mm, sm in margins[:6]: L_.append(f"  {t:6.2f} s  {w:12s} {m:6.1f}  (music {mm:.1f}, sfx {sm:.1f})")
    L_.append("")
    if wh is None: L_.append("Transcript check skipped (--no-whisper)")
    elif "error" in wh: L_.append("Transcript check FAILED to run: " + wh["error"])
    else:
        L_.append(f"faster-whisper small on the decoded final: {wh['word_errors']} word errors of {wh['expected_words']} expected (WER {wh['wer']})")
        L_.append("heard: " + wh["text"])
        L_.append("script: " + " ".join(w["w"] for w in words))
    (F / "sound-report.txt").write_text("\n".join(L_) + "\n")
    print("\n".join(L_))
    if unmapped and a.strict: sys.exit(1)


if __name__ == "__main__":
    main()
