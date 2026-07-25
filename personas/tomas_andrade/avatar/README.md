# Avatar assets for persona 'tomas_andrade' (display_name: Tomás Andrade)

Status: **NOT YET GENERATED.** Anchor-schema spec drafted; awaiting
Don's approval on FLUX-pro spend after Aurora anchor eyeball-check.

Backend: `fal.ai` model `fal-ai/flux-pro/v1.1-ultra`. Raw output
2752 × 1536. Four calls per pack.

Character: 36 M Latino, direct-coach archetype — names the
avoidance, warm without performing warmth. NOT a therapist; NOT a
life-coach stereotype.

---

## Prompt: `anchor.png` — canonical face reference

```text
Photorealistic neutral reference portrait of a Latino man in his mid 30s, short well kept dark brown hair with a slight natural wave on top, warm dark brown eyes, lightly tanned skin with a few small natural freckles across the cheekbones, light groomed dark stubble, neutral relaxed expression, mouth softly closed with the very faintest hint of a smile, looking directly at the camera. Even diffuse soft light with no harsh shadows, very subtle warm undertone. Plain neutral pale beige background, no objects in frame, simple wardrobe of a heather-charcoal lightweight crewneck sweater. Real skin texture with visible pores and natural imperfections, slim athletic build, no jewelry. Shot on 85mm at f/4 for clean focus across the face, sharp on the eyes. Square head and upper shoulders composition, anchor reference photo style: calm, present, not styled, grounded-warm demeanour. Avoid plastic skin, perfect symmetry, glamour pose, anime, gradient backgrounds, side rim lighting, motion blur, life-coach styling, wellness-brand styling.
```

## Prompt: `portrait.png` — personality picker shot

```text
Photorealistic candid portrait of a Latino man in his mid 30s, short dark brown hair with a slight natural wave, warm dark brown eyes that hold contact, light dark stubble, slight steady smile that reads as I am here and I am not in a hurry. Wearing a heather-charcoal crewneck sweater, sleeves pushed up showing forearms. Late afternoon home-office light, blurred well-lived bookshelves and a small plant behind, a half-full ceramic mug just inside the frame. Slim athletic build, real skin texture with visible pores and natural imperfections. Shot on 85mm at f/1.8. Reads as a direct, warm friend who would tell you the hard truth at 2am and means it, not a therapist, not a wellness-brand archetype. Avoid glamour pose, plastic skin, perfect symmetry, anime, AI tropes, life-coach styling, performative-empathy styling.
```

## Prompt: `profile_left.png` — 3/4 left angle

```text
Photorealistic 3/4 left profile of a Latino man in his mid 30s, short dark brown hair with slight natural wave, warm dark brown eyes, neutral relaxed expression, mouth softly closed, light groomed stubble, head turned 30 degrees right (showing his left 3/4). Even diffuse soft light, no harsh shadows, subtle warm undertone. Plain neutral pale beige background, heather-charcoal crewneck sweater. Real skin texture with visible pores. 85mm at f/4. Anchor-reference lighting. Avoid plastic skin, perfect symmetry, glamour pose, anime, side rim lighting.
```

## Prompt: `profile_right.png` — 3/4 right angle

Same as profile_left, head turned 30 degrees left (showing his right 3/4).

## Regen nudges if anchor reads off-character

- "...mid 30s reading as someone who has done his own work, not early 20s, not late 40s..." if age reads off
- "...grounded-warm, steady eye contact, not performatively-empathetic..." if expression drifts toward life-coach styling
- "...slim athletic build, not gym-stylized..." if frame reads stylized

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
- source URL: https://v3b.fal.media/files/b/0a9828e1/DYbC8JXV_VglyTgSUwQJL_868473bf3ee342058533551c8c9b27f7.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/anchor_raw.jpg`

### portrait.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828e2/Dh7BW0uHprRgFxcNdfkGt_69584439c0c34c38b6d9ae8e1e862278.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/portrait_raw.jpg`

### profile_left.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828e3/oi3ycaCpsytrJv15zmWIf_0be2ed4dd25f44cd95b8d5c44327e4e9.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/profile_left_raw.jpg`

### profile_right.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828e4/kfgxSw7iPEn5Gy_UHPMwZ_e826653711c34086b14e616da805a007.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/profile_right_raw.jpg`
