//! L5 browser-automation capability surface.
//!
//! **Status (T1.3 first impl slice):** Trait + types are now real, plus
//! a capability map and a default Playwright backend stub. Every stub
//! method returns [`BrowserExecError::BackendDisabled`]; the real
//! subprocess wiring (Node Playwright driver) lands in a later slice.
//!
//! # Surface
//!
//! - [`BrowserExecutor`] — object-safe async trait every backend
//!   implements.
//! - [`SessionId`], [`PageSnapshot`], [`FormField`], [`BrowserExecError`]
//!   — the value types the trait operates on.
//! - [`capability_for_method`] — maps trait method names to existing
//!   variants on [`aether_l5_policy::Capability`]. The integration
//!   point where future Tauri commands check L5 policy BEFORE invoking
//!   the executor.
//! - [`playwright_stub::PlaywrightExecutor`] — default backend. Gated
//!   behind the `playwright` feature; every method returns
//!   [`BrowserExecError::BackendDisabled`] today.
//!
//! # Layer rules
//!
//! Per CLAUDE.md §1.4 + §1.5, this crate:
//!
//! - extends the existing capability surface in
//!   [`aether_l5_policy`] additively (new variants already landed in
//!   [`Capability`](aether_l5_policy::Capability));
//! - does not perform its own policy check — call sites resolve a
//!   [`Capability`](aether_l5_policy::Capability) via
//!   [`capability_for_method`], ask L5 for `Decision::Allow`, and only
//!   then invoke a method on `dyn BrowserExecutor`.
//!
//! # Scope (frozen by Don 2026-04-30)
//!
//! - L5-gated browser automation: `BrowserOpen`, `BrowserReadPage`,
//!   `BrowserExtractData`, `BrowserFillForm`, `BrowserSubmit` (and the
//!   `BrowserUpload` / `BrowserDownload` / `BrowserLoginReuse`
//!   capabilities for later slices).
//! - Backend: Playwright via subprocess. Cross-platform, headless-safe.
//!   No WebView2 coupling, no CDP-direct re-implementation.
//! - Approval mode follows the active autonomy preset:
//!   - **Observer** — Deny.
//!   - **Assistant** — Ask (read), Ask (click/fill/submit/login).
//!   - **Operator** — Auto for navigation + read, Ask for write/submit/login.
//!   - **Power User** — additionally permits per-session grants.
//! - Outside-list nav drops to Ask in Operator mode (never silently
//!   navigates somewhere it wasn't told to).
//! - **No credential persistence.** OS keychain integration is a
//!   separate later slice with its own threat-model review.
//!
//! # References
//!
//! - `ARCHITECTURE.md` — the L5 policy layer, the approved browser/file
//!   workflow, and the ApprovalScope design (this slice does NOT implement
//!   new approval modes; it only makes the executor surface compatible with
//!   existing modes).
//! - `ARCHITECTURE.md` + `docs/adr/` — the "Power User / Builder" user-tier
//!   rules this surface honors.
//! - [`aether_l5_policy::Capability`] — the additive surface this crate
//!   plugs into.

#![forbid(unsafe_code)]

pub mod capability_map;
pub mod executor;
#[cfg(feature = "playwright")]
pub mod playwright_stub;
pub mod types;

pub use capability_map::capability_for_method;
pub use executor::BrowserExecutor;
pub use types::{BrowserExecError, FormField, PageSnapshot, SessionId};
