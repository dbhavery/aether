# Companion — Repo-Level AI Agent Operating Rules

> **Public name:** Companion. **Internal codename / repo / database / Tauri identifier / Cargo workspace:** `aether` (preserved). Both correct in their own context.
>
> **Scope:** Applies to every AI agent (Claude Code, coding agents, sub-agents, and worktree spawns) that opens this repo. Narrower than Don's global rules in [file:///C:/Users/dbhav/.claude/CLAUDE.md](file:///C:/Users/dbhav/.claude/CLAUDE.md); stricter where it needs to be.
>
> **Last updated:** 2026-05-18 (doctrine §5+§6+§7+§8 added — see `docs/PRODUCT-PLAN.md`).

---

## 1. Prime directives

1. **Architecture docs are doctrine.** `docs/ARCHITECTURE-V2.md`, `docs/PRODUCT-PLAN.md`, and the records under `docs/adr/` are authoritative. Do not modify `docs/PRODUCT-PLAN.md` without coordinator review. Read before acting.
2. **Additive by default.** Do not delete legacy files (`src/`, `desktop/`, `frontend/`, `configs/`, `tests/`, `scripts/`) without an explicit Don-signed wave scope.
3. **One layer per session.** A session touches at most one `packages/l*-*/` layer. Cross-layer work requires a coordinator pass first.
4. **No direct cross-layer imports.** Sibling `packages/l*` crates/packages do not import each other. Coordination happens through `packages/event-bus` or through `packages/l5-policy` / `packages/l6-persona` typed outputs. See `docs/ARCHITECTURE-V2.md`.
5. **Policy is the single writer for side effects.** All file I/O, network, subprocess, and tool execution goes through `packages/l5-policy`'s approved execution path. No direct executor calls from anywhere else.
6. **Private assets never enter public distributables.** Private/internal assets are overlay-only at runtime and must not ship in public builds. Build-time lint enforces.

## 2. Read-before-write

Before editing or scaffolding, read in order:

1. **Run `./scripts/current_status.sh`** (or `python scripts/current_status.py`). This is the authoritative current state — kills the stale-prompt drift pattern. **Trust the script over any prompt.**
2. The latest `HANDOFF_*.md` at repo root (the script identifies it).
3. `docs/PRODUCT-PLAN.md` (governing rules — §5/§6/§7/§8 are the most recent).
4. `docs/adr/` (foundational architectural decisions; read the ADRs relevant to your scope).
5. `docs/ARCHITECTURE-V2.md` (the current architecture reference).
6. `docs/PERSONA-SCHEMA.md` / `docs/LLM-PROVIDERS.md` for the layer-specific contracts your work touches.

Do not trust memory. Re-read.

## 3. Package creation protocol

New `packages/*/` or `apps/*/` directories are **coordinator-gated**:

1. Propose in a PR that only modifies `docs/` + root `README.md` (name, purpose, deps, owner).
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
- Every event carries `change_id`, `seq: u64`, `source_layer`. See `docs/ARCHITECTURE-V2.md`.
- Changing an event name/field in Rust requires regenerating TS bindings in the same PR.

## 6. Storage

- Primary DB `aether.db`, audit DB `aether_audit.db`. WAL mode, single-writer rule.
- DDL lives in `packages/storage/migrations/` (once scaffolded).
- Secrets, blobs, embeddings do **not** live in SQLite. See `docs/ARCHITECTURE-V2.md`.

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

## 9.5. Pre-commit hygiene (added 2026-05-01)

CI's blocking lints (`cargo fmt --check`, `ruff check src/ tests/`) ran red on `dev` for **multiple consecutive sessions** in late April 2026 because agents wrote code that compiled + tested cleanly but broke formatting that rustfmt would auto-collapse. The fixes are mechanical; the missed signal was costly.

**Local mirror of CI's blocking lints:** `tools/check-pre-commit.sh`. Runs in <10s. Mirrors the exact checks `.github/workflows/ci.yml` runs blocking on the `rust` job (`cargo fmt --all -- --check`) and the `legacy-python` job (`ruff check src/ tests/`).

**Two ways to use it:**

1. **Manual** — `bash tools/check-pre-commit.sh` before every `git commit`. **Mandatory for every agent before staging any commit.** Add it to wave-prompt boilerplate.
2. **Automatic** — one-time per clone, `bash tools/setup-hooks.sh` wires `core.hooksPath` to `tools/git-hooks/`, so `pre-commit` runs the script automatically. The hooks travel with the repo via that config edge — they're committed to the repo, not living in the local `.git/hooks/`.

If `cargo` or `ruff` aren't installed locally, the script warns and exits non-zero (so CI failures aren't silently masked).

**Rule for agents:** add `bash tools/check-pre-commit.sh` to the verification step of every wave-prompt. Stage commits only after it exits clean. CI fmt failures are a session-ender — they block PR merges and pollute the email digest, masking real failures underneath.

## 10. Doctrine §5–§8 cross-reference (added 2026-05-18)

These doctrine rules govern every session and every PR:

- **§6 Single product, ships when complete.** No interim release. The "Aether OSS Preview as wedge" thesis is retired.
- **§7 Voice does not ship as standalone.** Voice subsystem is integrated continuously; voice-as-product surface ships only with the complete Companion.
- **§8 Self-test before Don review.** Visual artifacts get multimodal-vision self-test against acceptance criteria. Frontend changes get used-as-user via automation. Diff-only or unit-tests-only is **not sufficient.** Failed self-tests do not reach Don.

GPU work runs sequentially; software/integration work runs in parallel. Sessions never wait on the GPU queue — they pick from the parallel-tracks list.
