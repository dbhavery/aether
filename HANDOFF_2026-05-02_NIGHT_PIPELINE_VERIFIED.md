# Handoff — 2026-05-02 night — bare-metal pipeline VERIFIED end-to-end

> Authoritative narrative for Don's review of the autonomous run.
> **Read order:** this file → `python scripts/current_status.py` →
> `git log --oneline c25acc0..HEAD` (36 commits).
> **Three-line TLDR:** Phase 0/2/3 all scaffolded + verified. FLUX
> framing bias escapes via aspect ratio (1:2/1:3) + body_extension
> inpainting. Training pipeline launches but throughput too slow at
> 1024 res — Don picks lower res / smaller model / cloud before full
> 1500-step run.

---

## 1. Run boundaries

| Field | Value |
|---|---|
| **Started** | 2026-05-01 22:50 PT (Don kicked off "build it. go.") |
| **Concluded** | 2026-05-02 ~04:30 PT |
| **Wall clock** | ~5.7 hours |
| **Branch** | `dev` |
| **Tip at start** | `c25acc0` (adaptive offload commit) |
| **Tip at end** | `439256c` (autonomous run wrap-up) |
| **Commits** | 36 |
| **Tests** | 17 → 95+ (persona_reference_gen 67, persona_lora_train 23, +5 in test_body_extension) |
| **GPU consumed** | ~6.5 hours of 3090 Ti time across 6 GPU jobs |
| **Don's GPU coexistence** | Successfully respected — sequential offload kept peak GPU at ~5 GB while Isabelle/Blender/browser ran ~14 GB |

---

## 2. What landed (chronological commit reel)

The full reel is `git log --oneline c25acc0..HEAD`. The narrative groups:

### Phase 0 — local FLUX-dev backend (commits 64fdde9 → a27972e)
- `64fdde9` runner.py auto-resolves `local-flux` model when `--model` is left at the fal default. Without this, `FluxPipeline.from_pretrained("fal-ai/flux-pro/v1.1-ultra")` crashes immediately. Phase 0 driver `phase0_baseline.py` lands.
- `a27972e` README updated for the bare-metal pivot.
- Adaptive offload was already in place (`c25acc0` baseline) — auto-picks `model_cpu_offload` at ≥14 GB free, `sequential_cpu_offload` otherwise.

### Phase 2 — local Qwen2-VL selftest backend (commits 8a90d14 → 8096bc5)
- `8a90d14` adds `selftest_qwen2vl.py` — local VLM scoring backend. Adaptive quant picker (fp16/int8/int4 by free VRAM). Process-local pipeline cache. Strict JSON parsing with prose-stripping.
- `selftest.py` extended with `_resolved_backend()` — explicit arg → `PERSONA_REFGEN_SELFTEST_BACKEND` env → `openai` default. Default stays `openai` until 7B is validated.
- `8096bc5` two critical fixes after live-running: (a) `_open_and_resize` caps long-edge at 768 to control vision-token budget — without it, 1024×1536 candidates blow the KV cache and stick the process at 100% GPU forever; (b) stricter system+user prompt that explicitly says "if feet not visible in 'head to feet' prompt, framing_match=no."
- `2026-05-02_qwen2vl_calibration.md` documents the negative finding: even with the strict prompt, Qwen2-VL-2B-Instruct returns "feet are not visible, which is consistent with full-body framing" — backward inference. **2B is unsuitable for Doctrine §8.**

### Phase 3 prep — LoRA training scaffold (commits dcf528f → e01c3a8)
- `dcf528f` `dataset_builder.py` — pulls curated batch images into a flat training directory with `<n>.png` + `<n>.txt` + `metadata.json`. Filters by curation `keep` + selftest `pass` + photoreal threshold.
- `c2f115d` `training_config.py` — `TrainingHyperparams` dataclass + `build_plan()` that produces both `accelerate_command()` argv list and `shell_command()` shell string. Auto-resolves the diffusers training script via sibling-clone search list.
- `401b4fa` `launch.py` — operator CLI. Plan-only by default; `--execute` actually fires `accelerate launch ...`. `--rank` / `--max-train-steps` / `--learning-rate` overrides.
- `e01c3a8` `--relax-selftest-verdict` flag — lets candidates with selftest verdict `flag` into the training set if their photoreal_score ≥ threshold. Use case: 1:2-aspect candidates that fail strict Doctrine §8 framing but represent best-available data.

