"""Wide 16:9 long-form look (1920x1080, 30 fps): the Case File dossier for list videos ("10 times ...").

Used by build.py when the edit list says "format": "wide" (shortkit.set_format("wide") must run before this module
and themes are imported). A long video is a manifest of segments (longform.py); each segment is one edit list with
its own voice-over, rendered and encoded on its own so the segments join without re-encoding.

Graphics (all animated in and out, every text box logged for the title-safe check x 96-1824 / y 54-1000, nothing in
the top-right 200x120 info-card corner; no text below 30 px, key text 80 px and more):
  card        case-number card over ink-tinted moving footage at the start of a case, revealed by a redact wipe
  title       cold-open promise: two huge lines on pasted paper strips, red circle on a word
  header      file tab "CASE 03 / 10" (top left) + lower third with game, developer, year and footage credit
  counter     small persistent "CASE 03/10" chip (top left) once the header has gone
  source_plates  mono "SOURCE: ..." line typed on whenever the narration states a fact
  quotes      typed quote (<= 14 words) with attribution on a torn paper slip with tape
  verdict     2-4 word rubber stamp slammed at the end of a case
  circles     hand-drawn red circle around something in the footage
  notes       index card beside a window clip (evidence moments)
  end_card    left-half sign-off; the right half stays free for YouTube end-screen elements
  out         redact wipe to ink at the end of the segment (the next segment opens on its case card)
Captions (word groups) stay available with "captions": {"enabled": true, ...}; off by default (subtitles are
uploaded as a file).
"""
import math
import subprocess
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import shortkit as K

if K.FORMAT != "wide":
    raise RuntimeError("import wide only after shortkit.set_format('wide')")

import themes as T  # noqa: E402
from shortkit import ease, back_out, lerp, clamp, font, blend, transform  # noqa: E402

W, H, FPS = K.W, K.H, K.FPS
Z = K.SAFE_WIDE
INK, BONE, RED, HI = T.CaseFile.INK, T.CaseFile.BONE, T.CaseFile.RED, T.CaseFile.HI
F_BIGSH, F_JBM, F_SPACE = T.F_BIGSH, T.F_JBM, T.F_SPACE
MIN_PX = 30  # smallest type size allowed at 1080p (phone held sideways)


# ============================================================================================ small helpers
def _min(size):
    if size < MIN_PX:
        raise ValueError(f"type size {size} px is below the {MIN_PX} px minimum for 1080p")
    return int(size)


def bigsh(size, w=900):
    return font(F_BIGSH, _min(size), (w,))


def mono(size, w=800):
    return font(F_JBM, _min(size), (w,))


def span(t, t0, t1, tin=0.25, tout=0.2):
    """Visibility of an element shown t0..t1: None outside, else (in progress, out progress), both 0..1."""
    if t < t0 or t >= t1:
        return None
    return clamp((t - t0) / tin) if tin > 0 else 1.0, clamp((t - (t1 - tout)) / tout) if tout > 0 else 0.0


def put(dst, im, x, y, log, name, alpha=1.0, thr=128):
    """Blend im with its top-left at (x, y) and log the ink box (alpha > thr) for the safe-zone check."""
    blend(dst, im, x, y, alpha)
    b = K.alpha_box(im, thr)
    if b and alpha > 0.05:
        log.append((name, x + b[0], y + b[1], x + b[2], y + b[3]))


def keyed(v, t):
    """Number or absolute-time keyframes [[t, v], ...]."""
    return K.anim(v, 0, t) if K.is_keys(v) else float(v)


