//! L5 file-workflow capability surface.
//!
//! **Status (T1.3 first impl slice):** Trait + types are now real, plus
//! a capability map and a default `std::fs` backend stub. Every stub
//! method returns [`FilesExecError::BackendDisabled`]; the real
//! `std::fs` / `tokio::fs` wiring lands in a later slice.
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
//!   `std-fs` feature; every method returns
//!   [`FilesExecError::BackendDisabled`] today.
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
//! - `planning/plans/T1.3_browser_file_workflow_proposal.md` §2.2 — the
//!   Approved coordinator proposal.
//! - `planning/12_permissions_autonomy.md` §"Power User / Builder" —
//!   user-tier rules this surface honors.
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