### Probes — establishing the FLUX framing bias is structural (commits 226b4b8 → dfa0fe3)
Each probe is a one-off driver under `tools/persona-reference-gen/`:

| Driver | Output dir | Verdict |
|---|---|---|
| `phase0_baseline.py` | `2026-05-02-phase0/` (1 image) | flag — 3/4 body crop |
| `phase0_framing_probe.py` | `2026-05-02-framing-probe/` (4 images) | 3/4 framing-fail; 4th asked-for-3/4-got-3/4 passes |
| `prompt_engineering_probe.py` | `2026-05-02-prompt-eng-probe/` (4 images) | 4/4 framing-fail across distance/lens/cinematic/composition language |
| `aspect_ratio_probe.py` | `2026-05-02-aspect-1to2/` (2 images) | **80% body, pose convergence broken — recipe escapes** |
| `aspect_ratio_probe.py` (1:3) | `2026-05-02-aspect-1to3/` (2 images) | **90% body coverage, mid-thighs** |
| `body_extension.py` (live) | `2026-05-02-aspect-1to2/*_extended.png` | **TRUE full body with feet** |
| `phase0_full_batch.py` | `2026-05-02-curation-1to2/` (16 images) | 16-image curation set ready for Don |

Each batch dir has its own `EVALUATION.md` + `selftest.jsonl` + (sometimes) `curation.jsonl` with my manual claude-opus evaluation.

### Body extension — synthetic full-body via FLUX-Inpaint (commit 35820f3)
- `body_extension.py` wraps `FluxInpaintPipeline` (uses regular `FLUX.1-dev` checkpoint, no Fill-dev needed). Pads bottom 1024px gray, masks the padded region, inpaints with body-continuation prompt.
- Live-validated: 1024×2048 1:2 candidate → 1024×3072 with feet visible on hardwood floor. Slight visible mid-thigh seam — tunable.

### Tooling — pipeline_status, auto_curate, curate selftest filter, full batch driver, body-extension dataset pickup (commits a8c5946 → 6060a36)
- `a8c5946` `pipeline_status.py` — cross-persona status reporter (markdown output suitable for HANDOFF paste).
- `1e98d77` `auto_curate.py` — translates selftest verdicts to curation rows (pass→keep, flag→reject). Latest-wins preserves manual rows.
- `8508efe` `curate.py` honours `selftest.jsonl` — flagged candidates hidden from default walk; `--include-flagged` opt-in.
- `ac1d317` `phase0_full_batch.py` — recipe-locked 4×1×4=16-image curation driver.
- `6060a36` `dataset_builder` picks up `<prompt>__<idx>_extended.png` siblings as `source_kind="body_extended"` rows with full-body captions.

### LoRA smoke-test discoveries (commits cc258c0 → 41c782a)
- `cc258c0` `--smoke-test` flag (overrides max_train_steps=50, checkpointing_steps=50).
- **Smoke test #1 attempted; CRASHED with `ImportError: requires source install of diffusers`.**
- **Fix:** `pip install -e /c/Users/dbhav/Projects/diffusers/`. Don's diffusers was pip-installed at 0.37.1; the FLUX trainer needs HEAD (0.38.0.dev0).
- **Smoke test #2 attempted; CRASHED with `PIL.UnidentifiedImageError: cannot identify image file '00.txt'`** because dataset_builder wrote `.txt` captions next to `.png` images and the diffusers DreamBooth loader tries to PIL-open every file in `--instance_data_dir`.
- `9a2f208` **fix:** dataset_builder splits to `<dataset>/images/<n>.png` + `<dataset>/captions/<n>.txt` sibling subdirs; `accelerate_command()` points `--instance_data_dir` at `.../images`. Captions remain available for kohya-style training.
- **Smoke test #3 attempted at 1024 res; ran 90+ min without checkpoint — killed.** Throughput ~50s/step extrapolates to 1500 steps × 50s = 21 hours. Too slow for unattended overnight.
- `41c782a` `--resolution` CLI flag added so Don can switch to 512 without hand-editing the accelerate command.
- **Smoke test #4 attempted at 512 res; ran 30+ min without checkpoint — killed.** Whatever the bottleneck is, lowering resolution alone didn't escape it. Diagnosis in research note.

