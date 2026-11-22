# What was tested (22 Nov 2026, macOS, Python 3.13, ffmpeg 9.0.1)

| Check | Result |
|---|---|
| `claude plugin validate .` and `claude plugin validate .claude-plugin/marketplace.json` | pass (only a "no icon" hint for the public directory) |
| `scripts/setup.sh` into an empty `SHORTS_HOME` and an empty `HF_HOME`, with real downloads | exit 0: 36 pinned packages from the lock file, Kokoro files downloaded and matching `engine/models.sha256`, whisper `small` downloaded; about 1.2 GB in total |
| `scripts/doctor.sh <project>` after that | every line ok, "All good." |
| `scripts/doctor.sh` on an empty machine | lists what is missing and exits 1 |
| `scripts/shorts-init.sh <dir>` | creates `_pipeline`, `_tools`, `_fonts`, `_footage`, `ready/`, `CHANNEL.md`, `AGENTS.md`, `CLAUDE.md`, `BRIEF.md` |
| Engine without a venv | stops with "run scripts/setup.sh or set SHORTS_PY" |
| `check.py` of the kit engine on a finished 21 s short | `ALL CHECKS PASS` |
| Four frames and the cover rendered by the kit engine vs the original engine, same edit list | identical pixels (max difference 0) |
| `mix.py --strict` in the freshly installed environment on the same short | -14.10 LUFS, -1.30 dBTP, LRA 3.8 LU, 0 word errors: equal to the original mix |
| The same mix without the `.overlay.json` | runs, warns, and comes out different (-14.20 LUFS, -3.50 dBTP): the file is required for a faithful mix |
| `build_vo.py` + `words.py` with `"voice": "ef_dora", "lang": "es"` and with no voice keys | Spanish voice transcribed as Spanish; default stays `am_puck`/English |

Not tested: `claude plugin install` / `codex plugin add` and `install-codex.sh` (they change the user's settings), `install-system-deps.sh`
(it installs system packages), Linux and Windows, long-form (`wide.py`, `longform.py`) from the kit.
