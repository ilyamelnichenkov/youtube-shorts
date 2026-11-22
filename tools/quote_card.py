"""Evidence card for the case-file look: a real quote (with its source line) on a paper slip
(same slip, tape and torn edge as the long-form `quotes`) over a blurred, ink-dimmed official screenshot.

Output is a 1080x1350 still (1080x1440 with --height 1440) used as a `window` clip (4:5, or 3:4) in a Short's edl.json, so the engine is not changed.
Keep the slip in the upper part of the card: the word captions cross the window's lower third.

Run with the pipeline venv:
  $SHORTS_HOME/venv/bin/python _tools/quote_card.py \
      OUT.png BG.jpg "quote text (<= 14 words, exact or with ...)" "NAME · ROLE · SOURCE YEAR" \
      [--crop x,y,w,h] [--ang -1.2] [--y 60] [--dim 0.6] [--kicker "QUOTE ON FILE"] [--height 1350]
--height 1440 makes a 3:4 card for the taller "aspect": "3:4" window (900x1200); the default 1350 is the 4:5 card.
"""
import argparse
import os
import sys
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_pipeline"))
import shortkit as K  # noqa: E402

K.set_format("wide")  # wide.py refuses to import otherwise; only its format-free paper/slip helpers are used here
import wide as Wd  # noqa: E402

CW, CH = 1080, 1350


class Card(Wd.WideCaseFile):
    """Only the quote slip of the long-form theme, laid out for a 1080 px wide card."""
    kicker = "QUOTE ON FILE"

    @lru_cache(maxsize=4)
    def quote_layout(self, text, by):
        maxw = 800
        size = 64
        while size > 48:
            if len(Wd.wrap(text, Wd.mono(size, 600), maxw)) <= 5:
                break
            size -= 2
        lines = Wd.wrap(text, Wd.mono(size, 600), maxw)
        lw = max(Wd.mono(size, 600).getlength(l) for l in lines)
        by_w = Wd.mono(34, 700).getlength(by)
        w = int(max(lw, by_w, 600) + 2 * 60)
        h = int(110 + len(lines) * size * 1.22 + 90)
        return size, lines, w, h

    @lru_cache(maxsize=8)
    def quote_img(self, text, by, n, caret, ang):
        size, lines, w, h = self.quote_layout(text, by)
        im = Wd.paper(w, h, 51).copy()
        d = ImageDraw.Draw(im)
        d.text((60, 44), self.kicker, font=Wd.mono(30, 800), fill=Wd.RED + (255,), anchor="lt")
        d.line([(60, 88), (w - 60, 88)], fill=Wd.INK + (60,), width=2)
        ft = Wd.mono(size, 600)
        ink = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        di = ImageDraw.Draw(ink)
        y = 110 + size * 0.95
        for l in lines:
            di.text((60, y), l, font=ft, fill=Wd.INK + (255,), anchor="ls")
            y += size * 1.22
        di.text((60, h - 46), by, font=Wd.mono(34, 700), fill=Wd.INK + (190,), anchor="ls")
        im.alpha_composite(Wd.inked(ink, 17, wear=0.22))
        im = Wd.torn(im, 8, "b", amp=12)
        tp = Wd.tape(190, 50, -4, seed=8)
        out = Image.new("RGBA", (w, h + 30), (0, 0, 0, 0))
        out.alpha_composite(im, (0, 30))
        out.alpha_composite(tp, (int(w / 2 - tp.width / 2), 6))
        return Wd.shadowed(out.rotate(ang, Image.BICUBIC, expand=True), 16, (0, 14), 0.55, pad=40)


def background(path, crop, dim):
    src = Image.open(path).convert("RGB")
    if crop:
        x, y, w, h = crop
    else:  # centred 4:5 crop
        w = min(src.width, int(src.height * CW / CH))
        h = int(w * CH / CW)
        x, y = (src.width - w) // 2, (src.height - h) // 2
    bg = src.crop((x, y, x + w, y + h)).resize((CW, CH), Image.LANCZOS).filter(ImageFilter.GaussianBlur(9))
    f = np.asarray(bg, np.float32)
    f = f * (1 - dim) + np.array(Wd.INK, np.float32) * dim
    return Image.fromarray(np.clip(f, 0, 255).astype(np.uint8)).convert("RGBA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("bg")
    ap.add_argument("text")
    ap.add_argument("by")
    ap.add_argument("--crop", type=lambda s: tuple(int(v) for v in s.split(",")))
    ap.add_argument("--ang", type=float, default=-1.2)
    ap.add_argument("--y", type=int, default=60, help="top of the slip on the 1350 px card")
    ap.add_argument("--dim", type=float, default=0.6)
    ap.add_argument("--kicker", default="QUOTE ON FILE")
    ap.add_argument("--height", type=int, default=1350)
    a = ap.parse_args()
    global CH
    CH = a.height
    if len(a.text.split()) > 14:
        sys.exit(f"quote has {len(a.text.split())} words; keep it to 14 or fewer")
    card = object.__new__(Card)
    card.kicker = a.kicker
    slip = card.quote_img(a.text, a.by, len(a.text), False, a.ang)
    if slip.width > CW:
        sys.exit(f"slip is {slip.width} px wide, wider than the card")
    im = background(a.bg, a.crop, a.dim)
    im.alpha_composite(slip, ((CW - slip.width) // 2, a.y))
    im.convert("RGB").save(a.out, quality=95)
    print(f"{a.out}: slip {slip.width}x{slip.height} at y {a.y}..{a.y + slip.height}")


if __name__ == "__main__":
    main()
