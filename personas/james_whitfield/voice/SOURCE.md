# Voice source for persona 'james_whitfield'

## Current (2026-04-28)

- **Source:** OpenAI TTS API (`gpt-4o-mini-tts` model, voice `sage`)
- **Generation date:** 2026-04-28 (evening)
- **Reference WAV:** 20.0s 24 kHz mono 16-bit PCM
- **Sample WAV:** 4.0s 24 kHz mono 16-bit PCM

**Steering / reference text recovery pending.** Voice generation
happened during the 2026-04-28 night session before the schema-redesign
landed. The exact steering instructions and reference text are in the
session-log artifacts; they need to be recovered and written here
before this persona ships in a release. The WAVs themselves are
committed canonically and unblock downstream voice-cloning work.

## License + provenance note

OpenAI TTS API output is owned by the API user under OpenAI's standard
terms; voices `sage`, `nova`, `ash`, `coral`, etc. are synthetic, not
based on a specific real person's voice. Suitable for commercial use
under the Companion persona pack's `custom_aether` license (bundled
under the repo's MIT umbrella).

## Selection rationale

Per the cast plan in file:///C:/Users/dbhav/Projects/aether/personas/CHARACTERS.md,
James occupies the PRACTICAL × SUPPORTIVE quadrant — counter to Aurora's
warm-engaged register. Voice goal: unhurried mid-low male, comfortable
with silence, unforced warmth, weathered without being mournful. OpenAI
`gpt-4o-mini-tts` voice `sage` matches the brief.
