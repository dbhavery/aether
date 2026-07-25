//! Supporting types for the [`FilesExecutor`](crate::executor::FilesExecutor)
//! trait surface.
//!
//! These types are intentionally minimal — just enough to express a
//! grep hit, an explicit-allowlist scope, and the failure modes any
//! backend will need to surface. Real fidelity (file metadata,
//! line-range reads, byte-range edits, watcher events) lands when the
//! real `std::fs` / `tokio::fs` wiring lands in a later slice.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use thiserror::Error;

/// A single grep hit returned by
/// [`FilesExecutor::grep`](crate::executor::FilesExecutor::grep).
///
/// `line_no` is 1-indexed (matching `grep -n`, `ripgrep`, and editor
/// conventions). `line_text` is the matching line with its trailing
/// newline stripped. The exact pattern grammar is backend-defined — the
/// real `std::fs` backend will use a regex crate; this type does not
/// constrain that choice.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GrepHit {
    /// Path of the file containing the hit.
    pub path: PathBuf,
    /// 1-indexed line number of the matching line.
    pub line_no: usize,
    /// Matching line, trailing newline stripped.
    pub line_text: String,
}

/// Explicit-allowlist scope model — the locked T1.3 §5.2 sub-decision.
///
/// The approved scope for any file capability is the explicit set of
/// directory roots the user granted via the existing approval
/// framework. There is no glob-pattern whitelist, no implicit
/// project-tree expansion, and no symlink traversal across roots.
///
/// Real backends MUST canonicalize paths before calling
/// [`is_within_scope`](Self::is_within_scope) so a symlink inside a
/// root cannot smuggle an outside-scope target through the check.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct ScopeAllowlist {
    /// The set of directory roots the user has granted access to. Each
    /// path SHOULD be absolute and canonicalized at construction time
    /// by the caller.
    pub roots: Vec<PathBuf>,
}

impl ScopeAllowlist {
    /// Construct a new allowlist from an iterable of roots.
    pub fn new(roots: impl IntoIterator<Item = PathBuf>) -> Self {
        Self {
            roots: roots.into_iter().collect(),
        }
    }

    /// Return `true` iff `path` is within at least one of the
    /// allowlist roots.
    ///
    /// "Within" is checked by path-prefix match against each root.
    /// Callers are responsible for canonicalizing `path` first if they
    /// need symlink-safe semantics; this method intentionally does no
    /// I/O, so it is cheap to call from a policy-evaluation hot path.
    pub fn is_within_scope(&self, path: &Path) -> bool {
        self.roots.iter().any(|root| path.starts_with(root))
    }
}

/// Failure modes for [`FilesExecutor`](crate::executor::FilesExecutor) calls.
///
/// Variants are deliberately coarse-grained at this stage; richer
/// diagnostics (errno, byte-offset, partial-write recovery) are added
/// when the real `std::fs` / `tokio::fs` backend lands. Every variant
/// is non-recoverable at the policy boundary — L5 logs the failure and
/// surfaces it to the caller.
#[derive(Debug, Error)]
pub enum FilesExecError {
    /// The supplied path is not within the active
    /// [`ScopeAllowlist`]. Callers MUST treat this as a hard deny — the
    /// executor never silently expands scope.
    #[error("path is not within approved scope: {0}")]
    NotInScope(String),

    /// The path does not exist.
    #[error("file not found: {0}")]
    NotFound(String),

    /// A create operation refused to overwrite an existing path.
    #[error("file already exists: {0}")]
    AlreadyExists(String),

    /// A backend I/O error not yet promoted to a typed variant.
    #[error("io error: {0}")]
    Io(String),

    /// The backend is compiled in but disabled at runtime — typically
    /// because the real `std::fs` / `tokio::fs` wiring has not yet
    /// landed. This is the variant the
    /// [`std_fs_stub`](crate::std_fs_stub) module returns for every
    /// method today.
    #[error("files backend is disabled (stub only)")]
    BackendDisabled,

    /// Catch-all for backend errors not yet promoted to a typed variant.
    #[error("internal files-executor error: {0}")]
    Internal(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_allowlist_rejects_everything() {
        let scope = ScopeAllowlist::default();
        assert!(!scope.is_within_scope(Path::new("/anywhere/at/all")));
        assert!(!scope.is_within_scope(Path::new("relative/path")));
    }

    #[test]
    fn path_inside_root_is_in_scope() {
        let scope = ScopeAllowlist::new([PathBuf::from("/home/don/projects")]);
        assert!(scope.is_within_scope(Path::new("/home/don/projects/aether/file.rs")));
        assert!(scope.is_within_scope(Path::new("/home/don/projects")));
    }

    #[test]
    fn path_outside_roots_is_rejected() {
        let scope = ScopeAllowlist::new([PathBuf::from("/home/don/projects")]);
        assert!(!scope.is_within_scope(Path::new("/etc/passwd")));
        assert!(!scope.is_within_scope(Path::new("/home/don/secrets/key.pem")));
    }

    #[test]
    fn multiple_roots_each_match() {
        let scope = ScopeAllowlist::new([
            PathBuf::from("/home/don/projects"),
            PathBuf::from("/srv/data"),
        ]);
        assert!(scope.is_within_scope(Path::new("/home/don/projects/x")));
        assert!(scope.is_within_scope(Path::new("/srv/data/y")));
        assert!(!scope.is_within_scope(Path::new("/var/log/z")));
    }

    #[test]
    fn sibling_prefix_does_not_falsely_match() {
        // Path::starts_with is component-wise, so /home/don/projects2
        // does NOT start with /home/don/projects. Lock that behavior in.
        let scope = ScopeAllowlist::new([PathBuf::from("/home/don/projects")]);
        assert!(!scope.is_within_scope(Path::new("/home/don/projects2/file.rs")));
    }
}
