# Avatar assets for persona 'aurora'

Each section below records exactly how one asset was generated.
Add a new section any time an asset is regenerated — do not
overwrite history. Schema: `docs/PERSONA-SCHEMA.md`.

## `portrait.png` — current (2026-04-28)

- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- generation date: `2026-04-28`
- seed: `1181057909`
- source URL: `https://v3b.fal.media/files/b/0a982359/4uk-BxXBCdnKiyowD1fqJ_72db72e5f8184e5188781c779817f062.jpg`
- raw output: 2752 × 1536 (16:9 — model ignored requested portrait_4_3 size)
- post-processing: center-square crop to 1536 × 1536, then Lanczos resize to 1024 × 1024 PNG via PIL
- pre-crop file: `../candidates_2026-04-28/aurora_03_honey_auburn_cafe.jpg`
- 1024-square file: `../candidates_2026-04-28/aurora_03_square_1024.png`
- selection: Don picked candidate 03 of 4 generated under the "good-looking warm friend" brief on 2026-04-28
- prompt:

```text
Photorealistic candid portrait of a woman in her early 30s, shoulder-length wavy honey-auburn hair tucked behind one ear, green-hazel eyes, light freckles, easy mid-laugh smile, wearing an oversized oatmeal cardigan over a thin t-shirt. Warm cafe window light, blurred wood and brass background. Natural skin texture with visible pores, no makeup, slim athletic frame, a single thin gold chain. Shot on 85mm at f/1.8. Looks like a friend across the table, not a model. Avoid: glamour pose, plastic skin, perfect symmetry, anime, AI-girl tropes.
```

## `states/*.png` — STALE (regeneration pending)

The 4 expression state images (idle / listening / thinking / speaking)
were archived to `_archived_2026-04-17/states/` when the canonical
portrait was replaced on 2026-04-28.

See `states/STALE_AFTER_PORTRAIT_REGEN.md` for the regeneration plan.

## `_archived_2026-04-17/` — prior portrait + states

The original Aurora avatar pack from 2026-04-17 is preserved here
for provenance. **Do not delete.** Schema audit tools may need to
verify the lineage of any inference that depended on those assets.

### Original `portrait.png` (archived)

- backend: `openai`
- model: `gpt-image-1.5`
- prompt:

```text
Portrait of a woman in her early 30s with warm hazel-brown eyes, natural wavy shoulder-length auburn hair with subtle highlights, light natural makeup, gentle genuine smile suggesting warmth and calm intelligence. Wearing a soft cream-colored knit sweater with a wide neckline. Skin has natural warm undertones with light freckles across the bridge of the nose. Background: Out-of-focus neutral warm beige interior wall, hint of a soft terracotta-toned textured fabric in the blur. Lighting: Soft diffused golden-hour window light from the left at a 45-degree angle, producing gentle warm highlights on the cheekbone and a soft catchlight in the eyes. No harsh shadows. Photorealistic editorial portrait. Natural skin texture with visible pores and subtle skin variation — NOT airbrushed, NOT porcelain, NOT plastic. No magenta or purple rim light. No indigo gradient background. No cyberpunk neon. No text, no watermark, no logo, no jewelry with text. Realistic eye reflections, correct eye anatomy (no extra catchlights, no over-saturated iris). Centered composition, head and upper shoulders visible, relaxed natural expression, looking directly at camera. Shot on 85mm lens, f/2.0, shallow depth of field, sharp focus on the eyes. Square 1:1 framing, portrait-oriented subject centered in frame.
```

### Original `states/{idle,listening,thinking,speaking}.png` (archived)

Same base prompt as the original portrait, with an additional
"Expression for this frame:" sentence per state. Full prompts
were captured in the prior version of this file in git history
(commit before 2026-04-28 swap).
