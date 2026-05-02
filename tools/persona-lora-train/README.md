# tools/persona-lora-train

LoRA training pipeline for the per-persona identity layer.

Phase 3 of the bare-metal local inference pivot
(file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-01_NIGHT_BARE_METAL_PIVOT.md).
Consumes the curated reference image sets from
`tools/persona-reference-gen/` and trains a per-persona LoRA against
`black-forest-labs/FLUX.1-dev` so the persona's identity is locked
into a small (~50-200 MB) adapter the inference path loads on top of
the base model.

## Scope

- **In scope:** dataset assembly from `personas/<slug>/_pipeline/step1_references/<batch_id>/`,
  caption template per persona, training launcher around
  `train_dreambooth_lora_flux.py` (or kohya), checkpoint provenance.
- **Out of scope:** the inference path (lives in
  `tools/persona-reference-gen/backend_local_flux.py`), the persona
  reference generator itself, video character LoRAs (Phase 4+).

## Layout (current)

```
tools/persona-lora-train/
├── __init__.py
├── dataset_builder.py    # GPU-free dataset assembly; pure Python
├── (TBD) train.py        # Launches diffusers DreamBooth-LoRA-FLUX
├── (TBD) config_aurora.toml
└── README.md
```

## Dataset shape

`build_dataset(persona_slug, output_dir)` produces a flat directory
that `train_dreambooth_lora_flux.py` consumes verbatim:

```
<output_dir>/
├── 00.png
├── 00.txt        ← caption for 00.png
├── 01.png
├── 01.txt
├── ...
└── metadata.json ← per-image provenance (batch id, prompt id, scores)
```

### Filtering rules (locked)

A candidate from a Step 1 batch is included only if **all** apply:

- `curation.jsonl` verdict is `keep` (Don's hand pick).
- `selftest.jsonl` verdict is `pass` AND `photoreal_score >=
  min_photoreal_score` (Doctrine §8 gate). Candidates with no
  `selftest.jsonl` row are included (not yet evaluated; defer to
  curation alone).
- Image file actually exists on disk.

The four `personas/<slug>/avatar/{anchor,portrait,profile_left,
profile_right}.png` images are included unconditionally when
`include_anchor_set=True` (default) — these are the v0 anchors Don
already trusts.

### Captions

Each image gets a one-line caption composed from the persona's
**instance token** plus framing + lighting from the source manifest:

```
aurora_nash, photorealistic, full-body shot head to feet visible standing neutral pose, soft natural daylight from a north-facing window
```

The instance token is per-persona (see
`DEFAULT_INSTANCE_TOKEN_BY_PERSONA`) and is intentionally distinct
from common English words so it doesn't collide with FLUX's prior.

## Training launcher (TBD — Phase 3 follow-up)

Will wrap `diffusers/examples/dreambooth/train_dreambooth_lora_flux.py`
with persona-specific config:

- LoRA rank 16-32 (Aurora-first; tune)
- Mixed precision bf16
- Gradient checkpointing
- Steps 1000-2000
- Learning rate 1e-4 cosine
- Resolution 1024 (matches inference target)
- Output: `personas/<slug>/loras/<persona>_v<n>.safetensors`

Hardware budget: ~10-15 GB VRAM with gradient checkpointing on the
3090 Ti. Overnight run (~6-8 hours per LoRA at 1500 steps).

## Usage (dataset assembly only — current scope)

```bash
python -c "
from pathlib import Path
import sys
sys.path.insert(0, 'tools/persona-lora-train')
from dataset_builder import build_dataset
report = build_dataset(
    'aurora',
    Path('build/lora-train/aurora-v1'),
    min_photoreal_score=7,
)
print(f'wrote {report.num_images} training images')
"
```

## Tests

```bash
pytest tests/unit/persona_lora_train/
```

GPU-free. Tests cover the full filter matrix (anchor inclusion, batch
filtering, curation verdict gating, selftest score gating).
