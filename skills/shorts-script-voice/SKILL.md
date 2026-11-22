---
name: shorts-script-voice
description: Plan a topic, write the script table (owner's language next to the video-language voice lines) for a vertical short-form video, record the voice with local Kokoro TTS, check it with whisper, and word the title. Use when choosing or writing a short, revising a script, or recording or re-recording a voice-over. Channel rules come from CHANNEL.md.
---

# Script and voice for a short (topic-neutral)

Read the project's `CHANNEL.md` first: audience, tone, languages, topic and fact rules, content rules, voice settings and the
closing-line rule all come from there and override the defaults below. Talk to the owner in the language the profile names.

## 1. Topic
- One claim per short, interesting or searchable for THIS audience, within the profile's content rules. Research it in a file:
  every claim marked verified / one source / unverified, with URL and the date checked. Open the primary page yourself for the
  claim that carries the video; never present a rumour as fact.
- Search-style titles: before a title is final, search the platform for identical or near-identical titles and report the closest
  matches (channel, views, age); propose a distinct variant if close duplicates exist.

## 2. Script file (`<short>/script.md`, or one file per batch)
A table with two columns: what is said in the owner's language (meaning) | the voice line in the video language. Below it:
the sources (outlet, date, URL, what each supports), a line "not said" (claims, motives, numbers left out on purpose), the big
on-screen text (hook lines and series tab) and the proposed title. Length: about 55-75 words per 20 s at speed 1.12.
Defaults for the text (the profile may override): full flowing sentences joined by connectives, who does what and where is clear,
every number and term explained, imperatives toward the viewer softened, one argument from hook to payoff. Show the script to the
owner the way the profile says and start production when the profile says to.

## 3. Voice (local Kokoro; voice, speed and language from the profile)
1. `<short>/vo/beats.json`: `{"lead": 0.0, "voice": "<voice>", "speed": 1.12, "lang": "<code>", "beats": [["hook", "text...", 0.3], ["id", "text...", pause_after_s], ...]}`.
   Spell numbers out. Write acronyms and brand names the way they are spoken. The last beat has pause 0. (`voice`, `speed` and
   `lang` may be left out: defaults are `am_puck`, 1.12, `en-us`; env `SHORTS_VOICE`, `SHORTS_SPEED`, `SHORTS_LANG` also work.)
2. `$SHORTS_HOME/venv/bin/python _tools/build_vo.py <short>/vo/beats.json` writes `vo/vo.wav` and `vo/timings.json`.
3. `$SHORTS_HOME/venv/bin/python _tools/words.py <short>/vo` writes `vo/words.json` (whisper word timings, language from `beats.json`).
4. Read the transcript in `words.json`. If whisper misheard a word, the listener may too: rephrase the line and re-record
   (sentence-initial "And", "So", "Load", acronyms and names are typical). If only the caption needs fixing (a name read as two
   words), fix it in `vo/words-captions.json` and leave the audio alone.
5. Trim a closing beat the owner dropped with `_tools/trim_last_beat.py` instead of re-recording everything.

## 4. Title and texts
Title in search form with the key words first. The description and tags come in the packaging step (skill `shorts-packaging`);
the question for the audience goes where the profile says (spoken line or pinned comment).

## Checks before you hand the script on
- One argument; every number explained; facts attributed; nothing the sources do not say; no spoilers if the profile forbids them.
- Spoken length matches the plan (`timings.json` total); the closing line follows the profile.
