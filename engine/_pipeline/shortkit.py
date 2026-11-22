"""Engine for clip-based vertical Shorts (build.py renders, check.py verifies, themes.py styles).

Everything is computed per output frame from the edit list (EDL) and the theme alone, so a render is deterministic
and any frame can be reproduced. Footage is decoded by ffmpeg (exact-frame seeks, source audio never read), laid out
and graded with numpy/Pillow, and encoded by ffmpeg (h264 yuv420p, 30 fps).

Pixel policy (lead review 2026-11-12): full-bleed crops of 4K/square sources at <= 1.0x source pixels; 1080p sources
in a designed window at <= 1.25x; 720p sources at <= 1.0x (keep them small or avoid them).
"""
import json
import math
import os
import re
import subprocess
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
FORMAT = "vertical"
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.normpath(os.path.join(HERE, "..", "_fonts"))
OLD_FONTS = os.path.join(FONTS, "legacy")  # Anton + Inter for the `classic` theme

# Phone safe zone (memory: shorts-phone-safe-zone). Text must stay inside at rest and in motion.
SAFE = {"x0": 130, "x1": 950, "y0": 300, "y1": 1580, "low_y0": 1000, "low_y1": 1600, "low_x1": 860}
# 16:9 long-form title-safe area: the bottom strip stays free for YouTube's progress bar and subtitles, and the
# top-right 200x120 for the info-card icon.
SAFE_WIDE = {"x0": 96, "x1": 1824, "y0": 54, "y1": 1000, "card_x0": 1720, "card_y1": 120}
FORMATS = {"vertical": (1080, 1920, SAFE), "wide": (1920, 1080, SAFE_WIDE)}


def set_format(name):
    """Switch the engine to "vertical" (Shorts, default) or "wide" (16:9 long-form). Call it before importing
    themes/covers/wide: they bind W and H at import time."""
    global W, H, SAFE, FORMAT
    W, H, SAFE = FORMATS[name]
    FORMAT = name
    vignette_map.cache_clear()


# ----------------------------------------------------------------------------------------------- easing
def clamp(v, a=0.0, b=1.0):
    return a if v < a else b if v > b else v


def _bezier(x1, y1, x2, y2):
    def f(p):
        p = clamp(p)
        lo, hi = 0.0, 1.0
        for _ in range(40):
            t = (lo + hi) / 2
            x = 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t * t * x2 + t ** 3
            lo, hi = (t, hi) if x < p else (lo, t)
        t = (lo + hi) / 2
        return 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t * t * y2 + t ** 3
    return f


EMIL_OUT = _bezier(0.23, 1, 0.32, 1)


def ease(name, p):
    """GSAP-named curves: power1..4 (in/out/inout), expo.out, back.out(s) via back_out, emil = cubic-bezier(.23,1,.32,1)."""
    p = clamp(p)
    if name == "linear":
        return p
    if name in ("in", "power2.in"):
        return p ** 3 if name == "in" else p ** 3
    if name in ("out", "power2.out"):
        return 1 - (1 - p) ** 3
    if name in ("inout", "power2.inOut"):
        return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2
    if name == "power3.out":
        return 1 - (1 - p) ** 4
    if name == "power3.in":
        return p ** 4
    if name == "power3.inOut":
        return 8 * p ** 4 if p < 0.5 else 1 - (-2 * p + 2) ** 4 / 2
    if name == "power4.out":
        return 1 - (1 - p) ** 5
    if name == "power4.in":
        return p ** 5
    if name == "expo_out" or name == "expo.out":
        return 1.0 if p >= 1 else 1 - 2 ** (-10 * p)
    if name == "emil":
        return EMIL_OUT(p)
    raise ValueError(f"unknown ease {name}")


def back_out(p, s=1.7):
    p = clamp(p) - 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


def lerp(a, b, t):
    return a + (b - a) * t


