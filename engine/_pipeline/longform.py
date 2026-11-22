#!/usr/bin/env python3
"""Long-form (16:9) videos as a manifest of segments, each built on its own and joined without re-encoding.

    python3 _pipeline/longform.py build <long>/longform.json [--only seg-01,seg-03] [--force] [--jobs 3]
    python3 _pipeline/longform.py join  <long>/longform.json
    python3 _pipeline/longform.py status <long>/longform.json

Manifest:
  {"title": ..., "segments": [{"id": "seg-00", "edl": "seg-00-cold-open/edl.json"}, ...],
   "out": "out/master-silent.mp4", "cues_out": "out/sfx-cues.json", "vo_out": "out/master-vo.wav",
   "preview_out": "out/master-vo-preview.mp4"}
Every segment edit list says "format": "wide" (see wide.py). build renders only the segments whose silent mp4 is
missing or older than their edit list, voice-over or the pipeline code (or those named with --only / all with
--force), each in its own build.py process. join checks that all segments share one H.264 parameter set, joins them
with the concat demuxer (-c copy), and writes next to the master: <master>.overlay.json (all frames, plus segment
boundaries), the cue list with absolute times (each cue gets "segment"), the voice-overs laid end to end on the
master's timeline (for the sound stage) and a rough preview mp4 with that voice-over (not the mix).
"""
import os
import sys

VENV_PY = os.environ.get("SHORTS_PY") or os.path.join(os.environ.get("SHORTS_HOME") or os.path.expanduser("~/.shorts-studio"), "venv", "bin", "python")
try:
    import numpy  # noqa: F401
except ImportError:
    if not os.environ.get("_SHORTS_REEXEC") and os.path.exists(VENV_PY):
        os.environ["_SHORTS_REEXEC"] = "1"
        os.execv(VENV_PY, [VENV_PY] + sys.argv)
    raise SystemExit("numpy and Pillow are missing: run scripts/setup.sh once (it creates $SHORTS_HOME/venv) or set SHORTS_PY=<python with numpy+Pillow>")

import json
import subprocess
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
CODE = [os.path.join(HERE, f) for f in ("build.py", "shortkit.py", "themes.py", "wide.py")]


def load(path):
    with open(path) as fh:
        man = json.load(fh)
    man["_root"] = os.path.dirname(os.path.abspath(path))
    segs = []
    for sg in man["segments"]:
        ep = os.path.join(man["_root"], sg["edl"])
        with open(ep) as fh:
            edl = json.load(fh)
        if edl.get("format") != "wide":
            raise SystemExit(f"{sg['id']}: edit list must say \"format\": \"wide\"")
        d = os.path.dirname(ep)
        segs.append(dict(sg, edl_path=ep, dir=d, edl=edl,
                         silent=os.path.join(d, edl["out_silent"]),
                         cues=os.path.join(d, edl["sfx_out"]),
                         vo=os.path.join(d, edl["vo"]) if edl.get("vo") else None))
    return man, segs


def out(man, key, default):
    return os.path.join(man["_root"], man.get(key, default))


def stale(sg):
    if not os.path.exists(sg["silent"]) or not os.path.exists(sg["silent"] + ".overlay.json"):
        return "not built"
    t = os.path.getmtime(sg["silent"])
    deps = [sg["edl_path"]] + ([sg["vo"]] if sg["vo"] else []) + CODE
    newer = [os.path.basename(p) for p in deps if os.path.getmtime(p) > t]
    return f"older than {', '.join(newer)}" if newer else None


def cmd_status(man, segs):
    for sg in segs:
        print(f"{sg['id']:8} {stale(sg) or 'up to date'}  {os.path.relpath(sg['silent'], man['_root'])}")


def cmd_build(man, segs, args):
    only = set(args[args.index("--only") + 1].split(",")) if "--only" in args else None
    jobs = int(args[args.index("--jobs") + 1]) if "--jobs" in args else 1
    todo = []
    for sg in segs:
        why = "forced" if "--force" in args else ("asked" if only and sg["id"] in only else stale(sg))
        if only and sg["id"] not in only:
            why = None
        print(f"{sg['id']:8} {'build: ' + why if why else 'skip (up to date)'}")
        if why:
            todo.append(sg)
    running, t0 = [], time.time()
    while todo or running:
        while todo and len(running) < jobs:
            sg = todo.pop(0)
            log = open(os.path.join(sg["dir"], "build.log"), "w")
            p = subprocess.Popen([sys.executable, os.path.join(HERE, "build.py"), sg["edl_path"]], stdout=log,
                                 stderr=subprocess.STDOUT)
            running.append((sg, p, log, time.time()))
        for item in list(running):
            sg, p, log, ts = item
            if p.poll() is not None:
                log.close()
                running.remove(item)
                if p.returncode != 0:
                    raise SystemExit(f"{sg['id']} failed, see {os.path.join(sg['dir'], 'build.log')}")
                print(f"{sg['id']:8} built in {time.time() - ts:.0f}s")
        time.sleep(0.5)
    print(f"build done in {time.time() - t0:.0f}s")


