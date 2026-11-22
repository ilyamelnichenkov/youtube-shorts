#!/usr/bin/env python3
"""Build a clip-based vertical Short from an edit list in one of the look themes.

    python3 _pipeline/build.py <short>/edl.json [--theme case-file]          # render + vo mux + sfx cues
    python3 _pipeline/build.py <short>/edl.json --theme vice-dusk --stills 0,1.4,19.6   # PNGs only (fast look)
    python3 _pipeline/build.py <short>/edl.json --words                     # caption word indices
    python3 _pipeline/build.py <seg>/edl.json --stills 2,9.5 --out <dir>      # stills somewhere else than <edl dir>/_stills

An edit list with "format": "wide" renders 1920x1080 long-form segments (wide.py: case-file graphics, title-safe
zone, fixed-bitrate encode so segments join without re-encoding; see longform.py).

Themes: classic, case-file, panel-heist, vice-dusk (themes.py). Without --theme the EDL's "theme" is used.
Outputs (EDL paths, "{theme}" replaced): silent mp4, mp4 with the voice-over, sfx cues, <silent>.overlay.json.
"""
import os
import sys

VENV_PY = os.environ.get("SHORTS_PY") or os.path.join(os.environ.get("SHORTS_HOME") or os.path.expanduser("~/.shorts-studio"), "venv", "bin", "python")
try:
    import numpy  # noqa: F401
    import PIL  # noqa: F401
except ImportError:  # re-run under the venv that has numpy + Pillow (nothing is installed by this project)
    if not os.environ.get("_SHORTS_REEXEC") and os.path.exists(VENV_PY):
        os.environ["_SHORTS_REEXEC"] = "1"
        os.execv(VENV_PY, [VENV_PY] + sys.argv)
    raise SystemExit("numpy and Pillow are missing: run scripts/setup.sh once (it creates $SHORTS_HOME/venv) or set SHORTS_PY=<python with numpy+Pillow>")

import json
import subprocess
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shortkit as K  # noqa: E402


def _edl_format(argv):
    """The format must be set before themes is imported (it binds W and H at import time)."""
    if len(argv) > 1 and argv[1].endswith(".json") and os.path.exists(argv[1]):
        with open(argv[1]) as fh:
            return json.load(fh).get("format", "vertical")
    return "vertical"


K.set_format(_edl_format(sys.argv))
import themes as T  # noqa: E402

if K.FORMAT == "wide":
    import wide  # noqa: E402


class Renderer:
    def __init__(self, edl, theme_name):
        self.edl = edl
        self.theme = wide.make(theme_name, edl) if K.FORMAT == "wide" else T.make(theme_name, edl)
        self.clips, self.total = K.timeline(edl, self.theme)
        self.theme.clips = self.clips
        self.theme.renderer = self
        self.sources = {}
        self.last = {}

    def src(self, i):
        if i not in self.sources:
            self.sources[i] = K.Source(self.clips[i])
        return self.sources[i]

    def release(self, f):
        for i in list(self.sources):
            c = self.clips[i]
            if f >= c["f1"] + c["post"]:
                self.sources.pop(i).close()

    def clip_frame(self, i, f):
        c = self.clips[i]
        img = K.render_clip_frame(c, self.src(i), (f - c["f0"]) / K.FPS, self.theme)
        if f < c["f1"]:
            self.last[c["id"]] = img
        return img

    def clip_frame_id(self, cid, f):
        return self.clip_frame(next(i for i, c in enumerate(self.clips) if c["id"] == cid), f)

    def last_frame_id(self, cid):
        if cid not in self.last:  # e.g. a --stills render that starts after the clip: decode its last frame
            i = next(i for i, c in enumerate(self.clips) if c["id"] == cid)
            c = self.clips[i]
            s = K.Source(c)
            self.last[cid] = K.render_clip_frame(c, s, (c["f1"] - c["f0"] - 1) / K.FPS, self.theme)
            s.close()
        return self.last[cid]

    def base_frame(self, f):
        hero = self.theme.base_hero(self, f)
        i = next(k for k, c in enumerate(self.clips) if c["f0"] <= f < c["f1"])
        if hero is not None:
            img = hero
        else:
            img = None
            for j in (i, i + 1):
                if 1 <= j < len(self.clips):
                    kind, cut = self.clips[j]["_tr"], self.clips[j]["f0"]
                    k = T.OVERLAP.get(kind, 0)
                    if k and cut - k <= f < cut + k:
                        img = self.theme.overlap_frame(kind, f, cut, k, lambda ff: self.clip_frame(j - 1, ff),
                                                       lambda ff: self.clip_frame(j, ff))
            if img is None:
                img = self.clip_frame(i, f)
        for j in (i, i + 1):
            if 1 <= j < len(self.clips):
                img = self.theme.post_cut(self.clips[j]["_tr"], img, f - self.clips[j]["f0"])
        return img

    def frame(self, f):
        self.theme.frame_text = []
        t = f / K.FPS
        img = self.base_frame(f)
        img = self.theme.post_base(img, t)
        img = self.theme.grade(img, f)
        img, log = self.theme.overlay(img, t)
        log += self.theme.frame_text
        self.release(f + 1)
        return img, log


