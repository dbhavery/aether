# Avatar assets for persona 'nadia_volkov' (display_name: Nadia Volkov)

Status: **NOT YET GENERATED.** Anchor-schema spec drafted; awaiting
Don's approval on FLUX-pro spend after Aurora anchor eyeball-check.

Backend: `fal.ai` model `fal-ai/flux-pro/v1.1-ultra`. Raw output
2752 × 1536. Four calls per pack.

Character: 27 F Slavic features, sharp cheekbones, pale skin, dark
hair, "your premise is wrong" archetype — precise rigorous skeptic.

---

## Prompt: `anchor.png` — canonical face reference

```text
Photorealistic neutral reference portrait of an Eastern European woman in her late 20s, shoulder length straight dark brown hair parted simply, sharp angular cheekbones, pale fair skin with a few small natural freckles, intense hazel eyes set wide apart, dark eyebrows with a natural arch, neutral resting expression, mouth softly closed with no smile, looking directly at the camera. Even diffuse soft light with no harsh shadows, slightly cool undertone (not warm). Plain neutral pale grey background, no objects in frame, simple wardrobe of a fitted black turtleneck. Real skin texture with visible pores and natural imperfections, no heavy makeup, slim athletic build. Shot on 85mm at f/4 for clean focus across the face, sharp on the eyes. Square head and upper shoulders composition, anchor reference photo style: calm, present, not styled, slightly serious resting face is correct. Avoid plastic skin, perfect symmetry, glamour pose, anime, gradient backgrounds, side rim lighting, motion blur, stage-Russian villain styling.
```

## Prompt: `portrait.png` — personality picker shot

```text
Photorealistic candid portrait of an Eastern European woman in her late 20s, straight dark brown hair, sharp cheekbones, intense hazel eyes mid-question with a slight skeptical raise of one eyebrow, faint reluctant half-smile that reads as okay your point is interesting. Wearing a fitted black turtleneck, sleeves pushed to the forearms, holding a thin notebook with a pen tucked behind one ear. Cool late-afternoon library light, blurred bookshelves. Slim athletic build, simple silver stud earrings, no other jewelry. Real skin texture with visible pores and natural imperfections, slightly cool undertone. Shot on 85mm at f/1.8. Reads as a precise sparring partner who is on your side but won't agree with you to be nice. Avoid glamour pose, plastic skin, perfect symmetry, anime, AI tropes, stage-Russian villain styling.
```

## Prompt: `profile_left.png` — 3/4 left angle

```text
Photorealistic 3/4 left profile of an Eastern European woman in her late 20s, shoulder length straight dark brown hair, sharp cheekbones, hazel eyes, neutral resting expression, mouth softly closed, head turned 30 degrees right (showing her left 3/4). Even diffuse soft light, no harsh shadows, slightly cool undertone. Plain neutral pale grey background, fitted black turtleneck. Real skin texture with visible pores. 85mm at f/4. Anchor-reference lighting. Avoid plastic skin, perfect symmetry, glamour pose, anime, side rim lighting.
```

## Prompt: `profile_right.png` — 3/4 right angle

Same as profile_left, head turned 30 degrees left (showing her right 3/4).

## Regen nudges if anchor reads off-character

- "...late 20s reading as someone with a graduate degree and an opinion, not late teens, not mid-30s..." if age reads off
- "...angular cheekbones natural, not retouched-flawless..." if face reads styled
- "...resting face slightly serious is correct, not unhappy, not bored..." if expression reads cold-cold instead of focused-cold

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
- source URL: https://v3b.fal.media/files/b/0a9828d0/0qzC4vO_zZYpGsvbg4iHz_7c8164e8604c47fca5da35f7b97755ec.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/anchor_raw.jpg`

### portrait.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828d1/pU3aBA7pPc5tJcc1OY-za_3e97f56cf2614374812a31204f404b47.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/portrait_raw.jpg`

### profile_left.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828d2/LcyliR5tevSdEvraMxyrd_611e929b31cb4a13a0c7b4a1ca430caf.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/profile_left_raw.jpg`

### profile_right.png — generated 2026-04-28
- backend: `fal.ai`
- model: `fal-ai/flux-pro/v1.1-ultra`
- aspect_ratio: `16:9`
- request_id: `?`
- source URL: https://v3b.fal.media/files/b/0a9828d3/20zQDt5eKcsNfvERXHr4w_da97487dba0b4b5c92959297610bf0c5.jpg
- raw output: kept at `anchor_set_raw_2026-04-28/profile_right_raw.jpg`
