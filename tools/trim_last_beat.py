"""Remove the last beat (the closing question) from <short>/vo without re-rendering the voice: cut vo.wav 0.25 s after
the end of the previous beat (0.2 s fade), drop the beat from beats.json and timings.json, drop its words from words.json.
Run: _tools/trim_last_beat.py <short>/vo [backup_dir]   (the originals are copied to backup_dir first)"""
import json, shutil, subprocess, sys
from pathlib import Path
vo = Path(sys.argv[1]); bk = Path(sys.argv[2]) if len(sys.argv) > 2 else None
if bk:
    bk.mkdir(parents=True, exist_ok=True)
    for f in ("vo.wav", "timings.json", "words.json", "beats.json"):
        shutil.copy2(vo / f, bk / f)
t = json.loads((vo / "timings.json").read_text())
last, prev = t["beats"][-1], t["beats"][-2]
cut = round(prev["end"] + 0.25, 3)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(vo / "vo.wav"), "-t", str(cut), "-af", f"afade=t=out:st={cut-0.2}:d=0.2",
                str(vo / "vo.tmp.wav")], check=True)
(vo / "vo.tmp.wav").replace(vo / "vo.wav")
t["beats"] = t["beats"][:-1]; t["duration"] = cut
(vo / "timings.json").write_text(json.dumps(t, indent=2))
w = json.loads((vo / "words.json").read_text())
w = [x for x in w if x["s"] < last["start"] - 0.05]
(vo / "words.json").write_text(json.dumps(w, indent=1))
b = json.loads((vo / "beats.json").read_text())
b["beats"] = b["beats"][:-1]; b["beats"][-1][2] = 0.0
(vo / "beats.json").write_text(json.dumps(b, indent=1))
print(vo, "removed", last["id"], "new duration", cut, "words", len(w), "last word", w[-1]["w"], w[-1]["e"])
