# Handoff — 2026-05-01 night — Bare-metal local inference pivot

> **Strategic redirect from Don tonight.** The persona character pipeline (ADR-0014, Aurora-first per `planning/plans/gpu_queue.md`) abandons retail APIs (fal.ai, OpenAI vision, Veo/Sora/Kling). All inference runs locally on the 3090 Ti. "Indistinguishable from a real human, full-body, full-animation video character" is the moat. Don's words: *"Stop using retail software. It's not good enough. Write the bare-metal software yourself."*

---

## Tonight's session shipped

Two commits on `dev`, both pushed:

| Commit | Subject |
|---|---|
| `343be55` | `test(desktop): Wave 19 — real-executor replay E2E for Wave 13b sink propagation` |
| `9c67da9` | `feat(persona-reference-gen): harden Step 1 — PuLID identity lock + Doctrine §8 self-test` |

Both commits achieved their nominal goals:

1. **Wave 19** — Rust integration test boots `AppState::new()` with the real `DefaultPolicyEngine` + real `ExecutorAllowlistSink` + real `StdFsExecutor` against a tempdir, drives `files_edit_inner` → captures Ask ticket → calls `issue_one_shot_grant_for_pending(Allow)` → replays through the now-populated allowlist → real bytes returned. Closes the Wave 13b coverage gap mock-based tests can't reach. cargo desktop 335 → 336.

2. **persona-reference-gen hardening** — Wired `fal-ai/flux-pulid` identity-conditioning + a new Doctrine §8 multimodal-vision self-test pass scoring photoreal/framing/identity per candidate before Don sees it. Stub paths free + offline; live paths gated. persona_reference_gen test suite 17 → 27.

But the live PuLID probe (4 images, $0.13) exposed a structural ceiling, and that's the load-bearing finding of the session.

---

## The probe finding

`personas/aurora/_pipeline/step1_references/2026-05-01c-probe-live/` (4 PuLID + 4 selftest rows).

Every single candidate flagged:

- `photoreal_score: 7/10` — plausible but with telltale AI signs (slightly glassy eyes, soft skin, perfect symmetry).
- `framing_match: no` (×4) — bust crops, not full-body. PuLID is structurally face-biased; identity-locking gets harder as face area shrinks.
- `identity_match: maybe` (×4) — softer + blonder than the auburn-vibrant anchor, freckles attenuated.
- `verdict: flag` (×4) — gate worked exactly as designed.

Doctrine §8 saved Don 30 minutes of curation hell on bust shots. But it also revealed that **fal-ai/flux-pulid cannot deliver "indistinguishable from real, full-body" no matter how much we tune the prompts** — the bias is structural to the model. Combined with gpt-4o-mini being a retail dependency, the whole fal.ai-and-OpenAI scaffold tops out below Don's bar.

---

## The pivot — bare-metal stack

Locked tonight as a feedback memory: file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/feedback_bare_metal_local_inference.md.

Stack already installed on Don's machine (verified tonight):

- torch 2.11.0+cu128, cuda=True, RTX 3090 Ti
- diffusers 0.37.1, transformers 4.57.6, accelerate 1.13.0, bitsandbytes 0.49.2, huggingface_hub 0.36.2, safetensors 0.8.0-rc.0
- HF cache 110GB at file:///C:/Users/dbhav/.cache/huggingface/hub/
  - `models--black-forest-labs--FLUX.1-dev` ← already downloaded (ready to load)
  - `models--XLabs-AI--flux-dev-fp8` ← quantized fallback for tighter VRAM
  - `models--xlabs-ai--xflux_text_encoders`

Existing FluxPipeline reference already in this repo at file:///C:/Users/dbhav/Projects/aether/.claude/worktrees/agent-a209cefbe70d0ee83/scripts/generate_showcase_scenes.py — diffusers `FluxPipeline.from_pretrained("black-forest-labs/FLUX.1-dev", ...)` with a working sequence already wired. Use as a starting reference for the pattern.

### Realistic ceiling on this hardware

| Layer | Open SOTA | 3090 Ti can run? | Quality ceiling |
|---|---|---|---|
| Photoreal stills | FLUX.1-dev, HiDream-I1, SD3.5-Large | Yes (fp8/fp16) | Indistinguishable-from-real at 1024×1024+ with custom LoRA |
| Identity locking | Local PuLID (FLUX), InstantID, custom IP-Adapter | Yes | Better than fal.ai PuLID (we control conditioning weight) |
| Vision self-test | Qwen2-VL-7B, InternVL2.5, Florence-2 | Yes | Equal to gpt-4o-mini for Doctrine §8 questions, zero ongoing cost |
| Identity LoRA training | diffusers + kohya scripts on FLUX | Yes (overnight) | Custom Aurora LoRA we own end-to-end |
| Character video | Wan 2.1 (5B fits 24GB; 14B tight), HunyuanVideo, LTX-Video | 5B yes | 720p–1080p; HD video at "indistinguishable" tier still needs 80GB+ today |