def param_sets(path):
    """SPS and PPS NAL units of the first access unit (Annex B)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-c:v", "copy", "-bsf:v", "h264_mp4toannexb",
                          "-frames:v", "1", "-f", "h264", "-"], capture_output=True, check=True).stdout
    nals, i = [], 0
    starts = []
    while True:
        j = raw.find(b"\x00\x00\x01", i)
        if j < 0:
            break
        starts.append(j + 3)
        i = j + 3
    for k, s in enumerate(starts):
        e = starts[k + 1] - 3 if k + 1 < len(starts) else len(raw)
        nal = raw[s:e].rstrip(b"\x00")
        if nal and nal[0] & 0x1F in (7, 8):
            nals.append(nal)
    return nals


def frame_count(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                          "stream=nb_read_packets", "-of", "csv=p=0", path], capture_output=True, text=True,
                         check=True).stdout
    return int(out.strip())


def cmd_join(man, segs):
    for sg in segs:
        why = stale(sg)
        if why == "not built":
            raise SystemExit(f"{sg['id']} is not built: python3 _pipeline/longform.py build ...")
        if why:
            print(f"WARNING {sg['id']} is {why}; joining the existing render")
    ref = param_sets(segs[0]["silent"])
    for sg in segs[1:]:
        if param_sets(sg["silent"]) != ref:
            raise SystemExit(f"{sg['id']}: H.264 parameter sets differ from {segs[0]['id']}; rebuild it with the "
                             f"current pipeline (wide.X264_WIDE) before joining")
    master = out(man, "out", "out/master-silent.mp4")
    os.makedirs(os.path.dirname(master), exist_ok=True)
    lst = master + ".concat.txt"
    with open(lst, "w") as fh:
        for sg in segs:
            fh.write(f"file '{sg['silent']}'\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-an",
                    "-movflags", "+faststart", master], check=True)
    os.remove(lst)
    # overlay log, cue list and voice-over on the master timeline
    frames, bounds, cues, offset = [], [], [], 0
    sr, vo_parts = None, []
    for sg in segs:
        n = frame_count(sg["silent"])
        ov = json.load(open(sg["silent"] + ".overlay.json"))
        if len(ov["frames"]) != n:
            raise SystemExit(f"{sg['id']}: overlay log has {len(ov['frames'])} frames, video {n}")
        frames += ov["frames"]
        t0 = offset / FPS
        bounds.append({"id": sg["id"], "start": round(t0, 3), "frames": n, "edl": sg["edl"]})
        for c in json.load(open(sg["cues"])):
            cues.append(dict(c, t=round(c["t"] + t0, 2), segment=sg["id"]))
        if sg["vo"]:
            import wave
            with wave.open(sg["vo"]) as w:
                sr = sr or w.getframerate()
                if w.getframerate() != sr or w.getnchannels() != 1 or w.getsampwidth() not in (2, 4):
                    raise SystemExit(f"{sg['id']}: voice-over must be mono {sr} Hz")
                data = w.readframes(w.getnframes())
                a = np.frombuffer(data, np.int16 if w.getsampwidth() == 2 else np.int32).astype(np.float32)
                a /= 32768.0 if w.getsampwidth() == 2 else 2147483648.0
        else:
            a = np.zeros(0, np.float32)
        vo_parts.append((a, n))
        offset += n
    with open(master + ".overlay.json", "w") as fh:
        json.dump({"fps": FPS, "theme": "case-file", "format": "wide", "segments": bounds, "frames": frames}, fh)
    cues.sort(key=lambda c: c["t"])
    with open(out(man, "cues_out", "out/sfx-cues.json"), "w") as fh:
        json.dump(cues, fh, indent=2, ensure_ascii=False)
    if sr:
        import wave
        track = []
        for a, n in vo_parts:  # each voice-over starts at its segment start, padded or cut to the segment length
            need = int(round(n / FPS * sr))
            track.append(np.pad(a[:need], (0, max(0, need - len(a)))))
        track = np.concatenate(track)
        vo_out = out(man, "vo_out", "out/master-vo.wav")
        with wave.open(vo_out, "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes((np.clip(track, -1, 1) * 32767).astype(np.int16).tobytes())
        prev = out(man, "preview_out", "out/master-vo-preview.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", master, "-i", vo_out, "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                        prev], check=True)
    kinds = sorted({c["kind"] for c in cues})
    print(f"{master}: {offset} frames ({offset / FPS:.2f}s) from {len(segs)} segments, joined with -c copy")
    print(f"segments: " + ", ".join(f"{b['id']} @ {b['start']:.2f}s" for b in bounds))
    print(f"cues: {len(cues)} ({', '.join(kinds)}) -> {out(man, 'cues_out', 'out/sfx-cues.json')}")
    if sr:
        print(f"voice-over on the master timeline -> {vo_out}; preview (voice only, not the mix) -> {prev}")


def main():
    args = sys.argv[1:]
    if len(args) < 2 or args[0] not in ("build", "join", "status"):
        raise SystemExit(__doc__)
    man, segs = load(args[1])
    {"build": lambda: cmd_build(man, segs, args), "join": lambda: cmd_join(man, segs),
     "status": lambda: cmd_status(man, segs)}[args[0]]()


if __name__ == "__main__":
    main()
