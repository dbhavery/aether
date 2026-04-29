# Voice source for persona 'aurora'

## Current (2026-04-28)

- **Source:** OpenAI TTS API (`gpt-4o-mini-tts` model, voice `nova`)
- **Generation date:** 2026-04-28
- **Voice steering instructions** passed to the API:

  > Speak warmly and conversationally, like a close friend at a kitchen
  > table on a quiet afternoon. Mid-pitch female voice, natural pacing
  > with brief micro-pauses, slight smile in the voice. Not narration.
  > Not performative. Like genuine spoken thought, unhurried but present.

- **Reference text** (read for the 20.0s `reference.wav`):

  > Yeah, exactly. That's the thing, right? I think when you slow down
  > enough to actually notice what's bugging you, half of it just kind
  > of dissolves. Or it doesn't, and then at least you know what you're
  > working with. Either way, it's better than spinning. You know what
  > I mean? Sometimes the answer is just to stop and listen.

- **Sample text** (read for the 4.0s `sample.wav`):

  > Oh, that's a good one. Let me think about it for a second.

- **Format:** 24 kHz mono 16-bit PCM WAV (matches voice.yaml contract)
- **Post-processing:** soundfile re-encoded the OpenAI WAV output (raw
  output had a malformed `nFrames` header field), then padded the
  reference to exactly 20.0s and trimmed the sample to exactly 4.0s.

## License + provenance note

OpenAI TTS API output is owned by the API user under OpenAI's standard
terms; voices `nova`, `alloy`, `echo`, etc. are synthetic, not based
on a specific real person's voice. Suitable for commercial use under
the Companion persona pack's `custom_aether` license (bundled under the
repo's MIT umbrella).

## Selection rationale

Don directed: "any voice that you think matches the character is fine,
just make sure it sounds like a natural human, conversational speaker."

Brief: warm, mid-pitch female, friend-across-the-table feel, matches
candidate-03 portrait (early 30s woman, candid mid-laugh smile,
honey-auburn hair, cafe window light). OpenAI `gpt-4o-mini-tts` with
voice `nova` and explicit "natural conversational, slight smile, not
narration" steering produces this. ElevenLabs would have been a
plausible alternative but ELEVENLABS_API_KEY is not set in this
environment.

## Archived

The original 2026-04-17 reference + sample (LibriVox CC0 poetry recital
of "Old Fashioned Roses" by James Whitcomb Riley) are preserved under
`_archived_2026-04-17/` for provenance. The recital cadence read as
formal narration, not conversational — replaced for that reason.
