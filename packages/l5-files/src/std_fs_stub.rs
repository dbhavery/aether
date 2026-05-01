//! Default file-workflow backend — `tokio::fs`.
//!
//! Gated behind the `std-fs` feature so default builds do not pull
//! `tokio::fs` (or any other async-fs runtime). When the feature is on,
//! [`StdFsExecutor`] is a real backend: every method canonicalizes
//! input paths, authorizes them against a [`ScopeAllowlist`], then
//! defers to `tokio::fs` for the actual I/O.
//!
//! # Architecture
//!
//! - Holds an immutable [`ScopeAllowlist`]; every input path is
//!   canonicalized BEFORE the allowlist check, so a symlink whose
//!   target falls outside the allowlist is rejected even if the symlink
//!   itself sits inside an approved root.
//! - `create` / `edit` are atomic: write to a sibling tempfile in the
//!   destination's parent directory, then `tokio::fs::rename` to the
//!   final path. `create` rejects pre-existing destinations; `edit`
//!   replaces unconditionally.
//! - `rename` authorizes BOTH endpoints (canonicalize the parent of the
//!   destination, then re-anchor the destination filename onto the
//!   canonical parent — `tokio::fs::canonicalize` requires the path to
//!   exist, and `dst` does not yet).
//! - `delete` is files-only; directories return [`FilesExecError::Io`]
//!   with a clear message. Directory deletion is out of scope for this
//!   slice.
//! - `grep` is a streaming line scanner over files DIRECTLY under
//!   `root` (non-recursive). Substring match against `pattern`. Each
//!   matching line is pushed as a [`GrepHit`] with a 1-indexed
//!   `line_no`. Recursive walk is deferred — see commit body for the
//!   sub-decision.
//!
//! # Runtime-absent self-degrade
//!
//! Synchronous test harnesses (no `#[tokio::test]`, no
//! `Builder::new_current_thread().enable_all().build()`) call into the
//! executor without a Tokio runtime; `tokio::fs` panics in that case.
//! Every public method short-circuits to
//! [`FilesExecError::BackendDisabled`] when
//! `tokio::runtime::Handle::try_current().is_err()`. This is the
//! pattern caught in the playwright slice (e2690d5) and applied
//! preemptively here.
//!
//! # Layer rules
//!
//! Per CLAUDE.md §1.5, the executor itself does NOT perform any policy
//! check — call sites resolve a `Capability` via
//! [`crate::capability_for_method`], ask L5 for `Decision::Allow`, and
//! only then invoke a method here. Scope authorization (the allowlist
//! check inside this module) is a defence-in-depth layer ON TOP of the
//! L5 policy gate, not a replacement for it.

use std::ffi::OsString;
use std::path::{Path, PathBuf};

use async_trait::async_trait;
use tokio::fs;
use tokio::io::{AsyncBufReadExt, BufReader};

use crate::executor::FilesExecutor;
use crate::types::{FilesExecError, GrepHit, ScopeAllowlist};

/// `tokio::fs`-backed [`FilesExecutor`].
///
/// Construct via [`StdFsExecutor::new`] with the
/// [`ScopeAllowlist`](crate::types::ScopeAllowlist) the caller has
/// already negotiated through L5 policy. The allowlist is held by
/// value; clone it before constructing if the caller needs to keep a
/// copy.
#[derive(Debug, Clone)]
pub struct StdFsExecutor {
    scope: ScopeAllowlist,
}

impl StdFsExecutor {
    /// Construct a new executor scoped to `scope`.
    ///
    /// The allowlist roots are NOT canonicalized at construction time —
    /// the caller is expected to have done that already (the L5 policy
    /// layer does it when the user grants scope). Each operation
    /// canonicalizes its input path and then path-prefix-matches it
    /// against the (already-canonical) roots.
    pub fn new(scope: ScopeAllowlist) -> Self {
        Self { scope }
    }
}

impl Default for StdFsExecutor {
    /// Construct an executor with an empty scope. Every method will
    /// reject every path with [`FilesExecError::NotInScope`]. Useful
    /// for tests and for wiring stages that have not yet plumbed real
    /// scope through.
    fn default() -> Self {
        Self::new(ScopeAllowlist::default())
    }
}

/// Short-circuit to [`FilesExecError::BackendDisabled`] when called
/// from a thread with no Tokio runtime. See module docs.
fn require_runtime() -> Result<(), FilesExecError> {
    if tokio::runtime::Handle::try_current().is_err() {
        return Err(FilesExecError::BackendDisabled);
    }
    Ok(())
}

