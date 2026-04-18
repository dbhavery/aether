# Persona Generator Toolkit

Developer tooling for producing persona packs that conform to
`docs/PERSONA-SCHEMA.md`. Used to generate the first three bundled packs
(aurora, caelum, luma) and designed to produce the remaining nine
(milo, ivy, atlas, wren, rhea, kai, nova, onyx, sage) in a future session.

This is not end-user product code — it prioritises running over polish.

---

## Prerequisites

| Variable | Purpose | Required |
|----------|---------|----------|
| `OPENAI_API_KEY` | GPT Image 1.5 portrait generation | yes |
| `FAL_KEY` | fal.ai (preferred when account has credit) | optional |
| `GEMINI_API_KEY` | Gemini 3 Flash Image (optional backend) | optional |

Scripts detect available backends automatically and fall back in order:
`fal` → `gpt-image-1.5` → `gemini-3.1-flash-image-preview`.

---

## One-persona recipe (end-to-end)

```bash
cd C:/Users/dbhav/Projects/aether-personas

# 1. Generate base portrait (1024x1024 square, writes personas/<id>/avatar/portrait.png)
python scripts/persona_generator/generate_portrait.py aurora

# 2. Generate the four state images from the same prompt family
python scripts/persona_generator/generate_states.py aurora

# 3. Source a CC0 voice reference (manual — document in metadata.yaml).
#    Drop it at personas/<id>/voice/reference.wav (24kHz mono, 10-30s).
#    Drop a 3-5s trimmed preview at personas/<id>/voice/sample.wav.

# 4. Optional: preprocess landmarks (runs the LivePortrait preprocess if installed)
python scripts/persona_generator/preprocess_landmarks.py aurora

# 5. Audit — runs the same validation as the loader + licensing rules
python scripts/persona_generator/audit_pack.py aurora
```

Expected output from step 5:
```
aurora: 0 issue(s) — clean
```

---

## File map

| Script | What it does |
|--------|-------------|
| `generate_portrait.py <id>` | Writes `personas/<id>/avatar/portrait.png` using the per-persona prompt template. Always produces 1024x1024 square PNG. |
| `generate_states.py <id>` | Writes the four `avatar/states/{idle,listening,thinking,speaking}.png` variants. Regenerates from the base prompt with expression modifiers. |
| `preprocess_landmarks.py <id>` | Runs 68-point face landmark extraction and writes `avatar/landmarks.json`. Stub if LivePortrait is not installed. |
| `audit_pack.py <id>` | Wrapper around `src.personas.audit.audit_pack` — schema-validates the pack then runs the licensing audit. Exit code 0 = clean. |

Per-persona prompt templates live in `prompts.py`. Add a new persona by:

1. Extending the `PERSONA_PROMPTS` dict in `prompts.py`.
2. Creating the target folder layout.
3. Running the recipe above.

---

## Decisions baked into the first three packs

- **Portrait backend:** GPT Image 1.5 (`gpt-image-1.5`) — fal was exhausted at the time of generation; GPT produced the most consistent skin texture and eye rendering for the three archetypes.
- **Art style:** Photorealistic editorial headshots, 85mm lens aesthetic, shallow depth of field, natural skin texture (no airbrushing). Deliberately NOT "indigo gradient AI slop" — every prompt carries explicit exclusion of gradient backgrounds, magenta lighting, and over-smooth skin.
- **State images:** Generated as fresh full-portraits sharing a persona prompt skeleton with an expression modifier — NOT inpainted from the base portrait. Inpainting at 1024x1024 with alpha masks was unreliable through the APIs available. Fresh generations keep each expression coherent even if small identity drift happens between frames; LivePortrait preprocessing (step 4 above) uses `portrait.png` as the authoritative identity anchor and re-reads landmarks from it at runtime, so state images are only seed references for LivePortrait's expression library.
- **Voice references:** Pixabay CC0 library voice-over samples. Source URL captured in each pack's `metadata.yaml`.

---

## Troubleshooting

### Portrait rejected by loader

```
portrait.png is 1023x1024 — minimum is 512x512 …
```

GPT Image 1.5 sometimes returns 1024x1024 minus one pixel. Re-run with the
script's built-in post-process (PIL resize to exactly 1024x1024).

### Audit reports placeholder source

```
metadata.assets.voice_reference.license: placeholder value 'n/a' …
```

You forgot to replace the scaffolded metadata.yaml with real attribution.
See `audit_pack.py --explain` for the field that needs filling.

### fal balance exhausted

Script will log `[fal] skipped — balance exhausted` and fall back to GPT.
No action needed unless you specifically want fal's model variety; top up
at https://fal.ai/dashboard/billing.

### Ran out of OpenAI credit mid-session

States don't have to be generated in one batch. Re-run `generate_states.py <id>`
— it skips files that already exist under `avatar/states/`.

---

## Regeneration policy

If you need to regenerate a persona from scratch:

```bash
rm -rf personas/aurora/avatar/  # keeps persona.yaml + voice/ + metadata.yaml
python scripts/persona_generator/generate_portrait.py aurora
python scripts/persona_generator/generate_states.py aurora
python scripts/persona_generator/audit_pack.py aurora
```

The persona.yaml `system_prompt` is hand-authored and must not be
regenerated from an LLM (locked rule — see the main `RUNWAY.md`).
