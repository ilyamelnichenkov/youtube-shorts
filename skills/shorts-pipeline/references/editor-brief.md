# Editor brief: one vertical short (1080x1920, tall 3:4 window)

You edit ONE short for the channel described in `CHANNEL.md` (read it first: its content, footage and look rules override this brief). Your job: its `edl.json`, a full render, a cover,
`check.py` passing and an honest report. The main session reviews every frame afterwards and does the sound mix.
(Fill the placeholders in the "Per Short" table below before handing this over.)

## Inputs (already final, do not change)
- `<short>/vo/vo.wav`, `vo/timings.json` (beats with start/end), `vo/words.json` (whisper word timings: keys `w`, `s`, `e`).
  Never re-render the voice. Fix whisper tokens in a copy `vo/words-captions.json` (keep start/end; merging two tokens takes
  the start of the first and the end of the second), then set `break_before` in the edl.
- The script section of your short (what each line means, its sources, what must not be implied).
- Engine: `_pipeline/` (read `_pipeline/README.md` and the kit's `edl-notes.md`). Do not edit engine files; if the engine blocks
  you, say so in the report.
- Template: `edl-template.json` (copy its top level, `hook`, `captions`, `cover`, `credit` and `hero`).

## Footage
- Only `_footage/<topic>/`, logged in `_footage/SOURCES.md` (creator, title, url). Another section of the same player's video:
  `$SHORTS_HOME/venv/bin/python _tools/grab.py <topic> '<url>' <start> <end> --tag <name>` (quote the URL).
- To search without downloading: `_tools/ytdl.sh --flat-playlist --print "%(id)s | %(uploader)s | %(duration)s | %(title)s" "ytsearch10:<query>"`.
  Prefer 2160p/1440p videos with no facecam or overlays. Follow the footage policy in `CHANNEL.md`; never use leaks, paid content or someone's commentary or music audio.
- Reject 640x360 files. Look at footage first (contact sheets, shot boundaries; see the kit's SKILL.md).
- Every clip gets a true `"exhibit"` label (for example "<SUBJECT> · PLAYER CLIP" or "<SUBJECT> · OWN RECORDING").

## Content rules (defaults; `CHANNEL.md` adds its own; any one broken = the short is rejected)
- No blood, gore, corpses, wounds, kills, weapons pointed at people, no violence in the first 3 seconds or on the cover.
- No creator text in any frame: titles, subtitles, watermarks, channel logos, stylised banners, "subscribe" boxes. The game's own
  small HUD is allowed only if unreadable; crop the minimap with `sources` picture overrides or the window position.
- Nothing on screen that the channel's rules forbid (spoilers, story titles, private data ...).
- People and characters: frame on the place, the object or the face and action; never crop or push in on a body, never hold a shot
  on a back or legs, cut away quickly; follow the profile's rules.
- Nothing on screen claims more than the script says; every picture is what its label says it is.

## Edit rules
- Frame 0 is a striking moving shot with the hook plate on from the first frame (`"y": 1170`); hold 2.6-3.2 s.
- A cut every 1.5-3 s, on pauses or just before a key word. Give the three or four big cuts a transition role (`hook`, `triple`, `reveal`).
- Every shot moves, at CONSTANT speed (`"move_ease": "linear"`): a push (`zoom` [from, to]) or a pan (`cx` [from, to]).
  Static menus and flat screens need the strongest motion (see `lessons.md`).
- One `hero` moment: a red hand-drawn circle on the key detail with a 2-3 word label naming only what the frame shows.
- Captions: 2-3 word phrases by meaning; names stay together.
- The last shot cuts cleanly back into the first frame. `credit` lists only the creators you used.
- Cover: `cover` block with `"upscale": true`, one strong frame, a red circle on the key detail, `headline` = the hook lines,
  `game` stamp (the topic name); `--cover` must report `safe-zone violations: none`; check it at 180 px wide.

## Definition of done
1. Full render, then `check.py` prints `ALL CHECKS PASS` with no change to its rules. Re-render after your LAST edit.
2. `--cover` reports `safe-zone violations: none`.
3. You looked at every contact sheet and at single frames of the hook, the hero, each cut and the cover.
4. Short report: clip list (id, source, in, timeline end, what it shows, exhibit label), hero position and label, token fixes,
   extra downloads, what you could not find or are unsure about, paths of the silent mp4, vo mp4, sfx cues, cover and check log.
   Do NOT run the sound mix and do not touch other Shorts' folders.
5. One render at a time; other renders may be running, so a render can take 10+ minutes. Kill nothing you did not start.

## Per short (fill in)
| Folder | Hook lines | file / label | Hero (line and idea) | Credit |
|---|---|---|---|---|
| `<short>` | LINE 1 / LINE 2 | SERIES 01 / SUBJECT | "<spoken line>" (about 9-13 s): circle on <detail>, label <TWO WORDS> | Clips: <creators> |