/// Canonicalize `path` and authorize the canonical form against
/// `scope`. Returns the canonical path on success.
async fn canonicalize_and_authorize(
    scope: &ScopeAllowlist,
    path: &Path,
) -> Result<PathBuf, FilesExecError> {
    let canonical = fs::canonicalize(path).await.map_err(|e| {
        if e.kind() == std::io::ErrorKind::NotFound {
            FilesExecError::NotFound(path.display().to_string())
        } else {
            FilesExecError::Io(format!("canonicalize {}: {}", path.display(), e))
        }
    })?;
    if !scope.is_within_scope(&canonical) {
        return Err(FilesExecError::NotInScope(canonical.display().to_string()));
    }
    Ok(canonical)
}

/// Authorize a destination path that does NOT yet exist (used by
/// `create` and the dst side of `rename`).
///
/// `tokio::fs::canonicalize` requires the path to exist, so we
/// canonicalize the *parent* and re-anchor the filename onto it. This
/// still resolves any symlinks in the parent chain BEFORE the allowlist
/// check, which is the property the locked T1.3 §5.2 sub-decision
/// requires.
async fn canonicalize_parent_and_authorize(
    scope: &ScopeAllowlist,
    path: &Path,
) -> Result<PathBuf, FilesExecError> {
    let parent = path.parent().ok_or_else(|| {
        FilesExecError::Io(format!("path has no parent: {}", path.display()))
    })?;
    let file_name: OsString = path
        .file_name()
        .ok_or_else(|| {
            FilesExecError::Io(format!("path has no file name: {}", path.display()))
        })?
        .to_os_string();
    let canonical_parent = fs::canonicalize(parent).await.map_err(|e| {
        if e.kind() == std::io::ErrorKind::NotFound {
            FilesExecError::NotFound(parent.display().to_string())
        } else {
            FilesExecError::Io(format!("canonicalize {}: {}", parent.display(), e))
        }
    })?;
    let mut canonical = canonical_parent;
    canonical.push(file_name);
    if !scope.is_within_scope(&canonical) {
        return Err(FilesExecError::NotInScope(canonical.display().to_string()));
    }
    Ok(canonical)
}

/// Build a sibling tempfile path next to `final_path` (same parent,
/// suffixed with `.aether-tmp.<pid>.<nanos>`). Same-directory siblings
/// are required for the rename-replace step to be atomic on every
/// platform we care about (Windows + Linux + macOS).
fn temp_sibling(final_path: &Path) -> PathBuf {
    use std::time::{SystemTime, UNIX_EPOCH};
    let pid = std::process::id();
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let mut name: OsString = final_path
        .file_name()
        .map(|n| n.to_os_string())
        .unwrap_or_else(|| OsString::from("aether"));
    name.push(format!(".aether-tmp.{pid}.{nanos}"));
    let mut tmp = final_path
        .parent()
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| PathBuf::from("."));
    tmp.push(name);
    tmp
}

/// Atomic write helper: write `contents` to a sibling tempfile, then
/// rename onto `final_path`. Used by `create` and `edit`.
async fn atomic_write(final_path: &Path, contents: &[u8]) -> Result<(), FilesExecError> {
    let tmp = temp_sibling(final_path);
    if let Err(e) = fs::write(&tmp, contents).await {
        // Best-effort cleanup; ignore secondary failure.
        let _ = fs::remove_file(&tmp).await;
        return Err(FilesExecError::Io(format!(
            "write tempfile {}: {}",
            tmp.display(),
            e
        )));
    }
    if let Err(e) = fs::rename(&tmp, final_path).await {
        let _ = fs::remove_file(&tmp).await;
        return Err(FilesExecError::Io(format!(
            "rename {} -> {}: {}",
            tmp.display(),
            final_path.display(),
            e
        )));
    }
    Ok(())
}

#[async_trait]
impl FilesExecutor for StdFsExecutor {
    async fn read(&self, path: &Path) -> Result<Vec<u8>, FilesExecError> {
        require_runtime()?;
        let canonical = canonicalize_and_authorize(&self.scope, path).await?;
        fs::read(&canonical)
            .await
            .map_err(|e| FilesExecError::Io(format!("read {}: {}", canonical.display(), e)))
    }

    async fn create(
        &self,
        path: &Path,
        contents: &[u8],
    ) -> Result<(), FilesExecError> {
        require_runtime()?;
        // `create` MUST refuse to overwrite — see executor.rs trait doc.
        // Reject pre-existing destinations BEFORE we touch the parent.
        if fs::metadata(path).await.is_ok() {
            return Err(FilesExecError::AlreadyExists(path.display().to_string()));
        }
        let canonical = canonicalize_parent_and_authorize(&self.scope, path).await?;
        atomic_write(&canonical, contents).await
    }

