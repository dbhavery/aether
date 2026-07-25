# Aether — Repo-Level AI Agent Operating Rules

> **Scope:** Applies to every AI agent (Claude Code, coding agents, sub-agents, and worktree spawns) that opens this repo. Narrower than Don's global rules in [file:///C:/Users/dbhav/.claude/CLAUDE.md](file:///C:/Users/dbhav/.claude/CLAUDE.md); stricter where it needs to be.
>
> **Last updated:** 2026-04-19 (Wave 1).

---

## 1. Prime directives

1. **Architecture docs are doctrine.** `ARCHITECTURE.md`, `docs/ARCHITECTURE-V2.md`, `docs/PRODUCT-PLAN.md`, and the ADR log under `docs/adr/` are authoritative. Do not change the product's hard rules without coordinator review. Read before acting.
2. **Additive by default.** Do not delete legacy files (`src/`, `desktop/`, `frontend/`, `configs/`, `tests/`, `scripts/`) without an explicit Don-signed wave scope.
3. **One layer per session.** A session touches at most one `packages/l*-*/` layer. Cross-layer work requires a coordinator pass first.
4. **No direct cross-layer imports.** Sibling `packages/l*` crates/packages do not import each other. Coordination happens through `packages/event-bus` or through `packages/l5-policy` / `packages/l6-persona` typed outputs. See `ARCHITECTURE.md` and the event surface in `packages/event-bus`.
5. **Policy is the single writer for side effects.** All file I/O, network, subprocess, and tool execution goes through `packages/l5-policy`'s approved execution path. No direct executor calls from anywhere else.
6. **Private assets never enter public distributables.** Private/internal assets are overlay-only at runtime and must not ship in public builds. Build-time lint enforces.

## 2. Read-before-write

Before editing or scaffolding, read in order:

1. `ARCHITECTURE.md` — the seven-layer architecture and the non-bypassable gate.
2. `docs/ARCHITECTURE-V2.md` — the current architecture detail.
3. `docs/PRODUCT-PLAN.md` — product direction and hard rules.
4. The ADR log under `docs/adr/` — the locked decisions relevant to your scope.
5. The layer crate you are touching: its `README.md` and `src/lib.rs` under `packages/l*-*/`.

Do not trust memory. Re-read.

## 3. Package creation protocol

New `packages/*/` or `apps/*/` directories are **coordinator-gated**:

1. Propose in a PR that only modifies the architecture docs (`ARCHITECTURE.md` / `docs/`) + root `README.md` (name, purpose, deps, owner).
2. Coordinator (Don) approves.
3. Separate PR scaffolds the package skeleton: manifest entry, empty lib target, README, CODEOWNERS line. Zero logic.
4. Only then may implementation PRs land.

Unilateral `packages/*/` creation is a block-the-PR violation.

## 4. Boundary and governance tooling

These live under `tools/` and are referenced from CI when CI lands:

- `tools/lint-layer-boundaries/` — Rust `cargo-deny` + TS ESLint rule enforcing §1.4.
- `tools/lint-policy-bypass/` — rejects direct executor calls outside `packages/l5-policy`.
- `tools/ts-bindings-gen/` — `ts-rs`/`specta` codegen from Rust structs; TS must never be hand-authored where Rust is canonical.

Wave 1 ships scaffolds + permissive configs; Wave 3+ tightens to blocking.

## 5. Events and types

- Rust enums (`L1Event | L2Event | ...`) are the canonical event surface. TS mirrors are generated.
- Every event carries `change_id`, `seq: u64`, `source_layer`. See the event types in `packages/event-bus`.
- Changing an event name/field in Rust requires regenerating TS bindings in the same PR.

## 6. Storage

- Primary DB `aether.db`, audit DB `aether_audit.db`. WAL mode, single-writer rule.
- DDL lives in `packages/storage/migrations/` (once scaffolded).
- Secrets, blobs, embeddings do **not** live in SQLite. See the migrations under `packages/storage/migrations/` and the storage ADRs in `docs/adr/`.

## 7. Legacy coexistence

The v1.0 Python tree (`src/`, `desktop/`, `frontend/`, etc.) remains in place during Waves 1–4. It is:

- Not imported by any Rust or TS workspace member.
- Not covered by Rust/TS workspace checks.
- Ported capability-by-capability from the upstream codebase and v1 content during later waves.
- Retired only after parity is verified.

Do not "clean up" legacy paths opportunistically.

## 8. Clickable links

Every user-facing path in an agent response must be a bare `file:///C:/...` or `https://...` URL, forward slashes only. No backticks, no markdown link syntax, no backslashes. Inherited from Don's global rule; restated here because it gets violated routinely.

## 9. When in doubt

- Stop and report, don't guess.
- A partial scaffold with a clear TODO beats fake completeness.
- Flag blockers in the wave execution report, not inline in code.
