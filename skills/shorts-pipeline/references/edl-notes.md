# Edit list digest (start here, then read `_pipeline/README.md`)

`edl-template.json` in this folder is a structural template taken from a short that passed `check.py` (10 clips, 3:4 window). All
texts and file names are placeholders and the footage it names does not exist: replace every value. Captions can merge a prefix
with a following number into one token through `captions.join_prefix` (for example ["ACME"] makes "ACME 6" one caption token).
Copy it, keep its top level / `hook` / `captions` / `cover` / `credit` / `hero` shape and change the content. All paths in
it are relative to the folder that holds the edl (`"footage_root": ".."` = the project root; clip `src` starts with `_footage/`).

## Top level
`title`, `theme` (`case-file`, `panel-heist`, `vice-dusk` or `classic`; the profile picks one), `footage_root`, `vo` (`vo/vo.wav`), `tail` (0.6 s after the voice),
`out_silent` / `out_vo` / `sfx_out` (names with `{theme}`), `target_mb` (50), `sources` (picture override, below),
`captions`, `hook`, `hero`, `cover`, `credit`, `clips`.

## Clip keys that matter
| key | meaning |
|---|---|
| `id`, `note` | name and a one-line reason ("hook", "hero", what the shot shows) |
| `src`, `in` | source file (relative) and the source second of the first frame |
| `end` | TIMELINE second where the clip is cut away (the last clip runs to the end of the voice + tail) |
| `layout`: `window` | photo in the themed "case file" frame; `aspect` `"3:4"` = 900x1200 photo (recommended: more picture) |
| `zoom` | output px per source px: number, `[from, to]` (push) or keyframes; `cx`, `cy` = crop centre in source px (same forms) |
| `move_ease` | `"linear"` = constant speed (needed for frozen-still safety); default eases in and out |
| `speed` | 0.4-0.7 slow motion for short 60 fps shots; `decode_fps: "source"` keeps 60 fps smooth |
| `timemap` | speed ramp `[[t, source_s], ...]` |
| `float` | `{amp, period}` camera float in output px; sine, so it stalls at the turns (not a substitute for a push/pan) |
| `transition` | `{"role": "hook" | "triple" | "reveal"}` on the 3-4 big cuts (case-file: redact wipe / shutter / shutter) |
| `exhibit` | label under the photo (for example "SUBJECT · PLAYER CLIP"; default: the file name), must be true |

Window geometry: the photo is 900 px wide; the crop is `900/zoom` x `1200/zoom` source px. Minimum zoom that still fills the
window is `max(900/width, 1200/height)` (4K: 0.556; 2048x1152: 1.042). `check.py` prints each clip's scale and limit
(4K <= 1.00, 1080p <= 1.25, 720p <= 1.0). The crop is clamped to the picture: a float or pan that would leave it just stops.

## Picture override (`sources`)
`"sources": {"_footage/x/clip.mp4": {"picture": [x, y, w, h]}}` tells the engine which part of a file is the real picture
(letterbox bars, a creator banner, a minimap strip, a watermark corner). Everything is cropped from that rectangle.

## Captions and words
`captions.words` is a whisper json (`vo/words.json`, or a copy `vo/words-captions.json` with token fixes: merge the
pieces of one name into one token, fix a name read as two words, "90" -> "ninety"; keep whisper's start/end, merging takes the
start of the first and the end of the last). `break_before` = word indices where a new 2-3 word phrase starts;
`python3 _pipeline/build.py <edl> --words` prints the indices. `onset_fix: true` snaps words after pauses to the real onset.

## Hook, hero, cover, credit
- `hook` {end 2.9-3.2, y 1170, lines [2 lines], file "SERIES 04", label "SUBJECT"}: plate on from frame 0.
- `hero` {t, end, clip, detail_src [x0, y0, x1, y1] (corners, not x/y/w/h), label (2-3 words), word}: red circle on the
  key detail while the word is spoken; the label names only what the frame shows.
- `cover` {src, t, cw 600-1215, cx, cy, upscale true, headline [2 lines], game, game_size, file, label, circle
  [cx, cy, rx, ry] in cover px, tab_y, stamp_y}. The cover is a full-bleed 1080x1920 crop of ONE source frame
  (`cw` x `cw*1920/1080` source px), so with `cw` near the frame height only x moves. The plate sits at `tab_y` (330) and
  the stamp at `stamp_y` (1390); if the subject is near the top set `tab_y` ~1090 and `stamp_y` ~410. `--cover` fails on
  text outside the safe zone or a file above 2 MB.
- `credit` {text}: "Clips: <creators actually used>" (short names fit the safe zone).

## What check.py fails on
Wrong size/fps/codec/duration, a clip above its pixel limit, identical frames for more than 0.3 s (mean luma change < 0.6 on
a 27x48 grid, frame to frame), a cut next to a still picture, any text outside the phone safe zone. It writes contact sheets
(`*-check-0N.jpg`): look at all of them.