    async fn edit(
        &self,
        path: &Path,
        contents: &[u8],
    ) -> Result<(), FilesExecError> {
        require_runtime()?;
        // `edit` requires the file to already exist.
        let canonical = canonicalize_and_authorize(&self.scope, path).await?;
        atomic_write(&canonical, contents).await
    }

    async fn rename(
        &self,
        src: &Path,
        dst: &Path,
    ) -> Result<(), FilesExecError> {
        require_runtime()?;
        let canonical_src = canonicalize_and_authorize(&self.scope, src).await?;
        // `dst` doesn't exist yet — canonicalize its parent.
        let canonical_dst = canonicalize_parent_and_authorize(&self.scope, dst).await?;
        // Refuse to clobber an existing destination — a rename that
        // replaces a file is the user-visible equivalent of a delete +
        // create, and we want delete to require its own capability.
        if fs::metadata(&canonical_dst).await.is_ok() {
            return Err(FilesExecError::AlreadyExists(
                canonical_dst.display().to_string(),
            ));
        }
        fs::rename(&canonical_src, &canonical_dst)
            .await
            .map_err(|e| {
                FilesExecError::Io(format!(
                    "rename {} -> {}: {}",
                    canonical_src.display(),
                    canonical_dst.display(),
                    e
                ))
            })
    }

    async fn delete(&self, path: &Path) -> Result<(), FilesExecError> {
        require_runtime()?;
        let canonical = canonicalize_and_authorize(&self.scope, path).await?;
        let meta = fs::metadata(&canonical).await.map_err(|e| {
            FilesExecError::Io(format!("metadata {}: {}", canonical.display(), e))
        })?;
        if meta.is_dir() {
            return Err(FilesExecError::Io(format!(
                "refusing to delete directory (out of scope for this slice): {}",
                canonical.display()
            )));
        }
        fs::remove_file(&canonical).await.map_err(|e| {
            FilesExecError::Io(format!("remove_file {}: {}", canonical.display(), e))
        })
    }

    async fn grep(
        &self,
        root: &Path,
        pattern: &str,
    ) -> Result<Vec<GrepHit>, FilesExecError> {
        require_runtime()?;
        let canonical_root = canonicalize_and_authorize(&self.scope, root).await?;
        let meta = fs::metadata(&canonical_root).await.map_err(|e| {
            FilesExecError::Io(format!("metadata {}: {}", canonical_root.display(), e))
        })?;
        // Single-file grep is a useful degenerate case (caller pointed
        // at a specific file).
        if meta.is_file() {
            return grep_one_file(&canonical_root, pattern).await;
        }
        if !meta.is_dir() {
            return Err(FilesExecError::Io(format!(
                "grep root is neither a file nor a directory: {}",
                canonical_root.display()
            )));
        }
        // Non-recursive walk: only files DIRECTLY under root. Recursive
        // walk is deferred — would need an explicit max-depth cap and
        // a per-entry allowlist re-check on symlink crossings, both of
        // which expand the threat surface beyond this slice.
        let mut hits = Vec::new();
        let mut entries = fs::read_dir(&canonical_root).await.map_err(|e| {
            FilesExecError::Io(format!("read_dir {}: {}", canonical_root.display(), e))
        })?;
        while let Some(entry) = entries.next_entry().await.map_err(|e| {
            FilesExecError::Io(format!("dir entry under {}: {}", canonical_root.display(), e))
        })? {
            let entry_path = entry.path();
            let entry_meta = match entry.metadata().await {
                Ok(m) => m,
                Err(_) => continue, // skip racing-removed entries
            };
            if !entry_meta.is_file() {
                continue;
            }
            let mut file_hits = grep_one_file(&entry_path, pattern).await?;
            hits.append(&mut file_hits);
        }
        Ok(hits)
    }
}

/// Stream a single file line-by-line, push hits whose text contains
/// `pattern` (substring match — regex is deferred until the workspace
/// adopts a regex crate). 1-indexed `line_no`, trailing newline already
/// stripped by `BufReader::lines`.
async fn grep_one_file(path: &Path, pattern: &str) -> Result<Vec<GrepHit>, FilesExecError> {
    let file = fs::File::open(path)
        .await
        .map_err(|e| FilesExecError::Io(format!("open {}: {}", path.display(), e)))?;
    let mut reader = BufReader::new(file).lines();
    let mut hits = Vec::new();
    let mut line_no: usize = 0;
    while let Some(line) = reader
        .next_line()
        .await
        .map_err(|e| FilesExecError::Io(format!("read line in {}: {}", path.display(), e)))?
    {
        line_no += 1;
        if line.contains(pattern) {
            hits.push(GrepHit {
                path: path.to_path_buf(),
                line_no,
                line_text: line,
            });
        }
    }
    Ok(hits)
}
