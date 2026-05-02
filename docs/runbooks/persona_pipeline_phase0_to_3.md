# Persona Pipeline Runbook — Phase 0 → Phase 3 (LoRA training)

> Operator runbook for running a persona's identity pipeline end-to-end
> on local hardware. Covers reference generation (Phase 0), self-test
> evaluation (Phase 2), dataset assembly + LoRA training (Phase 3).
>
> **Owns:** the bare-metal local inference pivot started 2026-05-01.
> **Skips:** the original Phase 1 (local PuLID) — see
> `planning/research/2026-05-02_phase1_identity_locking_options.md`
> for the rationale.

## Prerequisites (one-time setup)

- **GPU:** RTX 3090 Ti (24 GB) or larger. Sequential CPU offload runs
  FLUX.1-dev in <8 GB peak GPU; model offload tier needs ≥14 GB.
- **HF cache:** `black-forest-labs/FLUX.1-dev` already pulled at
  file:///C:/Users/dbhav/.cache/huggingface/hub/.
- **Python deps:** torch 2.11+ / diffusers 0.37+ / transformers 4.57+
  / accelerate / bitsandbytes / torchvision / Pillow.
- **Diffusers training script (for Phase 3):** clone
  https://github.com/huggingface/diffusers somewhere reachable. The
  launcher walks a sibling-clone search list:
    - `examples/dreambooth/train_dreambooth_lora_flux.py`
    - `../diffusers/examples/dreambooth/train_dreambooth_lora_flux.py`
    - `../../diffusers/examples/dreambooth/train_dreambooth_lora_flux.py`

## Phase 0 — Reference image generation

Generate full-body photoreal reference candidates. All Phase 0 work
runs through `tools/persona-reference-gen/`.

### 0a. Single-image baseline (sanity check)

Use this when standing up the pipeline against a new persona for the
first time. One image, ~5 min wall clock with warm pipeline cache.

```bash
PERSONA_REFGEN_LIVE=1 \
  python tools/persona-reference-gen/phase0_baseline.py \
    --persona aurora \
    --batch 2026-05-02-phase0
```

Inspect `personas/aurora/_pipeline/step1_references/2026-05-02-phase0/`
manually. If photoreal looks broken or identity is way off-anchor,
something is wrong with the persona's prompt anchor in
`prompt_matrix.PERSONA_ANCHORS` — fix that before continuing.

### 0b. Default-framings probe (4 images)

Tests whether `prompt_matrix.DEFAULT_FRAMINGS` produces full-body
output reliably. Empirically (Aurora, 2026-05-02) it does NOT —
3/4 framing-fail rate observed. Run anyway as a regression check
when changing framings or moving to a new persona.

```bash
PERSONA_REFGEN_LIVE=1 \
  python tools/persona-reference-gen/phase0_framing_probe.py \
    --persona aurora \
    --batch 2026-05-02-framing-probe
```

### 0c. Aggressive prompt-engineering probe (Plan B)

Tests escalated framing-prompt language (distance, lens, cinematic,
composition fractions). Run when the default-framings probe shows
framing failures.

```bash
PERSONA_REFGEN_LIVE=1 \
  python tools/persona-reference-gen/prompt_engineering_probe.py \
    --persona aurora \
    --batch 2026-05-02-prompt-eng-probe
```

### 0d. Offload strategy override

Default auto-picks `model` offload (≥14 GB free) or `sequential`
(otherwise). Override when needed:

```bash
PERSONA_REFGEN_OFFLOAD=sequential ...   # tightest GPU budget
PERSONA_REFGEN_OFFLOAD=model     ...   # faster, more VRAM
PERSONA_REFGEN_OFFLOAD=none      ...   # full GPU residence (24 GB)
```

## Phase 2 — Doctrine §8 self-test

Run multimodal-vision evaluation on every generated batch BEFORE
human curation. Saves Don's time on obvious defects.

### Backend selection

Two backends:
- `openai`: gpt-4o-mini, retail dependency, deprecated by the
  bare-metal pivot but currently the default until Qwen2-VL-7B is
  validated.
- `qwen2vl`: local `Qwen/Qwen2-VL-7B-Instruct` (preferred). Note:
  Qwen2-VL-2B-Instruct is **insufficient** at categorical reasoning —
  see `planning/research/2026-05-02_qwen2vl_calibration.md`.

```bash
PERSONA_REFGEN_SELFTEST_LIVE=1 \
PERSONA_REFGEN_SELFTEST_BACKEND=qwen2vl \
  python tools/persona-reference-gen/phase0_evaluate.py \
    --persona aurora \
    --batch 2026-05-02-prompt-eng-probe
```

