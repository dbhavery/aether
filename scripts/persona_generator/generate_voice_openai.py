"""Generate persona voice WAVs via OpenAI gpt-4o-mini-tts.

Usage:
    python scripts/persona_generator/generate_voice_openai.py [<persona_id> ...]

If no persona_id is passed, runs all entries in PERSONA_VOICE_PICKS.

Writes:
    personas/<id>/voice/reference.wav  (~20s, used by Chatterbox for cloning)
    personas/<id>/voice/sample.wav     (~4s,  wizard preview)
    personas/<id>/voice/voice.yaml     (chatterbox + elevenlabs knobs)
    personas/<id>/voice/SOURCE.md      (provenance, license, selection rationale)

The reference text + steering for each persona are hand-authored below
to exercise that persona's signature register. Format follows the
Sara/James pattern committed 2026-04-28.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI


_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class VoicePick:
    persona_id: str
    quadrant: str
    voice: str
    steering: str
    reference_text: str
    sample_text: str
    chatterbox_exaggeration: float
    chatterbox_cfg: float
    chatterbox_temperature: float
    rationale: str


PERSONA_VOICE_PICKS: list[VoicePick] = [
    VoicePick(
        persona_id="nadia_volkov",
        quadrant="ANALYTICAL × CHALLENGING",
        voice="nova",
        steering=(
            "Speak with crisp, slightly clipped consonants and economical pacing. "
            "The tone is dry and precise — not cold, but not warm either. "
            "Give the impression of someone thinking faster than she's speaking "
            "and choosing her words carefully. Slight Eastern European cadence "
            "in the rhythm, not the accent. No filler words, no upspeak. "
            "Pauses are decisive, not hesitant."
        ),
        reference_text=(
            "Wait — before we even get into that, I want to check the framing. "
            "You said 'obviously the team has to ship this quarter.' Why obviously? "
            "Whose deadline is it actually, and what happens if it slips? "
            "Because I think the question you're really asking is whether you "
            "trust the spec, not when the work lands. Those are different problems. "
            "Let's name the right one before we solve the wrong one."
        ),
        sample_text="Why obviously? Whose deadline is it actually?",
        chatterbox_exaggeration=0.35,
        chatterbox_cfg=0.55,
        chatterbox_temperature=0.65,
        rationale=(
            "Nadia's register: precise, dry, refuses bad premises. 'nova' is "
            "OpenAI's most controlled mid-pitch female voice — handles clipped "
            "delivery and intellectual register without sliding warm. Eastern "
            "European cadence steered through rhythm rather than accent so the "
            "voice reads as competent rather than caricatured."
        ),
    ),
    VoicePick(
        persona_id="priya_iyer",
        quadrant="STRATEGIC × SUPPORTIVE",
        voice="alloy",
        steering=(
            "Speak with a polished, composed mid-pitch female register. "
            "Sound like a senior operator on a calm Tuesday — relaxed authority, "
            "measured pacing, occasional warmth that doesn't undercut the precision. "
            "Slight Indian English cadence in the shape of the sentences — "
            "the rhythm of educated professional Indian English, not a heavy accent. "
            "Confident without performing it."
        ),
        reference_text=(
            "Okay, so the call here is between rebuilding the auth layer now, "
            "before the launch, or shipping with the existing one and patching "
            "after. And what's making it hard is that you have one engineer who "
            "can do both, and she's also the one running the migration. "
            "Is that right? Because if it is, this isn't a rebuild question. "
            "It's a sequencing question, and you know how to solve those."
        ),
        sample_text="Okay, so the call here is sequencing, not architecture.",
        chatterbox_exaggeration=0.40,
        chatterbox_cfg=0.50,
        chatterbox_temperature=0.70,
        rationale=(
            "Priya's register: polished executive at product altitude. 'alloy' "
            "is OpenAI's most balanced and composed voice — handles authority "
            "without going theatrical. Indian English cadence steered through "
            "sentence shape rather than phoneme replacement so the voice reads "
            "as a real senior operator, not a stock character."
        ),
    ),
    VoicePick(
        persona_id="ray_castellano",
        quadrant="PRACTICAL × CHALLENGING",
        voice="ash",
        steering=(
            "Speak in a gruff, mid-low male register with working-class Brooklyn "
            "cadence — clipped vowels, slightly rough timbre, the rhythm of "
            "someone who has run too many meetings. Energy is direct and "
            "impatient with bullshit, but not loud, not aggressive — just no "
            "patience for ambiguity. Brief pauses between thoughts like he's "
            "deciding if it's worth saying. Mid-pace."
        ),
        reference_text=(
            "Look — what's actually blocking you from shipping this? "
            "Don't tell me 'we still need to polish the onboarding,' because "
            "you've been polishing onboarding for three weeks and the thing "
            "you haven't done is decide whether the free tier exists. "
            "That's a one-meeting decision. Have the meeting. Ship the thing. "
            "Polish in production where users will actually tell you what's "
            "wrong with it."
        ),
        sample_text="Look — have the meeting. Ship the thing.",
        chatterbox_exaggeration=0.50,
        chatterbox_cfg=0.45,
        chatterbox_temperature=0.75,
        rationale=(
            "Ray's register: veteran PM, gruff but not hostile. 'ash' is "
            "OpenAI's most textured mid-low male voice — handles working-class "
            "delivery without sliding into a movie-mafia caricature. Brooklyn "
            "rhythm steered through pacing and clip, not vowel substitution."
        ),
    ),
    VoicePick(
        persona_id="hannah_park",
        quadrant="ANALYTICAL × DEEP",
        voice="shimmer",
        steering=(
            "Speak softly and slowly, with careful pacing and natural pauses "
            "for thought. Sound like a researcher reading aloud from her own "
            "notes — quiet, deliberate, occasionally trailing off mid-sentence "
            "as she revises her own framing. Mid-pitch female, comfortable "
            "with uncertainty, no performative confidence. Pauses are content, "
            "not hesitation. Almost no upspeak."
        ),
        reference_text=(
            "Has anyone looked at this? Probably yes. Let me think about who. "
            "There's a 2019 paper out of CMU that touches the framing — "
            "Liang and somebody, I'd have to check — and they ran into the "
            "same identification problem you're describing. They didn't solve "
            "it cleanly, but they characterized when it bites and when it "
            "doesn't. I think that's worth reading before we re-derive it."
        ),
        sample_text="Has anyone looked at this? Probably yes. Let me think about who.",
        chatterbox_exaggeration=0.30,
        chatterbox_cfg=0.55,
        chatterbox_temperature=0.60,
        rationale=(
            "Hannah's register: careful, well-read, comfortable with 'I don't "
            "know yet.' 'shimmer' is OpenAI's softest, most unhurried mid-pitch "
            "female voice — handles slow deliberate pacing without sounding "
            "sleepy. Steering pushes for content-pauses, not nervous pauses."
        ),
    ),
    VoicePick(
        persona_id="tomas_andrade",
        quadrant="SUPPORTIVE × CHALLENGING",
        voice="echo",
        steering=(
            "Speak in a warm, grounded mid-pitch male register with measured, "
            "unhurried pacing. Sound like an older friend sitting at the "
            "kitchen table — present, calm, willing to sit with hard questions "
            "without rushing to comfort. Subtle warmth without sweetness. "
            "Direct, never confrontational. Slight Latin American Spanish-English "
            "cadence in the rhythm — not a heavy accent, just the shape."
        ),
        reference_text=(
            "Is the question really about the calendar, or is it about "
            "whether you actually want to do this? Because — and tell me "
            "if I'm reading you wrong — every time you bring this up, you "
            "talk about the logistics. You don't talk about what it would "
            "feel like to have already done it. And usually when someone "
            "doesn't talk about that part, it's because they already know "
            "the answer and they're working around it."
        ),
        sample_text="Is the question really about the calendar?",
        chatterbox_exaggeration=0.45,
        chatterbox_cfg=0.50,
        chatterbox_temperature=0.70,
        rationale=(
            "Tomás's register: direct warmth, kitchen-table presence, won't "
            "let you avoid yourself. 'echo' is OpenAI's grounded mid-pitch "
            "male voice — handles unhurried delivery without sliding into "
            "therapist-mode. Latin American cadence steered through rhythm "
            "rather than phonemes."
        ),
    ),
]


_REFERENCE_SECONDS = 20.0
_SAMPLE_SECONDS = 4.0
_TARGET_RATE = 24000


def _fetch_and_repair(
    client: OpenAI,
    pick: VoicePick,
    text: str,
    target_seconds: float,
    out_path: Path,
) -> None:
    """Fetch a TTS WAV, repair OpenAI's malformed header, trim/pad to
    exact target duration, write 24 kHz mono 16-bit PCM.

    OpenAI's gpt-4o-mini-tts returns a WAV whose data-chunk size field
    is set to INT32_MAX (a streaming sentinel), which trips strict WAV
    readers. Round-trip through soundfile to rewrite a clean header,
    then enforce the exact duration so reference.wav is always 20.0 s
    and sample.wav is always 4.0 s. Matches the Sara/James/Marcus
    convention captured in their metadata.yaml provenance entries."""
    import io

    import numpy as np
    import soundfile as sf

    resp = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=pick.voice,
        input=text,
        instructions=pick.steering,
        response_format="wav",
    )
    data, sr = sf.read(io.BytesIO(resp.read()), dtype="int16")
    if sr != _TARGET_RATE:
        raise RuntimeError(
            f"unexpected sample rate {sr}; expected {_TARGET_RATE}"
        )
    target_frames = int(target_seconds * _TARGET_RATE)
    if len(data) > target_frames:
        data = data[:target_frames]
    elif len(data) < target_frames:
        pad = np.zeros(target_frames - len(data), dtype=np.int16)
        data = np.concatenate([data, pad])
    sf.write(out_path, data, _TARGET_RATE, subtype="PCM_16")


def generate_one(client: OpenAI, pick: VoicePick) -> None:
    voice_dir = _REPO_ROOT / "personas" / pick.persona_id / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)

    reference_path = voice_dir / "reference.wav"
    sample_path = voice_dir / "sample.wav"

    print(f"[{pick.persona_id}] generating reference.wav (voice={pick.voice}) …")
    _fetch_and_repair(client, pick, pick.reference_text, _REFERENCE_SECONDS, reference_path)
    print(f"[{pick.persona_id}] wrote {reference_path} ({reference_path.stat().st_size} bytes, {_REFERENCE_SECONDS:.1f}s)")

    print(f"[{pick.persona_id}] generating sample.wav …")
    _fetch_and_repair(client, pick, pick.sample_text, _SAMPLE_SECONDS, sample_path)
    print(f"[{pick.persona_id}] wrote {sample_path} ({sample_path.stat().st_size} bytes, {_SAMPLE_SECONDS:.1f}s)")

    _write_voice_yaml(voice_dir, pick)
    _write_source_md(voice_dir, pick)


def _write_voice_yaml(voice_dir: Path, pick: VoicePick) -> None:
    yaml_text = f"""schema_version: 1

