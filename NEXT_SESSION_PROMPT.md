# Paste-Ready Prompt for the Next Aether Session

> Don: copy everything between the `=== PROMPT START ===` and `=== PROMPT END ===` markers and paste it as the first user message in a fresh Claude Code session opened in `C:/Users/dbhav/Projects/aether/`.

---

## === PROMPT START ===

You are Claude Code, opening Aether for the next session after the 2026-04-28 autonomous V*-arc run that landed V4 → V5 → V6 conversation LoRA models.

Repo root: `C:/Users/dbhav/Projects/aether/`
Branch: `dev`
Expected tip: `169a442` or later — pull first to confirm.

================================================================
§MANDATORY FIRST READS — do these in order, no shortcuts
================================================================

1. **file:///C:/Users/dbhav/Projects/aether/PERSONA_ROADMAP.md**
   The living persona-trajectory document. Six phases (Backend ✓ /
   Text V6 / Voice scaffolded / Avatar scaffolded / Video research /
   Aurora-as-whole). Phase 2 sub-plan walks V7→V8→V9 with the
   structural decision point at V9 (RLHF path A, 7B base swap
   path B, ship V6 path C). Tells you the cursor: V6 of estimated
   8-12, ~70% through Phase 2. THIS IS YOUR PRIMARY ORIENTATION.
   You will UPDATE THIS FILE during your session.

2. **file:///C:/Users/dbhav/Projects/aether/V6_CONVERSATIONS.md**
   Six V6 self-chats (8 turns each, V6 plays both speakers), then
   six V3/V4/V6 side-by-side comparisons. Read enough of these to
   develop a *qualitative* sense of what V6 sounds like before you
   start producing more numbers. The bar is "does this sound like
   a person?" — and it's not always yes. The format here (real
   readable conversations, not data dumps) is the template for
   reporting any future training results.

3. **file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-28_AUTONOMOUS_SESSION_END.md**
   The ultra-detailed comprehensive handoff. Eight sections:
   project vision, current state, consolidated TODOs (11
   categories with [OPEN] / [CLOSED] / [DEFERRED] markers),
   what's next, recurring lessons, file index, wallclock,
   standing instructions. If anything in this prompt conflicts
   with that doc, the doc wins.

4. **file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/STATE_2026-04-28.md**
   Term 2's verified rolling state. Single source of truth for
   "what's open right now" — supersedes earlier audits.

5. **file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V6_RESULTS.md**
   The V*-arc terminal-state report with V7 candidates A-E in §5
   and recommendation in §6.

================================================================
§REPO CHECK — verify before doing anything
================================================================

Run these and read the results carefully:

```bash
cd C:/Users/dbhav/Projects/aether/
git log --oneline -10                      # confirm 169a442 in history
git status                                 # confirm clean
ls planning/session_2026-04-26/training/checkpoints_v6/qwen25_3b_human_lora_v6/final/   # V6 adapter
ls planning/session_2026-04-26/training/checkpoints_v4/discriminator_multi/final/        # multi-discriminator
nvidia-smi --query-gpu=memory.used,memory.free --format=csv      # GPU
```

State out loud: "Here's what I understand the state to be: V6 is the
current best at 28% WildChat / 33% multi-turn. Phase 2 cursor at V6
of 8-12. Working tree clean at tip <SHA>. GPU: <state>."

Wait for Don to confirm or correct before acting.

================================================================
§ABSOLUTE RULES (the lessons from the prior arc)
================================================================

1. **Repo beats prompt when status disagrees.** Three times in the
   prior arc, an authoritative-looking handoff was wrong because
   later commits had landed. Refuse to redo completed work. When
   the handoff says "X is pending" and the code shows X is done,
   trust the code. Verify with `git log`, not memory.

2. **Don't relitigate closed decisions.**
   - Q1=option B (match human distribution)
   - Q2=single-blended-register through V8 minimum
   - Q3=LoRA continuation
   - Phase 1 backend = closed
   - M2 Run 2 = closed (`9fad125` and successors)
   - All vision-track CONTINUE_COMPANION commits = on dev, shipped
   - Real-corpus retrieval calibration = landed
   - Aurora-strict canary suite = landed (`100a36f`)

3. **Atomic commits, named paths, never `git add .`.** The prior
   parallel-agent runs had 5 working-tree contamination incidents.
   Single-agent work bypasses this; if you ever spawn parallel
   agents, use worktrees.

4. **PYTHONUTF8=1 on every Python call.** Windows cp1252 surfaces
   in trl/transformers reading non-ASCII files.

