# Aether: Community Edition (preview)

A design and partial build of a local-first AI assistant in which every action
that touches files, runs commands or calls a remote model has to pass a policy
gate first, and every decision is written to an audit log that cannot be edited
without detection.

This is a pre-0.1 preview. There is no end-to-end app yet, and interfaces will
change.

---

## The problem

A personal assistant with access to files, commands and cloud models can act without asking the user, and it usually leaves no record the user can trust afterward. Most assistants also send the user's data to remote services
by default.

## How it solves it

- **One policy gate for every action.** A policy engine evaluates each request. The possible decisions are allow, ask, deny, draft-only and needs-upgrade. Grants can be issued and revoked, and "ask" opens an approval
  ticket for the user.
- **Audit before action.** An audit row is written before any allow decision is
  returned. If the write fails, the action does not go ahead.
- **A log that shows tampering.** In the SQLite build, each audit row is
  chained to the previous row by a SHA-256 hash and signed with HMAC-SHA256.
  A verify call walks the log and reports edited rows, inserted or deleted
  rows, a rolled-back chain tip, or the wrong key. SQLite triggers also reject
  `UPDATE` and `DELETE` on the audit table.
- **Local first.** Data the assistant keeps about the user, such as memory and persona state, is meant to stay on the
  user's machine, with remote calls made only through the gate.

**What the gate does not cover yet.** The older Python tree in this repository
(`src/`, `desktop/`, `frontend/`) has a push-to-talk voice loop, memory, an
avatar process and clients for cloud models (Anthropic and Google Gemini).
That code does not call the policy gate. It reads and writes files, starts processes and sends requests to cloud APIs directly. The same is true of the
customer-assistant demo under `apps/customer-assistant/`. Only the Rust
workspace goes through the gate today.

## Who it helps

- Developers building local assistants or agents that must ask before they act
  and keep an audit trail.
- People who want an assistant that keeps its data on the user's machine.
- Anyone studying how to put a policy check and a tamper-evident log in front
  of an agent's actions.

---

## Technical details

### Stack

- **Rust workspace** (toolchain pinned in `rust-toolchain.toml`): the policy
  engine, storage, the engine crates and a command-line demo. SQLite through
  `rusqlite` with the bundled library, `sha2` and `hmac` for audit sealing.
- **TypeScript workspace** (pnpm): shared types and UI primitives, typecheck
  only.
- **Legacy Python tree** (Python 3.13): the earlier voice assistant, kept in
  place while its parts are ported into the Rust layers. It is not routed
  through the policy gate (see above).

### Architecture

The design splits the assistant into layers, and each layer is a separate crate with explicit contracts:

| Layer | Name        | Responsibility                                         |
|-------|-------------|--------------------------------------------------------|
| L1    | Interaction | Turn state machine, reflex classifier, STT/TTS adapters |
| L2    | Memory      | Local memory kernel, embeddings, provenance            |
| L3    | Presence    | Avatar scheduler, behavior frames                      |
| L4    | Router      | Model and tool router (local and remote providers)     |
| L5    | Policy      | Authorization gate, audit, grants, BYOK cost counters  |
| L6    | Persona     | Persona profiles compiled into typed artifacts         |
| L7    | Trust UX    | Onboarding, approvals, posture banners                 |

Shared crates (`event-bus`, `storage`, `telemetry`, `media-engine`) sit
underneath. In the Rust workspace, side-effecting actions are meant to go
through L5. A layer-boundary linter in CI rejects dependencies between crates
that the architecture does not allow.

### Status

What is built in the Rust workspace (on `master`):

| Area | State |
|------|-------|
| L5 policy engine | Built. Five-stage evaluator; grants with revoke; approval tickets; audit before allow. |
| L5 storage | In-memory by default. SQLite grant ledger and audit store behind the `sqlite-backend` feature. |
| Audit sealing | Built behind `sqlite-backend`: SHA-256 hash chain, HMAC-SHA256 per row, chain-head record, `verify_chain()`. |
| Storage migrations | `0001_init`, `0002_audit_chain`, `0003_audit_seal`, with append-only triggers on the audit table. |
| L1 interaction | First slice built: a turn state machine that calls the L5 gate, then dispatches to a router or stops. |
| L6 persona | First slice built: a deterministic compiler from a persona profile to compiled artifacts. |
| L2, L3, L4, L7 | Traits and enums with smoke tests. No working logic yet. |
| BYOK cost caps | Types and events defined in L5. Not enforced by the engine yet. |
| Command-line demo | `apps/l1-cli` runs one turn through L1 and L5 with a stub router. It always uses in-memory storage. |

