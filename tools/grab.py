#!/usr/bin/env python3
"""Download one short section of a player's clip (video only, best <= 2160p) and log it in _footage/SOURCES.md.

  _tools/grab.py <topic> <url> <start> <end> [--tag NAME] [--max-height 2160]
start/end: seconds or m:ss. Output: _footage/<topic>/<tag>-<start>-<end>.<ext> next to the other clips.
Only for clips the channel's footage policy allows (see CHANNEL.md); each file is logged with
creator, title, url and the date, so credits can go in the description.
"""
import argparse, json, subprocess, sys, re
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
YT = HERE / "ytdl.sh"


def secs(s):
    p = [float(x) for x in s.split(":")]
    return p[-1] + (60 * p[-2] if len(p) > 1 else 0) + (3600 * p[-3] if len(p) > 2 else 0)  # "34", "1:05" or "1:02:03"


def safe(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:40]


ap = argparse.ArgumentParser()
ap.add_argument("topic"); ap.add_argument("url"); ap.add_argument("start"); ap.add_argument("end")
ap.add_argument("--tag"); ap.add_argument("--max-height", type=int, default=2160)
a = ap.parse_args()
meta = json.loads(subprocess.run([str(YT), "--skip-download", "--dump-json", "--no-warnings", a.url], capture_output=True, text=True, check=True).stdout)
tag = a.tag or safe(meta.get("channel") or meta.get("uploader") or "clip")
s, e = secs(a.start), secs(a.end)
out = ROOT / "_footage" / a.topic
out.mkdir(parents=True, exist_ok=True)
stem = f"{tag}-{meta['id']}-{int(s)}-{int(e)}"
fmt = f"bv*[height<={a.max_height}]"  # highest resolution wins (-S res,fps): an explicit codec filter once picked a 360p stream
subprocess.run([str(YT), "--no-warnings", "-f", fmt, "-S", "res,fps", "--download-sections", f"*{s}-{e}", "--force-keyframes-at-cuts",
                "-o", str(out / (stem + ".%(ext)s")), a.url], check=True)
files = sorted(out.glob(stem + ".*"))
if not files:
    sys.exit("nothing downloaded")
f = files[0]
pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,r_frame_rate:format=duration", "-of", "csv=p=0", str(f)], capture_output=True, text=True).stdout.split()
log = ROOT / "_footage" / "SOURCES.md"
if not log.exists():
    log.write_text("# Footage sources\n\nEach line: file | creator | title | url | section | what we got | date.\n\n")
with log.open("a") as fh:
    fh.write(f"- `{a.topic}/{f.name}` | {meta.get('channel')} | {meta.get('title')} | {a.url} | {a.start}-{a.end} | {' '.join(pr)} | {date.today()}\n")
print(f.name, " ".join(pr), f"{f.stat().st_size/1e6:.1f} MB")
