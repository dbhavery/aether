# Avatar assets for persona 'marcus_chen'

Each section below records exactly how one asset was generated.
Add a new section any time an asset is regenerated — do not
overwrite history. Schema: `docs/PERSONA-SCHEMA.md`.

## `portrait.png` — current (2026-04-28)

- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- generation date: `2026-04-28`
- seed: `1182764741`
- source URL: `https://v3b.fal.media/files/b/0a9823d8/YUvg1Rag0w-NARUA8aIfD_3a7648cbcc51447890c971c0fcbb014e.jpg`
- raw output: 2752 × 1536 (16:9 — model returned landscape despite intent)
- post-processing: center-square crop to 1536 × 1536, then Lanczos resize to 1024 × 1024 PNG via PIL
- raw file: `portrait_source_2026-04-28.jpg`
- prompt:

```text
Photorealistic candid portrait of an Asian American man in his late 30s, short well kept dark hair with a hint of grey at the temples, sharp brown eyes behind thin wire frame glasses, light stubble, slight asymmetric smile that reads as just got the answer, wearing a charcoal henley with sleeves pushed to the elbows. Warm afternoon study light, blurred bookshelf with a closed laptop on a wooden desk. Slim athletic build, no jewelry except a simple steel watch. Real skin texture with visible pores and natural imperfections. Shot on 85mm at f/1.8. Reads as a thoughtful technical friend across the table, not a stock photo. Avoid glamour pose, plastic skin, perfect symmetry, anime, AI tropes.
```

## `states/*.png` — pending generation

The 4 expression state images (idle / listening / thinking / speaking)
have not been generated yet.

See `states/STALE_AFTER_PORTRAIT_REGEN.md` for the regeneration notes.

Until states are generated, code that reads `states/idle.png` etc.
should fall back to `portrait.png` or block with a clear error.
