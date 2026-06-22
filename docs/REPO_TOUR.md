# Repo Tour — Free Aether, Community Edition

> Fifteen-minute guided walk through the directories. Read this before you
> touch code. [`ARCHITECTURE.md`](../ARCHITECTURE.md) is the authoritative
> description of the system; everything in this tour either points at that
> architecture or points at the code that materializes it.

---

## Top-level map

```
aether/
├── packages/        <- Cargo + pnpm workspace members (engines + shared infra). START HERE.
├── apps/            <- scaffold stubs; no runnable app yet.
├── src/             <- additional source surface alongside the workspace.
├── infra/           <- deploy / ops scaffolds.
├── tools/           <- governance linters (layer bans, policy bypass, etc.).
├── research/        <- research notes and exploration.
├── docs/            <- human-reading docs (this file, architecture, ADRs, etc.).
├── tests/           <- workspace + legacy test surface.
├── personas/        <- personality configs (legacy + forward-looking).
├── desktop/         <- legacy v1.0 Python tree. FROZEN. DO NOT IMPORT INTO RUST/TS.
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

## 1. `docs/` — start here

This is the human-reading surface. Read it before you touch code; everything
downstream is subordinate to the architecture it describes.

- [`ARCHITECTURE.md`](../ARCHITECTURE.md) (repo root) — the seven-layer
  architecture, the non-bypassable policy gate, and the direction of
  dependencies. If a code change conflicts with this file, the code is wrong.
- [`docs/ARCHITECTURE-V2.md`](ARCHITECTURE-V2.md) — the current architecture
  detail, expanded from the root overview.
- [`docs/PRODUCT-PLAN.md`](PRODUCT-PLAN.md) — product direction and the port
  plan for the legacy v1.0 tree. Use this to understand why the seven layers
  look the way they do.
- [`docs/adr/`](adr/) — the Architecture Decision Record log. Each ADR
  captures one locked decision (model defaults, retrieval wiring, hardware
  tier model, embeddings onboarding, persona delivery, mobile sync, …). Read
  the relevant ADR before proposing a change in its area.
- [`docs/LLM-PROVIDERS.md`](LLM-PROVIDERS.md),
  [`docs/PERSONA-SCHEMA.md`](PERSONA-SCHEMA.md),
  [`docs/ONBOARDING-SPEC.md`](ONBOARDING-SPEC.md),
  [`docs/DISTRIBUTION.md`](DISTRIBUTION.md) — topical specs for the provider
  surface, persona pack format, onboarding flow, and distribution model.
- [`docs/posts/`](posts/) — longer-form essays on the design (e.g. policy as
  a load-bearing layer).

**Rule of thumb:** if you are about to make a non-trivial decision and the
answer is not already captured in [`ARCHITECTURE.md`](../ARCHITECTURE.md) or
an ADR under [`docs/adr/`](adr/), record the decision there first — open a
docs PR before the code PR.

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
2. [`ARCHITECTURE.md`](../ARCHITECTURE.md) — the seven-layer architecture and
   the non-bypassable policy gate.
3. [`docs/PRODUCT-PLAN.md`](PRODUCT-PLAN.md) — product direction and hard rules.
4. [`docs/ARCHITECTURE-V2.md`](ARCHITECTURE-V2.md) — the layer map and current
   architecture detail.
5. [`docs/adr/`](adr/) — the locked decisions that shaped cross-layer
   communication and the storage/retrieval surfaces.
6. `packages/l5-policy/src/lib.rs` → `engine.rs` → `tests/engine_slice.rs` —
   the richest code in the repo today.
7. `WAVE3_EXECUTION_REPORT_2026-04-19.md` — how that code got there, with
   honest deferrals.
8. `CONTRIBUTING.md` — where your contribution fits.

That should take under an hour and leave you well-oriented.
