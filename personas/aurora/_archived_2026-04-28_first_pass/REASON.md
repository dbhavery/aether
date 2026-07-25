# Why this is archived (2026-04-28 night)

Aurora's first-pass avatar pack shipped 2026-04-28 morning under
the thin schema (single 1024×1024 headshot — `portrait.png` — plus
4 expression states + voice).

The portrait was FLUX-pro v1.1-ultra "candidate 03" — a cafe-candid,
honey-auburn, mid-laugh shot. Don picked it from a 4-candidate
spread under the brief "good-looking warm friend."

**Why it's archived:** Don raised the anchor-reference critique
later that day. Single candid shots — laughing-mouth-open, off-axis
gaze, hard side-light, busy background — optimize for "looks like a
real photograph" but are suboptimal as the canonical neutral face
reference for the pack.

A clean anchor reference works best with even diffuse light, neutral
relaxed expression, mouth closed, looking forward, simple background.
Aurora's cafe-candid violates every one of those.

**Second-pass approach:** ship `anchor.png` (canonical neutral
reference) AS WELL AS `portrait.png` (personality
shot for the picker UI). The cafe-candid shot will be regenerated
or re-purposed as the personality `portrait.png`; a new neutral
anchor will be the canonical face reference.

See file:///C:/Users/dbhav/Projects/aether/personas/CHARACTERS.md
for the new asset schema.

**Voice and persona.yaml are NOT archived** — they live at the
canonical paths (`personas/aurora/voice/` + `personas/aurora/persona.yaml`).
Only the avatar/ contents shipped under the wrong schema.

## Inside this archive

- `portrait.png` — the cafe-candid 1024×1024 (FLUX-pro, seed 1181057909)
- `avatar_README.md` — first-pass provenance
- `_archived_2026-04-17/` — the original gpt-image-1.5 portrait + 4 states
  (the layered archive — the gpt-image generation was the *first* first-pass)
- `states/STALE_AFTER_PORTRAIT_REGEN.md` — the placeholder marker that
  was in flight when this whole avatar dir got archived
- `candidates_2026-04-28/` — the 4 FLUX-pro candidates Don picked from
  (01 honey-blonde sunroom, 02 auburn kitchen, 03 honey-auburn cafe
  [Don's pick], 04 auburn lamp), plus the 1024-square crop of 03
