# Phase 1 Research — Local Identity Locking Options for FLUX.1-dev

> Research note compiled during the autonomous run on 2026-05-02. Phase 0
> baseline is shipped; this surveys Phase 1 (local identity-locking)
> implementation paths so Don can pick at review time.

## Background

Phase 0 baseline (file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-phase0/EVALUATION.md)
established that:

1. Unaided FLUX.1-dev produces 8/10 photoreal but **cannot lock Aurora's
   identity from prompt alone** — distinctive features (vibrant copper
   hair, bright green eyes, freckles) attenuate to a generic
   strawberry-blonde / hazel-eyed Aurora-adjacent woman.

2. FLUX has a **structural framing bias toward portrait crops**, even
   when explicitly prompted for full-body. This was observed both in
   the deprecated fal-PuLID probe and in the Phase 0 unaided baseline —
   so it's NOT a PuLID-specific problem, it's a FLUX prior.

Phase 1 of the bare-metal pivot was originally scoped as "local PuLID
weights for FLUX, custom IdentityConditioner class wrapping the
diffusers pipeline." This document surveys what that actually entails
and what the alternatives are.

## Options

### Option A — Local PuLID-FLUX (the original Phase 1 plan)

**What:** Wire up `guozinan/PuLID` weights into FluxPipeline. Identity
conditioning via face-embedding injection through transformer hooks.

**Pros:**
- Strong identity lock (the strongest single-image identity method on
  FLUX as of early 2026).
- Per-generation control: identity weight slider, multiple reference
  images, etc.
- Doesn't require training time — works zero-shot on Don's anchor.

**Cons:**
- Requires `insightface` + `onnxruntime` (heavy deps, GPU + CPU compute
  paths, pre-trained face detection/recognition models).
- Requires vendored PuLID inference code — `ToTheBeginning/PuLID`'s
  implementation isn't pip-installable as a clean library; it's a
  research repo with a custom inference loop.
- **Doesn't fix the framing bias.** PuLID enforces face identity, not
  body framing. The fal-PuLID probe produced the same bust-crop bias
  as unaided FLUX.
- Effort: 4-6 hr to wire, plus potentially significant tweaking of
  PuLID's identity_weight + diffusion guidance to balance identity vs
  framing prompt adherence.

**VRAM:** PuLID weights are small (~600 MB), but loaded alongside
FLUX-fp16 (~24 GB), insightface face detector (~50 MB GPU + ~150 MB
CPU), and the inference KV cache. With sequential offload the same
~3-4 GB peak applies.

### Option B — Local InstantID for FLUX

**What:** Like PuLID but with InstantID's pose-conditioning branch.

**Pros:**
- Better at preserving facial geometry across generation styles.
- Slightly easier integration via diffusers' built-in IP-Adapter
  loaders.

**Cons:**
- Same insightface dep.
- InstantID is officially SDXL-first; FLUX support is community-port,
  less mature than PuLID-FLUX.
- Still doesn't fix the framing bias.

### Option C — Identity LoRA training (the original Phase 3, considered as Phase 1 substitute)

**What:** Train a per-persona LoRA on the 4 anchor images plus 5-15
hand-curated Phase 0 generations. Skip PuLID entirely.

**Pros:**
- **Owns identity end-to-end.** No retail dep, no third-party identity
  model. The LoRA IS the identity lock.
- **Can teach framing.** If the training set includes full-body crops
  (curated from Phase 0 batches), the LoRA learns Aurora's identity
  AT full-body framing — fixing both problems in one pass.
- Reusable across all downstream stages (Phase 4 video character LoRA
  builds on it; Phase 5 motion clips inherit it).
- Already scaffolded — `tools/persona-lora-train/` ships with
  `dataset_builder` + `training_config` + `launch.py` ready to fire.

**Cons:**
- Requires curated training data. Phase 0 produced ONE image; we'd
  need 5-15 more to bootstrap, all with framing-fix attention.
- 6-8 hours overnight per LoRA on the 3090 Ti.
- Training failure modes: undertrained (weak identity), overtrained
  (single-pose lock-in, rigidity), wrong rank (too small = weak,
  too large = overfit). Empirical tuning required.

**VRAM:** 10-15 GB peak with gradient checkpointing on. Sequential
offload not applicable (training needs all weights addressable).

### Option D — Hybrid (PuLID for bootstrapping, then LoRA)

**What:** Use PuLID to generate 30-50 Aurora candidates with locked
identity. Curate. Train LoRA on the curated set. PuLID becomes
"training-data scaffolding," LoRA becomes the production lock.

**Pros:**
- Both identity locking layers inform each other.
- PuLID's framing bias is acceptable here because it produces training
  data, not ship artifacts — we manually crop or augment to expose
  full-body.

**Cons:**
- All of A's costs PLUS C's costs.
- Two failure surfaces.

## Recommendation

**Option C — skip directly to LoRA training.** Reasoning:

1. The framing bias is the bigger problem and PuLID doesn't solve it.
   A LoRA trained on full-body crops learns BOTH identity AND framing.
2. We already shipped the Phase 3 scaffold during the autonomous run.
   The marginal cost of running training is "curate ~10 images + run
   accelerate launch overnight."
3. Owning the LoRA end-to-end matches the bare-metal pivot's spirit:
   "indistinguishable from a real human" requires owning every layer.
   Adding insightface + PuLID adds complexity without addressing the
   framing bias that's the actual bottleneck.

Accepting Option C means **abandoning the Phase 1 step entirely** and
renumbering: Phase 0 (baseline, done) → Phase 3 (LoRA training, ready).

## Required pre-work for Option C

1. Generate 8-16 more Aurora candidates with varied framings/lightings.
   The framing-probe batch (running now, ~30 min) provides 4. A
   followup 4×2×1 = 8-image batch with the existing axes covers more
   surface. Or hand-craft prompts that try to escape the framing bias
   (e.g. "long shot from 3 meters away, person centered between crown
   and feet").

2. Don curates the keep set. Even if framing fails, identity-rich
   candidates can be cropped to body-only and fed to the LoRA. Don's
   eye is the final filter.

3. Augment if needed: if curated set is <8 images, augment from the
   anchor set with explicit body-region crops using PIL — the LoRA
   doesn't care about resolution, only identity.

4. Run `python tools/persona-lora-train/launch.py --persona aurora
   --workdir build/lora-train/aurora-v1`. Plan-only first; inspect
   `training_config.json`. Then `--execute`.

## What I'm NOT doing during the autonomous run

- Installing insightface (heavy dep, would persist; needs Don's call).
- Cloning huggingface/diffusers (already documented for the launcher).
- Generating production-quality LoRA without Don's curation in the loop
  (Doctrine §8 has Don curating Step 1, that's the boundary).

## Selftest backend swap (orthogonal)

Phase 2 (`selftest_qwen2vl.py`) is wired but never run live. Before
rolling it out as default, recommend running `phase0_evaluate.py
--backend qwen2vl` against the framing-probe outputs once they land
and comparing scores to the manual claude-opus-4-7 evaluation. If
agreement is reasonable, flip the default in `selftest._resolved_backend`.
