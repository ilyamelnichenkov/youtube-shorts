#!/usr/bin/env bash
# yt-dlp from the shared venv ($SHORTS_HOME/venv, created by scripts/setup.sh) with the certifi bundle
# (the system Python often cannot verify certificates).
# Metadata only:  _tools/ytdl.sh --flat-playlist --print "%(id)s | %(uploader)s | %(duration)s | %(title)s" "ytsearch10:<query>"
# One clip:       _tools/ytdl.sh --download-sections "*12.0-18.0" -f "bv*[height<=1080]" -o "_footage/<topic>/<name>.%(ext)s" <url>
# Quote URLs in zsh (a ? is a glob). Prefer _tools/grab.py, which also logs the source.
H="${SHORTS_HOME:-$HOME/.shorts-studio}/venv/bin"
[ -x "$H/yt-dlp" ] || { echo "yt-dlp not found in $H: run scripts/setup.sh first" >&2; exit 1; }
SSL_CERT_FILE="$("$H/python" -c 'import certifi;print(certifi.where())')"
export SSL_CERT_FILE
exec "$H/yt-dlp" "$@"
