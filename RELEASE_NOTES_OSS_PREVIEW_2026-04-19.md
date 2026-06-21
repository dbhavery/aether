# Free Aether — Community Edition

## OSS Preview 0 — `v0.1.0-oss-preview.0` (2026-04-19)

This is the first public preview tag of Free Aether — Community Edition. It
is **architecture-forward and intentionally incomplete**: the doctrine,
workspace, governance, and the first real slice of the policy engine are in
place; almost everything user-facing is not. Treat this as an invitation to
read the architecture and contribute to it, not as a runnable product yet.

---

## 1. Overview

Aether is a **local-first, desktop-native AI companion** built around a
seven-layer architecture:

| Layer | Name          | Responsibility                                          |
|-------|---------------|---------------------------------------------------------|
| L1    | Interaction   | Turn FSM, reflex classifier, STT/TTS adapters, timing   |
| L2    | Memory        | Local memory kernel, embeddings, provenance             |
| L3    | Presence      | Avatar scheduler, behavior frames, rendering surface    |
| L4    | Router        | Model / tool router (local + remote providers)          |
| L5    | **Policy**    | Non-bypassable authorization gate, audit, grants, BYOK  |
| L6    | Persona       | YAML → compiled persona artifacts, hot-reload           |
| L7    | Trust UX      | Onboarding, approvals, posture banners                  |

Shared infrastructure (`event-bus`, `storage`, `telemetry`, `types`,
`ui-kit`, `media-engine`) sits underneath. Every side-effectful action
routes through **L5** — there is no back door. This preview ships that
spine and the first real logic inside L5.

Full vision and guardrails live in
[`planning/00_VISION_AND_GUARDRAILS.md`](planning/00_VISION_AND_GUARDRAILS.md);
product doctrine in [`planning/01_product_doctrine.md`](planning/01_product_doctrine.md).

---

## 2. What's in this preview

### Doctrine and plans
- `planning/00_VISION_AND_GUARDRAILS.md` — canonical vision; sits above
  every other planning file.
- `planning/01_product_doctrine.md` + seventeen numbered spec files
  (`02_…18_`) covering family, UX, architecture, memory, avatar, trust,
  tiers, updates, tech stack, persona schema, and model router.
- `planning/plans/` — per-layer system designs + interface packs +
  `event_contracts_master.md` + `sqlite_schema_pack.md` +
  `test_matrix_master.md`.
- Five control-plane decisions locked in
  `DECISION_LOCK_PASS_2026-04-18c.md`.

### Repository and workspace (Waves 0 – 2)
- Cargo workspace with 11 member crates; pnpm workspace with three TS
  packages.
- `tools/lint-layer-boundaries/`, `tools/lint-policy-bypass/`,
  `tools/ts-bindings-gen/` —
  governance scaffolds (rules activated in future waves).
- `.github/CODEOWNERS` with per-layer ownership lines.

### L5 policy engine — first logic slice (Wave 3)
- `packages/l5-policy/` carries a real five-stage evaluator with:
  - in-memory grant ledger + audit store,
  - audit-before-Allow invariant,
  - typed decisions (`Allow`, `Deny`, `Ask`, `DraftOnly`, `NeedsUpgrade`),
  - 18 tests including the 10-item integration slice in
    `packages/l5-policy/tests/engine_slice.rs`.

### Engine stub shells (Wave 4)
- `packages/l1-interaction/`, `packages/l2-memory/`,
  `packages/l3-presence/`, `packages/l4-router/`,
  `packages/l6-persona/`, `packages/l7-trust/` — each with traits,
  core enums, error types, and a smoke test. Logic lands in future
  waves; the trait surface is deliberate.

### Storage substrate (Wave 3.5)
- `packages/storage/` now wires `rusqlite` (bundled — no system SQLite
  required).
- `open_with_migrations(path)` opens a database and runs the drafted
  DDL in `migrations/0001_init.sql` (policy_grants, policy_audit_log
  with append-only triggers, policy_audit_checkpoints, cost_counters,
  schema_migrations bookkeeping).
