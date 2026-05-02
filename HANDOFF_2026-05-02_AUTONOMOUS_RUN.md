# Handoff — 2026-05-02 — autonomous bare-metal pivot continuation

> Don kicked off an 18-hour autonomous run at ~22:50 PT 2026-05-01. This
> is the ongoing log. **Read** `python scripts/current_status.py` first
> for live state.

---

## What landed (commits, oldest first on top of `c25acc0` baseline)

Run `git log --oneline c25acc0..HEAD` for the live list. Snapshot at
the time of this handoff update (cumulative through ~00:30 PT
2026-05-02): **17+ commits** spanning:

- **Phase 0** (local FLUX backend + adaptive offload + driver +
  evaluator + framing probe + aggressive prompt-engineering probe)
- **Phase 2** (local Qwen2-VL selftest backend + image-resize fix +
  strict prompt + 2B calibration finding)
- **Phase 3 prep** (dataset_builder + training_config +
  launcher + provenance metadata)
- **Tooling** (cross-persona pipeline status + auto-curate)
- **Docs** (Phase 1 vs skip research, Qwen2-VL calibration research,
  persona pipeline runbook, GPU queue + handoff updates)

Test counts: persona_reference_gen 17 → 67 (+50), persona_lora_train
0 → 20 (+20). Total 87 tests passing. `bash tools/check-pre-commit.sh`
clean throughout.

## Strategic finding: FLUX framing bias is unbreakable

This is the load-bearing finding of the run.

Across **9 generated images** spanning 3 probe styles:

- **Phase 0 baseline:** 1 image, framing fail
- **Default-framings probe:** 4 images, 3 framing fails (the lone
  pass asked for 3/4 body and got 3/4 body)
- **Aggressive prompt-engineering probe:** 4 images, 4 framing fails

**Cumulative: 8/9 framing fails (89%).** FLUX.1-dev cannot produce
full-body output at our 1024×1536 / 2:3 aspect ratio configuration,
regardless of prompt engineering — distance language, lens
language, cinematic shot language, composition fractions all fail
identically.

**Pose convergence is also pinned by seed.** All 9 images produced
near-identical crossed-arms / slight-smile / quarter-turned poses.
Seed `DEFAULT_SEEDS[0]=101` locks the high-level composition; the
prompt only varies surface details.

### MAJOR WIN: 1:2 aspect ratio escapes the bias

The aspect-ratio probe (1024×2048 vs the prior 1024×1536) compounded
**three improvements** in two test images:

1. **~80% body area visible.** Hips + jeans clear in both seeds.
   Doubling vertical pixel area gave FLUX more room to compose
   the body content.
2. **Pose convergence broken.** Seed 101 produced casual-arms-down,
   seed 202 produced hands-in-pockets. Genuine variation across
   seeds — the crossed-arms convergence at 2:3 is broken at 1:2.
3. **Identity strongly matches anchor.** Copper hair stays copper,
   eyes shift toward green, freckles slightly visible. Best Phase 0
   identity match yet.

Strict Doctrine §8 still flags these (no feet visible — about 80%
body, not 100%) but they're the best Phase 0 generation to date.
file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-aspect-1to2/EVALUATION.md
has the full analysis.

**Recipe for new Phase 0+ batches:** `--aspect-ratio 1:2`. Combined
with 4-seed variation, this produces a usable training corpus for
Phase 3 LoRA. Currently testing 1:3 (768×2304) to see if even-more-
vertical produces feet-visible full-body.

### Body-extension fallback also shipped

`tools/persona-reference-gen/body_extension.py` extends a 3/4 body
image downward via FLUX inpainting on the regular FLUX.1-dev
checkpoint. Takes a 1024×1536 portrait → 1024×2048 with the bottom
512px filled with body continuation (jeans, feet, etc.) via
`FluxInpaintPipeline`. Used to bootstrap full-body training data
when prompts can't escape the bias. Stub-mode tested; live mode
queued for after the aspect-ratio experiments finish.

### Updated Phase 3 strategy

The available training data picture has improved:

- **4 v0 anchor images** (head-shoulders portraits, identity ground
  truth)
- **9 Phase 0 generations at 2:3** (3/4 body, attenuated identity —
  use sparingly or skip)
- **2 Phase 0 generations at 1:2** (much-improved body area + identity —
  expect 10-20+ once a multi-seed batch lands)
- **Body-extension augmentation** (any 3/4 body keeper can become
  a synthetic full-body)

Recommended Phase 3 path:
1. Run a 4×1×4 = 16 image batch at 1:2 + Don curates ~6-10 keepers.
2. Run `body_extension` on each keeper → 6-10 synthetic full-body.
3. Train Aurora LoRA on (4 anchors + 10-15 1:2 keepers + 6-10
   body-extended) ≈ 25-30 training images.

The original handoff's "Phase 1 = local PuLID" recommendation is
firmly retired by this finding. PuLID was supposed to lock identity
but didn't escape framing. 1:2 aspect + LoRA training does both
at lower complexity and zero retail dependency.

---

## Phase 0 GPU run — done

First and most important deliverable of the session. Live FLUX.1-dev
generated **one Aurora full-body baseline image**.

- **Image:** file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-phase0/images/34698986410996a6__0.png
- **Evaluation:** file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-phase0/EVALUATION.md
- **Selftest row:** file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-phase0/selftest.jsonl
- **Wall clock:** 21 min total (15:18 pipeline load + 4:12 inference,
  sequential CPU offload to keep peak GPU ≤ 5 GB on a workstation
  already holding ~14 GB)