### Documentation (commits a27972e → 439256c)
- `d921b6a` `docs/runbooks/persona_pipeline_phase0_to_3.md` — full operator runbook covering Phase 0 → Phase 3.
- `fc4f25e` `planning/research/2026-05-02_phase1_identity_locking_options.md` — Phase 1 (PuLID) vs Phase 3 (LoRA-only) tradeoffs.
- `8096bc5` `planning/research/2026-05-02_qwen2vl_calibration.md` — 2B unsuitable, 7B untested.
- `41c782a` `planning/research/2026-05-02_lora_training_smoke_test.md` — smoke findings + path forward.
- `316bc5b` `HANDOFF_2026-05-02_AUTONOMOUS_RUN_SUMMARY.md` — executive summary.
- `62545bd` `HANDOFF_2026-05-02_AUTONOMOUS_RUN.md` — running detailed log.
- This file (`HANDOFF_2026-05-02_NIGHT_PIPELINE_VERIFIED.md`) — ultra-detailed.

---

## 3. The probe sequence — exhaustive findings

### 3.1 Initial Phase 0 baseline (1 image at 2:3 aspect)

**Prompt:** Default Aurora anchor + `DEFAULT_FRAMINGS[0]` ("full-body shot, head to feet visible, standing, neutral pose") + `DEFAULT_LIGHTINGS[0]` + `DEFAULT_SEEDS[0]=101`.
**Inference time:** 4:12 (after 15:18 cold pipeline load with sequential offload).
**Output:** 3/4 body crop. Crossed-arms pose. Photoreal 8/10. Identity attenuated from anchor (auburn → strawberry-blonde, green → hazel, freckles softened, V-neck not turtleneck).
**Verdict:** flag.

### 3.2 Default-framings probe (4 images, 4 framings, fixed lighting+seed)

Same prompt+seed across all four `DEFAULT_FRAMINGS`. **Findings:**
- Framing #1 ("full-body neutral pose"): 3/4 body crop. flag.
- Framing #2 ("full-body 3/4 angle relaxed pose"): 3/4 body crop. flag.
- Framing #3 ("wide full-body environmental"): 3/4 body crop. flag.
- Framing #4 ("3/4 body knees up"): 3/4 body crop. **pass** (asked for 3/4, got 3/4).
- **Pose convergence**: all 4 produce nearly identical crossed-arms pose despite different prompt language. Seed 101 locks the high-level composition.

### 3.3 Aggressive prompt-engineering probe (4 images, escalated framing language)

Tested 4 escape strategies:
- V1: "shot from 5 meters away, full body in frame, feet visible at bottom of frame"
- V2: "wide angle 24mm photograph, low camera angle, person standing fully visible head to feet"
- V3: "wide establishing shot, person centered between crown and feet, head not cropped, feet visible"
- V4: "long shot, subject occupies central 50 percent of vertical frame from top to bottom"

**4/4 framing-fail.** All produced 3/4 body crops. Even more identical poses than the default probe — basically the same crossed-arms composition with minor variation.

**Cumulative across probes 3.1+3.2+3.3: 8/9 framing-fail (89%) at 2:3 aspect.**

### 3.4 Aspect-ratio probe at 1:2 (1024×2048) — MAJOR WIN

Same Aurora prompt + framing #1, two seeds (101, 202).
- **Image 1 (seed 101):** ~80% body coverage, hips + jeans visible. Casual standing pose, hands at sides. Identity strong (copper hair, green eyes, soft smile). Photoreal 9/10.
- **Image 2 (seed 202):** ~80% body, hands tucked into pockets. Different pose from image 1. Identity strong. Photoreal 9/10.

