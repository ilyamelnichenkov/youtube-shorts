#!/usr/bin/env python3
"""Tone-map an HDR10 (PQ / BT.2020) player capture to an SDR BT.709 copy that the Shorts engine can read.

The engine decodes with ffmpeg to rgb24 and never tone-maps, so an HDR source comes out dark, flat and grey.
This script builds a 3D LUT (PQ BT.2020 -> sRGB BT.709, luminance-driven shoulder, hue-keeping) and applies it
with ffmpeg's lut3d (no zscale/libplacebo needed). Frame count and frame times stay identical to the source, so the
`in` times of an edit list are the original clip times. Everything before --from is replaced by black frames (the
unused part, e.g. map screens), which keeps the timeline aligned without spending render time on it.

  _tools/hdr_to_sdr.py <src.mp4> <dst.mp4> [--from SECONDS] [--crf 18] [--white 203] [--lw 2.4]
Needs numpy (any venv) and ffmpeg. The derived file is logged in _footage/SOURCES.md by hand.
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

import numpy as np

N = 65  # LUT grid


def pq2nits(e):
    m1, m2 = 2610 / 16384, 2523 / 4096 * 128
    c1, c2, c3 = 3424 / 4096, 2413 / 4096 * 32, 2392 / 4096 * 32
    ep = np.power(np.clip(e, 0, 1), 1 / m2)
    return 10000 * np.power(np.maximum(ep - c1, 0) / (c2 - c3 * ep), 1 / m1)


def srgb_oetf(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def write_cube(path, white, lw):
    m = np.array([[1.6605, -0.5876, -0.0728], [-0.1246, 1.1329, -0.0083], [-0.0182, -0.1006, 1.1187]])  # 2020 -> 709
    luma = np.array([0.2126, 0.7152, 0.0722])
    g = np.linspace(0, 1, N)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")  # red varies fastest, as .cube expects
    rgb = np.stack([r, gg, b], -1).reshape(-1, 3)
    lin = np.maximum((pq2nits(rgb) / white) @ m.T, 0)
    y = lin @ luma
    yt = y * (1 + y / lw ** 2) / (1 + y)  # extended Reinhard on luminance
    out = lin * np.where(y > 1e-6, yt / np.maximum(y, 1e-6), 1.0)[:, None]
    over = np.clip(out.max(1, keepdims=True), 1, None)  # channels above 1: scale down, highlights desaturate
    k = np.clip(over - 1, 0, 1)
    out = np.clip(out * (1 - k) + k * out / over, 0, 1)
    code = srgb_oetf(out)
    with open(path, "w") as fh:
        fh.write(f'TITLE "pq2020_to_sdr709"\nLUT_3D_SIZE {N}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n')
        fh.writelines(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n" for v in code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--from", dest="start", type=float, default=0.0)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--white", type=float, default=203.0)
    ap.add_argument("--lw", type=float, default=2.4)
    a = ap.parse_args()
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                         "-of", "csv=p=0", a.src], capture_output=True, text=True, check=True).stdout.strip().split(",")
    w, h, rate = int(pr[0]), int(pr[1]), pr[2]
    n, d = (int(v) for v in rate.split("/"))
    first = int(round(a.start * n / d))  # first frame kept; everything before it becomes black
    with tempfile.TemporaryDirectory() as tmp:
        cube = Path(tmp) / "pq.cube"
        write_cube(cube, a.white, a.lw)
        conv = ("scale=in_color_matrix=bt2020:in_range=tv:out_range=pc:flags=accurate_rnd+full_chroma_int,format=gbrp16le,"
                f"lut3d=file={cube}:interp=tetrahedral,"
                "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p")
        graph = f"[0:v]trim=start_frame={first},setpts=PTS-STARTPTS,{conv}[v1];"
        if first:
            graph += (f"color=c=black:s={w}x{h}:r={rate},trim=end_frame={first},setpts=PTS-STARTPTS,format=yuv420p[v0];"
                      "[v0][v1]concat=n=2:v=1:a=0[v]")
        else:
            graph = f"[0:v]{conv}[v]"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.src, "-an", "-filter_complex", graph, "-map", "[v]",
                        "-c:v", "libx264", "-preset", "fast", "-crf", str(a.crf), "-x264-params", "keyint=30",
                        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
                        "-movflags", "+faststart", a.dst], check=True)


if __name__ == "__main__":
    main()
