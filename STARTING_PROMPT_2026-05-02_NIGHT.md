# Starting Prompt — Fresh Session After 2026-05-02 Night Autonomous Run

> Paste this into a new Claude Code session at `C:\Users\dbhav\Projects\aether`.
> It bootstraps the next session with everything it needs to be productive
> from message 1.

---

## Read in this order

1. **Run `python scripts/current_status.py` first.** Authoritative live state. Trust it over any prompt.
2. **Read `HANDOFF_2026-05-02_NIGHT_PIPELINE_VERIFIED.md`** (~10 min, ultra-detailed narrative of the run that just shipped).
3. **Skim `HANDOFF_2026-05-02_AUTONOMOUS_RUN_SUMMARY.md`** (5 min, executive-summary version).
4. **Skim `docs/runbooks/persona_pipeline_phase0_to_3.md`** (operator runbook for the whole pipeline).
5. **Skim the 3 research notes:**
   - `planning/research/2026-05-02_phase1_identity_locking_options.md`
   - `planning/research/2026-05-02_qwen2vl_calibration.md`
   - `planning/research/2026-05-02_lora_training_smoke_test.md`
6. **Read the locked feedback:** file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/feedback_bare_metal_local_inference.md
7. **Read the recipe memory:** file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/reference_flux_framing_bias.md (saved during the run; locks the 1:2/1:3/body_extension recipe in cross-session memory).

---

## Where the project stands (one paragraph)

The bare-metal local inference pivot's Phase 0 (image generation), Phase 2 (Doctrine §8 selftest), and Phase 3-prep (LoRA training scaffold) are all working end-to-end on Don's RTX 3090 Ti. Live Aurora candidates have been generated at three aspect ratios (2:3, 1:2, 1:3) plus one body-extended full-body image. **Major finding: FLUX framing bias escapes via aspect ratio** (1:2 → 80% body, 1:3 → 90%, body_extension via FLUX-Inpaint → true full body with feet). 16 candidates from a recipe-locked curation batch are awaiting Don's manual curation walk. Phase 3 LoRA training **launches cleanly** but throughput at 1024 res + grad checkpointing is too slow for unattended overnight runs (~50s/step extrapolates to 21 hours for 1500 steps). Don needs to pick a faster config (lower resolution / FLUX-Schnell / cloud rental) before launching the full training. 36 commits shipped, 95 tests passing, all docs updated.

---

## Don's morning queue (in priority order)

### 1. Walk the curation batch

```bash
cd /c/Users/dbhav/Projects/aether
python tools/persona-reference-gen/curate.py \
  --persona aurora \
  --batch 2026-05-02-curation-1to2
```

For each of 16 candidates, decide `keep` / `reject` / `reprompt`. Expect ~6-12 keepers. Notes from the autonomous-run probes for similar images: identity strong, ~80% body, pose variation across seeds.

### 2. Body-extend each keeper

For each `keep`-marked image:

```bash
PERSONA_REFGEN_LIVE=1 PERSONA_REFGEN_OFFLOAD=sequential \
  python tools/persona-reference-gen/body_extension.py \
    --input personas/aurora/_pipeline/step1_references/2026-05-02-curation-1to2/images/<keeper-filename>.png \
    --output personas/aurora/_pipeline/step1_references/2026-05-02-curation-1to2/images/<keeper-filename>_extended.png \
    --extend-down 1024
```

~5-7 min per image (warm cache). Produces `<filename>_extended.png` next to the original; `dataset_builder.py` picks both up automatically (via the `body_extended` source_kind path).

### 3. Pick the LoRA training config

Three options, in order of recommendation:

**Option A — `--resolution 512`** (untested but ~4x faster on paper). 50-step smoke at 512 didn't complete in 30 min during the run, but that may have been transient GPU contention from other processes:

```bash
python tools/persona-lora-train/launch.py \
  --persona aurora \
  --workdir build/lora-train/aurora-v1 \
  --relax-selftest-verdict \
  --resolution 512 \
  --max-train-steps 1000 \
  --execute
```

