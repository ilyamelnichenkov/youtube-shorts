"""Vertical covers (1080x1920) built from an official footage frame with a theme applied.

EDL block (all coordinates in source pixels unless noted):
  "cover": {"src": "_footage/topic/clip.mp4", "t": 0.35, "cw": 1215, "cx": 1300, "cy": 1080,
            "headline": ["COPS HUNT", "YOUR OUTFIT?!"], "game": "TOPIC NAME" (the big stamp), "label": "TOPIC / SUBJECT", "file": "FILE 01",
            "word": "outfit?", "lead": "COPS HUNT YOUR", "circle": [cx, cy, rx, ry]   # screen px, Case File only
  }
All text is kept inside x 130-950 / y 300-1580 (x <= 860 for y 1000-1600); the function returns the text boxes.
"""
import math
import subprocess

import numpy as np
from PIL import Image, ImageDraw

import shortkit as K
import themes as T
from shortkit import W, H, font, blend, place, transform


def source_frame(edl, cov):
    path = K.footage(edl, cov["src"])
    info = K.probe(path)
    pic = edl.get("sources", {}).get(cov["src"], {}).get("picture") or [0, 0, info["w"], info["h"]]
    cw = cov["cw"]
    ch = cw * H / W
    # Covers are seen as small feed thumbnails, so a 1080p trailer may be upscaled up to 2x when the edit list opts
    # in with "upscale": true (Steam trailers have no 4K). The video itself keeps check.py's pixel policy.
    min_cw = W / 2 if cov.get("upscale") else W
    if cw < min_cw - 0.5 or ch > pic[3] + 0.5:
        raise ValueError(f"cover crop must be >= {min_cw:.0f} source px wide and fit the picture height"
                         + ("" if cov.get("upscale") else " (no upscaling unless \"upscale\": true)"))
    x0 = K.clamp(cov["cx"] - cw / 2, pic[0], pic[0] + pic[2] - cw)
    y0 = K.clamp(cov["cy"] - ch / 2, pic[1], pic[1] + pic[3] - ch)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{cov['t']:.3f}", "-i", path, "-frames:v", "1", "-f",
                          "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    im = Image.frombytes("RGB", (info["w"], info["h"]), raw)
    return np.asarray(im.resize((W, H), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch)))


def make_cover(edl, theme):
    cov = edl["cover"]
    base = theme.grade(source_frame(edl, cov), 0)
    dst = base.astype(np.float32)
    log = []
    {"case-file": case_cover, "panel-heist": panel_cover, "vice-dusk": vice_cover, "classic": classic_cover}[
        theme.name](dst, theme, cov, log)
    viol = [(n, b) for n, *b in log if K.zone_violations(b)]
    return Image.fromarray(np.clip(dst, 0, 255).astype(np.uint8)), log, viol


def fit_size(path, axes, lines, maxw, start, stop=40):
    size = start
    while size > stop and max(font(path, size, axes).getlength(l) for l in lines) > maxw:
        size -= 2
    return size


# ---------------------------------------------------------------------------------------------- Case File
def case_cover(dst, th, cov, log):
    # ink border strip around the image
    dst[:18], dst[-18:], dst[:, :18], dst[:, -18:] = th.INK, th.INK, th.INK, th.INK
    cx, cy, rx, ry = cov["circle"]
    th.red_circle(dst, cx, cy, rx, ry, 1.0, seed=3, width=13)
    # file tab: mono file number + Big Shoulders headline
    lines = cov["headline"]
    size = fit_size(T.F_BIGSH, (900,), lines, 730 - 70, 190)
    ft = font(T.F_BIGSH, size, (900,))
    ftl = font(T.F_JBM, 44, (800,))
    lw = max(ft.getlength(l) for l in lines)
    w = int(min(730, max(lw, ftl.getlength(cov["file"] + " / " + cov["label"])) + 70))
    h = int(40 + 60 + size * 0.9 * len(lines) + 20)
    plate = np.zeros((h, w, 4), np.float32)
    plate[..., :3] = th.BONE
    plate[..., :3] += np.random.default_rng(5).normal(0, 6, (h, w))[..., None]
    plate[..., 3] = 255
    plate[:, :8, :3] = th.RED
    im = Image.fromarray(np.clip(plate, 0, 255).astype(np.uint8), "RGBA")
    d = ImageDraw.Draw(im)
    d.text((34, 30), cov["file"], font=ftl, fill=th.RED + (255,), anchor="lt")
    d.text((34 + ftl.getlength(cov["file"]), 30), " / " + cov["label"], font=ftl, fill=th.INK + (255,), anchor="lt")
    y = 92
    for l in lines:
        d.text((34, y), l, font=ft, fill=th.INK + (255,), anchor="lt")
        y += size * 0.9
    im = K.soft_shadow(im, 12, (0, 10), (0, 0, 0), 0.55, pad=30)
    ty = cov.get("tab_y", 330)
    blend(dst, im, 130 - 30, ty - 30)
    log.append(("cover-tab", 130, ty, 130 + w, ty + h))
    # big red stamp: the topic name (cov["game"])
    st = font(T.F_BIGSH, cov.get("game_size", 200), (900,))  # smaller for long names (CALL OF DUTY)
    t_im, bl, adv = K.text_img(cov["game"], st, th.RED + (255,), tracking=0.06, pad=30)
    b = K.alpha_box(t_im)
    s = Image.new("RGBA", (b[2] - b[0] + 80, b[3] - b[1] + 60), (0, 0, 0, 0))
    s.alpha_composite(t_im.crop(b), (40, 30))
    ImageDraw.Draw(s).rectangle([5, 5, s.width - 6, s.height - 6], outline=th.RED + (255,), width=12)
    s = s.rotate(6, Image.BICUBIC, expand=True)
    place(dst, s, 470, cov.get("stamp_y", 1390), log, "cover-stamp", alpha=0.95)