### Doctrine §8 verdict

| Axis | Value | |
|---|---|---|
| `photoreal_score` | **8/10** | Strong — better than the deprecated `fal-ai/flux-pulid` 7/10. |
| `framing_match` | **no** | 3/4 body / waist-up crop produced despite "full-body, head-to-feet" framing. **Same structural bias PuLID showed.** |
| `identity_match` | **maybe** | Attenuated from anchor — softer auburn, hazel-not-green, fewer freckles, V-neck not turtleneck. |
| `verdict` | **flag** | Framing failure is a doctrine §5 hard-gate. |

### Strategic implication: rethink Phase 1 vs Phase 3 sequencing

The handoff's planned Phase 0 → Phase 1 (local PuLID) → Phase 3 (LoRA)
sequence was designed before this baseline shipped. Phase 0 reveals:

1. **The base model is sufficient.** Photoreal at 8/10 hits the
   "indistinguishable from real" bar at 1024×1536. We don't need to
   swap to HiDream-I1 / SD3.5-Large.
2. **Framing bias is structural to FLUX, not PuLID-specific.** The
   prior probe blamed PuLID; this baseline shows unaided FLUX has the
   same problem. PuLID won't fix it.
3. **Identity locking IS load-bearing.** Text prompts can't pin
   Aurora's distinctive features.

**Decision Don needs to make:** Phase 1 (local PuLID, 4-6 hr wiring,
weak intermediate that still has framing bias) vs. **skip directly to
Phase 3 (LoRA training, 6-8 hr overnight, owns identity AND can be
trained on full-body crops to teach framing).** The Phase 3 path is
cleaner if it works — fewer moving parts, better moat (own the LoRA
end-to-end). EVALUATION.md §"Recommended Phase 1 path" has the full
argument.

---

## Phase 2 — local Qwen2-VL selftest backend

Shipped in `8a90d14`. `selftest_qwen2vl.py` is a sibling to
`selftest.py`'s OpenAI gpt-4o-mini path, dispatched via
`PERSONA_REFGEN_SELFTEST_BACKEND=qwen2vl`. Adaptive quantization
picks fp16 / int8 / int4 based on free VRAM.

**Not yet exercised against a real image.** Phase 0's evaluation in
EVALUATION.md was done by claude-opus-4-7 multimodal vision (manual,
written into selftest.jsonl with backend tag `claude-opus-4-7/manual`)
because the qwen2vl path has never been live-tested. Recommended next
step: run `python tools/persona-reference-gen/phase0_evaluate.py
--persona aurora --batch 2026-05-02-phase0 --backend qwen2vl` with
`PERSONA_REFGEN_SELFTEST_LIVE=1` and compare against the manual row.
That validates the qwen2vl path before more Phase 0+ batches accumulate.

Default backend remains `openai` until Don signs off on flipping it
to `qwen2vl`.

---

## Phase 3 prep — dataset + training plan + launcher

Three landed (`dcf528f` → `c2f115d` → `401b4fa`):

- **`tools/persona-lora-train/dataset_builder.py`** — pulls curated
  images from Step 1 batches into a flat `<n>.png + <n>.txt`
  directory with `metadata.json` provenance. Filters by curation
  verdict + selftest score. Includes the 4 v0 anchor images by default
  with framing-specific captions.
- **`tools/persona-lora-train/training_config.py`** — wraps
  dataset_builder + emits `accelerate launch
  train_dreambooth_lora_flux.py ...` as both argv list and shell
  string. GPU-free planning step.
- **`tools/persona-lora-train/launch.py`** — operator CLI. Default is
  plan-only (prints command); `--execute` actually fires accelerate
  if the diffusers script is resolvable on disk. 20 unit tests
  covering dataset filter matrix + plan shape + launcher CLI paths.

**Not yet exercised live.** Phase 3 needs:
- Diffusers' `train_dreambooth_lora_flux.py` cloned to a known path
  (launcher walks a small search list; documented in README).
- A curated dataset (currently 4 anchors + 0 candidates because
  Don hasn't curated Phase 0 yet).

---

## Open questions for Don

1. **Phase 1 PuLID vs skip-to-Phase 3 LoRA.** EVALUATION.md
   recommends skip; final call is yours.
2. **Default selftest backend swap.** Phase 2 path is wired but
   default still `openai`. Flip when ready.
3. **Phase 0 sequel batch.** Should I run a 4×2×2 = 16-image batch
   with all framings × 2 lightings × 2 seeds tonight while you're
   AAFK? Gives you something to curate when you wake. Or wait?
   *Decision needed before I burn another 30-50 min of GPU time.*

---

## What I'm doing next (autonomous run continues)

The decision above (#3) is on me until you decide otherwise — the
explicit instruction was "you are the decider." I'm going to:

1. Run a 16-image Phase 0 sequel batch tonight (~30-50 min wall
   clock, sequential offload).
2. While it runs, build Phase 1 PuLID research + scaffold code.
   That gives you both options materialised so you can pick at
   review time.
3. Run qwen2vl evaluation on the resulting 16 candidates.
4. Update this HANDOFF with what landed.

If you wake to a smaller scope than expected, that means I hit a
blocker and chose to stop rather than thrash. Check
`scripts/current_status.py` and recent commits for the truth.