**Option B — switch to FLUX.1-Schnell.** Smaller (8B vs 12B), much faster. `dataset_builder.TrainingHyperparams.base_model = "black-forest-labs/FLUX.1-schnell"` is a one-line change. Identity LoRAs trained on Schnell may transfer to dev for inference (community split — needs validation).

**Option C — Cloud rent (runpod.io A100/H100).** Most reliable. ~$3/hr × 3 hours = ~$10. Trains FLUX-dev LoRA at 1024 res in 2-3 hours.

**Don picks one** and runs. Until then, the training pipeline is verified-launches-cleanly but unverified-converges.

### 4. (Optional) Validate Qwen2-VL-7B for the selftest

When VRAM is free overnight:

```bash
PERSONA_REFGEN_SELFTEST_LIVE=1 \
PERSONA_REFGEN_SELFTEST_BACKEND=qwen2vl \
  python tools/persona-reference-gen/phase0_evaluate.py \
    --persona aurora \
    --batch 2026-05-02-aspect-1to2 \
    --backend qwen2vl
```

Default `selftest_qwen2vl.DEFAULT_MODEL` is `Qwen/Qwen2-VL-7B-Instruct` (16 GB download). If 7B's verdicts agree with manual claude-opus eval on ≥2/3 of framing-fails, flip `selftest._DEFAULT_BACKEND` from `"openai"` to `"qwen2vl"`.

---

## Hard constraints (carry-forward from previous handoffs)

- `bash tools/check-pre-commit.sh` must exit clean before any commit.
- cargo isn't on PATH by default in Git Bash: `export PATH="/c/Users/dbhav/.cargo/bin:$PATH"`.
- Explicit-path commits only: `git commit -- <paths>`. Never `-A` / `-u` / `.`.
- Pre-existing dirty paths (preview_voice.opus, LoRA training checkpoint dirs) must NEVER be staged.
- `personas/<slug>/_pipeline/` is gitignored — generated images don't get committed. EVALUATION.md / selftest.jsonl / curation.jsonl in those dirs are also gitignored.
- One layer per session per CLAUDE.md §1 — we've been operating entirely under `tools/persona-reference-gen/` + `tools/persona-lora-train/` + `tests/unit/persona_*` + `personas/aurora/_pipeline/` + `planning/`. Stay in this scope unless Don's request explicitly crosses layers.
- VRAM budget on the 3090 Ti: `nvidia-smi` shows ~14 GB resident from Don's other processes (Isabelle, Blender, browser GPU). Sequential offload keeps FLUX peak at ~5 GB; only model_cpu_offload at ≥14 GB free uses ~12 GB. Auto-pick handles this.

---

## Stack assumptions (verified during the run)

- Python 3.14.3
- torch 2.11.0+cu128
- diffusers **HEAD** (0.38.0.dev0) — pip-installed via `pip install -e /c/Users/dbhav/Projects/diffusers/` from the cloned repo. **Pip release 0.37.1 is too old** for the FLUX LoRA trainer.
- transformers 4.57.6
- accelerate 1.13.0
- peft 0.19.1
- bitsandbytes 0.49.2
- torchvision 0.26.0 (installed during the run; required by Qwen2-VL processor)
- ftfy 6.3.1 (installed during the run; required by diffusers training script)

HF cache at file:///I:/HuggingFaceCache/hub/. FLUX.1-dev pulled. Qwen2-VL-2B pulled (4 GB; produced unreliable scores). Qwen2-VL-7B NOT pulled (16 GB).

---

## Where to find things

| Want to do | Tool / file |
|---|---|
| Generate one Aurora baseline | `phase0_baseline.py` |
| Run a 4×N×M batch | `phase0_full_batch.py` |
| Test a new framing strategy | `prompt_engineering_probe.py` |
| Test an aspect ratio | `aspect_ratio_probe.py` |
| Score images via VLM | `phase0_evaluate.py` |
| Auto-curate from selftest | `auto_curate.py` |
| Manually curate | `curate.py` |
| Cross-persona status | `pipeline_status.py` |
| Extend portrait → full-body | `body_extension.py` |
| Build LoRA training plan | `tools/persona-lora-train/launch.py` (plan-only by default) |

