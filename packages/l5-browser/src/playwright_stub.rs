//! Default browser backend — Playwright via subprocess.
//!
//! **Stub only.** This module is gated behind the `playwright` feature
//! so default builds do not pull subprocess / transport infrastructure.
//! Every method on [`PlaywrightExecutor`] currently returns
//! [`BrowserExecError::BackendDisabled`]; the real Node-subprocess
//! wiring lands in a later slice per T1.3 §5.1 (locked sub-decision:
//! Playwright as the backend, cross-platform, headless-safe, no
//! WebView2 coupling, no CDP-direct re-implementation).
//!
//! # Planned shape (NOT implemented)
//!
//! - Spawn a long-lived Node child process running a thin Playwright
//!   driver script.
//! - Frame requests/responses over stdio with length-prefixed JSON.
//! - Track sessions in a `HashMap<SessionId, BrowserContext>`.
//! - Surface backend errors as typed [`BrowserExecError`] variants
//!   (`Navigation`, `SelectorNotFound`, `Timeout`, `Internal`).
//!
//! Until then, this struct exists so the trait surface compiles and
//! integrators can wire `Arc<dyn BrowserExecutor>` end-to-end and see
//! `BackendDisabled` propagate cleanly.

use async_trait::async_trait;

use crate::executor::BrowserExecutor;
use crate::types::{BrowserExecError, FormField, PageSnapshot, SessionId};

/// Playwright-backed [`BrowserExecutor`] — stub today, real subprocess
/// driver in a later slice.
///
/// Constructed via [`PlaywrightExecutor::new`]. Holds no state today;
/// the real impl will hold the Node-subprocess handle and the live
/// session map.
#[derive(Debug, Default)]
pub struct PlaywrightExecutor {
    // Future: subprocess handle, session map, IPC framer, etc.
    _private: (),
}

impl PlaywrightExecutor {
    /// Construct a new Playwright executor.
    ///
    /// Today this is a no-op constructor; the real impl will spawn the
    /// Node subprocess and verify the driver handshake here, returning
    /// an error if Playwright is not installed.
    pub fn new() -> Self {
        Self { _private: () }
    }
}

#[async_trait]
impl BrowserExecutor for PlaywrightExecutor {
    async fn open(&self, _url: &str) -> Result<SessionId, BrowserExecError> {
        Err(BrowserExecError::BackendDisabled)
    }

    async fn navigate(
        &self,
        _session: SessionId,
        _url: &str,
    ) -> Result<(), BrowserExecError> {
        Err(BrowserExecError::BackendDisabled)
    }

    async fn read_page(
        &self,
        _session: SessionId,
    ) -> Result<PageSnapshot, BrowserExecError> {
        Err(BrowserExecError::BackendDisabled)
    }

    async fn extract(
        &self,
        _session: SessionId,
        _selector: &str,
    ) -> Result<Vec<String>, BrowserExecError> {
        Err(BrowserExecError::BackendDisabled)
    }

    async fn fill_form(
        &self,
        _session: SessionId,
        _fields: &[FormField],
    ) -> Result<(), BrowserExecError> {
        Err(BrowserExecError::BackendDisabled)
    }

    async fn submit(
        &self,
        _session: SessionId,
        _selector: &str,
    ) -> Result<(), BrowserExecError> {
        Err(BrowserExecError::BackendDisabled)
    }

    async fn close(&self, _session: SessionId) -> Result<(), BrowserExecError> {
        Err(BrowserExecError::BackendDisabled)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sid() -> SessionId {
        SessionId::new("test-session")
    }

    /// Build a single-threaded runtime for these stub-only tests
    /// without taking a tokio dep — a tiny block-on poll loop is
    /// enough since every method returns immediately.
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

    #[test]
    fn open_returns_backend_disabled() {
        let exec = PlaywrightExecutor::new();
        let err = block_on(exec.open("https://example.com")).unwrap_err();
        assert!(matches!(err, BrowserExecError::BackendDisabled));
    }

    #[test]
    fn navigate_returns_backend_disabled() {
        let exec = PlaywrightExecutor::new();
        let err = block_on(exec.navigate(sid(), "https://example.com")).unwrap_err();
        assert!(matches!(err, BrowserExecError::BackendDisabled));
    }

    #[test]
    fn read_page_returns_backend_disabled() {
        let exec = PlaywrightExecutor::new();
        let err = block_on(exec.read_page(sid())).unwrap_err();
        assert!(matches!(err, BrowserExecError::BackendDisabled));
    }

    #[test]
    fn extract_returns_backend_disabled() {
        let exec = PlaywrightExecutor::new();
        let err = block_on(exec.extract(sid(), "h1")).unwrap_err();
        assert!(matches!(err, BrowserExecError::BackendDisabled));
    }

    #[test]
    fn fill_form_returns_backend_disabled() {
        let exec = PlaywrightExecutor::new();
        let fields = [FormField {
            selector: "#name".into(),
            value: "Don".into(),
        }];
        let err = block_on(exec.fill_form(sid(), &fields)).unwrap_err();
        assert!(matches!(err, BrowserExecError::BackendDisabled));
    }

    #[test]
    fn submit_returns_backend_disabled() {
        let exec = PlaywrightExecutor::new();
        let err = block_on(exec.submit(sid(), "#submit")).unwrap_err();
        assert!(matches!(err, BrowserExecError::BackendDisabled));
    }

    #[test]
    fn close_returns_backend_disabled() {
        let exec = PlaywrightExecutor::new();
        let err = block_on(exec.close(sid())).unwrap_err();
        assert!(matches!(err, BrowserExecError::BackendDisabled));
    }
}
