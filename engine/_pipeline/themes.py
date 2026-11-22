"""Look themes for the Shorts engine.

A theme owns: fonts, palette, caption system, plates/labels, the transitions used for each cut role, grade and texture,
the frame treatment of window clips, the hook treatment and one hero device. Looks: Panel Heist (comic
page), Case File (dossier), Vice Dusk (neon dusk); `classic` is the original Anton/yellow look. CSS/GSAP specs are ported as pure functions of time (same curves, durations,
sizes and colours), so every frame is reproducible.

Cut roles used in the edit list: "hook" (hook -> first beat), "triple" (into the wear/drive/with list), "reveal"
(into the stars line), "accent" (a secondary beat). Each theme maps the roles to its own transitions.
"""
import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import shortkit as K
from shortkit import FONTS, W, H, FPS, ease, back_out, lerp, clamp, rgba, font, text_img, blend, place, transform

F_ANTON = K.OLD_FONTS + "/Anton.woff2"
F_INTER = K.OLD_FONTS + "/Inter-var.woff2"
F_BIGSH = FONTS + "/bigshouldersdisplay/BigShouldersDisplay[wght].ttf"
F_JBM = FONTS + "/jetbrainsmono/JetBrainsMono[wght].ttf"
F_SPACE = FONTS + "/spacegrotesk/SpaceGrotesk[wght].ttf"
F_BOWLBY = FONTS + "/bowlbyone/BowlbyOne-Regular.ttf"
F_ARCHIVO = FONTS + "/archivo/Archivo[wdth,wght].ttf"
F_SERIF_I = FONTS + "/instrumentserif/InstrumentSerif-Italic.ttf"
F_HANKEN = FONTS + "/hankengrotesk/HankenGrotesk[wght].ttf"

OVERLAP = {"whip": 4, "whip16": 4, "skew": 4, "redact": 3}


def star_points(cx, cy, r, inner=0.45):
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * inner
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a) + r * 0.06))
    return pts


@lru_cache(maxsize=512)
def star_img(r, fill, stroke, stroke_w, hard_shadow=0, glow=None):
    """Five-point star, supersampled. fill/stroke are RGBA tuples; hard_shadow = ink offset px; glow = RGBA."""
    ss = 4
    pad = int(stroke_w + hard_shadow + (r if glow else 4) + 4)
    size = 2 * (r + pad)
    img = Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size * ss / 2
    if hard_shadow:
        pts = star_points(c + hard_shadow * ss, c + hard_shadow * ss, r * ss)
        d.line(pts + [pts[0]], fill=stroke, width=int(stroke_w * 2 * ss), joint="curve")
        d.polygon(pts, fill=stroke)
    pts = star_points(c, c, r * ss)
    if stroke_w:
        d.line(pts + [pts[0]], fill=stroke, width=int(stroke_w * 2 * ss), joint="curve")
        d.polygon(pts, fill=stroke)
    if fill[3]:
        d.polygon(pts, fill=fill)
    img = img.resize((size, size), Image.LANCZOS)
    if glow:
        g = Image.new("RGBA", img.size, glow[:3] + (0,))
        g.putalpha(img.getchannel("A").point(lambda v: int(v * glow[3] / 255)))
        g = g.filter(ImageFilter.GaussianBlur(r * 0.5))
        g.alpha_composite(img)
        img = g
    return img


class Theme:
    name = "base"
    bg_level = 0.6
    freeze_hold = 0.0
    roles = {}
    win_w, win_cy = 1000, 960
    star_cy, label_cy, star_r, star_pitch = 1436, 1324, 50, 116

    def __init__(self, edl):
        self.edl = edl
        self.clips = None
        self.renderer = None
        self.groups = self.make_groups()

    # ---------------------------------------------------------------- structure
    def transition_for(self, c):
        tr = c.get("transition")
        return self.roles.get(tr["role"], "cut") if tr else "cut"

    def handles(self, kind):
        return OVERLAP.get(kind, 0)

    def extend_handles(self, clips, edl):
        pass

    def window_box(self, c):
        lift = 70 if c.get("aspect") == "1:1" else 0  # square windows sit higher: the stars row needs the space
        return self.win_w, self.win_cy - lift

    # ---------------------------------------------------------------- transitions
    def overlap_frame(self, kind, f, cut, k, get_a, get_b):
        p = (f - (cut - k) + 0.5) / (2 * k)
        if kind in ("whip", "whip16"):
            e = ease("power3.inOut", p)
            off = int(round(e * W))
            out = np.empty((H, W, 3), np.uint8)
            if off < W:
                out[:, :W - off] = get_a(f)[:, off:]
            if off > 0:
                out[:, W - off:] = get_b(f)[:, :off]
            out = K.dir_blur(out, 70 * math.sin(math.pi * clamp(p)))
            if kind == "whip16":  # Vice Dusk: 1.6x push at the peak (transition frames only)
                out = K.zoom_img(out, 1 + 0.6 * math.sin(math.pi * clamp(p)))
            return out
        if kind == "skew":  # Panel Heist "Skew Wipe": paper panel skewed -8deg slides across, 220 ms power4.out
            a, b = get_a(f), get_b(f)
            e = ease("power4.out", p)
            band = 220
            sk = math.tan(math.radians(8)) * H
            lead = lerp(-band, W + band + sk, e)
            yy = np.arange(H, dtype=np.float32)[:, None]
            xx = np.arange(W, dtype=np.float32)[None, :]
            edge = lead - (H - yy) * (sk / H)  # leading edge, skewed
            out = np.where((xx < edge - band)[..., None], b, a)
            paper = (xx >= edge - band) & (xx < edge)
            out[paper] = (244, 239, 227)
            ink = ((xx >= edge - 5) & (xx < edge)) | ((xx >= edge - band) & (xx < edge - band + 5))
            out[ink] = (11, 11, 16)
            return out.astype(np.uint8)
        if kind == "redact":  # Case File "Redact Wipe": a black bar sweeps across, 180 ms, revealing the next shot
            a, b = get_a(f), get_b(f)
            e = ease("power3.out", p)
            band = 300
            lead = lerp(0, W + band, e)
            out = a.copy()
            x0 = int(clamp(lead - band, 0, W))
            x1 = int(clamp(lead, 0, W))
            out[:, :x0] = b[:, :x0]
            out[:, x0:x1] = (13, 17, 23)
            return out
        raise ValueError(kind)

    def post_cut(self, kind, img, d):
        """Effects that only touch the current frame, d = frame offset from the cut (negative = before)."""
        if kind == "flash" and -2 <= d <= 4:
            return K.mix(img, (255, 255, 255), {-2: 0.22, -1: 0.6, 0: 1.0, 1: 0.72, 2: 0.42, 3: 0.2, 4: 0.08}[d])
        if kind == "flash2" and d in (-2, -1):  # Panel Heist "Flash Frame": 2 white frames then the next shot
            return np.full_like(img, 255)
        if kind == "shutter" and -1 <= d <= 1:  # Case File "Shutter Cut": 3 black frames
            return np.full_like(img, 0)
        if kind == "zoom" and -5 <= d <= 4:
            if d < 0:
                q = (d + 6) / 5
                return K.zoom_img(img, 1 + 0.32 * ease("in", q), 0.03 * q)
            q = (d + 1) / 5
            return K.zoom_img(img, 1 + 0.32 * (1 - ease("out", q)), 0.03 * (1 - q))
        if kind == "zoom15" and -5 <= d <= 5:  # Vice "Zoom Through": 360 ms, 1 -> 1.5 into a flash, then settle
            if d < 0:
                q = (d + 6) / 6
                return K.mix(K.zoom_img(img, 1 + 0.5 * ease("power2.in", q), 0.03 * q), (255, 244, 230), 0.85 * q ** 2)
            q = d / 5
            return K.mix(K.zoom_img(img, 1 + 0.15 * (1 - ease("expo.out", q))), (255, 244, 230),
                         0.85 * (1 - ease("power3.out", q)))
        if kind == "gutter" and -4 <= d <= 3:
            return self.gutter_bars(img, (d + 4) / 8)
        if kind == "leak" and -6 <= d <= 6:  # Vice "Light Leak Sweep": 420 ms, cut at the brightest point
            return self.leak(img, (d + 6.5) / 13)
        if kind == "chroma" and -3 <= d <= 2:  # Vice "Chromatic Split": 200 ms, RGB offset up to 4 px
            off = int(round(4 * math.sin(math.pi * (d + 3.5) / 6)))
            if off:
                out = img.copy()
                out[:, off:, 0] = img[:, :-off, 0]
                out[:, :-off, 2] = img[:, off:, 2]
                return out
        return img

    @staticmethod
    def gutter_bars(img, p):
        """Panel Heist "Gutter Slam": two 24 px white bars slam from the edges to the centre and back, 240 ms."""
        out = img.copy()
        q = ease("power4.out", p / 0.5) if p < 0.5 else 1 - ease("power3.in", (p - 0.5) / 0.5)
        xl = int(lerp(-24, W / 2 - 24, q))
        xr = int(lerp(W, W / 2, q))
        for x in (xl, xr):
            a, b = max(0, x), min(W, x + 24)
            if b > a:
                out[:, a:b] = 255
                out[:, max(0, a - 4):a] = (11, 11, 16)
                out[:, b:min(W, b + 4)] = (11, 11, 16)
        return out

    @staticmethod
    def leak(img, p, strength=0.9):
        """Orange-blue light leak crossing the frame (screen blend), brightest at p = 0.5."""
        w, h = 135, 240
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        env = math.sin(math.pi * clamp(p)) * strength
        ox, oy = lerp(-0.45, 1.45, p) * w, lerp(0.75, 0.2, p) * h
        bx, by = ox - 0.5 * w, oy + 0.18 * h
        go = np.exp(-(((xx - ox) / (0.42 * w)) ** 2 + ((yy - oy) / (0.3 * h)) ** 2))
        gb = np.exp(-(((xx - bx) / (0.45 * w)) ** 2 + ((yy - by) / (0.32 * h)) ** 2))
        leak = (go[..., None] * np.array([255, 106, 26], np.float32) + gb[..., None] * np.array([47, 91, 255], np.float32)
                * 0.8) * env
        leak = np.asarray(Image.fromarray(np.clip(leak, 0, 255).astype(np.uint8)).resize((W, H), Image.BILINEAR),
                          np.float32)
        f = img.astype(np.float32)
        return (255 - (255 - f) * (1 - leak / 255)).astype(np.uint8)

    # ---------------------------------------------------------------- frame hooks (defaults)
    def base_hero(self, renderer, f):
        return None

    def post_base(self, img, t):
        return img

    def grade(self, img, fidx):
        return img

    def background(self, T, blurred):
        """Surface behind window clips; default = the clip's own blurred frame at bg_level."""
        return blurred * self.bg_level

    def compose_window(self, bg, fg, g, c, t):
        raise NotImplementedError

    def make_groups(self):
        raise NotImplementedError

    def overlay(self, img, t):
        dst = img.astype(np.float32)
        log = []
        self.draw_hero(dst, t, log)
        self.draw_hook(dst, t, log)
        self.draw_stars(dst, t, log)
        for g in self.groups:
            if g["start"] <= t and (g["end"] is None or t < g["end"]):
                self.draw_caption(dst, g, t, log)
        self.draw_credit(dst, log)
        return np.clip(dst, 0, 255).astype(np.uint8), log

    def draw_hero(self, dst, t, log):
        pass

    # ---------------------------------------------------------------- stars (shared timing, themed look)
    def star_layout(self, t):
        st = self.edl["stars"]
        q = ease("emil", (t - (st["slam"] - 0.12)) / 0.2)  # 5 slots re-centre into 6 just before 'six'
        xs = []
        for k in range(6):
            x5 = 495 + (k - 2) * self.star_pitch
            x6 = 495 + (k - 2.5) * self.star_pitch
            xs.append(x6 if k == 5 else lerp(x5, x6, q))  # the sixth slot appears in place (stays x <= 860)
        return xs, q

    def draw_stars(self, dst, t, log):
        st = self.edl.get("stars")
        if not st or not (st["start"] <= t < st["end"]):
            return
        xs, q = self.star_layout(t)
        r = self.star_r
        for k in range(6):
            if k < 5:
                t_on = st["ticks"][k]
                if t < t_on:
                    im = self.star_sprite(r, "slot")
                    place(dst, im, xs[k], self.star_cy, log, "star-slot", thr=40)
                    continue
                dt = t - t_on
                s = lerp(0.3, 1.0, back_out(dt / 0.18, 2.4)) if dt < 0.18 else 1.0
                state = "lit6" if t >= st["slam"] else "lit"
            else:
                if t < st["slam"] - 0.12:
                    continue  # five slots only: the sixth appears at the slam
                if t < st["slam"]:
                    im = self.star_sprite(r, "slot")
                    place(dst, im, xs[k], self.star_cy, log, "star-slot", alpha=q, thr=40)
                    continue
                dt = t - st["slam"]
                s = lerp(1.3, 1.0, ease("expo_out", dt / 0.16)) if dt < 0.16 else 1.0
                state = "six"
                if dt < 0.35:
                    self.slam_flash(dst, xs[k], self.star_cy, dt / 0.35)
            if t >= st["slam"] and k < 5:
                dts = t - st["slam"]
                if dts < 0.16:
                    s *= 1 + 0.12 * math.sin(math.pi * dts / 0.16)
            im = self.star_sprite(max(4, int(round(r * s))), state)
            place(dst, im, xs[k], self.star_cy, log, f"star{k + 1}", thr=40)
        lab = None
        for lt, txt in st["labels"]:
            if t >= lt:
                lab = (lt, txt)
        if lab:
            self.draw_star_label(dst, lab[1], t - lab[0], t, log)

    def slam_flash(self, dst, cx, cy, p):
        rad = int(self.star_r * (1.6 + 1.2 * p))
        yy, xx = np.mgrid[-rad:rad, -rad:rad]
        g = np.clip(1 - np.sqrt(xx ** 2 + yy ** 2) / rad, 0, 1) ** 1.5 * 255 * (1 - p)
        glow = np.zeros((2 * rad, 2 * rad, 4), np.float32)
        glow[..., :3] = (255, 250, 220)
        glow[..., 3] = g
        blend(dst, glow, cx - rad, cy - rad)

    # ---------------------------------------------------------------- helpers
    def clip_by_id(self, cid):
        return K.by_id(self.clips, cid)

    def hero_geom(self, t):
        """Screen-space ellipse around the hero detail (source rect in the hero clip) at time t."""
        hero = self.edl["hero"]
        c = self.clip_by_id(hero["clip"])
        g = K.window_geom(c, t - c["f0"] / FPS, self)
        x0, y0, x1, y1 = hero["detail_src"]
        a = K.src_to_screen(g, x0, y0)
        b = K.src_to_screen(g, x1, y1)
        return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (b[0] - a[0]) / 2, (b[1] - a[1]) / 2, g