| Want to read | Where |
|---|---|
| Live state | `python scripts/current_status.py` |
| GPU sequential queue | `planning/plans/gpu_queue.md` |
| Doctrine + boundaries | `planning/01_product_doctrine.md` |
| Pipeline contract | `docs/adr/ADR-0014-per-persona-character-pipeline.md` |
| Reference-gen scope | `docs/adr/ADR-0015-reference-image-generation-inside-companion.md` |
| Operator runbook | `docs/runbooks/persona_pipeline_phase0_to_3.md` |

---

## Lessons learned (don't repeat these mistakes)

1. **FLUX prior bias is hardware-of-prior, not prompt-fixable.** Don't waste time on prompt engineering for full-body framing at 2:3 aspect. Use 1:2/1:3 + body_extension instead.

2. **Qwen2-VL-2B is unsuitable for Doctrine §8.** Returns "feet not visible, consistent with full-body framing" — backward inference. Don't ship it as the default selftest backend.

3. **Diffusers HEAD differs from pip release on FLUX-specific APIs.** The training script crashes on 0.37.1 with "requires source install." Always `pip install -e <cloned-diffusers>` for FLUX work.

4. **Diffusers DreamBooth loader walks `--instance_data_dir` and crashes on non-image files.** dataset_builder splits images and captions into sibling subdirs (`<dataset>/images/` + `<dataset>/captions/`). Don't put them flat.

5. **tee + tqdm hides progress in log files.** tqdm uses `\r` for in-place updates; tee buffers on `\n`. Trust `nvidia-smi` + checkpoint files, not the log.

6. **Sequential offload is reliable on a busy 3090 Ti** but **slow.** ~5-7 min per FLUX inference vs ~2 min at full residence. Don't default to it if `≥14 GB free` — let the auto-picker choose `model` offload when possible.

7. **LoRA training at 1024 res + grad checkpointing on 3090 Ti is too slow for overnight.** Don't repeat the smoke-test at the same config and expect a different result. Switch resolution / model / hardware first.

8. **`personas/<slug>/_pipeline/` is gitignored.** All generated images, EVALUATION.md, selftest.jsonl, curation.jsonl in these dirs DO NOT get committed. Don't expect to see them in `git status` after generation.

9. **Pose convergence is seed-locked.** All 9 generations at 2:3 produced crossed-arms pose. At 1:2/1:3, different seeds produced different poses. Vary seed for pose diversity.

10. **`backend_local_flux.aspect_to_dims["9:16"]` is misleading** — it returns (1024, 1536) which is actually 2:3. Use `"9:16-strict"` for actual 9:16 dims (864, 1536). Don't trust the labels.

---

## What the autonomous run did NOT do

- **Curate the 16-image batch** — Don's manual call.
- **Train the LoRA** — pipeline launches but Don picks faster config first.
- **Validate Qwen2-VL-7B** — 16 GB download deferred.
- **Touch other 8 personas** — Aurora pioneers; the rest follow when her recipe locks.
- **Voice clone (ADR-0014 Step 3)** — not started.
- **Video character LoRA (Step 4)** — not started.

---

## If something looks broken

1. `python scripts/current_status.py` — repo state.
2. `git log --oneline c25acc0..HEAD` — 36 commits this run.
3. `tail -50 /tmp/curation_batch.log` (or any other `/tmp/*_log` file) — last GPU-job output.
4. `nvidia-smi` — current GPU state.
5. `python -m pytest tests/unit/persona_reference_gen/ tests/unit/persona_lora_train/ -q` — tests are 95+, all green at handoff.
6. `bash tools/check-pre-commit.sh` — clean at handoff.

If any of these disagree with what this prompt or the handoff says, **trust the repo over the prompt** (Decision #32, file:///C:/Users/dbhav/Projects/aether/CLAUDE.md §2).

---

## One more thing

The autonomous run worked because Don gave clear authority:

> "you are also in charge of the GPU work. it is training for the same project you are in. stop and clear it if you need to. you're the decider."
>
> "work continously. do not stop. keep building and working. keep finding things that need done."

That's the spirit to bring to the next session. Don has limited time per day; the agent's job is to remove blockers, not create them.
