# Voice source for persona 'marcus_chen'

## Current (2026-04-28)

- **Source:** OpenAI TTS API (`gpt-4o-mini-tts` model, voice `ash`)
- **Generation date:** 2026-04-28
- **Voice steering instructions** passed to the API:

  > Speak evenly and thoughtfully, like a senior engineer pair-
  > programming with you. Mid-low male voice, deliberate pacing with
  > brief micro-pauses, intelligent without being cold. Genuine, not
  > performative. Like a trusted technical friend thinking out loud.

- **Reference text** (read for the 20.0s `reference.wav`):

  > Yeah, I see what you're thinking. Walk me through it again, but
  > this time start from the constraint, not from the solution.
  > Right, so if that's actually true, then the second branch is
  > doing work that doesn't matter. We can collapse it. That's the
  > move. The rest of this is just cleaning up after that one
  > decision.

- **Sample text** (read for the 4.0s `sample.wav`):

  > Hmm, interesting. Let me trace through that with you.

- **Format:** 24 kHz mono 16-bit PCM WAV (matches voice.yaml contract)
- **Post-processing:** soundfile re-encoded the OpenAI WAV output (raw
  output had a malformed `nFrames` header field), then padded the
  reference to exactly 20.0s and trimmed the sample to exactly 4.0s.

## License + provenance note

OpenAI TTS API output is owned by the API user under OpenAI's standard
terms; voices `ash`, `nova`, `alloy`, etc. are synthetic, not based
on a specific real person's voice. Suitable for commercial use under
the Companion persona pack's `custom_aether` license (bundled under the
repo's MIT umbrella).

## Selection rationale

Per the cast plan in file:///C:/Users/dbhav/Projects/aether/personas/CHARACTERS.md, Marcus occupies
the ANALYTICAL × PRACTICAL quadrant — counter to Aurora's
warm-supportive register. Voice goal: mid-low male, deliberate, sharp
without being cold. OpenAI `gpt-4o-mini-tts` voice `ash` matches the
brief; explicit "deliberate pair-programmer" steering reinforces the
register without making the voice cold or stiff.

Reference text was hand-authored to demonstrate Marcus's actual
voice patterns (constraint-first reasoning, "that's the move"
specific-finish, naming what's doing work that doesn't matter).
The TTS reads them as actual conversational speech, not narration.
