# Shorts project rules (read by Codex as AGENTS.md; Claude Code imports it through CLAUDE.md)

This folder makes vertical short-form videos (YouTube Shorts / Reels / TikTok) with the clip-based pipeline of the Shorts Studio kit.

**Read `CHANNEL.md` first.** It describes THIS channel: topic, languages, audience, tone, facts policy, content and safety rules,
footage and rights, look, voice, schedule and working agreements. It overrides every default below. If it is missing or has
empty sections, ask the owner (or fill it with them from the template) before producing anything.
Talk to the owner in the language the profile names; keep code, commands, file names and API names as they are.

## How work is done here
- A video is an edit list `edl.json` + a voice-over -> render -> check -> sound mix -> package. Use the skills
  **shorts-script-voice** (topic, script, voice), **shorts-pipeline** (footage, edit, render, check, mix) and **shorts-packaging**
  (ready/ folder, upload block). If your tool does not load skills by itself, open their `SKILL.md` files in the kit
  (`$SHORTS_HOME/kit/skills/` or the plugin folder) and follow them.
- Toolchain check: `scripts/doctor.sh <this folder>` from the kit (it checks ffmpeg, Python packages, voice and whisper models; the
  list is in the kit's `DEPENDENCIES.md`). Python tools run with `$SHORTS_HOME/venv/bin/python`
  (`SHORTS_HOME` defaults to `~/.shorts-studio`).
- Briefing a sub-agent editor: give it `BRIEF.md` of this folder. You do the script, the voice, the frame-by-frame review and the
  sound mix yourself; an agent's report is a claim, not proof.

## Defaults (the profile may change them)
- One argument per video; facts verifiable and attributed in the voice; nothing the sources do not say.
- No violence, weapons or blood in the first 3 seconds or on the cover; no creator overlays or watermarks in any frame.
- All readable text inside the phone safe zone: y 300-1580, x 130-950 (x <= 860 for y 1000-1600). check.py enforces it.
- Covers are vertical 1080x1920 JPG under 2 MB, readable at 180 px wide, with the topic's name on them.
- Log every source file (creator, URL, date) in `_footage/SOURCES.md` and credit it in the description.

## Safety
- Do not commit, push, delete or overwrite the owner's files unless asked; look at a target before replacing it.
- Never put keys or tokens into files, logs or commands. Install tools only inside this folder or `$SHORTS_HOME`.
- Do not download from sources the channel profile does not allow; do not work around age restrictions or logins.
