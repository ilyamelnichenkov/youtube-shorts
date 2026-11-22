---
name: shorts-pipeline
description: Make, render, check, mix and package a vertical 1080x1920 short-form video (YouTube Shorts, Reels, TikTok) built from source footage plus a voice-over with the clip-based pipeline (edl.json, build.py, check.py, sound/mix.py). Use whenever the task is to produce, fix or review such a video, to brief a sub-agent editor, or to explain why check.py fails.
---

# Shorts pipeline (topic-neutral)

One edit list (`<short>/edl.json`) plus a voice-over gives a finished video: moving clips in a themed photo "window", word
captions, a hook plate, one hero circle, a cover, an sfx cue list, then a sound mix at -14 LUFS.
**Everything specific to a channel (topic, languages, audience, content rules, look, voice, credits, schedule) lives in the
project's `CHANNEL.md`. Read it first and follow it over the defaults below.** If it is missing or has empty sections, ask the
owner (or copy `engine/templates/CHANNEL.md` and fill it with them) before producing anything.
Related skills: `shorts-script-voice` (topic, script, voice) and `shorts-packaging` (finished files, upload texts).

## Before anything
0. Kit scripts (`setup.sh`, `shorts-init.sh`, `doctor.sh`, `install-codex.sh`) live in the `scripts/` folder of the kit: the plugin
   folder, or `$SHORTS_HOME/kit/scripts/` (`setup.sh` and `install-codex.sh` keep a copy there).
1. Work from a **project folder** that contains `_pipeline/`, `_tools/`, `_fonts/`, `CHANNEL.md` (create one with
   `scripts/shorts-init.sh <dir>`). Every command below runs from that folder's root.
2. Run `scripts/doctor.sh <project-dir>` once per machine. It checks every dependency (system programs, Python packages, models, free
   disk) and must end with "All good." If not: `scripts/install-system-deps.sh` for ffmpeg/Python/curl, `scripts/setup.sh` for the
   rest. The full list is in `DEPENDENCIES.md` of the kit.
3. `SHORTS_HOME` (default `~/.shorts-studio`) holds the Python venv and the voice models. Export it if you put it elsewhere.
4. Read `_pipeline/README.md` (engine reference) and `references/edl-notes.md` before writing an edit list.

## The workflow (each step has its own check)
| # | Step | Command / output | Verify |
|---|---|---|---|
| 1 | Topic + script | skill `shorts-script-voice` | one claim, sources attributed, owner OK when the profile asks for it |
| 2 | Voice | `$SHORTS_HOME/venv/bin/python _tools/build_vo.py <short>/vo/beats.json`, then `_tools/words.py <short>/vo` | read `vo/words.json`: every word right |
| 3 | Footage | `_tools/grab.py <topic> '<url>' <start> <end> --tag NAME` (logs `_footage/SOURCES.md`), or your own recordings | contact sheet of every clip; policy from `CHANNEL.md` |
| 4 | Edit list | copy `references/edl-template.json`, change the content | `build.py <edl> --words` shows caption tokens |
| 5 | Render | `python3 _pipeline/build.py <short>/edl.json --theme <theme>` (3-10 min; 4K60 is slow) | no error; the file is newer than the edl |
| 6 | Cover | `... build.py <edl> --cover` | "safe-zone violations: none", readable at 180 px wide |
| 7 | Check | `python3 _pipeline/check.py <short>/<name>-<theme>-silent.mp4 <short>/edl.json` | prints `ALL CHECKS PASS`; you looked at every contact sheet |
| 8 | Sound | `$SHORTS_HOME/venv/bin/python _pipeline/sound/mix.py <short> --theme <theme> --music <name> --strict` | -14.0 +/-0.5 LUFS, true peak <= -1.0 dBTP, word errors near 0 |
| 9 | Package | skill `shorts-packaging` | file + cover + upload block in `ready/` |

Contact sheets of a source clip: `ffmpeg -ss <t> -i <file> -t <d> -vf "fps=2,scale=320:-1,tile=7x4" -frames:v 1 out.png`
(write PNG: JPEG output of some sources fails with "non full-range YUV"). Shot boundaries:
`ffmpeg -i <file> -vf "scale=320:180,select='gt(scene,0.25)',showinfo" -an -f null - 2>&1 | grep -o "pts_time:[0-9.]*"`.
Themes: `case-file` (dossier paper), `panel-heist` (comic page), `vice-dusk` (neon dusk), `classic`; the profile picks one.

## What a good short looks like (defaults; the profile overrides)
- 18-45 s, one argument from hook to payoff, a cut every 1.5-3 s, every shot moves, the hook plate is on from frame 0
  (`hook.y` 1170 keeps it clear of the exhibit label), one hero moment with a red circle on something the frame really shows.
- Picture follows the words. Captions are 2-3 word phrases (`break_before`); names stay in one group.
- The last shot cuts back into the first frame (the video loops).
- All readable text stays in the phone safe zone: y 300-1580, x 130-950 (x <= 860 for y 1000-1600). check.py enforces it.
- Tall photo window `"aspect": "3:4"` (900x1200) on clips of 1080p and up; 720p or letterboxed sources cannot fill it.

## Hard-won lessons (details in `references/lessons.md`)
- **The edl is newer than the render? The render is stale.** Rebuild before you judge check.py.
- **Frozen stills** (consecutive frames barely differ for > 0.3 s) fail check.py. Static screens, flat colours and idle subjects
  need constant-speed motion: `"move_ease": "linear"`, a zoom range of 0.15-0.4 and a pan of 150+ source px.
  `float` alone is not enough (the sine slows to zero at its turns).
- **Zoom limits:** 4K sources <= 1.00, 1080p <= 1.25, 720p <= 1.0 (check.py prints the limit per clip).
- **Creator overlays** (watermark, facecam, lower third, subtitles, stylised banners) never reach the picture: crop with the
  top-level `sources` picture override, move the crop, or choose other frames. Look at every cut frame.
- **Honesty:** labels, circles and captions say only what the frame shows; attribute facts to their source in the voice.
- **Cover:** a full-bleed crop of one source frame; the plate sits at `tab_y` (330) and hides the top of the picture. For a
  subject near the top set `tab_y` about 1090 and `stamp_y` about 410.
- One render at a time (a 4K60 render uses all cores); never start a second render of the same folder.

## Delegating an edit to a sub-agent
Give the agent `BRIEF.md` (created by shorts-init from `references/editor-brief.md`) plus the script, the voice files and the
clip list. The main session writes the script and the voice, **reviews every frame itself** and does the sound mix: an agent's
report is a claim, not proof. Check file times (silent mp4 newer than edl, check log newer than the mp4) before accepting.