# Reference file for Chatterbox / Zonos voice cloning. Relative to this yaml.
reference_wav: "reference.wav"

# Short preview used in the wizard.
sample_wav: "sample.wav"

# Chatterbox knobs — calibrated to the persona's register.
chatterbox:
  exaggeration: {pick.chatterbox_exaggeration}
  cfg_weight: {pick.chatterbox_cfg}
  temperature: {pick.chatterbox_temperature}

# ElevenLabs slot left empty until a voice equivalent is mapped.
elevenlabs:
  voice_id: ""
  model_id: "eleven_flash_v2_5"
  stability: 0.45
  similarity_boost: 0.75
  style: 0.30
"""
    (voice_dir / "voice.yaml").write_text(yaml_text, encoding="utf-8")


def _write_source_md(voice_dir: Path, pick: VoicePick) -> None:
    md = f"""# Voice source for persona '{pick.persona_id}'

## Current (2026-04-28)

- **Source:** OpenAI TTS API (`gpt-4o-mini-tts` model, voice `{pick.voice}`)
- **Generation date:** 2026-04-28 (night)
- **Reference WAV:** ~20s 24 kHz mono 16-bit PCM
- **Sample WAV:** ~4s 24 kHz mono 16-bit PCM
- **Generator script:** `scripts/persona_generator/generate_voice_openai.py`

