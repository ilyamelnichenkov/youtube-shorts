#!/usr/bin/env bash
# Check everything the production pipeline needs; with a project dir also check its folders.   scripts/doctor.sh [<project-dir>]
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
PY="$SHORTS_HOME/venv/bin/python"
bad=0
ok()   { printf '  ok       %s\n' "$*"; }
fail() { printf '  MISSING  %s\n' "$*"; bad=1; }
warn() { printf '  warning  %s\n' "$*"; }
echo "SHORTS_HOME = $SHORTS_HOME"
echo "System programs"
for t in python3 ffmpeg ffprobe curl; do command -v "$t" >/dev/null 2>&1 && ok "$t" || fail "$t (scripts/install-system-deps.sh)"; done
if command -v ffmpeg >/dev/null 2>&1; then
  m="$(ffmpeg_missing)"; if [ -z "$m" ]; then ok "ffmpeg has libx264, aac and every filter used"; else fail "ffmpeg lacks: $(echo $m | tr '\n' ',') (install a full build)"; fi
fi
if [ -x "$PY" ]; then
  echo "Python environment"
  ok "venv python: $("$PY" --version 2>&1)"
  for m in numpy PIL scipy soundfile pyloudnorm faster_whisper kokoro_onnx onnxruntime yt_dlp certifi huggingface_hub; do
    "$PY" -c "import $m" 2>/dev/null && ok "python module $m" || fail "python module $m (scripts/setup.sh)"
  done
else
  fail "venv at $SHORTS_HOME/venv (run scripts/setup.sh)"
fi
echo "Models"
for f in kokoro-v1.0.onnx voices-v1.0.bin; do
  if [ ! -s "$MODELS_DIR/$f" ]; then fail "voice model $f (scripts/setup.sh downloads it)"; elif model_ok "$f"; then ok "voice model $f (checksum matches)"; else fail "voice model $f is damaged or a different version (delete it and run scripts/setup.sh)"; fi
done
if [ -x "$PY" ]; then whisper_cached && ok "whisper model small (cached)" || warn "whisper model small is not cached yet (scripts/setup.sh downloads it; needed by words.py and mix.py)"; fi
g="$(free_gb "$HOME")"; [ -z "$g" ] || { [ "$g" -ge 4 ] && ok "free disk: $g GB" || warn "free disk: $g GB (renders need several GB)"; }
if [ -n "${1:-}" ]; then
  echo "Project $1"
  for d in _pipeline _tools _fonts _footage ready; do [ -d "$1/$d" ] && ok "$d/" || fail "$d/ (run scripts/shorts-init.sh $1)"; done
  [ -s "$1/CHANNEL.md" ] && ok "CHANNEL.md" || fail "CHANNEL.md (run scripts/shorts-init.sh $1)"
fi
[ $bad = 0 ] && echo "All good." || echo "Some parts are missing (see above)."
exit $bad