@lru_cache(maxsize=64)
def paper(w, h, seed, tone=1.0):
    """Bone paper: fine noise, low-frequency mottling, darker aged edges (RGBA, opaque)."""
    rng = np.random.default_rng(seed)
    f = np.empty((h, w, 3), np.float32)
    f[:] = np.array(BONE, np.float32) * tone
    lo = rng.normal(0, 1, (h // 28 + 2, w // 28 + 2)).astype(np.float32)
    lo = np.asarray(Image.fromarray(lo).resize((w, h), Image.BICUBIC), np.float32)
    f += (rng.normal(0, 5, (h, w)).astype(np.float32) + 4 * lo)[..., None]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy))
    f *= (1 - 0.13 * np.exp(-d / 14))[..., None]
    out = np.concatenate([np.clip(f, 0, 255), np.full((h, w, 1), 255, np.float32)], 2)
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def torn(im, seed, edges="b", amp=9):
    """Cut ragged torn edges into an RGBA sheet (edges: any of 'tblr')."""
    w, h = im.size
    rng = np.random.default_rng(seed)
    m = Image.new("L", (w, h), 0)

    def rag(n):
        return np.cumsum(rng.normal(0, amp * 0.35, n)).clip(-amp, amp) * 0.5 + amp * 0.5 + rng.uniform(0, amp * 0.5, n)

    xs = np.linspace(0, w, max(2, w // 7))
    ys = np.linspace(0, h, max(2, h // 7))
    top = [(x, (rag(1)[0] if "t" in edges else 0)) for x in xs]
    bot = [(x, h - 1 - (r if "b" in edges else 0)) for x, r in zip(xs[::-1], rag(len(xs)))]
    pts = top + [(w - 1 - (r if "r" in edges else 0), y) for y, r in zip(ys, rag(len(ys)))] + bot + \
        [((r if "l" in edges else 0), y) for y, r in zip(ys[::-1], rag(len(ys)))]
    ImageDraw.Draw(m).polygon(pts, fill=255)
    out = im.copy()
    out.putalpha(Image.fromarray(np.minimum(np.asarray(im.getchannel("A")), np.asarray(m))))
    return out


@lru_cache(maxsize=16)
def tape(w, h, ang, seed=0):
    """Semi-transparent masking tape strip with ragged short ends."""
    rng = np.random.default_rng(seed)
    a = np.full((h, w), 165, np.float32) + rng.normal(0, 10, (h, w))
    for x in range(6):
        a[:, x] *= (rng.uniform(0, 1, h) > (6 - x) / 7)
        a[:, w - 1 - x] *= (rng.uniform(0, 1, h) > (6 - x) / 7)
    rgb = np.empty((h, w, 3), np.float32)
    rgb[:] = (240, 232, 200)
    im = Image.fromarray(np.concatenate([rgb, a[..., None]], 2).clip(0, 255).astype(np.uint8), "RGBA")
    return im.rotate(ang, Image.BICUBIC, expand=True)


def inked(im, seed, holes=0.0, wear=0.12):
    """Printed-ink texture on the alpha channel: uneven density (wear) and small voids (holes, rubber stamps)."""
    a = np.asarray(im.getchannel("A"), np.float32)
    h, w = a.shape
    rng = np.random.default_rng(seed)
    n = np.asarray(Image.fromarray(rng.normal(0, 1, (h // 3 + 1, w // 3 + 1)).astype(np.float32))
                   .resize((w, h), Image.BILINEAR), np.float32)
    a = a * (1 - wear + wear * np.clip(n * 0.5 + 0.5, 0, 1))
    if holes:
        fine = rng.uniform(0, 1, (h, w))
        a *= (fine > holes * (0.6 + 0.4 * np.clip(-n, 0, 1)))
    out = im.copy()
    out.putalpha(Image.fromarray(a.clip(0, 255).astype(np.uint8)))
    return out


def shadowed(im, r=12, off=(0, 10), op=0.5, pad=None):
    return K.soft_shadow(im, r, off, (0, 0, 0), op, pad=pad if pad is not None else int(r * 2 + abs(off[1]) + 4))


def wrap(text, ft, maxw):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        nxt = (cur + " " + wd).strip()
        if ft.getlength(nxt) <= maxw or not cur:
            cur = nxt
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


# ============================================================================================ theme
class WideCaseFile(T.CaseFile):
    """Case File dossier for 16:9 long-form. Inherits grade, dossier sheet, red circle, redact/shutter cuts."""
    name = "case-file"
    ANGLES = (-1.4, 1.1, -0.9, 1.2)

    def make_groups(self):
        cap = self.edl.get("captions")
        if cap and cap.get("enabled"):
            return K.auto_groups(self.edl, 4, upper=False)
        return []

    @property
    def total_s(self):
        return self.renderer.total / FPS if self.renderer else K.segment_seconds(self.edl)

    # ---------------------------------------------------------------- window = evidence photo beside a note
    def window_box(self, c):
        return c.get("win_w", 1120), c.get("win_cy", 500), c.get("win_cx", 700)

    def compose_window(self, bg, fg, g, c, t):
        ww, wh = g["ww"], g["wh"]
        ang = c.get("tilt", self.ANGLES[c["idx"] % len(self.ANGLES)])
        label = c.get("exhibit") or f"EXHIBIT {c['idx'] + 1:02d}"
        frame, label_box = self.photo_frame_w(ww, wh, ang, label)
        photo = frame["base"].copy()
        photo.paste(Image.fromarray(fg), (frame["ox"], frame["oy"]))
        rot = photo.rotate(ang, Image.BICUBIC, expand=True)
        rot.alpha_composite(frame["tape"])
        cx, cy = g["wx0"] + ww / 2, g["wy0"] + wh / 2 + 24
        cam = self.desk_cam(c, t)
        if cam is not None:  # a still in the window: the camera pans over the desk, photo and pages move together
            dx, dy = cam
            tex = sheet_texture()
            ox = int(round(clamp((tex.shape[1] - W) / 2 + dx, 0, tex.shape[1] - W)))
            oy = int(round(clamp((tex.shape[0] - H) / 2 + dy, 0, tex.shape[0] - H)))
            bg = tex[oy:oy + H, ox:ox + W].astype(np.float32)
            cx, cy = cx - dx, cy - dy
        x, y = int(cx - rot.width / 2), int(cy - rot.height / 2)
        sh = frame["shadow"]
        sx, sy = int(cx - sh.shape[1] / 2) + 10, int(cy - sh.shape[0] / 2) + 16
        reg = bg[max(0, sy):sy + sh.shape[0], max(0, sx):sx + sh.shape[1]]
        s = sh[max(0, -sy):max(0, -sy) + reg.shape[0], max(0, -sx):max(0, -sx) + reg.shape[1]]
        reg *= 1 - 0.6 * s
        blend(bg, rot, x, y)
        if hasattr(self, "frame_text"):
            self.frame_text.append(("exhibit-label", label_box[0] + x, label_box[1] + y, label_box[2] + x,
                                    label_box[3] + y))
        return np.clip(bg, 0, 255).astype(np.uint8)

    @staticmethod
    def desk_cam(c, t):
        """Camera offset (output px) over the desk for still-image window clips (and video windows with "desk").
        "desk": [[dx0, dy0], [dx1, dy1]] linear over the clip (default [[-110, -60], [110, 60]]), plus half the float."""
        if not c["info"].get("still") and "desk" not in c:  # video windows: only when "desk" is given
            return None
        (ax, ay), (bx, by) = c.get("desk", [[-110, -60], [110, 60]])
        dur = (c["f1"] - c["f0"]) / FPS
        p = clamp(t / dur) if dur > 0 else 1.0
        fx, fy = K.float_offset(c, t)
        return lerp(ax, bx, p) + 0.5 * fx, lerp(ay, by, p) + 0.5 * fy

    @lru_cache(maxsize=16)
    def photo_frame_w(self, ww, wh, ang, label):
        b, bb = 18, 70
        ow, oh = ww + 2 * b, wh + b + bb
        base = paper(ow, oh, 21).copy()
        ft = mono(32, 700)
        lab = Image.new("RGBA", (ow, oh), (0, 0, 0, 0))
        ImageDraw.Draw(lab).text((b + 4, wh + b + bb / 2 + 2), label, font=ft, fill=INK + (255,), anchor="lm")
        lab = inked(lab, 4, wear=0.25)
        base.alpha_composite(lab)
        label_box = K.alpha_box(lab.rotate(ang, Image.BICUBIC, expand=True))
        rot_size = base.rotate(ang, Image.BICUBIC, expand=True).size
        tp = Image.new("RGBA", rot_size, (0, 0, 0, 0))
        for tx, ty, ta in ((70, 22, 30), (rot_size[0] - 70, 26, -26)):
            s = tape(170, 46, ta, seed=tx)
            tp.alpha_composite(s, (int(tx - s.width / 2), int(ty - s.height / 2)))
        shadow = Image.new("L", (rot_size[0] + 60, rot_size[1] + 60), 0)
        shadow.paste(base.rotate(ang, Image.BICUBIC, expand=True).getchannel("A"), (30, 30))
        shadow = np.asarray(shadow.filter(ImageFilter.GaussianBlur(18)), np.float32)[..., None] / 255
        return {"base": base, "ox": b, "oy": b, "tape": tp, "shadow": shadow}, label_box

    # ---------------------------------------------------------------- picture treatments before the grade
    def post_base(self, img, t):
        e = self.edl
        dim, desat = 0.0, 0.0
        tt = e.get("cold_title")
        if tt:
            s = span(t, tt["t"], tt["end"], 0.3, 0.25)
            if s:
                dim = max(dim, 0.3 * s[0] * (1 - s[1]))
        for q in e.get("quotes", []):
            s = span(t, q["t"], q["end"], 0.3, 0.25)
            if s:
                dim = max(dim, 0.38 * s[0] * (1 - s[1]))
        v = e.get("verdict")
        if v:
            s = span(t, v["t"] - 0.05, v["end"], 0.15, 0.25)
            if s:  # "dim" (default 0.45) and "desat" (0-1, default 0): for light, pastel pictures under the stamp
                dim = max(dim, v.get("dim", 0.45) * s[0] * (1 - s[1]))
                desat = v.get("desat", 0) * s[0] * (1 - s[1])
        ec = e.get("end_card")
        if ec:
            s = span(t, ec["t"], self.total_s + 1, 0.4, 0)
            if s:
                dim = max(dim, 0.35 * s[0])
        if dim <= 0.005:
            return img
        f = img.astype(np.float32)
        if desat > 0.005:
            f = K.eq(f, 1.0, 1.0 - desat)
        return np.clip(f * (1 - dim) + np.array(INK, np.float32) * dim, 0, 255).astype(np.uint8)

    # ---------------------------------------------------------------- overlay
    def overlay(self, img, t):
        dst = img.astype(np.float32)
        log = []
        e = self.edl
        for c in e.get("circles", []):
            self.draw_circle(dst, c, t)
        for n in e.get("notes", []):
            self.draw_note(dst, n, t, log)
        self.draw_header(dst, t, log)
        self.draw_counter(dst, t, log)
        for s in e.get("source_plates", []):
            self.draw_source(dst, s, t, log)
        for q in e.get("quotes", []):
            self.draw_quote(dst, q, t, log)
        self.draw_verdict(dst, t, log)
        self.draw_title(dst, t, log)
        self.draw_end_card(dst, t, log)
        for g in self.groups:
            if g["start"] <= t and (g["end"] is None or t < g["end"]):
                self.draw_caption_w(dst, g, t, log)
        dst = self.draw_card(dst, img, t, log)
        self.draw_out(dst, t)
        return np.clip(dst, 0, 255).astype(np.uint8), log

    # ---------------------------------------------------------------- case card + redact reveal (segment start)
    @lru_cache(maxsize=4)
    def card_img(self, case, of, kicker):
        big = bigsh(330)
        num = f"CASE {case:02d}"
        tw = big.getlength(num)
        w, h = int(tw + 520), 560
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((0, 40), kicker, font=mono(40, 800), fill=RED + (255,), anchor="lt")
        base = 100 + big.getbbox("C", anchor="ls")[3] - big.getbbox("C", anchor="ls")[1] + 20
        d.text((-6, base), num, font=big, fill=BONE + (255,), anchor="ls")
        d.text((tw + 30, base), f"/ {of:02d}", font=bigsh(130), fill=BONE + (170,), anchor="ls")
        return inked(im, 9, wear=0.10)

    @lru_cache(maxsize=4)
    def open_stamp(self, text):
        return self.stamp_img((text,), 96, -8, seed=13)

    def draw_card(self, dst, img, t, log):
        cd = self.edl.get("card")
        if not cd:
            return dst
        end, wipe = cd["end"], cd.get("wipe", 0.33)
        if t >= end + wipe:
            return dst
        seg = self.edl["segment"]
        layer = img.astype(np.float32)
        layer = layer * 0.3 + K.luma(layer)[..., None] * 0.12 + np.array(INK, np.float32) * 0.45
        im = self.card_img(seg["case"], seg["of"], cd.get("kicker", "CASE FILE · OPENED"))
        p = ease("power3.out", t / 0.3)
        drift = 1 + 0.025 * clamp(t / (end + wipe))
        im2 = transform(im, scale=drift) if drift > 1.001 else im
        # "drift": the card type slides left by that many px over the card (0 = the demo look); over dark stills it
        # keeps the opening visibly moving
        dx = cd.get("drift", 0) * clamp(t / (end + wipe))
        put(layer, im2, 150 + cd.get("drift", 0) - dx, 250 + 40 * (1 - p), log, "case-card", alpha=p)
        st_t = cd.get("stamp_t", 0.45)
        if t >= st_t:
            ds = t - st_t
            s = lerp(1.7, 1.0, ease("expo_out", ds / 0.14)) if ds < 0.14 else 1.0
            stm = transform(self.open_stamp(cd.get("stamp", "OPEN")), scale=s)
            K.place(layer, stm, cd.get("stamp_x", 1450), cd.get("stamp_y", 330), log, "case-card-stamp", alpha=0.94 * clamp(ds / 0.05))
        if t < end:
            return layer
        q = ease("power3.out", (t - end) / wipe)
        band = 420
        lead = lerp(0, W + band, q)
        x0, x1 = int(clamp(lead - band, 0, W)), int(clamp(lead, 0, W))
        out = layer
        out[:, :x0] = dst[:, :x0]
        out[:, x0:x1] = INK
        return out

    # ---------------------------------------------------------------- redact out (segment end)
    def draw_out(self, dst, t):
        o = self.edl.get("out")
        if not o:
            return
        dur = o.get("dur", 0.4)
        t0 = self.total_s - dur
        if t < t0:
            return
        q = ease("power3.in", (t - t0) / (dur * 0.8))
        band = 420
        lead = lerp(0, W + band, q)
        x1 = int(clamp(lead, 0, W))
        dst[:, :x1] = INK
        if x1 > 0:
            dst[:, :x1] += np.random.default_rng(int(t * FPS)).normal(0, 3.5, (H, 1, 1)).astype(np.float32)

    # ---------------------------------------------------------------- header: file tab + lower third, then counter
    @lru_cache(maxsize=4)
    def header_tab(self, case, of, kicker):
        big = bigsh(118)
        main, tail = f"CASE {case:02d}", f" / {of:02d}"
        w = int(max(big.getlength(main + tail), mono(30).getlength(kicker)) + 34 + 40)
        h = 196
        im = paper(w, h, 31).copy()
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 9, h], fill=RED + (255,))
        d.text((34, 22), kicker, font=mono(30, 700), fill=INK + (200,), anchor="lt")
        d.text((34, 178), main, font=big, fill=INK + (255,), anchor="ls")
        d.text((34 + big.getlength(main), 178), tail, font=big, fill=RED + (255,), anchor="ls")
        im = torn(im, 5, "r", amp=8)
        return shadowed(inked(im, 2, wear=0.08), 12, (0, 10), 0.5, pad=26)

    @lru_cache(maxsize=4)
    def lower_third(self, game, sub, credit):
        big = bigsh(132)
        w = int(max(big.getlength(game), mono(40).getlength(sub), mono(30, 600).getlength(credit)) + 34 + 50)
        h = 262 if credit else 222
        im = paper(w, h, 41).copy()
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 9, h], fill=RED + (255,))
        d.text((34, 140), game, font=big, fill=INK + (255,), anchor="ls")
        d.line([(34, 158), (w - 30, 158)], fill=RED + (255,), width=3)
        d.text((34, 172), sub, font=mono(40), fill=INK + (255,), anchor="lt")
        d.text((34, 222), credit, font=mono(30, 600), fill=INK + (170,), anchor="lt")
        im = torn(im, 6, "r", amp=8)
        im = inked(im, 3, wear=0.08)
        tp = tape(150, 44, 24, seed=3)
        out = Image.new("RGBA", (im.width + 40, im.height + 40), (0, 0, 0, 0))
        out.alpha_composite(im, (0, 40))
        out.alpha_composite(tp, (im.width - tp.width + 10, 14))
        return shadowed(out, 12, (0, 10), 0.5, pad=26)

    def draw_header(self, dst, t, log):
        for k, hd in enumerate(headers(self.edl)):
            self.draw_one_header(dst, t, log, hd, hd.get("tab", k == 0))

    def draw_one_header(self, dst, t, log, hd, tab):
        seg = self.edl["segment"]
        s = span(t, hd["t"], hd["end"], 0.22, 0.18) if tab else None
        if s:
            im = self.header_tab(seg["case"], seg["of"], hd.get("kicker", "CASE FILE"))
            k = ease("power4.out", s[0]) - ease("power3.in", s[1])
            self.reveal_from_edge(dst, im, lerp(Z["x0"] - im.width, Z["x0"] - 26, k), Z["y0"] + 6 - 26, log,
                                  "header-tab")
        s = span(t, hd["t"] + hd.get("lt_delay", 0.35), hd.get("lt_end", hd["end"]), 0.24, 0.18)
        if s:
            im = self.lower_third(hd["game"], hd["sub"], hd.get("credit", ""))
            k = ease("power4.out", s[0]) - ease("power3.in", s[1])
            y = Z["y1"] - 10 - (im.height - 26)  # image = shadow pad 26 + tape 40 + paper + pad 26: paper ends at 990
            self.reveal_from_edge(dst, im, lerp(Z["x0"] - im.width, Z["x0"] - 26, k), y, log, "lower-third")

    @lru_cache(maxsize=4)
    def counter_img(self, case, of):
        ft = mono(34, 800)
        txt = f"CASE {case:02d}/{of:02d}"
        w = int(ft.getlength(txt) + 26 + 30)
        im = Image.new("RGBA", (w, 60), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, w - 1, 59], fill=INK + (226,))
        d.rectangle([0, 0, 8, 59], fill=RED + (255,))
        d.text((26, 31), txt, font=ft, fill=BONE + (255,), anchor="lm")
        return im

    def draw_counter(self, dst, t, log):
        seg = self.edl.get("segment", {})
        if seg.get("kind") != "case":
            return
        hd = (headers(self.edl) or [{}])[0]
        ct = self.edl.get("counter", {})
        t0 = ct.get("t", hd.get("end", 0) + 0.1)
        t1 = ct.get("end", self.total_s - (self.edl.get("out") or {}).get("dur", 0.4) + 0.1)
        s = span(t, t0, t1, 0.25, 0.15)
        if not s:
            return
        im = self.counter_img(seg["case"], seg["of"])
        k = ease("power4.out", s[0]) - ease("power3.in", s[1])
        self.reveal_from_edge(dst, im, lerp(Z["x0"] - im.width, Z["x0"], k), Z["y0"] + 10, log, "case-counter")

    # ---------------------------------------------------------------- source plate (typed mono line)
    @lru_cache(maxsize=64)
    def source_img(self, text, n):
        ft = mono(32, 700)
        head, rest = (text.split(":", 1)[0] + ":", text.split(":", 1)[1]) if ":" in text else ("", text)
        w = int(ft.getlength(text) + 30 + 44)
        im = Image.new("RGBA", (w, 58), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, w - 1, 57], fill=INK + (226,))
        d.rectangle([0, 0, 8, 57], fill=RED + (255,))
        x = 30
        shown = text[:n]
        hs = shown[:len(head)]
        d.text((x, 29), hs, font=ft, fill=HI + (255,), anchor="lm")
        x += ft.getlength(hs)
        if n > len(head):
            d.text((x, 29), shown[len(head):], font=ft, fill=BONE + (255,), anchor="lm")
            x += ft.getlength(shown[len(head):])
        if n < len(text):
            d.rectangle([x + 3, 12, x + 19, 46], fill=BONE + (255,))
        return im

    def draw_source(self, dst, s, t, log):
        sp = span(t, s["t"], s["end"], 0.2, 0.2)
        if not sp:
            return
        n = int(clamp((t - s["t"] - 0.1) * s.get("cps", 70), 0, len(s["text"])))
        im = self.source_img(s["text"], n)
        y = s.get("y", Z["y1"] - 10 - im.height)
        k = ease("power3.out", sp[0])
        put(dst, im, Z["x0"], y + 14 * (1 - k), log, "source-plate", alpha=k * (1 - sp[1]))

    # ---------------------------------------------------------------- quote slip (typed)
    @lru_cache(maxsize=4)
    def quote_layout(self, text, by):
        maxw = 980
        size = 74
        while size > 56:
            if len(wrap(text, mono(size, 600), maxw)) <= 4:
                break
            size -= 2
        lines = wrap(text, mono(size, 600), maxw)
        lw = max(mono(size, 600).getlength(l) for l in lines)
        w = int(max(lw, mono(36, 700).getlength(by)) + 2 * 70)
        h = int(110 + len(lines) * size * 1.22 + 90)
        return size, lines, w, h

    @lru_cache(maxsize=48)
    def quote_img(self, text, by, n, caret, ang):
        size, lines, w, h = self.quote_layout(text, by)
        im = paper(w, h, 51).copy()
        d = ImageDraw.Draw(im)
        d.text((70, 44), "QUOTE ON FILE", font=mono(30, 800), fill=RED + (255,), anchor="lt")
        d.line([(70, 88), (w - 70, 88)], fill=INK + (60,), width=2)
        ft = mono(size, 600)
        ink = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        di = ImageDraw.Draw(ink)
        y = 110 + size * 0.95
        left = n
        cx, cy = 70, y
        for l in lines:
            part = l[:max(0, left)]
            di.text((70, y), part, font=ft, fill=INK + (255,), anchor="ls")
            if 0 <= left <= len(l):
                cx, cy = 70 + ft.getlength(part), y
            left -= len(l) + 1
            y += size * 1.22
        if caret:
            di.rectangle([cx + 4, cy - size * 0.78, cx + 4 + size * 0.5, cy + size * 0.12], fill=RED + (220,))
        if n >= len(text):
            di.text((70, h - 46), by, font=mono(36, 700), fill=INK + (190,), anchor="ls")
        im.alpha_composite(inked(ink, 17, wear=0.22))
        im = torn(im, 8, "b", amp=12)
        tp = tape(190, 50, -4, seed=8)
        out = Image.new("RGBA", (w, h + 30), (0, 0, 0, 0))
        out.alpha_composite(im, (0, 30))
        out.alpha_composite(tp, (int(w / 2 - tp.width / 2), 6))
        return shadowed(out.rotate(ang, Image.BICUBIC, expand=True), 16, (0, 14), 0.55, pad=40)

    def draw_quote(self, dst, q, t, log):
        sp = span(t, q["t"], q["end"], 0.3, 0.22)
        if not sp:
            return
        text = q["text"]
        n = int(clamp((t - q["t"] - 0.35) * q.get("cps", 32), 0, len(text)))
        caret = n < len(text) or int((t - q["t"]) * 2.5) % 2 == 0
        im = self.quote_img(text, q.get("by", ""), n, caret, q.get("tilt", -1.6))
        k = ease("power3.out", sp[0])
        cx, cy = q.get("x", 960), q.get("y", 500)
        sx, sy = sway(q.get("sway", 0), t - q["t"])
        cx, cy = cx + sx, cy + sy
        K.place(dst, im, cx, cy + 50 * (1 - k) + 30 * ease("power3.in", sp[1]), log, "quote-slip",
                alpha=k * (1 - sp[1]), thr=200)

    # ---------------------------------------------------------------- verdict stamp
    @lru_cache(maxsize=8)
    def stamp_img(self, lines, size, ang, seed=1):
        sizes = [size * (0.62 if len(lines) > 1 and k == 0 else 1.0) for k in range(len(lines))]
        fts = [bigsh(s) for s in sizes]
        lw = max(f.getlength(l) for f, l in zip(fts, lines))
        pad = int(size * 0.3)
        bw = max(8, int(size * 0.07))
        caps = [f.getbbox("H", anchor="ls") for f in fts]
        caps = [b[3] - b[1] for b in caps]
        gap = size * 0.16
        h = int(sum(caps) + gap * (len(lines) - 1) + 2 * pad + 2 * bw)
        w = int(lw + 2 * pad + 2 * bw)
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, w - 1, h - 1], outline=RED + (255,), width=bw)
        d.rectangle([bw * 2, bw * 2, w - 1 - 2 * bw, h - 1 - 2 * bw], outline=RED + (255,), width=max(3, bw // 3))
        y = pad + bw
        for f, l, c in zip(fts, lines, caps):
            y += c
            d.text((w / 2, y), l, font=f, fill=RED + (255,), anchor="ms")
            y += gap
        im = inked(im, seed, holes=0.05, wear=0.22)
        return im.rotate(ang, Image.BICUBIC, expand=True)

    def draw_verdict(self, dst, t, log):
        v = self.edl.get("verdict")
        if not v or not (v["t"] <= t < v["end"]):
            return
        ds = t - v["t"]
        im = self.stamp_img(tuple(v["lines"]), v.get("size", 190), v.get("tilt", -6), seed=v.get("seed", 1))
        cx, cy = v.get("x", 960), v.get("y", 500)
        b = K.alpha_box(im, 60)  # the slam starts as large as the title-safe zone allows (never outside it)
        s0 = min(1.8, 2 * min(cx - Z["x0"], Z["x1"] - cx) / (b[2] - b[0]),
                 2 * min(cy - Z["y0"], Z["y1"] - cy) / (b[3] - b[1])) * 0.99
        s = lerp(max(1.0, s0), 1.0, ease("expo_out", ds / 0.13)) if ds < 0.13 else 1.0 + 0.012 * (ds - 0.13)
        a = clamp(ds / 0.05) * (1 - clamp((t - (v["end"] - 0.2)) / 0.2))
        if 0.12 <= ds < 0.3:  # impact shake, 6 frames
            k = int((ds - 0.12) * FPS)
            dx, dy = [(9, -6), (-7, 5), (5, -3), (-3, 2), (2, -1), (0, 0)][min(k, 5)]
            dst[:] = np.roll(dst, (dy, dx), (0, 1))
        sx, sy = sway(v.get("sway", 0), ds)
        K.place(dst, transform(im, scale=s), cx + sx, cy + sy, log, "verdict-stamp", alpha=a,
                thr=60)

    def draw_circle(self, dst, c, t):
        if not (c["t"] <= t < c["end"]):
            return
        p = ease("power2.out", (t - c["t"]) / c.get("draw", 0.45))
        if t > c["end"] - 0.15:
            p = min(p, 1 - ease("power2.in", (t - (c["end"] - 0.15)) / 0.15))
        self.red_circle(dst, keyed(c["cx"], t), keyed(c["cy"], t), c["rx"], c["ry"], p, seed=c.get("seed", 1),
                        width=c.get("width", 11))

    # ---------------------------------------------------------------- note card beside a window clip
    @lru_cache(maxsize=32)
    def note_img(self, title, lines, shown, ang):
        ft = bigsh(92, 900)
        w = int(max([ft.getlength(l) for l in lines] + [mono(34).getlength(title)]) + 2 * 46)
        h = int(120 + len(lines) * 96 + 40)
        im = paper(w, h, 61, tone=1.02).copy()
        d = ImageDraw.Draw(im)
        for yy in range(120 + 96 - 18, h - 20, 96):
            d.line([(20, yy), (w - 20, yy)], fill=(70, 110, 160, 70), width=2)
        d.line([(0, 98), (w, 98)], fill=RED + (200,), width=3)
        d.text((46, 50), title, font=mono(34), fill=RED + (255,), anchor="lm")
        ink = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        di = ImageDraw.Draw(ink)
        for k, l in enumerate(lines[:shown]):
            di.text((46, 120 + 96 * (k + 1) - 26), l, font=ft, fill=INK + (255,), anchor="ls")
        im.alpha_composite(inked(ink, 23, wear=0.15))
        tp = tape(150, 44, 8, seed=6)
        out = Image.new("RGBA", (w, h + 26), (0, 0, 0, 0))
        out.alpha_composite(im, (0, 26))
        out.alpha_composite(tp, (int(w / 2 - tp.width / 2), 2))
        return shadowed(out.rotate(ang, Image.BICUBIC, expand=True), 14, (0, 12), 0.5, pad=34)

    def draw_note(self, dst, n, t, log):
        sp = span(t, n["t"], n["end"], 0.3, 0.2)
        if not sp:
            return
        lines = tuple(n["lines"])
        shown = sum(1 for k in range(len(lines)) if t >= n["t"] + 0.35 + k * n.get("gap", 0.45))
        im = self.note_img(n["title"], lines, shown, n.get("tilt", 2.0))
        k = ease("power3.out", sp[0])
        K.place(dst, im, n.get("x", 1540), n.get("y", 500) + 60 * (1 - k), log, "note-card", alpha=k * (1 - sp[1]),
                thr=200)

    # ---------------------------------------------------------------- cold-open title
    @lru_cache(maxsize=8)
    def title_strip(self, line, size, red_words, seed, ang):
        ft = bigsh(size)
        sp = ft.getlength(" ")
        words = line.split()
        tw = sum(ft.getlength(w) for w in words) + sp * (len(words) - 1)
        padx, h = int(size * 0.28), int(size * 1.08)
        w = int(tw + 2 * padx)
        im = paper(w, h, seed).copy()
        ink = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(ink)
        x = padx
        for wd in words:
            col = RED if wd.strip("?!.,").upper() in red_words else INK
            d.text((x, h * 0.5 + size * 0.36), wd, font=ft, fill=col + (255,), anchor="ls")
            x += ft.getlength(wd) + sp
        im.alpha_composite(inked(ink, seed + 1, wear=0.18))
        im = torn(im, seed, "lr", amp=12)
        return shadowed(im.rotate(ang, Image.BICUBIC, expand=True), 16, (0, 14), 0.55, pad=40)

    def title_size(self, lines):
        size = 200
        while size > 80 and max(bigsh(size).getlength(l) for l in lines) + size * 0.56 + 60 > Z["x1"] - Z["x0"]:
            size -= 4
        return size

    def draw_title(self, dst, t, log):
        tt = self.edl.get("cold_title")
        if not tt or not (tt["t"] <= t < tt["end"]):
            return
        lines = tt["lines"]
        size = tt.get("size") or self.title_size(lines)
        red = tuple(w.upper() for w in tt.get("red", []))
        kick = tt.get("kicker")
        out = clamp((t - (tt["end"] - 0.25)) / 0.25)
        ys = tt.get("ys", [430, 430 + size * 1.12])
        angs = tt.get("tilts", [-1.5, 1.2])
        if kick and t >= tt["t"]:
            k = ease("power3.out", (t - tt["t"]) / 0.3)
            ft = mono(38, 800)
            im = Image.new("RGBA", (int(ft.getlength(kick)) + 60, 64), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rectangle([0, 0, im.width - 1, 63], fill=INK + (230,))
            d.rectangle([0, 0, 9, 63], fill=RED + (255,))
            d.text((32, 32), kick, font=ft, fill=BONE + (255,), anchor="lm")
            K.place(dst, im, 960, ys[0] - size * 0.75 - 40 + 20 * (1 - k), log, "title-kicker", alpha=k * (1 - out))
        for i, line in enumerate(lines):
            t_in = tt["t"] + tt.get("stagger", 0.32) * i + 0.12
            if t < t_in:
                continue
            ds = t - t_in
            im = self.title_strip(line, size, red, 71 + i, angs[i % len(angs)])
            b = K.alpha_box(im, 200)  # slam from 1.25x, or less when the strip would leave the title-safe zone
            s0 = max(1.0, min(1.25, 0.99 * (Z["x1"] - Z["x0"]) / (b[2] - b[0]) / 1.03))
            s = lerp(s0, 1.0, ease("expo_out", ds / 0.16)) if ds < 0.16 else 1.0 + 0.03 * clamp(
                (ds - 0.16) / max(0.1, tt["end"] - t_in))
            if out > 0:
                s *= 1 - 0.06 * out
            K.place(dst, transform(im, scale=s), 960, ys[i], log, f"title-line{i + 1}",
                    alpha=clamp(ds / 0.06) * (1 - out), thr=200)
        c = tt.get("circle")  # [line index, word, t]: red circle round a word once its strip has landed
        if c and t >= c[2]:
            li, word = c[0], c[1]
            ft = bigsh(size)
            line = lines[li]
            words = line.split()
            sp = ft.getlength(" ")
            tw = sum(ft.getlength(w) for w in words) + sp * (len(words) - 1)
            x = 960 - tw / 2
            for wd in words:
                if wd == word:
                    break
                x += ft.getlength(wd) + sp
            ww = ft.getlength(word)
            p = ease("power2.out", (t - c[2]) / 0.4) * (1 - out)
            self.red_circle(dst, x + ww / 2, ys[li] + angs[li % len(angs)] * -0.017 * (x + ww / 2 - 960),
                            ww / 2 + 46, size * 0.5 + 24, p, seed=4, width=12)

    # ---------------------------------------------------------------- end card (left half; right half stays free)
    @lru_cache(maxsize=2)
    def end_sheet(self, lines, sub, cta):
        w, h = 760, 820
        im = paper(w, h, 81).copy()
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 10, h], fill=RED + (255,))
        d.text((54, 60), sub, font=mono(32, 800), fill=RED + (255,), anchor="lt")
        size = 190
        while size > 80 and max(bigsh(size).getlength(l) for l in lines) > w - 110:
            size -= 4
        y = 130
        ink = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        di = ImageDraw.Draw(ink)
        for l in lines:
            di.text((54, y), l, font=bigsh(size), fill=INK + (255,), anchor="lt")
            y += size * 0.95
        di.text((54, h - 70), cta, font=mono(36, 800), fill=INK + (220,), anchor="ls")
        im.alpha_composite(inked(ink, 29, wear=0.15))
        return shadowed(torn(im, 12, "r", amp=10), 18, (0, 14), 0.55, pad=40)

    def draw_end_card(self, dst, t, log):
        ec = self.edl.get("end_card")
        if not ec or t < ec["t"]:
            return
        k = ease("power4.out", (t - ec["t"]) / 0.4)
        im = self.end_sheet(tuple(ec["lines"]), ec.get("sub", "CASE FILE · CLOSED"), ec.get("cta", "NEXT FILE >"))
        # "sway" (px, default 0): the sheet floats right/down and back within that range, never past the left edge
        sx, sy = sway(ec.get("sway", 0), t - ec["t"])
        sx = abs(sx)
        self.reveal_from_edge(dst, im, lerp(Z["x0"] - im.width, Z["x0"] - 40, k) + sx, 120 - 40 + sy, log, "end-card")
        if t >= ec["t"] + 0.6:
            ds = t - ec["t"] - 0.6
            s = lerp(1.7, 1.0, ease("expo_out", ds / 0.14)) if ds < 0.14 else 1.0
            st = self.stamp_img((ec.get("stamp", "CLOSED"),), 110, -9, seed=5)
            K.place(dst, transform(st, scale=s), 640 + sx, 760 + sy, log, "end-stamp", alpha=0.93 * clamp(ds / 0.05),
                    thr=60)

    # ---------------------------------------------------------------- optional captions (off by default)
    def draw_caption_w(self, dst, g, t, log):
        act = K.active_index(g, t)
        im = self.chip(g, act, 56)
        e = ease("power3.out", (t - g["start"]) / 0.16)
        K.place(dst, im, 960, Z["y1"] - 12 - im.height / 2 + 14 * (1 - e), log, "caption", alpha=e)


def sway(amp, t):
    """Paper floating on air: a slow drift of a plate by up to amp px (quotes and verdicts over still images, where
    the plate covers much of a dimmed picture). 0 = no movement, the default."""
    if not amp:
        return 0.0, 0.0
    return amp * math.sin(2 * math.pi * t / 3.1), 0.7 * amp * math.sin(2 * math.pi * t / 2.3 + 1.0)


def headers(edl):
    """"header" is one header or a list (a case about two games gets a second lower third, "tab": false)."""
    hd = edl.get("header")
    return [] if not hd else (hd if isinstance(hd, list) else [hd])


@lru_cache(maxsize=1)
def sheet_texture():
    """Dossier pages on the desk for "sheet" clips (no footage): 2400x1350, grid paper with a red margin, punch
    holes, blocks of redaction bars (no readable text, so it states no fact) and a ghost stamp ring; moved like a
    full-bleed still (push, pan, float), so it is real camera movement over a textured page."""
    w, h = 2400, 1350
    rng = np.random.default_rng(77)
    f = np.empty((h, w, 3), np.float32)
    f[:] = np.array(BONE, np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    ink = np.array(INK, np.float32)
    for step, a in ((54, 0.07), (270, 0.11)):
        line = ((xx % step) < 2) | ((yy % step) < 2)
        f[line] = f[line] * (1 - a) + ink * a
    for x0 in (150, 1350):  # two pages side by side, each with a red margin rule and punch holes
        red = (xx >= x0) & (xx < x0 + 3)
        f[red] = f[red] * 0.45 + np.array(RED, np.float32) * 0.55
        for hy in ((260, 675, 1090) if x0 < 1000 else ()):
            hole = (xx - (x0 - 70)) ** 2 + (yy - hy) ** 2 < 22 ** 2
            f[hole] = ink * 0.85 + f[hole] * 0.15
    im = Image.fromarray(np.clip(f, 0, 255).astype(np.uint8))
    bars = Image.new("L", (w, h), 0)  # faint typed-and-redacted lines, a texture for the eye, not a statement
    d = ImageDraw.Draw(bars)
    for x0 in (200, 1400):
        y = 150
        while y < h - 160:
            n = int(rng.integers(3, 7))
            for _ in range(n):
                x, right = x0 + 20, x0 + 860
                while x < right - 60:
                    bw = int(rng.integers(40, 220))
                    bw = min(bw, right - x)
                    d.rectangle([x, y + 30, x + bw, y + 44], fill=255)
                    x += bw + int(rng.integers(14, 30))
                y += 54
            y += 54
    f = np.asarray(im, np.float32)
    a = np.asarray(bars, np.float32)[..., None] / 255 * 0.3
    f = f * (1 - a) + np.array(INK, np.float32) * a
    lo = np.asarray(Image.fromarray(rng.normal(0, 1, (h // 30 + 2, w // 30 + 2)).astype(np.float32))
                    .resize((w, h), Image.BICUBIC), np.float32)
    f += (rng.normal(0, 5, (h, w)).astype(np.float32) + 5 * lo)[..., None]
    ring = np.abs(np.sqrt((xx - 1900) ** 2 + (yy - 1050) ** 2) - 150) < 9  # ghost stamp ring, red, faint
    f[ring] = f[ring] * 0.8 + np.array(RED, np.float32) * 0.2
    fold = np.abs(xx - 1200) < 40  # the gutter between the pages
    f[fold] *= (0.82 + 0.18 * (np.abs(xx[fold] - 1200) / 40))[..., None]
    return np.clip(f, 0, 255).astype(np.uint8)


K.SHEET_TEXTURE = sheet_texture


def make(name, edl):
    if name != "case-file":
        raise ValueError(f"wide format has only the case-file look (asked for {name})")
    return WideCaseFile(edl)


# ============================================================================================ encode
# One fixed set of x264 parameters for every wide segment: identical SPS/PPS, so the concat demuxer can join the
# segments with -c copy (longform.py join verifies this before joining).
X264_WIDE = ["-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-level:v", "4.2", "-crf", "17",
             "-maxrate", "16M", "-bufsize", "32M", "-g", "60", "-keyint_min", "30", "-pix_fmt", "yuv420p",
             "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]


def encode_segment(src, dst):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-an", *X264_WIDE, "-movflags", "+faststart", dst],
                   check=True)


# ============================================================================================ sound cues
TRANS_KIND = {"shutter": "shutter-clack", "redact": "marker-swipe"}


def sfx_cues(edl, r):
    """Cue list (segment-relative seconds) in the Shorts' sfx-cues format. New kinds for the sound stage:
    case-card, verdict-slam, title-slam, end-card (all others already exist in sound/cue_map.json)."""
    cues = []
    for c in r.clips[1:]:
        kind, t = c["_tr"], c["f0"] / FPS
        if kind == "cut":
            cues.append({"t": round(t - 0.06, 2), "kind": "whoosh-soft", "note": f"hard cut into {c['id']}"})
        else:
            cues.append({"t": round(t - 0.12, 2), "kind": TRANS_KIND.get(kind, kind),
                         "note": f"{kind} cut into {c['id']} ({c.get('note', '')[:60]})"})
    cd = edl.get("card")
    if cd:
        cues.append({"t": 0.0, "kind": "case-card", "note": "case-number card lands over tinted footage"})
        cues.append({"t": round(cd.get("stamp_t", 0.45), 2), "kind": "stamp", "note": "OPEN stamp on the card"})
        cues.append({"t": round(cd["end"] - 0.05, 2), "kind": "marker-swipe", "note": "redact wipe reveals the case"})
    for k, hd in enumerate(headers(edl)):
        if hd.get("tab", k == 0):
            cues.append({"t": round(hd["t"], 2), "kind": "tab-slide", "note": "case file tab slides in"})
        cues.append({"t": round(hd["t"] + hd.get("lt_delay", 0.35), 2), "kind": "paper-slide",
                     "note": f"lower third: {hd['game']}"})
    for s in edl.get("source_plates", []):
        cues.append({"t": round(s["t"] + 0.1, 2), "kind": "tab-type", "note": f"source plate types on: {s['text']}"})
    for q in edl.get("quotes", []):
        cues.append({"t": round(q["t"], 2), "kind": "paper-slide", "note": "quote slip slides in"})
        n = len(q["text"])
        cues.append({"t": round(q["t"] + 0.35, 2), "kind": "typewriter-tick", "dur": round(n / q.get("cps", 32), 2),
                     "note": "quote types on (repeat ticks for dur)"})
    for n in edl.get("notes", []):
        cues.append({"t": round(n["t"], 2), "kind": "paper-slide", "note": f"note card: {n['title']}"})
        for k in range(len(n["lines"])):
            cues.append({"t": round(n["t"] + 0.35 + k * n.get("gap", 0.45), 2), "kind": "stamp",
                         "note": f"note line {k + 1}"})
    for c in edl.get("circles", []):
        cues.append({"t": round(c["t"], 2), "kind": "circle-draw", "note": "red circle draws on"})
    v = edl.get("verdict")
    if v:
        cues.append({"t": round(v["t"] + 0.1, 2), "kind": "verdict-slam",
                     "note": f"verdict stamp: {' '.join(v['lines'])}"})
    tt = edl.get("cold_title")
    if tt:
        for i, _ in enumerate(tt["lines"]):
            cues.append({"t": round(tt["t"] + tt.get("stagger", 0.32) * i + 0.12, 2), "kind": "title-slam",
                         "note": f"title strip {i + 1} slams in"})
        if tt.get("circle"):
            cues.append({"t": round(tt["circle"][2], 2), "kind": "circle-draw", "note": "red circle on the title"})
    ec = edl.get("end_card")
    if ec:
        cues.append({"t": round(ec["t"], 2), "kind": "end-card", "note": "end card slides in (end-screen time)"})
        cues.append({"t": round(ec["t"] + 0.6, 2), "kind": "stamp", "note": "CLOSED stamp"})
    o = edl.get("out")
    if o:
        cues.append({"t": round(r.total / FPS - o.get("dur", 0.4), 2), "kind": "marker-swipe",
                     "note": "redact wipe to ink, end of segment"})
    cues += edl.get("sfx_extra", [])
    cues.sort(key=lambda c: c["t"])
    return cues


# ============================================================================================ thumbnail
TW_, TH_ = 1280, 720


def make_thumbnail(edl, out):
    """1280x720 JPG from the edit list's cover block:
    {"src", "t", "crop": [x, y, w, h] (source px, 16:9, w >= 1280 so nothing is upscaled), "words": [2-4 words on
     1-2 lines], "game", "tab", "circle": [cx, cy, rx, ry] (thumbnail px), "text_side": "left"|"right"}.
    Returns (bytes, text boxes, problems)."""
    cov = edl["cover"]
    path = K.footage(edl, cov["src"])
    info = K.probe(path)
    x, y, w, h = cov["crop"]
    probs = []
    if w < TW_ - 0.5 or abs(w / h - 16 / 9) > 0.01:
        probs.append("crop must be 16:9 and at least 1280 source px wide")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{cov['t']:.3f}", "-i", path, "-frames:v", "1", "-f",
                          "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    im = Image.frombytes("RGB", (info["w"], info["h"]), raw).resize((TW_, TH_), Image.LANCZOS, box=(x, y, x + w, y + h))
    f = np.asarray(im, np.float32)
    f = K.eq(f, 1.12, 1.12)
    yy, xx = np.mgrid[0:TH_, 0:TW_].astype(np.float32)
    left = cov.get("text_side", "left") == "left"
    g = np.clip(((TW_ * 0.62 - xx) if left else (xx - TW_ * 0.38)) / (TW_ * 0.5), 0, 1) ** 1.3
    f = f * (1 - 0.62 * g[..., None]) + np.array(INK, np.float32) * 0.62 * g[..., None]
    d = np.sqrt(((xx - TW_ / 2) / (TW_ / 2)) ** 2 + ((yy - TH_ / 2) / (TH_ / 2)) ** 2)
    f *= (1 - 0.3 * np.clip(d - 0.7, 0, None))[..., None]
    f += np.random.default_rng(3).normal(0, 3.5, (TH_, TW_, 1)).astype(np.float32)
    dst = np.clip(f, 0, 255)
    log = []
    th = WideCaseFile.__new__(WideCaseFile)  # graphics helpers only (no edit list timeline needed)
    cx, cy, rx, ry = cov["circle"]
    th.red_circle_t(dst, cx, cy, rx, ry)
    # words: huge Big Shoulders, bone and highlighter yellow, ink stroke + hard shadow
    words = cov["words"]
    lines = cov.get("lines") or [" ".join(words[:len(words) // 2 or 1]), " ".join(words[len(words) // 2 or 1:])]
    lines = [l for l in lines if l]
    maxw = cov.get("text_w", 640)
    size = 230
    while size > 100 and max(bigsh(size).getlength(l) for l in lines) > maxw:
        size -= 4
    x0 = 56 if left else TW_ - 56 - maxw
    yb = cov.get("text_y", 250) + size * 0.82
    for i, l in enumerate(lines):
        col = BONE if i == 0 else HI
        im_l, bl, adv = K.text_img(l, bigsh(size), col + (255,), stroke=9, stroke_fill=INK + (255,), pad=30)
        shadow = Image.new("RGBA", im_l.size, INK + (0,))
        shadow.putalpha(im_l.getchannel("A"))
        lx = x0 if left else x0 + maxw - adv
        blend(dst, shadow, lx - 30 + 9, yb - bl + 10)
        put(dst, im_l, lx - 30, yb - bl, log, f"thumb-line{i + 1}", thr=128)
        yb += size * 0.9
    # CASE FILE tab (top, text side) and the game as a red stamp under the words
    ft = mono(40, 800)
    tab = cov.get("tab", "CASE FILE")
    tw = int(ft.getlength(tab)) + 56
    t_im = paper(tw, 70, 91).copy()
    td = ImageDraw.Draw(t_im)
    td.rectangle([0, 0, 9, 69], fill=RED + (255,))
    td.text((30, 36), tab, font=ft, fill=INK + (255,), anchor="lm")
    t_im = shadowed(t_im, 8, (0, 6), 0.55, pad=20)
    put(dst, t_im, (x0 if left else TW_ - 56 - tw) - 20, 40 - 20, log, "thumb-tab", thr=200)
    st = WideCaseFile.stamp_img(th, (cov["game"],), cov.get("game_size", 92), -7, seed=7)
    gx = cov.get("game_x", x0 + st.width / 2 + 10 if left else TW_ - 56 - st.width / 2 - 10)
    K.place(dst, st, gx, cov.get("game_y", 600), log, "thumb-game", alpha=0.97, thr=60)
    img = Image.fromarray(np.clip(dst, 0, 255).astype(np.uint8))
    for n, a, b, c, e in log:  # keep 24 px clear of the edges and the duration badge (bottom-right 190x70)
        if a < 24 or b < 24 or c > TW_ - 24 or e > TH_ - 24:
            probs.append(f"{n} touches the edge")
        if c > TW_ - 190 and e > TH_ - 70:
            probs.append(f"{n} under the duration badge")
    q = 92
    while True:
        img.save(out, quality=q)
        import os
        size_b = os.path.getsize(out)
        if size_b <= 2e6 or q <= 70:
            break
        q -= 4
    return size_b, log, probs


def _red_circle_t(self, dst, cx, cy, rx, ry):
    T.CaseFile.red_circle(self, dst, cx, cy, rx, ry, 1.0, seed=3, width=12)


WideCaseFile.red_circle_t = _red_circle_t
