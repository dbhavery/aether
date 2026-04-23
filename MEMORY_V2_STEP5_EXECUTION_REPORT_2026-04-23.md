# Memory V2 step 5 execution report — 2026-04-23

**Run 2 of six-run roadmap (2026-04-23).** Two sub-phases: 2a
executes ADR-0001 (MemoryDomain relocation + kernel stub
retirement); 2b implements the retention sweep on top.

## What shipped

| SHA | Subject |
| --- | --- |
| `ef13b0e` | refactor(l2-memory,shell): execute ADR-0001 — relocate MemoryDomain, retire kernel stub |
| `a1e9028` | feat(memory): Memory V2 step 5 — retention sweep (boot + hourly tick) |

### Phase 2a — ADR-0001 execution (`ef13b0e`)

- Created `packages/l2-memory/src/domain.rs` — canonical
  `MemoryDomain` with the six V2 variants (Session / Durable /
  Facts / Projects / Preferences / Artifacts), `ALL`, `label()`,
  `#[serde(rename_all = "snake_case")]` verbatim from the shell.
  3 unit tests locking variant set + labels.
- Deleted `packages/l2-memory/src/kernel.rs`. `MemoryKernel`,
  `MemoryItem`, kernel `MemoryDomain`, `MemoryId`, `EmbeddingRef`,
  `EmbeddingStore`, `PrivacyClass`, `ProvenanceTag`,
  `RetentionKind` all retired. L5 has its own `ProvenanceTag`;
  no other Rust callers per grep.
- Trimmed `packages/l2-memory/src/lib.rs`: added
  `pub mod domain;` + `pub use domain::MemoryDomain;`, dropped
  kernel re-exports, dropped `#![allow(dead_code)]`.
- Updated `packages/l2-memory/src/session.rs` doc comment (stale
  `MemoryKernel` reference).
- Rewrote `packages/l2-memory/tests/smoke.rs` to lock the V2
  domain set (ProvenanceTag contract test retired — L5 owns that
  vocabulary now).
- Updated `packages/l2-memory/README.md` surface description.
- `apps/desktop/src-tauri/src/memory_config.rs`: removed local
  `MemoryDomain` declaration, added `pub use
  aether_l2_memory::MemoryDomain` so every
  `memory_config::MemoryDomain` callsite (state.rs, commands.rs,
  memory_service.rs, tests) compiles unchanged. `MemoryRisk`
  stays in shell — it is policy config, not taxonomy (ADR-0001
  §Consequences).

### Phase 2b — retention sweep (`a1e9028`)

#### L2 — trait growth

- `SessionMemoryStore::prune_before(session_id, cutoff_ms) ->
  Result<usize, L2Error>` — strict `<` comparison; returns
  evicted row count; unknown session returns `Ok(0)`.
- `SessionMemoryStore::list_sessions() -> Result<Vec<String>,
  L2Error>` — enumerate sessions with ≥1 row.
- `InMemorySessionMemoryStore` — `retain`-based prune with
  char-budget accounting; HashMap keys for `list_sessions`.
- `SqliteSessionMemoryStore` — `prune_before` delegates to the
  existing `prune_older_than` helper; `list_sessions` runs
  `SELECT DISTINCT session_id FROM conversation_log`.
- 6 new `session.rs` tests covering strict cutoff, unknown
  session no-op, session isolation, char-budget freeing, and
  `list_sessions` enumeration.

#### Shell — sweep implementation + wiring

- `memory_service.rs::AppState::run_retention_sweep(now_ms)` —
  walks `MemoryDomain::ALL`, computes cutoff = `now_ms -
  retention_days * 86_400_000`, calls `prune_before` per known
  session. Emits **one aggregated `memory_forgotten` telemetry
  row per domain that evicted ≥1 rows** and **one L5 audit row
  per sweep invocation** via the `MemoryForget` capability.
  Non-Session domains skip with a trace note (no domain-typed
  store yet). Policy-Deny returns `Ok(0)` with a `warn!` — the
  user owns their memory.
- `main.rs` boot-time sweep before first command served. Hourly
  background tick via `RETENTION_SWEEP_INTERVAL_MS` (60 min);
  consumes `tokio::interval`'s immediate first tick so we don't
  sweep twice right after boot. Failures trace-warn; sweep
  failure never takes the shell offline.
