"""Word-level timestamps for <short>/vo/vo.wav -> <short>/vo/words.json (burned-in captions).
Run: $SHORTS_HOME/venv/bin/python _tools/words.py <short>/vo
"""
import json, subprocess, sys
from pathlib import Path
import numpy as np
from faster_whisper import WhisperModel
here = Path(sys.argv[1])
# whisper language: SHORTS_WHISPER_LANG, else the "lang" of vo/beats.json (en-us -> en), else en
import os
LANG = os.environ.get("SHORTS_WHISPER_LANG")
if not LANG and (here / "beats.json").exists():
    LANG = (json.loads((here / "beats.json").read_text()).get("lang") or "en").split("-")[0]
LANG = {"cmn": "zh"}.get(LANG, LANG) or "en"
pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(here / "vo.wav"), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"], check=True, capture_output=True).stdout
audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
segs, _ = WhisperModel("small", device="cpu", compute_type="int8").transcribe(audio, language=LANG, word_timestamps=True, beam_size=5)
words = [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)} for s in segs for w in s.words]
(here / "words.json").write_text(json.dumps(words, indent=1))
print(" ".join(w["w"] for w in words)); print(len(words), "words")
