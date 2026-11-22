# Shorts Studio kit

**English** · [Русский](README.ru.md)

A portable kit for making short vertical videos (YouTube Shorts, Reels, TikTok) from source footage and a voice-over: script and voice,
an edit list (`edl.json`) rendered by a Python + ffmpeg engine, automatic checks, sound mix, and packaging for upload.
The kit is **topic-neutral**: everything specific to one channel (subject, languages, audience, content rules, look, voice, schedule)
lives in a single `CHANNEL.md` file in the project folder, and the skills read it first.

The same repository installs into **Claude Code** and **Codex**: both read `skills/*/SKILL.md` and the plugin manifest.

```
topic + script  ->  voice (local TTS)  ->  footage  ->  edl.json  ->  render  ->  check.py  ->  sound mix (-14 LUFS)  ->  upload package
```

## What is inside

| Path | What it is |
|---|---|
| `skills/shorts-script-voice` | topic, script, voice with local Kokoro TTS, whisper check, title |
| `skills/shorts-pipeline` | the main workflow: footage, `edl.json`, render, `check.py`, sound, delegating to an editor agent; `references/` holds the `edl.json` digest, lessons learned, an editor brief and `edl-template.json` |
| `skills/shorts-packaging` | the `ready/` folder, numbering, the upload text block, schedule, moving uploaded work to `published/` |
| `engine/_pipeline`, `engine/_fonts` | the engine (Python + ffmpeg): look themes, checks, sound mix (3 CC0 tracks, synthesised effects), open fonts |
| `tools/` | voice (`build_vo.py`), word timings (`words.py`), clip download (`grab.py`, `ytdl.sh`), quote card, HDR tone-mapping |
| `engine/templates/` | the blank channel profile `CHANNEL.md` and the project rules `PROJECT-AGENTS.md` |
| `extras/gaming/` | optional: Steam store media (trailers, screenshots) downloader |
| `scripts/` | `install-system-deps.sh` (ffmpeg, Python, curl), `setup.sh` (packages, models), `shorts-init.sh` (new project folder), `doctor.sh` (checks every dependency), `install-codex.sh` |
| `DEPENDENCIES.md`, `Brewfile`, `engine/requirements*.txt`, `engine/models.sha256` | the full dependency list, pinned package versions, model checksums |
| `.claude-plugin/`, `.codex-plugin/` | plugin and marketplace manifests |

## Install (macOS; Linux works the same except `brew`)

Every dependency is listed in [`DEPENDENCIES.md`](DEPENDENCIES.md): system programs, pinned Python packages, models, disk space.

1. **System programs** (once): `scripts/install-system-deps.sh` (Homebrew or apt; it asks before installing) or
   `brew bundle --file Brewfile`. You need Python 3.10+, ffmpeg (with `libx264` and `aac`) and curl.
2. **The kit**: `git clone https://github.com/ilyamelnichenkov/youtube-shorts ~/shorts-studio`.
3. **Environment, voice and transcription** (about 1 GB: the packages, the Kokoro models checked against checksums, and whisper `small`):
   ```bash
   cd ~/shorts-studio
   scripts/setup.sh
   echo 'export SHORTS_HOME="$HOME/.shorts-studio"' >> ~/.zshrc
   ```
   Everything goes into `$SHORTS_HOME` (default `~/.shorts-studio`: `venv/`, `kokoro/models/`, a copy of the kit in `kit/`); the whisper
   model goes into the Hugging Face cache (`~/.cache/huggingface`, or `$HF_HOME`). Without models: `scripts/setup.sh --skip-models`.
4. **Claude Code**:
   ```bash
   claude plugin marketplace add ~/shorts-studio
   claude plugin install shorts-studio@shorts-studio-kit
   ```
5. **Codex** (either way):
   ```bash
   codex plugin marketplace add ~/shorts-studio
   codex plugin add shorts-studio@shorts-studio-kit
   # or without a marketplace, by copying the skills into ~/.codex/skills:
   scripts/install-codex.sh
   ```
   Restart Codex afterwards. Codex reads the project rules from the `AGENTS.md` that `shorts-init.sh` creates in your project folder.
6. **A project folder**:
   ```bash
   scripts/shorts-init.sh ~/Shorts        # engine, tools, fonts, a blank CHANNEL.md, AGENTS.md, BRIEF.md
   scripts/doctor.sh ~/Shorts             # checks ALL dependencies; it must end with "All good."
   ```
   Then open `~/Shorts` in Claude Code or Codex and ask the agent to fill in `CHANNEL.md` with you.

## How to use it

- "Fill in the channel profile" (the agent interviews you section by section).
- "Find a topic and write a script for a video about ..." -> skill `shorts-script-voice`.
- "Make the video from this script" -> `shorts-pipeline`: voice, clips, `edl.json`, render, checks, sound.
- "Package it for upload" -> `shorts-packaging`.
- For a batch: an editor agent gets `BRIEF.md`, while the script, the voice, the frame-by-frame review and the sound mix stay with the main session.

## Making it yours

The skills know nothing about a subject. Fill in `CHANNEL.md` (languages, audience, facts and content rules, footage sources, labels, voice,
schedule). The look is a theme of the engine (`case-file`, `panel-heist`, `vice-dusk`, `classic`). Voice, speed and language are set in
`vo/beats.json` (`voice`, `speed`, `lang`) or with `SHORTS_VOICE`, `SHORTS_SPEED`, `SHORTS_LANG`; the whisper language follows `lang`.
Joined caption tokens such as "ACME 6" come from the `captions.join_prefix` key of `edl.json`.

## What is not included, and why

- **Footage and finished videos**: the kit neither contains nor distributes any. A project logs its sources in `_footage/SOURCES.md`.
- **System programs, Python packages and models**: not in the repository (size and licences); `install-system-deps.sh` and `setup.sh` install
  them. The list and versions are in `DEPENDENCIES.md`. One venv covers the sound mix too.
- **Long-form 16:9**: the code (`wide.py`, `longform.py`) is in the engine, but the kit ships no demo project and this path is untested.

## Updating

`scripts/shorts-init.sh <project> --update` replaces the project's `_pipeline`, `_tools` and `_fonts` with the kit's copy and touches nothing else.

## What was tested

The full list with results is in [`TESTED.md`](TESTED.md). In short:
- `claude plugin validate` passes for the plugin and the marketplace.
- `setup.sh` from scratch with real downloads and checksum verification, then `doctor.sh` with no warnings (about 1.2 GB).
- `check.py` on a finished video gives `ALL CHECKS PASS`; frames and the cover are pixel-identical to the reference render.
- The sound mix in a clean environment: -14.10 LUFS, -1.30 dBTP and 0 word errors, equal to the reference. Voice and whisper in Spanish and English.
- **Not tested**: installing the plugin with `claude plugin install` / `codex plugin add` and `install-codex.sh` (they change the user's settings),
  `install-system-deps.sh` (it installs system packages), Linux and Windows.

## Licence

The code and documentation of this kit are under the MIT License (`LICENSE`). It does not cover third-party material in the repository, which has
its own terms: fonts under the SIL OFL (texts next to them in `engine/_fonts/*/OFL.txt`) and three CC0 tracks from Freesound (licences and links in
`engine/_pipeline/sound/music/`). Sound effects are synthesised by code. Third-party programs and models (ffmpeg, Kokoro, faster-whisper, yt-dlp and
the packages in `requirements.lock.txt`) are not in the repository and keep their own licences; see `NOTICE.md`.
