//! L5 file-workflow capability surface.
//!
//! **Status (Wave 10A, 2026-04-30):** Trait + types are real, plus a
//! capability map and a real `tokio::fs`-backed default backend behind
//! the `std-fs` feature. Default builds still ship the trait + types
//! + capability map only — no async runtime dep.
//!
//! # Surface
//!
//! - [`FilesExecutor`] — object-safe async trait every backend
//!   implements.
//! - [`GrepHit`], [`ScopeAllowlist`], [`FilesExecError`] — the value
//!   types the trait operates on.
//! - [`capability_for_method`] — maps trait method names to existing
//!   variants on [`aether_l5_policy::Capability`]. The integration
//!   point where future Tauri commands check L5 policy BEFORE invoking
//!   the executor.
//! - [`std_fs_stub::StdFsExecutor`] — default backend. Gated behind the
//!   `std-fs` feature; real `tokio::fs` implementation with
//!   canonicalize-then-authorize, atomic write-to-tempfile + rename
//!   for `create`/`edit`, files-only `delete`, and a non-recursive
//!   substring `grep`. Self-degrades to
//!   [`FilesExecError::BackendDisabled`] when called from a thread
//!   with no Tokio runtime.
//!
//! # Layer rules
//!
//! Per CLAUDE.md §1.4 + §1.5, this crate:
//!
//! - extends the existing capability surface in
//!   [`aether_l5_policy`] additively (the file-related variants
//!   `FilesRead`, `FilesCreate`, `FilesEdit`, `FilesRenameMove`,
//!   `FilesDelete`, `FilesBulkOp` already live on
//!   [`Capability`](aether_l5_policy::Capability));
//! - does not perform its own policy check — call sites resolve a
//!   [`Capability`](aether_l5_policy::Capability) via
//!   [`capability_for_method`], ask L5 for `Decision::Allow`, and only
//!   then invoke a method on `dyn FilesExecutor`.
//!
//! # Scope (frozen by Don 2026-04-30)
//!
//! - **Scope model: explicit allowlist** (locked T1.3 §5.2). The
//!   approved scope is the set of directory roots the user explicitly
//!   granted via the existing approval framework. No glob whitelists,
//!   no implicit project-tree expansion. See [`ScopeAllowlist`].
//! - **No credential persistence.** OS keychain / secret-file handling
//!   is out of scope for T1.3 (locked §5.4) and lands in its own
//!   threat-modeled slice.
//! - Outside-scope writes are **Deny** in Observer / Assistant /
//!   Operator presets. Power User may grant outside-scope access on a
//!   per-session basis only.
//! - Approval mode follows the active autonomy preset:
//!   - **Observer** — Deny.
//!   - **Assistant** — Ask (read + grep + edit), Ask (delete / rename).
//!   - **Operator** — Auto for `FilesRead` / `FilesCreate` /
//!     `FilesEdit` / `grep` inside approved scope; `FilesDelete` /
//!     `FilesRenameMove` stay Ask; outside-scope writes Deny.
//!   - **Power User** — additionally permits per-session grants for
//!     outside-scope access.
//!
//! # References
//!
//! - `ARCHITECTURE.md` — the L5 policy layer and the approved browser/file
//!   workflow.
//! - `ARCHITECTURE.md` + `docs/adr/` — the "Power User / Builder" user-tier
//!   rules this surface honors.
//! - [`aether_l5_policy::Capability`] — the additive surface this crate
//!   plugs into. The file-related variants already live there.

#![forbid(unsafe_code)]

pub mod capability_map;
pub mod executor;
#[cfg(feature = "std-fs")]
pub mod std_fs_stub;
pub mod types;

pub use capability_map::capability_for_method;
pub use executor::FilesExecutor;
pub use types::{FilesExecError, GrepHit, ScopeAllowlist};
