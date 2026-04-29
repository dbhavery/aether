# tools/validate-personas

Strict-consumer validation for persona pack source dirs under
`personas/<slug>/`. Catches drift between metadata.yaml claims and
actual asset files BEFORE the build pipeline zips a broken pack.

## What it checks

For each persona:

1. **`persona.yaml` content** — top-level `id`, `display_name`,
   `tagline` are present and non-empty; `personality.archetype` is
   set; `id` matches the directory name.
2. **`metadata.yaml` content** — has `schema_version` + `assets`
   block; does NOT contain the `PENDING` sentinel (i.e. graduated
   from PENDING to ai_generated).
3. **Anchor-set PNGs** — all 4 of `avatar/{anchor,portrait,
   profile_left,profile_right}.png` exist and are non-empty.
4. **Voice WAVs** — `voice/reference.wav` and `voice/sample.wav`
   exist with valid headers (`wave.open` succeeds), 24 kHz mono
   16-bit PCM, durations 20.0 s ± 0.2 s and 4.0 s ± 0.2 s.
   This catches OpenAI's gpt-4o-mini-tts header-overflow bug
   (frames=INT32_MAX) which the generator now repairs but legacy
   files might still carry.
5. **Voice docs** — `voice/voice.yaml` and `voice/SOURCE.md` exist.

Soft warnings (non-fatal):
- `voice/voice.yaml` doesn't reference `reference_wav` field.

## Usage

```bash
# Validate all v0-cast personas (default discovery: persona.yaml + anchor.png)
python tools/validate-personas/validate.py

# Validate one specific persona
python tools/validate-personas/validate.py aurora

# CI-strict: fail on warnings as well as errors
python tools/validate-personas/validate.py --strict
```

Returns exit code 1 if any persona fails (or warns under `--strict`).
Suitable for CI gating.

## Output snapshot (2026-04-28 cast)

```
[PASS] aurora
[PASS] hannah_park
[PASS] james_whitfield
[PASS] marcus_chen
[PASS] nadia_volkov
[PASS] priya_iyer
[PASS] ray_castellano
[PASS] sara_reyes
[PASS] tomas_andrade

9 personas validated: 9 pass, 0 fail, 0 with warnings
```

## When this runs in the pipeline

```
personas/<slug>/                        [canonical source]
        │
        │  python tools/validate-personas/validate.py   ← gate
        ▼
        all-pass?
        │
        │  python tools/build-persona-pack/build.py
        │  python tools/build-persona-previews/build.py
        ▼
dist/personas/...                       [release artifacts]
```

Run validation before every release. If a persona fails, fix the
underlying source before letting the build pipeline run; otherwise
the broken pack ships and downstream consumers (the L6 persona
engine, the wizard, lipsync pipeline) will fail to load it.

## Why we don't just trust the build pipeline

`build-persona-pack` does check that all required files exist
before opening the zip — but it doesn't check WAV header sanity,
metadata graduated state, or persona.yaml field completeness. This
validator is the strict pre-flight that catches subtle data-quality
issues the zip-and-hash step misses.
