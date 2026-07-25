# Repo Tour — Free Companion, Community Edition

> Fifteen-minute guided walk through the directories. Read this before you
> touch code. The architecture docs under `docs/` are authoritative; everything
> in this tour either points at doctrine or points at code that materializes
> doctrine.

---

## Top-level map

```
aether/
├── packages/        <- Cargo + pnpm workspace members (engines + shared infra). START HERE.
├── apps/            <- scaffold stubs; no runnable app yet.
├── infra/           <- deploy / ops scaffolds.
├── tools/           <- governance linters (layer bans, policy bypass, etc.).
├── research/        <- research notes and exploration.
├── docs/            <- canonical doctrine + specs + this tour. The architecture reference.
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

## 1. `docs/` — the doctrine surface

This is doctrine. Everything downstream is subordinate to it.

- `ARCHITECTURE.md` (repo root) — the reference document, ~300 lines. The
  fastest way to understand the seven layers and the non-bypassable gate.
- `docs/ARCHITECTURE-V2.md` — the canonical architecture and vision. Sits above
  every other file. If a code change conflicts with this file, the code is
  wrong. Covers the layer model, event flow, storage, and the direction of
  dependencies.
- `docs/PRODUCT-PLAN.md` — hard rules and direction for the product family.
  Use this to understand why the seven layers look the way they do.
- `docs/adr/` — the architecture decision records (ADR-0001 onward). Every
  locked architectural call — the seven layers, the non-bypassable gate, the
  turn FSM, the re-evaluation triggers — lives here with its rationale. Check
  here before proposing architecture changes.
- `docs/PERSONA-SCHEMA.md` — the persona configuration schema.
- `docs/LLM-PROVIDERS.md` — the model-router provider contract.
- `docs/ONBOARDING-SPEC.md` and `docs/DISTRIBUTION.md` — the onboarding flow
  and how the product is packaged and shipped.
- `docs/posts/` — narrative explainers for the design (e.g. why policy is
  load-bearing).

**Rule of thumb:** if you are about to make a non-trivial decision and the
answer is not in `docs/`, you are probably supposed to open a PR against
`docs/` first, not against code.

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
- `tools/ts-bindings-gen/` — `ts-rs` / `specta` codegen from Rust structs.
  TS must never be hand-authored where Rust is canonical.

---

## 4. `apps/` — the shipped applications

- `apps/desktop/` is the real end-user application: the Companion desktop
  shell (Tauri 2 + React + Vite) that wraps the Rust engine path. It is
  the surface the UI doctrine rules (notably §8 used-as-user) apply to.
  - Tests: `pnpm test` (vitest unit + React Testing Library component
    tests under `src/**/*.test.tsx`) and `pnpm test:e2e` (Playwright
    used-as-user harness under `e2e/` — drives the real frontend in
    Chromium with the Tauri IPC mocked; covers the approval modal,
    persona / autonomy / media / mic permission gates, the memory tab,
    onboarding, capture panels, and chat outcomes). The e2e suite is a
    blocking CI job; see `apps/desktop/e2e/README.md`.
- `apps/l1-cli/` is the L1 interaction-timing CLI demo.

---

## 5. Legacy Python tree — frozen

`src/`, `desktop/`, `frontend/`, `configs/`, `personas/`, `scripts/`, and
`tests/` contain the **v1.0 Python predecessor product**. That tree is:

- Not imported by any Rust or TS workspace member.
- Not covered by Rust or TS workspace checks.
- Ported capability-by-capability from the upstream codebase and v1 content
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
2. `docs/ARCHITECTURE-V2.md` — doctrine.
3. `docs/PRODUCT-PLAN.md` — hard rules.
4. `docs/adr/` — the architecture decision records; the layer map and the
   shape of cross-layer communication.
5. `ARCHITECTURE.md` — the ~300-line reference walkthrough.
6. `packages/l5-policy/src/lib.rs` → `engine.rs` → `tests/engine_slice.rs` —
   the richest code in the repo today.
7. `WAVE3_EXECUTION_REPORT_2026-04-19.md` — how that code got there, with
   honest deferrals.
8. `CONTRIBUTING.md` — where your contribution fits.

That should take under an hour and leave you well-oriented.
