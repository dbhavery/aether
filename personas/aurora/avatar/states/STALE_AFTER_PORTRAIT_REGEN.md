# states/ are STALE as of 2026-04-28

The 4 expression state images (idle / listening / thinking / speaking)
were archived to `../_archived_2026-04-17/states/` when the canonical
portrait was replaced on 2026-04-28.

**Current portrait:** `../portrait.png` (FLUX-pro v1.1-ultra,
center-square crop of candidates_2026-04-28/aurora_03_honey_auburn_cafe.jpg)

**Old states do not match the new portrait** — they were generated
from the gpt-image-1.5 portrait (different model, different
character likeness, different lighting, different background, and
different framing).

## To regenerate states matching the new portrait

The states need a face-consistent generation pass that locks the
candidate-03 likeness across the four expression variants.

**Recommended pipeline:**
1. Use the new `portrait.png` as a reference image
2. Generate via one of:
   - **PuLID** (Pure and Lightning ID Customization) — best for
     identity-preserving generation, available as `fal-ai/pulid` or
     similar.
   - **FLUX redux** (`fal-ai/flux-pro/v1.1/redux`) with reference
     image guidance.
   - **IP-Adapter** with a FLUX backbone.
3. Use the same expression modifier sentences as the prior states
   (see `../_archived_2026-04-17/states/` README.md history if
   that file is preserved, or the original prompt design lives
   inline in each archived state).
4. Output 1024×1024 PNG, square, matching the portrait composition.

## Until regenerated

Code that reads `states/idle.png` etc. will get FileNotFoundError
or fall back to portrait.png depending on the loader. Audit
`packages/l*-*/` for state-image consumers and either:
- Add a fallback to `portrait.png` if state file missing, or
- Block consumers with a clear error pointing to this file.

This is a known temporary state. Do not regenerate states with
gpt-image-1.5 — that breaks the new likeness lock.