Honest limit: **HD video at the closed-model "Veo 3 / Sora" tier is not yet achievable on a single 3090 Ti** with open-source weights as of early 2026. Indistinguishable-from-real at 720p–1080p with a custom Aurora pipeline is the realistic short-term target — most companies use retail Sora/Veo, so owning a local 720p–1080p pipeline IS the moat. Pushing higher needs a second GPU, runpod.io rental for training, or waiting for the model frontier.

---

## Phase plan (multi-week, not multi-hour)

| Phase | Description | Effort | Deliverable |
|---|---|---|---|
| **0** | Local FLUX.1-dev inference rig. New module `tools/persona-reference-gen/backend_local_flux.py` mirroring the existing `backend_fal.py` interface. Generate ONE Aurora full-body baseline image with no identity locking. Establish ground truth for unaided FLUX quality on Don's hardware. | 2-3 hrs | One real generation; module wired into runner via `--backend local-flux` |
| **1** | Local PuLID weights for FLUX. Custom `IdentityConditioner` class wrapping the diffusers pipeline. Identity locking under our control, no retail dep. | 4-6 hrs | Aurora identity-locked full-body image |
| **2** | Local vision self-test using Qwen2-VL-7B (preferred) or Florence-2. Replaces `selftest._live_score`'s OpenAI path. | 2-3 hrs | `selftest.py` `_live_score` rewritten against local VLM; live OpenAI path tombstoned |
| **3** | Bootstrap Aurora identity LoRA. Train on the 4 anchor headshots + Phase-0/1 generations. Use diffusers `train_dreambooth_lora_flux.py` or kohya. | 1 overnight + Don curation | Aurora identity LoRA checkpoint |
| **4** | Iterate Step 1 with LoRA + FLUX. New Step 1 batch is identity-locked AND full-body. Curate, re-train final LoRA. | 1-2 days iterative | Final Aurora reference set + final identity LoRA |
| **5+** | Voice clone (Step 3 of ADR-0014), video character LoRA (Step 4), motion clips (Step 5). Each phase uses local models — Wan 2.1 / HunyuanVideo / LTX-Video. | Multiple sessions | Full Aurora character |

---

## What's deprecated (do not extend)

These exist in the repo but are now diagnostic scaffolds, not ship paths:

- file:///C:/Users/dbhav/Projects/aether/tools/persona-reference-gen/backend_fal.py — fal.ai backend. Working, useful for sanity-checks. New work routes through `backend_local_flux.py` instead.
- file:///C:/Users/dbhav/Projects/aether/tools/persona-reference-gen/selftest.py `_live_score` — OpenAI gpt-4o-mini path. Phase 2 replaces with local VLM.

Keep them for now (free + offline stub paths still useful for tests); don't add features.

---

## Repo state at handoff

