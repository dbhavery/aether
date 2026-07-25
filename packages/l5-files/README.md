# aether-l5-files — L5 file-workflow capability surface

> **Status (Wave 10A, 2026-04-30):** Trait + types defined; default backend (`StdFsExecutor`) is a real `tokio::fs`-backed implementation under the `std-fs` feature. Mirrors the playwright graduation that landed in `aether-l5-browser` the day prior.

This crate is the L5-gated file-workflow surface for Companion. It is not a *new* policy layer; it plugs additively into `aether_l5_policy::Capability` (variants `FilesRead`, `FilesCreate`, `FilesEdit`, `FilesRenameMove`, `FilesDelete`, `FilesBulkOp` already exist in L5).

## Surface

- `FilesExecutor` (`src/executor.rs`) — the object-safe async trait every backend implements. Methods: `read`, `create`, `edit`, `rename`, `delete`, `grep`.
- Value types (`src/types.rs`) — `GrepHit`, `ScopeAllowlist`, `FilesExecError`.
- `capability_for_method` (`src/capability_map.rs`) — maps method names to `aether_l5_policy::Capability` variants. The integration point where future Tauri commands check L5 policy **before** invoking the executor.
- `StdFsExecutor` (`src/std_fs_stub.rs`, `std-fs` feature) — default backend. Real `tokio::fs` implementation: canonicalize-then-authorize, atomic write-to-sibling-tempfile + rename for `create`/`edit`, files-only `delete`, non-recursive substring `grep`. Self-degrades to `BackendDisabled` when called from a thread with no Tokio runtime (synchronous test harnesses).

## Features

- `default = []` — ships the trait + types + capability map only.
- `std-fs` — additionally compiles the real `StdFsExecutor` and pulls `tokio` (features `fs`, `io-util`, `rt`).

## Wiring contract

L5 is the single writer for side effects (CLAUDE.md §1.5). The executor itself does NOT perform any policy check. Call sites:

1. Resolve a `Capability` via `capability_for_method(method_name)`.
2. Ask `aether_l5_policy::PolicyEngine` for a `Decision::Allow`.
3. Only on `Allow`, invoke the matching method on a `Arc<dyn FilesExecutor>`.

`grep` deliberately maps to `FilesRead` rather than a separate capability — a live grep is a read-side operation that returns matching lines without mutating anything, so anything `FilesRead` already permits is already greppable. (Mirrors the `navigate → BrowserOpen` consolidation in `aether-l5-browser`.)

## Scope model

**Explicit allowlist** (locked T1.3 §5.2). The approved scope is the set of directory roots the user explicitly granted via the existing approval framework. The `ScopeAllowlist` type carries those roots and exposes `is_within_scope(&Path) -> bool` for cheap, I/O-free policy-evaluation lookups. No glob-pattern whitelists; no implicit project-tree expansion.

Real backends MUST canonicalize paths before calling `is_within_scope` so a symlink inside a root cannot smuggle an outside-scope target through the check.

## Approval mode by autonomy preset

| Preset | Read / Grep | Create / Edit | Delete / Rename | Outside scope |
|---|---|---|---|---|
| Observer | Deny | Deny | Deny | Deny |
| Assistant | Ask | Ask | Ask | Deny |
| Operator | Auto (in scope) | Auto (in scope) | Ask | Deny |
| Power User | Auto + per-session grants | Auto + per-session grants | Ask + per-session grants | Per-session grant only |

## Hard rules

- **Outside-scope writes are Deny** in Observer / Assistant / Operator. There is no escalation path in those presets — the user must either grant the directory or switch to Power User.
- **Power User outside-scope grants are per-session only.** They do not persist across app restarts.
- **`FilesDelete` and `FilesRenameMove` never go Auto.** Even in Operator inside approved scope, both stay Ask. The cost of an unintended delete or rename is too high to fold into the auto path.
- **No symlink traversal across scope boundaries.** Implementation PRs must canonicalize before authorization checks.
- **No credential persistence.** OS keychain / secret-file handling is out of scope for T1.3 (locked §5.4).

## Backend

`tokio::fs` (native async). Atomic write semantics use a write-to-sibling-tempfile + `tokio::fs::rename` pattern; the tempfile name is `<final>.aether-tmp.<pid>.<nanos>` so concurrent writers in the same parent dir do not collide and best-effort cleanup deletes the tempfile on either tempfile-write or rename failure. `grep` is a streaming line scanner (`tokio::fs::File` + `BufReader::lines()`) doing substring match — regex is deferred until a regex crate enters the workspace deps.

## What this crate does NOT do

- Recursive directory walks. `grep` only inspects files DIRECTLY under its `root` argument. A recursive variant would need an explicit max-depth cap and a per-entry allowlist re-check on symlink crossings; both expand the threat surface beyond this slice.
- Directory deletion. `delete` is files-only; calling it on a directory returns a typed error.
- Tauri commands. The Tauri surface (`files_*` commands) was wired in a separate single-layer session under `apps/desktop/` (`3ffe041..b1b0447`).
- New approval modes. `ApprovalScope` ("Ask once per session / task") and "Draft only" land in `aether-l5-policy` directly per T1.3 §2.3.
- File search indexing. `grep` is a live-scan capability; persistent indexing is a separate later slice.

## References

- `ARCHITECTURE.md` — the L5 policy layer, file capability, and the approved browser/file workflow.
- `ARCHITECTURE.md` + `docs/adr/` — autonomy preset framework + risk classes; the "Power User / Builder" preset governs the per-session-grant rules above.
- `aether_l5_policy::Capability` — the additive surface this crate plugs into. The file-related variants already live there.
