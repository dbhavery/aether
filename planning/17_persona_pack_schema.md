# 17 — Persona Pack Schema

A persona pack is a **self-contained folder** that tells Aether how one character looks, sounds, and behaves. Users switch personas at runtime; the active persona drives avatar rendering, voice synthesis, and LLM system prompt construction.

Ported and generalized from v1.0 `PERSONA-SCHEMA.md` — engine-specific names (LivePortrait, Chatterbox, ChromaDB) replaced with the new plan's engine-agnostic references.

---

## Folder layout

```
personas/<persona_id>/
├── persona.yaml                    # Canonical metadata (REQUIRED)
├── avatar/
│   ├── portrait.png                # Base headshot, 1024x1024+, square crop
│   ├── landmarks.json              # 68-point face landmarks (cached, generated)
│   ├── states/
│   │   ├── idle.png                # neutral expression
│   │   ├── listening.png           # attentive expression
│   │   ├── thinking.png            # concentration / glance
│   │   └── speaking.png            # speaking-ready neutral
│   └── clips/
│       ├── idle_to_listening.mp4   # 0.8–1.2s transition clips at 25 fps
│       ├── listening_to_thinking.mp4
│       ├── thinking_to_speaking.mp4
│       ├── speaking_to_idle.mp4
│       └── manifest.json
├── voice/
│   ├── reference.wav               # 10–30s clean speech for voice cloning
│   ├── sample.wav                  # 3–5s preview used in wizard persona card
│   └── voice.yaml                  # Pitch, speed, emotion defaults
└── metadata.yaml                   # Licensing, source attribution, creator notes
```

**REQUIRED:** `persona.yaml`, `avatar/portrait.png`, `avatar/states/{idle,listening,thinking,speaking}.png`, `voice/reference.wav`, `voice/sample.wav`, `metadata.yaml`.

**Generated / cached (not committed):** `landmarks.json`, `clips/*.mp4`, `clips/manifest.json` — produced by the persona preprocessing pipeline from `portrait.png` + state images. Must be in `.gitignore`.

---

## `persona.yaml` schema

```yaml
# REQUIRED — stable identifier. Lowercase, alphanumeric + hyphens. Never change after release.
id: "aurora"

# REQUIRED — display name shown in UI. User can override.
display_name: "Aurora"

# REQUIRED — short description (<=120 chars). Shown in wizard persona card.
tagline: "Warm and grounded. A calm presence for focused work."

# REQUIRED — schema version. Bump when this file format changes.
schema_version: 1

# REQUIRED — LLM personality.
personality:
  archetype: "warm_supportive"
  # One of the 12 archetypes (see § "Archetype catalog" below)

  system_prompt: |
    You are Aurora, a warm and grounded AI companion...
    (Full prompt. Multi-line. 200-800 tokens typical.)

  # Style hints the LLM follows consistently.
  style:
    formality: "casual"          # casual | neutral | formal
    verbosity: "medium"          # terse | medium | expressive
    humor: "light"               # none | light | dry | playful
    emoji_usage: "never"         # never | sparingly | natural

# REQUIRED — TTS + voice cloning parameters.
voice:
  engine: "auto"                 # auto | <engine-specific> — resolves to active TTS engine
  gender_hint: "female"          # informational; used for ML-based fallbacks
  pitch_shift: 0                 # semitones, -6 to +6
  speed: 1.0                     # 0.85 to 1.15
  emotion_default: "neutral"     # neutral | warm | bright | calm | serious

  # Phrases spoken when routing to a slow model. One picked at random.
  # Consumed by the latency-aware social timing system (see 09_realtime_interaction.md).
  acknowledgment_phrases:
    - "Give me a moment on that."
    - "Let me think about that one."
    - "One sec while I look into that."
    - "Good question — let me work that out."

  # Phrases for interruption / barge-in.
  interruption_phrases:
    - "Sorry, go ahead."
    - "Yes?"
    - "I'm listening."

# REQUIRED — avatar behavior metadata.
# The rendering engine is configured globally; persona parameterizes it.
avatar:
  resolution: [1024, 1024]       # source portrait dimensions
  target_fps: 25                 # default; overridden by performance tier
  idle_blink_rate_hz: 0.28       # ~1 blink every 3.5s
  idle_micro_movement_scale: 0.6 # 0.0 (still) to 1.0 (lively)

  # Presence controller hints (see 11_avatar_presence.md).
  presence:
    gaze_warmth: 0.7             # 0.0 cool / 1.0 warm
    smile_baseline: 0.3          # resting expression neutrality
    listening_lean_strength: 0.5

# OPTIONAL — memory behavior overrides.
memory:
  isolation: true                # each persona has its own memory collection
  retention_days: 365            # 0 = forever
  persona_can_forget: true       # respects "forget this" commands

# OPTIONAL — model router hints (see 18_model_router_spec.md).
# The router still decides per turn; this only nudges tier selection.
llm_preferences:
  preferred_tier: "main"         # fast | main | heavy
  temperature: 0.7
  max_output_tokens: 1024
```

---

## `voice/voice.yaml` schema

Kept separate from `persona.yaml` so voice settings can evolve independently.

```yaml
schema_version: 1

# Reference file for voice cloning (relative path).
reference_wav: "reference.wav"

# Short preview used in the wizard.
sample_wav: "sample.wav"

# Engine-agnostic knobs resolved by the active TTS engine.
expression:
  exaggeration: 0.5              # 0.3 (flat) to 0.8 (expressive)
  stability: 0.5                 # consistency vs variation
  style: 0.0                     # stylistic emphasis
```

