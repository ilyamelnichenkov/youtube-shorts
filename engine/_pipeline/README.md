# Clip-based Shorts pipeline

One edit list (`edl.json`) plus a voice-over gives a finished 1080x1920 / 30 fps Short cut from moving official footage,
in one of several look themes, with word captions, a hook plate, a hero device, a phone-safe layout, a cover and a
sound-cue list.

```
python3 _pipeline/build.py <short>/edl.json --theme case-file          # render: silent + vo mp4, sfx cues, overlay log (~3.5 min)
python3 _pipeline/build.py <short>/edl.json --theme case-file --cover  # cover-<theme>.jpg from the edl's cover block (~5 s)
python3 _pipeline/build.py <short>/edl.json --theme vice-dusk --stills 0,1.4,19.6   # PNG frames in <short>/_stills; delete after
python3 _pipeline/build.py <short>/edl.json --words                    # caption word indices (break_before / highlight)
python3 _pipeline/check.py <short>/<name>-<theme>-silent.mp4 <short>/edl.json     # checks + contact sheets
python3 _pipeline/compare.py <short>/edl.json case-file panel-heist vice-dusk     # compare-3up.mp4, compare-sheet.jpg, boards
```

Run from the Shorts project folder (the one that holds `_pipeline/`, `_tools/`, `_fonts/`; `scripts/shorts-init.sh` creates it). The scripts need numpy and Pillow; when the calling python lacks them they re-run
themselves under `$SHORTS_HOME/venv/bin/python` (default `~/.shorts-studio`, made by `scripts/setup.sh`; override with `SHORTS_PY=...`).
Fonts: `_fonts/` (OFL, see `_fonts/SOURCES.md`); Anton/Inter for `classic` are in `_fonts/legacy/`.

## Files
- `shortkit.py` engine: EDL, exact-frame decoding, layout, pixel policy, image helpers, caption words/groups.
- `themes.py` looks: `classic`, `case-file` (Pack B), `panel-heist` (Pack A), `vice-dusk` (Pack C) from
  the original design research (not part of this kit). A theme owns fonts, palette, caption system, plates, the
  transition used for each cut role, grade/texture, the window frame and background, the hook and the hero device.
- `covers.py` cover builder; `build.py` render/cover/stills CLI; `check.py` verifier; `compare.py` review material.

## Pixel policy (enforced by check.py)
- `full` clips: 9:16 crop of a 4K or 2160-square source, at <= 1.0x source pixels (the 4K trailers' 2:1 picture is
  1920 px high, so there the crop is exactly 1080x1920 and can only pan; square and 16:9 4K clips can push in).
- `window` clips: 1080p sources at <= 1.25x (default zoom 1.25 into a 4:5 window about 900-1000 px wide, `1:1` for the
  letterboxed trailers). 720p sources at <= 1.0x only: keep them small or avoid them.
- Behind a window is the theme's designed background (dossier sheet, comic page, blue-orange light field), drifting
  slowly; never a black card.

## How a frame is made
1. ffmpeg decodes each clip from an exact frame (`-ss` just before it, `fps=30`, no audio).
2. Layout: `full` (crop, subpixel pan/push) or `window` (crop by `zoom`, theme frame on the theme background).
3. Cut transitions by role (`hook`, `triple`, `reveal`, `accent`), mapped per theme:

   | role | classic | case-file | panel-heist | vice-dusk |
   |---|---|---|---|---|
   | hook | whip | redact wipe | gutter slam | whip pan 1.6x |
   | triple | zoom | shutter cut | skew wipe | zoom through |
   | reveal | flash | shutter cut | flash frame (2 white) | light-leak sweep |
   | accent | cut | cut | cut | chromatic split |
   Hero freeze (`hero_freeze_at` on a clip): 0.2 / 0.25 (Freeze Verdict) / 0.3 (Freeze Pop) / none.
4. Theme grade (grain <= 8 %, vignette, look-specific colour), then hero graphics, hook plate, stars, captions, credit.
   Every text box of every frame is logged to `<silent>.overlay.json` for the safe-zone check.

