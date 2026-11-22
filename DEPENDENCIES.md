# Dependencies (everything needed to run production)

`scripts/install-system-deps.sh` installs the system programs, `scripts/setup.sh` installs everything else and downloads the models,
`scripts/doctor.sh` checks the result. Versions are the ones tested in Nov 2026 on macOS with Python 3.13.

## 1. System programs (not installed by pip)

| Program | Needed for | Notes |
|---|---|---|
| Python 3.10+ with `venv` | engine, tools | apt: `python3 python3-venv python3-pip` |
| ffmpeg and ffprobe | decoding clips, encoding, loudness, contact sheets | needs the encoders `libx264` and `aac` and the filters `scale fps tile select lut3d loudnorm ebur128 silencedetect blend`; Homebrew's and apt's builds have all of them (`zscale` is NOT needed) |
| curl | model download, Steam helper | preinstalled on macOS |
| a shell (bash) | scripts | macOS and Linux; Windows only through WSL (untested) |

Install: `scripts/install-system-deps.sh` (Homebrew or apt), or `brew bundle --file Brewfile`.

## 2. Python packages (venv in `$SHORTS_HOME/venv`)

| Package | Version | Used by |
|---|---|---|
| numpy | 2.5.4 | engine (frames), HDR tool, sound |
| pillow | 13.0.0 | engine (drawing, covers) |
| scipy | 1.18.1 | sound mix and sfx synthesis |
| soundfile | 0.14.0 | reading and writing audio |
| pyloudnorm | 0.2.0 | loudness (LUFS) measurement and normalisation |
| faster-whisper | 1.2.1 | word timings (`tools/words.py`) and the transcript check in the mix |
| kokoro-onnx | 0.6.1 | local text-to-speech (`tools/build_vo.py`) |
| onnxruntime | 1.31.1 | runs the Kokoro model |
| yt-dlp, certifi | latest | `tools/grab.py` and `tools/ytdl.sh` (kept current on purpose) |

`engine/requirements.txt` lists these; `engine/requirements.lock.txt` pins all 36 packages including transitive ones
(ctranslate2, huggingface_hub, tokenizers, av, phonemizer, espeakng-loader, ...). The text-to-speech phonemizer library is
bundled by `espeakng-loader`, so no separate espeak install is needed.

## 3. Models (downloaded by `setup.sh`)

| Model | Size | Where | Check |
|---|---|---|---|
| Kokoro v1.0 ONNX (`kokoro-v1.0.onnx`) | 326 MB | `$SHORTS_HOME/kokoro/models/` | sha256 in `engine/models.sha256` |
| Kokoro voices (`voices-v1.0.bin`) | 28 MB | same folder | same |
| faster-whisper `small` (Systran/faster-whisper-small) | about 0.5 GB | Hugging Face cache (`~/.cache/huggingface`, or `$HF_HOME`) | downloaded by the library |

Source of the Kokoro files: github.com/thewh1teagle/kokoro-onnx, release `model-files-v1.0`.

## 4. Bundled in the repository (nothing to install)

Engine and tools (`engine/`, `tools/`), look themes, fonts (open fonts under the SIL OFL, `engine/_fonts/`), three CC0 music tracks
and about 25 synthesised sound effects (`engine/_pipeline/sound/`).

## 5. Network and disk

- Internet is needed once for setup (packages, models) and later only for `tools/grab.py` and `tools/ytdl.sh`.
- Disk: the environment and models take about 1.2 GB (venv 0.4 GB, Kokoro 0.35 GB, whisper 0.46 GB); keep at least 4 GB free for footage and
  renders (a 4K60 render needs several GB of temporary files).
- A 4K60 render uses all CPU cores and takes 3-10 minutes per video; no GPU is needed.

## 6. Optional

- `extras/gaming/steam_media.py`: Steam store media (needs only Python and curl, no extra packages).
- A vision- or audio-inspection tool for the agent (for example an MCP server) can help review frames and sound but is not required.
