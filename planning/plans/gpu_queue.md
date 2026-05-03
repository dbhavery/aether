# GPU Queue — Sequential Job Schedule

> **Operating model.** GPU is pinned near 100%, single queue, sequential jobs. As one finishes, output goes to RAM/disk and the next job starts. No parallel GPU jobs. Software/integration work runs in parallel on CPU per `parallel_software_tracks.md`.
>
> **Lives next to daily handoffs.** Updated by every session that runs GPU work. Read by next session before adding work.
>
> **Created:** 2026-05-18 — under doctrine §5+§6 (photoreal full-body, single-product, ships when complete) and ADR-0014 (per-persona pipeline).

---

## Current job

**Status:** queued for clean-slate overnight run. Smoke #8 saturated at 23.5 GB used while idle was 11.9 GB — meaning the training process itself only added ~11.6 GB. **If Don closes everything (browsers, VS Code, Claude Code, Discord, ChatGPT, Isabelle+watchdog, gaming launchers, etc.) to ~1.5-3 GB idle, training fits at ~13-15 GB total with room to spare.** Runbook prepped at file:///C:/Users/dbhav/Projects/ai-toolkit/OVERNIGHT_TRAINING_RUNBOOK.md, full 1500-step config at file:///C:/Users/dbhav/Projects/ai-toolkit/config/aurora_v1_full.yaml, launcher at file:///C:/Users/dbhav/Projects/ai-toolkit/TRAIN_AURORA_OVERNIGHT.bat. Sampling disabled (saved smoke #8 from sample-related saturation). Estimated runtime 3-5h; checkpoints every 250 steps. Don kicks off via `start /B` from a fresh cmd, closes Claude Code, sleeps. Morning: trained `aurora_v1.safetensors` at `aether/build/lora-train/aurora-aitk/output/aurora_v1/`.

