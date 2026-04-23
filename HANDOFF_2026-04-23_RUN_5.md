# Handoff — 2026-04-23 Run 5 (Polish & IDs — Option A)

**Written:** 2026-04-23 session end.
**Branch:** `dev`. Tip `ca8219b` at session start → (this commit)
at session end. Push planned at end of session (roadmap-complete
is a natural publish moment per Decision #67).
**Working tree:** clean after this handoff commit.

Run 5 of the six-run roadmap 2026-04-23. Closed the roadmap
with Option A — **MemoryDrawer ↔ MemoryTab consolidation**.

## Roadmap status — COMPLETE

| Run | State |
| --- | --- |
| 0 | ✅ Truth & Push |
| 1 | ✅ QE Current |
| 2 | ✅ Memory Sweep |
| 3 | ✅ Memory Retrieval (embeddings) |
| 4 | ✅ Memory Lock |
| 5 | ✅ Polish & IDs (Option A — MemoryDrawer retired) |

The six-run roadmap 2026-04-23 is now done. The next session
should draft Milestone 2's roadmap before implementing anything
else. See §7 below.

## 1. Commit table

| SHA | Subject |
| --- | --- |
| (this commit) | feat(ui): consolidate Memory entry point |

One implementation commit plus this handoff + execution report.

## 2. Check matrix (frontend-only scope)

| Check | Result |
| --- | --- |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm test` | **188 / 188** (was 185, +3 TrustDrawer tests) |
| `apps/desktop && pnpm build` | 235 / 68 kB (was 237 / 68 kB) |

Rust / cargo checks not rerun — no Rust code was touched. Five
rot guards inherit their Run 3 + 4 pass state; `tools/lint-memory-doc`
re-verified at session end because the Memory V2 doc is the
closest contract to the change.

## 3. Post-session subsystem status

All five subsystems remain CLOSED and rot-guarded. No state
change from Run 3 + 4 handoff except:

- **Trust drawer** now owns a canonical `initialTab` prop. The
  Memory tab is the single Memory UI entry point; the v0
  `MemoryDrawer` component is retired.
- **Frontend bundle**: 63 modules (was 64; `MemoryDrawer.tsx`
  deleted).

## 4. Risks / alerts for next session

### A. Roadmap complete — next session needs a plan

The six-run roadmap 2026-04-23 has zero pending items. Starting
Milestone 2 without an explicit roadmap would reopen the
drift problem ADRs + rot guards were built to prevent. The next
session should be a **planning session**, not an implementation
session. See §7.

### B. Backlog items ripened during Milestone 1

- **5.5a Domain-typed durable store.** Unblocks per-domain
  retention (Memory V2 step 5 currently only prunes Session),
  enables embedding lifecycle paired with non-Session rows.
- **5.5b Per-item sweep telemetry opt-in.** Explicit reopen of
  Decision #56 if the Memory tab's History view surfaces a
  genuine need.
- **Retrieval wiring.** Turn engine consumes
  `EmbeddingStore::query_nearest` for Durable/Projects/Artifacts
  recall. Separate slice; the single biggest user-visible payoff
  of Memory V2 step 6.
- **Spec gaps #3–#6.** Requirement IDs (Option C, not picked
  this session), OSS/Pro/Cross-system views, light RTM,
  `docs/AC-STYLE.md`.
- **`pnpm eval` + CI kickoff** (Option B, not picked). Better
  bundled with GitHub Actions setup in Milestone 2.

None of these are blocking today. All are candidates for
Milestone 2 ordering.

### C. (CARRIED) Ollama embedding provider unverified on real workloads.

Unchanged from Run 3 + 4 handoff Risk B. First `ollama pull
nomic-embed-text` + toggle-on session validates the ADR-0002
default.

### D. (CARRIED) Flat-file embedding store rewrites on every
mutation.

Unchanged from Run 3 + 4 handoff Risk D. Not a blocker at
personal scale; trait is swappable.

### E. (CARRIED) Shell compiles embeddings even when disabled.

Unchanged from Run 3 + 4 handoff Risk E. Flag in privacy /
compliance docs if the question comes up.

## 5. Decisions log additions (#68 onward)

- **68. Trust drawer is the single canonical Memory UI entry
  point.** The v0 `MemoryDrawer` component is retired.
  `TrustDrawer` accepts an optional `initialTab` prop; the
  header's Memory button opens it with `initialTab="memory"`.
  Rationale: Memory V2 step 4 shipped a richer surface
  (per-domain lanes, forget, edit, approval modals) that
  subsumed the v0 drawer's capabilities, and two Memory
  surfaces made the "what does Aether remember about me?"
  question ambiguous.
- **69. `initialTab` re-applies on every open-false → open-true
  transition**, not just on mount. Rationale: drawer instances
  outlive individual open/close cycles; mount-only would surface
  the user's last-viewed tab instead of the button's intent.
  Unit-tested in `TrustDrawer.test.tsx`.
- **70. Keep the two drawer state values (`"memory"` and
  `"trust"`) in `App.tsx`** rather than collapsing to a single
  `"trust"` state with a separate `trustInitialTab` field.
  Rationale: header button semantics stay explicit
  (`onOpenMemory` vs. `onOpenTrust`); state machine reads the
  same way; future per-entry drawer behaviour becomes trivial.

Carried: 1–67 from prior handoffs (ADR-0001, ADR-0002, all
subsystem closure decisions).

## 6. Anti-drift corrections

- Option C (requirement IDs) was skipped per the Reserved
  Decisions rule (still Don-authorized only). No auto-lock of
  the `<layer>-<subsystem>-<NNN>` scheme in `docs/GLOSSARY.md`
  §11.
- Option B (`pnpm eval`) was skipped because the repo has no
  root `package.json` and no existing CI wiring. Shipping a
  `pnpm eval` script alone would age badly without GitHub
  Actions + a wider CI plan; bundling it with CI kickoff in
  Milestone 2 is the right move.

## 7. Next recommended prompt — Milestone 2 planning

Paste the fenced block below verbatim into the next session. It
is deliberately a **planning** prompt, not an implementation one.

````md
You are Claude Code, opening Milestone 2 for Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev (push state determined at runtime; if current session
landed commits, verify `git log origin/dev..dev --oneline`).

SESSION TYPE
- PLANNING, not implementation. The six-run roadmap 2026-04-23
  closed on Run 5. The next step is a Milestone 2 retrospective +
  roadmap, not more code.
- Output: three new artifacts — MILESTONE_1_RETROSPECTIVE.md,
  ROADMAP_2026-04-24_MILESTONE_2.md, and a first-slice prompt
  for the new milestone's Run 1. No source-code commits.

================================================================
§MANDATORY FIRST STEPS
================================================================

1. `./scripts/current_status.sh` (Windows fallback:
   `python scripts/current_status.py`). Paste the output. Repo
   beats prompt (Decision #32).
2. `git log --oneline -15`. Confirm ca8219b, the Run 5 commit,
   and this handoff are in history.
3. Read, in order:
   - `HANDOFF_2026-04-23_RUN_5.md` (this handoff — roadmap is
     complete).
   - `HANDOFF_2026-04-23_RUN_3_PLUS_4.md` §4 (risks) and §5
     (decisions #62-#67).
   - `HANDOFF_2026-04-23_RUN_1_PLUS_2.md` §4-5 (prior decisions).
   - `ROADMAP_2026-04-23_SIX_RUN_PLAN.md` (the milestone we just
     closed).

================================================================
§PHASE 1 — Milestone 1 retrospective
================================================================

Write `MILESTONE_1_RETROSPECTIVE_2026-04-23.md` (brief, ~60
lines). Cover:

- **Scope recap.** Six runs, 5 subsystems rot-guarded, 2 ADRs,
  +12-18 tests.
- **Patterns that worked.**
  - ADR-before-code (ADR-0001 unblocked Run 2, ADR-0002 unblocked
    Run 3).
  - Rot-guard-in-the-same-commit (Run 1 and Run 4 shipped the
    guard alongside the doc flip).
  - Bundle-when-natural (Runs 1+2 and 3+4 both landed as
    multi-phase sessions; Run 5 deliberately stood alone).
- **Patterns to fix.**
  - `current_status.sh` reads a frozen-in-time handoff; the
    2026-05-18 handoff was still the source well after its
    status block became stale. The script should read the
    *latest* `HANDOFF_*.md` by date, or the risks section should
    move out of handoffs entirely.
  - Line-ending warnings (LF ↔ CRLF) are noise in every commit.
    One-time `.gitattributes` fix would silence them.
- **Invariants worth promoting to doctrine.**
  - Every subsystem gets a rot guard before it claims "Current".
    Five examples now suggest this is a rule, not a coincidence.
  - ADRs precede cross-layer refactors. Two examples (0001,
    0002) suggest this should be policy.

================================================================
§PHASE 2 — Milestone 2 roadmap
================================================================

Write `ROADMAP_2026-04-24_MILESTONE_2.md`. Propose theme:
**"Aether becomes retrieval-aware and user-facing."** Sequence
candidate runs along the lines of:

1. Retrieval wiring (turn engine consumes
   `EmbeddingStore::query_nearest` for Durable/Projects/Artifacts
   recall).
2. Domain-typed durable store (backlog 5.5a).
3. Settings polish: embeddings onboarding + Ollama
   availability check.
4. Spec gaps #3-#6 bundled (requirement IDs, OSS/Pro/Cross-system
   views, light RTM, AC-STYLE.md).
5. `pnpm eval` + GitHub Actions CI kickoff.
6. Memory tab polish (turn-level "recalled X" chips now that
   retrieval is live).

Include:
- Per-run precondition gates (2 needs 1? 3 before 5?).
- Per-run "done when" criteria.
- Explicit reserved decisions (don't pre-commit anything that
  needs an ADR).
- A pragmatic variant if Don prefers shipping visible polish
  before infrastructure.

================================================================
§PHASE 3 — Milestone 2 Run 1 starter prompt
================================================================

Write `NEXT_SESSION_PROMPT_M2_RUN_1.md` for whatever Run 1 turns
out to be (likely retrieval wiring). Mirror the Run-3 prompt
shape: mandatory first steps, status correction, reserved
decisions, delegated decisions, phase scope, out-of-scope,
commit cadence, done-when, check matrix, session-end discipline.

================================================================
§HARD CONSTRAINTS
================================================================

- No source-code commits this session. Three markdown artifacts
  only.
- Do not reopen any of the 70 numbered decisions unless a
  Milestone 2 run explicitly supersedes one (and in that case,
  document it in the roadmap, don't silently decide).
- Doctrine rules unchanged.

================================================================
§SESSION-END DISCIPLINE
================================================================

1. Three new markdown files committed.
2. Clean working tree.
3. Short handoff `HANDOFF_2026-04-24_MILESTONE_2_PLAN.md`.
4. `git push origin dev` at session end — roadmap-complete +
   milestone-plan-ready is the natural publish moment.

Good luck.
````

---

(end of handoff)