# ---------------------------------------------------------------------------------------------- Panel Heist
def panel_cover(dst, th, cov, log):
    g = 26
    dst[:g + 6], dst[-g - 6:], dst[:, :g + 6], dst[:, -g - 6:] = th.INK, th.INK, th.INK, th.INK
    dst[:g], dst[-g:], dst[:, :g], dst[:, -g:] = 255, 255, 255, 255
    plate = th.plate(tuple(cov.get("headline_wide", cov["headline"])), maxsize=130, minsize=60, box_w=650)
    plate = transform(plate, rot=-3)
    place(dst, plate, 495, cov.get("plate_y", 520), log, "cover-plate", thr=200)
    # yellow number circle: last word of cov["game"] big, the words before it small
    r = 165
    im = Image.new("RGBA", (2 * r + 40, 2 * r + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([18, 18, 18 + 2 * r, 18 + 2 * r], fill=th.INK + (255,))
    d.ellipse([6, 6, 6 + 2 * r, 6 + 2 * r], fill=th.YEL + (255,), outline=th.INK + (255,), width=9)
    top = " ".join(cov["game"].split()[:-1])  # e.g. "ACME" of "ACME 6"
    if top:
        d.text((6 + r, 6 + r - 70), top, font=font(T.F_BOWLBY, 70), fill=th.INK + (255,), anchor="mm")
    d.text((6 + r, 6 + r + 45), cov["game"].split()[-1], font=font(T.F_BOWLBY, 190), fill=th.INK + (255,),
           anchor="mm")
    place(dst, transform(im, rot=-6), 650, cov.get("badge_y", 1340), log, "cover-badge", thr=200)


# ---------------------------------------------------------------------------------------------- Vice Dusk
def vice_cover(dst, th, cov, log):
    lk = th.leak(np.clip(dst, 0, 255).astype(np.uint8), 0.22, 0.85).astype(np.float32)
    dst[:] = lk
    # topic name in a glass pill at the top
    ft = font(T.F_HANKEN, 120, (800,))
    gim, bl, adv = K.text_img(cov["game"], ft, th.CLOUD + (255,), tracking=0.04, pad=10)
    b = K.alpha_box(gim)
    pw, ph = b[2] - b[0] + 110, b[3] - b[1] + 70
    gy = cov.get("game_y", 420)
    th.glass(dst, 495 - pw / 2, gy - ph / 2, 495 + pw / 2, gy + ph / 2, r=ph / 2)
    place(dst, gim, 495, gy, log, "cover-game", thr=200)
    # huge serif italic word with a small Hanken lead line on a glass card
    lead = th.label_img(cov["lead"])
    size = 300
    while size > 120 and T.alpha_w(th.serif_img(cov["word"], size)) > 690:
        size -= 10
    word = th.serif_img(cov["word"], size)
    lb, wb = K.alpha_box(lead), K.alpha_box(word)
    cw = max(lb[2] - lb[0], wb[2] - wb[0]) + 70
    chh = (lb[3] - lb[1]) + (wb[3] - wb[1]) + 100
    y0 = 1370 - chh / 2
    th.glass(dst, 495 - cw / 2, y0, 495 + cw / 2, y0 + chh)
    place(dst, lead, 495, y0 + 36 + (lb[3] - lb[1]) / 2, log, "cover-lead", thr=200)
    place(dst, word, 495, y0 + chh - 34 - (wb[3] - wb[1]) / 2 - (wb[1] + wb[3] - word.height) / 2, log, "cover-word",
          thr=200)


# ---------------------------------------------------------------------------------------------- classic
def classic_cover(dst, th, cov, log):
    im = th.headline(150)
    place(dst, im, 540, 520, log, "cover-headline")
