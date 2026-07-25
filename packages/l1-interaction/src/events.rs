//! L1 event family (14 events per L1 interface pack §4). Wave 4 names the
//! canonical events; per-event payloads expand in Wave 5+.

use serde::{Deserialize, Serialize};

use crate::engine::{ReflexClass, TurnId, TurnState};

/// Discriminator used by `EventFilter` bitsets.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum InteractionEventKind {
    /// `turn_begin`
    TurnBegin,
    /// `turn_state_change`
    TurnStateChange,
    /// `intent_hint`
    IntentHint,
    /// `ack_phrase`
    AckPhrase,
    /// `reflex_classified`
    ReflexClassified,
    /// `route_decision` (producer-side echo from L4)
    RouteDecision,
    /// `tool_call_started`
    ToolCallStarted,
    /// `tool_call_completed`
    ToolCallCompleted,
    /// `repair_started`
    RepairStarted,
    /// `repair_resolved`
    RepairResolved,
    /// `barge_in`
    BargeIn,
    /// `turn_timeout`
    TurnTimeout,
    /// `turn_completed`
    TurnCompleted,
    /// `turn_errored`
    TurnErrored,
}

/// Sum type of L1 events. Wave 4 keeps each payload intentionally small;
/// expansion lives in Wave 5 when the turn loop is implemented.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum InteractionEvent {
    /// Turn started.
    TurnBegin { turn_id: TurnId },
    /// Turn state transitioned.
    TurnStateChange {
        /// Turn correlated.
        turn_id: TurnId,
        /// New state.
        state: TurnState,
    },
    /// Reflex classifier produced a class.
    ReflexClassified {
        /// Turn correlated.
        turn_id: TurnId,
        /// Class emitted.
        class: ReflexClass,
    },
    /// Turn completed successfully.
    TurnCompleted { turn_id: TurnId },
    /// Turn errored.
    TurnErrored {
        /// Turn correlated.
        turn_id: TurnId,
        /// Short reason code.
        reason: String,
    },
}

impl InteractionEvent {
    /// Flat discriminator.
    pub fn kind(&self) -> InteractionEventKind {
        match self {
            InteractionEvent::TurnBegin { .. } => InteractionEventKind::TurnBegin,
            InteractionEvent::TurnStateChange { .. } => InteractionEventKind::TurnStateChange,
            InteractionEvent::ReflexClassified { .. } => InteractionEventKind::ReflexClassified,
            InteractionEvent::TurnCompleted { .. } => InteractionEventKind::TurnCompleted,
            InteractionEvent::TurnErrored { .. } => InteractionEventKind::TurnErrored,
        }
    }
}
