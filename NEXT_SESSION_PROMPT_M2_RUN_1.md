# Next session prompt — Milestone 2 Run 1 (Retrieval Wiring)

Paste the fenced block below verbatim into the next session.

````md
You are Claude Code, continuing work on Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev. Session-start tip should match the tip of the 2026-04-24
Milestone 2 planning handoff (verify with `git log --oneline -5`).
Push state: determined at runtime.

SESSION TYPE
- Implementation. Milestone 2 Run 1 of the roadmap
  `ROADMAP_2026-04-24_MILESTONE_2.md`: Retrieval Wiring.
- Target: turn engine consumes `EmbeddingStore::query_nearest` for
  Durable / Projects / Artifacts recall when embeddings are enabled;
  soft-fallback to `SessionMemoryStore::recent` when not.
- Also ships the hygiene chore bundled into Run 1's first commit:
  `.gitattributes` + `current_status.sh` newest-handoff fix.

================================================================
§MANDATORY FIRST STEPS
================================================================

1. `./scripts/current_status.sh` (Windows fallback:
   `python scripts/current_status.py`). Paste the output. Repo
   beats prompt (Decision #32). If the script still surfaces
   stale risks, trust the newest `HANDOFF_*.md` on disk — that
   fix ships THIS run.
2. `git log --oneline -15`. Confirm the Milestone 2 planning
   commit is present plus Milestone 1 run closure commits
   (`ad31f5d`, `09df5b0`, `120b6d0`, `e135c2a`, `ca8219b`).
3. Read, in order:
   - `HANDOFF_2026-04-24_MILESTONE_2_PLAN.md` (the planning
     session that opened this milestone).
   - `ROADMAP_2026-04-24_MILESTONE_2.md` Run 1 section + hygiene
     chore preamble.
   - `MILESTONE_1_RETROSPECTIVE_2026-04-23.md` §3 item 1 (the
     `current_status.sh` bug this run fixes).
   - `docs/MEMORY-V2-ARCHITECTURE.md` §§6, 8, 9 (embeddings +
     recall contracts).
   - `docs/adr/ADR-0002-embeddings-provider-and-vector-backend.md`
     — the embedding store shape Run 1 consumes.
   - `packages/l2-memory/src/embeddings.rs` — trait surface.
   - `packages/l2-memory/src/session.rs` — `SessionMemoryStore::recent`
     signature.
   - `packages/l4-router/` — wherever recall is assembled today.
     Confirm before designing the wiring.
   - `packages/l5-policy/src/capabilities.rs` — `MemoryRead` surface,
     to evaluate reserved decision #M2-01.

================================================================
§STATUS CORRECTION (supersedes any conflicting prompt)
================================================================

Verified subsystem state at Milestone 2 open:
- Vision V1, Voice V1, Presence V1, Memory V2, Quality-Eval V1 —
  CLOSED, rot-guarded. Unchanged.
- Memory V2 embeddings path is live but not yet consumed by the
  turn engine. That gap closes in this run.
- Default local text model: gemma4 (still unverified on real
  workloads).
- Default local embedding model: Ollama `nomic-embed-text` (still
  unverified on real workloads — Run 3 Onboarding turns this into
  a one-click experience).
- Decisions #1–#70 carry from Milestone 1. Milestone 2 adds
  #M2-01+ below.

================================================================
§DOCTRINE GROUNDING (hard rules still in force)
================================================================

- L5 single writer for side effects. Retrieval is a READ; it routes
  through the existing `MemoryRead` capability unless reserved
  decision #M2-01 decides otherwise.
- Rot guards != acceptance criteria.
- No raw-media persistence.
- Additive by default.
- Private assets stay out of public distributables.
- No silent fallback — fallback semantics must be explicit in code
  + doc.

================================================================
§RESERVED DECISIONS (do NOT resolve autonomously)
================================================================

1. **#M2-01** — Capability name for retrieval-augmented reads.
   Propose: reuse `MemoryRead` (same data, different source). Only
   introduce `MemoryRetrieve` if the audit surface genuinely needs
   to distinguish embedding-augmented reads. Propose with a short
   justification; Don decides.
2. **#M2-02** — Retrieval timing. Blocks the turn, or runs in
   parallel with prompt compilation? Propose: parallel with a
   short timeout (e.g. 250 ms) + silent fallback to
   `SessionMemoryStore::recent`. Include timeout value and rationale.
3. **#M2-03** — Union/rank strategy for embedding + session
   results. Propose: interleave by recency + similarity score,
   cap total at N items; make N configurable via `memory.json`.
   Don decides the default.
4. **#M2-04 — #M2-08** — reserved for later Milestone 2 runs.
   Do not touch.
5. Gemma 4 rollback. Git push. Requirement IDs (Gap #3).
   Unchanged from Milestone 1.

================================================================
§DELEGATED DECISIONS (you may decide)
================================================================

- Module layout inside `packages/l4-router/`. Naming, test
  patterns, commit messages, execution report shape.
- Deterministic tie-breaker for recall ordering when similarity
  scores are equal (e.g. newer wins, then stable ID).
- `.gitattributes` contents beyond the `* text=auto eol=lf`
  line (optional hardening).
- `scripts/current_status.sh` / `.py` implementation detail —
  how "newest handoff" is computed (filename date regex, mtime,
  etc.). Propose in the commit message; no ADR needed.

================================================================
§PHASE — Milestone 2 Run 1 (Retrieval Wiring)
================================================================

### Commit 1 — Hygiene chore (bundled per roadmap)

- Add root `.gitattributes` with `* text=auto eol=lf`. Verify
  `git status` stays clean after the change on Don's Windows
  environment.
- Fix `scripts/current_status.sh` + `scripts/current_status.py`
  to select the newest `HANDOFF_*.md` by filename date instead of
  the hard-coded reference. Confirm the script surfaces Milestone
  2 planning handoff data, not the 2026-05-18 stale one.

Commit subject: `chore: silence CRLF warnings + current_status reads newest handoff`

### Commit 2 — Retrieval wiring

- Propose + get sign-off on reserved decisions #M2-01 / #M2-02 /
  #M2-03 before writing router code. (Propose inline in the
  session; pause for Don's reply.)
- Wire recall path in `packages/l4-router/`: when
  `memory.json::embeddings.enabled == true` AND a valid provider
  is configured, query `EmbeddingStore::query_nearest` for the
  three embed-eligible domains (Durable / Projects / Artifacts);
  union with `SessionMemoryStore::recent` per decision #M2-03.
- When embeddings off OR provider unreachable OR timeout hit:
  fall back to session-only. Fallback must be logged at `warn!`
  level (not `debug!`); silent failures are a doctrine violation.
- Capability routing per decision #M2-01.

Commit subject: (shape per decisions; e.g.)
`feat(l4-router): consume embedding retrieval for Durable/Projects/Artifacts recall`

### Commit 3 — Tests + doc update

- L4 router tests:
  - Determinism: embeddings off → byte-identical recall to `ad31f5d`.
  - Fallback: embeddings on + provider unreachable → session-only
    recall, `warn!` emitted.
  - Happy path: embeddings on + matching rows → recall contains
    expected items in the expected order.
- `docs/MEMORY-V2-ARCHITECTURE.md` §10 item 6+ updated to reflect
  retrieval-is-live (was "embeddings shipped but not consumed").
- `tools/lint-memory-doc/check.py` re-verified; anchor count may
  grow if new headings are added.

Commit subject: `test+docs: retrieval wiring determinism + Memory V2 doc refresh`

### Out of scope (defer)

- UI feedback for recalled items (Run 6 Memory Tab Polish).
- Onboarding flow for Ollama / model-pull (Run 3).
- Non-Session domain storage (Run 2 Durable Store).
- `pnpm eval` / CI (Run 5).

================================================================
§DONE WHEN
================================================================

- `cargo fmt --all -- --check` clean.
- `cargo check --workspace` clean.
- `cargo test --workspace` all pass, including new L4 router
  determinism + fallback tests.
- With `embeddings.enabled = false` (default), turn output is
  byte-identical to `ad31f5d` across the test suite.
- With `embeddings.enabled = true` + unreachable provider, fallback
  works and emits exactly one `warn!` per turn (not per query).
- `python tools/lint-memory-doc/check.py` passes after doc update.
- `scripts/current_status.sh` surfaces the Milestone 2 plan handoff,
  not the 2026-05-18 one.
- `apps/desktop && pnpm typecheck` clean; `pnpm build` clean;
  `pnpm test` all pass (count may shift if frontend touches
  recall UI — but scope says it shouldn't, so expect unchanged).

================================================================
§CHECK MATRIX — run at session end
================================================================

Same shape as `HANDOFF_2026-04-23_RUN_3_PLUS_4.md` §2. Add:
- L4 router test count before/after (expected +3 at minimum).
- `scripts/current_status.sh` output showing newest handoff.

================================================================
§SESSION-END DISCIPLINE
================================================================

1. Full check matrix. All green.
2. Working tree clean.
3. One execution report:
   `RETRIEVAL_WIRING_EXECUTION_REPORT_2026-04-24.md`.
4. Handoff `HANDOFF_2026-04-24_M2_RUN_1.md` covering:
   - commit table, check matrix, subsystem status.
   - decisions log additions (#M2-01, #M2-02, #M2-03 at minimum;
     more if the hygiene chore surfaces any).
   - risks section with retired-risks: retrospective §3 item 1
     retires when the `current_status.sh` fix lands.
   - next prompt for Milestone 2 Run 2 (Durable Store / ADR-0003).
5. `git push origin dev` at session end. Milestone 1 retrospective
   §3 item 3 makes "push after every run" explicit doctrine in
   Milestone 2.

================================================================
§STANCE
================================================================

This run is the payoff for Milestone 1's embeddings infra. The
feature only matters if the turn engine reads it. Stay scoped:
retrieval wiring + tests + doc refresh, plus the bundled hygiene
chore. Don't start on Durable Store — Run 2 needs an ADR before
touching store shape, and that ADR is a conversation, not an
inline decision.

Propose the three reserved decisions up front, wait for Don, then
ship. Don't silently pick capability names or timeout values —
those are the decisions Milestone 2 will look back on.

Good luck.
````
