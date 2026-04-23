//! # aether-l3-presence
//!
//! **Status:** Wave 4 stub.
//!
//! L3 owns the presence controller: behavior scheduling, viseme timing,
//! listening / thinking / speaking posture choices. Borrowed rendering
//! surface; custom control plane.
//! Source: `planning/plans/L3_presence_engine_system_design.md`,
//! `planning/plans/implementation_prep/L3_interface_pack.md`.

#![deny(unsafe_code)]
#![warn(missing_docs)]
#![allow(dead_code)]

pub mod attention;
pub mod bridge;
pub mod controller;
pub mod engine;
pub mod error;

pub use attention::{
    AttentionEvent, AttentionSnapshot, AttentionThresholds, UserAttention, UserAttentionController,
};
pub use bridge::behavior_for_presence;
pub use controller::{
    render_presence, InMemoryPresenceController, PresenceController, PresenceSnapshot,
    PresenceState, TRANSITION_LOG_CAP,
};
pub use engine::{BehaviorClass, BehaviorFrame, PresenceEngine, PresenceTier, RenderingSurface};
pub use error::L3Error;
