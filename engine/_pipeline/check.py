#!/usr/bin/env python3
"""Check a rendered Short against its edit list.

    python _pipeline/check.py 01-cops-description/cops-description-silent.mp4 01-cops-description/edl.json
    python _pipeline/check.py <seg>/seg-01-silent.mp4 <seg>/edl.json            # one wide (16:9) segment
    python _pipeline/check.py <long>/out/master-silent.mp4 <long>/longform.json  # joined long video (manifest)

Prints PASS/FAIL lines and writes contact sheets <video stem>-check-NN.jpg next to the video: one frame at the
middle of every clip and at every caption/plate/stars change, with the phone safe zone drawn (red = outside
y300-1580 / x130-950, orange = x>860 inside y1000-1600). Exit code 1 if any FAIL.

Wide (16:9) videos get the same checks against the title-safe zone instead: text inside x 96-1824 / y 54-1000 and
nothing in the top-right 200x120 info-card corner (red = outside, orange = card corner on the sheets). The video is
decoded as a stream (only the sheet frames are kept), so a 10-minute master fits in memory.
"""
import os
import sys

VENV_PY = os.environ.get("SHORTS_PY") or os.path.join(os.environ.get("SHORTS_HOME") or os.path.expanduser("~/.shorts-studio"), "venv", "bin", "python")
try:
    import numpy  # noqa: F401
    import PIL  # noqa: F401
except ImportError:
    if not os.environ.get("_SHORTS_REEXEC") and os.path.exists(VENV_PY):
        os.environ["_SHORTS_REEXEC"] = "1"
        os.execv(VENV_PY, [VENV_PY] + sys.argv)
    raise SystemExit("numpy and Pillow are missing: run scripts/setup.sh once (it creates $SHORTS_HOME/venv) or set SHORTS_PY=<python with numpy+Pillow>")

import json
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shortkit as K  # noqa: E402


def _edl_format(argv):
    """Set before themes is imported (it binds W and H at import time). A manifest (with "segments") is wide."""
    if len(argv) > 2 and os.path.exists(argv[2]):
        with open(argv[2]) as fh:
            d = json.load(fh)
        return "wide" if "segments" in d else d.get("format", "vertical")
    return "vertical"


K.set_format(_edl_format(sys.argv))
import themes as T  # noqa: E402

if K.FORMAT == "wide":
    import wide  # noqa: E402

TW, TH = (270, 480) if K.FORMAT == "vertical" else (480, 270)  # tile size (quarter scale)
FREEZE_MAX = 0.3  # seconds of identical frames allowed
results = []


def report(ok, what):
    results.append(ok)
    print(f"{'PASS' if ok is True else 'FAIL' if ok is False else 'INFO'}  {what}")


def load_segment(edl_path):
    edl = K.load_edl(edl_path)
    return edl


def make_theme(name, edl):
    return wide.make(name, edl) if K.FORMAT == "wide" else T.make(name, edl)


def probe_video(video):
    pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                    "stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt,nb_frames:"
                                    "format=duration", "-of", "json", video],
                                   capture_output=True, text=True, check=True).stdout)
    v = next(s for s in pr["streams"] if s["codec_type"] == "video")
    return pr, v, float(pr["format"]["duration"]), int(v.get("nb_frames", 0))


