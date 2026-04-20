# Free Aether — Community Edition (OSS Preview)

> A local-first, desktop-native AI companion architecture. Rust-first engines, a
> non-bypassable policy gate, explicit trust surfaces. Early preview — the
> foundations are in place, most engine logic is not yet.

**Status:** `dev` branch, pre-0.1 preview. The repository is under active
architecture. Expect breaking changes.

---

## 1. What Aether is

Aether is not a chatbot UI and not a general-purpose "AI app." It is an
architecture for a **long-lived companion** that runs locally on a user's
machine and treats the user relationship — memory, presence, timing, trust —
as first-class engines, not afterthoughts.

The project is organized into **seven layers**, each an independent engine
with explicit contracts:

| Layer | Name              | Responsibility                                          |
|-------|-------------------|---------------------------------------------------------|
| L1    | Interaction       | Turn FSM, reflex classifier, STT/TTS adapters, timing   |
| L2    | Memory            | Local memory kernel, embeddings, provenance             |
| L3    | Presence          | Avatar scheduler, behavior frames, rendering surface    |
| L4    | Router            | Model / tool router (local + remote providers)          |
| L5    | **Policy**        | Non-bypassable authorization gate, audit, grants, BYOK  |
| L6    | Persona           | YAML → compiled persona artifacts, hot-reload           |
| L7    | Trust UX          | Onboarding, approvals, posture banners                  |

Shared infrastructure (`event-bus`, `storage`, `telemetry`, `types`, `ui-kit`,
`media-engine`) sits underneath. Everything routes through L5 for
side-effectful actions — there is no back door.

**Free Aether — Community Edition** is the open-source preview track. A
separate Pro flagship and a private build (Isabelle) exist in the doctrine
but are out of scope for this repository.

---

## 2. Why Aether

Most "AI companion" projects collapse into chat UIs on top of an LLM API.
Aether refuses that shape on purpose:

- **Companion, not chatbot.** Long-lived relationship, not single-session Q&A.
- **Local-first.** User data, memory, and persona state live on the user's
  machine. Remote calls are deliberate, visible, and policy-governed.
- **Policy is load-bearing.** Grants, audit, cost caps, degraded modes, and
  re-evaluation triggers are in the type system, not bolted on later.
- **Rust-first for engines.** Timing, policy, storage, routing, and memory
  engines are Rust crates. TypeScript is for UI and generated bindings only.
- **Desktop-first product.** Tauri long-term, pywebview tactical for the
  preview. Browser UI is an implementation detail, not the core product.

If you want a two-hour "chat with my notes" demo, this is the wrong repo. If
you want to help build durable architecture for a companion that still works
offline, you're in the right place.

---

## 3. Current status — honest snapshot

```
FREE AETHER — COMMUNITY EDITION — STATUS 2026-04-19

FOUNDATION / DOCTRINE
[##########] 100%  Vision & guardrails locked
[##########] 100%  Product doctrine
[##########] 100%  7-layer orchestration map
[##########] 100%  5 control-plane decisions locked

DESIGN / PREP
[##########] 100%  L1–L7 system designs
[##########] 100%  L1–L7 interface packs
[##########] 100%  Event contracts master
[##########] 100%  SQLite schema pack (DDL drafted)
[##########] 100%  Test matrix master

REPO / INFRA
[##########] 100%  Wave 0 — monorepo assimilation
[##########] 100%  Wave 1 — workspace + shared crates + governance
[##########] 100%  Wave 2 — L5 scaffold (types, traits, IPC surface)

L5 — POLICY ENGINE
[##########] 100%  Wave 3 — first real logic slice
                   (in-memory ledger + audit + 5-stage evaluator,
                    18 tests across engine_slice + ipc + sink + audit_store,
                    audit-before-Allow invariant)
[##########] 100%  Wave 3.5 — SQLite storage substrate
                   (rusqlite bundled, open_with_migrations() runs the
                    drafted DDL, 3 integration tests incl. append-only
                    trigger + warm-open idempotency.
                    L5 backends still in-memory — flipping L5 onto the
                    substrate is future work.)
[..........]   0%  Wave 4.x — hash-chain + HMAC + BYOK cost-cap +
                   SqliteGrantLedger / SqliteAuditStore

OTHER ENGINES — STUB SHELLS (Wave 4)
[##########] 100%  L1/L2/L3/L4/L6/L7 traits + core enums + smoke tests
[..........]   0%  L1–L7 first-logic slices

PRODUCT INTEGRATION
[..........]   0%  apps/desktop (Tauri shell)
[..........]   0%  apps/guest  (Cloudflare Worker + Groq endpoint)
[..........]   0%  apps/docs-site
[..........]   0%  End-to-end onboarding → first turn
```

