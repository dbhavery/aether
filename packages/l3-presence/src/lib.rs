//! # aether-l3-presence
//!
//! **Status:** Wave 4 stub.
//!
//! L3 owns the presence controller: behavior scheduling, viseme timing,
//! listening / thinking / speaking posture choices. Borrowed rendering
//! surface; custom control plane.
//! Source: `ARCHITECTURE.md` (the L3 presence layer).

#![deny(unsafe_code)]
#![warn(missing_docs)]
#![allow(dead_code)]

pub mod attention;
pub mod bridge;
pub mod controller;
pub mod engine;
pub mod error;
pub mod runtime;

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
pub use runtime::{
    AudioStreamHandle, BoxedRendererController, LogStubRenderer, MotionClipId,
    MotionClipLibraryHandle, Renderer, RendererEvent, RenderingPresenceController,
    RENDERER_EVENT_LOG_CAP,
};