Effect timings port HyperFrames registry components and the spec's CSS/GSAP values (same curves and durations)
as pure functions of time: `whip-pan-cut`, `zoom-through-transition`, `flash-through-white`, `beat-freeze-cut`,
`spring-pop`, `headline-slam`, `rgb-glitch-text`, `grain-overlay`; skew/gutter/redact/shutter/leak/chroma are hand-built
per the spec.

## Edit list reference (see the kit's `skills/shorts-pipeline/references/edl-template.json`)
Top level: `theme` (default when `--theme` is not given), `footage_root`, `vo`, `tail`, `out_silent`, `out_vo`,
`sfx_out` (use `{theme}` in names), `target_mb` (two-pass size target for the master, default 50), `sources`
{file: {picture: [x, y, w, h]}} for letterboxed files (for example a 4K file with bars `[0,120,3840,1920]`, a 16:9 file with bars `[0,108,1920,864]`).

Clip: `id`, `note`, `src`, `in` (source s of the first frame), `end` (timeline s of the cut out; the last clip runs to
the end), `layout` full|window, `transition` {role}. Full: `cw` (crop width, source px), `cx`, `cy`. Window: `aspect`
4:5|1:1 (case-file also takes `3:4`: a 900x1200 photo that grows upwards, bottom edge, exhibit label and credit stay put, +75 px of picture; needs a 1080p source at zoom 1.11-1.25, so no 720p or letterboxed trailers), `zoom` (output/source px), `cx`, `cy`. Each of cw/zoom/cx/cy takes a number, `[from, to]` (with `move_ease`,
`move_dur`) or keyframes `[[t, v], ...]`. Optional: `lift`, `speed`, `timemap` [[t, source_s], ...] (speed ramp,
nearest frame; `blend_frames` for low motion), `hero_freeze_at` (clip-local s), `exhibit` (case-file window label e.g. "GAME NAME · SIZZLE REEL"; without it the label is the source file name).

Captions: `words` (whisper json), `onset_fix` (snap words starting inside a pause to the real onset), `onset_override`
{word index: s} (for onsets whisper misplaces without a pause, e.g. "G.T.A. five"), `replace` (VI -> 6, V -> 5),
`break_before` (phrase breaks; each theme then cuts phrases into its own group size: 2 words panel-heist, up to 3
case-file/vice-dusk), `highlight` (key words, classic only; the other themes highlight the spoken word).

`hook` {end, lines, file, label, y (case-file only: top of the file tab, default 340; use about 1250 when a face sits under the default spot), circle [rx, ry, [[t, cx, cy], ...]], glass_label, hero_word}. `stars` {start, end,
labels [[t, text]], ticks (five pops), slam (sixth slot + star)}. `hero` {t, end, clip, detail_src (source px box the
case-file circle and punch target), label, glass_label, word, split {start, end, main, live, frozen, main_shift}}.
`credit` {text}. `sfx_extra` (hand cues merged into the cue list).

`cover` {src, t, cw, cx, cy (crop in source px, >= 1080 wide), headline, headline_wide (lines for wide display faces),
game, file, label, lead, word, circle (screen px), tab_y, stamp_y, plate_y, badge_y, game_y, game_size (case-file stamp, default 200; about 104 for CALL OF DUTY), upscale (true lets a 1080p trailer frame fill the cover from a crop down to 540 px wide: covers are seen as small thumbnails; the video itself keeps the pixel policy)}. `--cover` builds
`cover-<theme>.jpg` (q93, fails above 2 MB or with text outside the safe zone).

## Making the next Short (about 1.5-2 h)
1. Copy the kit's `skills/shorts-pipeline/references/edl-template.json` (a structural template) next to the new `vo/` (vo.wav, words.json); set `theme` and the clips.
2. `--words`; set `break_before`, `replace`; check onsets after pauses with
   `ffmpeg -i vo/vo.wav -af silencedetect=noise=-40dB:d=0.08 -f null -` and add `onset_override` where needed.
