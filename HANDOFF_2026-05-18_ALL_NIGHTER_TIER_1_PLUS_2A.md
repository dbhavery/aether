# Handoff — 2026-05-18 all-nighter (Tier 1A + 1B + 1C + 2A)

**Written:** 2026-05-18, session end.
**Branch:** `dev`, 34 commits ahead of `origin/dev`. **Push NOT authorized.**
**Working tree:** clean.

Session ran per `NEXT_SESSION_PROMPT_2026-05-17.md`. Tier 1 landed in full;
Tier 2A landed; Tier 2B onward left for the next run.

> Next session: start with `./scripts/current_status.sh` instead of
> restating status from memory. The stale-prompt pattern that cost
> hours on three prior sessions is now fixable at the source.

---

## 1. What shipped in this session (nine commits, chronological)

| SHA | Subject |
| --- | --- |
| `fc8ff85` | feat(l2-memory): add remove + update to SessionMemoryStore — Memory V2 step 4 (slice 1) |
| `1bd515d` | feat(apps/desktop): grow memory_service with per-item forget + edit — Memory V2 step 4 (slice 2) |
| `75e07de` | docs: add NEXT_SESSION_PROMPT_2026-05-17.md — all-nighter prompt with inline doctrine grounding (Don-authored) |
| `c7aec41` | feat(apps/desktop): Tauri commands + TS bindings for Memory tab — Memory V2 step 4 (slice 3) |
| `ee9e44b` | feat(apps/desktop): Memory tab in Trust drawer — Memory V2 step 4 (slice 4) |
| `d8f9906` | test: kill env-seam flakes via crate-shared lock + scoped EnvGuard |
| `f357d56` | chore(scripts): add current_status.sh — kills stale-prompt pattern |
| `6e2a4c0` | feat(tools/evals): v1.3 — session-log import for replay |

Four subsystem / workflow moves:

- **Memory V2 step 4 shipped** in four scoped slices. L2 trait grew
  `remove` + `update` (additive, returns `bool` for silent-no-op
  semantics). Shell `memory_service` grew `memory_edit(domain,
  session_id, sequence, new_content)`, `memory_forget_item`, and
  `*_after_approval` mirrors. Six Tauri commands wired through to
  TS (`memory_list`, `memory_forget`, `memory_forget_item`,
  `memory_forget_item_after_approval`, `memory_edit`,
  `memory_edit_after_approval`). New `MemoryTab.tsx` component is
  the third Trust-drawer tab — six per-domain lanes, per-item
  forget / edit actions, lane-level forget-all, inline
  confirmation dialog for Facts / Artifacts (Ask domains). Full
  TS type + Vitest coverage (16 new component tests).
- **Flake cleanup (Tier 1B).** Both known env-seam flakes retired
  by making the test locks actually shared. `l4-router` provider
  tests now use a crate-scoped `providers::env_lock()` instead of
  per-module statics; shell `state::tests` persona tests now use
  module-scoped `STATE_TESTS_ENV_LOCK` + a `PersonasDirGuard` RAII
  helper that also restores the previous env on panic. Full
  `cargo test -p aether-l4-router --features …` now passes under
  default parallelism (no `--test-threads=1` needed).
- **`scripts/current_status.sh` (Tier 1C).** Bash entry point +
  stdlib-only Python fallback. Prints live git state (branch,
  tip, ahead-of-origin, tree dirty/clean) plus the Subsystem
  Status / Check Matrix / Risks sections from the latest
  `HANDOFF_*.md`. Bash delegates parsing to Python so both
  surfaces render identical output. Supports `--list` and a
  date-filter argument.
- **Quality-Eval v1.3 — session-log importer (Tier 2A).** New
  `tools/evals/session_log_import.py` reads a JSONL session log
  matching `TurnMemoryRecord`'s serialisation, pairs
  user → assistant turns, matches against scenarios by
  whitespace-normalised exact OR substring, and emits v1.2-shaped
  capture JSONs with `backend: "session-log"` plus additive
  source-session metadata. 14 stdlib-only `unittest` cases;
  end-to-end smoke proved: import → capture → `--replay-from` →
  expectations evaluated.

---

## 2. End-of-session check matrix (all green)