- Three integration tests prove the migration runner works, that the
  append-only trigger rejects `DELETE`, and that warm reopens are
  idempotent.
- **L5 still uses in-memory backends today** — see §3 below.

### OSS launch pack
- `README.md`, `LICENSE` (MIT), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`
  (Contributor Covenant v2.1 by reference), `SECURITY.md`,
  `SUPPORT.md`, `ROADMAP.md`, `docs/REPO_TOUR.md`.
- `.github/ISSUE_TEMPLATE/{bug_report,feature_request,docs_request}.md`
  + `config.yml`, and `.github/PULL_REQUEST_TEMPLATE.md`.

### CI
- `.github/workflows/ci.yml` runs four jobs on push / PR to `dev` and
  `master`:
  - `rust`: `cargo fmt --check`, `cargo check --workspace`,
    `cargo clippy` (advisory), `cargo test --workspace`.
  - `typescript`: `pnpm -r --if-present typecheck`.
  - `governance`: required launch-pack files exist; coarse secret
    tripwire.
  - `legacy-python`: the frozen v1.0 Python tree runs
    `continue-on-error: true` so its breakage never blocks Rust / TS.

### Tests green on `v0.1.0-oss-preview.0`
- `cargo check --workspace` ✓
- `cargo test --workspace` ✓ (39 tests total)
- `cargo fmt --all --check` ✓
- `pnpm -r --if-present typecheck` ✓

---

## 3. What's NOT in this preview

Stated plainly so expectations are calibrated:

- **No durable L5 persistence.** The storage substrate (§2 above) is
  real, but L5's `GrantLedger` and `AuditStore` are still in-memory.
  L5 state is lost on process exit. Flipping L5 onto SQLite backends
  is an explicit future wave.
- **No first-logic slices for L1 / L2 / L3 / L4 / L6 / L7.** Those
  crates ship trait surfaces and smoke tests; logic lands layer by
  layer in future waves.
- **No runnable desktop app.** `apps/desktop`, `apps/guest`, and
  `apps/docs-site` are scaffolds only.
- **No LLM / STT / TTS / avatar pipeline wired up.** The engine stubs
  declare the right traits; none of the I/O paths are hooked up.
- **No hash-chain + HMAC audit triggers.** The append-only invariant
  is enforced today by SQL triggers; cryptographic chaining is a
  follow-on migration (`0002_audit_chain.sql`, future wave).
- **No activated layer-boundary bans.** `tools/lint-layer-boundaries/`
  is scaffolded; enforcement turns on in Wave 4.1 (the next wave).
- **No production-ready security hardening.** The secrets scan for
  this preview was a best-effort internal sweep; a dedicated
  third-party scanner run before public traffic is recommended.
- **No `.env`-based config.** All API keys go through the OS keyring
  (Windows Credential Manager / macOS Keychain / Secret Service on
  Linux). `.env.example` is provided for developers who want env-var
  fallback.

If you need a runnable chat app today, this is the wrong project. If
you want to help design and stress-test the architecture for a
companion that runs offline, you are welcome.

---

## 4. How to try it

### Prerequisites

- **Rust toolchain** — install via [rustup](https://rustup.rs/).
  `rust-toolchain.toml` pins the channel; `rustup show` should
  auto-install on first `cargo` run.
- **Node 20+** and **pnpm 9+**:
  `corepack enable && corepack prepare pnpm@latest --activate`.
- **Git**.

### Clone

```bash
git clone https://github.com/dbhavery/aether.git
cd aether
```

### TypeScript workspace

```bash
pnpm install
pnpm -r --if-present typecheck
```

### Rust workspace

```bash
cargo fmt --all --check           # style gate (CI)
cargo check --workspace           # green
cargo test --workspace            # green, ~39 tests
cargo test -p aether-l5-policy    # 18 tests on the first policy slice
cargo test -p aether-storage      # 5 unit + 3 integration (SQLite)
```

### Exploring the code

Read order:

1. [`README.md`](README.md) — section 3 has the honest status snapshot.
2. [`planning/00_VISION_AND_GUARDRAILS.md`](planning/00_VISION_AND_GUARDRAILS.md) — doctrine.
3. [`planning/01_product_doctrine.md`](planning/01_product_doctrine.md) — hard rules.
4. [`planning/plans/00_ORCHESTRATION_MAP.md`](planning/plans/00_ORCHESTRATION_MAP.md) — layer map.
5. [`docs/REPO_TOUR.md`](docs/REPO_TOUR.md) — fifteen-minute guided walk.
6. `packages/l5-policy/src/lib.rs` → `engine.rs` →
   `tests/engine_slice.rs` — the richest code in the repo.
7. `WAVE3_EXECUTION_REPORT_2026-04-19.md` and
   `WAVE3_5_EXECUTION_REPORT_2026-04-19.md` — how Wave 3 and 3.5 got
   here, with honest deferrals.

---

## 5. How to contribute

- [CONTRIBUTING.md](CONTRIBUTING.md) — scoping, branch / commit /
  review expectations, docs-first policy for architecture changes.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — Contributor Covenant v2.1.
- [SECURITY.md](SECURITY.md) — scope, reporting channels
  (GitHub private advisory preferred), disclosure timeline.
- [SUPPORT.md](SUPPORT.md) — where to ask what; what the
  single-maintainer preview promises (and does not).
- [ROADMAP.md](ROADMAP.md) — the priority stack.
- Issue templates cover bugs, feature / architecture proposals, and
  docs fixes. PR template enforces the layer-boundary / L5-single-
  writer / no-private-asset-leak checks.

The most contributor-friendly entry points today:

- Docs fixes and clarifications — anywhere in `planning/`, `docs/`,
  or the root community docs.
- Test expansions — especially `packages/l5-policy/tests/engine_slice.rs`
  and the stub-crate smoke tests.
- Governance tooling — `tools/lint-layer-boundaries/`,
  `tools/lint-policy-bypass/`, and `tools/ts-bindings-gen/`.
- CI improvements — the three active jobs have room to grow.

---

## 6. Next steps

In priority order, per [ROADMAP.md](ROADMAP.md):

1. **Wave 4.1 — Layer-boundary enforcement.** Activate the bans /
   rules in `tools/lint-layer-boundaries/` now that all six sibling
   engine crates exist. Wire into CI.
2. **L5 durable persistence.** Introduce `SqliteGrantLedger` +
   `SqliteAuditStore` behind the existing ledger / audit traits; flip
   L5 onto them behind a feature flag first, then as default. Add
   migration `0002_audit_chain.sql` for hash-chain + HMAC.
3. **First engine first-logic slice.** Either L1 turn FSM or L4
   provider adapter + L5 gate wire-through — either unlocks a visible
   end-to-end demo path.
4. **Community demo slice.** A single small binary that exercises the
   policy engine, the storage substrate, and one engine slice —
   intended to make the architecture legible in under fifteen minutes.

Further out: L2 memory kernel, L3 presence scheduler, L6 persona
compiler, L7 trust flows, Tauri shell (apps/desktop), guest mode
(apps/guest), docs site (apps/docs-site). These slot in once the
lower-numbered items land.

---

## 7. License

MIT © 2026 Don Havery — see [LICENSE](LICENSE).

---

## 8. Known limitations in this tag

- `cargo clippy --workspace -- -D warnings` is advisory in CI because
  of pre-existing `missing_docs` warnings; tightening is a small
  future PR.
- Wave execution reports use absolute `file:///C:/Users/dbhav/...`
  paths internally — a mild Windows-username disclosure. Cosmetic
  cleanup is a candidate for a future docs pass.
- Secret scanning for this preview was best-effort; a dedicated run
  (e.g. `gitleaks`) is recommended before the repo sees significant
  public traffic.

None of the above are blockers for exploring or contributing to the
preview.