What is not built:

- No end-to-end assistant. No model, STT, TTS or avatar is wired to the Rust
  layers; the demo's router returns a canned reply and does no inference.
- No desktop app on `master`. The Tauri shell is on the `dev` branch.
- The legacy Python tree and the customer-assistant demo bypass the gate.
- Audit sealing does not protect against theft of the signing key, root access
  on the host, or verification by a third party without the key.

**Branches.** `master` is the public snapshot this README describes. Work in
progress is on `dev`, which also carries the Tauri desktop shell under
`apps/desktop/`. Some ADRs name paths that exist only on that branch.

### Repository layout

```
aether/
├── packages/              # Cargo and pnpm workspace members
│   ├── l5-policy/         # Policy engine, grants, audit, sealing
│   ├── l5-policy-ts/      # Hand-written TS mirror of stable L5 types
│   ├── storage/           # SQLite substrate and migrations
│   ├── event-bus/         # Typed envelopes
│   ├── telemetry/         # Structured logging (stub)
│   ├── media-engine/      # Media I/O surface (stub)
│   ├── l1-interaction/    # Turn state machine slice
│   ├── l6-persona/        # Persona compiler slice
│   ├── l2-memory/ l3-presence/ l4-router/ l7-trust/   # Traits only
│   ├── types/             # Shared TS types
│   └── ui-kit/            # Shared TS UI primitives
├── apps/
│   ├── l1-cli/            # Command-line demo of one turn through L1 and L5
│   └── customer-assistant/  # Python support-bot demo (does not use L5)
├── tools/                 # Layer-boundary linter and other governance tools
├── infra/, research/, docs/
├── src/, desktop/, frontend/, configs/, personas/, scripts/, tests/
│                          # Legacy Python tree
├── Cargo.toml             # Rust workspace manifest
├── pnpm-workspace.yaml    # TS workspace manifest
└── rust-toolchain.toml    # Pinned Rust version
```

### Prerequisites