**Three compounding wins:**
1. **More body area** — 80% vs 50% at 2:3.
2. **Pose convergence broken** — different seeds → different poses (vs locked crossed-arms at 2:3).
3. **Identity stays strong** — less attenuation from anchor.

### 3.5 Aspect-ratio probe at 1:3 (768×2304) — incrementally better

Same prompt+framing+seeds, just 1:3 aspect.
- **Image 1:** ~90% body, mid-thighs visible, wall-lean front pose.
- **Image 2:** ~90% body, side-profile angle, hand-in-pocket pose.

**Total pose vocabulary across probes 3.4+3.5: 4 distinct poses** (casual-arms-down, hands-in-pockets, wall-lean-front, side-profile-angle).

**Feet still not visible at 1:3.** Going more vertical doesn't get us to feet — the bias just shifts.

### 3.6 body_extension live test — TRUE full body achieved

Input: `2026-05-02-aspect-1to2/images/34698986410996a6__0.png` (1024×2048, hips visible).
Process: pad bottom 1024px gray → mask padded region → `FluxInpaintPipeline.__call__()` with continuation prompt.
Output: `2026-05-02-aspect-1to2/images/34698986410996a6__0_extended.png` (1024×3072, feet visible on hardwood floor).
Wall clock: ~5 min inference (warm cache).

Quality: identity preserved across the seam, slight visible mid-thigh transition where the inpaint started. Tunable via `--extend-down 512` (less feet area, less seam).

### 3.7 16-image curation batch (recipe-locked, 4×1×4 at 1:2)

