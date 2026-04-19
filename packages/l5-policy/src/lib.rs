//! # aether-l5-policy — L5 Policy / Authorization Engine
//!
//! **Status:** Wave 2 scaffold. Types, traits, and command surface only.
//! **No evaluator logic. No persistence. No IPC handler.**
//!
//! L5 is the single, non-bypassable authorization gate for every autonomous
//! action Aether takes. Nothing executes without `Decision::Allow`.
//!
//! ## Source-of-truth docs
//!
//! - `planning/plans/L5_policy_engine_system_design.md`
//! - `planning/plans/implementation_prep/L5_interface_pack.md`
//! - `planning/plans/implementation_prep/event_contracts_master.md`
//! - `planning/plans/implementation_prep/sqlite_schema_pack.md` §3
//! - `planning/DECISION_LOCK_PASS_2026-04-18c.md` (Decisions 1–5)
//! - `planning/plans/L1_L4_L5_L7_integration_notes.md`
//!
//! ## Invariants this crate encodes (stub surface)
//!
//! 1. **Sync gate, sync commit.** `evaluate` is synchronous; the audit record
//!    is committed before any `Allow` returns.
//! 2. **Non-bypassable.** Every side-effectful call in the monorepo goes
//!    through a `Decision::Allow` branch held via `Arc<dyn PolicyEngine>`.
//! 3. **Typed capabilities only.** No stringly-typed permission ids cross
//!    the gate.
//! 4. **Append-only audit.** Chain continuity + HMAC integrity enforced by
//!    `aether-storage` triggers in later waves.
//! 5. **Degraded modes deny.** `SafeMode`, `AuditBroken`, `LedgerCorrupt`,
//!    `MinimumTrust` all prefer deny-all over silent-allow.

#![deny(unsafe_code)]
#![warn(missing_docs)]
// Scaffold allows during Wave 2 — types exist without callers yet.
#![allow(dead_code)]

pub mod approval;
pub mod audit;
pub mod audit_store;
pub mod byok;
pub mod capability;
pub mod common;
pub mod decision;
pub mod engine;
pub mod events;
pub mod grants;
pub mod ipc;
pub mod ledger;
pub mod policy_engine;
pub mod posture;
pub mod sink;
pub mod storage_hooks;

pub use approval::{ApprovalResponse, ApprovalTicket, ApprovalTicketId, UserChoice};
pub use audit::{AuditFilter, AuditId, AuditRecordEvent};
pub use byok::{CostCap, CostEvent, CostThreshold, CostWindow, ProviderId};
pub use capability::{
    ApiId, AutomationId, Capability, CapabilityFilter, CapabilityInfo, CapabilityPath,
    IntegrationId, ResourceScope,
};
pub use common::{
    ActorRef, Cents, ChangeId, Duration, MonotonicTimestamp, PersonaId, PresetId, RequestId,
    Seq, SessionId, TaskId,
};
pub use decision::{
    Decision, DecisionKind, DenyReason, DraftSource, HardcodedBlockId, ReEvalTrigger,
    StaticReasonId, TaintKind,
};
pub use events::{
    ActionRequestEvent, ApprovalPendingEvent, CostThresholdHitEvent,
    EmergencyRevokeAllEvent, EmergencyScope, GrantIssuedEvent, GrantRevokedEvent,
    L5Event, L5EventKind, PolicyDecisionEvent, PolicyPostureChangedEvent, RevokeReason,
};
pub use grants::{
    ApprovalMode, Grant, GrantDuration, GrantFilter, GrantId, GrantLedger,
    PersonaCompiledPolicyDefaults,
};
pub use ipc::{AuditExportFormat, PolicyCommands, PolicyIpcError};
pub use policy_engine::{
    ActionRequest, EventFilter, EventStream, PolicyEngine, PolicyEngineError,
};
pub use posture::{
    DegradedMode, PolicyPostureSummary, PostureTrigger, PrivacyPosture, WarnLevel,
};
pub use storage_hooks::{AuditStore, CostCounterStore, GrantStore};

// --- Wave 3 live surfaces ---
pub use audit_store::InMemoryAuditStore;
pub use engine::{CapabilityPolicy, DefaultPolicyEngine, EngineConfig};
pub use ledger::InMemoryGrantLedger;
pub use sink::{InMemorySink, L5EventSink, NullSink};
