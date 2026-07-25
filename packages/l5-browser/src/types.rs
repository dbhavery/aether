//! Supporting types for the [`BrowserExecutor`](crate::executor::BrowserExecutor)
//! trait surface.
//!
//! These types are intentionally minimal — just enough to express the
//! shape of a browser session, a page snapshot, a form-field write, and
//! the failure modes any backend will need to surface. Real fidelity
//! (DOM trees, accessibility roles, network logs) lands when the
//! Playwright subprocess wiring lands in a later slice.

use serde::{Deserialize, Serialize};
use thiserror::Error;

/// Opaque identifier for a live browser session.
///
/// The string contents are backend-defined (Playwright contexts return
/// UUIDs; future backends may use other shapes). Callers MUST treat this
/// as opaque and round-trip it through the [`BrowserExecutor`](crate::executor::BrowserExecutor)
/// surface only.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct SessionId(pub String);

impl SessionId {
    /// Construct a new `SessionId` from any string-like value.
    pub fn new(id: impl Into<String>) -> Self {
        Self(id.into())
    }

    /// Borrow the underlying identifier as a string slice.
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// A read-only snapshot of a browser page.
///
/// Returned from [`BrowserExecutor::read_page`](crate::executor::BrowserExecutor::read_page).
/// `text_content` is the visible text after JavaScript has settled; the
/// full DOM is intentionally not surfaced here — extraction lives behind
/// [`BrowserExecutor::extract`](crate::executor::BrowserExecutor::extract).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PageSnapshot {
    /// Final URL of the page after redirects.
    pub url: String,
    /// `<title>` element contents (may be empty).
    pub title: String,
    /// Visible text of the rendered page, post-JS.
    pub text_content: String,
    /// Wall-clock capture time, in milliseconds since the Unix epoch.
    pub captured_at_ms: u64,
}

/// A single form-field write request.
///
/// `selector` is interpreted by the backend (Playwright supports CSS,
/// text, role, and chained selectors). The `value` is written verbatim
/// — the executor does not interpret keystroke escapes.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FormField {
    /// Backend-specific selector identifying the input element.
    pub selector: String,
    /// Literal value to write into the field.
    pub value: String,
}

/// Failure modes for [`BrowserExecutor`](crate::executor::BrowserExecutor) calls.
///
/// Variants are deliberately coarse-grained at this stage; richer
/// diagnostics (network errors, HTTP status, retry hints) are added when
/// the real Playwright backend lands. Every variant is non-recoverable
/// at the policy boundary — L5 logs the failure and surfaces it to the
/// caller.
#[derive(Debug, Error)]
pub enum BrowserExecError {
    /// The supplied [`SessionId`] is not currently open in this executor.
    #[error("browser session not found: {0}")]
    SessionNotFound(String),

    /// Navigation failed — DNS, TLS, HTTP error, or the page never settled.
    #[error("navigation failed: {0}")]
    Navigation(String),

    /// The selector did not match any element on the page.
    #[error("selector not found: {0}")]
    SelectorNotFound(String),

    /// The operation exceeded the backend's wall-clock budget.
    #[error("browser operation timed out: {0}")]
    Timeout(String),

    /// The backend is compiled in but disabled at runtime — typically
    /// because the Playwright Node subprocess has not yet been wired up.
    /// This is the variant the [`playwright_stub`](crate::playwright_stub)
    /// module returns for every method today.
    #[error("browser backend is disabled (stub only)")]
    BackendDisabled,

    /// Catch-all for backend errors not yet promoted to a typed variant.
    #[error("internal browser-executor error: {0}")]
    Internal(String),
}
