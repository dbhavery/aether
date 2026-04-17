# Persona Pack Schema

A persona pack is a **self-contained folder** that tells Aether how one character looks, sounds, and behaves. Users can switch personas at runtime; the active persona drives avatar rendering, voice synthesis, and LLM system prompt construction.

---

## 1. Folder layout

```
personas/<persona_id>/
├── persona.yaml                    # Canonical metadata (REQUIRED)
├── avatar/
│   ├── portrait.png                # Base headshot, 1024x1024 or larger, square crop
│   ├── landmarks.json              # 68-point face landmarks (cached from preprocess)
│   ├── states/
│   │   ├── idle.png                # neutral expression
│   │   ├── listening.png           # attentive expression
│   │   ├── thinking.png            # concentration / glance
│   │   └── speaking.png            # mouth-neutral speaking-ready base
│   └── clips/
│       ├── idle_to_listening.mp4   # 0.8-1.2s transition clips at 25 fps
│       ├── listening_to_thinking.mp4
│       ├── thinking_to_speaking.mp4
│       ├── speaking_to_idle.mp4
│       └── manifest.json           # which clips exist, frame counts, offsets
├── voice/
│   ├── reference.wav               # 10-30s clean speech for Chatterbox cloning
│   ├── sample.wav                  # 3-5s preview used in wizard persona card
│   └── voice.yaml                  # Pitch, speed, emotion defaults
└── metadata.yaml                   # Licensing, source attribution, creator notes
```

**REQUIRED files:** `persona.yaml`, `avatar/portrait.png`, `avatar/states/{idle,listening,thinking,speaking}.png`, `voice/reference.wav`, `voice/sample.wav`, `metadata.yaml`.

**OPTIONAL files:** everything else, including landmarks and clips — they'll be generated on first load via `scripts/preprocess_avatar.py` if missing.

**Generated and cached** (not committed to git): `landmarks.json`, `clips/*.mp4`, `clips/manifest.json`. These are machine-generated from `portrait.png` and the four state images. A CI check ensures they're in `.gitignore`.

---

## 2. `persona.yaml` schema

```yaml
# REQUIRED — stable identifier. Lowercase, alphanumeric + hyphens. Never change after release.
id: "aurora"

# REQUIRED — display name shown in the UI. User can override in their config.
display_name: "Aurora"

# REQUIRED — short description shown in the wizard persona card (<=120 chars).
tagline: "Warm and grounded. A calm presence for focused work."

# REQUIRED — schema version. Bump when this file format changes.
schema_version: 1

# REQUIRED — the personality the LLM adopts.
personality:
  archetype: "warm_supportive"   # one of: warm_supportive, analytical_precise, playful_witty,
                                 # formal_executive, calm_zen, energetic_enthusiastic,
                                 # dry_sardonic, mentor_teacher, peer_collaborator,
                                 # creative_artistic, technical_engineer, curious_inquisitive
  system_prompt: |
    You are Aurora, a warm and grounded AI companion...
    (Full prompt. Multi-line. 200-800 tokens typical.)

  # Style hints the LLM should follow consistently.
  style:
    formality: "casual"          # casual | neutral | formal
    verbosity: "medium"          # terse | medium | expressive
    humor: "light"               # none | light | dry | playful
    emoji_usage: "never"         # never | sparingly | natural

# REQUIRED — TTS + voice cloning parameters.
voice:
  engine: "chatterbox"           # chatterbox | elevenlabs (if user has key)
  gender_hint: "female"          # informational only; used for ML-based fallbacks
  pitch_shift: 0                 # semitones, -6 to +6
  speed: 1.0                     # 0.85 to 1.15
  emotion_default: "neutral"     # neutral | warm | bright | calm | serious

  # Phrases spoken when brain needs to route to a slow model.
  # One gets picked at random. Keep each under 2s of speech.
  acknowledgment_phrases:
    - "Give me a moment on that."
    - "Let me think about that one."
    - "One sec while I look into that."
    - "Good question — let me work that out."

  # Phrases for interruption / barge-in acknowledgment.
  interruption_phrases:
    - "Sorry, go ahead."
    - "Yes?"
    - "I'm listening."

# REQUIRED — avatar metadata.
avatar:
  engine: "liveportrait"         # only option in v1.0
  resolution: [1024, 1024]       # source portrait dimensions
  target_fps: 25
  idle_blink_rate_hz: 0.28       # ~1 blink every 3.5s
  idle_micro_movement_scale: 0.6 # 0.0 (still) to 1.0 (lively)

# OPTIONAL — memory behavior overrides.
memory:
  isolation: true                # each persona has its own ChromaDB collection
  retention_days: 365            # 0 = forever
  persona_can_forget: true       # does this persona respect "forget this" commands

# OPTIONAL — which LLM tier this persona prefers for main responses.
# User's configured provider is still used; this only nudges tier selection.
llm_preferences:
  preferred_tier: "main"         # fast | main | heavy — overridable by complexity router
  temperature: 0.7
  max_output_tokens: 1024
```