| Check | Result |
| --- | --- |
| `git status` | clean |
| Commits ahead of `origin/dev` | **34** |
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean (pre-existing L5 warning unchanged) |
| `cargo test --workspace` | 38 test binaries, 0 failures |
| `cargo test -p aether-l3-presence` | 22 / 22 |
| `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` | **96 / 96 under default parallelism** (previously required `--test-threads=1`) |
| `apps/desktop/src-tauri cargo test --all-features` | **198 / 198** (was 186 pre-session) |
| `python tools/evals/__main__.py --dry-run` | 6 / 6 |
| `python tools/evals/__main__.py --dry-run --scenarios-root tools/evals/adversarial` | 6 FAIL (as designed) |
| `python tools/evals/test_capture_replay.py` | 13 / 13 |
| `python tools/evals/test_session_log_import.py` | **14 / 14** (NEW) |
| `python tools/lint-layer-boundaries/check.py` | 0 violations |
| `python tools/lint-vision-doc/check.py` | OK (51 anchors) |
| `python tools/lint-voice-doc/check.py` | OK (48 anchors) |
| `python tools/lint-presence-doc/check.py` | OK (39 anchors) |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm build` | 237 kB / 68 kB gzip (was 227 / 65) |
| `apps/desktop && pnpm test` | **185 / 185** (was 169) |

---

## 3. Subsystem status (post-session)

- **Vision V1** — DONE, rot-guarded. Closed subsystem. Unchanged.
- **Voice V1** — DONE, rot-guarded. Closed subsystem. Unchanged.
- **Presence V1** — DONE, rot-guarded. Closed subsystem. Unchanged.
- **Memory V2**:
  - Steps 1, 2, 3, **4 COMPLETE**.
  - Step 5 (retention sweep) — still pending. Blocked on the
    L2/shell `MemoryDomain` enum reconciliation (Risk A below).
  - Step 6 (embeddings) — pending, downstream of step 5.
  - Step 7 (rot guard `tools/lint-memory-doc/`) — pending,
    downstream of the tab (done) + retention sweep.
- **Quality-Eval V1**:
  - v1 scaffold, v1.1 (adversarial + live Ollama), v1.2 (capture +
    replay), **v1.3 (session-log importer)** COMPLETE.
  - Pending: `tools/lint-quality-doc/` rot guard + doc flip to
    "Current" (Tier 2B). Pending: `pnpm eval` regression harness.
- **Spec package (audit gaps)**:
  - Gap #1 glossary: DONE.
  - Gap #2 NFR skeleton: DONE.
  - Gap #3 forward-looking requirement IDs: pending.
  - Gap #4 OSS/Pro/Cross-system spec views: pending.
  - Gap #5 light RTM view: pending.
  - Gap #6 `docs/AC-STYLE.md`: pending.
- **Test infrastructure**:
  - Two known parallel-test flakes RETIRED. Default `cargo test`
    parallelism is now safe end-to-end.

---

## 4. RISKS / ALERTS — read these before starting the next session

### A. Memory V2 step 5 still blocked on the `MemoryDomain` enum decision

`packages/l2-memory::MemoryDomain` (Personal / Work / Health /
Finance / Creative / System) and
`apps/desktop/src-tauri/src/memory_config::MemoryDomain`
(Session / Durable / Facts / Projects / Preferences / Artifacts)
remain different enums. Step 4 sidestepped the problem by storing
everything in the session store and returning `empty_reason` for
the five non-Session lanes. Step 5 cannot sidestep — the
retention sweep needs to know which domain owns a row.

Three options are documented in
`HANDOFF_2026-05-17_SESSION_END_ULTRA_LONG_SETUP.md` §4 Risk C:

1. Replace L2 kernel enum with the design-doc enum; migrate
   `MemoryItem`.
2. Keep both enums with explicit mapping at the boundary.
3. Retire the L2 kernel stub; shell talks to
   `SessionMemoryStore` + a future domain-typed durable store.

**Recommendation for next session:** decide this BEFORE starting
step 5. Picking the wrong reconciliation path invalidates most of
step 5's work. Don — the prompt explicitly reserves this call for
you.

### B. 34 commits unpushed on `dev`

Push still not authorised. Seven new commits on top of the 27
carried in from the prior session, plus Don's own
`NEXT_SESSION_PROMPT` doc. The pile is getting large enough that
an `origin/dev` move would create real merge friction. Worth
authorising a push at the next natural break.

### C. Gemma 4 still unverified on real workloads

Unchanged from the previous handoff. No `ollama pull gemma4` +
`--backend ollama` run has happened. The fix if Gemma 4 misbehaves
on Don's hardware is two constants + four doc references — narrow.

### D. Memory tab does not (yet) coexist with the old `MemoryDrawer`

The header "Memory" button still opens `MemoryDrawer.tsx`, which
is the v0 read-only session inspector built on `memory_recent`.
The Memory tab inside Trust drawer covers strictly more surface
(six lanes, forget, edit, approval gate). Consolidation to a
single surface is a later polish pass; today both live, and the
UI has two Memory entry points. Worth calling out because a user
might forget one on the other's strengths.

### E. `MemoryDrawer` also never calls `memory_list` — only the tab does

Small consequence of D: the v0 drawer's code path is unchanged
and still uses the v0 `memory_recent` command. Nothing is wrong,
but the drawer is effectively "session lane only, no policy
pills, no actions". If we keep it, consider reusing the
`memory_list("session")` call to share a contract. If we don't
keep it, delete it once step 5 settles.

### F. Two sibling `TurnMemoryRecord` serialisation contracts now exist in the wild

`memory_service.rs` serialises turn content to the SQLite store;
`session_log_import.py` expects the same field layout in a
hand-authored JSONL. Today they agree because both use the Rust
struct's serde output, but there is no compile-time link between
the importer's expectations and the struct. If
`TurnMemoryRecord`'s shape ever changes, the importer's parser
will silently skip rows instead of loudly breaking. A future
slice could tighten this by codegen or by pinning a JSON schema.

### G. Rot guards for Vision / Voice / Presence are in force; Memory + Quality-Eval are not

`docs/MEMORY-V2-ARCHITECTURE.md` is still "design-only" (the doc's
own §11 promises the status flip at step 7). `docs/QUALITY-EVAL-V1-ARCHITECTURE.md`
is also "design-only" pending Tier 2B (next session). Both docs
are now behind the code; every commit is increasing that drift.
Neither is a production risk right now, but both need rot guards
before they become load-bearing for external contributors.

---

## 5. What's on deck for the next session

### Primary target (choose one): Memory V2 step 5 (retention sweep) OR Quality-Eval Tier 2B (rot guard + doc flip)

Don — the enum decision in Risk A is the gate on step 5. If you
make that call, the next session can move immediately into step 5.
If you want to defer the decision one more round, Tier 2B is a
clean, mechanical win that closes an accumulating doc-drift risk
(Risk G).

### Also on deck, in descending leverage order

1. **Push the 34 commits.** The pile is safe but growing; Risk B
   won't resolve on its own.
2. **Tier 2B: `tools/lint-quality-doc/` + QE doc flip.** Mirror
   exactly the pattern of `tools/lint-presence-doc/check.py`
   (shipped in `37f00fa`). Anchor manifest covers the QE doc's
   claimed files / symbols / strings. Reconcile any drift from
   v1.1 + v1.2 + v1.3 additions since the doc was written.
3. **Tier 2C: Autonomy preset picker UI.** Backend ready
   (`AppState::apply_preset`), no UI today.
4. **Tier 2D: Persona picker UI.** Similar shape.
5. **Memory tab / drawer consolidation** (Risk D/E).
6. **Gap #3: forward-looking requirement IDs.** Spec package
   hygiene; keyed to `docs/GLOSSARY.md` §11. Don-reserved.

### Out of scope next session (unchanged)

- Any L5 hash-chain / HMAC / SQLite persistence (Wave 3.5+).
- Cost-cap evaluator Stage 0 (Wave 4).
- Avatar / viseme / L3 social-behavior rendering.
- OSS/Pro assembled spec views (doctrine docs are stale; Don
  refresh pending).

---

## 6. Decisions log (new this session)

Cumulative from the prior handoffs plus today's additions:

- **46. L2 trait extension for Memory V2 step 4 was pre-authorized
  in-session** via `NEXT_SESSION_PROMPT_2026-05-17.md`'s Tier 1A
  with hard scope guardrails (only `remove` + `update`; no new
  domain typing, no storage-shape changes). Agent proceeded per
  that authorisation.
- **47. Silent-no-op semantics on `remove` / `update`.** Both
  return `Ok(false)` when the target row is missing instead of
  erroring. Motivated by the Memory tab forget / edit UX — a
  user-triggered forget against a row retention has already
  claimed should render softly, not surface an error. Persisted
  as the `NotFound` variant on `MemoryForgetOutcome` +
  `MemoryEditOutcome` at the shell layer.
- **48. Memory tab Ask-flow uses a local confirmation dialog,
  NOT the L5 `ApprovalModal`.** The service's per-domain gate
  short-circuits before L5 evaluates, so there is no L5 ticket
  to resolve. The Memory tab surfaces its own approval dialog
  and calls `*_after_approval` on user approval. Documented at
  the call site.
- **49. Session-log importer reads JSONL, not SQLite.** The
  importer stays stdlib-only and dependency-free; a future
  `telemetry_export` Tauri command can emit the JSONL that
  `session_log_import.py` consumes. Decision keeps the importer
  runnable against synthetic test fixtures and hand-authored
  logs without a live Aether process.
- **50. Session-log capture `backend` field is `"session-log"`.**
  Distinct from `"ollama"` so replay consumers can tell these
  captures came from a real conversation vs a live backend run.
  Additive metadata (`source_session_id`,
  `source_user_sequence`, `source_assistant_sequence`,
  `match_kind`) rides in the schema's existing `metadata` block
  — no schema shape change.
- **51. Crate-shared `providers::env_lock()` replaces
  per-module statics** in `packages/l4-router`. Two tests
  previously raced through `AETHER_OLLAMA_BASE_URL`; the shared
  lock fixes this at the source rather than forcing all callers
  onto `--test-threads=1`.

Carried: 1–45 from prior handoffs.

---

## 7. Next recommended prompt (paste verbatim into next session)

````md
You are Claude Code, continuing work on Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev

FIRST STEP — MANDATORY.
Run `./scripts/current_status.sh` and paste the output here
before proceeding. If the bash version errors on your shell,
`python scripts/current_status.py` produces the same output.
Do NOT restate status from memory; repo beats prompt
(Decision #32). If the script output conflicts with anything
else in this prompt, trust the script.

Session type: single-target day session. One primary goal,
optional cleanup if time remains.

Primary goal — pick ONE based on Don's direction:

  A. Memory V2 step 5 — retention sweep. BLOCKED until Don makes
     the L2/shell MemoryDomain enum reconciliation call
     (HANDOFF_2026-05-18_ALL_NIGHTER_TIER_1_PLUS_2A.md Risk A,
     three options documented). Do not start without the
     decision.

  B. Quality-Eval Tier 2B — tools/lint-quality-doc/ rot guard +
     flip docs/QUALITY-EVAL-V1-ARCHITECTURE.md from "Design-only
     as of 2026-05-14" to "Current as of 2026-05-18". Mirror the
     pattern in tools/lint-presence-doc/check.py exactly. Anchor
     manifest covers v1.1 / v1.2 / v1.3 symbols and strings.
     Reconcile any design-vs-code drift surfaced by the anchor
     seeding. Hard scope: only the rot guard + doc flip; no
     feature work, no new commands.

RESERVED for Don (do not resolve autonomously):
- The MemoryDomain enum reconciliation (Risk A).
- git push (34 commits ahead of origin/dev as of handoff).
- Any doctrine refresh.
- Avatar / viseme / L3 social-behavior rendering.
- Any new packages/*/ or apps/*/ directory (CLAUDE.md §3).

Delegated to Claude:
- Trait shapes, module organisation, test patterns, commit
  messages, execution reports, handoff content.
- Small helper scripts that support the work.

Process:
1. Current-status script, as above.
2. Read HANDOFF_2026-05-18_ALL_NIGHTER_TIER_1_PLUS_2A.md end to
   end, especially §4 (Risks) and §5 (on-deck).
3. Implement the chosen primary goal in scoped slices. One
   commit per slice.
4. Full check matrix from handoff §2 after the last slice. All
   green before stopping.
5. Execution report (if primary goal was B — follow the pattern
   of earlier EXECUTION_REPORT_*.md files). Fresh handoff.
6. Consider authorising `git push` if end-of-day feels right.

Hard constraints (still in force):
- No AuditRecordEvent shape change.
- User-sensitive domains (Facts, Artifacts) default Ask — do not
  flip.
- Do not destabilise the four rot guards that are already live.
- Dry-run evals 6/6, capture-replay 13/13, session-log-importer
  14/14 must all stay green.
- Default cargo test parallelism must remain safe (the two env-
  seam flakes stay dead). Do not add `--test-threads=1` back.
- Rot guards != acceptance criteria (GLOSSARY.md §6). Do not
  collapse.
- Memory tab and MemoryDrawer coexistence is deliberate for now;
  do not delete the drawer without explicit scope.
````

---

## 8. Anti-drift corrections made during this session

- None. Don's `NEXT_SESSION_PROMPT_2026-05-17.md` was accurate
  and the repo matched section-for-section. Decision #32 did
  not fire — the prompt included a §STATUS CORRECTION block
  that pre-empted the drift pattern.
- The agent did flag a real scope blocker at the start of Tier 1A
  (L2 trait needed extension for per-item forget / edit). Don
  confirmed via the prompt's pre-authorisation of Option B. No
  unilateral decision was made on the trait extension; the
  commit message spells out the scope guardrails observed.

---

(end of handoff)
