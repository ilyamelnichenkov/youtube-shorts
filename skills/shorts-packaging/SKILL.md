---
name: shorts-packaging
description: Package a finished, sound-mixed short-form video for upload - file and cover naming and numbering in ready/, the upload block (search-style title, description with sources and credits, tags, pinned comment), the schedule in the owner's timezone, and moving uploaded work to published/. Use right after the sound mix or when the owner reports an upload. Channel rules come from CHANNEL.md.
---

# Packaging a finished video (topic-neutral)

Read `CHANNEL.md`: folder names, label language, credit and disclaimer lines, timezone and slots, music credit rules.

## Folder rules (`ready/<direction>/`; names come from the profile)
- Finished, not yet uploaded files lie flat in the folder, numbered in upload order INSIDE that folder (01, 02, ...); a new video
  takes the next free number (a global production number does not matter). One `UPLOAD.md` per folder holds all blocks.
- Names: `<NN>-<slug>.mp4` (the `*-final.mp4` from the mix) and `<NN>-<slug>-cover-vertical.jpg` (JPG under 2 MB).
- When the owner says a video is uploaded or scheduled: move its files to `published/` and delete its block and schedule row;
  never renumber the others.

## Steps
1. Copy `<short>/<name>-<theme>-final.mp4` and `<short>/cover-<theme>.jpg` into `ready/<folder>/` under the new names.
2. Measure: `ffprobe -v error -show_entries format=duration -of csv=p=0 <file>`, size in MB, and the LUFS line from
   `sound-report.txt`. Put the real numbers into the block (do not copy them from the previous block).
3. Write the block from `references/upload-block-template.md`:
   - Title in search form, key words first, no promise the video does not deliver.
   - Description: the first sentence repeats the query words; 2-4 sentences of facts exactly as the voice says them, attributed;
     "Sources, checked <date>" with URLs; one line about what sources disagree on and that the video leaves it out; the clip
     credit and the disclaimer lines from the profile; the music credit (author, title, licence, URL) from `sound-report.txt`;
     3-5 hashtags; the question for the audience at the end of the text.
   - Tags: about 10, comma separated. Pinned comment: the same question.
   - A "caveat" row for a single-source fact, a sensitive topic (the platform decides age restriction and ads: say so), or
     footage that is honest b-roll rather than the thing named.
4. Add the row to the schedule table. Suggested slots are in the owner's timezone from the profile; use `TZ=<zone> date`
   for "today" (the machine clock may be on another zone).
5. Related video: the newest public long video on the same subject, if any.
6. Final check: the file plays (ffprobe), the cover is 1080x1920 and readable at 180 px, no placeholder is left in the block
   (`grep -n "<" UPLOAD.md`), every URL was copied from the research or footage log, not typed from memory.

## Reporting to the owner
In the owner's language: what is now in `ready/`, the suggested slots, anything not verified or honest b-roll, and the one
decision you need if any. Connected sentences, not telegraph lists; file names and numbers stay exact.
