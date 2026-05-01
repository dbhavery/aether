//! The [`FilesExecutor`] trait — the object-safe async surface every
//! file-workflow backend must implement.
//!
//! The trait is deliberately minimal: enough verbs to cover the
//! existing file-related variants on
//! [`aether_l5_policy::Capability`] (`FilesRead`, `FilesCreate`,
//! `FilesEdit`, `FilesRenameMove`, `FilesDelete`, `FilesBulkOp`),
//! plus `grep` for read-only content search. Higher-level
//! orchestration (atomic multi-file writes, transactional renames,
//! watch-and-rerun) is built on top by callers, not baked into the
//! trait.
//!
//! # Wiring
//!
//! L5 is the single writer for side effects (CLAUDE.md §1.5). Every
//! Tauri command that wants to drive a file workflow resolves a
//! [`Capability`](aether_l5_policy::Capability) via the
//! [`capability_for_method`](crate::capability_map::capability_for_method)
//! helper, asks L5 for a `Decision::Allow`, and then — and only then —
//! calls the matching method on a `dyn FilesExecutor`. The executor
//! itself does NOT perform any policy check; that responsibility lives
//! one layer up, by design.
//!
//! # Backends
//!
//! - [`std_fs_stub::StdFsExecutor`](crate::std_fs_stub::StdFsExecutor)
//!   — the default backend. Gated behind the `std-fs` feature; real
//!   `tokio::fs` implementation. Self-degrades to
//!   [`FilesExecError::BackendDisabled`] when called from a thread
//!   with no Tokio runtime (synchronous test harnesses).

use std::path::Path;

use async_trait::async_trait;

use crate::types::{FilesExecError, GrepHit};

/// Object-safe async surface for driving a file workflow.
///
/// Implementations MUST be `Send + Sync` so callers can store them as
/// `Arc<dyn FilesExecutor>` and share them across Tauri command
/// handlers. Each method maps one-to-one onto an
/// [`aether_l5_policy::Capability`] variant via
/// [`capability_for_method`](crate::capability_map::capability_for_method).
#[async_trait]
pub trait FilesExecutor: Send + Sync {
    /// Read the full contents of a file.
    ///
    /// Maps to
    /// [`Capability::FilesRead`](aether_l5_policy::Capability::FilesRead).
    /// Returns the raw bytes; callers are responsible for any
    /// text-decoding choices.
    async fn read(&self, path: &Path) -> Result<Vec<u8>, FilesExecError>;

    /// Create a new file with the given contents. MUST refuse to
    /// overwrite an existing path — overwrite is the
    /// [`edit`](FilesExecutor::edit) capability.
    ///
    /// Maps to
    /// [`Capability::FilesCreate`](aether_l5_policy::Capability::FilesCreate).
    async fn create(&self, path: &Path, contents: &[u8]) -> Result<(), FilesExecError>;

    /// Replace the contents of an existing file.
    ///
    /// Maps to
    /// [`Capability::FilesEdit`](aether_l5_policy::Capability::FilesEdit).
    /// Real backends SHOULD write atomically (write-to-temp + rename)
    /// to avoid partial-write windows.
    async fn edit(&self, path: &Path, contents: &[u8]) -> Result<(), FilesExecError>;

    /// Move or rename a file from `src` to `dst`.
    ///
    /// Maps to
    /// [`Capability::FilesRenameMove`](aether_l5_policy::Capability::FilesRenameMove).
    /// Both endpoints must be in approved scope; cross-scope renames
    /// are rejected by the policy boundary, not by this trait.
    async fn rename(&self, src: &Path, dst: &Path) -> Result<(), FilesExecError>;

    /// Delete a file.
    ///
    /// Maps to
    /// [`Capability::FilesDelete`](aether_l5_policy::Capability::FilesDelete).
    /// Per the locked T1.3 sub-decision, this capability NEVER auto-runs
    /// in any preset; the policy layer enforces the Ask gate above this
    /// trait.
    async fn delete(&self, path: &Path) -> Result<(), FilesExecError>;

    /// Search file contents under `root` for lines matching `pattern`.
    ///
    /// Maps to
    /// [`Capability::FilesRead`](aether_l5_policy::Capability::FilesRead)
    /// — see [`capability_for_method`](crate::capability_map::capability_for_method)
    /// for the rationale. The pattern grammar is backend-defined; the
    /// real backend will use a regex crate.
    async fn grep(&self, root: &Path, pattern: &str) -> Result<Vec<GrepHit>, FilesExecError>;
}
