#!/usr/bin/env bash
# One-time setup of everything the production pipeline needs on a new computer. Safe to run again (it skips what is in place).
#   scripts/setup.sh                 # venv + all Python packages + Kokoro voice models + whisper model (~1 GB download)
#   scripts/setup.sh --skip-models   # without the models (copy them from another machine or download later)
# System programs (ffmpeg, python, curl) come from scripts/install-system-deps.sh or your package manager.
# Everything else goes into $SHORTS_HOME (default ~/.shorts-studio): venv/, kokoro/models/, kit/. The whisper model goes to the
# Hugging Face cache (~/.cache/huggingface, or $HF_HOME). Nothing is installed system-wide.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
SKIP_MODELS=0
for a in "$@"; do [ "$a" = "--skip-models" ] && SKIP_MODELS=1; done
say() { printf '\n== %s\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1. $2" >&2; exit 1; }; }

say "Checking system programs"
need python3 "Install Python 3.10+ (scripts/install-system-deps.sh does it)."
need ffmpeg  "Install ffmpeg with libx264 and aac (scripts/install-system-deps.sh does it)."
need ffprobe "Comes with ffmpeg."
need curl    "Install curl."
python3 - <<'PY'
import sys
assert sys.version_info >= (3, 10), "Python 3.10+ is required, found %s" % sys.version.split()[0]
import venv  # noqa: F401  (apt: python3-venv)
print("python", sys.version.split()[0])
PY
miss="$(ffmpeg_missing)"
if [ -n "$miss" ]; then echo "This ffmpeg lacks what the pipeline needs:" >&2; echo "$miss" | sed 's/^/  - /' >&2; echo "Install a full ffmpeg build (Homebrew's or apt's has all of it)." >&2; exit 1; fi
echo "ffmpeg: $(ffmpeg -version | head -1 | cut -c1-60)"
mkdir -p "$SHORTS_HOME"
g="$(free_gb "$SHORTS_HOME")"; [ -z "$g" ] || [ "$g" -ge 4 ] || echo "Warning: only $g GB free in $SHORTS_HOME; the install needs about 4 GB." >&2

say "Python environment in $SHORTS_HOME/venv"
if [ ! -x "$SHORTS_HOME/venv/bin/python" ]; then python3 -m venv "$SHORTS_HOME/venv"; fi
PIP=("$SHORTS_HOME/venv/bin/python" -m pip install --quiet)
"${PIP[@]}" --upgrade pip
if ! "${PIP[@]}" -r "$KIT/engine/requirements.lock.txt"; then
  echo "The pinned set was not installable here; falling back to the top-level requirements." >&2
  "${PIP[@]}" -r "$KIT/engine/requirements.txt"
fi
"${PIP[@]}" --upgrade yt-dlp certifi   # video sites change often: the downloader is kept current on purpose

if [ "$SKIP_MODELS" = 0 ]; then
  say "Kokoro voice models in $MODELS_DIR"
  mkdir -p "$MODELS_DIR"
  BASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
  for f in kokoro-v1.0.onnx voices-v1.0.bin; do
    if model_ok "$f"; then echo "ok (checksum matches): $f"; continue; fi
    curl -L --fail -o "$MODELS_DIR/$f" "$BASE/$f"
    model_ok "$f" || { echo "Checksum or size of $f does not match engine/models.sha256; delete it and retry." >&2; exit 1; }
    echo "downloaded and verified: $f"
  done
  say "Whisper model (faster-whisper small, ~0.5 GB, Hugging Face cache)"
  if whisper_cached; then echo "already cached"; else
    "$SHORTS_HOME/venv/bin/python" -c 'from faster_whisper import WhisperModel; WhisperModel("small", device="cpu", compute_type="int8"); print("downloaded")'
  fi
fi

# keep a copy of the kit at a fixed place so any agent can find the scripts and skills
if [ "$KIT" != "$SHORTS_HOME/kit" ]; then
  rm -rf "$SHORTS_HOME/kit"; mkdir -p "$SHORTS_HOME/kit"
  (cd "$KIT" && tar --exclude .git --exclude __pycache__ -cf - .) | (cd "$SHORTS_HOME/kit" && tar -xf -)
fi

say "Done"
echo "Add this to your shell profile so every tool finds the environment:"
echo "  export SHORTS_HOME=\"$SHORTS_HOME\""
echo "Then check everything with:  scripts/doctor.sh"
