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
//! - Holds a [`ScopeAllowlist`] behind an `Arc<RwLock<...>>` so callers
//!   (the L5 policy layer) can swap the live scope wholesale at runtime
//!   without rebuilding the executor. The threat model is unchanged:
//!   every input path is canonicalized BEFORE the allowlist check, so
//!   a symlink whose target falls outside the allowlist is rejected
//!   even if the symlink itself sits inside an approved root. Only the
//!   wholesale-swap path is exposed (no per-entry add/remove) — this
//!   keeps the auditable surface to two methods,
//!   [`StdFsExecutor::set_allowlist`] and
//!   [`StdFsExecutor::update_allowlist_from_paths`], both of which
//!   atomically replace the live scope.
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
use std::sync::{Arc, RwLock};

use async_trait::async_trait;
use tokio::fs;
use tokio::io::{AsyncBufReadExt, BufReader};

use crate::executor::FilesExecutor;
use crate::types::{FilesExecError, GrepHit, ScopeAllowlist};

/// `tokio::fs`-backed [`FilesExecutor`].
///
/// Construct via [`StdFsExecutor::new`] with the
/// [`ScopeAllowlist`](crate::types::ScopeAllowlist) the caller has
/// already negotiated through L5 policy.
///
/// Internally the allowlist is held in an `Arc<RwLock<ScopeAllowlist>>`
/// so the executor's scope can be widened or narrowed at runtime
/// (e.g. when the user grants or revokes a fresh scope through L5
/// policy) without rebuilding the executor and without disrupting
/// in-flight operations. Cloning the executor is cheap — clones share
/// the same lock and therefore the same live scope state. See
/// [`set_allowlist`](Self::set_allowlist) and
/// [`update_allowlist_from_paths`](Self::update_allowlist_from_paths).
#[derive(Debug)]
pub struct StdFsExecutor {
    scope: Arc<RwLock<ScopeAllowlist>>,
}

