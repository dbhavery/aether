//! # aether-l5-browser — L5-gated browser-automation surface
//!
//! **Status:** Skeleton-only (T1.3 first slice, 2026-04-30). Zero logic.
//! Implementation lands in follow-up PRs.
//!
//! ## What this crate will be
//!
//! The L5-gated surface for browser-automation primitives:
//! `BrowserOpen`, `BrowserNavigate`, `BrowserClick`, `BrowserFillForm`,
//! `BrowserExtract`, `BrowserScreenshot`. Each primitive will be a
//! `Capability` declared additively under
//! [`aether-l5-policy`](../l5_policy/index.html)'s existing `Capability`
//! enum — no policy-engine reshape required.
//!
//! Backend is locked to **Playwright via subprocess** (cross-platform,
//! mature, headless-safe). See T1.3 proposal §7 for the locked decision.
//!
//! ## Scope ceiling (locked, T1.3 §2.1)
//!
//! - read + click + fill + extract
//! - **no** credential persistence
//! - **no** off-list navigation in Operator mode (must drop to Ask)
//! - **no** auto-submit on financial / auth / purchase pages
//!   (hard-blocked unless Power User + per-action confirm — Critical risk
//!   class per `planning/12_permissions_autonomy.md` §"Risk classes")
//!
//! ## Source-of-truth docs
//!
//! - `planning/plans/T1.3_browser_file_workflow_proposal.md` §2.1 — crate
//!   scope, primitives, scope ceiling
//! - `planning/12_permissions_autonomy.md` §"Power User / Builder" — the
//!   autonomy preset this surface is designed to serve
//! - `docs/adr/ADR-0009-*.md` and the `aether-l5-policy::Capability` enum —
//!   capability declarations slot in additively under existing policy
//!   doctrine; no ADR change required (T1.3 §3)
//! - `CLAUDE.md` §3 — package-creation protocol (this commit is the
//!   skeleton step)
//!
//! ## Why nothing here yet
//!
//! Per `CLAUDE.md` §3: "scaffolds the package skeleton: manifest entry,
//! empty lib target, README, CODEOWNERS line. Zero logic." Implementation
//! arrives in separate slices per the T1.3 sequencing.

#![deny(unsafe_code)]
#![warn(missing_docs)]
// Skeleton allows — placeholder enum exists without callers yet.
#![allow(dead_code)]

/// Placeholder for the browser-automation capability surface.
///
/// Intentionally uninhabited: this skeleton exists so that
/// `cargo build -p aether-l5-browser` produces an artifact and the
/// workspace check passes. The real variants (`Open`, `Navigate`,
/// `Click`, `FillForm`, `Extract`, `Screenshot`) land in the
/// follow-up implementation PR alongside the `aether-l5-policy`
/// `Capability` extensions described in T1.3 §2.1.
pub enum BrowserCapability {}
