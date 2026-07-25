# Why this is archived (2026-04-28 night)

Marcus Chen's first-pass avatar pack shipped 2026-04-28 evening
under the thin schema (single 1024×1024 headshot — `portrait.png`
— plus a placeholder STALE marker for state images, plus voice +
hand-authored system prompt).

The portrait was FLUX-pro v1.1-ultra, seed 1182764741, agent's
first-pick (no candidate spread for Marcus — generated and
committed in one shot under Don's autonomy directive). Asian-
American man late 30s, charcoal henley, wire-frame glasses, study
background.

**Why it's archived:** Same reason as Aurora's first-pass — the
single shot was a personality-style image (specific lighting,
specific framing, specific background), not a clean neutral
face anchor.

**Second-pass approach:** new asset schema requires `anchor.png`
(canonical neutral face reference) plus `portrait.png` (personality
shot) plus `profile_left.png` + `profile_right.png` (3/4 angles).
Marcus's existing portrait may be re-used as his personality shot
since his personality-image criteria are satisfied; a new anchor
shot must be generated regardless.

See file:///C:/Users/dbhav/Projects/aether/personas/CHARACTERS.md
for the new asset schema.

**Voice and persona.yaml are NOT archived** — they live at the
canonical paths. Only the avatar/ contents shipped under the wrong
schema.

## Inside this archive

- `portrait.png` — the 1024×1024 center-crop (FLUX-pro, seed 1182764741)
- `portrait_source.jpg` — the 2752×1536 raw FLUX output before crop
- `avatar_README.md` — first-pass provenance
- `states/STALE_AFTER_PORTRAIT_REGEN.md` — the states-pending marker