def pair(v):
    return (float(v[0]), float(v[1])) if isinstance(v, (list, tuple)) else (float(v), float(v))


def is_keys(v):
    return isinstance(v, (list, tuple)) and len(v) > 0 and isinstance(v[0], (list, tuple))


def anim(v, e, t):
    """Scalar, [from, to] (driven by the clip's eased progress e) or keyframes [[t, v], ...] (smooth between keys)."""
    if is_keys(v):
        if t <= v[0][0]:
            return float(v[0][1])
        for (ta, va), (tb, vb) in zip(v, v[1:]):
            if t <= tb:
                return lerp(va, vb, ease("inout", (t - ta) / (tb - ta)))
        return float(v[-1][1])
    a, b = pair(v)
    return lerp(a, b, e)


def values(v):
    return [float(k[1]) for k in v] if is_keys(v) else list(pair(v))


def frames(t):
    return int(round(t * FPS))


# ----------------------------------------------------------------------------------------------- EDL
def load_edl(path):
    with open(path) as fh:
        edl = json.load(fh)
    edl["_dir"] = os.path.dirname(os.path.abspath(path))
    edl["_path"] = os.path.abspath(path)
    return edl


def rel(edl, p):
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(edl["_dir"], p))


def out_path(edl, key, theme):
    return rel(edl, edl[key].replace("{theme}", theme))


def footage(edl, src):
    return os.path.normpath(os.path.join(rel(edl, edl["footage_root"]), src))


STILL_EXT = (".jpg", ".jpeg", ".png", ".webp")


def is_still(path):
    return path.lower().endswith(STILL_EXT)


@lru_cache(maxsize=None)
def probe(path):
    if is_still(path):  # still image (Steam screenshot): no time axis, movement comes from the layout
        with Image.open(path) as im:
            return {"w": im.width, "h": im.height, "fps": float(FPS), "dur": 1e9, "still": True}
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:format=duration", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    s = d["streams"][0]
    n, m = s["r_frame_rate"].split("/")
    return {"w": int(s["width"]), "h": int(s["height"]), "fps": int(n) / int(m), "dur": float(d["format"]["duration"])}


def wav_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def segment_seconds(edl):
    """Voice-over length + tail; an edit list without a voice-over (a silent end card) gives "duration"."""
    if edl.get("vo"):
        return wav_duration(rel(edl, edl["vo"])) + edl.get("tail", 0.6)
    return float(edl["duration"])


SHEET_TEXTURE = None  # set by wide.py: function returning the dossier-sheet image (H x W x 3) for "sheet" clips


def scale_limit(info):
    """Max output/source pixel ratio allowed for a source file."""
    short = min(info["w"], info["h"])
    if short >= 1440:
        return 1.0  # 4K and the 2160 square clips
    if short >= 1000:
        return 1.25  # 1080p
    return 1.0  # 720p


def timeline(edl, theme):
    """Clip list with integer frame ranges [f0, f1), transition handles and theme-resolved freezes."""
    total = frames(segment_seconds(edl))
    clips, f0 = [], 0
    for i, c in enumerate(edl["clips"]):
        f1 = total if i == len(edl["clips"]) - 1 else frames(c["end"])
        if f1 <= f0:
            raise ValueError(f"clip {c.get('id', i)} ends before it starts")
        r = dict(c)
        r["f0"], r["f1"], r["idx"] = f0, f1, i
        if c["layout"] == "sheet":  # no footage: the theme's dossier sheet, moved like a full-bleed still
            if SHEET_TEXTURE is None:
                raise ValueError(f"clip {c.get('id', i)}: layout sheet needs a theme with a sheet texture (wide)")
            th, tw = SHEET_TEXTURE().shape[:2]
            r["path"], r["src"] = None, "(dossier sheet)"
            r["info"] = {"w": tw, "h": th, "fps": float(FPS), "dur": 1e9, "still": True, "sheet": True}
        else:
            r["path"] = footage(edl, c["src"])
            r["info"] = probe(r["path"])
        r["picture"] = c.get("picture") or edl.get("sources", {}).get(r["src"], {}).get("picture") \
            or [0, 0, r["info"]["w"], r["info"]["h"]]
        r["pre"], r["post"] = 0, 0
        if "hero_freeze_at" in c and theme.freeze_hold > 0:
            r["freeze"] = [c["hero_freeze_at"], theme.freeze_hold]
        clips.append(r)
        f0 = f1
    for i, c in enumerate(clips[1:], 1):
        kind = theme.transition_for(c)
        c["_tr"] = kind
        k = theme.handles(kind)
        if k:
            c["pre"] = max(c["pre"], k)
            clips[i - 1]["post"] = max(clips[i - 1]["post"], k)
    clips[0]["_tr"] = "cut"
    theme.extend_handles(clips, edl)
    return clips, total


