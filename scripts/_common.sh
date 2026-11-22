# Shared helpers for setup.sh and doctor.sh (sourced, not run).
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHORTS_HOME="${SHORTS_HOME:-$HOME/.shorts-studio}"
MODELS_DIR="$SHORTS_HOME/kokoro/models"

sha256_of() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

# prints what the installed ffmpeg lacks for the pipeline (empty output = nothing missing)
ffmpeg_missing() {
  local enc fl x
  enc="$(ffmpeg -hide_banner -encoders 2>/dev/null)"; fl="$(ffmpeg -hide_banner -filters 2>/dev/null)"
  for x in libx264 aac; do grep -q " $x " <<<"$enc" || echo "encoder $x"; done
  for x in scale fps tile select lut3d loudnorm ebur128 silencedetect blend; do grep -q " $x " <<<"$fl" || echo "filter $x"; done
}

# model_ok <file-name>: size and sha256 match engine/models.sha256
model_ok() {
  local name="$1" f="$MODELS_DIR/$1" want size
  [ -s "$f" ] || return 1
  read -r want size < <(awk -v n="$name" '$3==n {print $1, $2}' "$KIT/engine/models.sha256")
  [ -n "$want" ] || return 1
  [ "$(wc -c < "$f" | tr -d ' ')" = "$size" ] && [ "$(sha256_of "$f")" = "$want" ]
}

# whisper_cached: the faster-whisper "small" model files are in the local Hugging Face cache
whisper_cached() {
  "$SHORTS_HOME/venv/bin/python" - <<'PY' 2>/dev/null
import sys
from faster_whisper.utils import download_model
try:
    download_model("small", local_files_only=True)
except Exception:
    sys.exit(1)
PY
}

free_gb() { df -k "$1" 2>/dev/null | awk 'NR==2 {printf "%d", $4/1024/1024}'; }
