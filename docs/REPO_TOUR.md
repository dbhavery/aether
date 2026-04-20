# Repo Tour — Free Aether, Community Edition

> Fifteen-minute guided walk through the directories. Read this before you
> touch code. The planning corpus is authoritative; everything in this tour
> either points at doctrine or points at code that materializes doctrine.

---

## Top-level map

```
aether/
├── planning/        <- canonical doctrine + interface packs + plans. READ FIRST.
├── packages/        <- Cargo + pnpm workspace members (engines + shared infra).
├── apps/            <- scaffold stubs; no runnable app yet.
├── infra/           <- deploy / ops scaffolds.
├── tools/           <- governance linters (layer bans, policy bypass, etc.).
├── research/        <- research notes and exploration.
├── docs/            <- human-reading docs (this file, architecture, etc.).
├── personas/        <- personality configs (legacy + forward-looking).
├── src/, desktop/   <- legacy v1.0 Python tree. FROZEN. DO NOT IMPORT INTO RUST/TS.
│   frontend/,
│   configs/,
│   scripts/,
│   tests/
├── Cargo.toml       <- Rust workspace manifest.
├── pnpm-workspace.yaml
├── rust-toolchain.toml
├── README.md
├── CONTRIBUTING.md
├── ROADMAP.md
├── SECURITY.md, SUPPORT.md, CODE_OF_CONDUCT.md
└── WAVE*_EXECUTION_REPORT_*.md   <- what actually landed, per wave.
```

---

## 1. `planning/` — start here

This is doctrine. Everything downstream is subordinate to it.

- `planning/00_VISION_AND_GUARDRAILS.md` — sits above every other file. If a
  code change conflicts with this file, the code is wrong.
- `planning/01_product_doctrine.md` — hard rules for the product family
  (Community Edition, Pro, Isabelle). Use this to understand why the seven
  layers look the way they do.
- `planning/02_*.md` through `planning/18_*.md` — numbered spec corpus
  covering family, vision, UX, architecture, memory, avatar, trust, tiers,
  updates, tech-stack, persona schema, model router.
- `planning/plans/00_ORCHESTRATION_MAP.md` — how the seven layers fit
  together, with direction of dependencies.
- `planning/plans/L1_*.md` through `planning/plans/L7_*.md` — per-layer
  system designs + top-level implementation plans.
- `planning/plans/implementation_prep/` — the concrete contracts the code
  materializes:
  - `event_contracts_master.md` — every event that crosses a layer boundary.
  - `sqlite_schema_pack.md` — SQLite DDL plan, §3a-3d covers L5 tables.
  - `test_matrix_master.md` — the test coverage target.
  - `Lx_interface_pack.md` — per-layer trait / enum / IPC surface.
- `planning/OPEN_QUESTIONS.md` — living list of undecided calls. Check here
  before proposing architecture changes.
- `planning/HANDOFF_2026-04-18.md` and
  `planning/DECISION_LOCK_PASS_2026-04-18c.md` — the current decision state
  heading into Wave 3.5 and beyond.

**Rule of thumb:** if you are about to make a non-trivial decision and the
answer is not in `planning/`, you are probably supposed to open a PR against
`planning/` first, not against code.

---

## 2. `packages/` — the real code surface

Cargo + pnpm workspace members. Each directory is a single crate or a single
TS package. Layer crates are prefixed `l1-` … `l7-`; shared infra crates have
topical names.

### Shared infrastructure (Rust)

- `packages/event-bus/` — typed event envelopes. Every event carries
  `change_id`, `seq: u64`, `source_layer`. Sibling engines do not import
  each other; they talk through the bus.
- `packages/storage/` — SQLite substrate. `open_with_migrations()` opens a
  DB and runs the drafted migrations. Migration SQL lives under
  `packages/storage/migrations/`.
- `packages/media-engine/` — media I/O surface (stub).
- `packages/telemetry/` — structured logging (stub).

### Shared infrastructure (TypeScript)

- `packages/types/` — shared TS types.
- `packages/ui-kit/` — shared TS UI primitives + design tokens.

### Layer crates

- `packages/l5-policy/` — **THE** policy engine. First logic slice landed:
  in-memory ledger + audit store + five-stage evaluator + 10 integration
  tests. Start reading at `src/lib.rs`, then `src/engine.rs`, then
  `tests/engine_slice.rs`.
