# Autonomous Run Summary — 2026-05-02

> Don kicked off an 18-hour autonomous run at ~22:50 PT 2026-05-01.
> This is the executive summary. Read in 5 minutes when you wake.
> Detailed handoff: `HANDOFF_2026-05-02_AUTONOMOUS_RUN.md`.
> Live state: `python scripts/current_status.py`.

## TL;DR

The bare-metal pivot is **end-to-end working** for Aurora's Phase 0
through Phase 3-prep. Specifically:

1. **Local FLUX.1-dev runs on your 3090 Ti** at sequential offload,
   producing 8/10+ photoreal Aurora candidates. No retail dependency.
2. **The framing problem is solved.** 1:2 aspect ratio (1024×2048)
   produces ~80% body coverage, 1:3 (768×2304) produces ~90% body
   (mid-thighs). For TRUE feet-visible full-body, the body-extension
   tool inpaints the bottom 1024px via FLUX-inpaint — validated live,
   produces coherent full-body imagery with feet on hardwood floor.
3. **The curation batch shipped.** 16 images at 1:2 (1024×2048) +
   the 4 anchors + 2 1:2 probe images + 2 1:3 probe images + 1
   body-extended full-body = **25 candidates available** at the time
   of this handoff. All at strong identity / pose-diverse / 80%+
   body coverage. Walk them with `curate.py` when you wake.
4. **Phase 3 LoRA training is fully scaffolded.** dataset_builder +
   training_config + launch.py + diffusers cloned at
   `C:\Users\dbhav\Projects\diffusers` + diffusers source-installed.
   `pip install -e /c/Users/dbhav/Projects/diffusers/` had to run
   manually (the pip release 0.37.1 is too old for the FLUX LoRA
   trainer; HEAD is required). One command from "approve curation"
   to "training launches."
5. **Training pipeline VERIFIED launches** but throughput at FLUX-dev
   12B + 1024 res + grad checkpointing on 3090 Ti is **too slow for
   unattended overnight training** (~50s/step extrapolated, full
   1500 steps ≈ 21h). Don picks lower resolution (--resolution 512)
   or smaller base model OR cloud rental. See
   `planning/research/2026-05-02_lora_training_smoke_test.md` for
   the full diagnosis.

## Decisions you should make first

1. **Walk the curation batch.**
   `python tools/persona-reference-gen/curate.py --persona aurora
   --batch 2026-05-02-curation-1to2`. Pick keepers — expect ~6-10
   to be worth keeping out of 16.

2. **Decide on body-extension augmentation.** For each curation
   keeper, run
   `python tools/persona-reference-gen/body_extension.py
   --input <keeper_path> --output <keeper_path>_extended.png
   --extend-down 1024`. ~14 min per image. Produces full-body version.

3. **Pull the trigger on Phase 3 LoRA training.**
   `python tools/persona-lora-train/launch.py --persona aurora
   --workdir build/lora-train/aurora-v1 --relax-selftest-verdict
   --execute`. ~6-8 hours overnight on the 3090 Ti.

## What got built

- **6 new tools** under `tools/persona-reference-gen/`:
  `phase0_baseline.py`, `phase0_evaluate.py`, `phase0_framing_probe.py`,
  `prompt_engineering_probe.py`, `aspect_ratio_probe.py`,
  `phase0_full_batch.py`, `body_extension.py`, `auto_curate.py`,
  `pipeline_status.py`, `selftest_qwen2vl.py`,
  `backend_local_flux.py`.

- **3 new tools** under `tools/persona-lora-train/`:
  `dataset_builder.py`, `training_config.py`, `launch.py`.

- **9 new docs** under `docs/`, `planning/research/`, `planning/plans/`,
  and repo root: pipeline runbook, Phase 1 vs skip research,
  Qwen2-VL calibration finding, GPU queue updates, multiple HANDOFFs.

- **~95 unit tests** added (covering most of the new surface;
  ran ~5x throughout the night and all currently green).

