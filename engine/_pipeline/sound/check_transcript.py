"""Whisper check of a decoded mix against the script.  Run with the shared venv (faster-whisper):
  $SHORTS_HOME/venv/bin/python check_transcript.py <audio.wav> <vo/words.json>
Audio is passed to faster-whisper as a 16 kHz float32 numpy array (not a path). Prints one JSON object."""
import json, re, subprocess, sys
import numpy as np
from faster_whisper import WhisperModel

import os
LANG = os.environ.get("SHORTS_WHISPER_LANG", "en")
NUMW = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
        "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]

def norm(w): return re.sub(r"[^a-z0-9]", "", w.lower())

def main(wav, words_json):
    global LANG
    bj = os.path.join(os.path.dirname(words_json), "beats.json")  # language of the voice, if the project says so
    if "SHORTS_WHISPER_LANG" not in os.environ and os.path.exists(bj):
        l = (json.load(open(bj)).get("lang") or "en").split("-")[0]
        LANG = {"cmn": "zh"}.get(l, l)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", wav, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, np.float32)
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(audio, language=LANG, word_timestamps=True, beam_size=5)
    got = [(w.word.strip(), w.start, w.end) for s in segs for w in s.words]
    exp = [w["w"] for w in json.load(open(words_json))]
    # English digits and number words count as the same token ("6" == "six"); everything else compares as spoken
    def canon(ws):
        out = []
        for x in ws:
            for t in x.lower().split():
                d = re.sub(r"[^0-9]", "", t)
                if LANG == "en" and d and d == re.sub(r"[^a-z0-9]", "", t) and int(d) < len(NUMW):
                    t = NUMW[int(d)]
                if norm(t): out.append(norm(t))
        return out
    e, g = canon(exp), canon([x[0] for x in got])
    # word-level edit distance
    d = np.zeros((len(e) + 1, len(g) + 1), int); d[:, 0] = range(len(e) + 1); d[0, :] = range(len(g) + 1)
    for i in range(1, len(e) + 1):
        for j in range(1, len(g) + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (e[i - 1] != g[j - 1]))
    print(json.dumps({"text": " ".join(x[0] for x in got), "expected_words": len(e), "heard_words": len(g),
                      "word_errors": int(d[-1, -1]), "wer": round(float(d[-1, -1]) / max(1, len(e)), 3),
                      "words": [[x[0], round(x[1], 2), round(x[2], 2)] for x in got]}))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