- Rust through [rustup](https://rustup.rs/). The toolchain is pinned in
  `rust-toolchain.toml`.
- Node 20 or later and pnpm 9 or later (`corepack enable`).
- Python 3 for the layer-boundary linter.

### Build and test

```bash
git clone https://github.com/dbhavery/aether.git
cd aether

# Rust workspace (no network needed after dependencies download)
cargo fmt --all -- --check
cargo check --workspace --all-targets
cargo test --workspace --all-targets

# Policy engine with SQLite storage and audit sealing
cargo test -p aether-l5-policy --features sqlite-backend

# Layer-boundary lint
python tools/lint-layer-boundaries/check.py

# TypeScript workspace
pnpm install
pnpm -r --if-present typecheck
```

What the tests check:

- `aether-l5-policy`: the evaluator's decisions and audit-before-allow, plus issuing and revoking grants. With `sqlite-backend`: grants and audit rows survive a restart, the
  append-only triggers reject edits, and `verify_chain()` passes on a clean log
  and fails on a tampered payload, a rolled-back chain tip and the wrong key.
- `aether-storage`: migrations create every expected table, the append-only
  trigger rejects `DELETE`, and reopening a database is idempotent.
- `aether-l1-interaction`: a turn moves through the right states for each
  policy decision, including against the SQLite backends.
- The other engine crates: smoke tests only.

CI (`.github/workflows/ci.yml`) runs the Rust checks and tests, the
layer-boundary lint, the TypeScript typecheck, a required-files check and a
secrets grep. It also runs the legacy Python unit tests as a non-blocking job.

### Try the command-line demo

`apps/l1-cli` is a small stdin loop that sends one turn through the real L1
state machine and the real L5 gate, with a stub router that does no inference.

```bash
cargo run -p aether-l1-cli
```

```
aether> read /tmp/x
  turn-id      : turn-1
  final-state  : Completed
  state-trace  : Idle -> AwaitingPolicyApproval -> RouterDispatched -> Completed
  policy       : Allow
  route        : tier=local-full provider=reflex-stub
  response     : [local-full] heard you: read /tmp/x

aether> shell ls
  turn-id      : turn-2
  final-state  : PolicyDenied
  state-trace  : Idle -> AwaitingPolicyApproval -> PolicyDenied
  policy       : Deny
  blocked      : policy denied

aether> write /tmp/x
  turn-id      : turn-3
  final-state  : AwaitingPolicyApproval
  state-trace  : Idle -> AwaitingPolicyApproval
  policy       : Ask
  blocked      : awaiting user approval (Ask ticket open)
```

The full command table is in [`apps/l1-cli/README.md`](apps/l1-cli/README.md).

### Using SQLite storage for L5

The default build keeps grants and audit rows in memory, and they are lost on
exit. To keep them in SQLite, enable the `sqlite-backend` feature on
`aether-l5-policy`:

```rust
use aether_l5_policy::{DefaultPolicyEngine, DurableBackends, EngineConfig, InMemorySink};
use std::sync::Arc;

let backends = DurableBackends::open("./aether.db")?;
let engine = DefaultPolicyEngine::new(
    EngineConfig::wave3_default(persona_id),
    backends.ledger.clone(),
    backends.audit.clone(),
    Arc::new(InMemorySink::new()),
);
```

### How audit sealing works

With `sqlite-backend` enabled, each audit row is sealed before it is inserted:

- `event_hash = SHA256(prev_hash || canonical_payload)`, where `prev_hash` is
  the previous row's `event_hash` (a fixed genesis value for the first row).
- `record_hmac = HMAC-SHA256(key, event_hash)`.
- A single `policy_audit_chain_head` row records the current tip.
- `SqliteAuditStore::verify_chain()` walks the log in order and returns
  `AuditVerifyError::ChainBreak` or `HmacMismatch` when a row was changed,
  inserted, removed, the tip was rolled back, or the key is wrong.

The signing key is loaded from, in order:

1. the `AETHER_AUDIT_HMAC_KEY_HEX` environment variable (64 hex characters,
   32 bytes), or
2. a 32-byte file at `<db_path>.hmac.key`, created on first run.

Anyone who can read the key file can re-seal altered history, so the key file
needs the same protection as the database. Root access on the host and remote
attestation are out of scope.

### Where to start reading

1. [`docs/REPO_TOUR.md`](docs/REPO_TOUR.md): a short walk through the
   directories.
2. [`ARCHITECTURE.md`](ARCHITECTURE.md): the layers and the policy gate.
3. [`docs/ARCHITECTURE-V2.md`](docs/ARCHITECTURE-V2.md): architecture detail.
4. [`docs/PRODUCT-PLAN.md`](docs/PRODUCT-PLAN.md): product direction and the
   port plan for the legacy Python tree.
5. [`ROADMAP.md`](ROADMAP.md): planned work.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short:

- Docs, tests and tooling changes are the easiest place to start.
- Engine logic should stay inside one layer.
- Architecture changes need discussion first; see
  [`ARCHITECTURE.md`](ARCHITECTURE.md) and the ADRs under [`docs/adr/`](docs/adr/).
- Do not add a side-effecting action to the Rust workspace that skips L5. If a
  new capability is needed, add it to the L5 contract.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Design rules

The full list is in [`ARCHITECTURE.md`](ARCHITECTURE.md). In summary:

1. Keep the layers separate.
2. L5 is the only path for side effects in the Rust workspace: file I/O,
   network, subprocesses and tool execution.
3. The system must stay useful offline or with remote services degraded.
4. Packages depend on each other only in approved directions, checked by
   `tools/lint-layer-boundaries/`.
5. Significant architecture changes are recorded in `ARCHITECTURE.md` and the
   ADR log before they land in code.

## Security

See [SECURITY.md](SECURITY.md) to report a vulnerability. Do not file public
issues for security problems.

## License

[MIT](LICENSE).