Output lands at `<batch_dir>/selftest.jsonl`. The default 768 long-
edge resize is required to keep vision-token budgets sane.

### Quantization override

Default auto-picks fp16 / int8 / int4 based on free VRAM. Override:

```bash
PERSONA_REFGEN_SELFTEST_QUANT=int4 ...   # tightest GPU budget
PERSONA_REFGEN_SELFTEST_QUANT=fp16 ...   # full precision
```

## Curation — Don in the loop

Don walks every batch's candidates through `curate.py`. By default
the walk hides candidates that the self-test flagged.

```bash
python tools/persona-reference-gen/curate.py \
  --persona aurora \
  --batch 2026-05-02-prompt-eng-probe
```

Verdicts: `keep` | `reject` | `reprompt` | `skip` (== pending).

Auto-curate fallback (when Don is unavailable):

```bash
python tools/persona-reference-gen/auto_curate.py \
  --persona aurora \
  --batch 2026-05-02-prompt-eng-probe
```

Maps selftest `pass` → curation `keep` and selftest `flag` →
curation `reject`. Don's later manual rows take precedence (latest-wins).

## Phase 3 — Identity LoRA training

Build the dataset + plan + run training. All under
`tools/persona-lora-train/`.

### Plan-only (recommended first step)

```bash
python tools/persona-lora-train/launch.py \
  --persona aurora \
  --workdir build/lora-train/aurora-v1
```

Creates `<workdir>/dataset/` with `<n>.png` + `<n>.txt` per training
image, plus `metadata.json` provenance. Prints the accelerate
command. Inspect `<workdir>/training_config.json` and the dataset
images before executing.

### Hyperparam overrides

```bash
python tools/persona-lora-train/launch.py \
  --persona aurora \
  --workdir build/lora-train/aurora-v1 \
  --rank 32 \
  --max-train-steps 2500 \
  --learning-rate 5e-5 \
  --min-photoreal-score 7
```

### Execute training

```bash
python tools/persona-lora-train/launch.py \
  --persona aurora \
  --workdir build/lora-train/aurora-v1 \
  --execute
```

Wall clock: ~6-8 hours on a 3090 Ti at 1500 steps with gradient
checkpointing + bf16. Output adapter at `<workdir>/output/*.safetensors`.

### Move LoRA into place

After training succeeds:

```bash
mkdir -p personas/aurora/loras
mv build/lora-train/aurora-v1/output/aurora_v1.safetensors \
   personas/aurora/loras/
```

The pipeline-status CLI (`tools/persona-reference-gen/pipeline_status.py`)
will then mark Aurora as having a LoRA on disk.

## Phase 4+ (future work)

- Identity LoRA inference path: load the LoRA on top of FLUX.1-dev
  in `backend_local_flux.py` to generate Aurora-locked candidates
  for all 8 remaining personas via the same pipeline.
- Voice clone (Phase 5), video character LoRA (Phase 6), motion
  clips (Phase 7), lip-sync (Phase 8). Separate runbooks when the
  tools land.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ValueError: ... is neither a valid local path nor a valid repo id` | `--backend local-flux` selected without per-backend default model | `runner.run_batch` auto-resolves now (commit `64fdde9`); upgrade if older. |
| FLUX OOM on pipeline load | `enable_model_cpu_offload` insufficient | Set `PERSONA_REFGEN_OFFLOAD=sequential` |
| Qwen2-VL stuck at 100% GPU forever | Vision-token budget blown by full-res images | Already fixed — `_open_and_resize` caps long edge at 768. Upgrade if older. |
| Qwen2-VL returns `framing=yes` for cropped images | 2B is too weak. | Use 7B variant, or fall back to `--backend openai`. |
| `accelerate` not on PATH | Not installed | `pip install accelerate` |
| `train_dreambooth_lora_flux.py` not found | Diffusers repo not cloned | Clone https://github.com/huggingface/diffusers, place at one of the search-list paths. |

## Reference files

- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-01_NIGHT_BARE_METAL_PIVOT.md — strategic redirect
- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-02_AUTONOMOUS_RUN.md — autonomous-run progress
- file:///C:/Users/dbhav/Projects/aether/planning/research/2026-05-02_phase1_identity_locking_options.md — why we skipped Phase 1
- file:///C:/Users/dbhav/Projects/aether/planning/research/2026-05-02_qwen2vl_calibration.md — Phase 2 backend findings
- file:///C:/Users/dbhav/Projects/aether/planning/plans/gpu_queue.md — sequential job tracker
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0014-per-persona-character-pipeline.md — pipeline contract
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0015-reference-image-generation-inside-companion.md — reference-gen scope