5. **`think:false` on every Ollama call to gemma4 / qwen3.** Without
   it, those reasoning models spend `num_predict` on internal
   thinking and return empty content.

6. **Kill stray Ollama before GPU-heavy training.** 24GB VRAM is
   tight; ollama running ~5GB will degrade step time 2-3x.

7. **Don't push trainer/ checkpoint state.** The optimizer.pt files
   are 500MB+, blow GitHub's 100MB limit. Only `final/` and
   `training_meta.json` should be tracked. Existing `.gitignore`
   already covers this; don't disable it.

================================================================
§WHAT TO DO THIS SESSION — three options, ranked
================================================================

Default to (1) unless Don directs otherwise.

### (1) RECOMMENDED — V7 + V8 pipelined experiment (~5h, was ~9h serial)

**This is a pipelined plan.** GPU stays saturated 100% of the
time. CPU does data prep, scoring, and report writes during GPU
work. See §BARE-METAL PARALLELIZATION below for VRAM techniques.

Two GPU pipelines + three CPU pipelines, overlapped:

```
HOUR 0────1────2────3────4────5
GPU [discrim train ~1h][V7 LoRA train ~3h───────][V7 gen + V8 train start ~1h]
CPU [V8 data prep ~30m][rescore V*-arc on new discrim ~30m][V7 report ~30m]
```

**(1a) Multi-turn discriminator** (GPU hour 0-1, ~1h). Negatives:
5-turn windows from gemma4 / qwen3:8b / raw Qwen base / V4 / V5 /
V6 self-chats. ~500 windows per source = 3000 total AI windows.
Positives: 5-turn windows from `data/normalized_eval_v3.jsonl`
~3000. 2 epochs DistilBERT. Save to
`checkpoints_v7/multi_turn_discriminator/final/`.

**(1b) V8 data prep** (CPU, hour 0-0.5, runs concurrently with 1a).
Build `data/sft_train_v8.jsonl` for rank-32 LoRA from base. Same
multi-turn-window format as v6 but optionally larger windows
(8-12 turns). This is pure JSON munging — no GPU.

**(1c) V7 LoRA training** (GPU hour 1-4, ~3h). LoRA continuation
from V6 adapter. Same multi-turn-format SFT, lr 1e-4. Use
`optim="adamw_8bit"` (saves 4-6 GB optimizer VRAM) and
`offload_optimizer=True` (saves 8-10 GB more, costs ~10% step
time). With ~14 GB free during training, you have headroom for
generation overlap in (1e). Save to
`checkpoints_v7/qwen25_3b_human_lora_v7/final/`.

**(1d) Re-score V*-arc on multi-turn discriminator** (CPU, hour
1-2, runs concurrently with 1c). DistilBERT inference on CPU is
~17 docs/sec — fast enough. Score V4, V5, V6 self-test
transcripts against the new multi-turn discriminator. Establishes
apples-to-apples baseline. No GPU contention.

**(1e) V7 generation + V8 training overlap** (GPU hour 4-5,
~1h). V7 generation needs ~6 GB (model + KV cache, no
optimizer). V8 LoRA training with 8-bit optimizer + offload
needs ~14 GB. Total 20 GB fits 24 GB headroom. Run them in
two Python processes against the same GPU; they share via
CUDA's process scheduler. Save V8 to
`checkpoints_v8/qwen25_3b_human_lora_v8/final/`.

**(1f) V7 report scaffold** (CPU, hour 4-5, runs concurrently
with 1e). Write `V7_RESULTS.md` skeleton with format from
`V6_CONVERSATIONS.md` and `V6_RESULTS.md`. Fill in numbers + sample
conversations after generation finishes.

**(1g) Final scoring** (CPU + GPU, hour 5-5.5). Score V7 outputs
against both discriminators. Pull representative conversation
samples for the report. Final commit + push.

**Hard-fail conditions and recovery:**
- If V8 training OOMs at hour 4 (because V7 gen + V8 train overlap
  fails): kill V8, finish V7 gen, then start V8 sequentially.
  Adds ~3h to next session, doesn't lose V7 results.
- If multi-turn discriminator accuracy is <70%: the discriminator
  is too noisy to trust; report V7 against single-turn
  discriminator only and flag.
- If V7 plateaus (≤+2pp over V6 on multi-turn discriminator):
  document the saturation and DEFER V8 to next session — V8
  needs a new hypothesis if V7 saturated.

### (2) HEAVIER — V8 alone capacity test (~3.5h)

