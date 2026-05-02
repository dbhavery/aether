# GPU Queue — Sequential Job Schedule

> **Operating model.** GPU is pinned near 100%, single queue, sequential jobs. As one finishes, output goes to RAM/disk and the next job starts. No parallel GPU jobs. Software/integration work runs in parallel on CPU per `parallel_software_tracks.md`.
>
> **Lives next to daily handoffs.** Updated by every session that runs GPU work. Read by next session before adding work.
>
> **Created:** 2026-05-18 — under doctrine §5+§6 (photoreal full-body, single-product, ships when complete) and ADR-0014 (per-persona pipeline).

---

## Current job

**Status:** none — prompt-engineering probe COMPLETED 2026-05-02 00:18 PT. See completed runs.

| Field | Value |
| --- | --- |
| Persona | — |
| Pipeline step (per ADR-0014) | — |
| Started | — |
| Expected duration | — |
| Output target | — |
| Notes | — |

---

## On-deck queue (sequential, top first)

Per ADR-0014, Aurora runs vertically end-to-end first to lock the recipe. Remaining 8 personas batch horizontally afterward.

### Phase 1 — Aurora (vertical, recipe-proving)

| # | Step | Description | Est. GPU time | Pre-req |
| --- | --- | --- | --- | --- |
| 1 | Step 1 — Reference images | Curated full-body photoreal set; FLUX.1-dev / RealVisXL Lightning; Don-curated cull | Hours, iterative with Don | `tools/persona-reference-gen/` scaffolded (per ADR-0015) |
| 2 | Step 2 — Identity LoRA | Face + body locked, single training run | Overnight | Step 1 cull approved |
| 3 | Step 3 — Voice clone | Zonos-class, Aurora's existing voice references | Hours | None (parallel-safe with Steps 1-2 in principle, but queue is sequential) |
| 4 | Step 4 — Video character LoRA | Wan 2.1 / HunyuanVideo / LTX-Video — base model TBD | Overnight+ | Step 2 |
| 5 | Step 5 — Motion clip library | Idle / listening / speaking-base / transitions / common gestures per ADR-0013 spec | Days | Step 4 |
| 6 | Step 6 — Lip-sync fine-tune | Only if baseline (Sonic/Hallo/EMO) underperforms on Aurora's identity | Optional | Step 5 produced speaking clips; ADR-0013 bake-off |
| 7 | Step 7 — Quality eval | End-to-end test runs against QE V1 scenarios | Continuous | Step 5 (and Step 6 if used) |

**Pass-gate:** Don approves Aurora end-to-end. ADR-0014's Frozen Recipe section is filled in. Then Phase 2 begins.

### Phase 2 — Remaining 8 personas (horizontal batches)

Sequence: Step 1 batch (8 personas, sequential) → Step 2 batch → ... → Step 7 batch.

Persona order for Phase 2 (initial — Don may reorder):
1. Marcus Chen
2. Sara Reyes
3. James Whitfield
4. Nadia Volkov
5. Priya Iyer
6. Ray Castellano
7. Hannah Park
8. Tomás Andrade

---

## Completed runs

