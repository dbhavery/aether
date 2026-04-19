//! `PresenceEngine` + `RenderingSurface` traits.

use serde::{Deserialize, Serialize};

use crate::error::L3Error;

/// Presence tier (Lite / Balanced / Pro) — maps to VRAM budget.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PresenceTier {
    /// 2D or minimal avatar.
    Lite,
    /// Full presence stack, moderate cost.
    Balanced,
    /// Highest fidelity.
    Pro,
}

/// Nine behavior classes per L3 interface pack §3.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum BehaviorClass {
    /// Idle — subtle breathing, blink cadence.
    Idle,
    /// Listening — gaze locked to user.
    Listening,
    /// Thinking — soft look-away, micro-frown.
    Thinking,
    /// Speaking — lip-sync + expression beats.
    Speaking,
    /// Barge-in handling.
    BargingIn,
    /// Emphatic emphasis beat.
    Emphasizing,
    /// Polite deflection posture.
    Deflecting,
    /// Repair / clarifying.
    Repairing,
    /// Signing off / closing.
    SigningOff,
}

/// A single frame of presence-layer instructions produced by the scheduler.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BehaviorFrame {
    /// Monotonic nanoseconds since presence init.
    pub t_ns: u64,
    /// Active behavior.
    pub behavior: BehaviorClass,
    /// Target blink intensity (0.0–1.0).
    pub blink: f32,
    /// Target gaze vector in normalized eye-space.
    pub gaze: (f32, f32),
    /// Mouth open-amount (0.0–1.0) — lip-sync driver.
    pub mouth: f32,
    /// Optional viseme id aligned to the current TTS chunk.
    pub viseme: Option<String>,
}

/// Rendering-surface adapter. Concrete impls wrap Three.js / Unreal / custom.
pub trait RenderingSurface: Send + Sync {
    /// Push a `BehaviorFrame` to the rendering backend.
    fn submit(&self, frame: &BehaviorFrame) -> Result<(), L3Error>;
    /// Set tier (may reconfigure the renderer).
    fn set_tier(&self, tier: PresenceTier) -> Result<(), L3Error>;
}

/// Presence-engine surface consumed by L1 (turn-state updates) and the TTS
/// pipeline (viseme timing).
pub trait PresenceEngine: Send + Sync {
    /// Notify presence of a turn-state transition (pairs with L1).
    fn on_turn_state(&self, state: crate::engine::BehaviorClass) -> Result<(), L3Error>;
    /// Produce the next `BehaviorFrame`. Typically called at 30–60 Hz by the
    /// renderer. Returns `None` if the scheduler is idle.
    fn next_frame(&self, now_ns: u64) -> Result<Option<BehaviorFrame>, L3Error>;
    /// Configure the active tier.
    fn set_tier(&self, tier: PresenceTier) -> Result<(), L3Error>;
}
