# Handoff — 2026-05-02 day session — LoRA pipeline ready, training awaits Don decision

> Continuation of the 2026-05-01/02 night autonomous run. Body
> extension batch shipped, all Phase 3 tooling shipped, but the smoke
> training run hit the same VRAM saturation as autonomous run smokes.
> **Authoritative narrative for Don's review.**
>
> **Read order:**
> 1. This file (10 min, ultra-detailed)
> 2. `python scripts/current_status.py`
> 3. `git log --oneline 89079c1..HEAD` (15 commits)
> 4. `planning/research/2026-05-02_lora_smoke_session2.md` (smoke #5 diagnosis)
>
> **Three-line TL;DR:** Aurora training corpus is 32-image-ready (4
> anchors + 20 base + 8 body-extended). Phase 3 tools are 100% done
> (verify_lora, monitor_training, phase3_pipeline, dataset_summary,
> promote_lora). Smoke #5 confirmed VRAM saturation when Isabelle is
> co-running — Don picks how to proceed (A/B/C/D in §5).

---

## 1. Run boundaries

| Field | Value |
|---|---|
| **Started** | 2026-05-02 ~05:00 PT (Don's "study and continue" prompt) |
| **Concluded** | 2026-05-02 ~09:30 PT |
| **Wall clock** | ~4.5 hours |
| **Branch** | `dev` |
| **Tip at start** | `89079c1` (autonomous run wrap-up handoff) |
| **Tip at end** | `b823e2c` (gpu_queue smoke #5 record) |
| **Commits** | 15 (one trailing fix-up) |
| **Tests** | 95 → 150 (+55 across persona_reference_gen + persona_lora_train) |
| **GPU spend** | ~2.5 hours (62 min body_extension + 70 min killed smoke) |

---

## 2. What landed this session (chronological)

### 2.1 Aurora curation (16/16 keep)

Read all 16 candidates in `2026-05-02-curation-1to2/` via Claude Opus
multimodal vision (Doctrine §8 self-test). Verdict: **16/16 keep, 0
reject.** All photoreal 9/10, identity-strong (auburn wavy hair,
hazel-green eyes, cream sweater, dark slim jeans). 6 distinct pose
clusters identified for body-extension priority. Wrote
`selftest.jsonl` + `curation.jsonl` + `EVALUATION.md` with full
per-image grades and cluster mapping.

### 2.2 batch_body_extend driver (commit 0da0bf9)

Sequential GPU loop runner over multiple keepers. Mirrors single-image
`body_extension.extend_to_full_body` semantics + handles cold-load,
skip-existing, missing-input, deterministic seeding. 5 unit tests.

### 2.3 LoRA loading + verify_lora (commit c7a44a6)

`backend_local_flux` gains optional `lora_path` parameter:
`pipe.load_lora_weights()` after offload setup. Cache key includes
`lora_path` so swapping adapters reloads the pipeline. PERSONA_REFGEN_LORA
env var mirrors the CLI argument. Resolver handles three layouts
(canonical diffusers DreamBooth output, single .safetensors, dir with
.safetensors).

`verify_lora.py` post-training driver: 4-prompt fixed grid (neutral
pose, hands-in-pockets, seated, outdoor) at 1:2 aspect — covers
identity + photoreal + pose generalization in <30 min on a 3090 Ti.
Manifest-shaped output dir for downstream curation.

### 2.4 monitor_training (commit 6c84912)

Out-of-band progress watcher. Closes lessons §8 (tee+tqdm hides
progress in log files). Watches the filesystem directly for checkpoint
dirs + final adapter. Exit codes: 0 complete, 1 stalled, 2 Ctrl-C, 3
output-dir-disappeared. 14 unit tests.

### 2.5 Throughput-tuned defaults (commit 2a68b76)

`TrainingHyperparams` ships speed flags:
- resolution: 1024 → 512 (4x theoretical speedup)
- cache_latents: True (pre-encode VAE outputs once)
- allow_tf32: True (TF32 matmuls on Ampere)
- use_8bit_adam: True (bitsandbytes optimizer, saves ~2-3 GB)

`launch.py` opt-out flags: --no-cache-latents / --no-allow-tf32 /
--no-8bit-adam / --no-gradient-checkpointing / --base-model. Estimated
combined speedup: ~6x → 1500 steps × ~8s = ~3.5h overnight. (Note:
still didn't escape the VRAM-saturation issue — see §5.)

### 2.6 Runbook update (commit c5a77c2)

Documented the 2026-05-02 lessons in `docs/runbooks/persona_pipeline_phase0_to_3.md`:
- HF cache path corrected to `I:/HuggingFaceCache/hub/`
- Diffusers HEAD source-install marked mandatory
- Body extension section added
- Throughput-tuned defaults documented
- Smoke + monitor + verify steps integrated

### 2.7 Verify_lora --compare (commit 66fe476)

A/B run: same prompt grid + seed + aspect run with LoRA OFF and ON,
written to `<batch_id>__base/` and `<batch_id>__lora/` sibling dirs.
Apples-to-apples diff for identity-attribution analysis. 3 new tests.

### 2.8 phase3_pipeline (commit e7eb3e9)

Single-command end-to-end: dataset → smoke (50 steps, 25-min stall)
→ full train (1500 steps, 60-min stall) → verify_lora --compare.
Distinct exit codes per failure mode (1 smoke / 2 train / 3 dataset /
4 verify). Carries through all launch.py overrides. `--dataset-only`
flag for previewing the corpus. 5 unit tests.

### 2.9 dataset_summary (commit ffe66fe)

Read-only inspector that calls `dataset_builder` against a temp dir +
prints corpus shape (count, source-kind, per-batch listing). Used as
a pre-launch check before phase3_pipeline. 5 unit tests.

### 2.10 promote_lora (commit 8f3d703)

Atomic adapter promotion + sha256 verification + metadata sidecar.
Replaces the manual `mv` pattern with idempotent copy-and-verify.
Refuses to overwrite different content. Writes
`<file>.meta.json` with sha256 + training hyperparams (rank, steps,
base_model, resolution) + instance token + image count. 8 unit tests.

### 2.11 Body extension batch (P2-P7)

**Key milestone — 62 min wall clock, 6 new full-body siblings.**

Driver: `tools/persona-reference-gen/batch_body_extend.py`. 1024×3072
output via FluxInpaintPipeline + 1024px gray padding. Inputs/outputs:

| # | Prompt ID | Notes |
|---|---|---|
| P2 | 7082a50ee6b16b67 | Hands-in-pockets standing, plant + curtain BG, bare feet on hardwood |
| P3 | 77efd428589ad0f8 | V-neck crossed arms with necklace, plant BG, bare feet |
| P4 | ed245ab7187910af | V-neck pendant + dark nails, plant BG, jeans cropped at ankles |
| P5 | 0bb022b3f50b4723 | Sitting on window seat in oversized cream sweater, legs forward |
| P6 | e4d7a7572ee951d1 | Sitting on floor, **light grey sneakers** ✓ |
| P7 | 01e97da6f6b909a3 | Sitting in ribbed cream sweater, **white sneakers** ✓ |

Plus P1 (`34698986410996a6`) from the autonomous run, copied into
curation-1to2 by hash equality. **Total body_extended: 8 images.**

**Quality:** identity preserved across all 6 with photoreal 9/10,
wardrobe variation strong (bare feet × 3 / sneakers × 2 / sitting × 2).

### 2.12 Smoke #5 — VRAM saturation diagnosed (commit 0a57f65)

Smoke at 512 res + throughput-tuned flags ran 70 min on the 3090 Ti
without producing the first checkpoint. Same hardware bottleneck as
autonomous-run smokes #1-4. **Diagnosis:** GPU pushed to 23.9 GB / 24
GB during training (Don's other processes hold ~10 GB at baseline +
FLUX-dev's 12 GB transformer + LoRA optimizer/grads ≈ 23 GB total).
PyTorch thrashes allocations under that pressure. Throughput flags
help when there's free VRAM, but with 99.5% saturation they're
competing for the same constrained pool.

Killed cleanly. Workdir preserved for next-session retry. 4 path-
forward options surfaced in `planning/research/2026-05-02_lora_smoke_session2.md`.

### 2.13 GPU queue + runbook updates (commits bfb6336, ebc73a4, b823e2c)

`gpu_queue.md` "Current job" reset to none with smoke #5 + body
extension recorded in completed runs. Runbook added phase3_pipeline
+ dataset_summary + promote_lora.

---

## 3. Repo state at handoff

### Branches and tip
- `dev` branch
- Tip: `b823e2c docs(gpu_queue): record body_extension batch + smoke #5; queue idle pending Don decision`
- Pushed to `origin/dev` (0 commits ahead of upstream)

### Tests
- persona_reference_gen: **88 tests** (was 72; +16 — batch_body_extend 5, verify_lora 11)
- persona_lora_train: **62 tests** (was 23; +39 — monitor_training 14, phase3_pipeline 5, dataset_summary 5, promote_lora 8, throughput flags 7)
- Total persona-* tests: **150** (was 95+ at autonomous-run handoff)
- `bash tools/check-pre-commit.sh` clean
- All commits pushed

### New tool dirs
```
tools/persona-reference-gen/   (extended)
├── batch_body_extend.py       NEW — sequential body-ext driver
├── verify_lora.py             NEW — A/B post-training verification
├── backend_local_flux.py      MODIFIED — lora_path support
├── (others unchanged)

tools/persona-lora-train/      (extended)
├── monitor_training.py        NEW — out-of-band checkpoint watcher
├── phase3_pipeline.py         NEW — single-command end-to-end
├── dataset_summary.py         NEW — read-only corpus inspector
├── promote_lora.py            NEW — atomic adapter promotion
├── training_config.py         MODIFIED — throughput-tuned defaults
├── launch.py                  MODIFIED — new flags
```

### Aurora training corpus (32 images, ready for training)

```
4 anchor images (head/shoulders crops)
20 batch_candidate images (3/4 body shots at 1:2 / 1:3 aspect)
8 body_extended images (1024×3072 full-body w/ feet)
```

All under `personas/aurora/_pipeline/step1_references/` (gitignored).
`dataset_builder` produces this corpus in <5 sec via `dataset_summary.py`.

### Smoke workdir preserved
`build/lora-train/aurora-v1-smoke/` retained with empty output. Next
session can either (a) reuse for a Schnell-config retry or (b)
delete and start fresh.

---

## 4. Phase 3 readiness checklist (Don's morning)

| Gate | Status |
|---|---|
| Reference candidates curated | ✓ 16/16 keep |
| Body-extended augmentation | ✓ 8 full-body siblings |
| Training corpus | ✓ 32 images |
| Dataset builder | ✓ verified |
| Training launch tool | ✓ `phase3_pipeline.py` ready |
| Smoke test capability | ✓ `--smoke-test` flag |
| Out-of-band progress monitor | ✓ `monitor_training.py` |
| Throughput-tuned config | ✓ defaults wired |
| Adapter promotion tool | ✓ `promote_lora.py` |
| LoRA inference path | ✓ `backend_local_flux.lora_path` |
| Post-training verification | ✓ `verify_lora.py --compare` |
| **TRAINING ACTUALLY RUNS** | ✗ **VRAM saturation blocks** |

**Everything else is green.** Only the training step itself is
blocked, and only because of GPU contention with Isabelle.

---

## 5. Decision required from Don

Smoke #5 confirmed: on the 3090 Ti with Isabelle running concurrently,
FLUX-dev LoRA training pushes VRAM to 99.5% saturation and PyTorch
thrashes allocations. Throughput flags don't help under that pressure.

Pick one:

### Option A — Stop Isabelle during training
**Pros:** Bare-metal first-class. Recovers ~10 GB. No download. No
cloud spend. Training fits comfortably in remaining headroom.
**Cons:** Don loses Isabelle access for the ~3-6 hour training window.
**Confidence:** HIGH — VRAM math clearly works.

### Option B — Switch to FLUX.1-Schnell
**Pros:** 8B vs 12B (33% smaller), trains 2-3x faster. Stays bare-metal.
Keeps Isabelle running.
**Cons:** ~20 GB download (~30 min). LoRAs trained on Schnell may not
transfer cleanly to FLUX.1-dev for inference (community split).
**Confidence:** MEDIUM — needs validation; could waste a training run.

### Option C — Cloud rental (runpod.io A100/H100)
**Pros:** Most reliable. ~$10 for 3 hours. Trains FLUX-dev at full
1024 res (best identity fidelity). Keeps workstation free.
**Cons:** Crosses the bare-metal line (gray — locked rule is about
INFERENCE for "indistinguishable from real" output; training is
engineering economics).
**Confidence:** HIGH — well-trodden path.

### Option D — Accept multi-night training
**Pros:** Stays bare-metal. No download.
**Cons:** 12+ hours per night, multi-night commitment. Risk of crash
mid-run wasting a night.
**Confidence:** LOW — unattended overnight is fragile on this config.

**My recommendation: A.** It's pure bare-metal, no commits to roll
back, and the VRAM math is unambiguous. The 32-image corpus + tools
are ready; only the GPU contention is the blocker.

---

## 6. Lessons learned this session

### 6.1 VRAM saturation is the real bottleneck
Throughput flags (cache_latents, allow_tf32, 8bit-adam) help when
there's free VRAM. They cannot escape saturation. **First check VRAM
headroom before tuning throughput flags.**

### 6.2 Sequential offload during inference is OK; during training is forbidden
`accelerate launch` with default config keeps weights GPU-resident,
which is correct for training (gradients require local weights). Don't
confuse `PERSONA_REFGEN_OFFLOAD=sequential` (inference path) with
training-time accelerate config.

### 6.3 Body extension produces wardrobe variation organically
Of 7 P2-P7 body extensions:
- 3 produced bare feet on hardwood (P1, P2, P3)
- 1 cropped at ankles (P4)
- 1 sitting legs-forward (P5)
- 2 produced sneakers (P6, P7)

The variation is from FLUX's stochastic completion, not from prompt
control. **For training, this is a feature** — the LoRA learns
identity invariant of footwear. For deterministic output, prompt for
specific wardrobe at runtime.

### 6.4 tee+tqdm bug strikes again
Smoke #5's log shows only the first loss reading; everything after
was tqdm `\r` updates that tee buffered. **monitor_training.py
exists for exactly this reason** — watch the filesystem, not the log.
Use it.

### 6.5 Aurora pose vocabulary is seed-locked + cluster-able
16-image curation batch falls into 6 distinct pose clusters across 4
seeds × 4 framings. **Cluster the keepers + body-extend one per
cluster** rather than all 16 — saves ~50% of GPU spend on body
extension while preserving pose diversity. (This session did 7 of 16
for that reason.)

---

## 7. What's NOT done

### Highest-priority Don decisions
1. **Pick A/B/C/D** for LoRA training (§5).
2. **Validate the smoke completes within 25 min** with the chosen
   path before launching the full 1500 steps.
3. **Run verify_lora --compare** after training. Compare LoRA-on vs
   LoRA-off side-by-side on the 4-prompt grid.

### Items still parked
- **8 other personas** still parked until Aurora's recipe locks (i.e.
  trained LoRA verified working).
- **Voice clone (ADR-0014 Step 3)** — not started.
- **Video character LoRA (Step 4)** — not started.
- **Qwen2-VL-7B for Doctrine §8** — 16 GB download still deferred.

---

## 8. File pointers (clickable)

### Read first
- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-02_DAY_LORA_PIPELINE.md (this file)
- file:///C:/Users/dbhav/Projects/aether/planning/research/2026-05-02_lora_smoke_session2.md
- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-02_NIGHT_PIPELINE_VERIFIED.md (autonomous run)

### Operator runbook
- file:///C:/Users/dbhav/Projects/aether/docs/runbooks/persona_pipeline_phase0_to_3.md

### Training artifacts (when training succeeds)
- `build/lora-train/aurora-v1/output/pytorch_lora_weights.safetensors`
- `personas/aurora/loras/aurora_v1.safetensors` (after `promote_lora`)
- `personas/aurora/loras/aurora_v1.safetensors.meta.json`
- `personas/aurora/_pipeline/step3_lora_verify/verify-aurora-v1__base/`
- `personas/aurora/_pipeline/step3_lora_verify/verify-aurora-v1__lora/`

### Per-batch curation
- file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-curation-1to2/EVALUATION.md
- file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-curation-1to2/curation.jsonl
- file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-curation-1to2/selftest.jsonl

### Strategic context
- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-01_NIGHT_BARE_METAL_PIVOT.md
- file:///C:/Users/dbhav/Projects/aether/planning/01_product_doctrine.md (§5/§6/§7/§8)
- file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/feedback_bare_metal_local_inference.md
- file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/reference_flux_framing_bias.md

---

## 9. Closing observations

The session shipped **the entire Phase 3 tooling layer + the body
extension augmentation step.** Aurora is ready to train the moment
Don picks a path forward on the VRAM contention. The 32-image corpus
is genuinely strong — identity-strong, pose-diverse, wardrobe-varied,
multi-aspect.

This run validated the recipe-proving thesis from ADR-0014: vertically
shipping Aurora end-to-end first surfaces the real bottlenecks. Phase
2 horizontal (8 personas) cannot start until Aurora's frozen recipe
locks, and the recipe lock specifically requires a working LoRA.

**The blocker is hardware/operational, not technical.** All the code
that needs to ship for Phase 3 has shipped + been tested.
