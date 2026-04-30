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
├── __main__.py          # python entry shim
├── runner.py            # orchestration + CLI
├── prompt_matrix.py     # framing × lighting × seed expansion (deterministic)
├── backend_fal.py       # fal.ai adapter (gated by PERSONA_REFGEN_LIVE)
├── output_schema.py     # BatchManifest / Candidate / CurationEntry
├── curate.py            # Don-in-loop curation CLI
└── README.md
```

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

### Generate a batch (live fal.ai)

```bash
export PERSONA_REFGEN_LIVE=1
export FAL_KEY=...   # standard fal.ai env var
python tools/persona-reference-gen/__main__.py --persona aurora --batch 2026-05-18a
```

Live mode uses `fal-ai/flux-pro/v1.1-ultra` at aspect ratio `9:16`
(vertical, full-body framing). Override with `--model` / `--aspect-ratio`.

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

2. **Doctrine §8 visual self-test.** ADR-0014 §"Visual self-test gate"
   requires multimodal-vision evaluation of every candidate **before**
   Don sees it. Not yet wired here. Expected shape: a `selftest.jsonl`
   sibling to `curation.jsonl` populated by a vision-model pass that
   scores each candidate on (a) photorealism, (b) full-body framing
   actually achieved, (c) identity alignment with persona anchor.
   Failing candidates should be flagged before the curation CLI surfaces
   them. Tracked as a follow-up.

3. **RealVisXL Lightning backend.** ADR-0015 names FLUX.1-dev and
   RealVisXL Lightning as primitives. Only the FLUX path is wired
   (via fal.ai). RealVisXL is a one-line constant change in
   `backend_fal.DEFAULT_MODEL` once its fal.ai endpoint id is locked.

4. **Local-runtime backend.** ADR-0015 says local FLUX dev runtime is
   acceptable but not required for v0. Not wired. Add a sibling
   `backend_local_flux.py` if Don wants to escape API-credit dependence.

5. **Curation GUI.** Current CLI is the minimum viable Don-in-loop
   surface. Future GUI is explicitly deferred per the scaffold prompt.

## Style match with existing scripts

- File layout mirrors `scripts/persona_generator/` (one module per
  concern, no class hierarchies).
- fal.ai usage style mirrors
  file:///C:/Users/dbhav/Projects/aether/scripts/persona_generator/generate_anchor_set.py
  (the v0 anchor-set generator). The new tool is structured + reproducible
  per ADR-0015; the old script remains for the canonical 4-image anchor
  sets and is **not regenerated** by this tool.
