# tools/persona-reference-gen

Structured, reproducible, batch-oriented reference-image generator for the
public-cast personas. Implements **ADR-0014 Step 1** (Don-curated full-body
photoreal reference set) and is the module specified by **ADR-0015**
(reference-image generation lives inside Companion, not in CIGE/Forge).

This tool unblocks the Aurora kickoff in
file:///C:/Users/dbhav/Projects/aether/planning/plans/gpu_queue.md
(Phase 1, Step 1).

## ADR cross-links

- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0015-reference-image-generation-inside-companion.md
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0014-per-persona-character-pipeline.md
- file:///C:/Users/dbhav/Projects/aether/planning/plans/gpu_queue.md

## Scope

Produces curated **full-body photoreal** reference image sets for the public
cast personas. Doctrine §5 — no headshot intermediate — is enforced in
`prompt_matrix.py` via `validate_framings`: any framing string containing
`headshot`, `head and shoulders`, `bust`, `face only`, etc. is rejected.

This tool **is not** for regenerating the existing 9-persona v0 anchor sets
under `personas/<slug>/avatar/`. Those are canonical. This tool produces the
full-body reference sets that ADR-0014 Step 2 (identity LoRA) consumes.

## Layout

```
tools/persona-reference-gen/
├── __init__.py
├── __main__.py             # python entry shim
├── runner.py               # orchestration + CLI (--backend {fal,local-flux})
├── phase0_baseline.py      # one-off 1×1×1 driver — bare-metal Phase 0
├── prompt_matrix.py        # framing × lighting × seed expansion (deterministic)
├── backend_fal.py          # fal.ai adapter — DEPRECATED diagnostic scaffold (bare-metal pivot)
├── backend_local_flux.py   # local FLUX.1-dev adapter on the 3090 Ti — bare-metal Phase 0/1+
├── selftest.py             # Doctrine §8 dispatcher (openai | qwen2vl | stub)
├── selftest_qwen2vl.py     # local Qwen2-VL-7B Doctrine §8 backend — bare-metal Phase 2
├── output_schema.py        # BatchManifest / Candidate / SelfTestRow / CurationEntry
├── curate.py               # Don-in-loop curation CLI
└── README.md
```

## Bare-metal pivot (2026-05-01 → present)

Per file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-01_NIGHT_BARE_METAL_PIVOT.md
and file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/feedback_bare_metal_local_inference.md
this tool is migrating off retail APIs onto the local 3090 Ti.

| Phase | Scope | Module | Status |
| --- | --- | --- | --- |
| 0 | Local FLUX.1-dev unaided baseline | `backend_local_flux.py` | scaffolded; awaiting first live image |
| 1 | Local PuLID identity locking | `backend_local_flux.py` (sibling `IdentityConditioner` TBD) | not started |
| 2 | Local Qwen2-VL Doctrine §8 selftest | `selftest_qwen2vl.py` | scaffolded; awaiting first live evaluation |
| 3 | Aurora identity LoRA training | `tools/persona-lora-train/` (TBD) | not started |
| 4 | Iterate Step 1 with LoRA + FLUX | runner | not started |
| 5+ | Voice clone, video character LoRA, motion clips, lip-sync | separate tools | not started |

`backend_fal.py` and `selftest._live_score` (OpenAI) remain in-repo as
deprecated diagnostic scaffolds. New work goes through the local
adapters.

## Outputs (per ADR-0015 §"Outputs")

```
personas/<slug>/_pipeline/step1_references/<batch_id>/
├── manifest.json        # all inputs (prompts, seeds, model id, fal request ids)
├── images/
│   └── <prompt_id>__<idx>.png
└── curation.jsonl       # appended by curate.py — Don's verdicts
```

`manifest.json` is the reproducibility contract: re-running with the same
persona slug, axes, model, and aspect ratio produces an identical prompt set
and identical fal.ai request payloads.

## Usage

### Generate a batch (stub backend — default, free)

```bash
python tools/persona-reference-gen/__main__.py \
    --persona aurora \
    --batch 2026-05-18a \
    --notes "Aurora kickoff per gpu_queue.md"
```

The default backend is a deterministic stub that writes 1×1 PNG placeholders
keyed off seed. This lets the manifest pipeline be exercised end-to-end
without burning fal.ai credits.

### Generate a batch (live fal.ai — DEPRECATED scaffold)

```bash
export PERSONA_REFGEN_LIVE=1
export FAL_KEY=...   # standard fal.ai env var
python tools/persona-reference-gen/__main__.py --persona aurora --batch 2026-05-18a
```

Live mode uses `fal-ai/flux-pro/v1.1-ultra` at aspect ratio `9:16`
(vertical, full-body framing). Override with `--model` / `--aspect-ratio`.

This path is deprecated by the bare-metal pivot — kept as a
diagnostic scaffold but no new work should land here.

### Generate a batch (live local FLUX.1-dev — bare-metal Phase 0/1+)

```bash
export PERSONA_REFGEN_LIVE=1
python tools/persona-reference-gen/__main__.py \
    --persona aurora --batch 2026-05-02a --backend local-flux
```