def by_id(clips, cid):
    return next(c for c in clips if c["id"] == cid)


# ----------------------------------------------------------------------------------------------- geometry
def aspect(c, default="4:5"):
    a = c.get("aspect", default)
    n, m = a.split(":")
    return float(n) / float(m)


def float_offset(c, t):
    """Camera float in output px for still-image clips (or any clip with "float"): two slow sines on x and y, so a
    screenshot keeps moving even where its push or pan is slow. "float": amplitude px, or {"amp", "period"}; stills
    default to 12 px / 4.5 s, "float": 0 switches it off. Clips without the key and not stills: (0, 0)."""
    f = c.get("float")
    if f is None:
        if not c["info"].get("still"):
            return 0.0, 0.0
        f = 12.0
    amp, per = (float(f), 4.5) if not isinstance(f, dict) else (float(f.get("amp", 12)), float(f.get("period", 4.5)))
    if amp <= 0:
        return 0.0, 0.0
    ph = 1.7 * c.get("idx", 0)
    return (amp * math.sin(2 * math.pi * t / per + ph),
            0.6 * amp * math.sin(2 * math.pi * t / (per * 1.37) + 0.8 + ph))


def window_geom(c, t, theme):
    """Window clip geometry at clip-local time t: crop box in source px and the window rectangle on screen."""
    px, py, pw, ph = c["picture"]
    asp = aspect(c)
    box = theme.window_box(c)
    ww, cy_scr = box[0], box[1]
    wh = int(round(ww / asp))
    zmin = max(ww / pw, wh / ph)
    dur = (c["f1"] - c["f0"]) / FPS
    md = c.get("move_dur", dur)
    e = ease(c.get("move_ease", "inout"), t / md if md > 0 else 1)
    zoom = max(zmin, anim(c.get("zoom", 1.25), e, t))
    cw, ch = ww / zoom, wh / zoom
    cx = anim(c.get("cx", px + pw / 2), e, t)
    cy = anim(c.get("cy", py + ph / 2), e, t)
    fx, fy = float_offset(c, t)
    cx, cy = cx + fx / zoom, cy + fy / zoom
    x0 = clamp(cx - cw / 2, px, px + pw - cw)
    y0 = clamp(cy - ch / 2, py, py + ph - ch)
    wx0 = (W - ww) // 2 if len(box) < 3 else int(round(box[2] - ww / 2))
    wy0 = int(round(cy_scr - wh / 2))
    return {"ww": ww, "wh": wh, "wx0": wx0, "wy0": wy0, "zoom": zoom, "crop": (x0, y0, cw, ch), "zmin": zmin}


def src_to_screen(geom, sx, sy):
    x0, y0, cw, ch = geom["crop"]
    return geom["wx0"] + (sx - x0) * geom["zoom"], geom["wy0"] + (sy - y0) * geom["zoom"]


def default_cw(c):
    px, py, pw, ph = c["picture"]
    return min(pw, ph * W / H)