### What runs today

- `pnpm -r --if-present typecheck` is green across the TS packages.
- `cargo check --workspace` is **green** on stable Rust (toolchain pinned in
  `rust-toolchain.toml`).
- `cargo test --workspace` is **green** — every crate's tests pass. Highlights:
  - `aether-l5-policy`: 18 tests (10 integration slice + 8 type/IPC/sink).
  - `aether-storage`: 8 tests, including 3 integration tests that open a
    real SQLite file, run the drafted migration, assert every expected
    table exists, assert the append-only trigger rejects `DELETE`, and
    assert a warm reopen is idempotent.
  - Six engine stub crates (L1–L7 minus L5): smoke tests only.

### What does not run yet

- No end-to-end user-facing flow. There is no runnable desktop app in this
  repository yet.
- No LLM, STT, TTS, or avatar pipeline is wired up. The engine stubs declare
  the right traits and enums; none of the I/O is hooked up.
- **L5 still uses in-memory persistence.** The storage substrate
  (`rusqlite` + `open_with_migrations()`) exists and runs, but L5's
  `GrantLedger` and `AuditStore` have not yet been swapped onto SQLite-backed
  implementations. That swap is an explicit future wave (see
  [ROADMAP.md](ROADMAP.md) § "L5 durable persistence"). Today, L5 state is
  lost on process exit.

### What is in `src/`, `desktop/`, `frontend/`

The legacy **v1.0 Python tree** is intentionally left in place. It is the
predecessor product; its useful content is being ported forward into the new
architecture capability-by-capability. Do not import from it into Rust or TS
workspace members, and do not "clean it up." See
`planning/LEGACY_ROOT_MAPPING_2026-04-19.md` for the port plan.

---

## 4. Repo layout

```
aether/
├── planning/              # Canonical doctrine + plans. Read before editing.
│   ├── 00_VISION_AND_GUARDRAILS.md     # Sits above everything else.
│   ├── 01_product_doctrine.md
│   ├── 02..18_*.md                      # Numbered spec corpus.
│   ├── plans/                           # L1–L7 system designs + interface packs.
│   └── plans/implementation_prep/       # Event contracts, SQLite schema, test matrix.
│
├── packages/              # Cargo + pnpm workspace members.
│   ├── event-bus/         # Typed envelopes (Rust).
│   ├── storage/           # Local persistence substrate (Rust; migrations drafted).
│   ├── media-engine/      # Media I/O surface (Rust, stub).
│   ├── telemetry/         # Structured logging (Rust, stub).
│   ├── types/             # Shared TS types.
│   ├── ui-kit/            # Shared TS UI primitives + tokens.
│   ├── l5-policy/         # THE policy engine. First logic slice landed.
│   ├── l5-policy-ts/      # Hand-written TS mirror of stable L5 types.
│   ├── l1-interaction/    # Engine stubs — traits, enums, smoke tests only.
│   ├── l2-memory/         # Engine stubs.
│   ├── l3-presence/       # Engine stubs.
│   ├── l4-router/         # Engine stubs.
│   ├── l6-persona/        # Engine stubs.
│   └── l7-trust/          # Engine stubs.
│
├── apps/                  # Scaffolds only; no runnable app yet.
├── infra/                 # Deployment / ops scaffolds.
├── tools/                 # Governance linters (cargo-deny, ESLint rules, ts-rs).
├── research/              # Research notes.
│
├── src/, desktop/,        # Legacy v1.0 Python tree. Frozen; being ported out.
│   frontend/, configs/,
│   personas/, scripts/,
│   tests/
│
├── Cargo.toml             # Rust workspace manifest.
├── pnpm-workspace.yaml    # TS workspace manifest.
├── rust-toolchain.toml    # Pinned Rust version.
└── WAVE{0..4}_*_2026-04-19.md   # Per-wave execution reports.
```

