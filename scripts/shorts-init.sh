#!/usr/bin/env bash
# Create (or refresh) a Shorts project folder: engine, tools, fonts, briefing and folders for footage and finished videos.
#   scripts/shorts-init.sh <project-dir>            # new project with an empty CHANNEL.md to fill in
#   scripts/shorts-init.sh <project-dir> --update   # overwrite _pipeline/_tools/_fonts with the kit's newer copy (your work is untouched)
set -euo pipefail
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="${1:?usage: shorts-init.sh <project-dir> [--update]}"
UPDATE=0
shift
while [ $# -gt 0 ]; do
  case "$1" in
    --update) UPDATE=1 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
mkdir -p "$DIR"; DIR="$(cd "$DIR" && pwd)"

copy_dir() {  # copy_dir <from> <to>: replaces engine folders, never touches anything else
  if [ -e "$2" ] && [ "$UPDATE" = 0 ]; then echo "exists, kept: $2 (use --update to refresh)"; return; fi
  rm -rf "$2"; mkdir -p "$(dirname "$2")"; cp -R "$1" "$2"; echo "copied: $2"
}
copy_dir "$KIT/engine/_pipeline" "$DIR/_pipeline"
copy_dir "$KIT/engine/_fonts"    "$DIR/_fonts"
copy_dir "$KIT/tools"            "$DIR/_tools"
mkdir -p "$DIR/_footage" "$DIR/ready/published"
find "$DIR/_pipeline" "$DIR/_tools" -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
chmod +x "$DIR/_tools/ytdl.sh" 2>/dev/null || true

[ -e "$DIR/AGENTS.md" ] || { cp "$KIT/engine/templates/PROJECT-AGENTS.md" "$DIR/AGENTS.md"; echo "created: $DIR/AGENTS.md"; }
[ -e "$DIR/CHANNEL.md" ] || { cp "$KIT/engine/templates/CHANNEL.md" "$DIR/CHANNEL.md"; echo "created: $DIR/CHANNEL.md (empty profile: fill it in with the agent)"; }
[ -e "$DIR/CLAUDE.md" ] || { printf '@AGENTS.md\n' > "$DIR/CLAUDE.md"; echo "created: $DIR/CLAUDE.md (imports AGENTS.md)"; }
[ -e "$DIR/BRIEF.md" ] || { cp "$KIT/skills/shorts-pipeline/references/editor-brief.md" "$DIR/BRIEF.md"; echo "created: $DIR/BRIEF.md"; }
echo
echo "Project ready: $DIR"
echo "Next: fill in $DIR/CHANNEL.md, run scripts/doctor.sh $DIR (checks the toolchain), then ask the agent to make a video with the shorts-pipeline skill."