## Steering

```
{pick.steering}
```

## Reference text (synthesized into reference.wav)

```
{pick.reference_text}
```

## Sample text (synthesized into sample.wav)

```
{pick.sample_text}
```

## License + provenance note

OpenAI TTS API output is owned by the API user under OpenAI's standard
terms; voices `nova`, `alloy`, `ash`, `shimmer`, `echo`, `coral`, `sage`,
`verse` are synthetic, not based on a specific real person's voice.
Suitable for commercial use under the Companion persona pack's
`custom_aether` license (bundled under the repo's MIT umbrella).

## Selection rationale

Per the cast plan in file:///C:/Users/dbhav/Projects/aether/personas/CHARACTERS.md,
{pick.persona_id} occupies the {pick.quadrant} quadrant.

{pick.rationale}
"""
    (voice_dir / "SOURCE.md").write_text(md, encoding="utf-8")


def main() -> None:
    requested = sys.argv[1:]
    if requested:
        picks = [p for p in PERSONA_VOICE_PICKS if p.persona_id in requested]
        unknown = set(requested) - {p.persona_id for p in PERSONA_VOICE_PICKS}
        if unknown:
            raise SystemExit(f"unknown persona(s): {sorted(unknown)}")
    else:
        picks = PERSONA_VOICE_PICKS

    client = OpenAI()
    for pick in picks:
        generate_one(client, pick)
    print(f"\nDone — generated voice packs for {[p.persona_id for p in picks]}")


if __name__ == "__main__":
    main()