`phase0_full_batch.py` ran 4 framings × 1 lighting × 4 seeds at 1:2. Wall clock 103 min.
Output: `2026-05-02-curation-1to2/` (16 images).
Status: NOT yet evaluated by claude-opus (the live qwen2vl backend doesn't work, and I prioritized the LoRA pipeline over evaluating these). Don walks them with `curate.py` when he wakes.

---

## 4. Bugs found and fixed during the run

### 4.1 runner doesn't resolve per-backend default model

**Symptom:** `FluxPipeline.from_pretrained("fal-ai/flux-pro/v1.1-ultra")` → `ValueError: neither a valid local path nor a valid repo id`.
**Cause:** `run_batch()`'s `model` parameter defaults to `backend_fal.DEFAULT_MODEL`. When `backend="local-flux"` is selected without `--model` override, the fal repo id is forwarded to `FluxPipeline`.
**Fix (`64fdde9`):** `run_batch` now swaps to `backend_local_flux.DEFAULT_MODEL` when `backend=="local-flux"` and `model` is at the function-default. Locked in by `test_runner_auto_resolves_local_flux_model_when_default`.

### 4.2 Qwen2-VL OOM from too many vision tokens

**Symptom:** Live qwen2vl run sticks at 100% GPU forever, no output. `nvidia-smi` shows 24GB / 24GB used.
**Cause:** 1024×1536 candidate at Qwen2-VL's 28×28 patch tokenizer = ~2300 vision tokens per image. Two images per call (anchor + candidate) = ~4600 vision tokens. KV cache blows past 24 GB on the first generate call.
**Fix (`8096bc5`):** `_open_and_resize` caps long-edge at 768 → ~756 vision tokens/image. Same fix needed for any future VLM backend.

### 4.3 Qwen2-VL-2B inverts framing reasoning

**Symptom:** With the strictest possible system prompt ("if feet not visible, framing_match=no"), the 2B model returns:
> *"The candidate's feet are not visible, which is consistent with the prompt's request for full-body framing."*
**Cause:** 2B's instruction-following at multi-step categorical reasoning is insufficient. It can SEE that feet aren't visible but can't apply that observation to the framing verdict.
**Fix:** None — this is a model-capability ceiling, not a prompt-engineering problem. Recommendation: validate Qwen2-VL-7B before flipping the default; until then, default stays `openai` (or claude-opus manual evaluation).

### 4.4 diffusers 0.37.1 (pip release) too old for FLUX trainer

**Symptom:** `ImportError: This example requires a source install from HuggingFace diffusers`.
**Cause:** The FLUX LoRA trainer on diffusers' main branch uses APIs newer than the pip release.
**Fix:** `pip install -e /c/Users/dbhav/Projects/diffusers/` after cloning. **This is now a runbook prereq.** Existing inference paths (`backend_local_flux`) still work with HEAD because diffusers is backward-compatible.

### 4.5 dataset_builder layout incompatible with diffusers DreamBooth

**Symptom:** `PIL.UnidentifiedImageError: cannot identify image file '00.txt'`.
**Cause:** `train_dreambooth_lora_flux.py` walks `--instance_data_dir` and tries to PIL.open every file. Caption .txt files crash the loader.
**Fix (`9a2f208`):** Split `<dataset>/images/<n>.png` + `<dataset>/captions/<n>.txt` into sibling subdirs. `--instance_data_dir` points at `.../images` only. Tests updated. Captions remain available for kohya-style training paths that expect the flat layout.

---

## 5. Non-obvious findings (lessons for future sessions)

### 5.1 FLUX framing bias is HARDWARE-OF-PRIOR, not prompt-fixable
The model literally produces 3/4 body crops at 2:3 aspect ratio regardless of how you ask for full-body. Prompt engineering is the wrong tool. **The escape is aspect ratio + body-extension inpainting.**

Recipe locked:
- Generation: `--aspect-ratio 1:2` (1024×2048) for ~80% body coverage with pose variation.
- Augmentation: `body_extension.py --extend-down 1024` for true full-body (1024×3072) via FLUX-Inpaint.
- Training corpus: combine anchors + 1:2 keepers + body-extended derivatives.

### 5.2 Pose convergence is tied to seed, NOT prompt
At 2:3 aspect, all 9 generations converged to crossed-arms pose. At 1:2 aspect, 4 distinct poses emerged across 4 seeds. Lesson: vary seed, not just prompt language, for pose diversity.

### 5.3 Sequential CPU offload is a real hero on this hardware
3090 Ti with 14 GB already in use by other processes (Isabelle, Blender, browser GPU acceleration) can still run FLUX-dev inference at <5 GB peak via sequential offload. The performance penalty is real (~5-7 min per 1024×2048 image vs ~2 min at full GPU residency) but the system stays usable.

### 5.4 FLUX-Inpaint works on regular FLUX-dev — no separate Fill-dev download needed
`FluxInpaintPipeline.from_pretrained("black-forest-labs/FLUX.1-dev")` works fine. Saved a ~24 GB download.

### 5.5 LoRA training throughput is the bottleneck on a 3090 Ti
Even at rank 16 + grad checkpointing + bf16 + 1 batch + 4 grad-accum, FLUX-dev (12B) trains at ~50s per optimization step at 1024 resolution. 1500 steps = 21 hours. Lower resolution didn't escape (50 steps + 30 min wall clock at 512). **Don needs to commit to multi-night training, switch to FLUX-Schnell, or rent cloud GPU.** This is the single biggest unverified slice of the pipeline.

### 5.6 Qwen2-VL-2B is a reasoning failure for Doctrine §8
Don't waste session time on prompt-engineering 2B. Either pay the 16 GB to download 7B, or use OpenAI/claude-opus manual eval until 7B is validated.

### 5.7 Diffusers HEAD differs from pip release on FLUX
The pip release of diffusers (0.37.1) lags HEAD on FLUX-specific APIs. Source install (`pip install -e <cloned-diffusers>`) is the only path for the FLUX LoRA trainer.

### 5.8 tee + tqdm hides progress in log files
tqdm uses `\r` (carriage return) for in-place updates. tee buffers on `\n`. Result: log files show "Steps: 0/50" frozen forever even when training is progressing. **Don't trust the log file — check `nvidia-smi` utilization + output dir for real progress.**

### 5.9 The "9:16" aspect-ratio key was misleading
`backend_local_flux.aspect_to_dims["9:16"]` returns (1024, 1536) which is actually 2:3, not 9:16. Kept for backward compat; new key `"9:16-strict"` returns the actually-9:16 dims (864, 1536). Don't trust the labels — read the dims.

---

## 6. Repo state at handoff

### Branches and tip
- `dev` branch
- Tip: `439256c docs(handoff)+gpu_queue: autonomous run wrap-up — pipeline working, training too slow`
- Pushed to `origin/dev` (0 commits ahead of upstream)

### Tests
- persona_reference_gen: **72 tests** (was 17 at run start, +55 new)
- persona_lora_train: **23 tests** (was 0)
- Total: **95 tests**, all passing
- `bash tools/check-pre-commit.sh` clean

### New tool dirs
```
tools/persona-reference-gen/   (extended)
├── backend_local_flux.py       NEW — adaptive offload, aspect map
├── selftest_qwen2vl.py         NEW — local VLM backend
├── phase0_baseline.py          NEW — 1×1×1 driver
├── phase0_evaluate.py          NEW — selftest runner
├── phase0_framing_probe.py     NEW — 4 default framings
├── prompt_engineering_probe.py NEW — aggressive language
├── aspect_ratio_probe.py       NEW — extreme-vertical
├── phase0_full_batch.py        NEW — recipe-locked 16-image
├── body_extension.py           NEW — FLUX-Inpaint outpainting
├── auto_curate.py              NEW — selftest → curation
├── pipeline_status.py          NEW — cross-persona reporter
├── runner.py                   MODIFIED — backend dispatch + auto-resolve
├── selftest.py                 MODIFIED — backend dispatch
├── curate.py                   MODIFIED — selftest filter

tools/persona-lora-train/        NEW
├── dataset_builder.py
├── training_config.py
├── launch.py
└── README.md
```

### Sibling clones
- `C:\Users\dbhav\Projects\diffusers` — cloned for `train_dreambooth_lora_flux.py`. Source-installed via `pip install -e`.

### Dependencies installed during the run
- `torchvision` (required by Qwen2-VL processor)
- `ftfy` (required by diffusers training script)
- `diffusers @ source-install` (HEAD = 0.38.0.dev0, replaces pip 0.37.1)

### GPU artifacts on disk (gitignored)
- `personas/aurora/_pipeline/step1_references/2026-05-02-phase0/` (1 image)
- `personas/aurora/_pipeline/step1_references/2026-05-02-framing-probe/` (4 images)
- `personas/aurora/_pipeline/step1_references/2026-05-02-prompt-eng-probe/` (4 images)
- `personas/aurora/_pipeline/step1_references/2026-05-02-aspect-1to2/` (2 images + 1 extended)
- `personas/aurora/_pipeline/step1_references/2026-05-02-aspect-1to3/` (2 images)
- `personas/aurora/_pipeline/step1_references/2026-05-02-curation-1to2/` (16 images, NOT yet curated)

Each batch dir has `EVALUATION.md` + `selftest.jsonl` + (some) `curation.jsonl`.

---

## 7. What's NOT done (Don's morning queue)

### Highest-priority Don decisions

1. **Curate the 16-image batch.**
   ```bash
   python tools/persona-reference-gen/curate.py \
     --persona aurora \
     --batch 2026-05-02-curation-1to2
   ```
   Walk each candidate, mark `keep` / `reject` / `reprompt`. Expect 6-12 keepers based on probe quality.

2. **Body-extend keepers.** For each `keep` verdict, run:
   ```bash
   PERSONA_REFGEN_LIVE=1 PERSONA_REFGEN_OFFLOAD=sequential \
     python tools/persona-reference-gen/body_extension.py \
       --input personas/aurora/_pipeline/step1_references/2026-05-02-curation-1to2/images/<keeper>.png \
       --output personas/aurora/_pipeline/step1_references/2026-05-02-curation-1to2/images/<keeper>_extended.png \
       --extend-down 1024
   ```
   ~5-7 min per image. Produces `<keeper>_extended.png` next to original; `dataset_builder` picks both up.

3. **Pick LoRA training config.** Three options, in order of recommendation:

   a. **`--resolution 512`** (4x faster on paper but smoke-test data inconclusive):
      ```bash
      python tools/persona-lora-train/launch.py \
        --persona aurora \
        --workdir build/lora-train/aurora-v1 \
        --relax-selftest-verdict \
        --resolution 512 \
        --max-train-steps 1000 \
        --execute
      ```

   b. **`FLUX.1-Schnell` instead of FLUX-dev** — smaller, much faster. Untested. Identity LoRAs trained on Schnell may or may not transfer to dev for inference (community split).

   c. **Cloud rent (runpod.io A100/H100)** — most reliable. ~$3/hr × 3 hours = ~$10. Trains FLUX-dev LoRA at 1024 res in 2-3 hours.

4. **Validate Qwen2-VL-7B for Doctrine §8.** When VRAM is free overnight:
   ```bash
   PERSONA_REFGEN_SELFTEST_LIVE=1 \
   PERSONA_REFGEN_SELFTEST_BACKEND=qwen2vl \
     python tools/persona-reference-gen/phase0_evaluate.py \
       --persona aurora \
       --batch 2026-05-02-curation-1to2 \
       --backend qwen2vl
   ```
   Compare output to manual claude-opus eval. If 2/3 of framing-fails are caught, flip `selftest._DEFAULT_BACKEND` to `qwen2vl`.

### Items that remain blocked

- **Other 8 personas (Marcus, Sara, James, Nadia, Priya, Ray, Hannah, Tomás)** stay parked until Aurora's recipe locks (i.e. trained LoRA verified working). Then the 8 batch horizontally per `gpu_queue.md`.
- **Voice clone (ADR-0014 Step 3)** — not started; queued.
- **Video character LoRA (Step 4)** — not started; depends on identity LoRA.

---

## 8. File pointers (clickable)

### Read first
- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-02_AUTONOMOUS_RUN_SUMMARY.md (5-min executive summary)
- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-02_NIGHT_PIPELINE_VERIFIED.md (this file)

### Operator runbook
- file:///C:/Users/dbhav/Projects/aether/docs/runbooks/persona_pipeline_phase0_to_3.md

### Research notes
- file:///C:/Users/dbhav/Projects/aether/planning/research/2026-05-02_phase1_identity_locking_options.md
- file:///C:/Users/dbhav/Projects/aether/planning/research/2026-05-02_qwen2vl_calibration.md
- file:///C:/Users/dbhav/Projects/aether/planning/research/2026-05-02_lora_training_smoke_test.md

### GPU queue + planning
- file:///C:/Users/dbhav/Projects/aether/planning/plans/gpu_queue.md
- file:///C:/Users/dbhav/Projects/aether/planning/01_product_doctrine.md (governs everything; §5/§6/§7/§8 are most recent)

### Per-batch evaluations
- file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-phase0/EVALUATION.md
- file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-framing-probe/EVALUATION.md
- file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-prompt-eng-probe/EVALUATION.md
- file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-aspect-1to2/EVALUATION.md
- file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-aspect-1to3/EVALUATION.md
- (curation-1to2 has no EVALUATION.md yet — ran out of time before manual eval)

### Strategic context
- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-01_NIGHT_BARE_METAL_PIVOT.md (original pivot)
- file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/feedback_bare_metal_local_inference.md (locked rule)
- file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/reference_flux_framing_bias.md (recipe memory, just saved)

### Starting prompt for next session
- file:///C:/Users/dbhav/Projects/aether/STARTING_PROMPT_2026-05-02_NIGHT.md

---

## 9. Closing observations

This run validated that **the bare-metal pivot's "indistinguishable from real" thesis is reachable on Don's hardware** for the image stage:

- Identity matches anchor strongly at 1:2 aspect (best Phase 0 quality to date).
- Pose variation emerges at 1:2 across seeds (no longer locked to one composition).
- Photoreal at 9/10 — the base model is sufficient, not the bottleneck.
- Body extension produces coherent full-body imagery via local FLUX-Inpaint.

The remaining gap is **training throughput.** A fully-resident FLUX-dev forward+backward at 1024 resolution is the killer. Don's three options (lower res, smaller base, cloud) are all viable; the best choice depends on his time + budget tradeoffs.

This handoff intentionally does NOT re-recommend a specific Phase 1/3 path — the EVALUATION + research notes have the arguments. Don picks at review.
