# states/ pending generation as of 2026-04-28

Marcus's portrait shipped 2026-04-28 (FLUX-pro v1.1-ultra). State
images (idle / listening / thinking / speaking) are not yet generated
and are blocked on the same face-consistent pipeline that Aurora's
states are blocked on.

**Current portrait:** `../portrait.png` (1024×1024, FLUX-pro,
seed 1182764741)

## To generate states matching the portrait

Same pipeline plan as Aurora's states:

1. Use `../portrait.png` as a reference image
2. Generate via one of:
   - **PuLID** (Pure and Lightning ID Customization)
   - **FLUX redux** (`fal-ai/flux-pro/v1.1/redux`)
   - **IP-Adapter** with FLUX backbone
3. Use Marcus-specific expression modifiers (mid-low male, technical
   pair-programmer feel, not the warm cafe register Aurora uses):
   - **idle:** neutral expression, eyes on screen-direction, slight
     focus tension at the brow, mouth closed.
   - **listening:** head tilted half-degree, eyebrows raised one
     millimeter in genuine attention, eyes engaged, mouth closed
     and slightly inward (not smiling — assessing).
   - **thinking:** gaze angled off-camera mid-distance, eyebrows
     drawn together slightly, fingers possibly mid-pinch in front
     of mouth (out of frame OK), expression of working through it.
   - **speaking:** mouth open mid-word, slight asymmetry, eyes back
     on the listener, expression of "here's the move."
4. Same lighting (warm afternoon study, blurred bookshelf), 1024×1024
   square PNG.

## Sequencing

Aurora's pipeline must verify first (she's been waiting since
2026-04-28). Marcus inherits whatever pipeline ships for Aurora.
Don't generate Marcus's states with a different model than Aurora's
or the cast will read as inconsistent.
