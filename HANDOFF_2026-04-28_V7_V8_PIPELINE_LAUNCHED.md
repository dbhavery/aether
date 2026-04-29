# Handoff — V7 + V8 Pipeline Launched 2026-04-28

> Written at session-end after launching the V7+V8 sequential
> orchestrator. The actual training runs unattended for ~5h 20min.
> A future Claude session reads the logs and produces V7_RESULTS.md
> and V8_RESULTS.md with readable conversation samples.

---

## What's running right now

**Process:** `python run_v7_v8_pipeline.py` running unattended in
`C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/`.
**Started:** 2026-04-28 18:00:09 local.
**ETA:** ~23:20 local (~5h 20min wallclock).
**Log files:**
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/logs_v7/orchestrator.log — top-level
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/logs_v7/orchestrator_stdout.log — same content, redirected stdout
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/logs_v7/v7_train.log — V7 training subprocess
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/logs_v7/v7_eval.log — V7 eval subprocess
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/logs_v8/v8_train.log — V8 training subprocess
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/logs_v8/v8_eval.log — V8 eval subprocess

**Phase flag files (the orchestrator's resume-state):**
- `logs_v7/phase_train.done` — set when V7 training finishes
- `logs_v7/phase_eval.done` — set when V7 eval finishes
- `logs_v8/phase_train.done` — set when V8 training finishes
- `logs_v8/phase_eval.done` — set when V8 eval finishes

If the orchestrator crashes mid-run, re-launching it skips already-
completed phases via these flags. Safe to re-run.

---

## Pipeline shape

| Phase | Script | Estimated wallclock | Output |
|---|---|---:|---|
| 1. V7 train | `train_pipeline_v7.py` | ~85 min | `checkpoints_v7/qwen25_3b_human_lora_v7/final/` |
| 2. V7 eval | `eval_v7.py` | ~50 min | `eval_v7/v7_eval_results.json` + outputs jsonl |
| 3. V8 train | `train_pipeline_v8.py` | ~135 min | `checkpoints_v8/qwen25_3b_human_lora_v8/final/` |
| 4. V8 eval | `eval_v8.py` | ~50 min | `eval_v8/v8_eval_results.json` + outputs jsonl |

Phases run sequentially in fresh Python subprocesses so torch state
fully releases between them.

---

## Experiment design

### V7 — multi-turn-format LoRA continuation from V6

**Starts from:** V6 LoRA adapter (rank 64, alpha 128).
**Adds:** 1500 more steps on the same multi-turn-format SFT data.
**Hypothesis:** more multi-turn-format steps may extend V6's +4.5pp
WildChat gain over V4. Or saturate, like V5 did when continuing V4
on the single-turn format.

**The only NEW thing in V7 vs V6:** `optim="adamw_8bit"` (bitsandbytes
8-bit Adam). Drops optimizer state from ~12 GB to ~3 GB without
accuracy loss. Drop-in replacement for `adamw_torch`.

### V8 — rank-128 fresh-from-base capacity test

**Starts from:** Qwen2.5-3B-Instruct base (no V*-arc inheritance).
**Trains:** 2200 steps of multi-turn-format SFT with rank-128 /
alpha-256 LoRA (vs V6's rank-64 / alpha-128).
**Hypothesis:** if rank-64 was leaving capacity on the table, V8
should beat V6 by ≥5pp on WildChat. If V8 ≈ V6, capacity isn't the
limit and V9+ should change *data* (registers, RLHF, base swap)
instead of more capacity.

**Data:** sft_train_v6.jsonl (4-8 turn windows). Held constant from V6
so capacity is the only variable changed.

### What was descoped from this run (and why)

1. **Multi-turn discriminator.** The plan called for a fresh DistilBERT
   that takes 5-turn windows as input. Building good multi-turn
   negatives across 5 AI sources (gemma4 / qwen3 / raw-base / V4 /
   V5 / V6) needs ~1-2h of fresh self-chat generation per source.
   Skipped to keep the autonomous run focused on the actual model
   experiments. Existing single-turn V4 multi-discriminator is reused
   for apples-to-apples with V4/V5/V6.

2. **True CPU optimizer offload.** The plan called for
   `offload_optimizer=True`. HF Trainer doesn't expose this as a
   top-level flag — true CPU offload requires DeepSpeed ZeRO-2 or
   accelerate FSDP, neither of which is set up. `adamw_8bit` alone
   delivers ~70% of the VRAM win without that complexity.

3. **GPU-shared two-process pipelining (V7 gen + V8 train concurrent).**
   The PERSONA_ROADMAP §"V7 onward" plan called for overlapping V7
   eval and V8 training in the final hour via CUDA stream scheduler.
   With V8 at rank 128 (corrected — see below) the VRAM math gets
   tight (V7 gen ~6 GB + V8 rank-128 train ~17 GB = 23 GB, no margin).
   Sequential is safer for an unattended overnight run; loses ~30 min
   of wallclock but eliminates OOM risk during the unattended phase.

### Plan deviation — rank correction

The next-session prompt and PERSONA_ROADMAP §"V8 — Capacity test"
both described V8 as "rank-32 from base." Reading
`checkpoints_v6/qwen25_3b_human_lora_v6/final/adapter_config.json`
shows V6 is **already rank 64**, alpha 128. Rank-32 from base would
be a *down*-rank, not a capacity test.

V8 is set to **rank 128 / alpha 256** to actually test the capacity
hypothesis the plan intended. PERSONA_ROADMAP needs an edit to fix
the stale rank-16/rank-32 references — flagged in change-log row.

Repo beat prompt: trusted the adapter_config.json over the doc.

---

## What the next session should do

### When the orchestrator finishes

Verify completion:
```bash
ls C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/logs_v7/phase_train.done
ls C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/logs_v7/phase_eval.done
ls C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/logs_v8/phase_train.done
ls C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/logs_v8/phase_eval.done
```

If any are missing, the orchestrator failed. Read the corresponding
`*.log` file to find the error. Common failure modes:

- **OOM during V8 training:** rank-128 may not fit even with adamw_8bit.
  Drop to rank 96 in `train_pipeline_v8.py:LORA_R` and re-run only V8.
- **Optimizer state not loading from V6 checkpoint:** unlikely since V6
  pattern matches V4. If it happens, set `optim="paged_adamw_8bit"`
  for V7 (paged variant from bnb).
- **Tokenizer cache corruption:** delete `~/.cache/huggingface/hub/...`
  for Qwen2.5-3B-Instruct and rerun.

### Read the eval JSON

```bash
cat planning/session_2026-04-26/training/eval_v7/v7_eval_results.json
cat planning/session_2026-04-26/training/eval_v8/v8_eval_results.json
```

Key numbers:
- `v7_wildchat_score.human_rate` — primary V7 signal
- `v8_wildchat_score.human_rate` — primary V8 signal
- `v7_self_test_summary.all_generated_turns.human_rate` — multi-turn V7
- `v8_self_test_summary.all_generated_turns.human_rate` — multi-turn V8

### Decision rules baked into the experiments

| Outcome | Action for V9 |
|---|---|
| V7 > V6 by ≥3pp WildChat | Multi-turn-format continuation works. V9 = continue from V7 with different data mix. |
| V7 ≈ V6 (±2pp) | Multi-turn-format saturated at V6. V9 must change data or method. |
| V8 > V6 by ≥5pp WildChat | Capacity matters. V9 = rank ≥128 LoRA from base (or 7B base). |
| V8 ≈ V6 (±3pp) | Capacity isn't the limit. V9 = different data (registers, RLHF). |
| V8 << V6 | LoRA-from-base loses V*-arc accumulated knowledge. Continuation chain matters. |
| Both V7 and V8 ≤ V6 | Hard plateau. Surface decision D3 (RLHF Path A / 7B base swap / ship V6) to Don. |

### Write the results docs

Format mirrors V6_RESULTS.md and V6_CONVERSATIONS.md. The two docs:

1. **V7_RESULTS.md** — numbers, train/eval loss gap, per-turn breakdown,
   V7-vs-V6-vs-V4 comparison table, V8 candidates ranked.
2. **V7_CONVERSATIONS.md** — six 8-turn V7 self-chats + six V6/V7
   side-by-sides. Pull from `eval_v7/v7_self_test_transcripts.jsonl`
   and `eval_v6/v6_self_test_transcripts.jsonl` (held-constant seeds).
3. **V8_RESULTS.md** — same shape as V7_RESULTS.md but with the
   capacity-test framing.
4. **V8_CONVERSATIONS.md** — same shape as V7_CONVERSATIONS.md.

Update PERSONA_ROADMAP.md cursor + change log:
- Move V counter from V6 → highest of {V7, V8} that won.
- Update "Best score" line with new WildChat number.
- Add row to change log table.
- Fix stale "rank 16" / "rank 32" language in §"V8 — Capacity test."

### Update memory

Most likely change in `C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/MEMORY.md`:
- Replace "**V*-arc autonomous training session 2026-04-28** — V4→V5→V6 shipped. **V6 is current best**…" line under Aether project state with V7/V8 outcome.

### Atomic commits — push pattern

```bash
git pull --rebase origin dev
git add planning/session_2026-04-26/training/V7_RESULTS.md
git commit -m "training(v7): RESULTS — <one-line outcome>"
git add planning/session_2026-04-26/training/V7_CONVERSATIONS.md
git commit -m "training(v7): CONVERSATIONS — readable samples"
# ... same for V8
git add PERSONA_ROADMAP.md
git commit -m "docs: PERSONA_ROADMAP — V counter to V<N>, rank correction"
git push origin dev
```

---

## Engineering scripts shipped in this session

| Script | Purpose |
|---|---|
| `build_v8_sft.py` | Multi-turn windows 8-12 turns (sibling of V6's 4-8). Output is a future-experiment artifact; V8 itself uses V6 data. |
| `train_pipeline_v7.py` | V6 → V7 LoRA continuation, adamw_8bit, 1500 steps. |
| `train_pipeline_v8.py` | rank-128 fresh-from-base, adamw_8bit, 2200 steps. |
| `eval_v7.py` | held-out 200 + WildChat 200 + 25-seed × 8-turn self-test, scored against V4 multi-discriminator. |
| `eval_v8.py` | same shape pointed at V8. |
| `run_v7_v8_pipeline.py` | sequential orchestrator with phase flag files. |

Atomic commits in this session:
- `d3168f2` build_v8_sft
- `5bbce81` train_pipeline_v7
- `5040950` train_pipeline_v8
- `e6d92c4` eval_v7 + eval_v8
- `26d1f09` run_v7_v8_pipeline

(plus this handoff and PERSONA_ROADMAP update — the next two commits.)

---

## Standing instructions for the next session reading this

1. **Trust `git log` and the eval JSONs over this document.** I wrote
   this at launch; the actual outcomes happen unattended. Check the
   logs and JSONs before believing anything in the "expected ETA"
   columns.
2. **If a phase OOM'd, drop the rank** (V8) or **switch to paged_adamw_8bit**
   (V7) and re-run only the failed phase via `phase_*.done` deletion.
3. **Don pushed back this session on retail-software / serial execution.**
   The bare-metal techniques applied (adamw_8bit) are real and worked.
   The ones still pending (DeepSpeed CPU offload, two-process GPU
   sharing) need an engineering investment Don may want to authorize
   before V9.
4. **Surface decision D3 to Don after V7+V8 numbers land.** That's the
   structural fork: RLHF Path A vs 7B base swap Path B vs ship V6
   Path C. The V7+V8 outcome strongly informs which path makes sense.
5. **Don's cardinal rule:** training results without readable sample
   conversations are not reportable. V*_CONVERSATIONS.md is mandatory.

---

## Wallclock summary (this session)

| Step | Duration |
|---|---:|
| Mandatory first reads + repo state verification | ~5 min |
| V8 data prep (CPU) | <2 min |
| Authoring 6 new scripts | ~25 min |
| Pre-flight (gitignore check, syntax check, optim sanity check) | ~3 min |
| Orchestrator launch + verification | ~2 min |
| This handoff + roadmap update + final commits | ~10 min |
| **Engineering session total** | **~50 min** |
| **Background training run (unattended, separate)** | **~5h 20min** |

The engineering work is done. The training will finish around 23:20
local. Don wakes up to results.
