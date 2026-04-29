# Avatar assets for persona 'priya_iyer' (display_name: Priya Iyer)

Status: **NOT YET GENERATED.** Anchor-schema spec drafted; awaiting
Don's approval on FLUX-pro spend after Aurora anchor eyeball-check.

Backend: `fal.ai` model `fal-ai/flux-pro/v1.1-ultra`. Raw output
2752 × 1536. Four calls per pack.

Character: 47 F Indian-American, polished-warm, senior operator,
strategic-executive archetype.

---

## Prompt: `anchor.png` — canonical face reference

```text
Photorealistic neutral reference portrait of an Indian American woman in her late 40s, shoulder length straight black hair with a few natural silver strands at the temples, parted simply, warm dark brown eyes with kind crow's feet, deep medium-brown skin tone, neutral relaxed expression, mouth softly closed with the very faintest hint of a smile, looking directly at the camera. Even diffuse soft light with no harsh shadows, very subtle warm undertone. Plain neutral pale beige background, no objects in frame, simple wardrobe of a fitted charcoal blazer over a cream silk blouse, no statement jewelry. Real skin texture with visible pores and natural imperfections that read as a real face at her age, slim build. Shot on 85mm at f/4 for clean focus across the face, sharp on the eyes. Square head and upper shoulders composition, anchor reference photo style: calm, present, not styled, polished-without-over-styling. Avoid plastic skin, perfect symmetry, glamour pose, anime, gradient backgrounds, side rim lighting, motion blur, age-erased retouching.
```

## Prompt: `portrait.png` — personality picker shot

```text
Photorealistic candid portrait of an Indian American woman in her late 40s, shoulder length straight black hair with a few natural silver strands at the temples, warm dark brown eyes with crinkles from a real smile, slight knowing smile that reads as I have heard this version of the question before. Wearing a fitted charcoal blazer over a cream silk blouse, simple gold studs, no other jewelry. Soft late-morning office light, blurred floor-to-ceiling windows behind, a clean leather notebook and a pen on a wooden table beside her. Slim build, polished without over-styling. Real skin texture with visible pores and the faint natural lines of a real face at her age. Shot on 85mm at f/1.8. Reads as a senior operator who is on your side and respects your time. Avoid glamour pose, plastic skin, perfect symmetry, anime, AI tropes, retouched-out wrinkles.
```

## Prompt: `profile_left.png` — 3/4 left angle

```text
Photorealistic 3/4 left profile of an Indian American woman in her late 40s, shoulder length straight black hair with silver strands at the temples, warm dark brown eyes, neutral relaxed expression, mouth softly closed, head turned 30 degrees right (showing her left 3/4). Even diffuse soft light, no harsh shadows, subtle warm undertone. Plain neutral pale beige background, charcoal blazer over cream silk blouse. Real skin texture with visible pores and natural age-appropriate lines. 85mm at f/4. Anchor-reference lighting. Avoid plastic skin, perfect symmetry, glamour pose, anime, age-erased retouching.
```

## Prompt: `profile_right.png` — 3/4 right angle

Same as profile_left, head turned 30 degrees left (showing her right 3/4).

## Regen nudges if anchor reads off-character

- "...late 40s reading as a senior operator with twenty years of context, not mid-30s, not 60s..." if age reads off
- "...natural silver at the temples, not artificially-coloured highlights, not full grey..." if hair reads off
- "...polished-without-over-styling, not retouched-flawless, not magazine-cover..." if face reads too perfect

---

See file:///C:/Users/dbhav/Projects/aether/personas/marcus_chen/avatar/README.md
for full schema explanation. Same conventions apply.
