# Handoff — 2026-05-02 — autonomous bare-metal pivot continuation

> Don kicked off an 18-hour autonomous run at ~22:50 PT 2026-05-01. This
> is the ongoing log. **Read** `python scripts/current_status.py` first
> for live state.

---

## What landed (commits, oldest first on top of `c25acc0` baseline)

| Commit | Subject |
|---|---|
| `64fdde9` | `fix(persona-reference-gen): auto-resolve local-flux model + Phase 0 driver` |
| `8a90d14` | `feat(persona-reference-gen): Phase 2 — local Qwen2-VL selftest backend` |
| `a481f51` | `docs(planning): claim GPU queue slot for Aurora Phase 0 baseline` |
| `a27972e` | `docs(persona-reference-gen): update README for bare-metal pivot Phase 0/2` |
| `dcf528f` | `feat(persona-lora-train): scaffold Phase 3 prep — LoRA training dataset builder` |
| `c405081` | `feat(persona-reference-gen): Phase 0 selftest evaluator` |
| `c2f115d` | `feat(persona-lora-train): training plan + accelerate command builder` |
| `401b4fa` | `feat(persona-lora-train): launcher CLI for persona LoRA training` |
| `8508efe` | `feat(persona-reference-gen)+docs: curate honors selftest flags + Phase 0 GPU queue update` |

Net: Phase 0 (local FLUX) + Phase 2 (local Qwen2-VL selftest) +
Phase 3 prep (dataset_builder + training_config + launch) all
shipped, plus the runner bug fix that made Phase 0 actually executable.

---

## Phase 0 GPU run — done

First and most important deliverable of the session. Live FLUX.1-dev
generated **one Aurora full-body baseline image**.

- **Image:** file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-phase0/images/34698986410996a6__0.png
- **Evaluation:** file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-phase0/EVALUATION.md
- **Selftest row:** file:///C:/Users/dbhav/Projects/aether/personas/aurora/_pipeline/step1_references/2026-05-02-phase0/selftest.jsonl
- **Wall clock:** 21 min total (15:18 pipeline load + 4:12 inference,
  sequential CPU offload to keep peak GPU ≤ 5 GB on a workstation
  already holding ~14 GB)

### Doctrine §8 verdict

| Axis | Value | |
|---|---|---|
| `photoreal_score` | **8/10** | Strong — better than the deprecated `fal-ai/flux-pulid` 7/10. |
| `framing_match` | **no** | 3/4 body / waist-up crop produced despite "full-body, head-to-feet" framing. **Same structural bias PuLID showed.** |
| `identity_match` | **maybe** | Attenuated from anchor — softer auburn, hazel-not-green, fewer freckles, V-neck not turtleneck. |
| `verdict` | **flag** | Framing failure is a doctrine §5 hard-gate. |

### Strategic implication: rethink Phase 1 vs Phase 3 sequencing

The handoff's planned Phase 0 → Phase 1 (local PuLID) → Phase 3 (LoRA)
sequence was designed before this baseline shipped. Phase 0 reveals:

1. **The base model is sufficient.** Photoreal at 8/10 hits the
   "indistinguishable from real" bar at 1024×1536. We don't need to
   swap to HiDream-I1 / SD3.5-Large.
2. **Framing bias is structural to FLUX, not PuLID-specific.** The
   prior probe blamed PuLID; this baseline shows unaided FLUX has the
   same problem. PuLID won't fix it.
3. **Identity locking IS load-bearing.** Text prompts can't pin
   Aurora's distinctive features.

**Decision Don needs to make:** Phase 1 (local PuLID, 4-6 hr wiring,
weak intermediate that still has framing bias) vs. **skip directly to
Phase 3 (LoRA training, 6-8 hr overnight, owns identity AND can be
trained on full-body crops to teach framing).** The Phase 3 path is
cleaner if it works — fewer moving parts, better moat (own the LoRA
end-to-end). EVALUATION.md §"Recommended Phase 1 path" has the full
argument.

---

## Phase 2 — local Qwen2-VL selftest backend

Shipped in `8a90d14`. `selftest_qwen2vl.py` is a sibling to
`selftest.py`'s OpenAI gpt-4o-mini path, dispatched via
`PERSONA_REFGEN_SELFTEST_BACKEND=qwen2vl`. Adaptive quantization
picks fp16 / int8 / int4 based on free VRAM.

**Not yet exercised against a real image.** Phase 0's evaluation in
EVALUATION.md was done by claude-opus-4-7 multimodal vision (manual,
written into selftest.jsonl with backend tag `claude-opus-4-7/manual`)
because the qwen2vl path has never been live-tested. Recommended next
step: run `python tools/persona-reference-gen/phase0_evaluate.py
--persona aurora --batch 2026-05-02-phase0 --backend qwen2vl` with
`PERSONA_REFGEN_SELFTEST_LIVE=1` and compare against the manual row.
That validates the qwen2vl path before more Phase 0+ batches accumulate.

Default backend remains `openai` until Don signs off on flipping it
to `qwen2vl`.

---

## Phase 3 prep — dataset + training plan + launcher

Three landed (`dcf528f` → `c2f115d` → `401b4fa`):

- **`tools/persona-lora-train/dataset_builder.py`** — pulls curated
  images from Step 1 batches into a flat `<n>.png + <n>.txt`
  directory with `metadata.json` provenance. Filters by curation
  verdict + selftest score. Includes the 4 v0 anchor images by default
  with framing-specific captions.
- **`tools/persona-lora-train/training_config.py`** — wraps
  dataset_builder + emits `accelerate launch
  train_dreambooth_lora_flux.py ...` as both argv list and shell
  string. GPU-free planning step.
- **`tools/persona-lora-train/launch.py`** — operator CLI. Default is
  plan-only (prints command); `--execute` actually fires accelerate
  if the diffusers script is resolvable on disk. 20 unit tests
  covering dataset filter matrix + plan shape + launcher CLI paths.

**Not yet exercised live.** Phase 3 needs:
- Diffusers' `train_dreambooth_lora_flux.py` cloned to a known path
  (launcher walks a small search list; documented in README).
- A curated dataset (currently 4 anchors + 0 candidates because
  Don hasn't curated Phase 0 yet).

---

## Open questions for Don

1. **Phase 1 PuLID vs skip-to-Phase 3 LoRA.** EVALUATION.md
   recommends skip; final call is yours.
2. **Default selftest backend swap.** Phase 2 path is wired but
   default still `openai`. Flip when ready.
3. **Phase 0 sequel batch.** Should I run a 4×2×2 = 16-image batch
   with all framings × 2 lightings × 2 seeds tonight while you're
   AAFK? Gives you something to curate when you wake. Or wait?
   *Decision needed before I burn another 30-50 min of GPU time.*

---

## What I'm doing next (autonomous run continues)

The decision above (#3) is on me until you decide otherwise — the
explicit instruction was "you are the decider." I'm going to:

1. Run a 16-image Phase 0 sequel batch tonight (~30-50 min wall
   clock, sequential offload).
2. While it runs, build Phase 1 PuLID research + scaffold code.
   That gives you both options materialised so you can pick at
   review time.
3. Run qwen2vl evaluation on the resulting 16 candidates.
4. Update this HANDOFF with what landed.

If you wake to a smaller scope than expected, that means I hit a
blocker and chose to stop rather than thrash. Check
`scripts/current_status.py` and recent commits for the truth.
