# Licence and third-party material

The code and documentation of this kit are under the MIT License (`LICENSE`). The MIT License does not cover the third-party material below.

- Fonts in `engine/_fonts/` are open fonts under the SIL Open Font License; each folder keeps its `OFL.txt`; sources in `_fonts/SOURCES.md`.
  `engine/_fonts/legacy/` (Anton, Inter) belong to the `classic` theme and are also open fonts.
- Music in `engine/_pipeline/sound/music/`: three CC0 tracks from Freesound; credits and licence copies sit next to them (`music.md`).
- Sound effects are synthesised by `engine/_pipeline/sound/synth_sfx.py`; nothing comes from a game, trailer or sample pack.
- Installed at setup time and governed by their own licences: ffmpeg, Python packages in `engine/requirements.txt` (numpy, Pillow,
  scipy, soundfile, pyloudnorm, faster-whisper, kokoro-onnx, onnxruntime, yt-dlp, certifi), the Kokoro ONNX voice model
  (github.com/thewh1teagle/kokoro-onnx) and the whisper "small" model that faster-whisper downloads on first use.
- `skills/shorts-pipeline/references/edl-template.json` is a structural template with placeholder texts and file names.
- This kit does not include or redistribute anyone's footage. Use only footage your channel profile allows and credit its creators.