| Field | Value |
| --- | --- |
| Persona | aurora |
| Pipeline step (per ADR-0014) | Step 2 — Identity LoRA training (BLOCKED — Option A failed) |
| Started | n/a |
| Expected duration | n/a |
| Output target | n/a |
| Notes | Body-extension batch produced 6 new full-body siblings + 1 from autonomous run = 7 in curation-1to2 + 1 in aspect-1to2 = 8 body_extended total. Training corpus is 32 images (4 anchors + 20 base + 8 body-extended). Smokes #5 + #6 both confirmed VRAM saturation: FLUX-dev's 12B transformer + LoRA optimizer + activations + Don's compositor baseline (~8-9 GB) leaves zero training headroom on 24 GB cards. Throughput flags (cache_latents/tf32/8bit-adam) help when there's free VRAM — they cannot escape saturation. Don's revised pick: B) download FLUX.1-Schnell (~20 GB), C) cloud rental, D) multi-night with smaller config. |

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
| aurora | Step 1 — Phase 0 curation batch (1:2, 4×1×4=16 images) | 2026-05-02 01:00 PT | 2026-05-02 02:43 PT | 16 prompt_ids | 16 images @ 1024×2048, 4 framings × 4 seeds, ~103 min wall clock. Real curation set for Don. Identity strong + diverse poses (crossed-arms, hands-in-pockets, smile-leaning-on-window, etc.) + ~80% body coverage. See `personas/aurora/_pipeline/step1_references/2026-05-02-curation-1to2/`. |
| aurora | LoRA training smoke test #1 (FLUX-dev, 1024 res, rank 16) | 2026-05-02 01:54 PT | 2026-05-02 03:25 PT (killed) | none | Pipeline launched cleanly after fixing diffusers HEAD install + dataset images/captions split. Throughput too slow at 1024 res + grad checkpointing — 90+ min wall clock without first checkpoint. Killed. See file:///C:/Users/dbhav/Projects/aether/planning/research/2026-05-02_lora_training_smoke_test.md. |
| aurora | LoRA training smoke test #2 (FLUX-dev, 512 res, rank 16) | 2026-05-02 03:30 PT | 2026-05-02 04:00 PT (killed) | none | Same throughput problem at 512 — appeared not to escape the bottleneck. Killed. Don needs to pick a different config (smaller base model / cloud / multi-night training) before launching the full 1500 steps. |
| aurora | body_extension batch P2-P7 (FluxInpaintPipeline, sequential offload) | 2026-05-02 07:07 PT | 2026-05-02 08:09 PT | 6 prompt_ids | 6 new full-body siblings via `batch_body_extend.py` driver. Inputs: P2 7082a50ee6b16b67 + P3 77efd428589ad0f8 + P4 ed245ab7187910af + P5 0bb022b3f50b4723 + P6 e4d7a7572ee951d1 + P7 01e97da6f6b909a3. 62 min wall clock (15 min cold load + 47 min inference). Image 1 ~29 min cold-cache; subsequent ~7 min warm. **Quality:** strong identity preservation, photoreal 9/10 across all 6. Wardrobe variation: P1+P2+P3 bare feet on hardwood, P4 cropped at ankles, P5 sitting legs-forward, P6 light grey sneakers, P7 white sneakers. Training corpus now 32 images. See file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-curation-1to2/EVALUATION.md. |
| aurora | LoRA training smoke test #5 (FLUX-dev, 512 res + cache_latents + tf32 + 8bit-adam) | 2026-05-02 08:11 PT | 2026-05-02 09:21 PT (killed) | none | Throughput-tuned config still hit the VRAM saturation problem when Isabelle held ~10 GB at baseline. GPU pushed to 23.9 GB / 24 GB. 70 min wall clock without first checkpoint. Killed. **Don picks A/B/C/D** per file:///C:/Users/dbhav/Projects/aether/planning/research/2026-05-02_lora_smoke_session2.md. |
| aurora | LoRA training smoke test #6 (Don picked A: stop Isabelle + apps; FLUX-dev, 512 res, throughput-tuned) | 2026-05-02 18:04 PT | 2026-05-02 18:54 PT (killed) | none | Don picked Option A. Stopped Isabelle PID 23464; killed 12 non-essential apps (voiceflow, Tobii, steamwebhelper, EpicWebHelper, EpicGamesLauncher, GoPro Webcam, Overwolf×2, LinkedIn, Photos, ChatGPT, asus_framework). VRAM headroom went from 8.7→11 GB free at idle, but during training pushed to 22.7 GB used / 1.6 GB free — still effectively saturated. Pipeline reached step 1 in **1143 s/step** (~19 min/step). 1500 steps × 19 min = 476 h = ~20 days. **Option A unviable on 3090 Ti hardware floor.** Phase3 `setdefault` quirk: smoke phase ran 1500 steps because explicit `--max-train-steps 1500` overrode the smoke=50 default. Killed PID 67644 (training) + 66044 (accelerate). Awaiting Don's revised pick: B (Schnell), C (cloud), D (multi-night). |
| aurora | LoRA training smoke test #7 (technical-decider pivot to B: FLUX-Schnell, 512 res, throughput-tuned, smoke=50) | 2026-05-02 19:51 PT | 2026-05-02 20:35 PT (killed) | none | Don delegated decision; agent picked B. Schnell downloaded clean (10:26 wall clock, 54 GB on disk). Direct launch.py invocation with `--smoke-test` (50-step override held this time). Schnell loaded 4× faster than dev (8 s/it shards vs 36). Cache latents completed in ~11 min but slowed under memory pressure (7→52 s/it). Training reached step 0/50 at 20:09:30 PT and **made zero progress in the next 25 min**. Same fundamental saturation as #6 even with the 8B vs 12B transformer difference — the **11.5 GB Windows compositor + Claude Code + electron baseline** is the irreducible floor. After it, training has ~12 GB to allocate transformer + LoRA + optimizer + grads + activations, which doesn't fit either way. Killed PID 68216. **Conclusion: A and B both empirically dead on this hardware via diffusers' train_dreambooth_lora_flux script. ai-toolkit's `quantize: true` config has not been tested yet; it should fit because 8-bit quantized transformer ≈ 6 GB instead of 16 GB.** |
| aurora | LoRA training smoke test #8 (ai-toolkit pivot fully attempted 2026-05-02 21:14 PT) | 2026-05-02 21:14 PT | 2026-05-02 21:54 PT (killed) | none | Reversed prior defer. Created `Projects/ai-toolkit/.venv` (uv + Python 3.11.15 from `Astral/CPython3.11.15`), installed torch 2.6.0+cu124 + torchvision + torchaudio + full `requirements.txt` clean. Configured `config/aurora_v1_smoke.yaml` from `train_lora_flux_24gb.yaml` template — FLUX-dev base, `quantize: true`, `low_vram: true`, 50 steps, 512 res, 32-image flat dataset at `build/lora-train/aurora-aitk/dataset/` (cp'd from existing aurora-v1 dataset). First launch failed on `torchaudio` import (added). Second launch hit 0/2 sample generation (1024×1024 inference saturated VRAM); added `disable_sampling: true` + `skip_first_sample: true`. **Third launch:** transformer shards loaded in 5.4 sec (vs diffusers' 73 sec), cache latents in 7 sec (vs diffusers' 15 min), sampling skipped — but training itself **still saturated at 23.5 GB / 769 MB free** and made zero step progress in 14 min wall clock. **Definitive empirical conclusion across three frameworks (diffusers DreamBooth × FLUX-dev, diffusers × FLUX-Schnell, ai-toolkit × FLUX-dev quantize:true low_vram:true): local FLUX-class LoRA training is INFEASIBLE on this 24 GB 3090 Ti while Windows desktop is running.** Even ai-toolkit's published-as-24GB-friendly config can't escape the floor. Aurora venv at `Projects/ai-toolkit/.venv/` + config at `Projects/ai-toolkit/config/aurora_v1_smoke.yaml` + flat dataset at `aether/build/lora-train/aurora-aitk/dataset/` are all preserved for cloud-side or future-hardware reuse. |

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
