//! L5 file-workflow capability surface.
//!
//! **Skeleton only.** Per CLAUDE.md §3 (coordinator-gated package
//! creation), this crate ships in two PRs: this skeleton + later
//! implementation slices. Implementation lands in follow-up sessions
//! per the T1.3 sub-decisions.
//!
//! # Scope (frozen by Don 2026-04-30)
//!
//! - L5-gated file workflow primitives. `FilesRead` and `FilesCreate`
//!   already exist on `aether_l5_policy::Capability`; this crate adds
//!   `FilesEdit`, `FilesDelete`, `FilesMove`, `FilesArchive`,
//!   `FilesGrep` in follow-up impl PRs. Each is additive — this crate
//!   does not fork the policy enum.
//! - **Scope model: explicit allowlist** (locked T1.3 §5.2). The
//!   approved scope for any file capability is the directory tree the
//!   user explicitly granted via the existing approval framework.
//!   Matches the `MediaPermissions` shape already in the policy layer.
//! - Outside-scope writes are **Deny** in Observer / Assistant /
//!   Operator presets. Power User may grant outside-scope access on a
//!   per-session basis only.
//! - Approval mode follows the active autonomy preset:
//!   - **Observer** — Deny (all write capabilities; reads gated separately).
//!   - **Assistant** — Ask (read + edit + grep), Ask (delete / move / archive).
//!   - **Operator** — Auto for `FilesRead` + `FilesCreate` + `FilesEdit`
//!     + `FilesGrep` inside approved scope; `FilesDelete` + `FilesMove`
//!     stay Ask; outside-scope writes Deny.
//!   - **Power User** — additionally permits per-session grants for
//!     outside-scope access.
//!
//! # References
//!
//! - `planning/plans/T1.3_browser_file_workflow_proposal.md` §2.2 — the
//!   Approved coordinator proposal. Status flipped to Approved
//!   2026-04-30 under Don's "1–5 are your decisions now" delegation.
//! - `planning/12_permissions_autonomy.md` §"Power User / Builder" —
//!   user-tier rules this surface honors.
//! - `aether_l5_policy::Capability` — the additive surface where new
//!   variants land. `FilesRead` and `FilesCreate` already live there;
//!   `FilesEdit`, `FilesDelete`, `FilesMove`, `FilesArchive`,
//!   `FilesGrep` arrive in follow-up impl PRs.

#![forbid(unsafe_code)]

/// Placeholder file-capability marker.
///
/// Implementation PRs replace this enum's empty variant set with the
/// real capabilities, which then map onto
/// `aether_l5_policy::Capability` additions. Today the type only
/// exists so `cargo build -p aether-l5-files` produces a real artifact
/// and the workspace check passes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FilesCapability {}
