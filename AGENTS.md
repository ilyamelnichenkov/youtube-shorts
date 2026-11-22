# Shorts Studio kit (instructions for an agent that opens this repository)

This is a plugin kit, not a video project. Do not render videos here. To make videos, create a project folder with
`scripts/shorts-init.sh <dir>` and work there (it has its own `AGENTS.md` and `CHANNEL.md`).

- Skills: `skills/shorts-script-voice`, `skills/shorts-pipeline`, `skills/shorts-packaging` (topic-neutral; the channel profile
  `CHANNEL.md` of the project holds everything specific to one channel).
- Engine: `engine/_pipeline` (Python + ffmpeg), tools in `tools/`, setup in `scripts/setup.sh`, check in `scripts/doctor.sh`.
- When you change the engine, keep it topic-neutral and re-run an A/B: render the same stills with the old and new engine and
  compare pixels. Update `README.md` (Russian) and the skill that describes the behaviour.