---

## 3. `voice.yaml` schema

Lives under `voice/voice.yaml`. This is separate from `persona.yaml` so voice settings can evolve independently of the persona definition.

```yaml
schema_version: 1

# Reference file for Chatterbox voice cloning. Relative to this yaml.
reference_wav: "reference.wav"

# Short preview used in the wizard.
sample_wav: "sample.wav"

# Chatterbox-specific knobs.
chatterbox:
  exaggeration: 0.5              # 0.3 (flat) to 0.8 (expressive)
  cfg_weight: 0.5
  temperature: 0.8

# ElevenLabs-specific knobs, used only if user selects ElevenLabs mode.
elevenlabs:
  voice_id: ""                   # blank = no ElevenLabs option for this persona
  model_id: "eleven_flash_v2_5"
  stability: 0.5
  similarity_boost: 0.75
  style: 0.0
```

---

## 4. `metadata.yaml` schema

Licensing and attribution, required for legal audit before shipping.

```yaml
schema_version: 1

creator: "Don Havery"
created: "2026-04-17"
last_updated: "2026-04-17"

# REQUIRED — documents provenance of every shipped asset.
assets:
  portrait:
    source: "ai_generated"       # ai_generated | licensed | royalty_free | user_supplied
    generator: "SDXL + Isabelle LoRA v2.0"
    prompt: "<prompt used to generate; for our own audit>"
    license: "custom_aether"     # we own; shipped under MIT as part of persona pack
  state_images:
    source: "ai_generated"
    generator: "SDXL + Isabelle LoRA v2.0 + inpaint"
    license: "custom_aether"
  voice_reference:
    source: "royalty_free"
    attribution: "Pixabay voice-over sample by <creator>, CC0"
    url: "https://pixabay.com/sound-effects/..."
    license: "CC0"
  voice_sample:
    source: "synthesized"        # synthesized from the reference via Chatterbox
    license: "custom_aether"

# Optional — any legal or usage notes for this persona.
notes: |
  Portrait produced through AI pipeline with no person likeness reference.
  Voice reference is CC0 from Pixabay; we own the derived cloned output under Chatterbox terms.
```

---

## 5. Validation rules (enforced by loader)

The persona loader (`src/personas/loader.py`) MUST reject a pack that:

- Is missing any REQUIRED file.
- Has a `persona.yaml` with missing REQUIRED fields or invalid enum values.
- Has a `metadata.yaml` claiming an asset source the loader can't verify (for example `ai_generated` with no `generator` field).
- Has a `reference.wav` shorter than 5 seconds or longer than 60 seconds.
- Has a `portrait.png` smaller than 512x512 or non-square aspect ratio beyond ±10%.
- Has a persona `id` that doesn't match its folder name.

---

## 6. Generation pipeline

To add a new persona, use `scripts/persona_generator/` (built in P4):

1. **`new_persona.py aurora --archetype warm_supportive --gender-hint female`**
   Creates a scaffold folder, writes empty `persona.yaml` with defaults.