Live mode loads `black-forest-labs/FLUX.1-dev` via diffusers, runs
inference on the local 3090 Ti at 1024×1536 (9:16). The pipeline
loader picks an offload strategy automatically based on free VRAM:

- ≥14 GB free → `enable_model_cpu_offload` (~12 GB peak, fast)
- otherwise → `enable_sequential_cpu_offload` (~3-4 GB peak, slower)

Override with `PERSONA_REFGEN_OFFLOAD={model,sequential,none}` when you
want explicit control. cuda OOM during pipeline setup falls back to
sequential automatically.

### Phase 0 one-off baseline

```bash
PERSONA_REFGEN_LIVE=1 python tools/persona-reference-gen/phase0_baseline.py \
    --persona aurora --batch 2026-05-02-phase0
```

Generates ONE image only — axes pinned to 1×1×1. Used to establish
ground truth for unaided FLUX quality on local hardware before adding
identity-locking layers.

### Curate the batch (Don-in-loop)

```bash
python tools/persona-reference-gen/curate.py --persona aurora --batch 2026-05-18a
```

Walks Don through each candidate and records `keep | reject | reprompt`
with optional notes into `curation.jsonl`. Latest-wins per
(prompt_id, candidate_index).

For non-interactive smoke runs use `--auto-keep`. To inspect current state
without prompting use `--report-only`.

### Why no `python -m tools.persona_reference_gen`

ADR-0015 specifies the directory name `tools/persona-reference-gen/`
(hyphen). Python packages can't have hyphens in their import paths. So
the canonical invocation is the explicit path:

```
python tools/persona-reference-gen/__main__.py --persona ... --batch ...
```

This matches the convention used by the sibling tool
file:///C:/Users/dbhav/Projects/aether/tools/build-persona-pack/build.py .

## Reproducibility

- `prompt_matrix.expand_matrix` is deterministic in iteration order
  (framing, then lighting, then seed) and hashes inputs into stable
  `prompt_id`s. Two invocations with identical args produce
  byte-identical PromptSpec lists.
- `backend_fal.generate` passes `seed` through to fal.ai.
- `BatchManifest` records the full axes lists, model id, aspect ratio,
  and persona_yaml SHA-256 — every input that determines the output.
- `manifest.json` round-trips through `BatchManifest.from_json` exactly
  (covered by `tests/unit/persona_reference_gen/test_manifest_roundtrip.py`).

## Testing

```bash
pytest tests/unit/persona_reference_gen/
```

The default `pytest` run never calls fal.ai. Live calls require
`PERSONA_REFGEN_LIVE=1` to be exported.

## Doctrine §5 enforcement

`prompt_matrix.DEFAULT_FRAMINGS` contains only full-body and 3/4-body
framings. `validate_framings` rejects any custom framing containing
forbidden headshot/bust tokens. This is the single chokepoint — adding a
new framing axis without going through validation is a §5 violation.

## What's stubbed (TODO for follow-up sessions)

1. **Persona anchor migration.** `prompt_matrix.PERSONA_ANCHORS` is a v0
   dict with Aurora only. The canonical home for these is a new
   `reference_prompt_anchor` field in `personas/<slug>/persona.yaml`
   (one-line schema bump). Aurora-first; backfill the other 8 only when
   they enter Phase 2 of the gpu_queue.

2. **Doctrine §8 visual self-test — local backend live evaluation.**
   The OpenAI gpt-4o-mini path (`selftest._live_score`) and the local
   Qwen2-VL path (`selftest_qwen2vl.score`) both work; only the openai
   path has been exercised against real candidates. Once Phase 0
   delivers a baseline image, the qwen2vl path should be evaluated
   side-by-side and the dispatcher's default flipped to `qwen2vl`.

3. **Identity LoRA training (Phase 3 of the pivot).** No tool exists
   yet under `tools/persona-lora-train/`. Aurora-first via
   `train_dreambooth_lora_flux.py` or kohya, fed by the curated Phase
   0/1 reference set.

4. **Local PuLID identity-conditioning (Phase 1 of the pivot).** Not
   yet wired into `backend_local_flux.py`. Requires PuLID-FLUX weights
   from `guozinan/PuLID` and a custom IdentityConditioner wrapping
   FluxPipeline's text-conditioning hook.

5. **RealVisXL Lightning backend.** ADR-0015 names FLUX.1-dev and
   RealVisXL Lightning as primitives. Only the FLUX paths are wired.
   RealVisXL is a one-line `DEFAULT_MODEL` swap in either backend once
   its endpoint id is locked.

6. **Curation GUI.** Current CLI is the minimum viable Don-in-loop
   surface. Future GUI is explicitly deferred per the scaffold prompt.

## Style match with existing scripts

- File layout mirrors `scripts/persona_generator/` (one module per
  concern, no class hierarchies).
- fal.ai usage style mirrors
  file:///C:/Users/dbhav/Projects/aether/scripts/persona_generator/generate_anchor_set.py
  (the v0 anchor-set generator). The new tool is structured + reproducible
  per ADR-0015; the old script remains for the canonical 4-image anchor
  sets and is **not regenerated** by this tool.
