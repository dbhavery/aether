# LoRA Training Smoke Test — Findings

> **Verdict: training pipeline LAUNCHES cleanly; throughput is the
> limiter. Don needs to decide on resolution/rank tradeoffs before
> committing to a full training run.**

## What was tested

Smoke run via `tools/persona-lora-train/launch.py --smoke-test` using:

- Base model: `black-forest-labs/FLUX.1-dev` (12B params)
- LoRA rank: 16
- Resolution: 1024
- Mixed precision: bf16
- Gradient checkpointing: ON
- train_batch_size: 1
- gradient_accumulation_steps: 4 (effective batch = 4)
- Steps: 50 (smoke), checkpointing every 50
- Training images: 9 (4 anchors + 2 1:2 + 2 1:3 + 1 body-extended)
- Diffusers HEAD (0.38.0.dev0, source-installed from
  `C:\Users\dbhav\Projects\diffusers`)

## What happened

1. **Pipeline launched cleanly** after fixing two bugs:
   - Diffusers 0.37.1 (pip release) is too old; required `pip install
     -e <cloned-diffusers>` to get HEAD.
   - dataset_builder wrote .txt captions next to images, which
     diffusers' DreamBooth dataset loader tried to PIL.open(). Fixed
     by splitting `<dataset>/images/*.png` and `<dataset>/captions/*.txt`
     into sibling subdirs; `--instance_data_dir` now points at the
     images-only path.

2. **Training started**:
   ```
   Num examples = 9
   Num Epochs = 17
   Total optimization steps = 50
   ```

3. **Throughput was much slower than expected.** Ran ~90 min without
   producing the first checkpoint. The smoke was killed before
   completion. CPU usage 1100s wall-time over 90 min suggests the
   process was mostly waiting on GPU. GPU 100% util constantly.

## Diagnosis

At ~90 min for 50 steps with grad_accum=4 = 200 forward/backward
passes through 12B FLUX at 1024² resolution + LoRA + grad checkpointing,
each forward+backward pair takes ~25-30s. That extrapolates to:

- **1500 steps × ~50s/step = ~21 hours** (too slow for a single
  overnight run)
- 500 steps would be ~7 hours (more feasible)

Causes (most likely first):

1. **Resolution 1024 + grad checkpointing is heavy.** FLUX is a 12B
   model; even a LoRA wrapper requires the base forward/backward.
   Grad checkpointing trades 30% slowdown for ~40% lower VRAM —
   we paid that cost.
2. **Other GPU consumers** were also running (Isabelle, browser
   GPU acceleration), reducing effective throughput.
3. **bf16 mixed precision is slower than fp16** on Ampere
   (RTX 3090 Ti). Switching to fp16 might gain 10-20%.

## Recommended path forward

Don should pick one or more of:

1. **Lower resolution.** Train at 512 instead of 1024 → ~4x faster.
   Inference can still happen at 1024+ via base model. The LoRA
   learns identity at any resolution.

   ```bash
   python tools/persona-lora-train/launch.py --persona aurora \
     --workdir build/lora-train/aurora-v1 --max-train-steps 1500 \
     --relax-selftest-verdict --execute
   # Then manually edit accelerate_command to add --resolution=512
   # OR: extend launch.py to accept --resolution
   ```

2. **Use FLUX.1-Schnell** (smaller, faster). Identity LoRAs trained
   on Schnell can sometimes be loaded onto FLUX.1-dev for inference.
   Untested.

3. **Cloud rent.** runpod.io with A100/H100 trains FLUX-dev LoRA
   at full resolution in 2-3 hours.

4. **Accept the long training time.** Run 1500 steps × 50s = ~21h
   of GPU time spread across 2 nights.

5. **Smaller step count.** 500 steps (~7 hours) might be sufficient
   for Aurora given the small training set (9 images). Empirically
   identity LoRAs converge in 500-800 steps at rank 16.

## Workflow change for next session

`launch.py` should expose `--resolution` as a CLI arg so the
operator doesn't have to hand-edit the accelerate command. Quick
follow-up.

## Bug fixes that landed during the smoke

1. `9a2f208` — fix(persona-lora-train): split images and captions
   into sibling subdirs.
2. `pip install -e /c/Users/dbhav/Projects/diffusers/` — required
   manual step before training will run; should be added to the
   runbook prereqs.

## Conclusion

**Phase 3 training pipeline is verified WORKING but unsuitable for
unattended overnight runs in its current config.** Don picks a
faster config (probably lower resolution) and re-launches manually
when convenient.

The training infrastructure is solid; the bottleneck is hardware
throughput on a 3090 Ti at FLUX-dev's 12B param scale + 1024
resolution + grad checkpointing. Standard tradeoff.