# =================================================================================================== classic
class Classic(Theme):
    """The pilot's first look: Anton, white + yellow key word, heavy black stroke, sticker headline."""
    FONTS = [("Display / captions", "Anton", F_ANTON, None, "COPS HUNT YOUR OUTFIT?!"),
             ("Credit", "Inter 800", F_INTER, (800,), "Footage © <owner>")]
    PALETTE = [("white", "#FFFFFF"), ("yellow", "#FFE11A"), ("black stroke", "#000000")]
    HERO = "Hero device: drawn star row (five pop on 'five', the sixth slams in on 'six') over a HUD push-in."
    name = "classic"
    roles = {"hook": "whip", "triple": "zoom", "reveal": "flash"}
    freeze_hold = 0.2
    win_w, win_cy = 1000, 960
    YEL, WHT = (255, 225, 26), (255, 255, 255)

    def make_groups(self):
        cfg = self.edl["captions"]
        words = K.join_tokens(K.caption_words(self.edl), tuple(cfg.get("join_prefix", ())))
        hi = set(cfg.get("highlight", []))
        brk = set(cfg.get("break_before", []))
        groups, cur = [], []
        for w in words:
            if cur and (set(w["ids"]) & brk):
                groups.append(cur)
                cur = []
            cur.append(dict(w, text=w["text"].upper(), key=bool(set(w["ids"]) & hi)))
        groups.append(cur)
        res = []
        for gi, g in enumerate(groups):
            start = g[0]["s"] - 0.04
            if gi + 1 < len(groups):
                nxt = groups[gi + 1][0]["s"] - 0.04
                end = nxt if nxt - g[-1]["e"] <= 0.4 else g[-1]["e"] + 0.2
            else:
                end = None
            res.append({"words": g, "start": max(0, start), "end": end, "gi": gi})
        return res

    def compose_window(self, bg, fg, g, c, t):
        ww, wh, x0, y0 = g["ww"], g["wh"], g["wx0"], g["wy0"]
        sh, rim, mask = self._dress(ww, wh, x0, y0)
        bg *= 1 - 0.8 * sh
        reg = bg[y0:y0 + wh, x0:x0 + ww]
        bg[y0:y0 + wh, x0:x0 + ww] = reg * (1 - mask) + fg * mask
        a = rim[..., 3:4] / 255
        bg = bg * (1 - a) + rim[..., :3] * a
        return np.clip(bg, 0, 255).astype(np.uint8)

    @staticmethod
    @lru_cache(maxsize=8)
    def _dress(ww, wh, x0, y0):
        r = 22
        sh = Image.new("L", (W, H), 0)
        ImageDraw.Draw(sh).rounded_rectangle([x0 - 4, y0 + 10, x0 + ww + 3, y0 + wh + 16], r + 4, fill=190)
        sh = np.asarray(sh.filter(ImageFilter.GaussianBlur(14)), np.float32)[..., None] / 255
        rim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(rim)
        d.rounded_rectangle([x0 - 8, y0 - 8, x0 + ww + 7, y0 + wh + 7], r + 8, outline=(0, 0, 0, 255), width=4)
        d.rounded_rectangle([x0 - 5, y0 - 5, x0 + ww + 4, y0 + wh + 4], r + 5, outline=(255, 255, 255, 255), width=5)
        m = Image.new("L", (ww, wh), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, ww - 1, wh - 1], r, fill=255)
        return sh, np.asarray(rim, np.float32), np.asarray(m, np.float32)[..., None] / 255

    def grade(self, img, fidx):
        f = K.eq(img.astype(np.float32), 1.05, 1.06)
        f *= K.vignette_map(0.35)
        return np.clip(K.grain(f, 5.0, fidx), 0, 255).astype(np.uint8)

    @lru_cache(maxsize=2048)
    def word(self, text, size, col):
        ft = font(F_ANTON, size)
        im, base, adv = text_img(text, ft, rgba(col), stroke=max(2, int(size * 0.12)), pad=int(size * 0.12) + 14)
        return K.soft_shadow(im, max(3, size * 0.06), (0, max(3, int(size * 0.06))), (0, 0, 0), 0.7, pad=0), base

    def draw_caption(self, dst, g, t, log):
        if "_size" not in g:
            size = 116
            while size > 76:
                wsum = sum(alpha_w(self.word(w["text"], size, self.WHT)[0]) for w in g["words"])
                if wsum + size * 0.13 * (len(g["words"]) - 1) <= 640 / 1.1:
                    break
                size -= 2
            g["_size"] = size
        base = g["_size"]
        rel_t = t - g["start"]
        gs = lerp(0.6, 1.0, back_out(rel_t / 0.2, 2.0)) if rel_t < 0.2 else 1.0
        items = []
        for w in g["words"]:
            s = gs
            if w["key"] and 0 <= t - w["s"] < 0.22:
                s *= 1 + 0.14 * math.sin(math.pi * (t - w["s"]) / 0.22)
            im, bl = self.word(w["text"], max(10, int(round(base * s))), self.YEL if w["key"] else self.WHT)
            items.append((w, im, bl))
        boxes = [K.alpha_box(im) for _, im, _ in items]
        widths = [b[2] - b[0] for b in boxes]
        sp = base * 0.13 * gs
        x = 540 - (sum(widths) + sp * (len(items) - 1)) / 2
        baseline = 1110 + base * 0.36 * gs
        for (w, im, bl), b, wd in zip(items, boxes, widths):
            blend(dst, im, x - b[0], baseline - bl)
            log.append(("caption", x, baseline - bl + b[1], x + wd, baseline - bl + b[3]))
            x += wd + sp

    def draw_hook(self, dst, t, log):
        hk = self.edl["hook"]
        if not (0 <= t < hk["end"]):
            return
        land = 0.2
        if t < land:
            s = lerp(1.2, 1.0, ease("expo_out", t / land))
        elif t > hk["end"] - 0.14:
            s = lerp(1.0, 0.0, ease("in", (t - (hk["end"] - 0.14)) / 0.14))
        else:
            s = 1.0
        if s < 0.05:
            return
        im = self.headline(max(8, int(round(110 * s))))
        fi = int(round((t - land) * FPS))
        dx, dy = {0: (14, -8), 1: (-10, 5), 2: (4, -2)}.get(fi, (0, 0))
        if land + 0.02 <= t < land + 0.32:
            step = int((t - land - 0.02) * FPS) // 2
            off = 9 if step % 2 == 0 else -6
            for col, o in (((255, 30, 70), -off), ((30, 235, 255), off)):
                tint = Image.new("RGBA", im.size, col + (0,))
                tint.putalpha(im.getchannel("A").point(lambda v: int(v * 0.85)))
                blend(dst, tint, 540 + dx + o - im.width / 2, 480 + dy - im.height / 2)
        place(dst, im, 540 + dx, 480 + dy, log, "headline")

    @lru_cache(maxsize=64)
    def headline(self, size):
        lines = self.edl["hook"]["lines"]
        ims = [self.word(l, size, c)[0] for l, c in zip(lines, (self.WHT, self.YEL))]
        boxes = [K.alpha_box(i) for i in ims]
        w = max(b[2] - b[0] for b in boxes) + 40
        h = sum(b[3] - b[1] for b in boxes) + 40
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        y = 20
        for im, b in zip(ims, boxes):
            out.alpha_composite(im.crop(b), (int((w - (b[2] - b[0])) / 2), y))
            y += b[3] - b[1]
        return out

    def star_sprite(self, r, state):
        if state == "slot":
            return star_img(int(r * 0.9), (95, 95, 110, 180), (0, 0, 0, 180), 3)
        col = (255, 225, 26, 255) if state in ("lit6", "six") else (255, 255, 255, 255)
        return star_img(r, col, (0, 0, 0, 255), 4)

    def draw_star_label(self, dst, text, dt, t, log):
        s = lerp(0.6, 1.0, back_out(dt / 0.2, 2.0)) if dt < 0.2 else 1.0
        place(dst, self.word(text, max(8, int(64 * s)), self.WHT)[0], 495, self.label_cy, log, "stars-label")

    def draw_credit(self, dst, log):
        cr = self.edl["credit"]
        ft = font(F_INTER, 28, (800,))
        im, bl, adv = text_img(cr["text"], ft, (255, 255, 255, 235), stroke=5, stroke_fill=(0, 0, 0, 255))
        b = K.alpha_box(im)
        blend(dst, im, 132 - b[0], 1542 - b[1])
        log.append(("credit", 132, 1542, 132 + b[2] - b[0], 1542 + b[3] - b[1]))