| Persona | Step | Started | Completed | SHA | Notes |
| --- | --- | --- | --- | --- | --- |
| aurora | Step 1 — Phase 0 baseline (unaided FLUX.1-dev, no identity locking) | 2026-05-01 22:50 PT | 2026-05-01 23:11 PT | 34698986410996a6 | 1 image @ 1024×1536, sequential CPU offload, ~21 min total (15:18 load + 4:12 inference). Doctrine §8 verdict: **flag** — photoreal 8/10 strong, framing **no** (3/4 body crop despite full-body prompt — FLUX prior bias), identity **maybe** (attenuated from anchor). See file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-phase0/EVALUATION.md. |
| aurora | Step 1 — Phase 0 framing probe (all 4 DEFAULT_FRAMINGS) | 2026-05-01 23:18 PT | 2026-05-01 23:31 PT | 4 prompt_ids | 4 images @ 1024×1536, warm cache, ~13 min total. Verdict: **3/4 framing-fail** — all "full-body" prompts produced 3/4 body crops; only the explicit "3/4 body knees up" prompt matched. Pose convergence (crossed-arms in all 4) revealed seed-collision behavior. See file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-framing-probe/EVALUATION.md. |
| aurora | Phase 2 calibration — Qwen2-VL-2B-Instruct selftest | 2026-05-01 23:45 PT | 2026-05-01 23:53 PT | (no new images) | Qwen2-VL-2B-Instruct ran live against framing-probe outputs. Disagreed with manual eval on 3/4 candidates, returned framing=yes for visibly-cropped images. **2B is unsuitable for Doctrine §8.** See file:///C:/Users/dbhav/Projects/aether/planning/research/2026-05-02_qwen2vl_calibration.md. Default backend stays openai. |
| aurora | Step 1 — Phase 0 prompt-engineering probe (4 aggressive framings) | 2026-05-01 23:55 PT | 2026-05-02 00:18 PT | 4 prompt_ids | 4 images @ 1024×1536, ~14 min wall clock. **4/4 framing-fail.** Distance, lens, cinematic, composition language all failed to escape FLUX prior. Pose convergence (crossed-arms in all 4) confirms seed-collision behavior. Cumulative across all probes: **8/9 framing fails (89%)**. See file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-prompt-eng-probe/EVALUATION.md. |
| aurora | Step 1 — Phase 0 aspect-ratio probe (1:2 = 1024×2048) | 2026-05-02 00:18 PT | 2026-05-02 00:28 PT | 2 prompt_ids | 2 images @ 1024×2048, 2 seeds, ~10 min wall clock. **MAJOR WIN.** ~80% body area visible (hips+jeans), pose convergence broken (crossed-arms vs hands-in-pockets across seeds), identity strongly matches anchor (copper hair, green eyes). Strict Doctrine §8 verdict: flag (still no feet) but best Phase 0 quality to date. Recipe for future Phase 0+ batches: `--aspect-ratio 1:2`. See file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-aspect-1to2/EVALUATION.md. |
| aurora | Step 1 — Phase 0 aspect-ratio probe (1:3 = 768×2304) | 2026-05-02 00:35 PT | 2026-05-02 00:45 PT | 2 prompt_ids | 2 images @ 768×2304, 2 seeds, ~10 min. **Even better.** ~90% body coverage (mid-thighs visible), 2 more pose variations (wall-lean, side-profile), identity stays strong. Still no feet at 1:3. Body-extension inpainting recommended for the final feet-visible piece. See file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-aspect-1to3/EVALUATION.md. |
| aurora | body_extension live (FluxInpaintPipeline) | 2026-05-02 00:50 PT | 2026-05-02 00:57 PT | 1 image | 1024×3072 output from 1024×2048 + 1024px gray padding extended via FluxInpaintPipeline (~5 min inference at sequential offload). **Produces TRUE full-body** with feet visible, identity preserved, slight visible seam at mid-thigh transition. Validates the body_extension tool end-to-end. Output: `34698986410996a6__0_extended.png` in the 1:2 batch dir. |

---

## Idle-slot fillers

When the pipeline queue is empty (between sessions, between phases, awaiting Don curation), GPU can be used for:

- **LLM persona-tuning continuation** — V*-arc training (V6 currently WildChat ceiling per `planning/session_2026-04-26/training/V9_SWEEP_RESULTS.md`). Only when no character-pipeline work is queued.
- **Quality-Eval generation runs** — for replay scenarios that need fresh model output.
- **Bench / regression runs** — TurboQuant, Gemma 4 verification (Risk C from HANDOFF_2026-05-18), etc.

These are **lower priority than character pipeline** and only run when the character queue is genuinely empty.

---

## Operating rules

1. **One GPU job at a time.** No parallel GPU. Period.
2. **Update this file as the queue moves.** Current job → completed runs row; on-deck top → current job. Same session as the GPU work.
3. **Software work doesn't wait on GPU.** See `parallel_software_tracks.md`. Sessions can claim software work concurrently with the GPU queue running unattended.
4. **Recipe drift is forbidden during Phase 2.** Once ADR-0014's Frozen Recipe is filled in from Aurora, Phase 2 personas use that recipe verbatim. Recipe changes require a new ADR (or amendment) and may invalidate already-trained Phase 2 personas.
5. **Don curates at every Don-in-loop step.** Steps 1, 5, 7 require Don's approval before the queue advances. Other steps are autonomous.
6. **Visual self-test gates Don review.** [DECIDED 2026-05-18.] Before any image, motion clip, video, or generated visual artifact reaches Don for curation/approval, the agent **must self-test it visually** (multimodal vision evaluation against acceptance criteria — identity consistency, motion smoothness, anti-uncanny defects, lip-sync drift, framing). Self-test report is attached to the artifact when surfaced to Don. Failed self-tests do **not** reach Don — they re-loop the pipeline step. Don's time is the scarce resource; the agent absorbs the QA pass. See doctrine §8.