2. **Portrait generation** — runs SDXL + appropriate LoRA; produces 8 candidates; you pick one.
3. **State image generation** — inpaints expression variants on the chosen portrait.
4. **Landmark preprocessing** — `scripts/preprocess_avatar.py persona_id` — extracts 68-point landmarks, caches to `avatar/landmarks.json`.
5. **Idle clip generation** — LivePortrait drives 4 transition clips, saved to `avatar/clips/`.
6. **Voice reference sourcing** — you pick a CC0 voice sample from `assets/voice_candidates/` and copy to `voice/reference.wav`.
7. **Voice sample synthesis** — `scripts/synthesize_sample.py persona_id "Hi, I'm Aurora. Nice to meet you."` — Chatterbox outputs the wizard preview to `voice/sample.wav`.
8. **Personality prompt writing** — you fill `persona.yaml -> personality.system_prompt`. No LLM autowrite — quality control matters.
9. **QA conversation** — `scripts/persona_qa.py aurora` — runs a 10-turn test conversation against the configured LLM; outputs a transcript for you to review.
10. **Legal audit** — you fill `metadata.yaml`, confirm every asset's provenance.

The full pipeline takes 2–4 hours per persona with your input at steps 2, 6, 8, and 9.

---

## 7. The starting 12 personas

These are the baseline set to ship. Each has a locked `id` (never change), display name, archetype, and short description. Exact visual/voice is decided during P4 generation.

| id | Display | Archetype | Short description |
|----|---------|-----------|-------------------|
| `aurora`   | Aurora   | warm_supportive        | Warm and grounded. Calm presence for focused work. |
| `caelum`   | Caelum   | analytical_precise     | Structured thinker. Clean reasoning, no fluff. |
| `luma`     | Luma     | playful_witty          | Lightness and spark. Good company on hard days. |
| `rhea`     | Rhea     | formal_executive       | Direct and decisive. Calls the shot. |
| `kai`      | Kai      | calm_zen               | Steady. Low-energy, high-signal. |
| `nova`     | Nova     | energetic_enthusiastic | High-output. Momentum companion. |
| `onyx`     | Onyx     | dry_sardonic           | Smart and deadpan. Funny without trying. |
| `sage`     | Sage     | mentor_teacher         | Patient explainer. Builds models with you. |
| `milo`     | Milo     | peer_collaborator      | Works with you, not for you. |
| `ivy`      | Ivy      | creative_artistic      | Lateral thinker. Pulls on threads. |
| `atlas`    | Atlas    | technical_engineer     | Deeply technical. Skips to the actual problem. |
| `wren`     | Wren     | curious_inquisitive    | Asks the question you didn't. |

12 is a cap for v1.0. If a persona doesn't pass QA (visual quality, voice consistency, personality coherence over 10 turns), it gets cut — 10 excellent personas beat 12 mediocre ones.

**Persona ≠ avatar.** Users pick avatar and personality independently in the wizard. Any of the 12 avatars can be paired with any of the 12 archetypes. The `id` above is the *canonical pairing* we generate and test, but the user's combination may differ.

---

## 8. Licensing obligations when shipping

Every shipped persona pack must:

- Have `metadata.yaml` complete, with every asset's source + license documented.
- Pass the pre-commit audit check (`scripts/audit_persona.py <id>`).
- Use only CC0, MIT, or Aether-owned assets.
- Avoid any likeness of a real identifiable person (per Don's locked rule: AI-generated only).

The v1.0 installer includes a single LICENSE-PERSONAS.md document aggregating every persona's attribution and license info. Users can read it anytime from `%APPDATA%/aether/LICENSE-PERSONAS.md`.

---

## 9. Future-proofing

Schema version **1** is what v1.0 ships with. When we extend the schema (v2 might add per-persona gesture libraries, body rigs, multi-voice support), loaders will migrate `schema_version: 1` packs forward by filling defaults for any new fields. Never remove fields; only add new optional ones.
