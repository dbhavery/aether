# Avatar assets for persona 'sara_reyes' (display_name: Sara Reyes)

Status: **NOT YET GENERATED.** Anchor-schema spec drafted; awaiting
Don's approval on FLUX-pro spend after Aurora anchor eyeball-check.

Backend: `fal.ai` model `fal-ai/flux-pro/v1.1-ultra`. Raw output
2752 × 1536. Four calls per pack.

Character: 28 F Latina, dark wavy hair, expressive mid-thought
energy, denim-jacket terrace vibe, brainstorm-partner archetype.

---

## Prompt: `anchor.png` — canonical face reference

```text
Photorealistic neutral reference portrait of a Latina woman in her late 20s, shoulder length dark wavy hair tucked simply behind both ears, warm brown eyes, lightly tanned skin with a few small natural freckles, neutral relaxed expression, mouth softly closed with the very faintest hint of a smile, looking directly at the camera. Even diffuse soft light with no harsh shadows, very subtle warm undertone. Plain neutral pale beige background, no objects in frame, simple wardrobe of a lightweight cream cotton tee under an unbuttoned indigo denim jacket. Real skin texture with visible pores and natural imperfections, no heavy makeup, slim athletic build. Shot on 85mm at f/4 for clean focus across the face, sharp on the eyes. Square head and upper shoulders composition, anchor reference photo style: calm, present, not styled. Avoid plastic skin, perfect symmetry, glamour pose, anime, gradient backgrounds, side rim lighting, motion blur.
```

## Prompt: `portrait.png` — personality picker shot

```text
Photorealistic candid portrait of a Latina woman in her late 20s, shoulder length dark wavy hair caught mid-motion as if she just turned to say something, warm brown eyes with crinkles from a real smile, mid-thought expressive smile that reads as just had an idea, wearing a lightweight cream tee and an open indigo denim jacket. Late afternoon golden hour light on a small outdoor cafe terrace, blurred string lights and a half-finished sketchbook on the table beside her. Slim athletic build, simple silver hoop earrings, no other jewelry. Real skin texture with visible pores and natural imperfections. Shot on 85mm at f/1.8. Reads as a creative friend riffing across the table, not a stock photo. Avoid glamour pose, plastic skin, perfect symmetry, anime, AI tropes.
```

## Prompt: `profile_left.png` — 3/4 left angle

```text
Photorealistic 3/4 left profile of a Latina woman in his late 20s, shoulder length dark wavy hair, warm brown eyes, neutral relaxed expression, mouth softly closed, head turned 30 degrees right (showing her left 3/4). Even diffuse soft light, no harsh shadows. Plain neutral pale beige background, lightweight cream tee under indigo denim jacket. Real skin texture with visible pores. 85mm at f/4. Anchor-reference lighting. Avoid plastic skin, perfect symmetry, glamour pose, anime, side rim lighting.
```

## Prompt: `profile_right.png` — 3/4 right angle

```text
Photorealistic 3/4 right profile of a Latina woman in her late 20s, shoulder length dark wavy hair, warm brown eyes, neutral relaxed expression, mouth softly closed, head turned 30 degrees left (showing her right 3/4). Same wardrobe and lighting as anchor.
```

## Regen nudges if anchor reads off-character

- "...late 20s, not late teens, not mid-30s..." if age reads off
- "...natural wavy texture, not styled curls, not straight..." if hair reads wrong
- "...soft natural smile hint, not full grin, mouth still closed..." if face reads too animated for anchor purposes

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
- source URL: https://v3b.fal.media/files/b/0a9828c6/uHPtz-y1FptuUJQTircUz_00e75f89bff143bca24ada8499459320.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/anchor_raw.jpg`

### portrait.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828c7/L798cFRJqrt2B49ckN3bs_2733ff0fe637446485ac8987c2060018.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/portrait_raw.jpg`

### profile_left.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828c8/zV-4FHfR_M61jE0hrjO7b_b4046a97032c4e0887b8a33436f91ccb.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/profile_left_raw.jpg`

### profile_right.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828c9/6SdiLPwMw5c2rMzcHVWk5_e0ea1fe09d8741ffb5520728ef7de287.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/profile_right_raw.jpg`


### anchor.png — REGENERATED 2026-04-28 (single-subject fix)
First roll produced a double-subject composition (ghosted second face).
Regenerated with an anti-doubling suffix appended to the prompt:
"Single subject only, exactly one person in the entire frame, no
second figure, no mirror, no reflection, no ghosted face, no double
exposure, no twin, no companion." Second roll passed face-lock QA
(clean single subject, characteristic features intact). The original
PNG was overwritten; the v2 raw is at
`anchor_set_raw_2026-04-28/anchor_raw_v2.jpg`.