---

## 5. Getting started

### Prerequisites

- **Rust toolchain** — install via [rustup](https://rustup.rs/). The workspace
  pins the toolchain in `rust-toolchain.toml`.
- **Node 20+** and **pnpm 9+** — `corepack enable && corepack prepare pnpm@latest --activate`.
- **Git**. That's it for the preview.

### First run

```bash
git clone https://github.com/dbhavery/aether.git
cd aether

# TypeScript workspace
pnpm install
pnpm -r --if-present typecheck

# Rust workspace (requires rustup)
cargo check --workspace          # green as of Wave 3.5 (2026-04-19)
cargo test --workspace           # green: storage substrate + L5 slice + stubs
cargo test -p aether-l5-policy   # 18 tests on the first L5 logic slice
cargo test -p aether-storage     # 8 tests incl. 3 SQLite integration tests
```

If any of these fail on a clean clone, please open a Bug report — the wave
reports assume they all pass on stable Rust.

### Where to start reading

1. `planning/00_VISION_AND_GUARDRAILS.md` — start here. This file is doctrine.
2. `planning/01_product_doctrine.md` — hard rules for the product family.
3. `planning/plans/00_ORCHESTRATION_MAP.md` — how the layers fit together.
4. `planning/plans/implementation_prep/` — interface packs, event contracts,
   schema, and test matrix. These are the concrete contracts the code
   materializes.
5. `WAVE3_EXECUTION_REPORT_2026-04-19.md` and `WAVE4_EXECUTION_REPORT_2026-04-19.md`
   — what was done last, with honest deferrals called out.
6. `docs/REPO_TOUR.md` — a short guided walk through the directories.

---

## 6. Roadmap

See [ROADMAP.md](ROADMAP.md) for the full list. The next three meaningful
moves, in priority order:

1. **L5 durable persistence** — introduce `SqliteGrantLedger` +
   `SqliteAuditStore` behind the existing ledger / audit traits, flip
   L5 onto them behind a feature flag first, then as default. Add
   migration `0002_audit_chain.sql` for hash-chain + HMAC. This is the
   real follow-up to Wave 3.5.
2. **An L1 or L4 first-logic slice** — either unblocks a visible end-to-end
   demo path: L1 turn FSM, or L4 provider adapter + policy gate.
3. **Community demo slice** — smallest runnable surface that exercises
   L5, the storage substrate, and one engine slice.

Wave 4.1 (layer-boundary enforcement) landed 2026-04-19 — see
[`tools/lint-layer-boundaries/`](tools/lint-layer-boundaries/) and
`WAVE4_1_EXECUTION_REPORT_2026-04-19.md`.

---

## 7. Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the long version. Short version:

- **Docs, tests, and tooling PRs** are the friendliest entry points.
- **Engine logic** should be scoped to a single layer and produce a wave
  execution report alongside the code.
- **Planning doc changes** require extra care: `planning/00_VISION_AND_GUARDRAILS.md`
  and `planning/01_product_doctrine.md` are doctrine — do not edit without
  prior discussion.
- **Never bypass L5** for any side-effectful action. If you need a new
  capability, add it to the L5 contract, not around it.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

---

## 8. Guardrails (short form)

Full list: `planning/00_VISION_AND_GUARDRAILS.md`. In summary:

1. **Seven-layer architecture is non-negotiable.** No collapsing layers into
   each other "for convenience."
2. **L5 is the single writer for side effects.** All file I/O, network,
   subprocess, and tool execution goes through `packages/l5-policy`.
3. **No uncontrolled remote dependence.** The system must remain useful in
   degraded or offline modes.
4. **No "just a chat app" pivot.** Any chat UI is a skin on top of the full
   companion stack.
5. **No ad-hoc cross-package dependencies.** Packages depend only along
   approved directions, enforced by `tools/lint-layer-boundaries/`.
6. **Docs-first for significant changes.** Architecture moves land in
   `planning/` before they land in code.

---

## 9. Security & reporting

Please see [SECURITY.md](SECURITY.md) for how to report vulnerabilities
responsibly. Do **not** file public issues for security problems.

---

## 10. License

Aether Community Edition is released under the [MIT License](LICENSE).
