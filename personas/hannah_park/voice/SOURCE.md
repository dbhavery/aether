# Voice source for persona 'hannah_park'

## Current (2026-04-28)

- **Source:** OpenAI TTS API (`gpt-4o-mini-tts` model, voice `shimmer`)
- **Generation date:** 2026-04-28 (night)
- **Reference WAV:** ~20s 24 kHz mono 16-bit PCM
- **Sample WAV:** ~4s 24 kHz mono 16-bit PCM

## Steering

```
Speak softly and slowly, with careful pacing and natural pauses for thought. Sound like a researcher reading aloud from her own notes — quiet, deliberate, occasionally trailing off mid-sentence as she revises her own framing. Mid-pitch female, comfortable with uncertainty, no performative confidence. Pauses are content, not hesitation. Almost no upspeak.
```

## Reference text (synthesized into reference.wav)

```
Has anyone looked at this? Probably yes. Let me think about who. There's a 2019 paper out of CMU that touches the framing — Liang and somebody, I'd have to check — and they ran into the same identification problem you're describing. They didn't solve it cleanly, but they characterized when it bites and when it doesn't. I think that's worth reading before we re-derive it.
```

## Sample text (synthesized into sample.wav)

```
Has anyone looked at this? Probably yes. Let me think about who.
```

## License + provenance note

OpenAI TTS API output is owned by the API user under OpenAI's standard
terms; voices `nova`, `alloy`, `ash`, `shimmer`, `echo`, `coral`, `sage`,
`verse` are synthetic, not based on a specific real person's voice.
Suitable for commercial use under the Companion persona pack's
`custom_aether` license (bundled under the repo's MIT umbrella).

## Selection rationale

Per the cast plan in file:///C:/Users/dbhav/Projects/aether/personas/CHARACTERS.md,
hannah_park occupies the ANALYTICAL × DEEP quadrant.

Hannah's register: careful, well-read, comfortable with 'I don't know yet.' 'shimmer' is OpenAI's softest, most unhurried mid-pitch female voice — handles slow deliberate pacing without sounding sleepy. Steering pushes for content-pauses, not nervous pauses.