def clip_scale(c, theme):
    """Largest output/source pixel ratio a clip ever uses."""
    if c["layout"] in ("full", "sheet"):
        return W / min(values(c.get("cw", default_cw(c))))
    dur = (c["f1"] - c["f0"]) / FPS
    return max(window_geom(c, k / FPS, theme)["zoom"] for k in range(0, int(dur * FPS) + 1))


# ----------------------------------------------------------------------------------------------- source reading
class Source:
    """Forward-only frame reader for one clip: frames are fetched by fractional source position."""

    def __init__(self, c):
        self.c = c
        if c["info"].get("still"):  # still image: the region of the picture, the same array for every t
            self.proc = None
            self._region()  # validates the crop height
            px, py, pw, ph = c["picture"]
            self.region = [px, py, pw, ph]  # whole picture: the float may move past the push's own range
            rx, ry, rw, rh = self.region
            if c["info"].get("sheet"):
                self.still = np.ascontiguousarray(SHEET_TEXTURE()[ry:ry + rh, rx:rx + rw])
            else:
                with Image.open(c["path"]) as im:
                    self.still = np.asarray(im.convert("RGB").crop((rx, ry, rx + rw, ry + rh)))
            self.shape = self.still.shape
            return
        self.sfps = c["info"]["fps"]
        # "decode_fps": "source" reads every source frame (60 fps trailers slowed to 0.5x stay sharp); default:
        # resampled to the output rate as before
        self.rate = self.sfps if c.get("decode_fps") == "source" else FPS
        self.region = self._region()
        rx, ry, rw, rh = self.region
        first = self.src_time(-c["pre"] / FPS)
        self.idx0 = max(0, int(round(first * self.sfps)) - 1)
        self.t0 = self.idx0 / self.sfps
        seek = max(0.0, self.t0 - 0.0005)
        last = self.src_time((c["f1"] - c["f0"] + c["post"]) / FPS)
        n = int(math.ceil((last - self.t0) * self.rate)) + 3
        vf = f"crop={rw}:{rh}:{rx}:{ry}" + ("" if c.get("decode_fps") == "source" else f",fps={FPS}")
        # decoder stderr is muted because closing a clip early always ends in "Broken pipe"; a real decode failure
        # still surfaces as "source ran out" in _get()
        self.proc = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{seek:.4f}", "-i", c["path"], "-an",
                                      "-frames:v", str(n), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.fsize = rw * rh * 3
        self.buf = {}
        self.next_j = 0
        self.shape = (rh, rw, 3)

    def _region(self):
        c = self.c
        px, py, pw, ph = c["picture"]
        if c["layout"] == "window":
            return [px, py, pw - pw % 2, ph - ph % 2]
        cws = values(c.get("cw", default_cw(c)))
        cxs = values(c.get("cx", px + pw / 2))
        cw = max(cws)
        if cw * H / W > ph + 0.5:
            raise ValueError(f"clip {c.get('id')}: crop height {cw * H / W:.0f} exceeds picture height {ph}")
        x0 = max(px, int(math.floor(min(cxs) - cw / 2)) - 2)
        x1 = min(px + pw, int(math.ceil(max(cxs) + cw / 2)) + 2)
        w = x1 - x0
        return [x0, py, w - w % 2, ph - ph % 2]

    def src_time(self, t):
        c = self.c
        if "timemap" in c:
            tm = c["timemap"]
            if t <= tm[0][0]:
                return tm[0][1] + (t - tm[0][0]) * ((tm[1][1] - tm[0][1]) / (tm[1][0] - tm[0][0]))
            for (ta, sa), (tb, sb) in zip(tm, tm[1:]):
                if t <= tb:
                    return lerp(sa, sb, (t - ta) / (tb - ta))
            (ta, sa), (tb, sb) = tm[-2], tm[-1]
            return sb + (t - tb) * (sb - sa) / (tb - ta)
        fr = c.get("freeze")  # beat-freeze-cut: [at, hold] in clip-local seconds
        if fr and t > fr[0]:
            t = max(fr[0], t - fr[1])
        return c["in"] + t * c.get("speed", 1.0)

    def _get(self, j):
        while self.next_j <= j:
            b = self.proc.stdout.read(self.fsize)
            if len(b) < self.fsize:
                raise RuntimeError(f"clip {self.c.get('id')}: source ran out at frame {self.next_j} "
                                   f"({self.t0 + self.next_j / self.rate:.3f}s) of {self.c['src']}")
            self.buf[self.next_j] = np.frombuffer(b, np.uint8).reshape(self.shape)
            self.next_j += 1
            for k in [k for k in self.buf if k < self.next_j - 3]:
                del self.buf[k]
        return self.buf[j]

    def frame(self, t):
        if self.proc is None:
            return self.still
        p = (self.src_time(t) - self.t0) * self.rate
        j = int(math.floor(p + 1e-6))
        fr = p - j
        if self.c.get("blend_frames") and fr > 0.05:
            a, b = self._get(j), self._get(j + 1)
            return (a.astype(np.float32) * (1 - fr) + b.astype(np.float32) * fr).astype(np.uint8)
        return self._get(j + 1) if fr > 0.5 else self._get(j)

    def close(self):
        if self.proc is None:
            return
        try:
            self.proc.stdout.close()
            self.proc.kill()
            self.proc.wait()
        except Exception:
            pass