Engine-specific overrides (if needed) go under a namespaced section (e.g., `xtts:`, `piper:`, `coqui:`) — resolved at runtime by the active TTS wrapper.

---

## `metadata.yaml` schema

Licensing and attribution. Required for legal audit before shipping.

```yaml
schema_version: 1

creator: "Don Havery"
created: "2026-04-17"
last_updated: "2026-04-17"

# REQUIRED — provenance of every shipped asset.
assets:
  portrait:
    source: "ai_generated"       # ai_generated | licensed | royalty_free | user_supplied
    generator: "SDXL + Isabelle LoRA v2.0"
    prompt: "<prompt used; for audit>"
    license: "custom_aether"     # we own; ship under pack license
  state_images:
    source: "ai_generated"
    generator: "SDXL + Isabelle LoRA v2.0 + inpaint"
    license: "custom_aether"
  voice_reference:
    source: "royalty_free"
    attribution: "Pixabay voice-over sample by <creator>, CC0"
    url: "https://..."
    license: "CC0"
  voice_sample:
    source: "synthesized"
    license: "custom_aether"

notes: |
  Portrait AI-generated. No real-person likeness reference.
  Voice reference CC0. Derived cloned output owned under TTS engine terms.
```

---

## Archetype catalog (12)

These are the baseline personality archetypes. Each persona pack uses exactly one.

| archetype | Typical use |
|-----------|-------------|
| `warm_supportive` | Calm presence, focused work |
| `analytical_precise` | Structured, clean reasoning |
| `playful_witty` | Light spark, humor |
| `formal_executive` | Direct, decisive |
| `calm_zen` | Low-energy, high-signal |
| `energetic_enthusiastic` | Momentum, high-output |
| `dry_sardonic` | Smart, deadpan |
| `mentor_teacher` | Patient explainer |
| `peer_collaborator` | Works with, not for |
| `creative_artistic` | Lateral thinker |
| `technical_engineer` | Skips to the problem |
| `curious_inquisitive` | Asks the missed question |

Persona ≠ avatar. Users can pair any avatar appearance with any archetype. The pack's `id` represents its canonical pairing (the one we generate and QA); user combinations may differ.

---

## Validation rules (loader-enforced)

The persona loader MUST reject a pack that:

- Is missing any REQUIRED file
- Has `persona.yaml` with missing REQUIRED fields or invalid enum values
- Has `metadata.yaml` claiming an asset source the loader can't verify (e.g., `ai_generated` without `generator`)
- Has a `reference.wav` shorter than 5 s or longer than 60 s
- Has a `portrait.png` smaller than 512×512 or non-square beyond ±10%
- Has a persona `id` that doesn't match its folder name

---

## Generation pipeline (for adding a persona)

1. **Scaffold** — creates folder, writes `persona.yaml` with archetype-appropriate defaults.
2. **Portrait generation** — SDXL + LoRA produces candidates; creator picks one.
3. **State image generation** — inpaint expression variants (idle / listening / thinking / speaking).
4. **Landmark preprocessing** — extract 68-point face landmarks → `landmarks.json`.
5. **Idle / transition clip generation** — driver model produces 4 transition clips → `clips/`.
6. **Voice reference sourcing** — pick a CC0 voice sample; copy to `voice/reference.wav`.
7. **Voice sample synthesis** — active TTS engine generates `voice/sample.wav` preview.
8. **Personality prompt writing** — human-written (no LLM auto-draft) for quality.
9. **QA conversation** — 10-turn test conversation; review transcript.
10. **Legal audit** — complete `metadata.yaml`, confirm every asset's provenance.

Expected cost per persona: 2–4 hours with human input at steps 2, 6, 8, 9.

---

## Licensing obligations when shipping

Every shipped persona pack must:

- Have `metadata.yaml` complete with every asset's source + license
- Pass the pre-ship audit check
- Use only CC0, MIT, Aether-owned, or explicitly-licensed assets
- **Avoid likeness of any real identifiable person** (Don's locked rule: [AI-generated source models only](file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/feedback_ai_source_models_only.md))

Shipped products include a single `LICENSE-PERSONAS.md` aggregating all pack attributions.

---

## Isabelle-specific note

Isabelle's persona pack is **private** — not distributed with Aether OSS Preview or Aether Pro public packs. Her appearance, voice, and system prompt are Don's private configuration on top of the Aether Pro platform (see [roadmaps/isabelle_private.md](roadmaps/isabelle_private.md)).

Isabelle's pack uses the same schema but lives in Don's private overlay, not any public persona directory.

---

## Future-proofing

- Schema version `1` is the baseline.
- Future versions may add: per-persona gesture libraries, body rigs, multi-voice support, affect curves.
- Loaders migrate older packs forward by filling defaults for new fields.
- **Never remove fields** — only add optional ones.

---

## Cross-references
- Avatar system: [11_avatar_presence.md](11_avatar_presence.md)
- Realtime / acknowledgment phrases: [09_realtime_interaction.md](09_realtime_interaction.md)
- Model router (LLM preferences): [18_model_router_spec.md](18_model_router_spec.md) *(when written)*
- Memory (isolation, retention): [10_memory_architecture.md](10_memory_architecture.md)
- Persona compiler (how persona.yaml becomes runtime state): [01_product_doctrine.md § Must-own layers](01_product_doctrine.md#must-own-layers-custom-built-aether-pro-onward)
- Tech stack: [16_tech_stack.md](16_tech_stack.md)
