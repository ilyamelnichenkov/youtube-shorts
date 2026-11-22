"""Render one segment's voice-over beat by beat with local Kokoro: <seg>/vo/vo.wav + timings.json.

Run: $SHORTS_HOME/venv/bin/python _tools/build_vo.py <seg>/vo/beats.json
beats.json: {"lead": s, "beats": [[id, text, pause_after_s], ...], "voice": "am_puck", "speed": 1.12, "lang": "en-us"} (numbers spelled out;
voice/speed/lang optional, see the channel profile; Kokoro languages: en-us, en-gb, es, fr-fr, it, ja, pt-br, cmn).
"lead" is silence before the first word (room for the case card); pauses give graphics their reading time.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

MODELS = Path(os.environ.get("SHORTS_HOME") or Path.home() / ".shorts-studio") / "kokoro" / "models"


def main():
    cfg = Path(sys.argv[1])
    out = cfg.parent
    spec = json.loads(cfg.read_text())
    beats, lead = spec["beats"], spec.get("lead", 0.0)
    # voice settings: beats.json keys "voice" / "speed" / "lang", else SHORTS_VOICE / SHORTS_SPEED / SHORTS_LANG, else the defaults
    VOICE = spec.get("voice") or os.environ.get("SHORTS_VOICE", "am_puck")
    SPEED = float(spec.get("speed") or os.environ.get("SHORTS_SPEED", 1.12))
    LANG = spec.get("lang") or os.environ.get("SHORTS_LANG", "en-us")
    k = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    chunks, timings, t, sr = [], [], lead, None
    for bid, text, pause in beats:
        samples, sr = k.create(text, voice=VOICE, speed=SPEED, lang=LANG)
        dur = len(samples) / sr
        timings.append({"id": bid, "text": text, "start": round(t, 3), "end": round(t + dur, 3)})
        chunks += [samples, np.zeros(int(pause * sr), dtype=samples.dtype)]
        t += dur + pause
    chunks.insert(0, np.zeros(int(round(lead * sr)), dtype=chunks[0].dtype))
    sf.write(out / "vo.wav", np.concatenate(chunks), sr)
    (out / "timings.json").write_text(json.dumps({"voice": VOICE, "speed": SPEED, "duration": round(t, 3),
                                                  "beats": timings}, indent=2))
    for b in timings:
        print(f"{b['start']:6.2f}-{b['end']:6.2f}  {b['id']}")
    print(f"total {t:.2f}s")


if __name__ == "__main__":
    main()
