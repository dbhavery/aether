# Avatar assets for persona 'marcus_chen' (display_name: Marcus Chen)

Each section below records exactly how one asset was generated.
Add a new section any time an asset is regenerated — do not
overwrite history.

This will be the **second-pass anchor-schema** avatar pack. The
first-pass single-portrait pack is preserved at
`../_archived_2026-04-28_first_pass/`.

---

## Status

**NOT YET GENERATED.** This file holds the prompt briefs and
generation parameters so the pack is ready to fire when Don
approves the FLUX-pro API spend (~5 calls × $0.05 ≈ $0.25). Do
not generate without Don's eyeball-check on Aurora's anchor first
(per CHARACTERS.md face-consistency lock-before-scale rule).

---

## Asset schema (Phase 4 — headshot)

Same shape as Aurora's pack:

- `anchor.png` — canonical neutral face reference. Even diffuse
  light, neutral relaxed expression, mouth softly closed, looking
  forward, simple background.
- `portrait.png` — personality picker shot. Marcus's character:
  thoughtful technical sparring partner, study/desk vibe, charcoal
  henley, slight asymmetric smile that reads as "just got the answer."
  Inherits the personality framing from the archived first-pass.
- `profile_left.png` — 3/4 left angle, anchor-style lighting.
- `profile_right.png` — 3/4 right angle, anchor-style lighting.

Backend: `fal.ai` model `fal-ai/flux-pro/v1.1-ultra`.
Raw output: 2752 × 1536 (model ignores requested sizes).
Sizing/cropping deferred per Don's 2026-04-28 directive.

---

## Prompt: `anchor.png` — canonical face reference

```text
Photorealistic neutral reference portrait of an Asian American man in his late 30s, short well kept dark hair with a hint of grey at the temples, sharp brown eyes behind thin wire frame glasses, light groomed stubble, neutral relaxed expression, mouth softly closed, looking directly at the camera. Even diffuse soft light with no harsh shadows, very subtle warm undertone. Plain neutral pale grey background, no objects in frame, simple wardrobe of a charcoal henley with the top button undone. Real skin texture with visible pores and natural imperfections, no jewelry, slim athletic build. Shot on 85mm at f/4 for clean focus across the face, sharp on the eyes. Square head and upper shoulders composition, anchor reference photo style: calm, present, not styled. Avoid plastic skin, perfect symmetry, glamour pose, anime, gradient backgrounds, side rim lighting, motion blur.
```

Differs from first-pass portrait prompt: removes the laptop / desk /
asymmetric-smile elements; adds neutral expression + mouth closed +
direct camera gaze + plain pale grey background. The anchor needs
this calmness; the personality goes into `portrait.png` instead.

## Prompt: `portrait.png` — personality picker shot

Inherits from the archived first-pass attempt, lightly cleaned up.
Use the SAME face Marcus has in `anchor.png` so the portrait reads as
the same person.

```text
Photorealistic candid portrait of an Asian American man in his late 30s, short well kept dark hair with a hint of grey at the temples, sharp brown eyes behind thin wire frame glasses, light stubble, slight asymmetric smile that reads as just got the answer, wearing a charcoal henley with sleeves pushed to the elbows. Warm afternoon study light, blurred bookshelf with a closed laptop on a wooden desk. Slim athletic build, no jewelry except a simple steel watch. Real skin texture with visible pores and natural imperfections. Shot on 85mm at f/1.8. Reads as a thoughtful technical friend across the table, not a stock photo. Avoid glamour pose, plastic skin, perfect symmetry, anime, AI tropes.
```

## Prompt: `profile_left.png` — 3/4 left angle

```text
Photorealistic 3/4 left profile of an Asian American man in his late 30s, short well kept dark hair with a hint of grey at the temples, sharp brown eyes behind thin wire frame glasses, light groomed stubble, neutral relaxed expression, mouth softly closed, head turned 30 degrees right (showing the camera his left 3/4). Even diffuse soft light, no harsh shadows. Plain neutral pale grey background, simple charcoal henley wardrobe. Real skin texture with visible pores. 85mm at f/4. Anchor-reference lighting, not portrait-glamour lighting. Avoid plastic skin, perfect symmetry, glamour pose, anime, side rim lighting.
```

## Prompt: `profile_right.png` — 3/4 right angle

```text
Photorealistic 3/4 right profile of an Asian American man in his late 30s, short well kept dark hair with a hint of grey at the temples, sharp brown eyes behind thin wire frame glasses, light groomed stubble, neutral relaxed expression, mouth softly closed, head turned 30 degrees left (showing the camera his right 3/4). Even diffuse soft light, no harsh shadows. Plain neutral pale grey background, simple charcoal henley wardrobe. Real skin texture with visible pores. 85mm at f/4. Anchor-reference lighting, not portrait-glamour lighting. Avoid plastic skin, perfect symmetry, glamour pose, anime, side rim lighting.
```

## Prompt: regen candidates (in case anchor reads off-character)

If the first anchor generation doesn't read as the canonical Marcus
(face geometry off, glasses style wrong, hair too dark/light, age
reads younger or older than late 30s), regenerate with one of these
nudges:

- "...thin wire frame glasses with rectangular frames, not round..."
  (if first pass returned round/Harry-Potter glasses)
- "...short tapered cut, not buzz cut, not styled long..." (if hair
  reads wrong length)
- "...late 30s reading as someone with a decade of senior engineering
  behind him, not mid-20s..." (if age reads too young)
- "...one or two small scattered grey strands at the temples, not a
  full grey patch..." (if grey reads heavy)

---

## Cross-pack QA (worth eyeballing)

Open all four side-by-side in an image viewer. Same person? Same hair
color and length, same glasses frame, same approximate face geometry,
same skin tone? If any one feels off-character, flag for regeneration.
The anchor specifically must read as the canonical Marcus — if it
doesn't, every other shot in the pack inherits the error.

---

## What's NOT in this pack yet

- **Expression states (idle/listening/thinking/speaking).** Deferred,
  not pre-generated as static stills. Abandoned per Aurora's
  anchor-schema redesign.
- **Body shot.** Phase 5+ (end of project).
- **Multi-pose / motion.** Phase 5+.

See file:///C:/Users/dbhav/Projects/aether/personas/CHARACTERS.md
for the full asset schema.

---

## Generation log — 2026-04-28

### anchor.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828c0/-cqEaWZajeuJSdvfmUtBC_71638bd38e6742c8bfd0115d3fd906ce.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/anchor_raw.jpg`

### portrait.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828c1/mwtnmBFfxoJ57gDLh4Cgo_fecffe1f92f443c3af715bdb902f400c.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/portrait_raw.jpg`

### profile_left.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828c2/ztVIhh6e4Qj4TTQAc4dwz_71095515edae44648a4d30cb00a61a52.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/profile_left_raw.jpg`

### profile_right.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828c3/RxOVCSJqWwumh8bf_C_JB_d0fb39473fd642a29662f386f0909fd5.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/profile_right_raw.jpg`
