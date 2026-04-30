//! Default file-workflow backend — `std::fs` / `tokio::fs`.
//!
//! **Stub only.** This module is gated behind the `std-fs` feature so
//! default builds do not pull `tokio::fs` (or any other fs runtime).
//! Every method on [`StdFsExecutor`] currently returns
//! [`FilesExecError::BackendDisabled`]; the real `std::fs` /
//! `tokio::fs` wiring lands in a later slice per T1.3 §2.2.
//!
//! # Planned shape (NOT implemented)
//!
//! - Hold a [`ScopeAllowlist`](crate::types::ScopeAllowlist) and
//!   canonicalize every input path before authorization.
//! - Use atomic write-to-temp + rename for `create` / `edit`.
//! - Use `tokio::fs` (or `std::fs` behind `spawn_blocking`) to keep
//!   the executor non-blocking under the Tauri runtime.
//! - Implement `grep` as a streaming line scanner over the approved
//!   roots; no persistent index in this slice.
//!
//! Until then, this struct exists so the trait surface compiles and
//! integrators can wire `Arc<dyn FilesExecutor>` end-to-end and see
//! `BackendDisabled` propagate cleanly.

use std::path::Path;

use async_trait::async_trait;

use crate::executor::FilesExecutor;
use crate::types::{FilesExecError, GrepHit};

/// `std::fs`-backed [`FilesExecutor`] — stub today, real
/// `std::fs` / `tokio::fs` wiring in a later slice.
///
/// Constructed via [`StdFsExecutor::new`]. Holds no state today; the
/// real impl will hold the active
/// [`ScopeAllowlist`](crate::types::ScopeAllowlist) and any
/// blocking-task pool handle it needs.
#[derive(Debug, Default)]
pub struct StdFsExecutor {
    // Future: scope allowlist, blocking-pool handle, audit hook, etc.
    _private: (),
}

impl StdFsExecutor {
    /// Construct a new `std::fs` executor.
    ///
    /// Today this is a no-op constructor; the real impl will accept a
    /// [`ScopeAllowlist`](crate::types::ScopeAllowlist) and any
    /// runtime handles it needs.
    pub fn new() -> Self {
        Self { _private: () }
    }
}

#[async_trait]
impl FilesExecutor for StdFsExecutor {
    async fn read(&self, _path: &Path) -> Result<Vec<u8>, FilesExecError> {
        Err(FilesExecError::BackendDisabled)
    }

    async fn create(
        &self,
        _path: &Path,
        _contents: &[u8],
    ) -> Result<(), FilesExecError> {
        Err(FilesExecError::BackendDisabled)
    }

    async fn edit(
        &self,
        _path: &Path,
        _contents: &[u8],
    ) -> Result<(), FilesExecError> {
        Err(FilesExecError::BackendDisabled)
    }

    async fn rename(
        &self,
        _src: &Path,
        _dst: &Path,
    ) -> Result<(), FilesExecError> {
        Err(FilesExecError::BackendDisabled)
    }

    async fn delete(&self, _path: &Path) -> Result<(), FilesExecError> {
        Err(FilesExecError::BackendDisabled)
    }

    async fn grep(
        &self,
        _root: &Path,
        _pattern: &str,
    ) -> Result<Vec<GrepHit>, FilesExecError> {
        Err(FilesExecError::BackendDisabled)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    /// Build a single-threaded poll loop for these stub-only tests
    /// without taking a tokio dep — every method returns immediately.
    fn block_on<F: std::future::Future>(fut: F) -> F::Output {
        use std::sync::Arc;
        use std::task::{Context, Poll, Wake, Waker};

        struct NoopWaker;
        impl Wake for NoopWaker {
            fn wake(self: Arc<Self>) {}
        }
        let waker = Waker::from(Arc::new(NoopWaker));
        let mut ctx = Context::from_waker(&waker);
        let mut fut = Box::pin(fut);
        loop {
            if let Poll::Ready(v) = fut.as_mut().poll(&mut ctx) {
                return v;
            }
        }
    }

    fn p() -> PathBuf {
        PathBuf::from("/tmp/aether-stub-test")
    }

    #[test]
    fn read_returns_backend_disabled() {
        let exec = StdFsExecutor::new();
        let err = block_on(exec.read(&p())).unwrap_err();
        assert!(matches!(err, FilesExecError::BackendDisabled));
    }

    #[test]
    fn create_returns_backend_disabled() {
        let exec = StdFsExecutor::new();
        let err = block_on(exec.create(&p(), b"hello")).unwrap_err();
        assert!(matches!(err, FilesExecError::BackendDisabled));
    }

    #[test]
    fn edit_returns_backend_disabled() {
        let exec = StdFsExecutor::new();
        let err = block_on(exec.edit(&p(), b"hello")).unwrap_err();
        assert!(matches!(err, FilesExecError::BackendDisabled));
    }

    #[test]
    fn rename_returns_backend_disabled() {
        let exec = StdFsExecutor::new();
        let err = block_on(exec.rename(&p(), &PathBuf::from("/tmp/dst"))).unwrap_err();
        assert!(matches!(err, FilesExecError::BackendDisabled));
    }

    #[test]
    fn delete_returns_backend_disabled() {
        let exec = StdFsExecutor::new();
        let err = block_on(exec.delete(&p())).unwrap_err();
        assert!(matches!(err, FilesExecError::BackendDisabled));
    }

    #[test]
    fn grep_returns_backend_disabled() {
        let exec = StdFsExecutor::new();
        let err = block_on(exec.grep(&p(), "TODO")).unwrap_err();
        assert!(matches!(err, FilesExecError::BackendDisabled));
    }
}
