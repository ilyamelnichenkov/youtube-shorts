# Lessons from 24 shorts (read before fixing a failing render)

## Process
- A render is stale when `edl.json` is newer than the silent mp4. Compare times (`stat -f %Sm` on macOS) before reading any
  check result; a killed agent often leaves a new edl and an old render.
- Never run two renders of the same folder; a 4K60 build uses all cores. Other heavy jobs (Blender, TTS on the same GPU)
  starve it: do the voice first, renders after.
- Agent reports are claims. Look at both contact sheets, single frames at every cut, the hook, the hero and the cover.
- `build.py --cover` is cheap (5 s): iterate on the cover alone, then render the video once.

## check.py: frozen stills
- Cause: static UI (menus, slot lists), flat coloured screens, idle characters, slow motion on flat content.
- Fix that works: `move_ease: "linear"`, `zoom` range 0.15-0.4 (for example 0.56 -> 0.92), `cx` pan 150-450 source px,
  plus a fast small `float` (amp 36-56, period 0.8-1.3). Keep both ends of the move inside the picture and under the zoom
  limit (4K <= 1.00; a limit failure like "c10 scale 1.080 (limit 1.00)" is a separate error).
- The pan must not run into a clamp: at the 3:4 window on a 2048x1152 source the vertical room is only a few px, so vertical
  float does nothing there; pan horizontally.
- "cut at X sits next to a still picture" means the clip on one side of the cut is still: fix that clip, not the cut.

## Footage
- Whatever the footage policy of the channel allows, log every file (creator, title, URL, date) in `_footage/SOURCES.md`, credit it in
  the description and never use someone's commentary or music audio.
- Reject: 360p downloads, facecams, creator subtitles, watermarks, lower thirds, "subscribe" banners, stylised banners drawn by
  the creator, and anything the channel's content rules forbid (violence, spoilers, private data ...).
- HDR10 sources (smpte2084) come out dark and flat: tone-map to an SDR copy with `_tools/hdr_to_sdr.py`, keep the original.
- Age-restricted videos cannot be downloaded without cookies; do not look for ways around that (the profile may forbid it anyway).
- `_tools/grab.py` takes m:ss or plain seconds and picks the highest resolution; log lines go to `_footage/SOURCES.md`.

## Voice and captions
- Kokoro voice, speed and language come from the profile (default `am_puck`, 1.12, `en-us`). Spell numbers out. Whisper mishears
  letter-by-letter acronyms at the start of a sentence ("G T A six"): write them the way they are spoken ("Grand Theft Auto six")
  and keep the caption spelling you want in `words-captions.json`.
- Whisper also trips on sentence-initial "And", "So", "Load": rephrase ("But the moment...", "Try a save...").
- Names TTS reads as two words are fixed in `words-captions.json`, not by re-recording.

## Cover and hero
- Hero circle and label describe only what the frame shows ("THE PHONE", "SAVE MENU"), never a claim.
- A cover plate at the default `tab_y` hides the top of the frame: choose a frame whose subject sits in the middle, or move the plate.
- Keep the topic's name readable on every cover (readable at 180 px).

## Sound
- `mix.py` needs exactly one `*-<theme>-silent.mp4` in the folder, with its `.overlay.json` next to it (sounds of the circle, tab and stamps
  are derived from it; a mix without it is quieter on peaks and differs from the real one). `--strict` fails on unknown sfx cues.
- Targets: -14.0 +/-0.5 LUFS, true peak <= -1.0 dBTP, whisper word errors near 0 (tolerate 1-4 on long texts).
- Rotate the bundled CC0 tracks between neighbouring videos (`--music trap-suspense|the-chase|trip-hop`); credit the track in the description.
