# Avatar assets for persona 'hannah_park' (display_name: Hannah Park)

Status: **NOT YET GENERATED.** Anchor-schema spec drafted; awaiting
Don's approval on FLUX-pro spend after Aurora anchor eyeball-check.

Backend: `fal.ai` model `fal-ai/flux-pro/v1.1-ultra`. Raw output
2752 × 1536. Four calls per pack.

Character: 34 F Korean-American, glasses, depth-researcher archetype
— careful, well-read, citations on tap.

---

## Prompt: `anchor.png` — canonical face reference

```text
Photorealistic neutral reference portrait of a Korean American woman in her mid 30s, shoulder length straight black hair tucked simply behind both ears, warm dark brown eyes behind delicate round wire frame glasses, fair skin with a few small natural freckles across the nose, neutral relaxed expression, mouth softly closed with the very faintest hint of a smile, looking directly at the camera. Even diffuse soft light with no harsh shadows, very subtle warm undertone. Plain neutral pale beige background, no objects in frame, simple wardrobe of a fitted slate-grey wool cardigan over a thin cream tee. Real skin texture with visible pores and natural imperfections, no heavy makeup, slim build. Shot on 85mm at f/4 for clean focus across the face, sharp on the eyes. Square head and upper shoulders composition, anchor reference photo style: calm, present, not styled, thoughtful-careful demeanour. Avoid plastic skin, perfect symmetry, glamour pose, anime, gradient backgrounds, side rim lighting, motion blur, stylized-academic styling.
```

## Prompt: `portrait.png` — personality picker shot

```text
Photorealistic candid portrait of a Korean American woman in her mid 30s, shoulder length straight black hair, warm dark brown eyes behind round wire frame glasses, slight thoughtful smile that reads as let me think about that for a minute. Wearing a fitted slate-grey wool cardigan over a thin cream tee, a simple silver pendant just visible at the collar. Soft afternoon library light, blurred wooden bookshelves behind, a closed paperback with a leather bookmark on the table beside her. Slim build, real skin texture with visible pores and natural imperfections. Shot on 85mm at f/1.8. Reads as a careful researcher friend who knows the literature and shares it generously, not a lecturer, not a pedant. Avoid glamour pose, plastic skin, perfect symmetry, anime, AI tropes, stylized-academic styling.
```

## Prompt: `profile_left.png` — 3/4 left angle

```text
Photorealistic 3/4 left profile of a Korean American woman in her mid 30s, shoulder length straight black hair, dark brown eyes behind round wire frame glasses, neutral relaxed expression, mouth softly closed, head turned 30 degrees right (showing her left 3/4). Even diffuse soft light, no harsh shadows, subtle warm undertone. Plain neutral pale beige background, slate-grey cardigan over cream tee. Real skin texture with visible pores. 85mm at f/4. Anchor-reference lighting. Avoid plastic skin, perfect symmetry, glamour pose, anime, side rim lighting.
```

## Prompt: `profile_right.png` — 3/4 right angle

Same as profile_left, head turned 30 degrees left (showing her right 3/4).

## Regen nudges if anchor reads off-character

- "...mid 30s reading as a researcher with a PhD and a few years of postdoc behind her, not late 20s, not late 40s..." if age reads off
- "...delicate round wire frames, not chunky frames, not rimless..." if glasses style reads wrong
- "...thoughtful-careful, not mousy, not stereotyped-bookish..." if expression drifts toward cliché

---

See file:///C:/Users/dbhav/Projects/aether/personas/marcus_chen/avatar/README.md
for full schema explanation. Same conventions apply.