impl Clone for StdFsExecutor {
    /// Clones share the same allowlist state via `Arc`. Mutating the
    /// scope on any clone (via [`set_allowlist`](Self::set_allowlist) or
    /// [`update_allowlist_from_paths`](Self::update_allowlist_from_paths))
    /// is observed by every other clone immediately.
    fn clone(&self) -> Self {
        Self {
            scope: Arc::clone(&self.scope),
        }
    }
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
        Self {
            scope: Arc::new(RwLock::new(scope)),
        }
    }

    /// Atomically replace the active allowlist.
    ///
    /// All in-flight operations that have already cloned the previous
    /// allowlist (inside `canonicalize_and_authorize` /
    /// `canonicalize_parent_and_authorize`) finish under the previous
    /// scope; subsequent calls observe the new scope. The roots are
    /// stored verbatim — canonicalize them first if symlink-safe
    /// semantics are required (see
    /// [`update_allowlist_from_paths`](Self::update_allowlist_from_paths)
    /// for a helper that does this).
    pub fn set_allowlist(&self, scope: ScopeAllowlist) {
        // Poisoned locks are treated as an unrecoverable invariant
        // violation in this stub; unwrap matches the convention used
        // elsewhere in this crate's tests.
        let mut guard = self.scope.write().expect("scope lock poisoned");
        *guard = scope;
    }

    /// Build a new allowlist by canonicalizing each supplied path
    /// (synchronously, via [`std::fs::canonicalize`] — matching what
    /// L5 policy does at grant time) and atomically swap it in.
    ///
    /// Each path must already exist; a path that fails canonicalization
    /// returns [`FilesExecError::Io`] and the existing allowlist is
    /// left untouched. Empty input is allowed and clears the scope
    /// (every subsequent call will reject paths with
    /// [`FilesExecError::NotInScope`]).
    pub fn update_allowlist_from_paths<I>(&self, roots: I) -> Result<(), FilesExecError>
    where
        I: IntoIterator<Item = PathBuf>,
    {
        let mut canonical = Vec::new();
        for root in roots {
            let resolved = std::fs::canonicalize(&root).map_err(|e| {
                FilesExecError::Io(format!("canonicalize {}: {}", root.display(), e))
            })?;
            canonical.push(resolved);
        }
        self.set_allowlist(ScopeAllowlist::new(canonical));
        Ok(())
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

/// Snapshot the current allowlist by cloning it under a short read
/// guard. The guard is released before this function returns, which is
/// required because callers go on to `.await` and `RwLockReadGuard`
/// from `std::sync` is not safe to hold across await points.
fn snapshot_scope(scope: &Arc<RwLock<ScopeAllowlist>>) -> ScopeAllowlist {
    scope.read().expect("scope lock poisoned").clone()
}

/// Canonicalize `path` and authorize the canonical form against the
/// current contents of `scope`. Returns the canonical path on success.
async fn canonicalize_and_authorize(
    scope: &Arc<RwLock<ScopeAllowlist>>,
    path: &Path,
) -> Result<PathBuf, FilesExecError> {
    let snapshot = snapshot_scope(scope);
    let canonical = fs::canonicalize(path).await.map_err(|e| {
        if e.kind() == std::io::ErrorKind::NotFound {
            FilesExecError::NotFound(path.display().to_string())
        } else {
            FilesExecError::Io(format!("canonicalize {}: {}", path.display(), e))
        }
    })?;
    if !snapshot.is_within_scope(&canonical) {
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
    scope: &Arc<RwLock<ScopeAllowlist>>,
    path: &Path,
) -> Result<PathBuf, FilesExecError> {
    let snapshot = snapshot_scope(scope);
    let parent = path
        .parent()
        .ok_or_else(|| FilesExecError::Io(format!("path has no parent: {}", path.display())))?;
    let file_name: OsString = path
        .file_name()
        .ok_or_else(|| FilesExecError::Io(format!("path has no file name: {}", path.display())))?
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
    if !snapshot.is_within_scope(&canonical) {
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

    async fn create(&self, path: &Path, contents: &[u8]) -> Result<(), FilesExecError> {
        require_runtime()?;
        // `create` MUST refuse to overwrite — see executor.rs trait doc.
        // Reject pre-existing destinations BEFORE we touch the parent.
        if fs::metadata(path).await.is_ok() {
            return Err(FilesExecError::AlreadyExists(path.display().to_string()));
        }
        let canonical = canonicalize_parent_and_authorize(&self.scope, path).await?;
        atomic_write(&canonical, contents).await
    }

    async fn edit(&self, path: &Path, contents: &[u8]) -> Result<(), FilesExecError> {
        require_runtime()?;
        // `edit` requires the file to already exist.
        let canonical = canonicalize_and_authorize(&self.scope, path).await?;
        atomic_write(&canonical, contents).await
    }

    async fn rename(&self, src: &Path, dst: &Path) -> Result<(), FilesExecError> {
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
        let meta = fs::metadata(&canonical)
            .await
            .map_err(|e| FilesExecError::Io(format!("metadata {}: {}", canonical.display(), e)))?;
        if meta.is_dir() {
            return Err(FilesExecError::Io(format!(
                "refusing to delete directory (out of scope for this slice): {}",
                canonical.display()
            )));
        }
        fs::remove_file(&canonical)
            .await
            .map_err(|e| FilesExecError::Io(format!("remove_file {}: {}", canonical.display(), e)))
    }

    async fn grep(&self, root: &Path, pattern: &str) -> Result<Vec<GrepHit>, FilesExecError> {
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
            FilesExecError::Io(format!(
                "dir entry under {}: {}",
                canonical_root.display(),
                e
            ))
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use tempfile::TempDir;

    /// Build a `StdFsExecutor` whose scope is the canonicalized form
    /// of the supplied `TempDir` — `tempfile` returns a path that may
    /// itself contain symlinks (e.g. /tmp -> /private/tmp on macOS,
    /// short-name expansion on Windows), so canonicalize at scope
    /// construction time to match what `canonicalize_and_authorize`
    /// will see at call time.
    fn exec_for(dir: &TempDir) -> StdFsExecutor {
        let canonical = std::fs::canonicalize(dir.path()).expect("canonicalize tmpdir");
        StdFsExecutor::new(ScopeAllowlist::new([canonical]))
    }

    #[tokio::test]
    async fn read_round_trips_existing_file() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("hello.txt");
        std::fs::write(&path, b"hello world").unwrap();
        let exec = exec_for(&dir);

        let bytes = exec.read(&path).await.unwrap();
        assert_eq!(bytes, b"hello world");
    }

    #[tokio::test]
    async fn read_missing_path_returns_not_found() {
        let dir = TempDir::new().unwrap();
        let exec = exec_for(&dir);

        let err = exec.read(&dir.path().join("nope.txt")).await.unwrap_err();
        assert!(matches!(err, FilesExecError::NotFound(_)), "got {err:?}");
    }

    #[tokio::test]
    async fn create_writes_new_file_atomically() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("new.txt");
        let exec = exec_for(&dir);

        exec.create(&path, b"first write").await.unwrap();
        assert_eq!(std::fs::read(&path).unwrap(), b"first write");

        // No leftover tempfile sibling.
        let leftovers: Vec<_> = std::fs::read_dir(dir.path())
            .unwrap()
            .filter_map(|e| e.ok())
            .filter(|e| e.file_name().to_string_lossy().contains(".aether-tmp."))
            .collect();
        assert!(leftovers.is_empty(), "leftover tempfile(s): {leftovers:?}");
    }

    #[tokio::test]
    async fn create_refuses_existing_destination() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("existing.txt");
        std::fs::write(&path, b"old").unwrap();
        let exec = exec_for(&dir);

        let err = exec.create(&path, b"new").await.unwrap_err();
        assert!(
            matches!(err, FilesExecError::AlreadyExists(_)),
            "got {err:?}"
        );
        // Original content preserved.
        assert_eq!(std::fs::read(&path).unwrap(), b"old");
    }

    #[tokio::test]
    async fn edit_replaces_existing_file() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("e.txt");
        std::fs::write(&path, b"v1").unwrap();
        let exec = exec_for(&dir);

        exec.edit(&path, b"v2 longer").await.unwrap();
        assert_eq!(std::fs::read(&path).unwrap(), b"v2 longer");
    }

    #[tokio::test]
    async fn edit_missing_file_is_not_found() {
        let dir = TempDir::new().unwrap();
        let exec = exec_for(&dir);

        let err = exec
            .edit(&dir.path().join("absent.txt"), b"x")
            .await
            .unwrap_err();
        assert!(matches!(err, FilesExecError::NotFound(_)), "got {err:?}");
    }

    #[tokio::test]
    async fn rename_moves_within_scope() {
        let dir = TempDir::new().unwrap();
        let src = dir.path().join("a.txt");
        let dst = dir.path().join("b.txt");
        std::fs::write(&src, b"payload").unwrap();
        let exec = exec_for(&dir);

        exec.rename(&src, &dst).await.unwrap();
        assert!(!src.exists());
        assert_eq!(std::fs::read(&dst).unwrap(), b"payload");
    }

    #[tokio::test]
    async fn rename_refuses_to_clobber_existing_dst() {
        let dir = TempDir::new().unwrap();
        let src = dir.path().join("src.txt");
        let dst = dir.path().join("dst.txt");
        std::fs::write(&src, b"src").unwrap();
        std::fs::write(&dst, b"dst").unwrap();
        let exec = exec_for(&dir);

        let err = exec.rename(&src, &dst).await.unwrap_err();
        assert!(
            matches!(err, FilesExecError::AlreadyExists(_)),
            "got {err:?}"
        );
        // Both still present.
        assert!(src.exists());
        assert_eq!(std::fs::read(&dst).unwrap(), b"dst");
    }

    #[tokio::test]
    async fn delete_removes_file() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("doomed.txt");
        std::fs::write(&path, b"x").unwrap();
        let exec = exec_for(&dir);

        exec.delete(&path).await.unwrap();
        assert!(!path.exists());
    }

    #[tokio::test]
    async fn delete_refuses_directory() {
        let dir = TempDir::new().unwrap();
        let sub = dir.path().join("subdir");
        std::fs::create_dir(&sub).unwrap();
        let exec = exec_for(&dir);

        let err = exec.delete(&sub).await.unwrap_err();
        assert!(matches!(err, FilesExecError::Io(_)), "got {err:?}");
        assert!(sub.exists()); // untouched
    }

    #[tokio::test]
    async fn grep_finds_substring_hits() {
        let dir = TempDir::new().unwrap();
        std::fs::write(
            dir.path().join("a.txt"),
            b"first line\nTODO: fix this\nthird\n",
        )
        .unwrap();
        std::fs::write(dir.path().join("b.txt"), b"no hits here\n").unwrap();
        std::fs::write(dir.path().join("c.txt"), b"another TODO line\nclean\n").unwrap();
        let exec = exec_for(&dir);

        let hits = exec.grep(dir.path(), "TODO").await.unwrap();
        assert_eq!(hits.len(), 2);
        // Both hits should report 1-indexed line numbers.
        for h in &hits {
            assert!(h.line_text.contains("TODO"));
            assert!(h.line_no >= 1);
        }
    }

    #[tokio::test]
    async fn grep_single_file_root_works() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("solo.txt");
        std::fs::write(&path, b"alpha\nbeta TODO\ngamma\n").unwrap();
        let exec = exec_for(&dir);

        let hits = exec.grep(&path, "TODO").await.unwrap();
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].line_no, 2);
        assert_eq!(hits[0].line_text, "beta TODO");
    }

    #[tokio::test]
    async fn out_of_scope_path_is_rejected() {
        let scope_dir = TempDir::new().unwrap();
        let other_dir = TempDir::new().unwrap();
        let path = other_dir.path().join("file.txt");
        std::fs::write(&path, b"x").unwrap();
        let exec = exec_for(&scope_dir);

        let err = exec.read(&path).await.unwrap_err();
        assert!(matches!(err, FilesExecError::NotInScope(_)), "got {err:?}");
    }

    /// `..` segments must resolve BEFORE the allowlist check — any
    /// path that canonicalizes outside the allowlist is rejected, even
    /// if its lexical form lives inside an approved root.
    #[tokio::test]
    async fn parent_dir_traversal_is_rejected() {
        let outer = TempDir::new().unwrap();
        let inner = outer.path().join("inner");
        std::fs::create_dir(&inner).unwrap();
        let escape_target = outer.path().join("escape.txt");
        std::fs::write(&escape_target, b"secret").unwrap();

        // Allowlist is `inner/` only. Lexical path `inner/../escape.txt`
        // canonicalizes to `outer/escape.txt`, which is outside scope.
        let canonical_inner = std::fs::canonicalize(&inner).unwrap();
        let exec = StdFsExecutor::new(ScopeAllowlist::new([canonical_inner]));

        let traversal: PathBuf = inner.join("..").join("escape.txt");
        let err = exec.read(&traversal).await.unwrap_err();
        assert!(matches!(err, FilesExecError::NotInScope(_)), "got {err:?}");
    }

    // ---------------------------------------------------------------
    // Wave 13a — runtime allowlist mutation
    // ---------------------------------------------------------------

    /// Widen the executor's scope at runtime. With an empty scope, a
    /// read of an in-tempdir file fails as `NotInScope`; after
    /// `set_allowlist` adds the canonical tempdir, the same read
    /// succeeds.
    #[tokio::test]
    async fn set_allowlist_widens_scope_at_runtime() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("hello.txt");
        std::fs::write(&path, b"hi").unwrap();

        let exec = StdFsExecutor::default();
        let err = exec.read(&path).await.unwrap_err();
        assert!(matches!(err, FilesExecError::NotInScope(_)), "got {err:?}");

        let canonical = std::fs::canonicalize(dir.path()).unwrap();
        exec.set_allowlist(ScopeAllowlist::new([canonical]));

        let bytes = exec.read(&path).await.unwrap();
        assert_eq!(bytes, b"hi");
    }

    /// Narrow the executor's scope at runtime. A read that succeeds
    /// under the original scope must fail with `NotInScope` after the
    /// scope is cleared.
    #[tokio::test]
    async fn set_allowlist_narrows_scope_at_runtime() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("h.txt");
        std::fs::write(&path, b"x").unwrap();
        let exec = exec_for(&dir);

        // Sanity: read succeeds under the seeded scope.
        assert_eq!(exec.read(&path).await.unwrap(), b"x");

        exec.set_allowlist(ScopeAllowlist::default());
        let err = exec.read(&path).await.unwrap_err();
        assert!(matches!(err, FilesExecError::NotInScope(_)), "got {err:?}");
    }

    /// `update_allowlist_from_paths` must run the inputs through
    /// `std::fs::canonicalize` so a path containing `..` is stored in
    /// its canonical form.
    #[tokio::test]
    async fn update_allowlist_from_paths_canonicalizes() {
        let dir = TempDir::new().unwrap();
        let inner = dir.path().join("inner");
        std::fs::create_dir(&inner).unwrap();

        // Lexical path with a `..` segment that resolves back to dir.
        let traversal: PathBuf = inner.join("..");
        let expected = std::fs::canonicalize(dir.path()).unwrap();

        let exec = StdFsExecutor::default();
        exec.update_allowlist_from_paths([traversal]).unwrap();

        // Read the live allowlist to verify the canonical form landed.
        let scope = exec.scope.read().expect("scope lock poisoned").clone();
        assert_eq!(scope.roots.len(), 1);
        assert_eq!(scope.roots[0], expected);
    }

    /// A nonexistent path fails canonicalize and surfaces as
    /// `FilesExecError::Io`. The pre-existing allowlist must be left
    /// untouched.
    #[tokio::test]
    async fn update_allowlist_from_paths_rejects_nonexistent() {
        let dir = TempDir::new().unwrap();
        let exec = exec_for(&dir);
        let original = exec.scope.read().unwrap().clone();

        let bogus = dir.path().join("does-not-exist-ever");
        let err = exec.update_allowlist_from_paths([bogus]).unwrap_err();
        assert!(matches!(err, FilesExecError::Io(_)), "got {err:?}");

        let after = exec.scope.read().unwrap().clone();
        assert_eq!(original, after, "failed update must not mutate scope");
    }

    /// Cloning the executor shares allowlist state via `Arc`. Mutating
    /// scope on one clone must be observed by all the others.
    #[tokio::test]
    async fn clone_shares_allowlist_state() {
        let exec = StdFsExecutor::default();
        let twin = exec.clone();

        let dir = TempDir::new().unwrap();
        let path = dir.path().join("shared.txt");
        std::fs::write(&path, b"shared").unwrap();
        let canonical = std::fs::canonicalize(dir.path()).unwrap();

        // Mutate via the clone.
        twin.set_allowlist(ScopeAllowlist::new([canonical]));

        // The original sees the new scope.
        let bytes = exec.read(&path).await.unwrap();
        assert_eq!(bytes, b"shared");
    }

    /// Concurrency smoke: N readers race a writer that swaps
    /// equivalent allowlists. Reads must all succeed and no thread may
    /// deadlock or panic. Bounded iterations keep the test
    /// deterministic.
    #[tokio::test]
    async fn concurrent_reads_and_set_allowlist_dont_deadlock() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("c.txt");
        std::fs::write(&path, b"concurrent").unwrap();
        let canonical_a = std::fs::canonicalize(dir.path()).unwrap();
        // `canonical_b` is identical to `canonical_a` — both authorize
        // the same file. We swap between two equivalent allowlists so
        // every read is guaranteed to remain in-scope regardless of
        // which scope was live at canonicalize time.
        let canonical_b = canonical_a.clone();

        let exec = StdFsExecutor::new(ScopeAllowlist::new([canonical_a.clone()]));

        let writer_exec = exec.clone();
        let writer = tokio::spawn(async move {
            for i in 0..50usize {
                let scope = if i % 2 == 0 {
                    ScopeAllowlist::new([canonical_a.clone()])
                } else {
                    ScopeAllowlist::new([canonical_b.clone()])
                };
                writer_exec.set_allowlist(scope);
                tokio::task::yield_now().await;
            }
        });

        let mut readers = Vec::new();
        for _ in 0..4 {
            let exec = exec.clone();
            let path = path.clone();
            readers.push(tokio::spawn(async move {
                for _ in 0..50usize {
                    let bytes = exec.read(&path).await.expect("read should succeed");
                    assert_eq!(bytes, b"concurrent");
                    tokio::task::yield_now().await;
                }
            }));
        }

        writer.await.expect("writer task panicked");
        for r in readers {
            r.await.expect("reader task panicked");
        }
    }

    /// On a thread without a Tokio runtime, every method must
    /// self-degrade to `BackendDisabled` rather than panicking inside
    /// `tokio::fs`. Mirrors the playwright slice's runtime check
    /// (e2690d5).
    #[test]
    fn runtime_absent_yields_backend_disabled() {
        std::thread::spawn(|| {
            // No tokio runtime in this thread.
            let exec = StdFsExecutor::default();
            // Build a tiny ad-hoc poll loop so we can drive the future
            // to completion without borrowing a tokio runtime.
            use std::future::Future;
            use std::sync::Arc;
            use std::task::{Context, Poll, Wake, Waker};
            struct NoopWaker;
            impl Wake for NoopWaker {
                fn wake(self: Arc<Self>) {}
            }
            let waker = Waker::from(Arc::new(NoopWaker));
            let mut ctx = Context::from_waker(&waker);
            let fut = exec.read(Path::new("/anywhere"));
            let mut fut = Box::pin(fut);
            let result = loop {
                match fut.as_mut().poll(&mut ctx) {
                    Poll::Ready(v) => break v,
                    Poll::Pending => {
                        // Should NOT pend — `require_runtime()` returns
                        // synchronously. If we ever reach Pending here,
                        // the self-degrade has regressed.
                        panic!("require_runtime() should short-circuit synchronously");
                    }
                }
            };
            assert!(matches!(result, Err(FilesExecError::BackendDisabled)));
        })
        .join()
        .unwrap();
    }
}
