//! L5 browser-automation capability surface.
//!
//! **Skeleton only.** Per CLAUDE.md §3 (coordinator-gated package
//! creation), this crate ships in two PRs: this skeleton + later
//! implementation slices. Implementation lands in follow-up sessions
//! per the T1.3 sub-decisions.
//!
//! # Scope (frozen by Don 2026-04-30)
//!
//! - L5-gated browser automation: `BrowserOpen`, `BrowserNavigate`,
//!   `BrowserClick`, `BrowserFillForm`, `BrowserExtract`,
//!   `BrowserScreenshot`.
//! - Each primitive becomes a variant on the existing
//!   `aether_l5_policy::Capability` enum (additive; this crate does
//!   not fork the policy enum).
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
//! - `planning/plans/T1.3_browser_file_workflow_proposal.md` §2.1 — the
//!   Approved coordinator proposal. Status flipped to Approved
//!   2026-04-30 under Don's "1–5 are your decisions now" delegation.
//! - `planning/12_permissions_autonomy.md` §"Power User / Builder" —
//!   user-tier rules this surface honors.
//! - `aether_l5_policy::Capability` — the additive surface where new
//!   variants land.
//! - `tools/redteam/scenarios/browser_misuse/` — capability-specific
//!   adversarial scenarios. The credential-fill scenario currently
//!   stubbed (T2.2) unblocks once this crate's first impl PR lands.

#![forbid(unsafe_code)]

/// Placeholder browser-capability marker.
///
/// Implementation PRs replace this enum's empty variant set with the
/// real capabilities, which then map onto
/// `aether_l5_policy::Capability` additions. Today the type only
/// exists so `cargo build -p aether-l5-browser` produces a real
/// artifact and the workspace check passes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BrowserCapability {}
