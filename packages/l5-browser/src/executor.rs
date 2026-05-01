//! The [`BrowserExecutor`] trait — the object-safe async surface every
//! browser backend must implement.
//!
//! The trait is deliberately minimal: enough verbs to support the
//! existing capabilities in [`aether_l5_policy::Capability`] (`BrowserOpen`,
//! `BrowserReadPage`, `BrowserExtractData`, `BrowserFillForm`,
//! `BrowserSubmit`, etc.), and nothing more. Higher-level orchestration
//! (multi-step flows, retries, screenshot capture) is built on top by
//! callers, not baked into the trait.
//!
//! # Wiring
//!
//! L5 is the single writer for side effects (CLAUDE.md §1.5). Every
//! Tauri command that wants to drive a browser session resolves a
//! [`Capability`](aether_l5_policy::Capability) via the
//! [`capability_for_method`](crate::capability_map::capability_for_method)
//! helper, asks L5 for a `Decision::Allow`, and then — and only then —
//! calls the matching method on a `dyn BrowserExecutor`. The executor
//! itself does NOT perform any policy check; that responsibility lives
//! one layer up, by design.
//!
//! # Backends
//!
//! - [`playwright_stub::PlaywrightExecutor`](crate::playwright_stub::PlaywrightExecutor)
//!   — the default backend stub. Every method returns
//!   [`BrowserExecError::BackendDisabled`] today; the real subprocess
//!   wiring lands in a later slice.

use async_trait::async_trait;

use crate::types::{BrowserExecError, FormField, PageSnapshot, SessionId};

/// Object-safe async surface for driving a browser session.
///
/// Implementations MUST be `Send + Sync` so callers can store them as
/// `Arc<dyn BrowserExecutor>` and share them across Tauri command
/// handlers. Each method maps one-to-one onto an
/// [`aether_l5_policy::Capability`] variant via
/// [`capability_for_method`](crate::capability_map::capability_for_method).
#[async_trait]
pub trait BrowserExecutor: Send + Sync {
    /// Open a fresh browser session and navigate to `url`.
    ///
    /// Returns the [`SessionId`] for subsequent calls. Maps to
    /// [`Capability::BrowserOpen`](aether_l5_policy::Capability::BrowserOpen).
    async fn open(&self, url: &str) -> Result<SessionId, BrowserExecError>;

    /// Navigate an existing session to a new URL.
    ///
    /// Maps to [`Capability::BrowserOpen`](aether_l5_policy::Capability::BrowserOpen)
    /// in policy terms — a navigation IS a re-open from L5's perspective
    /// (the agent is asking to point a browser at a new origin), so the
    /// same scope-allowlist check applies.
    async fn navigate(&self, session: SessionId, url: &str) -> Result<(), BrowserExecError>;

    /// Read a snapshot of the current page contents.
    ///
    /// Maps to [`Capability::BrowserReadPage`](aether_l5_policy::Capability::BrowserReadPage).
    async fn read_page(&self, session: SessionId) -> Result<PageSnapshot, BrowserExecError>;

    /// Extract text values matching `selector` from the current page.
    ///
    /// The exact selector grammar is backend-defined. Maps to
    /// [`Capability::BrowserExtractData`](aether_l5_policy::Capability::BrowserExtractData).
    async fn extract(
        &self,
        session: SessionId,
        selector: &str,
    ) -> Result<Vec<String>, BrowserExecError>;

    /// Fill one or more form fields. Does NOT submit — submission goes
    /// through [`submit`](BrowserExecutor::submit) under a separate
    /// capability.
    ///
    /// Maps to [`Capability::BrowserFillForm`](aether_l5_policy::Capability::BrowserFillForm).
    async fn fill_form(
        &self,
        session: SessionId,
        fields: &[FormField],
    ) -> Result<(), BrowserExecError>;

    /// Submit a form, identified by `selector` (typically the form
    /// element or its submit button).
    ///
    /// Maps to [`Capability::BrowserSubmit`](aether_l5_policy::Capability::BrowserSubmit).
    async fn submit(&self, session: SessionId, selector: &str) -> Result<(), BrowserExecError>;

    /// Close the session and release its resources.
    ///
    /// No capability check is performed at this layer — closing a
    /// session is always permitted; cleanup must not be gateable. The
    /// capability-map helper returns `None` for `"close"` to make this
    /// explicit.
    async fn close(&self, session: SessionId) -> Result<(), BrowserExecError>;
}
