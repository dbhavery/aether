# Aether — Repo-Level AI Agent Operating Rules

> **Scope:** Applies to every AI agent (Claude Code, coding agents, sub-agents, and worktree spawns) that opens this repo. Narrower than Don's global rules in [file:///C:/Users/dbhav/.claude/CLAUDE.md](file:///C:/Users/dbhav/.claude/CLAUDE.md); stricter where it needs to be.
>
> **Last updated:** 2026-04-19 (Wave 1).

---

## 1. Prime directives

1. **Planning corpus is doctrine.** Everything under `planning/` is authoritative. Do not modify `planning/01_product_doctrine.md` without coordinator review. Read before acting.
2. **Additive by default.** Do not delete legacy files (`src/`, `desktop/`, `frontend/`, `configs/`, `tests/`, `scripts/`) without an explicit Don-signed wave scope.
3. **One layer per session.** A session touches at most one `packages/l*-*/` layer. Cross-layer work requires a coordinator pass first.
4. **No direct cross-layer imports.** Sibling `packages/l*` crates/packages do not import each other. Coordination happens through `packages/event-bus` or through `packages/l5-policy` / `packages/l6-persona` typed outputs. See `planning/planning/monorepo_plan_draft.md` §4.1 and `planning/plans/implementation_prep/event_contracts_master.md`.
5. **Policy is the single writer for side effects.** All file I/O, network, subprocess, and tool execution goes through `packages/l5-policy`'s approved execution path. No direct executor calls from anywhere else.
6. **Private assets never enter public distributables.** Isabelle-tagged assets are overlay-only at runtime for Don's profile. Build-time lint enforces.

## 2. Read-before-write

Before editing or scaffolding, read in order:

1. `planning/HANDOFF_2026-04-18.md`
2. `planning/DECISION_LOCK_PASS_2026-04-18c.md`
3. `planning/OPEN_QUESTIONS.md` (search for `[DECIDED` locks relevant to your scope)
4. `planning/planning/monorepo_plan_draft.md`
5. The layer-specific plan under `planning/plans/L*_*.md` and `planning/plans/implementation_prep/L*_interface_pack.md`

Do not trust memory. Re-read.

## 3. Package creation protocol

New `packages/*/` or `apps/*/` directories are **coordinator-gated**:

1. Propose in a PR that only modifies `planning/` + root `README.md` (name, purpose, deps, owner).
2. Coordinator (Don) approves.
3. Separate PR scaffolds the package skeleton: manifest entry, empty lib target, README, CODEOWNERS line. Zero logic.
4. Only then may implementation PRs land.

Unilateral `packages/*/` creation is a block-the-PR violation.

## 4. Boundary and governance tooling

These live under `tools/` and are referenced from CI when CI lands:

- `tools/lint-layer-boundaries/` — Rust `cargo-deny` + TS ESLint rule enforcing §1.4.
- `tools/lint-policy-bypass/` — rejects direct executor calls outside `packages/l5-policy`.
- `tools/lint-private-asset-leak/` — fails builds if Isabelle-tagged content appears in public distributable manifests.
- `tools/ts-bindings-gen/` — `ts-rs`/`specta` codegen from Rust structs; TS must never be hand-authored where Rust is canonical.

Wave 1 ships scaffolds + permissive configs; Wave 3+ tightens to blocking.

## 5. Events and types

- Rust enums (`L1Event | L2Event | ...`) are the canonical event surface. TS mirrors are generated.
- Every event carries `change_id`, `seq: u64`, `source_layer`. See `planning/plans/implementation_prep/event_contracts_master.md`.
- Changing an event name/field in Rust requires regenerating TS bindings in the same PR.

## 6. Storage

- Primary DB `aether.db`, audit DB `aether_audit.db`. WAL mode, single-writer rule.
- DDL lives in `packages/storage/migrations/` (once scaffolded).
- Secrets, blobs, embeddings do **not** live in SQLite. See `planning/plans/implementation_prep/sqlite_schema_pack.md` §1.

## 7. Legacy coexistence

The v1.0 Python tree (`src/`, `desktop/`, `frontend/`, etc.) remains in place during Waves 1–4. It is:

- Not imported by any Rust or TS workspace member.
- Not covered by Rust/TS workspace checks.
- Ported capability-by-capability by X2 (Isabelle) and X4 (v1 content) during later waves.
- Retired only after parity is verified.

Do not "clean up" legacy paths opportunistically.

## 8. Clickable links

Every user-facing path in an agent response must be a bare `file:///C:/...` or `https://...` URL, forward slashes only. No backticks, no markdown link syntax, no backslashes. Inherited from Don's global rule; restated here because it gets violated routinely.

## 9. When in doubt

- Stop and report, don't guess.
- A partial scaffold with a clear TODO beats fake completeness.
- Flag blockers in the wave execution report, not inline in code.