def lift_lut(lift):
    x = np.arange(256, dtype=np.float32) / 255
    if lift:
        x = x ** (1 / (1 + lift))
    return np.clip(x * 255 + 0.5, 0, 255).astype(np.uint8)


def render_clip_frame(c, src, t, theme):
    """One laid-out 1080x1920 frame of clip c at clip-local time t (may be outside the clip for handles)."""
    arr = src.frame(t)
    if c.get("lift"):
        arr = lift_lut(c["lift"])[arr]
    rx, ry, rw, rh = src.region
    if c["layout"] in ("full", "sheet"):
        dur = (c["f1"] - c["f0"]) / FPS
        md = c.get("move_dur", dur)
        e = ease(c.get("move_ease", "inout"), t / md if md > 0 else 1)
        px, py, pw, ph = c["picture"]
        cw = anim(c.get("cw", default_cw(c)), e, t)
        cx = anim(c.get("cx", px + pw / 2), e, t)
        cy = anim(c.get("cy", py + ph / 2), e, t)
        fx, fy = float_offset(c, t)
        cx, cy = cx + fx * cw / W, cy + fy * cw / W
        chh = cw * H / W
        x0 = clamp(cx - cw / 2, rx, rx + rw - cw) - rx
        y0 = clamp(cy - chh / 2, ry, ry + rh - chh) - ry
        return np.asarray(Image.fromarray(arr).resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + chh),
                                                      reducing_gap=None if cw < 1.6 * W else 2.0))
    g = window_geom(c, t, theme)
    x0, y0, cw, ch = g["crop"]
    im = Image.fromarray(arr)
    # fill: the same frame enlarged, blurred and kept clearly visible (theme.bg_level, about 0.6)
    small = im.reduce(8)
    sw, sh = small.size
    bw = sh * W / H
    bcx = clamp((x0 - rx + cw / 2) / 8, bw / 2, sw - bw / 2)
    bg = small.crop((int(bcx - bw / 2), 0, int(bcx + bw / 2), sh)).filter(ImageFilter.GaussianBlur(2.5))
    bg = np.asarray(bg.resize((W, H), Image.BILINEAR), np.float32)
    bg = theme.background(c["f0"] / FPS + t, bg)  # designed surface of the look (blurred fill passed in for glass)
    fg = np.asarray(im.resize((g["ww"], g["wh"]), Image.BICUBIC, box=(x0 - rx, y0 - ry, x0 - rx + cw, y0 - ry + ch)))
    return theme.compose_window(bg, fg, g, c, t)


