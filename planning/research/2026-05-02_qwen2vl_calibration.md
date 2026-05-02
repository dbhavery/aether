# Qwen2-VL-2B-Instruct Calibration — UNSUITABLE for Doctrine §8 selftest

> **Verdict: do not use Qwen2-VL-2B-Instruct as the Phase 2 backend.**
> Use Qwen2-VL-7B-Instruct (or larger) when you flip the dispatcher
> default from `openai` to `qwen2vl`. Until 7B is validated against
> real candidates, keep `openai` as the default selftest backend.

## Test setup

- **Backend:** `selftest_qwen2vl.score` (`tools/persona-reference-gen/selftest_qwen2vl.py`)
- **Model:** `Qwen/Qwen2-VL-2B-Instruct`, fp16 (no quantization), CUDA
- **Image processor input:** 768×1152 (downscaled from 1024×1536 per
  `_open_and_resize` to fit vision-token budget — necessary fix in
  this commit)
- **Inputs:** 4 framing-probe candidates from
  `personas/aurora/_pipeline/step1_references/2026-05-02-framing-probe/`
  + Aurora anchor (`personas/aurora/avatar/anchor.png`)
- **Comparison:** ground truth from claude-opus-4-7 multimodal vision
  (manual; see `selftest.jsonl` rows in the same batch dir)

## Round 1 — original system prompt

| Image | claude-opus verdict | Qwen2-VL-2B verdict |
|---|---|---|
| #1 (full-body neutral) | flag (framing fail) | **pass** (8/yes/yes) |
| #2 (full-body 3/4 relaxed) | flag (framing fail) | **pass** (8/yes/yes) |
| #3 (wide full-body envir.) | flag (framing fail) | **pass** (8/yes/yes) |
| #4 (3/4 body knees up) | pass | pass (8/yes/yes) |

**Disagreement: 3/4 candidates.** 2B uniformly returned `framing=yes`
on candidates that visibly cropped at the waist.

## Round 2 — strict system prompt

Tightened `_SYSTEM_PROMPT` and `_USER_PROMPT_TEMPLATE` to explicitly
say "if feet are not visible in a 'head to feet' prompt,
framing_match=no" and to instruct the model to "mention specifically
whether feet are visible if the prompt requested full-body framing."

| Image | claude-opus verdict | Qwen2-VL-2B (Round 2) |
|---|---|---|
| #1 (full-body neutral) | flag | **pass** (8/yes/yes) |
| #2 (full-body 3/4 relaxed) | flag | **pass** (8/yes/yes) |
| #3 (wide full-body envir.) | flag | **pass** (9/yes/yes) |
| #4 (3/4 body knees up) | pass | pass (8/yes/yes) |

**Same disagreement.** Critically, the Round-2 notes for image #1
include the literal string:

> *"The candidate's feet are not visible, which is consistent with
> the prompt's request for full-body framing."*

The model **observed** that feet aren't visible AND **labeled** that
observation as "consistent with full-body framing." Pure backward
inference. The visual capability is present (it sees feet aren't
visible) but the categorical reasoning step inverts.

## Failure analysis

This isn't a prompt-engineering problem we can patch around. The
model's failure mode is reasoning, not perception. Possible causes:

1. **Insufficient categorical-reasoning capacity at 2B.** The 7B
   variant has 3.5x parameter count and significantly stronger
   instruction-following at multi-step reasoning tasks per the
   official Qwen2-VL paper (sec 4.3). 2B is positioned as a
   "high-throughput" tier, not a "high-precision" one.

2. **Persona-yaml description anchoring.** The Aurora persona's
   `prompt_text` includes "auburn shoulder-length wavy hair, hazel
   eyes" as part of the framing prompt. The 2B model latched onto
   matching identity attributes rather than evaluating composition.
   A purely composition-focused prompt might do better, but the
   Doctrine §8 spec asks all three axes in one call — splitting
   them adds 3x latency.

3. **Default sampling.** Generation flags `temperature/top_p/top_k`
   were ignored (transformers warning). Greedy decoding may be
   collapsing to template-matched pleasantries.

## Recommendations

1. **Do not flip the `_DEFAULT_BACKEND` from "openai" to "qwen2vl"
   yet.** The current dispatch behavior is correct: default openai,
   qwen2vl opt-in via env var or arg.

2. **Validate 7B before any flip.** When VRAM permits (or run
   overnight when other GPU consumers are idle), download
   `Qwen/Qwen2-VL-7B-Instruct` (~16 GB) and re-run the
   framing-probe evaluation. If 7B catches at least 2/3 of the
   framing fails the manual eval caught, it's a viable replacement.

3. **Keep `_open_and_resize` in selftest_qwen2vl.py.** The 1024×1536
   inputs blow vision-token budgets even when not used; the resize
   is required for the backend to be usable at all.

4. **Document this finding.** This file + the calibration row in
   `selftest.jsonl` make the failure permanent in the repo so a
   future session doesn't repeat the experiment.

## What this means for the bare-metal pivot

- Phase 2 (local selftest) is **not yet shippable**. The qwen2vl
  backend works mechanically, returns scoreable JSON, but its
  scores are unreliable at the 2B tier we tested.
- For the immediate Phase 0 → Phase 3 path, the manual / claude-opus
  selftest is the practical fallback. Don's curation step (also
  Doctrine §8 / human-in-loop) is the real gate; the automated
  selftest is "screen out obvious garbage so Don's time isn't
  wasted on it" — and 2B can't even do that reliably.
- A re-test with 7B is the next experiment, not now (16 GB download
  + ~10 min eval) but documented for next session.