3. Pick footage you logged in `_footage/SOURCES.md`, find exact shot boundaries (frame-difference scan or
   a strip every 0.1 s). Watch for badges, burned-in subtitles, HUD prompts, editor bars and freeze-frames. Put cuts on pauses or just before key words; give the three or four big cuts a role.
4. Set `hook`, `stars`/`hero` (or drop them) and `cover`; `--stills` on risky moments; full build; `check.py`;
   `--cover`; look at every sheet and at single frames before handing it on.

check.py fails on: wrong size/fps/codec/duration, a clip above its pixel limit, identical frames longer than 0.3 s,
text outside the safe zone in any frame (phone zone for Shorts, title-safe zone for wide videos).

## Known limits
- whip16 / zoom / zoom15 scale the finished frame for a few transition frames under blur or flash (reported as INFO).
- The real HUD stars can only be punched to 1.25x (about 35 px per star): the drawn stars carry the moment.
- Render time is about 3.5 min per theme on this machine (2.5 min frames + two-pass encode).

## Long-form (16:9)
(The engine code `wide.py` and `longform.py` is part of the kit. The kit ships no long-form demo project and the long-form path is untested here; treat this section as a reference.)

A long video (9-10 min, 1920x1080, 30 fps) is a manifest of segments: cold open, case 01 ... case 10, outro. Each
segment is one edit list with `"format": "wide"` and its own voice-over, rendered on its own by `build.py` (theme
`case-file` in `wide.py`) and encoded with one fixed x264 parameter set, so `longform.py join` can glue the segments
with the concat demuxer without re-encoding. Rebuilding one segment never touches the others.

```
cd <long-form-project>
python3 ../_pipeline/longform.py status longform.json            # which segments are stale
python3 ../_pipeline/longform.py build longform.json [--only seg-01] [--force] [--jobs 3]
python3 ../_pipeline/longform.py join longform.json              # out/master-silent.mp4 + logs, cues, VO
python3 ../_pipeline/check.py seg-01-demo/seg-01-silent.mp4 seg-01-demo/edl.json   # one segment
python3 ../_pipeline/check.py out/master-silent.mp4 longform.json                  # the joined video
python3 ../_pipeline/build.py seg-01-demo/edl.json --stills 3.2,21 --out _style/tmp  # quick look
python3 ../_pipeline/build.py seg-01-demo/edl.json --cover      # 1280x720 thumbnail from "cover"
$SHORTS_HOME/venv/bin/python _tools/build_vo.py seg-01-demo/vo/beats.json
```
One 40 s segment takes about 4-5 min on this machine (frames ~5-6 fps + a 20 s x264 encode); `--jobs 3` builds
three segments at once, so ten cases plus cold open and outro take roughly 20-25 min, and one fix costs one segment.

