//! L3 presence → avatar-behavior bridge.
//!
//! Thin, stateless mapping from the macro [`PresenceState`] emitted by
//! [`PresenceController`] (the "quiet / listening / thinking /
//! awaiting-approval / responding" lifecycle used by L1 turns) to the
//! frame-rate [`BehaviorClass`] enum consumed by the avatar / rendering
//! surface.
//!
//! ## Why this is a separate module
//!
//! There is no real avatar yet. When one lands — Three.js, Unreal, a
//! GLTF rig, anything — it will need to know which of the nine Wave-4
//! `BehaviorClass` variants to play whenever the presence controller
//! fires a macro transition. Without this bridge, that avatar would
//! have to recreate the mapping inside its own code, drifting away
//! from the canonical one here.
//!
//! The bridge is **stateless**, **deterministic**, and **total** — it
//! maps every `PresenceState` to exactly one `BehaviorClass`. That
//! keeps the surface area that an avatar maintainer has to understand
//! small, and lets us test it as a pure function.
//!
//! Future avatar-side work (blink cadence, gaze control, lip-sync,
//! viseme drivers) happens inside the `BehaviorClass` vocabulary and
//! does not need to know anything about `PresenceState`.
//!
//! ## Mapping rules
//!
//! | `PresenceState`      | `BehaviorClass` | Rationale |
//! |----------------------|-----------------|-----------|
//! | Quiet                | Idle            | Default — subtle breathing / blink cadence. |
//! | Listening            | Listening       | Gaze locked to user during input. |
//! | Thinking             | Thinking        | Soft look-away during routing / model call. |
//! | AwaitingApproval     | Deflecting      | Polite hold posture while the user decides on an Ask. Not Thinking (model is not actually running) and not Idle (there's an open request). |
//! | Responding           | Speaking        | Lip-sync + expression beats during reply. |
//!
//! ## Non-goals for this slice
//!
//! - No feedback in the opposite direction (behavior class → presence
//!   state). The engine fans in, it doesn't round-trip.
//! - No sub-state nuance (no `BargingIn`, no `Emphasizing`, etc.).
//!   Those are driven by per-frame behavior scheduling, not by the
//!   five-state macro lifecycle.
//! - No explicit timing / duration information. The bridge is a pure
//!   function of the current macro state.

use crate::controller::PresenceState;
use crate::engine::BehaviorClass;

/// Map a macro [`PresenceState`] to the avatar-side [`BehaviorClass`]
/// that best represents it. Total and deterministic — see the
/// module-level docs for the rationale behind each arm.
pub fn behavior_for_presence(state: PresenceState) -> BehaviorClass {
    match state {
        PresenceState::Quiet => BehaviorClass::Idle,
        PresenceState::Listening => BehaviorClass::Listening,
        PresenceState::Thinking => BehaviorClass::Thinking,
        PresenceState::AwaitingApproval => BehaviorClass::Deflecting,
        PresenceState::Responding => BehaviorClass::Speaking,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mapping_is_total_and_expected() {
        assert_eq!(
            behavior_for_presence(PresenceState::Quiet),
            BehaviorClass::Idle
        );
        assert_eq!(
            behavior_for_presence(PresenceState::Listening),
            BehaviorClass::Listening
        );
        assert_eq!(
            behavior_for_presence(PresenceState::Thinking),
            BehaviorClass::Thinking
        );
        assert_eq!(
            behavior_for_presence(PresenceState::AwaitingApproval),
            BehaviorClass::Deflecting
        );
        assert_eq!(
            behavior_for_presence(PresenceState::Responding),
            BehaviorClass::Speaking
        );
    }

    #[test]
    fn awaiting_approval_is_not_thinking_or_idle() {
        // Encoded as a guard against accidental future rewrites that
        // collapse AwaitingApproval into Thinking (wrong — the model
        // is not running) or Idle (wrong — there is an open request).
        let b = behavior_for_presence(PresenceState::AwaitingApproval);
        assert_ne!(b, BehaviorClass::Thinking);
        assert_ne!(b, BehaviorClass::Idle);
    }

    #[test]
    fn mapping_is_deterministic() {
        for _ in 0..10 {
            assert_eq!(
                behavior_for_presence(PresenceState::Thinking),
                BehaviorClass::Thinking
            );
        }
    }
}