- 6 new `memory_service.rs` tests covering: no-retention no-op,
  Session domain evicts when retention set, aggregated telemetry
  shape, no telemetry when nothing evicted, multi-session walk,
  non-Session domain skip.

#### Docs

- `docs/MEMORY-V2-ARCHITECTURE.md` §10 item 5 flipped from
  pending to shipped with implementation pointers; items 6 + 7
  remain pending.

## Check matrix (all green, post-Phase-2b)

| Check | Result |
| --- | --- |
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean |
| `cargo test --workspace` | all pass |
| `cargo test -p aether-l2-memory --all-features` | 21 session + 1 smoke + 16 sqlite |
| `cargo test -p aether-l4-router --features …` | 96 / 96 |
| `apps/desktop/src-tauri cargo test --all-features` | **204 / 204** (was 198, +6 sweep) |
| `python tools/lint-layer-boundaries/check.py` | 0 violations |
| `python tools/lint-vision-doc/check.py` | OK (51 anchors) |
| `python tools/lint-voice-doc/check.py` | OK (48 anchors) |
| `python tools/lint-presence-doc/check.py` | OK (39 anchors) |
| `python tools/lint-quality-doc/check.py` | OK (60 anchors) |
| `python tools/evals/__main__.py --dry-run` | 6 / 6 |
| `python tools/evals/__main__.py --dry-run --scenarios-root tools/evals/adversarial` | 6 fail (as designed) |
| `python tools/evals/test_capture_replay.py` | 13 / 13 |
| `python tools/evals/test_session_log_import.py` | 14 / 14 |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm build` | 237 / 68 kB |
| `apps/desktop && pnpm test` | 185 / 185 |

## Done-when checklist

- [x] `MemoryDomain` lives in L2; `kernel.rs` is gone; shell
      imports via `pub use aether_l2_memory::MemoryDomain`.
- [x] Retention sweep runs at boot + every hour.
- [x] Sweep eviction produces `memory_forgotten` telemetry + L5
      audit rows via `MemoryForget`.
- [x] Full check matrix green.
- [x] `docs/MEMORY-V2-ARCHITECTURE.md` §10 item 5 no longer
      "pending".

## Decisions (in-flight)

- **Aggregated telemetry per domain per sweep** (not per evicted
  row). Per-row would flood the Trust drawer's History tab on
  the first large eviction — aggregated keeps the signal useful.
  `memory_id` is `None` because the sweep operates on a set.
- **One L5 audit row per sweep invocation** (not per evicted
  row, not per domain). Symmetric with other scheduled
  maintenance tasks like the presence tick.
- **Non-Session domains skip with a trace note.** Today only
  Session has a backing store; the per-domain retention policy
  in `memory.json` persists verbatim for the future domain-typed
  durable store (Memory V2 step 6+). Avoids pretending the sweep
  is doing work on domains that have no content to evict.
- **`cutoff_ms == 0` is effectively a no-op** (strict `<`); a
  `retention_days` value that arithmetically underflows `now_ms`
  is saturated to `0`. Sweep output: nothing evicted.
- **Hourly tick swallows its own immediate first tick.** Boot
  sweep already ran in `setup`; letting `tokio::interval` fire
  immediately would double-sweep.
- **Policy-Deny on a sweep returns `Ok(0)` with a `warn!`**, not
  an error. The user's retention policy is the sovereign truth;
  an Observer-like posture refusing to evict is observable but
  should not abort the shell.

## Out of scope (intentional)

- Memory V2 step 6 (embeddings) — Run 3.
- Memory V2 step 7 (rot guard `tools/lint-memory-doc/`) — Run 4.
- Any `MemoryKernel` trait resurrection.
- Any change to `memory.json` shape.
- Any change to `AuditRecordEvent` shape (hard constraint).
- Any user-sensitive domain default flip (Facts / Artifacts
  stay Ask).
- Per-row telemetry and per-row audit rows.

## Known limitations (documented, not blocking)

- Only Session domain actively prunes today. Other domains'
  `retention_days` values are persisted but ignored by the
  sweep until a domain-typed store lands. Step 6 / 6-adjacent
  work closes this.
- Sweep operates on all of `MemoryDomain::ALL` but today five
  of six domains trace-skip. The trace level (`trace!`) is low
  enough not to flood logs.
