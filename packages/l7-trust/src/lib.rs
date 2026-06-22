//! # aether-l7-trust
//!
//! **Status:** Wave 4 stub. **Backend surfaces only** — the React UI lives in
//! `apps/desktop/` (future wave). This crate owns the Rust side of the
//! trust-UX bridge: approval renderer hooks, posture banner hooks,
//! onboarding-state machine, shell-adapter trait.
//!
//! L7 reads L5 events (approval pending, posture changed, audit rows) and
//! exposes a small typed surface the desktop shell implements.
//!
//! Source: `ARCHITECTURE.md` and `docs/ONBOARDING-SPEC.md`.

#![deny(unsafe_code)]
#![warn(missing_docs)]
#![allow(dead_code)]

pub mod error;
pub mod shell;

pub use error::L7Error;
pub use shell::{ApprovalPrompt, OnboardingScreen, OnboardingState, PostureBanner, ShellAdapter};
