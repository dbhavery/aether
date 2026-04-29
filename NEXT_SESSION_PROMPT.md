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

### (1) RECOMMENDED — V7 dual experiment (~4h)

Two parallel sub-tracks per PERSONA_ROADMAP.md §"V7 — Likeliest next step":

**(1a) Build a multi-turn discriminator** (~1h). The current
multi-discriminator was trained on single-turn outputs. Self-test
multi-turn scoring against it is weakly calibrated. Train a new
DistilBERT on (5-turn-window, AI-or-human) pairs.

  - Negatives: 5-turn windows from gemma4 / qwen3:8b / raw Qwen base /
    V4 / V5 / V6 self-chats. Re-use the prior generation pipeline
    structure from `gen_transformers_negatives.py` and
    `gen_ollama_negatives.py`. ~500 windows per source = 3000 total
    AI windows.
  - Positives: 5-turn windows sliced from
    `data/normalized_eval_v3.jsonl` real human conversations. ~3000.
  - Train 2 epochs DistilBERT. Save to
    `checkpoints_v7/multi_turn_discriminator/final/`.

**(1b) V7 LoRA continuation from V6** (~3h). Same recipe as V6
(multi-turn-format SFT, lr 1e-4, max_length 1024) but starting from
V6's adapter and 2200 more steps. Tests whether multi-turn-format
training has more room or has saturated.

  - Save to `checkpoints_v7/qwen25_3b_human_lora_v7/final/`.

**Eval both:** score V6 and V7 against both old (single-turn) and
new (multi-turn) discriminators. Report a 2x2 matrix in
`V7_RESULTS.md`. Includes readable sample conversations in the
report — DO NOT report numbers without conversations.

**Update PERSONA_ROADMAP.md cursor** to V7. Add a change-log entry.
Push.

### (2) HEAVIER — V8 capacity test (~3.5h)

Higher-rank LoRA (rank 32) trained from base on V6's multi-turn-format
data. Tests if rank-16 was the bottleneck. See PERSONA_ROADMAP.md
§"V8 — Capacity test." Do this only if Don explicitly asks for V8
and not V7, since V7 is cheaper and a better test of the recipe.

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