def sfx_cues(edl, r):
    names = {"whip": "whoosh", "whip16": "whoosh", "zoom": "whoosh-zoom", "zoom15": "whoosh-zoom",
             "flash": "flash-hit", "flash2": "flash-hit", "gutter": "panel-slam", "skew": "paper-swipe",
             "shutter": "shutter-clack", "redact": "marker-swipe", "leak": "shimmer-swell", "chroma": "glitch-tick"}
    cues = []
    for c in r.clips[1:]:
        kind, t = c["_tr"], c["f0"] / K.FPS
        if kind == "cut":
            cues.append({"t": round(t - 0.06, 2), "kind": "whoosh-soft", "note": f"hard cut into {c['id']}"})
        else:
            cues.append({"t": round(t - 0.12, 2), "kind": names.get(kind, kind),
                         "note": f"{kind} transition into {c['id']} ({c.get('note', '')})"})
    st = edl.get("stars")
    if st:
        for k, t in enumerate(st["ticks"]):
            cues.append({"t": round(t, 2), "kind": "star-tick", "note": f"star {k + 1} of 5 pops"})
        cues.append({"t": round(st["slam"], 2), "kind": "star-slam", "note": "sixth slot and star arrive on 'six'"})
    cues.append({"t": 0.1, "kind": "impact", "note": f"hook plate lands ({r.theme.name})"})
    cues += edl.get("sfx_extra", [])
    cues.sort(key=lambda c: c["t"])
    return cues


def encode_to_size(src, dst, target_mb, dur):
    """Two-pass x264 from the lossless-ish intermediate so the master lands near target_mb."""
    kbps = int(target_mb * 8 * 1024 / dur * 0.97)
    logdir = tempfile.mkdtemp(prefix="x264pass-")
    plog = os.path.join(logdir, "pass")
    common = ["-c:v", "libx264", "-preset", "slow", "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.6)}k",
              "-bufsize", f"{kbps * 2}k", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
              "-colorspace", "bt709", "-passlogfile", plog]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-an", *common, "-pass", "1", "-f", "mp4", os.devnull],
                   check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-an", *common, "-pass", "2", "-movflags", "+faststart",
                    dst], check=True)
    for fn in os.listdir(logdir):
        os.remove(os.path.join(logdir, fn))
    os.rmdir(logdir)