- branch: `dev`
- tip: `9c67da9` (run `python scripts/current_status.py` to confirm)
- ahead of `@{u}`: 0 (pushed)
- working tree dirty: pre-existing (preview_voice.opus + LoRA training checkpoints) + the live probe outputs at `personas/aurora/_pipeline/` (now gitignored — won't show in `git status` once `.gitignore` is in effect).

Tests at handoff:
- cargo desktop: **336 passed** (was 335)
- persona_reference_gen pytest: **27 passed** (was 17)
- vitest desktop: **288 passed / 25 files** (unchanged)

---

## Phase 0 starting prompt for the next session

Paste into a fresh Claude session at `C:\Users\dbhav\Projects\aether`:

```
You are starting Phase 0 of the bare-metal local inference pivot for the
Companion/Aether persona character pipeline. Read in order:

1. python scripts/current_status.py — authoritative state
2. file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-01_NIGHT_BARE_METAL_PIVOT.md — this file
3. file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/feedback_bare_metal_local_inference.md — locked rule
4. file:///C:/Users/dbhav/Projects/aether/planning/01_product_doctrine.md §5/§6/§7/§8
5. file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0014-per-persona-character-pipeline.md
6. file:///C:/Users/dbhav/Projects/aether/.claude/worktrees/agent-a209cefbe70d0ee83/scripts/generate_showcase_scenes.py — existing diffusers FluxPipeline pattern in this repo (reference, do not edit)

Goal of this session:

Phase 0 — local FLUX.1-dev inference rig. Generate ONE Aurora full-body
baseline image with no identity locking, just text. Establishes ground
truth for unaided FLUX quality on Don's RTX 3090 Ti.

Concretely:

1. Create file:///C:/Users/dbhav/Projects/aether/tools/persona-reference-gen/backend_local_flux.py.
   Mirror the interface of the existing backend_fal.py:
     - generate(prompt_text, negative_prompt, seed, out_path, model,
       aspect_ratio, reference_image_url=None) -> FalResult-shaped result
     - is_live_mode() / LIVE_ENV_VAR
     - Stub path that produces a tiny PNG so default pytest stays free
     - Live path that loads FLUX.1-dev via diffusers FluxPipeline,
       runs inference at 1024x1536 (9:16 close approximation),
       writes PNG to out_path
2. Wire backend selection into runner.py via --backend {fal,local-flux}.
   Default stays fal (don't break existing behavior); --backend local-flux
   routes through the new module. Stub mode is shared.
3. Add tests/unit/persona_reference_gen/test_backend_local_flux.py — at
   least the stub-path output shape + module-import smoke. Don't load
   FLUX in tests (24GB load).
4. Manually run: PERSONA_REFGEN_LIVE=1 python tools/persona-reference-gen/__main__.py --persona aurora --batch 2026-05-02-phase0 --backend local-flux --notes "Phase 0 baseline — local FLUX.1-dev unaided" with axes manually trimmed to 1 framing × 1 lighting × 1 seed (one image only).
5. Inspect the resulting image with the Read tool (multimodal vision).
   Self-test: photoreal/framing/identity. Report verdict to Don.

Hard constraints:

- bash tools/check-pre-commit.sh must exit clean before any commit
- cargo isn't on PATH by default in Git Bash: export PATH="/c/Users/dbhav/.cargo/bin:$PATH"
- Explicit-path commits only: git commit -- <paths>. Never -A / -u / .
- Pre-existing dirty paths (preview_voice.opus, LoRA checkpoint dirs)
  must NEVER be staged
- One layer per session per CLAUDE.md §1 — apps/desktop/ is its own scope;
  this Phase 0 work is entirely under tools/persona-reference-gen/ +
  tests/, no overlap

VRAM budget: FLUX.1-dev unquantized needs ~24GB. If OOM, fall back to
FLUX-dev-fp8 (XLabs-AI variant, already cached). The runner module
should expose a model_id parameter so the swap is one-line.

Phase 0 is finished when one Aurora image lands on disk that you've
vision-evaluated and reported to Don. Don decides whether quality is
good enough to proceed to Phase 1 (local PuLID) or whether to swap base
model first (HiDream-I1, SD3.5-Large).
```

---

## Don-decisions still owed (unchanged from prior handoff)

- L4 vs L7 Guest-mode contradiction — surgical sweep waits on Don's call.
- Drag-drop attachment phase scoping — 6 questions in file:///C:/Users/dbhav/Projects/aether/planning/research/2026-05-01_drag_drop_attachment_ux.md §5.
- **Wave 19 UI half** — Playwright used-as-user against `pnpm tauri dev` requires `tauri-driver` + `msedgedriver` infrastructure that does not exist in repo today. Rust integration test (this session) closed the load-bearing backend coverage. UI piece is owed but the bigger leverage right now is the Phase 0 bare-metal pivot.

---

## Useful reference paths

- file:///C:/Users/dbhav/Projects/aether/scripts/current_status.py
- file:///C:/Users/dbhav/Projects/aether/CLAUDE.md
- file:///C:/Users/dbhav/Projects/aether/planning/01_product_doctrine.md
- file:///C:/Users/dbhav/Projects/aether/planning/plans/gpu_queue.md
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0014-per-persona-character-pipeline.md
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0015-reference-image-generation-inside-companion.md
- file:///C:/Users/dbhav/Projects/aether/tools/persona-reference-gen/README.md
- file:///C:/Users/dbhav/Projects/aether/tools/persona-reference-gen/backend_fal.py — deprecated reference, do not extend
- file:///C:/Users/dbhav/Projects/aether/tools/persona-reference-gen/selftest.py — `_live_score` OpenAI path deprecated
- file:///C:/Users/dbhav/Projects/aether/tools/persona-reference-gen/runner.py
- file:///C:/Users/dbhav/Projects/aether/.claude/worktrees/agent-a209cefbe70d0ee83/scripts/generate_showcase_scenes.py — existing FluxPipeline pattern
- file:///C:/Users/dbhav/.cache/huggingface/hub/models--black-forest-labs--FLUX.1-dev/ — already-cached weights
- file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/feedback_bare_metal_local_inference.md — locked rule
