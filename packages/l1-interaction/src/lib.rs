//! # aether-l1-interaction
//!
//! **Status:** Wave 4 stub. Traits + key enums only. No turn loop, no reflex
//! classifier, no media plumbing.
//!
//! L1 owns interaction timing, the turn state machine, and the reflex router.
//! Source: `ARCHITECTURE.md` (the L1 interaction layer).
//!
//! ## Invariants this crate will enforce (later waves)
//!
//! - Every tool plan dispatch holds an `Arc<dyn aether_l5_policy::PolicyEngine>`
//!   and presents a `Decision::Allow` before L4 executes.
//! - Turn state transitions are monotonic per `turn_id`.
//! - Every L1 event carries `change_id`, `seq`, `source_layer = L1`.

#![deny(unsafe_code)]
#![warn(missing_docs)]
#![allow(dead_code)]

pub mod engine;
pub mod error;
pub mod events;
pub mod turn;

pub use engine::{
    InteractionEngine, ModelRouterClient, PresenceClient, ReflexClass, ReflexClassifier, Stt,
    TimingBudgets, Tts, TurnId, TurnState,
};
pub use error::L1Error;
pub use events::{InteractionEvent, InteractionEventKind};
pub use turn::{
    BlockReason, EchoStubRouter, RouteOutcome, TokenUsage, TurnEngine, TurnRequest, TurnResult,
    TurnRouter,
};