def main():
    args = sys.argv[1:]
    edl = K.load_edl(args[0])
    theme = args[args.index("--theme") + 1] if "--theme" in args else edl.get("theme", "classic")
    if "--words" in args:
        for w in K.caption_words(edl):
            print(f"{w['i']:3d}  {w['s']:6.2f}  {w['text']}")
        return
    if "--cover" in args and K.FORMAT == "wide":  # 1280x720 YouTube thumbnail from the EDL's cover block
        out = K.rel(edl, edl["cover"].get("out", "thumbnail.jpg"))
        size, log, viol = wide.make_thumbnail(edl, out)
        print(f"{out}: 1280x720, {size / 1e6:.2f} MB, {len(log)} text boxes, problems: {viol or 'none'}")
        if viol or size > 2e6:
            sys.exit(1)
        return
    if "--cover" in args:  # cover-<theme>.jpg from the EDL's cover block (JPEG q93, must stay under 2 MB)
        import covers
        th = T.make(theme, edl)
        im, log, viol = covers.make_cover(edl, th)
        out = K.rel(edl, edl["cover"].get("out", "cover-{theme}.jpg").replace("{theme}", theme))
        im.save(out, quality=93)
        size = os.path.getsize(out)
        print(f"{out}: {size / 1e6:.2f} MB, {len(log)} text boxes, safe-zone violations: {viol or 'none'}")
        if viol or size > 2e6:
            sys.exit(1)
        return
    if "--stills" in args:
        from PIL import Image
        ts = [float(x) for x in args[args.index("--stills") + 1].split(",")]
        outdir = args[args.index("--out") + 1] if "--out" in args else K.rel(edl, "_stills")
        os.makedirs(outdir, exist_ok=True)
        for t in ts:
            rr = Renderer(edl, theme)
            img, _ = rr.frame(K.frames(t))
            p = os.path.join(outdir, f"{theme}-{t:06.2f}.png")
            if "--out" in args and K.FORMAT == "wide":
                p = os.path.join(outdir, f"{os.path.basename(edl['_dir'])}-{t:06.2f}.png")
            Image.fromarray(img).save(p)
            for s in rr.sources.values():
                s.close()
            print(p)
        return

    r = Renderer(edl, theme)
    out_silent = K.out_path(edl, "out_silent", theme)
    tmp = out_silent + ".master.mkv"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                            f"{K.W}x{K.H}", "-r", str(K.FPS), "-i", "-", "-an", "-c:v", "libx264", "-preset",
                            "veryfast", "-crf", "8", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    logs = []
    t0 = time.time()
    for f in range(r.total):
        img, log = r.frame(f)
        enc.stdin.write(img.tobytes())
        logs.append([[n, round(a, 1), round(b, 1), round(c, 1), round(d, 1)] for n, a, b, c, d in log])
        if f % 90 == 0:
            print(f"[{theme}] frame {f}/{r.total}  {time.time() - t0:.0f}s", flush=True)
    enc.stdin.close()
    if enc.wait() != 0:
        sys.exit("encoder failed")
    t_frames = time.time() - t0
    if K.FORMAT == "wide":
        wide.encode_segment(tmp, out_silent)
    else:
        encode_to_size(tmp, out_silent, edl.get("target_mb", 50), r.total / K.FPS)
    os.remove(tmp)
    with open(out_silent + ".overlay.json", "w") as fh:
        json.dump({"fps": K.FPS, "theme": theme, "frames": logs}, fh)
    out_vo = K.out_path(edl, "out_vo", theme) if edl.get("vo") and edl.get("out_vo") else "(no voice-over)"
    if edl.get("vo") and edl.get("out_vo"):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", out_silent, "-i", K.rel(edl, edl["vo"]), "-map", "0:v",
                        "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-af", "apad", "-shortest",
                        "-movflags", "+faststart", out_vo], check=True)
    cues = wide.sfx_cues(edl, r) if K.FORMAT == "wide" else sfx_cues(edl, r)
    with open(K.out_path(edl, "sfx_out", theme), "w") as fh:
        json.dump(cues, fh, indent=2, ensure_ascii=False)
    print(f"[{theme}] done: frames {t_frames:.0f}s, total {time.time() - t0:.0f}s -> {out_silent}, {out_vo}")


if __name__ == "__main__":
    main()
