# Avatar assets for persona 'ray_castellano' (display_name: Ray Castellano)

Status: **NOT YET GENERATED.** Anchor-schema spec drafted; awaiting
Don's approval on FLUX-pro spend after Aurora anchor eyeball-check.

Backend: `fal.ai` model `fal-ai/flux-pro/v1.1-ultra`. Raw output
2752 × 1536. Four calls per pack.

Character: 52 M Italian-American, working-class executive, "stop
thinking, ship it" field-commander archetype. NOT a stereotype — a
veteran PM who happens to be Italian-American from the NY/NJ area.

---

## Prompt: `anchor.png` — canonical face reference

```text
Photorealistic neutral reference portrait of an Italian American man in his early 50s, short close-cropped salt-and-pepper hair, broad strong-featured face with a defined nose and jaw, warm dark brown eyes, light grey-flecked stubble, neutral resting expression with a steady direct gaze, mouth softly closed, looking directly at the camera. Even diffuse soft light with no harsh shadows, very subtle warm undertone. Plain neutral pale grey background, no objects in frame, simple wardrobe of a navy chambray work shirt with the top button undone. Real skin texture with visible pores, natural sun-weathered imperfections, broad shoulders working-build not gym-build, no jewelry except a simple steel watch on the wrist. Shot on 85mm at f/4 for clean focus across the face, sharp on the eyes. Square head and upper shoulders composition, anchor reference photo style: calm, present, not styled, slightly weathered-real. Avoid plastic skin, perfect symmetry, glamour pose, anime, gradient backgrounds, side rim lighting, motion blur, mob-stereotype styling, slick-suit styling.
```

## Prompt: `portrait.png` — personality picker shot

```text
Photorealistic candid portrait of an Italian American man in his early 50s, short close-cropped salt-and-pepper hair, broad strong-featured face, warm dark brown eyes mid-thought with a slight pragmatic squint, half-smile that reads as alright let's just get this done. Wearing a navy chambray work shirt with sleeves rolled up to the forearms, a simple steel watch. Mid-morning warehouse-office light, blurred whiteboard with a half-erased project timeline behind, a coffee mug with a battered logo just inside the frame. Working-build broad shoulders, real skin texture with visible pores and weathered imperfections. Shot on 85mm at f/1.8. Reads as a veteran program manager who has shipped a thousand things and knows the difference between fake progress and real progress. Avoid glamour pose, plastic skin, perfect symmetry, anime, AI tropes, mob-stereotype styling, slick-suit styling.
```

## Prompt: `profile_left.png` — 3/4 left angle

```text
Photorealistic 3/4 left profile of an Italian American man in his early 50s, short close-cropped salt-and-pepper hair, broad strong-featured face, warm dark brown eyes, neutral resting expression with steady direct gaze, mouth softly closed, head turned 30 degrees right (showing his left 3/4). Even diffuse soft light, no harsh shadows. Plain neutral pale grey background, navy chambray work shirt. Real skin texture with visible pores and weathered imperfections. 85mm at f/4. Anchor-reference lighting. Avoid plastic skin, perfect symmetry, glamour pose, anime, side rim lighting, mob-stereotype styling.
```

## Prompt: `profile_right.png` — 3/4 right angle

Same as profile_left, head turned 30 degrees left (showing his right 3/4).

## Regen nudges if anchor reads off-character

- "...early 50s reading as a veteran with two decades of shipping behind him, not late 30s, not retirement-aged..." if age reads off
- "...broad working-build shoulders, not gym-build, not slim..." if frame reads wrong
- "...weathered-real, not stylized, not mob-stereotype, not slick-suit..." if styling drifts wrong

---

See file:///C:/Users/dbhav/Projects/aether/personas/marcus_chen/avatar/README.md
for full schema explanation. Same conventions apply.

---

## Generation log — 2026-04-28

### anchor.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828d8/QdRdZTuuMj5rd8O8ujFjX_d016efd9a0614e8c8cc52018e582a366.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/anchor_raw.jpg`

### portrait.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828d9/KfQEdnTs2LSL6s6_hhoGO_95895227bfca4d72b000a1a4d544e456.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/portrait_raw.jpg`

### profile_left.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828da/K9or6jGvlheLhxHU4lfI7_a53d7303caf542b7a3105a3e7e6f6cae.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/profile_left_raw.jpg`

### profile_right.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828db/yVj5VAlQBpxNFXIIUpwbS_9fac2132aadd4d20bf9e081112349075.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/profile_right_raw.jpg`