Higher-rank LoRA (rank 32) trained from base on V6's multi-turn-format
data. Tests if rank-16 was the bottleneck. See PERSONA_ROADMAP.md
§"V8 — Capacity test." Do this if (1) is too aggressive and Don
wants only one new model this session.

### (3) PRODUCT-IMPACT — Ship V6 to Aurora (~6-10h, multi-session)

Replace prompted gemma4:e4b with V6 LoRA-on-Qwen2.5-3B in Aurora's
backbone. Touches `packages/l4-router/`, `packages/l6-persona/`, and
the model router. Likely needs a new ADR-0012 to formalize. Has
behavioral consequences (audit trail format, presence response
register) that need careful integration testing.

This is the highest product-impact move per V6_RESULTS §6 and
PERSONA_ROADMAP.md §3. **Do this only if Don explicitly authorizes
it; not the default autonomous move.**

================================================================
§BARE-METAL PARALLELIZATION — read this before training
================================================================

Don pushed back this session: "We aren't using retail software."
He's right. The prior arc treated GPU + CPU as serial phases and
the GPU sat at 24 GB during training but 6-10 GB during eval —
massive idle headroom. Use it.

**Rules of thumb for this hardware (RTX 3090 Ti 24 GB + 64 GB RAM):**

1. **Discriminator inference → CPU permanently.** DistilBERT is
   ~250 MB; CPU runs ~17 docs/sec. Saves 0.5-1 GB VRAM. NEVER
   load the discriminator on GPU during V* training or eval.

2. **Optimizer 8-bit always.** `optim="adamw_8bit"` from
   bitsandbytes drops optimizer state 4 GB → 0.5 GB. Same
   accuracy. Drop-in replacement for `adamw_torch`.

3. **Optimizer state offload to RAM during training.**
   `offload_optimizer=True` in TrainingArguments (or
   `accelerate` config). Frees 8-10 GB more. Costs 5-15% step
   time. We have 64 GB system RAM. Use it.

4. **`device_map="auto"` + `offload_folder` for big models.**
   If a 7B model swap happens (V9 path B), use accelerate to put
   layer 0-15 on GPU, 16-31 on CPU. Slower but fits.

5. **CPU work runs in parallel with GPU.** Data prep,
   normalization, JSON writes, report scaffolds, sample-pulling.
   Always launch these in a background bash task while the GPU
   pipeline is busy. Coordination rule: don't both touch the
   same file from CPU and GPU procs.

6. **Two-process GPU sharing.** When VRAM allows, a generation
   process + a training process can share one GPU via CUDA's
   stream scheduler. Saves session wallclock by ~25%. Hard fail
   if combined VRAM exceeds 24 GB — set `PYTORCH_CUDA_ALLOC_CONF=
   "max_split_size_mb:512"` to keep allocation predictable.