# ----------------------------------------------------------------------------------------------- image helpers
def dir_blur(img, radius):
    r = int(round(radius))
    if r < 1:
        return img
    f = img.astype(np.float32)
    pad = np.pad(f, ((0, 0), (r, r), (0, 0)), mode="edge")
    cs = np.cumsum(pad, axis=1, dtype=np.float32)
    cs = np.concatenate([np.zeros_like(cs[:, :1]), cs], axis=1)
    return ((cs[:, 2 * r + 1:] - cs[:, :-2 * r - 1]) / (2 * r + 1))[:, :W].astype(np.uint8)


def zoom_img(img, s, streak=0.0):
    im = Image.fromarray(img)
    acc, n = None, (4 if streak > 0.004 else 1)
    for k in range(n):
        sk = s * (1 + streak * k)
        bw, bh = W / sk, H / sk
        f = np.asarray(im.resize((W, H), Image.BILINEAR, box=((W - bw) / 2, (H - bh) / 2, (W + bw) / 2, (H + bh) / 2)),
                       np.float32)
        acc = f if acc is None else acc + f
    return (acc / n).astype(np.uint8)


def mix(img, color, a):
    if a <= 0:
        return img
    return (img.astype(np.float32) * (1 - a) + np.array(color, np.float32) * a).astype(np.uint8)


def luma(f):
    return f @ np.array([0.299, 0.587, 0.114], np.float32)


@lru_cache(maxsize=4)
def vignette_map(strength):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((x - W / 2) / (W / 2)) ** 2 * 0.8 + ((y - H / 2) / (H / 2)) ** 2)
    return (1 - strength * np.clip(d - 0.55, 0, None) ** 1.6)[..., None].astype(np.float32)


