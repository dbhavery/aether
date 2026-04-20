# Handoff — Continue the companion build (2026-04-25)

**Written:** 2026-04-24 (autonomous continuation run).
**Branch state:** `dev`, three new commits this run, **NOT pushed**.
**Next session mode:** broad autonomous build authorization; no push
authorization assumed.

---

## 0. Morning status

1. Branch `dev` has three new local commits on top of `70b5734`:
   - `adcc3f0` feat(l2,apps/desktop): [P1] durable memory retention policy
   - `76a3fe9` feat(apps/desktop): [P2] Trust drawer history tab with latency/tokens
   - `42d01d6` feat(l6,apps/desktop): [P3] persona-pack YAML loader
2. Working tree is clean.
3. Full check set is green:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cargo test -p aether-l2-memory --features sqlite-backend` (11/11)
   - `cargo test -p aether-l6-persona` (16/16)
   - `apps/desktop/src-tauri && cargo test` (24/24)
   - `python tools/lint-layer-boundaries/check.py` (0 violations)
   - `apps/desktop && pnpm typecheck && pnpm build` (clean)
4. **Not pushed.** Previous rule holds — push authorization must be
   explicit.

## 1. Commits landed this run

```
adcc3f0 feat(l2,apps/desktop): [P1] durable memory retention policy
76a3fe9 feat(apps/desktop): [P2] Trust drawer history tab with latency/tokens
42d01d6 feat(l6,apps/desktop): [P3] persona-pack YAML loader
```

## 2. Execution reports

- [P1_RETENTION_POLICY_EXECUTION_REPORT_2026-04-24.md](file:///C:/Users/dbhav/Projects/aether/P1_RETENTION_POLICY_EXECUTION_REPORT_2026-04-24.md)
- [P2_TRUST_HISTORY_TAB_EXECUTION_REPORT_2026-04-24.md](file:///C:/Users/dbhav/Projects/aether/P2_TRUST_HISTORY_TAB_EXECUTION_REPORT_2026-04-24.md)
- [P3_PERSONA_PACK_YAML_LOADER_EXECUTION_REPORT_2026-04-24.md](file:///C:/Users/dbhav/Projects/aether/P3_PERSONA_PACK_YAML_LOADER_EXECUTION_REPORT_2026-04-24.md)

## 3. What the product does now

Everything from 2026-04-24, plus:

- **Durable memory is bounded.** Default retention is 500 rows per
  session with automatic row-cap eviction on write. Age-based pruning
  is configurable and exposed via `prune_session` / `prune_all`; the
  user-facing "Forget older than N days" Tauri command
  (`forget_older_than_days`) lives on the shell.
- **Trust drawer has a History tab.** Shows the last 50 turns with
  outcome kind, persona/provider/tier, latency (ms or s), and
  prompt/completion/total tokens. "Clear" button invokes
  `telemetry_clear`. Buffer is in-memory only.
- **Personas can be loaded from YAML.** On boot, the shell scans
  `<app_data_dir>/personas/*.yaml` (or `AETHER_PERSONAS_DIR` if set)
  and merges those personas into the built-in catalog. Collisions
  with built-ins are skipped with a WARN.

## 4. What to build next — priority backlog

### Priority 1 — UI for `forget_older_than_days`

Add a Settings section (or a button in the Trust drawer footer) that
calls `forget_older_than_days` with an "N days" input (or a 30-day
default). Show the returned `{ removed, applied }` as an
affirmation. Backend is ready; only React work remains.

### Priority 2 — Settings entry to change autonomy preset after
first-run

The PresetPicker only shows once (versioned localStorage gate).
Settings currently has no way to change preset. Add a row (or a
whole Settings panel) calling `set_autonomy_preset` with the three
choices.

### Priority 3 — Shipped persona pack `personas/` directory

Create a `personas/` directory with one or two example YAML
personas in the repo (beside README.md). Document where to put them
for the shipped app (`%APPDATA%/Aether/personas/`). No code — just
docs + sample YAML.

### Priority 4 — Persona pack hot-reload

Currently the catalog is built once per AppState. A file watcher on
`<app_data_dir>/personas/` that rebuilds the catalog on change
would let contributors iterate without restart. Possible mirror:
`notify` crate, event-bus emission for "catalog changed", shell
picker refresh.

### Priority 5 — Telemetry durability (optional)

The History tab is in-memory. If users want a persistent "what did
Aether do this week" view, tee each `TelemetryEntry` into a new
SQLite table gated behind the same `sqlite-backend` feature.
Reuses the retention plumbing from P1.

### Priority 6 — Wave-5 tool execution through L5

Still on the horizon. Plan when ready.

## 5. Risks / things to review first

- **`default_bounded` retention (500 rows/session) is now the shipped
  default.** Existing `aether.db` files with more rows per session
  will get their oldest rows evicted on the next append. Intended
  behaviour; worth mentioning in release notes.
- **Enum wire format changed.** `Tone`/`Verbosity`/`Stance`/`Humor`
  now serialise lowercase (for YAML ergonomics). Grep confirmed no
  external consumer used PascalCase. If any persisted JSON with the
  old casing ever surfaces, add a migration shim.
- **YAML personas are additive-only.** Can't override a built-in
  persona. A later wave can lift this with signed packs.
- **`AETHER_PERSONAS_DIR` env var is process-global.** Test isolation
  uses a file-scoped mutex. If the project ever runs tests out of
  process, adjust.
- **Telemetry buffer is process-scoped.** Restarting the app wipes
  history. If durability is desired (P5 above), wire to SQLite.

## 6. How to run / validate

```bash
export PATH="$HOME/.cargo/bin:$PATH"
cargo fmt --all -- --check
cargo check --workspace
cargo test --workspace

# Feature-gated / targeted:
cargo test -p aether-l2-memory --features sqlite-backend
cargo test -p aether-l5-policy --lib
cargo test -p aether-l6-persona

python tools/lint-layer-boundaries/check.py

cd apps/desktop/src-tauri
cargo check
cargo test
cargo check --features ollama-provider
cargo test  --features ollama-provider

cd ../
pnpm typecheck && pnpm build
pnpm tauri dev
```

---

## 7. Copy-paste starting prompt for the next unattended session

```
You are Claude Code, working on Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch:    dev (NOT pushed; three local commits adcc3f0, 76a3fe9,
           42d01d6 await review)

Read in this exact order before touching anything:

1. HANDOFF_2026-04-25_CONTINUE_COMPANION_BUILD.md
2. HANDOFF_2026-04-24_CONTINUE_COMPANION_BUILD.md (prior context)
3. P1_RETENTION_POLICY_EXECUTION_REPORT_2026-04-24.md
4. P2_TRUST_HISTORY_TAB_EXECUTION_REPORT_2026-04-24.md
5. P3_PERSONA_PACK_YAML_LOADER_EXECUTION_REPORT_2026-04-24.md
6. apps/desktop/src-tauri/src/state.rs + commands.rs
7. git status + git log --oneline -20

---

### Autonomy authorization

Broad autonomous build authorization, zero launch/distribution.
Do NOT push unless Don explicitly says so again.

You ARE authorized to:
- expand the shell, engines, supporting crates,
- add tests, reports, docs, handoffs,
- create multiple local commits,
- refactor implementation details.

You are NOT authorized to:
- push anything without explicit instruction,
- publish a release,
- touch signing / notarization / release secrets,
- weaken tests, lint, CI, or boundary rules,
- do destructive cleanup of legacy trees.

---

### Priority backlog for this run

P1 — Settings UI for forget_older_than_days (30-day default, show
     removed count). Backend is ready.

P2 — Settings entry to change the autonomy preset after first run
     via set_autonomy_preset.

P3 — Ship example persona YAML files in a repo-level `personas/`
     directory with a README documenting the loader contract.

P4 — Persona-pack hot-reload (notify crate) if time.

P5 — Telemetry durability via a new SQLite table + migration 0005
     if time.

---

Work cadence unchanged. Per slice: implement → focused tests →
full check set → execution report → commit with conventional
message + Co-Authored-By. End-of-run: handoff.

Start by reading the files above, confirming git state, then
executing P1.
```
