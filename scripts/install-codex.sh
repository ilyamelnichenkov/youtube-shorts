#!/usr/bin/env bash
# Install the kit's skills for Codex without a plugin marketplace (user scope), and keep a copy of the kit in $SHORTS_HOME/kit
# so the scripts have a fixed location.   scripts/install-codex.sh
set -euo pipefail
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHORTS_HOME="${SHORTS_HOME:-$HOME/.shorts-studio}"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$SHORTS_HOME" "$CODEX_HOME/skills"
if [ "$KIT" != "$SHORTS_HOME/kit" ]; then
  rm -rf "$SHORTS_HOME/kit"; mkdir -p "$SHORTS_HOME/kit"
  (cd "$KIT" && tar --exclude .git --exclude __pycache__ -cf - .) | (cd "$SHORTS_HOME/kit" && tar -xf -)
fi
for d in "$KIT"/skills/*/; do
  n="$(basename "$d")"; rm -rf "$CODEX_HOME/skills/$n"; cp -R "$d" "$CODEX_HOME/skills/$n"; echo "skill installed: $CODEX_HOME/skills/$n"
done
echo "Kit copy: $SHORTS_HOME/kit   (scripts: $SHORTS_HOME/kit/scripts)"
echo "Restart Codex so it rescans the skills. Add to ~/.codex/AGENTS.md or the project AGENTS.md:  The Shorts kit lives in $SHORTS_HOME/kit."