def alpha_w(im):
    b = K.alpha_box(im)
    return b[2] - b[0]


# =================================================================================================== case file
class CaseFile(Theme):
    """Pack B "Case File": dossier look. Ink #0D1117, bone #EDE8DA, stamp red #E5352B, highlighter #FFE14D."""
    FONTS = [("Display", "Big Shoulders Display 900", F_BIGSH, (900,), "COPS HUNT YOUR OUTFIT?!"),
             ("Caption", "Space Grotesk 700", F_SPACE, (700,), "And witnesses tell them what you wear"),
             ("Label", "JetBrains Mono 800", F_JBM, (800,), "FILE 01 / EXHIBIT 05 · TOPIC")]
    PALETTE = [("ink", "#0D1117"), ("bone", "#EDE8DA"), ("stamp red", "#E5352B"), ("highlighter", "#FFE14D")]
    HERO = "Hero device: Circle and punch - a hand-drawn red circle draws onto the HUD stars, the frame dims outside it and pushes in, a file tab names the detail."
    name = "case-file"
    INK, BONE, RED, HI = (13, 17, 23), (237, 232, 218), (229, 53, 43), (255, 225, 77)
    roles = {"hook": "redact", "triple": "shutter", "reveal": "shutter", "accent": "cut"}
    freeze_hold = 0.25  # "Freeze Verdict"
    win_w, win_cy = 900, 930
    ANGLES = (-1.2, 1.0, -0.8, 1.3, -1.0, 0.9)

    def make_groups(self):
        return K.auto_groups(self.edl, 3, upper=False, first_start=0.20)

    # ---- grade: desaturate 15 %, cool shadows, vignette 20 %, grain 8 %
    def grade(self, img, fidx):
        f = K.eq(img.astype(np.float32), 1.0, 0.85)
        l = K.luma(f)[..., None] / 255
        f += (1 - l) ** 2 * np.array([-3, 2, 10], np.float32)
        f *= K.vignette_map(0.29)
        return np.clip(K.grain(f, 5.6, fidx), 0, 255).astype(np.uint8)

    # ---- background: a bone dossier sheet with a faint grid, red margin rule and paper noise, drifting slowly
    def background(self, T, blurred):
        tex = case_paper()
        ox = int(round(30 + 22 * math.sin(0.35 * T)))
        oy = int(round(30 + 22 * math.cos(0.28 * T)))
        return tex[oy:oy + H, ox:ox + W].copy()

    # ---- window = evidence photo: bone border, mono exhibit label, tape, slight tilt
    def window_box(self, c):
        lift = 180 if c.get("aspect") == "1:1" else 0  # square photos sit higher so the stamp and stars stay clear
        asp = K.aspect(c)
        if asp < 0.79:  # opt-in taller photo ("3:4" = 900x1200): it grows upwards, the bottom edge (exhibit label, credit) stays
            return self.win_w, self.win_cy + self.win_w / 0.8 / 2 - self.win_w / asp / 2
        return self.win_w, self.win_cy - lift

    def compose_window(self, bg, fg, g, c, t):
        ww, wh = g["ww"], g["wh"]
        ang = self.ANGLES[c["idx"] % len(self.ANGLES)]
        frame, label_box = self.photo_frame(ww, wh, ang, self.exhibit(c))
        photo = frame["base"].copy()
        photo.paste(Image.fromarray(fg), (frame["ox"], frame["oy"]))
        rot = photo.rotate(ang, Image.BICUBIC, expand=True)
        tape = frame["tape"]
        rot.alpha_composite(tape)
        cx, cy = W / 2, g["wy0"] + wh / 2 + 14
        x, y = int(cx - rot.width / 2), int(cy - rot.height / 2)
        bg = bg * frame["shadow_scale"]
        sh = frame["shadow"]
        sx, sy = int(cx - sh.shape[1] / 2) + 8, int(cy - sh.shape[0] / 2) + 14
        reg = bg[max(0, sy):sy + sh.shape[0], max(0, sx):sx + sh.shape[1]]
        s = sh[max(0, -sy):max(0, -sy) + reg.shape[0], max(0, -sx):max(0, -sx) + reg.shape[1]]
        reg *= 1 - 0.6 * s
        blend(bg, rot, x, y)
        if hasattr(self, "frame_text"):
            self.frame_text.append(("exhibit-label", label_box[0] + x, label_box[1] + y, label_box[2] + x,
                                    label_box[3] + y))
        return np.clip(bg, 0, 255).astype(np.uint8)

    @staticmethod
    def exhibit(c):
        """Label under the photo: the edit list's "exhibit" text, else the source file name."""
        if c.get("exhibit"):
            return f"EXHIBIT {c['idx'] + 1:02d} · {c['exhibit'].upper()}"
        stem = c["src"].split("/")[-1].rsplit(".", 1)[0]
        name = " ".join(stem.replace("_", " ").replace("-", " ").split())
        return f"EXHIBIT {c['idx'] + 1:02d} · {name.upper()}"

    @lru_cache(maxsize=32)
    def photo_frame(self, ww, wh, ang, label):
        b, bb = 16, 50
        ow, oh = ww + 2 * b, wh + b + bb
        base = Image.new("RGBA", (ow, oh), self.BONE + (255,))
        noise = np.random.default_rng(7).normal(0, 6, (oh, ow)).astype(np.float32)  # paper noise on bone only
        arr = np.asarray(base, np.float32)
        arr[..., :3] = np.clip(arr[..., :3] + noise[..., None], 0, 255)
        base = Image.fromarray(arr.astype(np.uint8))
        d = ImageDraw.Draw(base)
        ft = font(F_JBM, 22, (700,))
        d.text((b + 60, wh + b + 13), label, font=ft, fill=self.INK + (255,))
        lab_layer = Image.new("RGBA", (ow, oh), (0, 0, 0, 0))
        ImageDraw.Draw(lab_layer).text((b + 60, wh + b + 13), label, font=ft, fill=(0, 0, 0, 255))
        lab_rot = lab_layer.rotate(ang, Image.BICUBIC, expand=True)
        label_box = K.alpha_box(lab_rot)
        rot_size = base.rotate(ang, Image.BICUBIC, expand=True).size
        tape = Image.new("RGBA", rot_size, (0, 0, 0, 0))
        for tx, ty, ta in ((60, 18, 32), (rot_size[0] - 60, 22, -28)):
            strip = Image.new("RGBA", (150, 40), (243, 236, 205, 175))
            ImageDraw.Draw(strip).rectangle([0, 0, 149, 39], outline=(200, 190, 160, 120), width=1)
            strip = strip.rotate(ta, Image.BICUBIC, expand=True)
            tape.alpha_composite(strip, (int(tx - strip.width / 2), int(ty - strip.height / 2)))
        m = Image.new("L", rot_size, 0)
        ImageDraw.Draw(m).rectangle([0, 0, rot_size[0], rot_size[1]], fill=0)
        shadow = Image.new("L", (rot_size[0] + 60, rot_size[1] + 60), 0)
        shadow.paste(base.rotate(ang, Image.BICUBIC, expand=True).getchannel("A"), (30, 30))
        shadow = np.asarray(shadow.filter(ImageFilter.GaussianBlur(16)), np.float32)[..., None] / 255
        return {"base": base, "ox": b, "oy": b, "tape": tape, "shadow": shadow, "shadow_scale": 1.0}, label_box

    # ---- captions: 3 words, sentence case, Space Grotesk 700, bone on an ink chip, spoken word yellow
    def chip(self, g, active, size):
        ft = font(F_SPACE, size, (700,))
        words = [w["text"] for w in g["words"]]
        sp = ft.getlength(" ")
        adv = [ft.getlength(w) for w in words]
        lines = [list(range(len(words)))]
        if sum(adv) + sp * (len(words) - 1) > 730 - 52:
            k = max(1, (len(words) + 1) // 2)  # wrap after the first half (rounded up)
            lines = [list(range(k)), list(range(k, len(words)))]
        asc, desc = ft.getmetrics()
        cap = ft.getbbox("Hd")[1]
        lh = asc - cap + int(size * 0.24)
        lw = [sum(adv[i] for i in ln) + sp * (len(ln) - 1) for ln in lines]
        cw, chh = int(max(lw) + 52), int(lh * len(lines) + 28)
        im = Image.new("RGBA", (cw, chh), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, cw - 1, chh - 1], 14, fill=self.INK + (int(255 * 0.88),))
        y = 14
        for ln, w_ in zip(lines, lw):
            x = (cw - w_) / 2
            for i in ln:
                col = self.HI if i == active else self.BONE
                d.text((x, y + asc - cap), words[i], font=ft, fill=col + (255,), anchor="ls")
                x += adv[i] + sp
            y += lh
        return im

    def draw_caption(self, dst, g, t, log):
        if "_size" not in g:  # 80 px; 76 if that keeps the group on one line; else wrap at 80
            ft = font(F_SPACE, 76, (700,))
            one = sum(ft.getlength(w["text"]) for w in g["words"]) + ft.getlength(" ") * (len(g["words"]) - 1)
            ft80 = font(F_SPACE, 80, (700,))
            one80 = sum(ft80.getlength(w["text"]) for w in g["words"]) + ft80.getlength(" ") * (len(g["words"]) - 1)
            g["_size"] = 80 if one80 <= 678 else (76 if one <= 678 else 80)
        size = g["_size"]
        act = K.active_index(g, t)
        im = self.chip(g, act, size)
        p = (t - g["start"]) / 0.16
        e = ease("power3.out", p)
        op = e
        if g["gap_after"] and g["end"] is not None and t > g["end"] - 0.1:
            op = min(op, (g["end"] - t) / 0.1)
        place(dst, im, 495, 1110 + 18 * (1 - e), log, "caption", alpha=clamp(op))

    # ---- hook: file tab slides in from the left (revealed at the safe-zone edge), red circle draws on the detail
    @lru_cache(maxsize=4)
    def tab(self):
        hk = self.edl["hook"]
        ftl = font(F_JBM, 30, (800,))
        num, rest = hk["file"], " / " + hk["label"]
        maxw = 730 - 6 - 48
        size = 120
        while size > 80:
            fth = font(F_BIGSH, size, (900,))
            if max(fth.getlength(l) for l in hk["lines"]) <= maxw and size * 0.92 * len(hk["lines"]) + 70 <= 250:
                break
            size -= 4
        fth = font(F_BIGSH, size, (900,))
        lw = max(fth.getlength(l) for l in hk["lines"])
        w = int(max(lw, ftl.getlength(num + rest)) + 6 + 48)
        hgt = int(30 + 42 + size * 0.92 * len(hk["lines"]) + 14)
        im = Image.new("RGBA", (w, hgt), (0, 0, 0, 0))
        mask = Image.new("L", (w, hgt), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle([0, 0, w - 1, hgt - 1], 26, fill=255)
        md.rectangle([26, 0, w, hgt], fill=255)
        md.rectangle([0, 26, w, hgt], fill=255)
        plate = np.zeros((hgt, w, 4), np.float32)
        plate[..., :3] = self.BONE
        plate[..., :3] += np.random.default_rng(3).normal(0, 6, (hgt, w))[..., None]
        plate[..., 3] = np.asarray(mask, np.float32)
        plate[:, :6, :3] = self.RED
        im = Image.fromarray(np.clip(plate, 0, 255).astype(np.uint8), "RGBA")
        d = ImageDraw.Draw(im)
        d.text((30, 22), num, font=ftl, fill=self.RED + (255,), anchor="lt")
        d.text((30 + ftl.getlength(num), 22), rest, font=ftl, fill=self.INK + (255,), anchor="lt")
        y = 64
        for l in hk["lines"]:
            d.text((30, y), l, font=fth, fill=self.INK + (255,), anchor="lt")
            y += size * 0.92
        return K.soft_shadow(im, 10, (0, 8), (0, 0, 0), 0.5, pad=24)

    def draw_hook(self, dst, t, log):
        hk = self.edl["hook"]
        if t < hk["end"]:
            im = self.tab()
            tin = ease("power4.out", (t + 0.08) / 0.2)
            tout = ease("power3.in", (t - (hk["end"] - 0.16)) / 0.16) if t > hk["end"] - 0.16 else 0
            x = lerp(K.SAFE["x0"] - im.width, K.SAFE["x0"] - 24, tin - tout)
            # hook.y moves the tab down when the opening shot has a face under the default spot
            self.reveal_from_edge(dst, im, x, hk.get("y", 340) - 24, log, "file-tab")
        c0 = hk.get("circle")  # [rx, ry, [[t, cx, cy], ...]]: follows the detail through the opening shot
        cut = self.clips[1]["f0"] / FPS if self.clips else 1.37
        if c0 and t < cut:
            cx = K.anim([[k[0], k[1]] for k in c0[2]], 0, t)
            cy = K.anim([[k[0], k[2]] for k in c0[2]], 0, t)
            self.red_circle(dst, cx, cy, c0[0], c0[1], ease("power2.out", t / 0.35), seed=1)

    def reveal_from_edge(self, dst, im, x, y, log, name):
        """Draw im with everything left of the safe-zone edge cut away (slide-in that never leaves the zone)."""
        cut = int(round(K.SAFE["x0"] - x))
        if cut >= im.width:
            return
        if cut > 0:
            im = im.crop((cut, 0, im.width, im.height))
            x += cut
        blend(dst, im, x, y)
        b = K.alpha_box(im, 200)
        if b:
            log.append((name, x + b[0], y + b[1], x + b[2], y + b[3]))

    def red_circle(self, dst, cx, cy, rx, ry, p, seed=0, width=9):
        """Hand-drawn red circle drawing on (stroke-dashoffset port), 3 px wobble, ~375 degrees with overlap."""
        if p <= 0:
            return
        ss = 2
        pad = width * 2 + 8
        wd, ht = int(2 * rx + 2 * pad), int(2 * ry + 2 * pad)
        im = Image.new("RGBA", (wd * ss, ht * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        n = 90
        sweep = math.radians(375) * p
        a0 = math.radians(-110)
        pts = []
        for k in range(n + 1):
            a = a0 + sweep * k / n
            wob = 3 * math.sin(3 * a + seed) + 2 * math.sin(5 * a + 2 * seed)
            grow = 1 + 0.05 * (k / n) * p  # end overshoots a little outward, like a pen loop
            pts.append(((wd / 2 + (rx + wob) * grow * math.cos(a)) * ss, (ht / 2 + (ry + wob) * grow * math.sin(a)) * ss))
        d.line(pts, fill=self.RED + (255,), width=width * ss, joint="curve")
        im = im.resize((wd, ht), Image.LANCZOS)
        blend(dst, im, cx - wd / 2, cy - ht / 2)

    # ---- stars: bone stars, sixth highlighter yellow, label is a rubber stamp
    def star_sprite(self, r, state):
        if state == "slot":
            return star_img(int(r * 0.92), (0, 0, 0, 0), self.BONE + (200,), 3)
        col = self.HI if state == "six" else self.BONE
        return star_img(r, col + (255,), self.INK + (255,), 5)

    @lru_cache(maxsize=8)
    def stamp(self, text):
        ft = font(F_BIGSH, 64, (900,))
        im, bl, adv = text_img(text, ft, self.RED + (255,), tracking=0.08, pad=22)
        b = K.alpha_box(im)
        out = Image.new("RGBA", (b[2] - b[0] + 48, b[3] - b[1] + 36), (0, 0, 0, 0))
        out.alpha_composite(im.crop(b), (24, 18))
        ImageDraw.Draw(out).rectangle([3, 3, out.width - 4, out.height - 4], outline=self.RED + (255,), width=6)
        return out.rotate(6, Image.BICUBIC, expand=True)

    def draw_star_label(self, dst, text, dt, t, log):
        st = self.edl["stars"]
        ds = t - st["slam"]
        land = ds if 0 <= ds < dt else dt  # re-stamps on 'six'
        s = lerp(1.35, 1.0, ease("expo_out", land / 0.12)) if land < 0.12 else 1.0
        sx = 3 if 0 <= land < 0.08 and int(land * FPS) % 2 == 0 else (-3 if 0 <= land < 0.08 else 0)
        im = transform(self.stamp(text), scale=s)
        place(dst, im, 495 + sx, self.label_cy, log, "stars-stamp", alpha=0.92)

    # ---- hero: red circle + Focus Punch (dim outside a soft circle) on the HUD at 'six', file-tab label
    def post_base(self, img, t):
        hero = self.edl.get("hero")
        if not hero or not (hero["t"] <= t < hero["end"]):
            return img
        cx, cy, rx, ry, g = self.hero_geom(t)
        p = ease("power2.out", (t - hero["t"]) / 0.45)
        return dim_outside(img, cx, cy, max(rx, ry) * 1.9, 0.35 * p)

    def draw_hero(self, dst, t, log):
        hero = self.edl.get("hero")
        if not hero or not (hero["t"] <= t < hero["end"]):
            return
        cx, cy, rx, ry, g = self.hero_geom(t)
        self.red_circle(dst, cx, cy, rx * 1.35 + 20, ry * 1.8 + 26, ease("power2.out", (t - hero["t"]) / 0.4), seed=2)
        im = self.hero_tab(hero["label"])
        tin = ease("power4.out", (t - hero["t"] - 0.1) / 0.2)
        if tin > 0:
            self.reveal_from_edge(dst, im, lerp(K.SAFE["x0"] - im.width, K.SAFE["x0"] - 24, tin), 330, log, "hero-tab")

    @lru_cache(maxsize=4)
    def hero_tab(self, label):
        ft = font(F_JBM, 34, (800,))
        w = int(ft.getlength(label) + 6 + 44)
        im = Image.new("RGBA", (w, 70), self.BONE + (255,))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 5, 69], fill=self.RED + (255,))
        d.text((26, 35), label, font=ft, fill=self.INK + (255,), anchor="lm")
        return K.soft_shadow(im, 8, (0, 6), (0, 0, 0), 0.5, pad=24)

    def draw_credit(self, dst, log):
        cr = self.edl["credit"]
        ft = font(F_JBM, 24, (700,))  # bone mono on a small ink chip: readable on footage and on the bone sheet
        w = int(ft.getlength(cr["text"])) + 28
        im = Image.new("RGBA", (w, 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, w - 1, 39], 8, fill=self.INK + (int(255 * 0.88),))
        d.text((14, 20), cr["text"], font=ft, fill=self.BONE + (255,), anchor="lm")
        blend(dst, im, 132, 1538)
        log.append(("credit", 132, 1538, 132 + w, 1578))


@lru_cache(maxsize=1)
def case_paper():
    """Bone dossier sheet (oversized by 60 px each way for drift): grid every 54 px, stronger every 5th, a red
    margin rule, a slightly darker folder band at the bottom, paper noise and a soft ink vignette."""
    h, w = H + 60, W + 60
    bone = np.array(CaseFile.BONE, np.float32)
    f = np.empty((h, w, 3), np.float32)
    f[:] = bone
    yy, xx = np.mgrid[0:h, 0:w]
    ink = np.array(CaseFile.INK, np.float32)
    for step, a in ((54, 0.07), (270, 0.10)):
        line = ((xx % step) < 2) | ((yy % step) < 2)
        f[line] = f[line] * (1 - a) + ink * a
    red = (xx >= 118) & (xx < 121)
    f[red] = f[red] * 0.45 + np.array(CaseFile.RED, np.float32) * 0.55
    folder = yy > h - 330
    f[folder] *= np.array([0.93, 0.91, 0.86], np.float32)
    f += np.random.default_rng(11).normal(0, 5, (h, w))[..., None]
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    f *= (1 - 0.18 * np.clip(d - 0.6, 0, None))[..., None]
    return np.clip(f, 0, 255)


@lru_cache(maxsize=64)
def _dim_mask(cx, cy, r, strength):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    soft = np.clip((d - r) / (0.6 * r), 0, 1)
    return (1 - strength * soft)[..., None]


def dim_outside(img, cx, cy, r, strength):
    if strength <= 0.01:
        return img
    m = _dim_mask(int(cx) // 4 * 4, int(cy) // 4 * 4, int(r) // 4 * 4, round(strength, 2))
    return (img.astype(np.float32) * m).astype(np.uint8)


# =================================================================================================== panel heist
class PanelHeist(Theme):
    """Pack A "Panel Heist": comic panels, white gutters, halftone corners. Ink #0B0B10, paper #F4EFE3,
    Vice pink #FF2E88, sun yellow #FFD23F, teal #11C5C9. Evokes a retro vice-city poster look."""
    FONTS = [("Display", "Bowlby One", F_BOWLBY, None, "COPS HUNT YOUR OUTFIT?!"),
             ("Caption", "Archivo 900 (wdth 100)", F_ARCHIVO, (900, 100), "WHAT YOU WEAR"),
             ("Credit", "Archivo 800", F_ARCHIVO, (800, 100), "Footage © <owner>")]
    PALETTE = [("ink", "#0B0B10"), ("paper", "#F4EFE3"), ("Vice pink", "#FF2E88"), ("sun yellow", "#FFD23F"),
               ("teal", "#11C5C9")]
    HERO = "Hero device: Panel Split - on 'who you're with' the frame breaks into three angled panels (wear, drive, with) with white gutters."
    name = "panel-heist"
    INK, PAPER, PINK, YEL, TEAL = (11, 11, 16), (244, 239, 227), (255, 46, 136), (255, 210, 63), (17, 197, 201)
    roles = {"hook": "gutter", "triple": "skew", "reveal": "flash2", "accent": "cut"}
    freeze_hold = 0.3  # "Freeze Pop"
    win_w, win_cy = 960, 922

    def make_groups(self):
        return K.auto_groups(self.edl, 2, upper=True, first_start=-0.075)

    # ---- grade: contrast +8 %, saturation +6 %, halftone in two corners (10 % multiply, teal), grain 6 %
    def grade(self, img, fidx):
        f = K.eq(img.astype(np.float32), 1.08, 1.06)
        f *= halftone_map()
        return np.clip(K.grain(f, 4.2, fidx), 0, 255).astype(np.uint8)

    # ---- background: a comic page, paper field with ink halftone dots growing toward two corners, a teal dot
    #      corner and a page keyline; the dot screen drifts slowly
    def background(self, T, blurred):
        tex = panel_page()
        ox = int(round(T * 9)) % 14
        oy = int(round(T * 6)) % 14
        f = tex[oy:oy + H, ox:ox + W].copy()
        f[:, :6] = self.INK
        f[:, W - 6:] = self.INK
        return f

    # ---- window = comic panel: white gutter, ink keyline, hard ink shadow
    def compose_window(self, bg, fg, g, c, t):
        ww, wh, x0, y0 = g["ww"], g["wh"], g["wx0"], g["wy0"]
        gut = 16
        bg[y0 + 12 - gut:y0 + wh + 12 + gut, x0 + 12 - gut:x0 + ww + 12 + gut] *= 0.25  # hard ink shadow
        bg[y0 - gut - 5:y0 + wh + gut + 5, x0 - gut - 5:x0 + ww + gut + 5] = self.INK
        bg[y0 - gut:y0 + wh + gut, x0 - gut:x0 + ww + gut] = 255
        bg[y0:y0 + wh, x0:x0 + ww] = fg
        return np.clip(bg, 0, 255).astype(np.uint8)

    # ---- captions: 2 words UPPERCASE Archivo 900, paper with hard 8/8 ink shadow, spoken word on a pink pill
    @lru_cache(maxsize=1024)
    def group_img(self, gi, active, size, wdth=100, stack=False):
        g = self.groups[gi]
        ft = font(F_ARCHIVO, size, (900, wdth))
        asc, desc = ft.getmetrics()
        pieces = []
        for k, w in enumerate(g["words"]):
            txt = w["text"]
            adv = ft.getlength(txt)
            bb = ft.getbbox(txt, anchor="ls")
            pad = 26
            im = Image.new("RGBA", (int(adv) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            bx, by = pad, pad + asc
            if k == active:
                d.rounded_rectangle([bx + bb[0] - 18, by + bb[1] - 6, bx + bb[2] + 18, by + bb[3] + 6], 12,
                                    fill=self.PINK + (255,))
                d.text((bx, by), txt, font=ft, fill=self.INK + (255,), anchor="ls")
            else:
                d.text((bx + 8, by + 8), txt, font=ft, fill=self.INK + (255,), anchor="ls")
                d.text((bx, by), txt, font=ft, fill=self.PAPER + (255,), anchor="ls")
            pieces.append((im, adv, pad))
        gap = size * 0.34
        if stack:  # too wide even condensed: one word per line
            lh = int(size * 1.08)
            out = Image.new("RGBA", (int(max(p[1] for p in pieces)) + 60, asc + desc + 52 + lh * (len(pieces) - 1)),
                            (0, 0, 0, 0))
            for k, (im, adv, pad) in enumerate(pieces):
                out.alpha_composite(im, (int(30 + (out.width - 60 - adv) / 2 - pad), k * lh))
            return out
        tw = sum(p[1] for p in pieces) + gap * (len(pieces) - 1)
        out = Image.new("RGBA", (int(tw) + 60, asc + desc + 52), (0, 0, 0, 0))
        x = 30
        for im, adv, pad in pieces:
            out.alpha_composite(im, (int(x - pad + 0), 0))
            x += adv + gap
        return out

    def fit(self, g):
        """104 -> 76 px at wdth 100 (spec); if a group still overflows the 730 px box, condense the width axis down
        to 75, and only then stack the two words."""
        if "_fit" not in g:
            states = [None] + list(range(len(g["words"])))

            def ok(size, wdth, stack=False):
                return max(alpha_w(self.group_img(g["gi"], a, size, wdth, stack)) for a in states) * 1.06 <= 730
            res = None
            for size in range(104, 75, -2):
                if ok(size, 100):
                    res = (size, 100, False)
                    break
            if res is None:
                for wdth in range(95, 74, -5):
                    if ok(76, wdth):
                        res = (76, wdth, False)
                        break
            g["_fit"] = res or (88, 100, True)
        return g["_fit"]

    def draw_caption(self, dst, g, t, log):
        size, wdth, stack = self.fit(g)
        act = K.active_index(g, t)
        im = self.group_img(g["gi"], act, size, wdth, stack)
        b = back_out((t - g["start"]) / 0.15, 1.8)
        op = 1.0
        if g["gap_after"] and g["end"] is not None and t > g["end"] - 0.08:
            op = clamp((g["end"] - t) / 0.08)
        im = transform(im, scale=lerp(0.7, 1.0, b), rot=3 * (1 - b))
        place(dst, im, 495, 1120 + 24 * (1 - b), log, "caption", alpha=op)

    # ---- plates: paper, 5 px ink border, hard 10 px ink shadow, 2 deg tilt, yellow tape; Bowlby One
    @lru_cache(maxsize=16)
    def plate(self, lines, maxsize=96, minsize=56, box_w=640):
        size = maxsize
        while size > minsize:
            ft = font(F_BOWLBY, size)
            if max(ft.getlength(l) for l in lines) <= box_w - 56:
                break
            size -= 2
        ft = font(F_BOWLBY, size)
        asc, desc = ft.getmetrics()
        lh = int(size * 1.02)
        w = int(max(ft.getlength(l) for l in lines) + 56)
        h = int(lh * len(lines) + 36)
        im = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([10 + 10, 10 + 10, 10 + w + 10, 10 + h + 10], fill=self.INK + (255,))
        d.rectangle([10, 10, 10 + w, 10 + h], fill=self.PAPER + (255,), outline=self.INK + (255,), width=5)
        y = 10 + 18
        for l in lines:
            d.text((10 + w / 2, y), l, font=ft, fill=self.INK + (255,), anchor="mt")
            y += lh
        tape = Image.new("RGBA", (72, 32), self.YEL + (235,)).rotate(20, Image.BICUBIC, expand=True)
        im.alpha_composite(tape, (0, 0))
        return im

    def draw_plate(self, dst, lines, t0, t1, t, cy, log, name):
        p = (t - t0) / 0.22
        if p < 0:
            return
        b = back_out(p, 1.4)
        dy, rot, op = -60 * (1 - b), -(2 + 3 * (1 - b)), 1.0
        if t > t1 - 0.12:
            q = clamp((t - (t1 - 0.12)) / 0.12)
            dy -= 40 * q
            op = 1 - q
        if op <= 0:
            return
        im = transform(self.plate(tuple(lines)), rot=rot)
        place(dst, im, 495, cy + dy, log, name, alpha=op, thr=200)

    def post_base(self, img, t):
        if 0.10 <= t < 0.34:  # hook: Gutter Slam crashes in and out on the headline (240 ms)
            return self.gutter_bars(img, (t - 0.10) / 0.24)
        return img

    def draw_hook(self, dst, t, log):
        hk = self.edl["hook"]
        if t < hk["end"]:
            self.draw_plate(dst, hk["lines"], -0.12, hk["end"], t, 450, log, "plate")

    # ---- stars: yellow stars (a number) with ink keyline + hard shadow, label on a small paper plate
    def star_sprite(self, r, state):
        if state == "slot":
            return star_img(int(r * 0.92), self.PAPER + (110,), self.INK + (200,), 3)
        col = self.YEL if state in ("lit", "lit6", "six") else self.PAPER
        return star_img(r, col + (255,), self.INK + (255,), 5, hard_shadow=6)

    def draw_star_label(self, dst, text, dt, t, log):
        st = self.edl["stars"]
        ds = t - st["slam"]
        t0 = st["slam"] if ds >= 0 else t - dt  # the sticker re-lands on 'six' (Freeze Pop)
        p = (t - t0) / 0.22
        b = back_out(p, 1.4)
        im = transform(self.plate((text,), maxsize=60, minsize=40, box_w=320), rot=-(2 + 3 * (1 - b)))
        place(dst, im, 495, self.label_cy - 60 * (1 - b) * 0.5, log, "stars-label", thr=200)

    # ---- hero: Panel Split on 'and who you're with' (three angled panels: wear frozen, drive, with)
    def extend_handles(self, clips, edl):
        sp = edl.get("hero", {}).get("split")
        if not sp:
            return
        f1 = K.frames(sp["end"])
        for cid in sp["live"]:
            c = K.by_id(clips, cid)
            c["post"] = max(c["post"], f1 - c["f1"])

    def base_hero(self, renderer, f):
        sp = self.edl.get("hero", {}).get("split")
        if not sp or not (K.frames(sp["start"]) <= f < K.frames(sp["end"])):
            return None
        t = f / FPS
        main = renderer.clip_frame_id(sp["main"], f)
        out = np.empty_like(main)
        out[:] = np.roll(main, sp.get("main_shift", 330), axis=0)
        out[:sp.get("main_shift", 330)] = main[:1].mean(axis=0, keepdims=True)
        live = renderer.clip_frame_id(sp["live"][0], f)
        frozen = renderer.last_frame_id(sp["frozen"][0])
        q = (t - sp["start"]) / (sp["end"] - sp["start"])
        frozen = K.zoom_img(frozen, 1 + 0.06 * q)
        e = back_out((t - sp["start"]) / 0.15, 1.8)
        drop = int(round(-800 * (1 - e)))
        mA, mB, gut = split_masks()
        a_src = np.roll(frozen, (-520, -260), axis=(0, 1))
        b_src = np.roll(live, (-560, 270), axis=(0, 1))
        if drop:
            mA = np.roll(mA, drop, axis=0)
            mB = np.roll(mB, drop, axis=0)
            gut = np.roll(gut, drop, axis=0)
            if drop < 0:
                mA[drop:] = 0
                mB[drop:] = 0
                gut[drop:] = 0
            a_src = np.roll(a_src, drop, axis=0)
            b_src = np.roll(b_src, drop, axis=0)
        o = out.astype(np.float32)
        o = o * (1 - mA) + a_src * mA
        o = o * (1 - mB) + b_src * mB
        g = gut[..., :1]
        o = o * (1 - g) + gut[..., 1:] * g
        return np.clip(o, 0, 255).astype(np.uint8)

    def draw_credit(self, dst, log):
        cr = self.edl["credit"]
        ft = font(F_ARCHIVO, 25, (800, 100))  # ink on a small paper plate with an ink keyline (page or footage)
        w = int(ft.getlength(cr["text"])) + 26
        im = Image.new("RGBA", (w + 6, 46), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([5, 5, w + 5, 45], fill=self.INK + (255,))
        d.rectangle([0, 0, w, 40], fill=self.PAPER + (255,), outline=self.INK + (255,), width=3)
        d.text((13, 21), cr["text"], font=ft, fill=self.INK + (255,), anchor="lm")
        blend(dst, im, 132, 1532)
        log.append(("credit", 132, 1532, 132 + w + 6, 1578))


@lru_cache(maxsize=1)
def panel_page():
    """Paper field with an ink halftone screen (9 px pitch) whose dots grow toward the top-right and bottom-left
    corners, plus a teal screen in the top-left corner (oversized by 14 px for drift)."""
    h, w = H + 14, W + 14
    f = np.empty((h, w, 3), np.float32)
    f[:] = PanelHeist.PAPER
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d1 = np.sqrt((w - xx) ** 2 + yy ** 2) / 900
    d2 = np.sqrt(xx ** 2 + (h - yy) ** 2) / 900
    cover = np.clip(1 - np.minimum(d1, d2), 0, 1)
    cx, cy = (xx % 14) - 7, (yy % 14) - 7
    dot = np.sqrt(cx ** 2 + cy ** 2) < 6.0 * np.sqrt(cover)
    f[dot] = f[dot] * 0.82 + np.array(PanelHeist.INK, np.float32) * 0.18
    dt = np.sqrt(xx ** 2 + yy ** 2) / 520
    tcover = np.clip(1 - dt, 0, 1)
    tdot = np.sqrt(cx ** 2 + cy ** 2) < 6.0 * np.sqrt(tcover)
    f[tdot] = f[tdot] * 0.7 + np.array(PanelHeist.TEAL, np.float32) * 0.3
    return f


@lru_cache(maxsize=1)
def halftone_map():
    """Halftone dots (7 px pitch) in the top-left and bottom-right corners, about 18 % of the frame, teal multiply
    at 10 % opacity."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = 490
    d1 = np.sqrt(xx ** 2 + yy ** 2) / r
    d2 = np.sqrt((W - xx) ** 2 + (H - yy) ** 2) / r
    cover = np.clip(1 - np.minimum(d1, d2), 0, 1)
    cx = (xx % 7) - 3.5
    cy = (yy % 7) - 3.5
    dot = (np.sqrt(cx ** 2 + cy ** 2) < 3.4 * np.sqrt(cover)).astype(np.float32)
    teal = np.array([17, 197, 201], np.float32) / 255
    a = (0.10 * dot * (cover > 0))[..., None]
    return (1 - a) + a * teal


@lru_cache(maxsize=1)
def split_masks():
    """Panel Split layout: a diagonal gutter (y 770 at the left to 650 at the right) and a slanted vertical gutter
    (x 575 at the top to 520 at the diagonal). A = top-left, B = top-right, the big panel is everything below."""
    ss = 2
    a = Image.new("L", (W * ss, H * ss), 0)
    b = Image.new("L", (W * ss, H * ss), 0)
    gl = Image.new("RGBA", (W * ss, H * ss), (0, 0, 0, 0))
    dA = ImageDraw.Draw(a)
    dB = ImageDraw.Draw(b)
    yl, yr = 770, 650
    xt, xb = 575, 520
    yb = yl + (yr - yl) * xb / W
    dA.polygon([(0, 0), (xt * ss, 0), (xb * ss, yb * ss), (0, yl * ss)], fill=255)
    dB.polygon([(xt * ss, 0), (W * ss, 0), (W * ss, yr * ss), (xb * ss, yb * ss)], fill=255)
    dg = ImageDraw.Draw(gl)
    for wdt, col in ((26, (11, 11, 16, 255)), (16, (255, 255, 255, 255))):
        dg.line([(0, yl * ss), (W * ss, yr * ss)], fill=col, width=wdt * ss)
        dg.line([(xt * ss, 0), (xb * ss, yb * ss)], fill=col, width=wdt * ss)
    a = np.asarray(a.resize((W, H), Image.LANCZOS), np.float32)[..., None] / 255
    b = np.asarray(b.resize((W, H), Image.LANCZOS), np.float32)[..., None] / 255
    g = np.asarray(gl.resize((W, H), Image.LANCZOS), np.float32)
    gut = np.concatenate([g[..., 3:] / 255, g[..., :3]], axis=2)
    return a, b, gut


# =================================================================================================== vice dusk
class ViceDusk(Theme):
    """Pack C "Vice Dusk": blue/orange grade, soft kinetic captions, frosted glass. Night #07101F, luminous blue
    #2F5BFF, energy orange #FF6A1A, cloud #F6F4EE."""
    FONTS = [("Hero word", "Instrument Serif Italic", F_SERIF_I, None, "your outfit?"),
             ("Caption", "Hanken Grotesk 800", F_HANKEN, (800,), "And witnesses tell them"),
             ("Label", "Hanken Grotesk 800, tracked", F_HANKEN, (800,), "WANTED LEVEL")]
    PALETTE = [("night", "#07101F"), ("luminous blue", "#2F5BFF"), ("energy orange", "#FF6A1A"), ("cloud", "#F6F4EE"),
               ("pop pink", "#FF5FA2")]
    HERO = "Hero device: Glass title - 'six' in Instrument Serif italic sweeps in on frosted glass behind a light leak, labelled WANTED LEVEL."
    name = "vice-dusk"
    NIGHT, BLUE, ORANGE, CLOUD = (7, 16, 31), (47, 91, 255), (255, 106, 26), (246, 244, 238)
    roles = {"hook": "whip16", "triple": "zoom15", "reveal": "leak", "accent": "chroma"}
    freeze_hold = 0.0
    win_w, win_cy = 980, 930

    def make_groups(self):
        return K.auto_groups(self.edl, 3, upper=False, first_start=0.25)

    # ---- grade: blue shadows (+0.06), orange highlights (+0.05 red), bloom 12 % screen, vignette 15 %, grain 4 %
    def grade(self, img, fidx):
        f = K.eq(img.astype(np.float32), 1.04, 1.05)
        l = K.luma(f)[..., None] / 255
        f += (1 - l) ** 2 * np.array([-4, 4, 0.06 * 255], np.float32)
        f += l ** 2 * np.array([0.05 * 255, 0.02 * 255, -6], np.float32)
        f = np.clip(f, 0, 255)
        bloom = K.blur_small(np.clip(f, 0, 255).astype(np.uint8), 8, 3)
        f = 255 - (255 - f) * (1 - 0.12 * bloom / 255)
        f *= K.vignette_map(0.22)
        return np.clip(K.grain(f, 2.8, fidx), 0, 255).astype(np.uint8)

    # ---- background: deep night-to-blue gradient with an orange horizon glow, two soft light blobs drifting and a
    #      faint screen of the clip itself (glass)
    def background(self, T, blurred):
        w, h = 135, 240
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        v = yy / h
        night, blue, orange = (np.array(c, np.float32) for c in (self.NIGHT, self.BLUE, self.ORANGE))
        g = night * (1 - v[..., None]) + blue * 0.55 * v[..., None]
        glow = np.exp(-((v - 0.92) / 0.16) ** 2)[..., None]
        g = g * (1 - 0.55 * glow) + orange * 0.55 * glow
        for (bx, by, bs, col, a) in ((0.25 + 0.08 * math.sin(0.3 * T), 0.28 + 0.04 * math.cos(0.25 * T), 0.35,
                                      blue, 0.35), (0.78 + 0.07 * math.cos(0.22 * T), 0.7 + 0.05 * math.sin(0.3 * T),
                                                    0.3, orange, 0.28)):
            b = np.exp(-(((xx / w - bx) / bs) ** 2 + ((yy / h - by) / (bs * 0.6)) ** 2))[..., None]
            g = 255 - (255 - g) * (1 - a * b * col / 255)
        g = np.asarray(Image.fromarray(np.clip(g, 0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC),
                       np.float32)
        return 255 - (255 - g) * (1 - 0.22 * blurred / 255)

    # ---- window = glass-framed still: rounded 28 px, 1.5 px cloud border at 60 %, soft glow
    def compose_window(self, bg, fg, g, c, t):
        ww, wh, x0, y0 = g["ww"], g["wh"], g["wx0"], g["wy0"]
        sh, mask, rim = self._dress(ww, wh, x0, y0)
        bg = bg * (1 - 0.55 * sh) + sh * np.array(self.BLUE, np.float32) * 0.18
        reg = bg[y0:y0 + wh, x0:x0 + ww]
        bg[y0:y0 + wh, x0:x0 + ww] = reg * (1 - mask) + fg * mask
        a = rim[..., 3:4] / 255
        bg = bg * (1 - a) + rim[..., :3] * a
        return np.clip(bg, 0, 255).astype(np.uint8)

    @staticmethod
    @lru_cache(maxsize=8)
    def _dress(ww, wh, x0, y0):
        r = 28
        sh = Image.new("L", (W, H), 0)
        ImageDraw.Draw(sh).rounded_rectangle([x0 - 6, y0 + 6, x0 + ww + 6, y0 + wh + 26], r + 6, fill=210)
        sh = np.asarray(sh.filter(ImageFilter.GaussianBlur(26)), np.float32)[..., None] / 255
        m = Image.new("L", (ww * 2, wh * 2), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, ww * 2 - 1, wh * 2 - 1], r * 2, fill=255)
        m = np.asarray(m.resize((ww, wh), Image.LANCZOS), np.float32)[..., None] / 255
        rim = Image.new("RGBA", (W * 2, H * 2), (0, 0, 0, 0))
        ImageDraw.Draw(rim).rounded_rectangle([x0 * 2, y0 * 2, (x0 + ww) * 2 - 1, (y0 + wh) * 2 - 1], r * 2,
                                              outline=(246, 244, 238, 153), width=3)
        rim = np.asarray(rim.resize((W, H), Image.LANCZOS), np.float32)
        return sh, m, rim

    # ---- captions: Hanken Grotesk 800, 84 px, sentence case, cloud with soft shadow + 6 px outline at 35 % night,
    #      spoken word orange; per-word entrance y+28, blur 8, opacity, 200 ms expo.out, 40 ms stagger
    @lru_cache(maxsize=2048)
    def word(self, text, col, size):
        ft = font(F_HANKEN, size, (800,))
        im, bl, adv = text_img(text, ft, col + (255,), stroke=6, stroke_fill=self.NIGHT + (89,), pad=10)
        return K.soft_shadow(im, 12, (0, 4), (5, 10, 25), 0.55, pad=30), bl + 30, adv

    def fit(self, g):
        if "_size" not in g:
            size = 84
            while size > 76:
                ft = font(F_HANKEN, size, (800,))
                tw = sum(ft.getlength(w["text"]) for w in g["words"]) + ft.getlength(" ") * (len(g["words"]) - 1)
                if tw + 12 <= 730:
                    break
                size -= 2
            g["_size"] = size
        return g["_size"]

    def draw_caption(self, dst, g, t, log):
        size = self.fit(g)
        ft = font(F_HANKEN, size, (800,))
        act = K.active_index(g, t)
        sp = ft.getlength(" ")
        advs = [ft.getlength(w["text"]) for w in g["words"]]
        x = 495 - (sum(advs) + sp * (len(advs) - 1)) / 2
        base_y = 1110 + size * 0.36
        ex_y, ex_op = 0.0, 1.0
        tw = sum(advs) + sp * (len(advs) - 1)
        e0 = ease("expo_out", (t - g["start"]) / 0.2)
        if g["gap_after"] and g["end"] is not None and t > g["end"] - 0.12:
            e0 *= 1 - ease("power3.in", (t - (g["end"] - 0.12)) / 0.12)
        blend(dst, self.underlay(int(tw)), 495 - (tw + 240) / 2, 1110 - 110, alpha=e0)
        if g["gap_after"] and g["end"] is not None and t > g["end"] - 0.12:
            q = ease("power3.in", (t - (g["end"] - 0.12)) / 0.12)
            ex_y, ex_op = -10 * q, 1 - q
        for k, (w, adv) in enumerate(zip(g["words"], advs)):
            e = ease("expo_out", (t - g["start"] - 0.04 * k) / 0.2)
            if e <= 0:
                x += adv + sp
                continue
            col = self.ORANGE if k == act else self.CLOUD
            im, bl, _ = self.word(w["text"], col, size)
            if e < 0.98:
                im = transform(im, blur=8 * (1 - e))
            y = base_y + 28 * (1 - e) + ex_y - bl
            pad_x = 30 + 10
            blend(dst, im, x - pad_x, y, alpha=e * ex_op)
            b = K.alpha_box(im, 200)
            if b and e * ex_op > 0.05:
                log.append(("caption", x - pad_x + b[0], y + b[1], x - pad_x + b[2], y + b[3]))
            x += adv + sp

    @lru_cache(maxsize=64)
    def underlay(self, tw):
        """Soft 40 % night underlay behind a caption line (the spec's glass underlay, applied to captions so cloud
        text stays readable over bright footage)."""
        w, h = tw + 240, 220
        im = Image.new("RGBA", (w, h), self.NIGHT + (0,))
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rounded_rectangle([90, 70, w - 90, h - 70], 40, fill=int(255 * 0.42))
        im.putalpha(m.filter(ImageFilter.GaussianBlur(34)))
        return im

    # ---- glass plates: blur 18 behind, 40 % night underlay, cloud fill 0.28, 1.5 px cloud border at 60 %
    def glass(self, dst, x0, y0, x1, y1, r=28, strength=1.0):
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        x0c, y0c, x1c, y1c = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        if x1c <= x0c or y1c <= y0c or strength <= 0:
            return
        reg = dst[y0c:y1c, x0c:x1c]
        im = Image.fromarray(np.clip(reg, 0, 255).astype(np.uint8))
        sm = im.resize((max(1, im.width // 4), max(1, im.height // 4)), Image.BILINEAR).filter(
            ImageFilter.GaussianBlur(4.5))
        blur = np.asarray(sm.resize(im.size, Image.BILINEAR), np.float32)
        glass = blur * 0.6 + np.array(self.NIGHT, np.float32) * 0.4
        glass = glass * 0.72 + np.array(self.CLOUD, np.float32) * 0.28
        m = Image.new("L", (x1 - x0, y1 - y0), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, x1 - x0 - 1, y1 - y0 - 1], r, fill=255)
        m = np.asarray(m, np.float32)[y0c - y0:y1c - y0, x0c - x0:x1c - x0][..., None] / 255 * strength
        dst[y0c:y1c, x0c:x1c] = reg * (1 - m) + glass * m
        bd = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
        ImageDraw.Draw(bd).rounded_rectangle([0, 0, x1 - x0 - 1, y1 - y0 - 1], r, outline=self.CLOUD + (153,),
                                             width=2)
        blend(dst, bd, x0, y0, alpha=strength)

    @lru_cache(maxsize=16)
    def label_img(self, text):
        ft = font(F_HANKEN, 40, (800,))
        im, bl, adv = text_img(text.upper(), ft, self.CLOUD + (255,), tracking=0.06, pad=6)
        return im

    @lru_cache(maxsize=16)
    def serif_img(self, text, size):
        ft = font(F_SERIF_I, size)
        im, bl, adv = text_img(text, ft, self.CLOUD + (255,), pad=12)
        return K.soft_shadow(im, 12, (0, 4), (5, 10, 25), 0.55, pad=30)

    def glass_card(self, dst, label, word, t0, t1, t, cy, log, name, word_size=180):
        p = (t - t0) / 0.26
        if p < 0 or t >= t1:
            return
        e = ease("expo_out", p)
        op = e
        if t > t1 - 0.14:
            op = min(op, (t1 - t) / 0.14)
        size = word_size
        while size > 90 and alpha_w(self.serif_img(word, size)) > 680:
            size -= 6
        lab = self.label_img(label)
        wd = self.serif_img(word, size)
        lb, wb = K.alpha_box(lab), K.alpha_box(wd)
        cw = max(lb[2] - lb[0], wb[2] - wb[0]) + 80
        chh = (lb[3] - lb[1]) + (wb[3] - wb[1]) + 92
        s = lerp(0.94, 1.0, e)
        cw, chh = cw * s, chh * s
        x0, y0 = 495 - cw / 2, cy - chh / 2
        self.glass(dst, x0, y0, x0 + cw, y0 + chh, strength=op)
        bl = 10 * (1 - e)
        lab_t = transform(lab, scale=s, blur=bl)
        wd_t = transform(wd, scale=s, blur=bl)
        place(dst, lab_t, 495, y0 + 34 * s + (lb[3] - lb[1]) * s / 2, log, name + "-label", alpha=op, thr=200)
        place(dst, wd_t, 495, y0 + chh - 30 * s - (wb[3] - wb[1]) * s / 2 - (wb[1] + wb[3] - wd.height) * s / 2,
              log, name, alpha=op, thr=200)

    def post_base(self, img, t):
        if t < 0.30:  # hook: light leak sweeps over the opening shot (0.00-0.30)
            img = self.leak(img, 0.15 + 0.85 * t / 0.30, 0.8)
        hero = self.edl.get("hero")
        if hero and hero["t"] - 0.04 <= t < hero["t"] + 0.38:  # glass title sweeps in behind a light leak
            img = self.leak(img, (t - hero["t"] + 0.04) / 0.42, 0.7)
        return img

    def draw_hook(self, dst, t, log):
        hk = self.edl["hook"]
        self.glass_card(dst, hk["glass_label"], hk["hero_word"], -0.1, hk["end"], t, 460, log, "hook-card")

    def draw_hero(self, dst, t, log):
        hero = self.edl.get("hero")
        if hero:
            self.glass_card(dst, hero["glass_label"], hero["word"], hero["t"], hero["end"], t, 740, log, "glass-title",
                            word_size=200)

    def star_sprite(self, r, state):
        if state == "slot":
            return star_img(int(r * 0.92), self.CLOUD + (40,), self.CLOUD + (130,), 2)
        if state == "six":
            return star_img(r, self.ORANGE + (255,), self.NIGHT + (90,), 3, glow=self.ORANGE + (200,))
        return star_img(r, self.CLOUD + (255,), self.NIGHT + (90,), 3, glow=(246, 244, 238, 90))

    def draw_star_label(self, dst, text, dt, t, log):
        e = ease("expo_out", dt / 0.26)
        lab = self.label_img(text)
        b = K.alpha_box(lab)
        w, h = b[2] - b[0] + 56, b[3] - b[1] + 30
        self.glass(dst, 495 - w / 2, self.label_cy - h / 2, 495 + w / 2, self.label_cy + h / 2, r=h / 2, strength=e)
        place(dst, transform(lab, blur=10 * (1 - e)), 495, self.label_cy, log, "stars-label", alpha=e, thr=200)

    def draw_credit(self, dst, log):
        cr = self.edl["credit"]
        ft = font(F_HANKEN, 27, (700,))
        im, bl, adv = text_img(cr["text"], ft, self.CLOUD + (240,), stroke=3, stroke_fill=self.NIGHT + (150,))
        im = K.soft_shadow(im, 6, (0, 2), (5, 10, 25), 0.6, pad=12)
        b = K.alpha_box(im, 200)
        blend(dst, im, 132 - b[0], 1546 - b[1])
        log.append(("credit", 132, 1546, 132 + b[2] - b[0], 1546 + b[3] - b[1]))


THEMES = {t.name: t for t in (Classic, CaseFile, PanelHeist, ViceDusk)}


def make(name, edl):
    return THEMES[name](edl)