7. **Pre-load eval datasets into CPU memory at session start.**
   GPU shouldn't wait on disk reads during gen. `load_dataset(...).
   to_list()` and keep in Python.

8. **`torch.cuda.empty_cache()` between phases.** Already
   habitual; keep doing it.

9. **Stray Ollama is a 5 GB tax** — kill before any GPU-heavy
   training. Set `OLLAMA_KEEP_ALIVE=0` for short-running gens to
   stop it auto-respawning mid-session.

10. **`PYTHONUTF8=1` always.** cp1252 surfaces in trl/transformers
    on Windows reading non-ASCII corpora.

**Concrete VRAM accounting for V7 training with these techniques:**

| Component | VRAM | Notes |
|---|---:|---|
| Qwen2.5-3B base in 4-bit | 2.0 GB | bnb nf4 |
| LoRA adapter rank 16 (active params) | 0.5 GB | fp16 |
| Activations + gradients (max_length 1024, batch 4) | 4.5 GB | with grad checkpointing |
| KV cache during gen | 2.5 GB | only during eval |
| Optimizer state (adamw_8bit + offload) | 0.5 GB | most goes to CPU RAM |
| **Total during V7 training** | **~7.5 GB** | down from ~22 GB w/o offload |
| **Headroom for V8 train overlap** | **~16 GB** | enough for second model + activations |

This is why pipelining V7 + V8 fits.

================================================================
§DON 2-MIN ITEMS — surface these to Don early
================================================================

If Don is around for any part of this session, prompt him to do
these. They unblock visible work:

1. **`setx OLLAMA_FLASH_ATTENTION false`** (Windows env, then
   reopen terminal). Workaround for content-deterministic NaN bug
   in Ollama. Confirmed 65/65 on previously-failing rows. Currently
   not set system-wide.

2. **Drop a `fridge_open.jpg` in `tools/evals/fixtures/`.** Any
   representative still — fridge interior, open door, food visible.
   Unblocks `vision_response_quality` quality-eval scenario.

3. **Pick: 10th paraphrase variant for `memory_appropriateness`.**
   Aurora produced "Got it. Let's leave that out of it." outside
   the 9 documented variants. Add the 10th to expectations or leave
   as canary. Recommendation in HANDOFF §3.1: leave as canary.

After all three: re-run `python tools/evals __main__.py --backend
ollama` and expect 5 or 6 of 6 PASS (was 3/6 with these three
blocking 2 scenarios).

================================================================
§STRUCTURAL DECISIONS DON OWES (V9 path)
================================================================

These don't have to be answered today, but they gate Phase 2
forward past V8. Surface them to Don at end of session.

- **D3 (V9 path):** RLHF with Don as rater (path A — only path to
  truly indistinguishable, costs 20-40h of Don's time across
  weeks), or 7B base swap (path B — +5-15pp ceiling raise, modest
  hedge), or accept V6/V7/V8 as Aurora's voice (path C —
  pragmatic). See PERSONA_ROADMAP.md §"V9 — structural decision
  point."

- **D1 (Aurora's face):** what does she look like? Gates Phase 4
  avatar work.

- **D2 (Aurora's voice):** clone from whose audio? Gates Phase 3
  voice integration.

- **D4 (real-time video):** pursue now or wait for tech? Gates
  Phase 5.

- **D5 (Milestone 3 theme):** four candidates in HANDOFF §3.4.
  Don picks.

================================================================
§HOW TO CLOSE OUT THE SESSION
================================================================

When you're done with the work for the session:

1. Commit each unit of work atomically with named paths. Co-author
   line: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
2. `git pull --rebase origin dev` before push (in case Don or
   another session pushed).
3. Push.
4. Update PERSONA_ROADMAP.md cursor + change-log if you crossed
   any phase boundary or moved the V counter.
5. Update MEMORY.md if any persistent fact changed (e.g., new
   best model). Memory file at:
   `C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/`
6. Write a session-end report. Format like `V6_RESULTS.md` —
   numbers + readable sample conversations + V*+1 candidates +
   recommendation. Commit + push.
7. State out loud: "Session complete. Cursor moved from <X> to
   <Y>. Here's what shipped: [list]. Here's what's next: [list].
   Don: please answer <decision> when you can."

================================================================
§DO NOT
================================================================

- Do NOT redo M2 Run 2 wiring (closed in `9fad125`).
- Do NOT redo the vision-track work (all 7 commits on dev).
- Do NOT redo real-corpus retrieval calibration (landed; ADR-0011
  unblocked memo at file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/ADR_0011_UNBLOCK_MEMO.md
  says STILL-DEFER).
- Do NOT trust morning handoffs that contradict `git log`.
- Do NOT touch private Isabelle-tagged content if any surfaces.
- Do NOT modify repo `CLAUDE.md` or root `ROADMAP.md` (the
  engineering-substrate one); update `PERSONA_ROADMAP.md` instead.
- Do NOT push trainer/ checkpoint state. `.gitignore` blocks it.
- Do NOT skip git hooks (--no-verify) without explicit Don
  authorization.
- Do NOT generate fake numbers. If a measurement fails, document
  the failure rather than approximate.
- Do NOT report training results without including readable sample
  conversation outputs.

================================================================
§WHEN IN DOUBT
================================================================

Stop and ask Don. A 30-second question prevents a 3-hour
debugging session. The cost of pausing to confirm is low; the
cost of an unwanted action (lost work, wrong direction) can be
high.

The hardest part of "build an AI assistant indistinguishable from
a human friend" is deciding what to measure and trusting the
measurement. Everything else is execution.

## === PROMPT END ===

---

## How Don should use this

1. Open a fresh Claude Code session in `C:/Users/dbhav/Projects/aether/`.
2. Paste everything from `=== PROMPT START ===` through `=== PROMPT END ===` as the first message.
3. Watch for the agent's "Here's what I understand the state to be" line. If it's wrong, correct it before letting it act.
4. If you have time + want to be in the loop early, do the three Don 2-min items and answer one of the structural decisions (D3 V9 path is the most leveraged).
5. If you want autonomous mode, say "go autonomous, V7 dual experiment, surface decisions at end" and the agent should execute Option (1) in §What to do.
