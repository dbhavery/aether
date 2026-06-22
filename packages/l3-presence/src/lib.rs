//! # aether-l3-presence
//!
//! **Status:** Wave 4 stub.
//!
//! L3 owns the presence controller: behavior scheduling, viseme timing,
//! listening / thinking / speaking posture choices. Borrowed rendering
//! surface; custom control plane.
//! Source: `ARCHITECTURE.md`.

#![deny(unsafe_code)]
#![warn(missing_docs)]
#![allow(dead_code)]

pub mod engine;
pub mod error;

pub use engine::{BehaviorClass, BehaviorFrame, PresenceEngine, PresenceTier, RenderingSurface};
pub use error::L3Error;
