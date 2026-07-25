# Avatar assets for persona 'james_whitfield' (display_name: James Whitfield)

Status: **NOT YET GENERATED.** Anchor-schema spec drafted; awaiting
Don's approval on FLUX-pro spend after Aurora anchor eyeball-check.

Backend: `fal.ai` model `fal-ai/flux-pro/v1.1-ultra`. Raw output
2752 × 1536. Four calls per pack.

Character: 55 M white, weathered, grey-flecked hair, "sit with it"
elder archetype.

---

## Prompt: `anchor.png` — canonical face reference

```text
Photorealistic neutral reference portrait of a white American man in his mid 50s, short well kept hair more salt than pepper, weathered face with deep but kind crow's feet around hazel-grey eyes, light groomed grey stubble, neutral relaxed expression, mouth softly closed, looking directly at the camera. Even diffuse soft light with no harsh shadows, very subtle warm undertone. Plain neutral pale grey background, no objects in frame, simple wardrobe of a heavy slate-grey wool henley with the top button undone. Real skin texture with visible pores, natural sun-weathered imperfections, calm steady demeanor, broad shoulders working-build not gym-build. Shot on 85mm at f/4 for clean focus across the face, sharp on the eyes. Square head and upper shoulders composition, anchor reference photo style: calm, present, not styled. Avoid plastic skin, perfect symmetry, glamour pose, anime, gradient backgrounds, side rim lighting, motion blur, overly young-looking face.
```

## Prompt: `portrait.png` — personality picker shot

```text
Photorealistic candid portrait of a white American man in his mid 50s, short salt-and-pepper hair, weathered kind face with deep crow's feet, hazel-grey eyes that hold contact, light grey stubble, slight quiet smile that reads as listened to the whole story before saying anything. Wearing a heavy slate-grey wool henley over a faded charcoal tee, sleeves pushed up showing forearms with the marks of someone who works with his hands. Late afternoon kitchen light, warm wood table, a steaming dark mug just inside the frame, blurred shelves of well-read paperbacks behind. Real skin texture with visible pores and sun-weathered imperfections. Shot on 85mm at f/1.8. Reads as an older friend who knows when to talk and when to wait, not a stock photo, not a wisdom-on-demand stereotype. Avoid glamour pose, plastic skin, perfect symmetry, anime, AI tropes, hipster lumberjack tropes.
```

## Prompt: `profile_left.png` — 3/4 left angle

```text
Photorealistic 3/4 left profile of a white American man in his mid 50s, short salt-and-pepper hair, weathered kind face, hazel-grey eyes, light grey stubble, neutral relaxed expression, mouth softly closed, head turned 30 degrees right (showing his left 3/4). Even diffuse soft light, no harsh shadows. Plain neutral pale grey background, slate-grey wool henley. Real skin texture with visible pores. 85mm at f/4. Anchor-reference lighting. Avoid plastic skin, perfect symmetry, glamour pose, anime, side rim lighting.
```

## Prompt: `profile_right.png` — 3/4 right angle

Same as profile_left, head turned 30 degrees left (showing his right 3/4).

## Regen nudges if anchor reads off-character

- "...mid 50s reading as a man who has worked outdoors and read indoors, not retirement-aged, not mid-40s..." if age reads off
- "...salt and pepper, not full grey, not dark with single grey patch..." if hair reads off
- "...kind crow's feet that crinkle when he listens, not severe brow..." if face reads stern instead of grounded

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
- source URL: https://v3b.fal.media/files/b/0a9828cb/WbdlfZlt_apkFz0jPuh6I_18cc4070083e4152bbf2fdf399c18850.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/anchor_raw.jpg`

### portrait.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828cc/fPnKOjrPmDFiYt30UVkCk_9d783e2bad124a93b5825262a6bbaad1.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/portrait_raw.jpg`

### profile_left.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828cd/Sxus24Kw9jyyokrtKvfWZ_0e8228212b9e4e5d9d8cc369a3604f31.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/profile_left_raw.jpg`

### profile_right.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828ce/9sazcZbyAdOF3EQRRzmKn_a54f08b075dc456ca9acd1bc364cfdf1.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/profile_right_raw.jpg`
