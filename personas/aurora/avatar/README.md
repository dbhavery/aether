# Avatar assets for persona 'aurora' (display_name: Aurora Nash)

Each section below records exactly how one asset was generated.
Add a new section any time an asset is regenerated — do not
overwrite history.

This is the **second-pass anchor-schema** avatar pack (2026-04-28
night). The first-pass single-portrait pack is preserved at
`../_archived_2026-04-28_first_pass/`.

## Asset schema (Phase 4 — headshot)

- `anchor.png` — canonical neutral face reference. Even diffuse
  light, neutral relaxed expression, mouth softly closed, looking
  forward, simple background.
- `portrait.png` — personality picker shot. Cafe-candid, mid-laugh,
  warm setting. Used in the persona-picker UI where personality
  matters more than face geometry.
- `profile_left.png` — 3/4 left angle, anchor-style lighting.
  A side view of the same face.
- `profile_right.png` — 3/4 right angle, anchor-style lighting.

All four are 2752×1536 raw FLUX output (the model ignores requested
sizes and returns 16:9 landscape regardless). Sizing/cropping is
deferred per Don's directive 2026-04-28: "we can deal with sizing
later."

Raw JPGs preserved at `anchor_set_raw_2026-04-28/` for re-cropping
without quality loss.

---

## `anchor.png` — canonical face reference

- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- generation date: `2026-04-28`
- request_id: `019dd6f3...` (see logs)
- source URL: `https://v3b.fal.media/files/b/0a982484/Ijui4cvhYR2Y9VvxNu5sT_47f1d510630f4393b4eb0bc98686dd28.jpg`
- raw output: 2752 × 1536 (kept as-is, not cropped)
- prompt:

```text
Photorealistic neutral reference portrait of a woman in her early 30s with shoulder length wavy honey auburn hair tucked simply behind both ears, hazel green eyes, light freckles across the bridge of her nose, neutral relaxed expression, mouth softly closed with the very faintest hint of a smile, looking directly at the camera. Even diffuse soft light with no harsh shadows, very subtle warm undertone. Plain neutral pale beige background, no objects in frame, simple wardrobe of a thin neutral cream knit top with a high collar. Real skin texture with visible pores, no makeup, slim athletic build. Shot on 85mm at f/4 for clean focus across the face, sharp on the eyes. Square head and upper shoulders composition, anchor reference photo style: calm, present, not styled. Avoid plastic skin, perfect symmetry, glamour pose, anime, gradient backgrounds, side rim lighting, motion blur.
```

## `portrait.png` — personality picker shot

- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- generation date: `2026-04-28`
- source URL: `https://v3b.fal.media/files/b/0a982478/vdYJZCtKywYoZoowDNMml_431843d4228644f39874045d006a41e0.jpg`
- raw output: 2752 × 1536
- prompt: same brief as the archived first-pass candidate 03 (cafe candid mid-laugh) — re-rolled with a fresh seed under the same description so the personality shot stays a personality shot.

## `profile_left.png` — 3/4 left angle

- source URL: `https://v3b.fal.media/files/b/0a982479/FLMG_JdVvAjB4NN4-40p7_0ff595c8fb4f4014a1f6e88695d31763.jpg`
- prompt: anchor brief with head turned 30 degrees right (showing left 3/4 from camera).

## `profile_right.png` — 3/4 right angle

- source URL: `https://v3b.fal.media/files/b/0a982479/PGxnU-S6_oUkm1WesGnwV_386b6b9dd00641bcb4b79233973e4428.jpg`
- prompt: anchor brief with head turned 30 degrees left (showing right 3/4 from camera).

## What's NOT in this pack yet

- **Expression states (idle/listening/thinking/speaking).** Deferred,
  not pre-generated as static stills. The first-pass approach
  (4 still PNGs) is being abandoned.
- **Body shot.** Phase 5+ (end-of-project) per Don's 2026-04-28 directive.
- **Multi-pose / motion.** Phase 5+.

See file:///C:/Users/dbhav/Projects/aether/personas/CHARACTERS.md
for the full asset schema.

---

## Cross-pack QA (worth eyeballing)

Open all four side-by-side in an image viewer. Same person? Same
hair color, same freckle pattern, same eye color, same approximate
face geometry across the 4 shots? If any one feels off-character,
flag it for regeneration. The anchor specifically must read as the
canonical Aurora — if it doesn't, every other shot in the pack
inherits the error.