def container_checks(pr, v, dur, nb, total, expect_s, what):
    report(v["width"] == K.W and v["height"] == K.H, f"resolution {v['width']}x{v['height']}")
    report(v["r_frame_rate"] == "30/1", f"frame rate {v['r_frame_rate']}")
    report(v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p", f"codec {v['codec_name']} {v['pix_fmt']}")
    report(nb == total and abs(dur - expect_s) <= 1.5 / K.FPS, f"duration {dur:.3f}s, {nb} frames ({what} = {total} frames)")
    audio = [s for s in pr["streams"] if s["codec_type"] == "audio"]
    report(None, f"audio streams in this file: {len(audio)} ({'silent master' if not audio else audio[0]['codec_name']})")


def pixel_policy(clips, theme, offset=0, label=""):
    """<= 1.0x for 4K/square and 720p sources, <= 1.25x for 1080p sources (lead review)."""
    print("\nclip  start-end        src res     layout  max out/src px  limit  source" + label)
    for c in clips:
        sc = K.clip_scale(c, theme)
        info = c["info"]
        lim = K.scale_limit(info)
        print(f"{c['id']:5} {(c['f0'] + offset) / 30:5.2f}-{(c['f1'] + offset) / 30:5.2f}s  {info['w']}x{info['h']:<5} "
              f"{c['layout']:7} {sc:5.3f}           {lim:4.2f}   {c['src']} @ {c.get('in', 0)}")
        report(sc <= lim + 1e-6, f"{c['id']} scale {sc:.3f} (limit {lim:.2f})")


def decode(video, keep):
    """Stream the video at tile size: per-frame 10x10-block luma (for still detection), first-frame luma and the
    tiles listed in keep (contact-sheet frames)."""
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", video, "-vf", f"scale={TW}:{TH}:flags=area", "-f",
                             "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    size = TW * TH * 3
    grays, tiles, first, n = [], {}, None, 0
    while True:
        b = proc.stdout.read(size)
        if len(b) < size:
            break
        fr = np.frombuffer(b, np.uint8).reshape(TH, TW, 3)
        if first is None:
            first = fr.mean()
        grays.append(fr.astype(np.float32).mean(2).reshape(TH // 10, 10, TW // 10, 10).mean((1, 3)))
        if n in keep:
            tiles[n] = fr.copy()
        n += 1
    if proc.wait() != 0:
        raise RuntimeError(f"decode of {video} failed")
    return np.stack(grays), tiles, first


def still_checks(gray, first, cuts):
    diff = np.abs(np.diff(gray, axis=0)).mean((1, 2))
    still = diff < 0.6
    runs, run = [], 0
    for i, s in enumerate(still):
        run = run + 1 if s else 0
        if run == 1:
            runs.append([i, 1])
        elif run > 1:
            runs[-1][1] = run
    worst = max([r[1] for r in runs] or [0])
    bad = [(r[0] / 30, (r[1] + 1) / 30) for r in runs if (r[1] + 1) / 30 > FREEZE_MAX]
    report(not bad, f"no frozen stills > {FREEZE_MAX}s (longest identical run {(worst + 1) / 30 if worst else 0:.2f}s"
                    f"{'; at ' + ', '.join(f'{a:.2f}s for {b:.2f}s' for a, b in bad) if bad else ''})")
    for f in cuts:
        prev_run = diff[max(0, f - 10):f - 1]
        next_run = diff[f:f + 9]
        if (prev_run < 0.6).all() or (next_run < 0.6).all():
            report(False, f"cut at {f / 30:.2f}s sits next to a still picture")
    report(None, "cut-frame change (mean |diff| of 27x48 luma): " +
           ", ".join(f"{f / 30:.2f}s={diff[f - 1]:.1f}" for f in cuts))
    report(first > 20 and diff[:10].mean() > 0.6,
           f"first frame is moving footage (mean luma {first:.0f}, motion {diff[:10].mean():.1f})")


def zone_checks(logs, what):
    viol = []
    for fi, boxes in enumerate(logs):
        for n, x0, y0, x1, y1 in boxes:
            for why in K.zone_violations((x0, y0, x1, y1)):
                viol.append((fi, n, why, (x0, y0, x1, y1)))
    ext = {}
    for boxes in logs:
        for n, x0, y0, x1, y1 in boxes:
            k = n.rstrip("0123456789")
            e = ext.setdefault(k, [1e9, 1e9, -1e9, -1e9])
            ext[k] = [min(e[0], x0), min(e[1], y0), max(e[2], x1), max(e[3], y1)]
    report(not viol, f"all text inside the safe zone in all {len(logs)} frames"
                     + (f": {len(viol)} violations, first {viol[:3]}" if viol else ""))
    report(None, f"text extents over the whole {what}: " +
           "; ".join(f"{k} x{a:.0f}-{c:.0f} y{b:.0f}-{d:.0f}" for k, (a, b, c, d) in sorted(ext.items())))


def shorts_marks(edl, clips, groups):
    marks = [((c["f0"] + c["f1"]) // 2, f"{c['id']} mid") for c in clips]
    for g in groups:
        marks.append((K.frames(g["start"] + 0.25), "cap " + " ".join(w["text"] for w in g["words"])))
    hk = edl.get("hook")
    if hk:
        marks += [(0, "hook frame 0"), (K.frames(0.3), "hook landed"), (K.frames(hk["end"]) - 2, "hook out")]
    hero = edl.get("hero")
    if hero:
        marks += [(K.frames(hero["t"]) + 9, "hero")]
        if hero.get("split"):
            marks += [(K.frames(hero["split"]["start"]) + 8, "split (panel theme)")]
    st = edl.get("stars")
    if st:
        marks += [(K.frames(st["ticks"][0]) + 3, "star 1"), (K.frames(st["ticks"][-1]) + 6, "star 5"),
                  (K.frames(st["slam"]) + 2, "6th star slam"), (K.frames(st["slam"]) + 12, "six")]
    return marks


def wide_marks(edl, clips, total, offset=0, tag=""):
    """Sheet frames for a wide segment: every clip middle and each graphic once it has landed."""
    m = [((c["f0"] + c["f1"]) // 2, f"{c['id']} mid") for c in clips]
    ev = []
    if edl.get("card"):
        ev += [(0.0, "card frame 0"), (0.6, "case card"), (edl["card"]["end"] + 0.15, "redact reveal")]
    for hd in wide.headers(edl):
        ev += [(hd["t"] + 0.8, "header + lower third")]
    if edl.get("cold_title"):
        ev += [(edl["cold_title"]["t"] + 1.2, "title")]
    ev += [(s["t"] + 1.0, "source plate") for s in edl.get("source_plates", [])]
    ev += [(q["t"] + 0.4, "quote typing") for q in edl.get("quotes", [])]
    ev += [(q["end"] - 0.4, "quote typed") for q in edl.get("quotes", [])]
    ev += [(n["t"] + 1.6, "note card") for n in edl.get("notes", [])]
    ev += [(c["t"] + 0.6, "red circle") for c in edl.get("circles", [])]
    if edl.get("verdict"):
        ev += [(edl["verdict"]["t"] + 0.05, "verdict slam"), (edl["verdict"]["t"] + 0.8, "verdict")]
    if edl.get("end_card"):
        ev += [(edl["end_card"]["t"] + 1.0, "end card")]
    m += [(K.frames(t), n) for t, n in ev]
    m += [(total - 2, "segment end")]
    return [(f + offset, (tag + n)) for f, n in m if 0 <= f < total]


def sheets(video, marks, tiles):
    fnt = ImageFont.load_default(13)
    per = 24
    stem = os.path.splitext(video)[0]
    sx = TW / K.W
    for sheet in range(0, len(marks), per):
        chunk = marks[sheet:sheet + per]
        cols = 8 if K.FORMAT == "vertical" else 6
        rows = (len(chunk) + cols - 1) // cols
        S = Image.new("RGB", (cols * TW, rows * (TH + 34)), (20, 20, 20))
        d = ImageDraw.Draw(S)
        for k, (f, name) in enumerate(chunk):
            tile = Image.fromarray(tiles[f]).convert("RGBA")
            ov = Image.new("RGBA", tile.size, (0, 0, 0, 0))
            o = ImageDraw.Draw(ov)
            red, orange = (255, 0, 0, 70), (255, 140, 0, 80)
            if K.FORMAT == "vertical":
                o.rectangle([0, 0, TW, K.SAFE["y0"] * sx], fill=red)
                o.rectangle([0, K.SAFE["y1"] * sx, TW, TH], fill=red)
                o.rectangle([0, K.SAFE["y0"] * sx, K.SAFE["x0"] * sx, K.SAFE["y1"] * sx], fill=red)
                o.rectangle([K.SAFE["x1"] * sx, K.SAFE["y0"] * sx, TW, K.SAFE["y1"] * sx], fill=red)
                o.rectangle([K.SAFE["low_x1"] * sx, K.SAFE["low_y0"] * sx, K.SAFE["x1"] * sx, K.SAFE["y1"] * sx],
                            fill=orange)
            else:
                z = K.SAFE_WIDE
                o.rectangle([0, 0, TW, z["y0"] * sx], fill=red)
                o.rectangle([0, z["y1"] * sx, TW, TH], fill=red)
                o.rectangle([0, z["y0"] * sx, z["x0"] * sx, z["y1"] * sx], fill=red)
                o.rectangle([z["x1"] * sx, z["y0"] * sx, TW, z["y1"] * sx], fill=red)
                o.rectangle([z["card_x0"] * sx, z["y0"] * sx, z["x1"] * sx, z["card_y1"] * sx], fill=orange)
            tile = Image.alpha_composite(tile, ov).convert("RGB")
            x, y = (k % cols) * TW, (k // cols) * (TH + 34)
            S.paste(tile, (x, y + 34))
            d.text((x + 4, y + 2), f"{f / 30:.2f}s f{f}", fill=(255, 225, 26), font=fnt)
            d.text((x + 4, y + 17), name[:40 if K.FORMAT == "vertical" else 70], fill=(230, 230, 230), font=fnt)
        out = f"{stem}-check-{sheet // per + 1:02d}.jpg"
        S.save(out, quality=88)
        print(f"sheet {out}")


def check_segment(video, edl_path):
    edl = load_segment(edl_path)
    side = video + ".overlay.json"
    theme_name = json.load(open(side)).get("theme", "classic") if os.path.exists(side) else edl.get("theme", "classic")
    theme = make_theme(theme_name, edl)
    clips, total = K.timeline(edl, theme)
    theme.clips = clips
    groups = theme.groups
    report(None, f"theme {theme_name}" + (" (wide 16:9)" if K.FORMAT == "wide" else ""))

    # 1. container facts
    pr, v, dur, nb = probe_video(video)
    if edl.get("vo"):
        vo = K.wav_duration(K.rel(edl, edl["vo"]))
        what = f"voice-over {vo:.3f}s + tail {edl.get('tail', 0.6)}s"
    else:
        what = f"fixed duration {edl['duration']}s"
    container_checks(pr, v, dur, nb, total, K.segment_seconds(edl), what)

    # 2. pixel policy
    pixel_policy(clips, theme)
    trs = [f"{c['id']}:{c['_tr']}" for c in clips[1:] if c["_tr"] != "cut"]
    report(None, "transitions: " + ", ".join(trs) + " (whip16/zoom/zoom15 scale the finished frame for a few "
                 "transition frames under blur or flash; resting picture follows the limits above)")

    # 3. decode once at tile size (streamed)
    if K.FORMAT == "vertical":
        marks = shorts_marks(edl, clips, groups)
    else:
        marks = wide_marks(edl, clips, total)
    keep = {f for f, _ in marks}
    gray, tiles, first = decode(video, keep)
    still_checks(gray, first, [c["f0"] for c in clips[1:]])

    # 4. text inside the safe zone (boxes logged by build.py for every frame)
    if os.path.exists(side):
        zone_checks(json.load(open(side))["frames"], "Short" if K.FORMAT == "vertical" else "segment")
    else:
        report(False, f"missing {side} (render with build.py)")

    # 5. contact sheets
    marks = sorted({f: n for f, n in marks if 0 <= f < len(gray)}.items())
    sheets(video, marks, tiles)


def check_manifest(video, man_path):
    """Joined long video: the same checks over the whole master, segment by segment where they need an edit list."""
    man = json.load(open(man_path))
    root = os.path.dirname(os.path.abspath(man_path))
    report(None, f"long video, {len(man['segments'])} segments (wide 16:9)")
    segs, offset, marks, cuts = [], 0, [], []
    for sg in man["segments"]:
        edl = K.load_edl(os.path.join(root, sg["edl"]))
        theme = make_theme(edl.get("theme", "case-file"), edl)
        clips, total = K.timeline(edl, theme)
        theme.clips = clips
        segs.append((sg, edl, theme, clips, total, offset))
        marks += wide_marks(edl, clips, total, offset, f"{sg['id']}: ")
        cuts += [offset + c["f0"] for c in clips[1:]] + ([offset] if offset else [])
        offset += total
    pr, v, dur, nb = probe_video(video)
    container_checks(pr, v, dur, nb, offset, offset / K.FPS, "sum of " + " + ".join(
        f"{sg['id']} {total / K.FPS:.2f}s" for sg, _, _, _, total, _ in segs))
    for sg, edl, theme, clips, total, off in segs:
        pixel_policy(clips, theme, off, f"   [{sg['id']}]")
    keep = {f for f, _ in marks}
    gray, tiles, first = decode(video, keep)
    seg_cuts = [c for c in cuts if c not in [off for *_, off in segs]]
    still_checks(gray, first, seg_cuts)
    report(None, "segment joins at " + ", ".join(f"{off / 30:.2f}s" for *_, off in segs[1:]))
    side = video + ".overlay.json"
    if os.path.exists(side):
        logs = json.load(open(side))["frames"]
        report(len(logs) == offset, f"overlay log covers {len(logs)} of {offset} frames")
        zone_checks(logs, "long video")
    else:
        report(False, f"missing {side} (join with longform.py)")
    marks = sorted({f: n for f, n in marks if 0 <= f < len(gray)}.items())
    sheets(video, marks, tiles)


def main():
    video, path = sys.argv[1], sys.argv[2]
    with open(path) as fh:
        is_manifest = "segments" in json.load(fh)
    (check_manifest if is_manifest else check_segment)(video, path)
    fails = sum(1 for r in results if r is False)
    print(f"\n{'ALL CHECKS PASS' if not fails else f'{fails} FAIL'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