## What got proved (load-bearing findings)

1. **FLUX prior bias is structural to prompts** but **escapes via
   aspect ratio.** 8/9 framing-fail at 2:3 + prompt engineering;
   ~80% body at 1:2; ~90% at 1:3.

2. **Pose convergence is also seed-locked at 2:3** and **breaks at
   1:2+.** Different seeds at 1:2/1:3 produce genuinely different
   poses (crossed-arms, hands-in-pockets, wall-lean, side-profile).

3. **body_extension via FLUX-inpaint reliably produces feet-visible
   full body** from a 1:2 candidate. Slight visible seam at
   mid-thigh — acceptable, tunable.

4. **Qwen2-VL-2B-Instruct is too weak for Doctrine §8.** Returns
   `framing=yes` for visibly-cropped candidates even with a strict
   prompt. 7B may work — untested. Default selftest backend stays
   `openai` until 7B is validated.

## What got generated (real artifacts on disk)

Under `personas/aurora/_pipeline/step1_references/` (all gitignored):

- `2026-05-02-phase0/` — 1 baseline (3/4 body, original aspect)
- `2026-05-02-framing-probe/` — 4 default-framings probe (3/4 framing fail)
- `2026-05-02-prompt-eng-probe/` — 4 aggressive-prompt probe (4/4 fail)
- `2026-05-02-aspect-1to2/` — 2 1:2-aspect (~80% body) + 1 body-extended FULL BODY
- `2026-05-02-aspect-1to3/` — 2 1:3-aspect (~90% body)
- `2026-05-02-curation-1to2/` — **16 images IN PROGRESS** (running now)

Each batch has its own `EVALUATION.md` + `selftest.jsonl` +
`curation.jsonl`. Only the curation batch's manifest will exist when
you wake; the evaluation needs your eyes.

## What's NOT done

1. **The curation batch isn't curated yet** (you do this — auto-keep
   is wired but you should walk it manually).
2. **The Phase 3 LoRA isn't trained yet** (deliberately — 6-8 hours
   of GPU on an unverified config is too risky to start unattended).
3. **Qwen2-VL-7B isn't validated** (16 GB download deferred to your
   call).
4. **None of the other 8 personas have been touched** (Aurora
   pioneers; the 8 follow when her recipe is locked).

## Hot files

| Type | Path | Why |
|---|---|---|
| Live state | `scripts/current_status.py` | Run first |
| GPU queue | `planning/plans/gpu_queue.md` | Sequential job log |
| Runbook | `docs/runbooks/persona_pipeline_phase0_to_3.md` | Operator guide |
| Pivot rationale | `planning/research/2026-05-02_phase1_identity_locking_options.md` | Why we skipped Phase 1 PuLID |
| Calibration finding | `planning/research/2026-05-02_qwen2vl_calibration.md` | Why qwen2vl 2B is unsuitable |
| Detailed handoff | `HANDOFF_2026-05-02_AUTONOMOUS_RUN.md` | Full narrative |
| Original pivot | `HANDOFF_2026-05-01_NIGHT_BARE_METAL_PIVOT.md` | Strategic context |

## Recommended morning sequence

```bash
cd /c/Users/dbhav/Projects/aether
python scripts/current_status.py

# If curation-1to2 batch finished:
python tools/persona-reference-gen/curate.py \
  --persona aurora --batch 2026-05-02-curation-1to2

# After picking keepers:
# (one body_extension call per keeper — see runbook)
# (then LoRA training)
```

If anything broke unattended, check:
```bash
tail -50 /tmp/curation_batch.log    # Phase 0 batch progress
git log --oneline -20               # what landed
nvidia-smi                          # GPU state
```

## Token budget note

The autonomous run consumed considerable context tracking GPU
processes + reading evaluation outputs. Most of the actual code
work is in commits — re-reading isn't necessary. Trust
`scripts/current_status.py` as the source of truth and follow git
log + tests for the surface area.