`join` writes next to the master: `<master>.overlay.json` (every frame's text boxes plus the segment table),
`out/sfx-cues.json` (absolute times, each cue tagged with its segment), `out/master-vo.wav` (the voice-overs laid on
the master timeline, for the sound stage) and `out/master-vo-preview.mp4` (picture + voice only, not the mix). It
refuses to join segments whose H.264 parameter sets differ (rebuild them with the current pipeline).
Cue kinds the wide format adds (not yet in `sound/cue_map.json`): `case-card`, `verdict-slam`, `title-slam`,
`end-card`; it also uses the existing `marker-swipe`, `shutter-clack`, `whoosh-soft`, `stamp`, `tab-slide`,
`paper-slide`, `tab-type`, `typewriter-tick` (with `dur`) and `circle-draw`.

### Wide layout rules (enforced by check.py)
- Title-safe zone: all text inside x 96-1824 / y 54-1000 (the strip below stays free for YouTube's progress bar and
  subtitles) and nothing in the top-right 200x120 (info-card icon). Every graphic logs its boxes per frame.
- Type: nothing below 30 px (`wide.py` refuses smaller sizes), key text 80 px and more.
- `full` clips: 16:9 crop `cw` source px wide; 1080p sources push in to `cw` 1536 at most (1.25x), 4K sources
  to 3840 (1.0x). Letterboxed trailers: `sources` {file: {picture: [x, y, w, h]}} as for Shorts.
- `window` clips: evidence photo on the dossier sheet, `aspect` "16:9", `win_w` (default 1120), `win_cx` (700),
  `win_cy` (500), `zoom` output/source px (<= 1.25 for 1080p), `exhibit` label; the right third is free for `notes`.
- `decode_fps: "source"` reads every frame of 50/60 fps trailers, so 0.5x slow holds stay smooth; use speeds of
  0.3-0.6 to stretch 1-3 s trailer shots into 4-8 s holds.
- No word captions by default (subtitles are uploaded as a file); `"captions": {"enabled": true, "words": ...}`
  turns the case-file chips back on at the bottom of the safe zone.

### Still images and the dossier sheet (no footage)
- A clip whose `src` ends in .jpg/.jpeg/.png/.webp is a still (Steam screenshots). It takes the same `full` and
  `window` keys as video (`cw`/`cx`/`cy` or `zoom` as numbers, `[from, to]` or keyframes; `in`/`speed` are ignored)
  and the same pixel policy: 1080-high screenshots at most 1.25x (`cw` >= 1536), 720p at 1.0x.
- Stills always move. `float` (amplitude px, or {amp, period}) adds a slow two-axis camera float; stills default to
  12 px / 4.5 s, `"float": 0` turns it off (video clips: only when the key is given). In a `window`, a still also
  gets a desk camera: photo and dossier pages slide together, `desk` [[dx0, dy0], [dx1, dy1]] in output px over the
  clip (default [[-110, -60], [110, 60]]); keep the exhibit label inside the zone (check.py says when it is not).
- How much movement: check.py's still test needs a mean luma change of 0.6 per frame on its 27x48 blocks. Dark or
  smooth screenshots need about 60-100 px/s of travel at the output (a diagonal over most of the crop range in
  4-6 s, use `move_ease` "linear"; keyframes ease in and out and stall at every key). Keep the end points inside
  the picture for that `cw`, or the move stops against the edge. Under a quote or verdict (dimmed picture, plate
  covering a third of the frame) use the faster end, shorter holds, and `sway` on the plate.
- `"layout": "sheet"` with no `src`: the dossier pages themselves (2400x1350, grid, red rules, punch holes, faint
  redacted lines, no readable text), moved like a full-bleed still with `cw`/`cx`/`cy`. For stories where we have no
  footage of the game (e.g. Fortnite, Titanfall), with quote slips and notes on top.
- `sway` (px, default 0) on `quotes` and `verdict`: the plate floats slowly by that much (use 12-14 over stills).
- `card.drift` (px, default 0): the case-number type slides left by that much during the card (use ~90 over stills).
- `header` may be a list: a second lower third for a second game in the same case, `"tab": false`, `"credit": ""`.

### Wide edit-list keys
Top level: `format` "wide", `segment` {kind case|cold-open|outro, case, of}, `vo` (or `null` plus `duration` for a
silent segment), `tail`, `out_silent`, `out_vo`, `sfx_out`, `clips` (as for Shorts plus `decode_fps`, `win_*`,
`exhibit`, `tilt`). Graphics (times are segment seconds):
- `card` {end, kicker, stamp, stamp_t, stamp_x, stamp_y, wipe}: case-number card over ink-tinted moving footage,
  revealed by a redact wipe at `end`. Together with `out` this is the transition between cases.
- `out` {dur}: redact wipe to ink at the end of the segment (the next segment opens on its card).
- `header` {t, end, lt_end, lt_delay, game, sub, credit, kicker}: file tab "CASE 01 / 10" + lower third.
- `counter` {t, end}: small "CASE 01/10" chip top left; by default from the header's end to the segment's end.
- `source_plates` [{t, end, text, cps, y}]: mono "SOURCE: ..." typed on, bottom left.
- `quotes` [{t, end, text (<= 14 words), by, cps, x, y, tilt}]: typed quote on a torn paper slip; footage dims.
- `notes` [{t, end, title, lines, x, y, gap, tilt}]: index card beside a window clip, lines stamp in one by one.
- `circles` [{t, end, cx, cy, rx, ry, draw, width}]: red hand-drawn circle; cx/cy may be keyframes [[t, v], ...].
- `verdict` {t, end, lines (2-4 words), size, x, y, tilt}: rubber stamp slam with a 6-frame shake; footage dims.
- `cold_title` {t, end, kicker, lines (2), red (words in red), circle [line, word, t], ys, size}: cold-open promise.
- `end_card` {t, lines, sub, cta, stamp}: left-half sheet; keep `t` at least 15 s before the end; right half free.
- `cover` {src, t, crop [x, y, w, h] (16:9, >= 1280 source px wide), words, lines, game, tab, circle [cx, cy, rx,
  ry] (thumbnail px), text_side, text_w, text_y, game_x, game_y, game_size, out}: `--cover` writes a 1280x720 JPG
  (< 2 MB) and fails if text touches the edges or the duration badge (bottom-right 190x70).

### Making the next long video
1. Lay out a project: `longform.json` (the segment manifest, see `longform.py`), one `seg-NN-*/` folder per case with `edl.json`
   and `vo/beats.json`, plus `seg-00-cold-open` and `seg-99-outro` (end card in the last 15 s).
2. Put the source clips in `footage/<topic>/` (video only) and log them in `footage/SOURCES.md`; find shot boundaries
   with the scene filter command listed there.
3. Per segment: write `vo/beats.json` (lead silence for the case card, pauses where a quote or verdict needs reading
   time), run `_tools/build_vo.py`; read `vo/timings.json` and place clips and graphics on those times.
4. `--stills` on every graphic moment and look at them; then `longform.py build --jobs 3`, `check.py` per segment.
5. `longform.py join`, `check.py out/master-silent.mp4 longform.json`, `--cover` for the thumbnail; hand
   `out/master-silent.mp4`, `out/master-vo.wav` and `out/sfx-cues.json` to the sound stage.

## Sound
`$SHORTS_HOME/venv/bin/python _pipeline/sound/mix.py <short-folder> [--theme case-file] [--music trip-hop|the-chase|trap-suspense] [--no-whisper] [--strict]`
(about 25 s with the transcript check). Needs `vo/vo.wav`, `vo/words.json`, `sfx-cues-<theme>.json`, `*-<theme>-silent.mp4` and its `*-<theme>-silent.mp4.overlay.json` (cues for the red circle, tab and stamps are derived from it; without it the mix runs but warns and lacks them) in the folder; writes
`<name>-<theme>-final.mp4` (video copied, AAC 48 kHz stereo 192k) and `sound-report.txt` (LUFS and true peak of the decoded mp4, masking margins per word, whisper transcript vs script,
cue -> sample table, music credit, UNMAPPED cue kinds). Targets: -14 LUFS (+/-0.3 enforced by the loop), true peak <= -1.05 dBTP, voice peak -3 dBFS, music -18 dB under speech and -10 dB in gaps and the last 2 s, SFX bus -6 dB under speech.
- New cue kind: add one entry to `sound/cue_map.json` (layers of samples from `sound/sfx/`, gain, align, pitch); unknown kinds are listed in the report, `--strict` fails on them. Cues the editor does not list (red circle, exhibit stamp, file tab) are derived from the overlay log and `edl.json` (`derive` block in the same file).
- New sample: add a function to `sound/synth_sfx.py` and run it (all sounds are synthesised, nothing from games or sample packs).
- Music: `sound/music/music.json` (3 CC0 Freesound tracks, credits and licence copies in `music.md`); picked by `--music` or by folder number (01 trip-hop, 02 the-chase, 03 trap-suspense, 04 trip-hop ...).
- Credit line for the description comes from the report ("Music:" line); keep the Freesound URL.