- `packages/l5-policy-ts/` — hand-written TS mirror of stable L5 types.
  Intended to be regenerated via `tools/ts-bindings-gen/` in a later wave.
- `packages/l1-interaction/`, `packages/l2-memory/`, `packages/l3-presence/`,
  `packages/l4-router/`, `packages/l6-persona/`, `packages/l7-trust/` —
  engine stubs. Traits, core enums, smoke tests only. Any of these is a
  reasonable place to start a first-logic slice.

### Layer boundary rule

Sibling `packages/l*-*` crates **do not** import each other. Coordination
happens through `packages/event-bus` or through `packages/l5-policy` /
`packages/l6-persona` typed outputs. `tools/lint-layer-boundaries/` enforces
this once Wave 4.1 flips it to blocking.

---

## 3. `tools/` — governance

These are the linters and code-generators that protect the architecture from
drift. Wave 1 landed scaffolds; Wave 4.1 flips the critical ones to blocking.

- `tools/lint-layer-boundaries/` — `cargo-deny` bans + ESLint rule enforcing
  the no-cross-layer-import rule.
- `tools/lint-policy-bypass/` — rejects direct executor calls outside
  `packages/l5-policy`.
- `tools/lint-private-asset-leak/` — fails builds if Isabelle-tagged content
  leaks into public distributable manifests.
- `tools/ts-bindings-gen/` — `ts-rs` / `specta` codegen from Rust structs.
  TS must never be hand-authored where Rust is canonical.

---

## 4. `apps/` — intentionally empty

The roadmap says apps land after the engines are credible on their own. The
current scaffolds exist so the workspace manifests resolve.

- `apps/desktop/` — future Tauri shell.
- `apps/guest/` — future Cloudflare Worker + Groq guest-mode endpoint.
- `apps/docs-site/` — future docs site.

Do not add meaningful app logic until L1 (or L4) has a first-logic slice.

---

## 5. Legacy Python tree — frozen

`src/`, `desktop/`, `frontend/`, `configs/`, `personas/`, `scripts/`, and
`tests/` contain the **v1.0 Python predecessor product**. That tree is:

- Not imported by any Rust or TS workspace member.
- Not covered by Rust or TS workspace checks.
- Ported capability-by-capability by X2 (Isabelle) and X4 (v1 content port)
  during later waves.
- Retired only after parity is verified.

**Do not "clean up" the legacy tree.** Leave it alone unless you are working
inside a planned port wave.

---

## 6. Reports — the honest record

Each wave ships a dated execution report at the repo root:

- `WAVE0_ASSIMILATION_REPORT_2026-04-19.md` — monorepo genesis.
- `WAVE1_EXECUTION_REPORT_2026-04-19.md` — shared infra + governance
  scaffolds.
- `WAVE2_EXECUTION_REPORT_2026-04-19.md` — L5 scaffold.
- `WAVE3_EXECUTION_REPORT_2026-04-19.md` — first L5 logic slice.
- `WAVE3_5_EXECUTION_REPORT_2026-04-19.md` — storage substrate
  (`rusqlite` + migration runner).
- `WAVE4_EXECUTION_REPORT_2026-04-19.md` — L1/L2/L3/L4/L6/L7 stub shells.
- `STABILIZATION_RECONCILIATION_REPORT_2026-04-19.md` — pre-publication
  alignment pass.
- `OSS_LAUNCH_PACK_REPORT_2026-04-19.md` — community-docs pack creation.
- `CHECKPOINT_COMMIT_REPORT_2026-04-19.md` — the commit-split pass that
  unstuck the `dev` branch history.

If a report disagrees with a README status block, the report wins for
"what actually landed," and the README is the one that should be updated.

---

## 7. Suggested reading order for a new contributor

1. `README.md` — section 3 (current status) is the honest picture.
2. `planning/00_VISION_AND_GUARDRAILS.md` — doctrine.
3. `planning/01_product_doctrine.md` — hard rules.
4. `planning/plans/00_ORCHESTRATION_MAP.md` — layer map.
5. `planning/plans/implementation_prep/event_contracts_master.md` — the
   shape of cross-layer communication.
6. `packages/l5-policy/src/lib.rs` → `engine.rs` → `tests/engine_slice.rs` —
   the richest code in the repo today.
7. `WAVE3_EXECUTION_REPORT_2026-04-19.md` — how that code got there, with
   honest deferrals.
8. `CONTRIBUTING.md` — where your contribution fits.

That should take under an hour and leave you well-oriented.
