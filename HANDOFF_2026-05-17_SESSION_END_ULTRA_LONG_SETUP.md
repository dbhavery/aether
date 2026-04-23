# Handoff — 2026-05-17 session end (setup for ultra-long next session)

**Written:** 2026-05-17, session end.
**Branch:** `dev`, 27 commits ahead of `origin/dev`. **Push NOT authorized.**
**Working tree:** clean.

This handoff is optimised for an **ultra-long next session**.
Read it end to end; paste the "Next recommended prompt" section
verbatim into the next session to keep anti-drift cheap.

---

## 1. What shipped in this session (six commits, chronological)

| SHA | Subject |
| --- | --- |
| `939d953` | feat(l5-policy): register Memory V2 coarse caps in wave3_default — Memory V2 step 3 (slice 1) |
| `b43a9b0` | feat(apps/desktop): memory_service with per-domain gate + audit + telemetry — Memory V2 step 3 (slice 2) |
| `a02a851` | feat(apps/desktop/src/lib): memory telemetry kinds + TS parity test — Memory V2 step 3 (slice 3) |
| `37f00fa` | feat(presence): rot guard + flip Presence V1 doc to current — Presence V1 step 4 |
| `86798ee` | docs: add NFR skeleton — closes audit gap #2 |
| `917b37f` | docs: 2026-05-17 session handoff — Memory V2 step 3 + Presence V1 step 4 + NFR skeleton |
| `a4a571e` | chore: switch default local model from llama3 / llama3.2 to gemma4 |
| `cabaf4a` | feat(tools/evals): v1.2 — structured capture + replay mode |

Three subsystem closures / advances and two cross-cutting moves:

- **Presence V1 closed.** Rot guard at `tools/lint-presence-doc/`
  (39 anchors, 10 files, first-try green). Doc flipped to
  **Current as of 2026-05-17**. Design reconciled with reality:
  posture + user-attention are two implemented axes; session
  lifecycle axis is reserved as Future / V2.
- **Memory V2 step 3 shipped in three slices.** L5 preset
  registration; shell `memory_service` with per-domain
  Auto/Ask/Deny gate, `memory_write` / `memory_write_after_approval`
  / `memory_forget` / `memory_edit` / sampled `memory_read_audit_tick`;
  TS telemetry kinds + parity test.
- **NFR skeleton landed.** 11 sections; router-tier ≠
  performance-tier locked orthogonal; latency has three scales;
  security NFRs are one-way.
- **Default model flipped to Gemma 4.** L4 Ollama `DEFAULT_MODEL`
  and evals `AETHER_EVAL_OLLAMA_MODEL` both switched from
  `llama3` / `llama3.2` to `gemma4`. Test fixtures with literal
  `"llama3"` strings left alone — they exercise serializer
  round-trips, not the default contract.
- **Quality-Eval v1.2 shipped.** Structured JSON capture
  alongside the v1.1 markdown; `--replay-from <dir>` flag
  re-evaluates scenarios from captures without touching the
  backend. 13 unit tests in `tools/evals/test_capture_replay.py`;
  end-to-end smoke validated (replay produces correct pass /
  skip counts; mutex with --backend / --capture-into works).

---

## 2. End-of-session check matrix (all green)

