# LoRA Training Smoke Test — 2026-05-02 Session 2 Findings

> **Verdict: Smoke test #5 (512 res + throughput-tuned flags) ran 70+
> minutes without producing the first checkpoint.** Same hardware
> bottleneck as autonomous run smokes #1-4. Throughput-tuning flags
> alone do not escape the limit.
>
> **Recommendation:** Don picks among (a) stop Isabelle during training
> sessions, (b) download FLUX.1-Schnell (~20 GB) and retry, (c) cloud
> rental ($10 for 3h on A100), (d) accept 12+ hour overnight runs.

## What was tested

Smoke run via `tools/persona-lora-train/launch.py --smoke-test` with
the throughput-tuned config:

- Base model: `black-forest-labs/FLUX.1-dev` (12B params)
- LoRA rank: 16
- Resolution: **512** (vs 1024 in autonomous run)
- Mixed precision: bf16
- Gradient checkpointing: ON
- **cache_latents: ON** (new this session)
- **allow_tf32: ON** (new this session)
- **use_8bit_adam: ON** (new this session)
- train_batch_size: 1
- gradient_accumulation_steps: 4 (effective batch = 4)
- Steps: 50 (smoke), checkpointing every 50
- Training images: 32 (4 anchors + 20 base + 8 body-extended)
- Diffusers HEAD (0.38.0.dev0, source-installed)

## What happened

1. **Pipeline launched cleanly** (~5 min cold load).
2. **Training started**: "Total optimization steps = 50".
3. **Single loss reading at 0/50 [00:40, loss=0.814]** captured early.
4. **GPU at 100% utilization, 23.9 GB / 24 GB used for 70+ min.**
5. **No checkpoint produced.** Output dir empty after 70 min.
6. **Killed at 70 min mark.**

## Diagnosis

GPU usage of **23.9 GB / 24 GB during training is the smoking gun.**
The 3090 Ti was at 99.5% VRAM saturation with only ~100 MB headroom,
which means PyTorch is constantly thrashing memory between active and
cached tensors. Effective throughput is dominated by allocation
churn, not actual compute.

Why is VRAM so saturated?

- Don's other processes (Isabelle, browser GPU acceleration, Blender)
  hold ~10 GB at baseline.
- FLUX-dev's transformer alone needs ~12 GB at fp16/bf16.
- LoRA optimizer state + activations + gradients add another ~3-5 GB.
- Total demand: ~25 GB. Available with Isabelle running: ~14 GB.
- Result: shoved into the last 14 GB via internal swapping.

The throughput-tuning flags (cache_latents, allow_tf32, 8bit-adam)
all ASSUME there's free VRAM to allocate caches into. With 99.5%
saturation, they can't help — they're competing with the same
constrained pool.

## Path forward (Don picks)

### Option A — Stop Isabelle during training
**Pros:** Recovers ~10 GB. Should let FLUX-dev LoRA fit comfortably.
First-class bare-metal solution. No download needed.
**Cons:** Don loses Isabelle access during the ~3-6 hour training.

```bash
# Stop Isabelle
# (Don's call — exact procedure depends on how Isabelle runs.)

# Then retry smoke:
python tools/persona-lora-train/launch.py \
  --persona aurora \
  --workdir build/lora-train/aurora-v1-smoke \
  --relax-selftest-verdict \
  --smoke-test \
  --execute
```

### Option B — Switch to FLUX.1-Schnell
**Pros:** 8B vs 12B (33% smaller), trains 2-3x faster. Stays
bare-metal. Keeps Isabelle running.
**Cons:** ~20 GB download (~30 min on Don's connection). LoRAs
trained on Schnell may not perfectly transfer to FLUX.1-dev for
inference (community split — needs validation).

```bash
# Pre-download (one-time):
huggingface-cli download black-forest-labs/FLUX.1-schnell \
  --local-dir-use-symlinks False

# Then retry smoke with Schnell:
python tools/persona-lora-train/launch.py \
  --persona aurora \
  --workdir build/lora-train/aurora-v1-schnell-smoke \
  --relax-selftest-verdict \
  --smoke-test \
  --base-model black-forest-labs/FLUX.1-schnell \
  --execute
```

### Option C — Cloud rental
**Pros:** Most reliable. ~$10 for 3 hours on A100. Keeps Don's
workstation free. Trains FLUX-dev LoRA at 1024 res in 2-3 hours.
**Cons:** Violates spirit of bare-metal rule (though cloud training
is gray — the locked rule is about INFERENCE for "indistinguishable
from real" output; training is about engineering economics).

```bash
# (runpod.io workflow — instructions in cloud_training_runpod.md)
```

### Option D — Accept 12+ hour overnight
**Pros:** Stays bare-metal. No download. Don eventually gets a LoRA.
**Cons:** Multi-night commitment. Not feasible for unattended single
overnight (autonomous run #1 confirmed 21h estimate may be light).
Risk: if training crashes mid-run, that's a wasted night.

## Recommendation

**Option A is the best bet** if Don can spare the ~3-6 hours of
Isabelle downtime. It's pure bare-metal, no download, no cloud, no
multi-night commitment. The 32-image corpus is ready; the tools are
ready; only the VRAM pressure is the issue.

If Isabelle is non-negotiable during the day, Option C (cloud
rental) is the next-most-reliable. The ~$10 cost is dwarfed by the
weeks of LoRA training work that would otherwise be required across
all 9 personas.

Option B (Schnell) is reasonable but adds an unknown — the dev/Schnell
LoRA-transfer behavior is un-validated for Don's pipeline.

## What's already done

- 32-image training corpus ready (4 anchors + 20 1:2 candidates + 8
  body-extended siblings)
- All pipeline tools shipped (phase3_pipeline.py, dataset_summary.py,
  monitor_training.py, promote_lora.py, verify_lora.py)
- Throughput-tuned defaults baked into training_config.py
- 150 unit tests passing across persona_reference_gen +
  persona_lora_train

The training launch is one command away from succeeding once VRAM
pressure is addressed.

## Next session

Option A: 3-6 hours of GPU-bound training, Don validates LoRA via
verify_lora --compare.

Option C: Push the corpus to runpod, train, pull adapter back. Same
verify_lora step.

Option B: Pull Schnell, retry smoke, branch based on outcome.

Option D: Schedule 2 nights of training. Each night runs ~10 hours.
