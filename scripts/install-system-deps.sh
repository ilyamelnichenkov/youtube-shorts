#!/usr/bin/env bash
# Install the system programs the pipeline calls: ffmpeg (with libx264 and aac; it provides ffprobe), curl, Python 3.10+ with venv.
#   scripts/install-system-deps.sh          # shows the command and asks before running it
#   scripts/install-system-deps.sh --yes    # no question
# Supports Homebrew (macOS or Linux) and apt (Debian/Ubuntu). Other systems: see DEPENDENCIES.md.
set -euo pipefail
YES=0; [ "${1:-}" = "--yes" ] && YES=1
if command -v brew >/dev/null 2>&1; then
  CMD=(brew install ffmpeg python)
elif command -v apt-get >/dev/null 2>&1; then
  CMD=(sudo apt-get install -y ffmpeg python3 python3-venv python3-pip curl)
else
  echo "No Homebrew or apt found. Install ffmpeg (with libx264 and aac), Python 3.10+ with venv, and curl yourself; see DEPENDENCIES.md." >&2
  exit 1
fi
echo "This will run: ${CMD[*]}"
if [ "$YES" = 0 ]; then read -r -p "Continue? [y/N] " a; [ "$a" = "y" ] || [ "$a" = "Y" ] || { echo "Cancelled."; exit 0; }; fi
"${CMD[@]}"
echo "Done. Next: scripts/setup.sh"