| Check | Result |
| --- | --- |
| `git status` | clean |
| Commits ahead of `origin/dev` | **27** |
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean |
| `cargo test --workspace` | 151 / 151 |
| `cargo test -p aether-l3-presence` | 22 / 22 |
| `cargo test -p aether-l4-router --features ... -- --test-threads=1` | 96 / 96 |
| `apps/desktop/src-tauri cargo test --features …` | 186 / 186 |
| `python tools/evals/__main__.py --dry-run` | 6 / 6 |
| `python tools/evals/__main__.py --dry-run --scenarios-root tools/evals/adversarial` | 6 FAIL (as designed) |
| `python tools/evals/test_capture_replay.py` | **13 / 13** (NEW) |
| `python tools/lint-layer-boundaries/check.py` | 0 violations |
| `python tools/lint-vision-doc/check.py` | OK (51 anchors) |
| `python tools/lint-voice-doc/check.py` | OK (48 anchors) |
| `python tools/lint-presence-doc/check.py` | OK (39 anchors) |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm build` | 227 kB / 65 kB gzip |
| `apps/desktop && pnpm test` | 169 / 169 |

---

## 3. Subsystem status (post-session)

- **Vision V1** — DONE, rot-guarded. Closed subsystem.
- **Voice V1** — DONE, rot-guarded. Closed subsystem.
- **Presence V1** — DONE, rot-guarded. **Closed subsystem.**
- **Memory V2**:
  - Steps 1, 2, **3** complete.
  - **Step 4 (Trust drawer Memory tab)** — next major work.
  - Steps 5–7 (retention sweep / embeddings / rot guard) pending.
- **Quality-Eval V1**:
  - v1 scaffold, v1.1 (adversarial + live Ollama), **v1.2
    (capture + replay)** complete.
  - Pending: session-log replay importer, `lint-quality-doc/`
    rot guard, `pnpm eval` regression harness.
- **Spec package (audit gaps)**:
  - Gap #1 glossary: DONE.
  - Gap #2 NFR skeleton: DONE.
  - Gap #3 forward-looking requirement IDs: pending.
  - Gap #4 OSS/Pro/Cross-system spec views: pending.
  - Gap #5 light RTM view: pending.
  - Gap #6 `docs/AC-STYLE.md`: pending.

---

## 4. RISKS / ALERTS — read these before starting the next session

### A. Gemma 4 directive overrode an "ON HOLD" memory note.

My auto-memory from earlier tracks had **"Gemma 4 upgrade ON
HOLD"** with concerns: FA hang, slow inference, misleading
benchmarks (see `project_gemma4_upgrade.md`). Don's "we are
going to use gemma 4 for this project" directive this session
flipped `DEFAULT_MODEL` and `AETHER_EVAL_OLLAMA_MODEL` to
`gemma4` without re-verifying those concerns are resolved.

**Concrete risk:** the first time someone runs
`ollama pull gemma4 && pnpm tauri dev --features ollama-provider`
or `python tools/evals/__main__.py --backend ollama`, they will
hit whatever real-world problem put Gemma 4 on hold originally.
The eval harness has a 30 s default timeout, so a hang would
surface as a `ProviderTimeout` error per scenario; the shell
has the same timeout behaviour. Degradation is visible, but the
user-experience impact is real.

**Recommendation for next session:** if / when a real `ollama
pull gemma4` happens, confirm inference speed and stability on
Don's hardware **before** the next public-facing doc or
demo-facing commit. If problems resurface, the fix is narrow:
re-flip the defaults (two constants + four doc references).

### B. Stale-prompt drift triggered three times today.

Each time a fresh prompt arrived, its "Current reality" block
was out of sync with work that had just landed. Decision #32
held — I pushed back and verified against the repo — but the
cost is real (context, verification, re-planning).

**Recommendation for next session:** either paste section 5 of
this handoff (the track-status snapshot) verbatim into any new
prompt, or trust the repo-beats-prompt rule and stop restating
status in prompts at all. The planned
`scripts/current_status.sh` helper was **not** created this
session — it was an optional phase that got bumped by the
Gemma 4 directive.

### C. Memory V2 L2/shell enum mismatch is still deferred.

`packages/l2-memory::MemoryDomain` (Personal / Work / Health /
Finance / Creative / System) and
`apps/desktop/src-tauri/src/memory_config::MemoryDomain`
(Session / Durable / Facts / Projects / Preferences /
Artifacts) are different enums. The L2 kernel stub has no
consumers, so step 3 could ignore this. **Step 5 (retention
sweep) will force the choice.**

Three options, documented in `HANDOFF_2026-05-17_MEMORY_STEP3_PRESENCE_STEP4_NFR.md`
§1.1:
1. Replace L2 kernel enum with the design-doc enum; migrate
   `MemoryItem`.
2. Keep both enums with explicit mapping at the boundary.
3. Retire the L2 kernel stub; shell talks to
   `SessionMemoryStore` + a future domain-typed durable store.

**Recommendation for next session:** read option list before
starting step 5 or step 6. Picking the wrong reconciliation
path invalidates a lot of work.

### D. 27 commits unpushed on `dev`.

Push still not authorized. At some point this backlog is its
own risk — merge conflicts if origin moves, lost work if the
local tree corrupts, review pressure if the whole pile lands
at once. Nothing unsafe about the current state; just worth
calling out.

**Recommendation:** consider authorising `git push` at the end
of the next session, or at a natural "milestone" moment.

### E. Two known flaky tests still unaddressed.

`state::tests::yaml_persona_pack_merges_into_catalog` and
`providers::ollama::tests::from_env_uses_defaults_when_vars_unset`
— both env-contamination class flakes. Pass in isolation, pass
under `--test-threads=1`, intermittent under parallel. Today's
Gemma 4 change was in the same file as the second flake but
didn't affect it (the assertion is against the `DEFAULT_MODEL`
constant, not a literal).

**Recommendation for an ultra-long session:** a ~30 minute
cross-cutting cleanup to migrate `AETHER_PERSONAS_DIR` and
`AETHER_OLLAMA_*` test seams to `TempDir` / scoped-env patterns
would kill both flakes. High leverage; low surface area.

### F. Eval test file uses `importlib` + `sys.modules` registration.

`tools/evals/test_capture_replay.py` loads `__main__.py` via
`importlib.util.spec_from_file_location` and registers it in
`sys.modules` before `exec_module` so Python 3.14's dataclass
decorator can find the owning module. This works but is fragile:
renaming or restructuring `__main__.py` will break the test
silently (tests won't run, won't import).

**Recommendation:** if the eval harness is ever restructured
(e.g. split across files or renamed to `runner.py`), the test
file needs a matching update. There's no compile-time link
between them.

### G. My auto-memory is now stale.

The "Gemma 4 upgrade ON HOLD" note in
`C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/`
is no longer accurate. I will update it at session end.

---

## 5. What's on deck for the next session

### Primary target: Memory V2 step 4 — Trust drawer Memory tab

This is the first real UI surface that consumes the
`memory_service` API landed in step 3 slice 2. Scope:

- New Tauri commands: `memory_list(domain)` and wrapping the
  existing `AppState::memory_forget` / `memory_edit` methods as
  commands (`memory_forget`, `memory_edit`).
- New `MemoryTab.tsx` component inside `TrustDrawer.tsx`.
  Per-domain lanes (Session / Durable / Facts / Projects /
  Preferences / Artifacts). Per-item rows: timestamp · domain ·
  privacy class · source · content preview.
- Actions: forget item, forget-all-in-domain, edit fact.
- Approval surface for Facts / Artifacts: the existing media /
  mic modal pattern generalised; post-modal entry point is
  `memory_write_after_approval`.
- Tests: unit (Rust) + component (Vitest) + TS types.

### Secondary (if step 4 lands with time to spare)

In priority order — pick **one**, not all:

1. **Flake cleanup (Risk E).** ~30 min cross-cutting slice;
   unblocks parallel test runs. Useful for ultra-long sessions
   because it reduces the cost of every subsequent full-matrix
   verification.
2. **Session-log replay importer.** Bridges an existing Aether
   session log into the v1.2 capture directory format so a
   replay can cover real conversations. Scope: a small Python
   script that reads a telemetry log and emits the capture
   JSON schema.
3. **Forward-looking requirement ID scheme (gap #3).** A short
   design doc keyed to glossary §11, with one concrete ID per
   existing architecture doc. Validates the scheme shape
   against NFR, Memory V2, Presence V1 before locking.
4. **`scripts/current_status.sh`** (Risk B mitigation). Tiny
   helper that reads the latest `HANDOFF_*.md` and prints the
   subsystem snapshot. Unblocks every future session's prompt
   from being stale.

### Out of scope next session

- Memory V2 step 5 (retention sweep) — needs the L2/shell enum
  decision (Risk C) first.
- Memory V2 step 6 (embeddings) — downstream of step 5.
- Memory V2 step 7 (rot guard) — downstream of the Memory tab.
- `pnpm eval` wiring — downstream of the session-log importer.
- Any Gemma-4-specific debugging unless Don explicitly opens a
  thread for it.

---

## 6. Decisions log (new this session)

Cumulative from the prior handoffs plus today's additions:

- **42. Gemma 4 is the project default local model as of
  2026-05-17.** `DEFAULT_MODEL` in L4 Ollama and
  `AETHER_EVAL_OLLAMA_MODEL` in evals both flipped from
  `llama3` / `llama3.2`. Per-env override via `AETHER_OLLAMA_MODEL`
  remains the escape hatch.
- **43. Capture directory schema is additive.** v1.2 replay
  ignores unknown top-level fields, so future capture writers
  (richer metadata, persona snapshots, memory-window snapshots)
  can extend the schema without breaking existing replays.
- **44. `--replay-from` is mutually exclusive with
  `--capture-into` and `--backend ollama`.** Captures already
  exist by the time you are replaying; enforcing mutex at
  argparse time catches category errors cleanly.
- **45. Capture unit tests load the harness via
  `importlib.util.spec_from_file_location`.** The `__main__.py`
  naming collides with the CLI runtime sentinel, so a distinct
  module name (`aether_evals_harness`) is loaded explicitly and
  registered in `sys.modules` for Python 3.14's dataclass
  decorator.

Carried: 1–41 from prior handoffs.

---

## 7. Next recommended prompt (paste verbatim into next session)

````md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev (27 commits ahead of origin/dev at session start; not yet
pushed).

Execution vocabulary (use only these)
- Waves 1–4 for coarse architectural phasing.
- <Subsystem> V<N> step <N> for day-to-day execution.
- L1–L7 for dependency/moat layers (not time phases).

Current subsystem status (treat repo + latest handoff as source
of truth if this block disagrees)
- Vision V1, Voice V1, Presence V1: CLOSED subsystems.
- Memory V2 steps 1, 2, 3 complete.
  - Step 4 (Trust drawer Memory tab) is NEXT.
  - Steps 5–7 pending; step 5 will force the L2/shell
    MemoryDomain enum reconciliation (see handoff §C).
- Quality-Eval V1: v1 + v1.1 + v1.2 (capture + replay) complete.
  Pending: session-log importer, rot guard, pnpm eval.
- Spec package: glossary (gap #1) + NFR skeleton (gap #2) in.
  Forward-looking requirement IDs (gap #3) is the next spec
  move if time permits.
- Default local model: gemma4 (flipped 2026-05-17). Known
  concerns (FA hang, slow inference) unverified on Don's
  hardware; see handoff Risk A.

Anti-drift rule (non-negotiable; Decision #32)
- If this prompt's status is contradicted by git log, docs, or
  the handoff, STOP, verify, refuse to redo completed work, and
  update the handoff instead of silently complying.

Mandatory first steps
1. `git status` and `git log --oneline -30`. Expect ~27
   commits ahead of origin/dev; confirm tip matches the
   handoff.
2. Read `HANDOFF_2026-05-17_SESSION_END_ULTRA_LONG_SETUP.md`
   end to end — especially §4 (risks / alerts) and §5 (on-deck
   work).
3. Read `docs/MEMORY-V2-ARCHITECTURE.md` §§3, 4, 6 (Memory tab
   is the headline V2 surface per §6).
4. Skim:
   - `apps/desktop/src-tauri/src/memory_service.rs` — the
     backend surface step 4 will expose via Tauri commands.
   - `apps/desktop/src/components/TrustDrawer.tsx` — the UI
     host the Memory tab will land in.
   - `apps/desktop/src/lib/memoryTurns.ts` — TS allow-list for
     memory telemetry kinds.

Session focus: Memory V2 step 4 — Trust drawer Memory tab.

Scope
- Tauri commands: `memory_list(domain)`, `memory_forget`,
  `memory_edit`. Wire on top of the existing `AppState`
  methods; do NOT modify `AppState::memory_write` / `memory_forget`
  / `memory_edit` beyond what the commands need.
- `MemoryTab.tsx` component inside `TrustDrawer.tsx` (or a
  sibling file co-located with it). Per-domain lanes for all
  six domains. Per-item rows: timestamp · domain · privacy
  class · source · content preview.
- Actions: forget item, forget-all-in-domain, edit fact.
- Approval surface for Facts / Artifacts writes: reuse the
  existing media / mic approval-modal pattern; post-modal
  entry point is `memory_write_after_approval`.
- TS types mirroring the new commands.
- Tests: Rust unit (commands), Vitest component (tab +
  per-row), round-trip through the existing modal pattern.

Optional (only if step 4 lands cleanly with time to spare,
pick ONE):
a. Cross-cutting flake cleanup — migrate `AETHER_PERSONAS_DIR`
   and `AETHER_OLLAMA_*` test seams to `TempDir` / scoped-env.
   High leverage (makes every future parallel-test run
   cheaper).
b. Session-log replay importer for Quality-Eval v1.2 — small
   Python script that bridges an existing Aether session log
   into the capture directory schema so replay can cover real
   conversations.
c. `scripts/current_status.sh` — reads the latest HANDOFF_*.md
   and prints a one-screen subsystem snapshot. Unblocks every
   future prompt from being stale (see handoff Risk B).

Out of scope
- Memory V2 step 5 (retention sweep) — needs the L2/shell enum
  decision first.
- Memory V2 step 6 (embeddings) — downstream of step 5.
- Memory V2 step 7 (rot guard) — downstream of the tab.
- Any reconciliation of the two `MemoryDomain` enums.
- `pnpm eval` wiring.
- Gemma-4-specific debugging unless Don explicitly opens that
  thread.

Hard constraints (still in force)
- No push. No release / signing.
- No `AuditRecordEvent` shape change.
- User-sensitive domains (Facts, Artifacts) default Ask — do
  not flip.
- No new heavy dependencies.
- Do not destabilise Vision / Voice / Presence rot guards.
- Dry-run evals must still be 6/6 pass; capture/replay unit
  tests must still be 13/13 pass.
- Do not touch the two known flaky tests unless you are
  explicitly working on option (a) above. If you choose (a),
  migrate the env seams — do not patch the assertions.
- Rot guards and acceptance criteria remain conceptually
  separate (`docs/GLOSSARY.md` §6). Do not collapse.

Process
1. `git status` / `git log`, then read the handoff.
2. Implement the three Tauri commands with unit tests.
3. Build the Memory tab + component tests.
4. Wire the approval modal for Facts / Artifacts operations.
5. TS types for the new commands.
6. Full check matrix (fmt, workspace, l4-router
   --test-threads=1, shell, lints, evals dry-run + capture
   unit tests, pnpm typecheck/build/test).
7. Commit in scoped slices.
8. Execution report + fresh handoff. Update decisions log.
9. At session end, consider whether `git push` is appropriate
   (handoff Risk D).

Stay strictly on Memory V2 step 4 for the primary goal. If
tempted to do step 5 (sweep) or step 6 (embeddings), stop and
write the next handoff instead — the enum decision (Risk C)
must be explicit, not implicit.
````

---

(end of handoff)
