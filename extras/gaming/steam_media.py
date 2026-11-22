#!/usr/bin/env python3
"""Optional (gaming channels): official Steam store media (trailers, screenshots) for the Shorts; logs to the project's _footage/SOURCES.md.

  steam_media.py list <appid> [<appid> ...]
      prints the store name, every trailer (index, name, top resolution) and the screenshot count
  steam_media.py get <appid> <outdir> [--movies 0,2|all] [--shots] [--tag NAME]
      downloads the chosen trailers (largest HLS variant, video only, stream copy) and/or all
      screenshots (path_full) into <outdir>, and appends one line per file to _footage/SOURCES.md

HTTP goes through curl because Python's urllib fails certificate checks on this machine.
"""
import fcntl
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

SOURCES = Path(__file__).resolve().parent.parent / "_footage" / "SOURCES.md"


def fetch(url):
    return subprocess.run(["curl", "-sL", "--fail", url], check=True, capture_output=True).stdout


def details(appid):
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=english"
    d = json.loads(fetch(url))[str(appid)]
    if not d.get("success"):
        raise SystemExit(f"appid {appid}: store API returned no data")
    return d["data"]


def best_variant(master_url):
    text = fetch(master_url).decode()
    best, best_px, res = None, -1, None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
        if line.startswith("#EXT-X-STREAM-INF") and m and i + 1 < len(lines):
            px = int(m.group(1)) * int(m.group(2))
            if px > best_px:
                best_px, best, res = px, urljoin(master_url, lines[i + 1].strip()), f"{m.group(1)}x{m.group(2)}"
    if best is None:
        raise SystemExit(f"no video variant in {master_url}")
    return best, res


def log(rows):
    if not SOURCES.exists():
        SOURCES.write_text("# Footage sources (evolution Shorts)\n\n")
    with SOURCES.open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)  # five downloads run in parallel and share this log
        f.write(f"\n## Downloaded {date.today().isoformat()}\n\n| File | App id | Steam title | URL | Resolution | Size |\n|---|---|---|---|---|---|\n")
        for r in rows:
            f.write("| " + " | ".join(r) + " |\n")


def safe(name):
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")[:60]


def cmd_list(appids):
    for a in appids:
        d = details(a)
        movies = d.get("movies", [])
        print(f"== {a} {d['name']} ({d.get('release_date', {}).get('date', '?')}): "
              f"{len(movies)} trailers, {len(d.get('screenshots', []))} screenshots")
        for i, m in enumerate(movies):
            print(f"  [{i}] {m['name']}  hls={'yes' if m.get('hls_h264') else 'no'}")


def cmd_get(appid, outdir, movies_arg, shots, tag):
    d = details(appid)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    movies = d.get("movies", [])
    if movies_arg:
        idx = range(len(movies)) if movies_arg == "all" else [int(x) for x in movies_arg.split(",")]
        for i in idx:
            m = movies[i]
            if not m.get("hls_h264"):
                print(f"skip [{i}] {m['name']}: no HLS")
                continue
            url, res = best_variant(m["hls_h264"])
            dst = out / f"{safe(m['name'])}.mp4"
            if not dst.exists():
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", url, "-c", "copy", "-an", str(dst)], check=True)
            mb = dst.stat().st_size / 1e6
            print(f"ok [{i}] {dst} {res} {mb:.0f} MB")
            rows.append([str(dst.resolve().relative_to(SOURCES.parent)), str(appid), m["name"], m["hls_h264"], res, f"{mb:.0f} MB"])
    if shots:
        for n, s in enumerate(d.get("screenshots", []), 1):
            dst = out / f"{(tag + '-') if tag else ''}ss{n:02d}.jpg"
            if not dst.exists():
                dst.write_bytes(fetch(s["path_full"]))
            rows.append([str(dst.resolve().relative_to(SOURCES.parent)), str(appid), d["name"] + " screenshot", s["path_full"], "", f"{dst.stat().st_size // 1000} KB"])
        print(f"ok {len(d.get('screenshots', []))} screenshots -> {out}")
    if rows:
        log(rows)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] not in ("list", "get"):
        raise SystemExit(__doc__)
    if a[0] == "list":
        cmd_list(a[1:])
    else:
        movies_arg = a[a.index("--movies") + 1] if "--movies" in a else None
        tag = a[a.index("--tag") + 1] if "--tag" in a else ""
        cmd_get(a[1], a[2], movies_arg, "--shots" in a, tag)