def grain(f, sigma, fidx):
    rng = np.random.default_rng(1000 + fidx)  # seeded per frame: reproducible
    n = rng.normal(0, sigma, (H // 2, W // 2)).astype(np.float32)
    f += np.repeat(np.repeat(n, 2, 0), 2, 1)[..., None]
    return f


def eq(f, contrast=1.0, sat=1.0):
    if contrast != 1.0:
        f = (f - 128) * contrast + 128
    if sat != 1.0:
        g = luma(f)[..., None]
        f = g + (f - g) * sat
    return f


def blur_small(img_u8, factor, radius):
    im = Image.fromarray(img_u8)
    sm = im.resize((W // factor, H // factor), Image.BILINEAR).filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(sm.resize((W, H), Image.BILINEAR), np.float32)


# ----------------------------------------------------------------------------------------------- text
@lru_cache(maxsize=None)
def font(path, size, axes=None):
    ft = ImageFont.truetype(path, int(size))
    if axes:
        ft.set_variation_by_axes(list(axes))
    return ft


def rgba(c, a=1.0):
    if isinstance(c, str):
        c = c.lstrip("#")
        c = tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(c[:3]) + (int(round(255 * a)),)


def text_img(text, ft, fill, stroke=0, stroke_fill=(0, 0, 0, 255), tracking=0.0, pad=None):
    """RGBA image of one line of text anchored on a fixed ascender box (so words share a baseline).
    Returns (image, baseline_y, advance)."""
    asc, desc = ft.getmetrics()
    pad = stroke + 6 if pad is None else pad
    if tracking:
        chars = list(text)
        widths = [ft.getlength(ch) for ch in chars]
        adv = sum(widths) + tracking * ft.size * (len(chars) - 1)
    else:
        adv = ft.getlength(text)
    img = Image.new("RGBA", (int(math.ceil(adv)) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if tracking:
        x = pad
        for ch, wch in zip(chars, widths):
            d.text((x, pad + asc), ch, font=ft, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill, anchor="ls")
            x += wch + tracking * ft.size
    else:
        d.text((pad, pad + asc), text, font=ft, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill, anchor="ls")
    return img, pad + asc, adv


def alpha_box(im, thr=128):
    a = im.getchannel("A").point(lambda v: 255 if v > thr else 0)
    return a.getbbox()


def blend(dst, im, x, y, alpha=1.0):
    """Alpha-blend a PIL RGBA image (or float RGBA array) into dst (HxWx3 float32), top-left at (x, y)."""
    spr = np.asarray(im, np.float32) if isinstance(im, Image.Image) else im
    x, y = int(round(x)), int(round(y))
    h, w = spr.shape[:2]
    sx0, sy0 = max(0, -x), max(0, -y)
    dx0, dy0 = max(0, x), max(0, y)
    dx1, dy1 = min(W, x + w), min(H, y + h)
    if dx1 <= dx0 or dy1 <= dy0 or alpha <= 0:
        return
    s = spr[sy0:sy0 + dy1 - dy0, sx0:sx0 + dx1 - dx0]
    a = s[..., 3:4] / 255 * alpha
    dst[dy0:dy1, dx0:dx1] = dst[dy0:dy1, dx0:dx1] * (1 - a) + s[..., :3] * a


def place(dst, im, cx, cy, log, name, alpha=1.0, thr=128):
    """Blend im centred on (cx, cy) and log its ink box (alpha > thr) for the safe-zone check."""
    x, y = cx - im.width / 2, cy - im.height / 2
    blend(dst, im, x, y, alpha)
    b = alpha_box(im, thr)
    if b and alpha > 0.05:
        log.append((name, x + b[0], y + b[1], x + b[2], y + b[3]))


def transform(im, scale=1.0, rot=0.0, blur=0.0, opacity=1.0):
    if scale != 1.0:
        im = im.resize((max(1, int(round(im.width * scale))), max(1, int(round(im.height * scale)))), Image.BICUBIC)
    if rot:
        im = im.rotate(rot, Image.BICUBIC, expand=True)
    if blur > 0.3:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    if opacity < 1.0:
        a = im.getchannel("A").point(lambda v: int(v * opacity))
        im = im.copy()
        im.putalpha(a)
    return im


def soft_shadow(im, radius, offset, color=(5, 10, 25), opacity=0.55, pad=None):
    pad = int(radius * 2 + abs(offset[1]) + 4) if pad is None else pad
    out = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    a = im.getchannel("A")
    sh = Image.new("RGBA", im.size, color + (0,))
    sh.putalpha(a.point(lambda v: int(v * opacity)))
    out.alpha_composite(sh, (pad + offset[0], pad + offset[1]))
    out = out.filter(ImageFilter.GaussianBlur(radius))
    out.alpha_composite(im, (pad, pad))
    return out


# ----------------------------------------------------------------------------------------------- captions
def silences(wav, noise=-40, d=0.08):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", wav, "-af", f"silencedetect=noise={noise}dB:d={d}",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    st = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    return list(zip(st, en))


def caption_words(edl):
    """Words with corrected onsets: snapped out of detected pauses, plus manual onset overrides by index."""
    cfg = edl["captions"]
    words = json.load(open(rel(edl, cfg["words"])))
    sil = silences(rel(edl, edl["vo"])) if cfg.get("onset_fix", True) else []
    rep = cfg.get("replace", {})
    ov = {int(k): v for k, v in cfg.get("onset_override", {}).items()}
    out = []
    for i, wd in enumerate(words):
        raw = wd["w"]
        core = raw.strip(".,;:!\"")
        txt = rep.get(core, core)
        if raw.endswith("?"):
            txt = txt.rstrip("?") + "?"
        s, e = wd["s"], wd["e"]
        for a, b in sil:
            if a - 0.02 <= s < b - 0.02:
                s = b
        s = ov.get(i, s)
        out.append({"i": i, "text": txt, "s": s, "e": max(e, s + 0.05), "raw": raw,
                    "stop": raw[-1] in ".,?!;:"})
    return out


def join_tokens(words, join_prefix=()):
    """Merge a prefix token with the following number into one caption token (prefix "ACME" + "6" -> "ACME 6").
    The prefixes come from the edit list: "captions": {"join_prefix": ["ACME"]}; default none."""
    toks, i = [], 0
    while i < len(words):
        w = dict(words[i])
        if w["text"] in join_prefix and i + 1 < len(words) and words[i + 1]["text"].rstrip("?").isdigit():
            nx = words[i + 1]
            w = dict(w, text=w["text"] + " " + nx["text"], e=nx["e"], stop=nx["stop"], raw=nx["raw"],
                     ids=[w["i"], nx["i"]])
            i += 2
        else:
            w["ids"] = [w["i"]]
            i += 1
        toks.append(w)
    return toks


def auto_groups(edl, max_words, upper, lead=0.04, max_gap=0.4, first_start=None, hold_last=True):
    """Caption groups: phrases split at punctuation, each phrase cut into balanced chunks of <= max_words tokens."""
    toks = join_tokens(caption_words(edl), tuple(edl.get("captions", {}).get("join_prefix", ())))
    for t in toks:
        t["text"] = t["text"].upper() if upper else t["text"]
    # phrases: the edit list's hand-made breaks (break_before word indices) when present, else punctuation
    brk = set(edl["captions"].get("break_before", []))
    phrases, cur = [], []
    for t in toks:
        if brk and cur and set(t["ids"]) & brk:
            phrases.append(cur)
            cur = []
        cur.append(t)
        if not brk and t["stop"]:
            phrases.append(cur)
            cur = []
    if cur:
        phrases.append(cur)
    groups = []
    for ph in phrases:
        k = math.ceil(len(ph) / max_words)
        sizes = [len(ph) // k + (1 if j < len(ph) % k else 0) for j in range(k)]
        if len(sizes) == 2 and sizes == [2, 1] and ph[1]["text"].lower() in ("the", "a", "an", "to", "of"):
            sizes = [1, 2]  # keep an article/preposition with its noun: "REPORTS / THE CRIME"
        j = 0
        for sz in sizes:
            groups.append(ph[j:j + sz])
            j += sz
    res = []
    for gi, g in enumerate(groups):
        start = g[0]["s"] - lead
        if gi + 1 < len(groups):
            nxt = groups[gi + 1][0]["s"] - lead
            gap = nxt - g[-1]["e"] > max_gap
            end = g[-1]["e"] + 0.2 if gap else nxt
        else:
            gap, end = True, (None if hold_last else g[-1]["e"] + 0.3)
        res.append({"words": g, "start": max(0.0, start), "end": end, "gap_after": gap, "gi": gi})
    if first_start is not None:
        res[0]["start"] = first_start
    return res


def active_index(group, t):
    a = None
    for k, w in enumerate(group["words"]):
        if t >= w["s"] - 0.01:
            a = k
    return a


def zone_violations(box):
    x0, y0, x1, y1 = box
    v = []
    if FORMAT == "wide":
        z = SAFE_WIDE
        if x0 < z["x0"] - 0.5 or x1 > z["x1"] + 0.5 or y0 < z["y0"] - 0.5 or y1 > z["y1"] + 0.5:
            v.append("outside title-safe x96-1824 / y54-1000")
        if x1 > z["card_x0"] + 0.5 and y0 < z["card_y1"] - 0.5:
            v.append("inside the info-card corner (x>1720, y<120)")
        return v
    if x0 < SAFE["x0"] - 0.5 or x1 > SAFE["x1"] + 0.5 or y0 < SAFE["y0"] - 0.5 or y1 > SAFE["y1"] + 0.5:
        v.append("outside x130-950 / y300-1580")
    if y1 > SAFE["low_y0"] and y0 < SAFE["low_y1"] and x1 > SAFE["low_x1"] + 0.5:
        v.append("x>860 inside y1000-1600")
    return v
