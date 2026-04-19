//! `InteractionEngine` trait surface + the five adapter traits it consumes.
//!
//! Source: L5_interface_pack.md §6.1 (producer relationship) and
//! L1_interface_pack.md (authoritative) — 19-state `TurnState`, 14 events,
//! reflex-classifier pseudocode, 12 timing budgets.

use serde::{Deserialize, Serialize};

use aether_l5_policy::{Capability, Decision, ResourceScope};

use crate::error::L1Error;

/// Turn id correlating a single utterance-to-final-speech arc.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct TurnId(pub String);

/// 19-state turn state machine. Wave 4 surfaces the canonical names; the full
/// transition diagram lives in the system design doc.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TurnState {
    /// No active turn.
    Idle,
    /// VAD detected speech.
    Listening,
    /// User stopped; waiting on STT final.
    EndOfUserSpeech,
    /// Reflex classifier working.
    ReflexClassifying,
    /// Ack phrase playing.
    ReflexAck,
    /// Full deliberative route decided.
    DeliberativeThinking,
    /// Router dispatched to local or remote.
    RouterDispatched,
    /// Tool plan awaiting policy approval.
    AwaitingPolicyApproval,
    /// Policy denied the plan.
    PolicyDenied,
    /// Tool call executing.
    ToolExecuting,
    /// Tool call completed.
    ToolCompleted,
    /// Output drafting.
    Drafting,
    /// TTS speaking.
    Speaking,
    /// User barge-in mid-speech.
    BargeIn,
    /// Repair flow after error.
    Repairing,
    /// Explicit deflection (persona safety etc.).
    Deflected,
    /// Turn gracefully completed.
    Completed,
    /// Timeout without user response.
    TimedOut,
    /// Error surfaced to UI.
    Errored,
}

/// Reflex-classifier output. See L1 §reflex-classifier.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ReflexClass {
    /// Ack only; no deliberative path.
    AckOnly,
    /// Short templated reply, no tool use.
    ShortReply,
    /// Defer to deliberative deliberation.
    Deliberative,
    /// Safety deflection.
    Deflect,
}

/// Timing budgets consumed across a turn. Values are monotonic nanoseconds.
#[derive(Debug, Clone, Copy)]
pub struct TimingBudgets {
    /// Time budget for reflex classification.
    pub reflex_ns: u64,
    /// Time budget for end-of-speech detection → ack.
    pub ack_ns: u64,
    /// Time budget for policy evaluate (matches L5 p95).
    pub policy_ns: u64,
    /// Time budget for router dispatch.
    pub router_ns: u64,
    /// Time budget for first audible speech.
    pub first_speech_ns: u64,
}

impl Default for TimingBudgets {
    /// Defaults from L1_interface_pack.md §12 (flagged DELAYS).
    fn default() -> Self {
        Self {
            reflex_ns: 150_000_000,
            ack_ns: 120_000_000,
            policy_ns: 20_000_000,
            router_ns: 80_000_000,
            first_speech_ns: 700_000_000,
        }
    }
}

/// Reflex classifier adapter. A real implementation is a tiny local
/// transformer / hand-rolled rule set.
pub trait ReflexClassifier: Send + Sync {
    /// Classify an in-progress utterance. Must return within
    /// `TimingBudgets::reflex_ns`.
    fn classify(&self, partial_transcript: &str) -> Result<ReflexClass, L1Error>;
}

/// Streaming STT adapter.
pub trait Stt: Send + Sync {
    /// Deliver the next audio frame. Returns any chunks ready for consumption.
    fn push_audio(&self, pcm: &[i16]) -> Result<Vec<String>, L1Error>;
    /// Flush final transcript.
    fn finalize(&self) -> Result<Option<String>, L1Error>;
}

/// Streaming TTS adapter.
pub trait Tts: Send + Sync {
    /// Synthesize a chunk of text; returns a stream of audio bytes + visemes.
    fn speak(&self, text: &str) -> Result<(), L1Error>;
    /// Interrupt any in-flight synthesis (barge-in).
    fn interrupt(&self) -> Result<(), L1Error>;
}

/// L4 model-router client from L1's perspective.
pub trait ModelRouterClient: Send + Sync {
    /// Hand off a turn for deliberative handling.
    fn dispatch(&self, turn_id: &TurnId, prompt: &str) -> Result<(), L1Error>;
}

/// L3 presence client from L1's perspective.
pub trait PresenceClient: Send + Sync {
    /// Notify L3 of a turn-state transition so presence can react.
    fn on_turn_state(&self, turn_id: &TurnId, state: TurnState) -> Result<(), L1Error>;
}

/// Core interaction engine trait. Synchronous surface over async internals
/// managed by the implementation.
pub trait InteractionEngine: Send + Sync {
    /// Begin a new turn. Returns the allocated `TurnId`.
    fn start_turn(&self) -> Result<TurnId, L1Error>;

    /// Deliver a partial STT transcript to the reflex classifier.
    fn handle_partial_transcript(&self, turn_id: &TurnId, text: &str) -> Result<(), L1Error>;

    /// Feed a policy decision back into the turn state machine. Called by the
    /// router / policy gate after `evaluate`.
    fn on_policy_decision(
        &self,
        turn_id: &TurnId,
        capability: &Capability,
        resource: &ResourceScope,
        decision: &Decision,
    ) -> Result<(), L1Error>;

    /// Mark a turn as completed (normal path or errored).
    fn end_turn(&self, turn_id: &TurnId) -> Result<(), L1Error>;

    /// Current state of a turn, if live.
    fn state(&self, turn_id: &TurnId) -> Option<TurnState>;
}
