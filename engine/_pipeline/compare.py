#!/usr/bin/env python3
"""Side-by-side review material for several theme renders of one Short.

    python3 _pipeline/compare.py <short>/edl.json case-file panel-heist vice-dusk

Writes into the Short's folder: compare-3up.mp4 (themes side by side, 640x1138 each, names under them, voice-over once),
compare-sheet.jpg (the same moments for every theme), board-<theme>.png (cover, four frames, font specimen,
palette, hero device) and board-all.png (the boards stacked). Needs the renders (build.py) and covers (--cover).
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

import subprocess

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shortkit as K  # noqa: E402
import themes as T  # noqa: E402

MOMENTS = [0.0, 0.9, 2.3, 7.8, 10.4, 13.8, 19.7, 21.5]
BOARD_FRAMES = [(0.3, "hook"), (10.4, "full-bleed clip + captions"), (7.8, "window clip on its background"),
                (19.7, "stars hero moment")]
PACK = {"case-file": "Pack B · Case File", "panel-heist": "Pack A · Panel Heist", "vice-dusk": "Pack C · Vice Dusk",
        "classic": "Classic (pilot v1)"}
BOARD_BG = {"case-file": (226, 220, 204), "panel-heist": (244, 239, 227), "vice-dusk": (12, 20, 38),
            "classic": (20, 20, 24)}
LABEL = K.OLD_FONTS + "/Inter-var.woff2"


def frame_at(video, t, size=None):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    im = Image.frombytes("RGB", (K.W, K.H), raw)
    return im.resize(size, Image.LANCZOS) if size else im


def label_font(size, wght=700):
    return K.font(LABEL, size, (wght,))


def three_up(edl, names, out):
    vids = [K.out_path(edl, "out_silent", n) for n in names]
    gap, tw, th = 15, 640, 1138
    cw, ch = gap + len(names) * (tw + gap), th + 110
    lab = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(lab)
    for i, n in enumerate(names):
        d.text((gap + i * (tw + gap) + tw / 2, th + 20 + 45), n, font=label_font(46, 800), fill=(240, 240, 240, 255),
               anchor="mm")
    lp = out + ".labels.png"
    lab.save(lp)
    dur = K.wav_duration(K.rel(edl, edl["vo"])) + edl.get("tail", 0.6)
    fc = [f"color=c=0x101014:s={cw}x{ch}:r=30:d={dur:.3f}[bg]"]
    prev = "bg"
    for i in range(len(names)):
        fc.append(f"[{i}:v]scale={tw}:{th}:flags=lanczos[s{i}]")
        fc.append(f"[{prev}][s{i}]overlay={gap + i * (tw + gap)}:20[o{i}]")
        prev = f"o{i}"
    fc.append(f"[{prev}][{len(names)}:v]overlay=0:0,format=yuv420p[v]")
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for v in vids:
        cmd += ["-i", v]
    cmd += ["-i", lp, "-i", K.rel(edl, edl["vo"]), "-filter_complex", ";".join(fc), "-map", "[v]", "-map",
            f"{len(names) + 1}:a", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
            "-af", "apad", "-t", f"{dur:.3f}", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    os.remove(lp)


def sheet(edl, names, out):
    tw, th, lw, hh = 270, 480, 230, 50
    S = Image.new("RGB", (lw + len(MOMENTS) * tw, hh + len(names) * (th + 10)), (16, 16, 20))
    d = ImageDraw.Draw(S)
    for j, t in enumerate(MOMENTS):
        d.text((lw + j * tw + tw / 2, hh / 2), f"{t:.1f} s", font=label_font(28), fill=(255, 225, 26), anchor="mm")
    for i, n in enumerate(names):
        v = K.out_path(edl, "out_silent", n)
        y = hh + i * (th + 10)
        d.text((lw / 2, y + th / 2), n, font=label_font(32, 800), fill=(235, 235, 235), anchor="mm")
        for j, t in enumerate(MOMENTS):
            S.paste(frame_at(v, min(t, 22.3), (tw, th)), (lw + j * tw, y))
    S.save(out, quality=90)


def board(edl, name, out):
    th = T.make(name, edl)
    bgc = BOARD_BG[name]
    ink = (12, 12, 16) if sum(bgc) > 400 else (240, 240, 236)
    sub = tuple(int(c * 0.55 + (128 if sum(bgc) < 400 else 0) * 0.45) for c in ink)
    m, gw, gh, gap = 70, 540, 960, 30
    wdt = 2 * m + 5 * gw + 4 * gap
    hgt = 1960
    B = Image.new("RGB", (wdt, hgt), bgc)
    d = ImageDraw.Draw(B)
    d.text((m, 60), f"{name}", font=label_font(64, 900), fill=ink, anchor="lt")
    d.text((m + 20 + label_font(64, 900).getlength(name), 82), PACK.get(name, ""), font=label_font(34, 600), fill=sub,
           anchor="lt")
    y0 = 170
    cover = Image.open(K.rel(edl, f"cover-{name}.jpg")).convert("RGB").resize((gw, gh), Image.LANCZOS)
    tiles = [(cover, "cover (1080x1920)")]
    v = K.out_path(edl, "out_silent", name)
    tiles += [(frame_at(v, t, (gw, gh)), f"{t:.1f} s · {lab}") for t, lab in BOARD_FRAMES]
    for k, (im, lab) in enumerate(tiles):
        x = m + k * (gw + gap)
        B.paste(im, (x, y0))
        d.text((x, y0 + gh + 16), lab, font=label_font(28, 600), fill=ink, anchor="lt")
    y = y0 + gh + 90
    d.text((m, y), "Fonts", font=label_font(34, 800), fill=ink, anchor="lt")
    y += 56
    for role, fname, path, axes, sample in th.FONTS:
        d.text((m, y + 8), f"{role} · {fname}", font=label_font(26, 600), fill=sub, anchor="lt")
        size = 76
        while size > 40 and K.font(path, size, axes).getlength(sample) > 1640:
            size -= 4
        d.text((m + 520, y), sample, font=K.font(path, size, axes), fill=ink, anchor="lt")
        y += 110
    px = wdt - m - 560
    py = y0 + gh + 90
    d.text((px, py), "Palette", font=label_font(34, 800), fill=ink, anchor="lt")
    py += 56
    for k, (pn, hx) in enumerate(th.PALETTE):
        col = K.rgba(hx)[:3]
        yy = py + k * 74
        d.rectangle([px, yy, px + 110, yy + 58], fill=col, outline=ink, width=2)
        d.text((px + 130, yy + 29), f"{pn}  {hx}", font=label_font(28, 600), fill=ink, anchor="lm")
    yh = max(y, py + len(th.PALETTE) * 74) + 30
    d.text((m, yh), th.HERO, font=label_font(32, 700), fill=ink, anchor="lt")
    B = B.crop((0, 0, wdt, yh + 90))
    B.save(out)
    return B


def main():
    edl = K.load_edl(sys.argv[1])
    names = sys.argv[2:] or ["case-file", "panel-heist", "vice-dusk"]
    folder = edl["_dir"]
    three_up(edl, names, os.path.join(folder, "compare-3up.mp4"))
    sheet(edl, names, os.path.join(folder, "compare-sheet.jpg"))
    boards = [board(edl, n, os.path.join(folder, f"board-{n}.png")) for n in names]
    w = max(b.width for b in boards)
    allb = Image.new("RGB", (w, sum(b.height for b in boards) + 40 * (len(boards) - 1)), (40, 40, 44))
    y = 0
    for b in boards:
        allb.paste(b, (0, y))
        y += b.height + 40
    allb.save(os.path.join(folder, "board-all.png"))
    print("written:", ", ".join(["compare-3up.mp4", "compare-sheet.jpg"] + [f"board-{n}.png" for n in names] +
                                ["board-all.png"]))


if __name__ == "__main__":
    main()
