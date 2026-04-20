//! `DefaultPolicyEngine` — Wave 3 slice implementation of `PolicyEngine`.
//!
//! ## What is implemented
//!
//! - 5-stage evaluator (pre-gates → feature → mode → resource/grant → duration)
//!   on a narrow capability set.
//! - Sync audit write **before** `Allow` returns (L5 interface pack §5).
//! - Auto-mode capability issues a session-scoped grant on first evaluate.
//! - Ask-mode capability returns `Decision::Ask` with a pending ticket; a
//!   subsequent `respond_approval(Allow*)` issues a grant and future
//!   `evaluate`s short-circuit via `ledger.covers(...)`.
//! - Decision 1 — `NeedsUpgrade(CapabilityPath)` returned for capabilities
//!   absent from the active preset.
//! - Decision 2 — `UserChoice::DeferToDraft` resolves to
//!   `Decision::DraftOnly { source: UserChoice }`.
//! - Decision 4 re-eval triggers covered: TTL expiry (runs every `evaluate`
//!   before cover-check) and explicit revoke (grant dropped from `covers`).
//! - Emergency revoke revokes every active grant and emits an
//!   `EmergencyRevokeAllEvent`.
//!
//! ## What is **not** implemented (deferred)
//!
//! - SQLite persistence — `aether-storage` driver wire-up lands in Wave 3.5.
//! - Audit hash-chain + HMAC — Wave 4.
//! - Pre-evaluator hardcoded blocks table (§2.3 L5 source) — only `Deny` mode
//!   on `ShellExec` is wired.
//! - Privacy-posture gate on remote routes.
//! - Cost-cap evaluator Stage 0.
//! - `subscribe()` returning a real `tokio::broadcast::Receiver`.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use crate::approval::{ApprovalResponse, ApprovalTicket, ApprovalTicketId, UserChoice};
use crate::audit::{AuditId, AuditRecordEvent, KeyId};
use crate::capability::{Capability, CapabilityFilter, CapabilityInfo, CapabilityPath, RiskClass};
use crate::common::{
    ActorRef, ChangeId, MonotonicTimestamp, PersonaId, PresetId, TaskId, WallTimestamp,
};
use crate::decision::{Decision, DecisionKind, DenyReason, DraftSource, StaticReasonId};
use crate::events::{
    ActionRequestEvent, ApprovalPendingEvent, EmergencyRevokeAllEvent, EmergencyScope,
    GrantIssuedEvent, L5Event, PolicyDecisionEvent, PolicyPostureChangedEvent, RevokeReason,
};
use crate::grants::{ApprovalMode, Grant, GrantDuration, GrantFilter, GrantLedger};
use crate::policy_engine::{
    ActionRequest, EmergencyReceipt, EventFilter, EventStream, PolicyEngine, PolicyEngineError,
};
use crate::posture::{DegradedMode, PolicyPostureSummary, PostureTrigger, PrivacyPosture};
use crate::sink::L5EventSink;
use crate::storage_hooks::AuditStore;

/// Preset-derived policy for one capability.
#[derive(Debug, Clone, Copy)]
pub struct CapabilityPolicy {
    /// Approval mode the preset assigns to this capability.
    pub mode: ApprovalMode,
    /// Risk class for UX rendering + audit.
    pub risk: RiskClass,
}

/// Snapshot used to configure a new engine instance.
#[derive(Debug, Clone)]
pub struct EngineConfig {
    /// Preset id (e.g. `"wave3.balanced"`).
    pub preset: PresetId,
    /// Preset version (monotonic integer).
    pub preset_version: u32,
    /// Persona the engine starts with.
    pub persona: PersonaId,
    /// Persona version.
    pub persona_version: u32,
    /// Privacy posture.
    pub posture: PrivacyPosture,
    /// Per-capability preset decision.
    pub preset_defaults: HashMap<Capability, CapabilityPolicy>,
}

impl EngineConfig {
    /// Wave 3 slice preset. Enables five capabilities with a mix of modes so
    /// every decision branch gets coverage in the tests.
    ///
    /// | Capability        | Mode       | Risk     |
    /// |-------------------|------------|----------|
    /// | `FilesRead`       | `Auto`     | Low      |
    /// | `FilesCreate`     | `Ask`      | Medium   |
    /// | `FilesEdit`       | `Ask`      | Medium   |
    /// | `FilesDelete`     | `Ask`      | High     |
    /// | `ShellExec`       | `Deny`     | Critical |
    ///
    /// Everything else returns `Decision::NeedsUpgrade` pointing at a
    /// hypothetical `"wave3.operator"` preset (not shipped in this wave).
    pub fn wave3_default(persona: PersonaId) -> Self {
        let mut d: HashMap<Capability, CapabilityPolicy> = HashMap::new();
        d.insert(
            Capability::FilesRead,
            CapabilityPolicy {
                mode: ApprovalMode::Auto,
                risk: RiskClass::Low,
            },
        );
        d.insert(
            Capability::FilesCreate,
            CapabilityPolicy {
                mode: ApprovalMode::Ask,
                risk: RiskClass::Medium,
            },
        );
        d.insert(
            Capability::FilesEdit,
            CapabilityPolicy {
                mode: ApprovalMode::Ask,
                risk: RiskClass::Medium,
            },
        );
        d.insert(
            Capability::FilesDelete,
            CapabilityPolicy {
                mode: ApprovalMode::Ask,
                risk: RiskClass::High,
            },
        );
        d.insert(
            Capability::ShellExec,
            CapabilityPolicy {
                mode: ApprovalMode::Deny,
                risk: RiskClass::Critical,
            },
        );
        Self {
            preset: PresetId(String::from("wave3.balanced")),
            preset_version: 1,
            persona,
            persona_version: 1,
            posture: PrivacyPosture::Balanced,
            preset_defaults: d,
        }
    }
}

#[derive(Debug)]
struct EngineInner {
    preset: PresetId,
    preset_version: u32,
    active_persona: PersonaId,
    persona_version: u32,
    posture: PrivacyPosture,
    degraded: Option<DegradedMode>,
    preset_defaults: HashMap<Capability, CapabilityPolicy>,
    pending_tickets: HashMap<ApprovalTicketId, PendingTicket>,
}

#[derive(Debug, Clone)]
struct PendingTicket {
    request: ActionRequest,
    risk: RiskClass,
}

/// Concrete `PolicyEngine`. Ledger + audit backends are trait objects so
/// callers can plug in either the in-memory backends (default) or the
/// SQLite-backed ones gated behind the `sqlite-backend` feature.
pub struct DefaultPolicyEngine {
    ledger: Arc<dyn GrantLedger>,
    audit: Arc<dyn AuditStore>,
    sink: Arc<dyn L5EventSink>,
    inner: Mutex<EngineInner>,
    seq: AtomicU64,
    change_ctr: AtomicU64,
    audit_ctr: AtomicU64,
    ticket_ctr: AtomicU64,
    grant_ctr: AtomicU64,
}

impl DefaultPolicyEngine {
    /// Build an engine from its config + injected backends.
    ///
    /// Pass `Arc::new(InMemoryGrantLedger::new()) as Arc<dyn GrantLedger>`
    /// for the default in-memory mode, or `Arc::new(SqliteGrantLedger::...)`
    /// when the `sqlite-backend` feature is enabled.
    pub fn new(
        cfg: EngineConfig,
        ledger: Arc<dyn GrantLedger>,
        audit: Arc<dyn AuditStore>,
        sink: Arc<dyn L5EventSink>,
    ) -> Self {
        Self {
            ledger,
            audit,
            sink,
            inner: Mutex::new(EngineInner {
                preset: cfg.preset,
                preset_version: cfg.preset_version,
                active_persona: cfg.persona,
                persona_version: cfg.persona_version,
                posture: cfg.posture,
                degraded: None,
                preset_defaults: cfg.preset_defaults,
                pending_tickets: HashMap::new(),
            }),
            seq: AtomicU64::new(1),
            change_ctr: AtomicU64::new(1),
            audit_ctr: AtomicU64::new(1),
            ticket_ctr: AtomicU64::new(1),
            grant_ctr: AtomicU64::new(1),
        }
    }

    /// Clone of the current posture summary (e.g. for test assertions).
    pub fn posture(&self) -> PolicyPostureSummary {
        let s = self.inner.lock().unwrap();
        PolicyPostureSummary {
            preset: s.preset.clone(),
            preset_version: s.preset_version,
            persona_id: s.active_persona.clone(),
            persona_version: s.persona_version,
            privacy_posture: s.posture,
            degraded: s.degraded,
            hash: 0,
        }
    }

    /// Flip the engine into or out of a degraded mode. Emits a
    /// `PolicyPostureChangedEvent`.
    pub fn set_degraded(&self, mode: Option<DegradedMode>) {
        let (prior, new, trigger) = {
            let mut s = self.inner.lock().unwrap();
            let prior = self.posture_from_locked(&s);
            s.degraded = mode;
            let new = self.posture_from_locked(&s);
            let trigger = if mode.is_some() {
                PostureTrigger::DegradedEntry
            } else {
                PostureTrigger::DegradedExit
            };
            (prior, new, trigger)
        };
        self.sink
            .emit(L5Event::PolicyPostureChanged(PolicyPostureChangedEvent {
                prior_posture: prior,
                new_posture: new,
                trigger,
                stripped_grants: Vec::new(),
                added_capabilities: Vec::new(),
                audit_ref: AuditId(String::from("posture-transient")),
                change_id: self.next_change(),
                seq: self.next_seq(),
            }));
    }

    /// Direct access to the ledger as a trait object.
    pub fn ledger(&self) -> &Arc<dyn GrantLedger> {
        &self.ledger
    }

    /// Direct access to the audit store as a trait object.
    pub fn audit(&self) -> &Arc<dyn AuditStore> {
        &self.audit
    }

    // ---------- internals ----------

    fn next_seq(&self) -> u64 {
        self.seq.fetch_add(1, Ordering::Relaxed)
    }

    fn next_change(&self) -> ChangeId {
        ChangeId(format!(
            "ch-{}",
            self.change_ctr.fetch_add(1, Ordering::Relaxed)
        ))
    }

    fn next_audit_id(&self) -> AuditId {
        AuditId(format!(
            "a-{}",
            self.audit_ctr.fetch_add(1, Ordering::Relaxed)
        ))
    }

    fn next_ticket_id(&self) -> ApprovalTicketId {
        ApprovalTicketId(format!(
            "t-{}",
            self.ticket_ctr.fetch_add(1, Ordering::Relaxed)
        ))
    }

    fn next_grant_id(&self) -> crate::grants::GrantId {
        crate::grants::GrantId(format!(
            "g-{}",
            self.grant_ctr.fetch_add(1, Ordering::Relaxed)
        ))
    }

    fn posture_from_locked(&self, s: &EngineInner) -> PolicyPostureSummary {
        PolicyPostureSummary {
            preset: s.preset.clone(),
            preset_version: s.preset_version,
            persona_id: s.active_persona.clone(),
            persona_version: s.persona_version,
            privacy_posture: s.posture,
            degraded: s.degraded,
            hash: 0,
        }
    }

    /// Sync-commit an audit row. Returns its id for the caller to thread into
    /// the outgoing `Decision`.
    fn write_audit(
        &self,
        req: &ActionRequest,
        decision: DecisionKind,
        change_id: &ChangeId,
        reason: Option<StaticReasonId>,
    ) -> Result<AuditId, PolicyEngineError> {
        let audit_id = self.next_audit_id();
        let row = AuditRecordEvent {
            audit_id: audit_id.clone(),
            timestamp_monotonic: req.emitted_at,
            timestamp_wall: WallTimestamp { epoch_s: 0, ns: 0 },
            actor: ActorRef::Persona(req.actor_persona.clone()),
            capability: req.capability.clone(),
            resource: req.resource.clone(),
            decision,
            change_id: change_id.clone(),
            prev_hash: Vec::new(),
            record_hmac: Vec::new(),
            key_id: KeyId(String::from("wave3-placeholder")),
            seq: self.next_seq(),
            reason,
            stage_trace: Vec::new(),
            privileged_profile: false,
        };
        self.audit
            .append(&row)
            .map_err(|e| PolicyEngineError::Internal(format!("audit write: {e}")))?;
        self.sink.emit(L5Event::AuditRecord(row));
        Ok(audit_id)
    }

    fn emit_decision_event(&self, req: &ActionRequest, decision: &Decision, change_id: &ChangeId) {
        self.sink.emit(L5Event::PolicyDecision(PolicyDecisionEvent {
            request_id: req.request_id.clone(),
            decision: decision.kind(),
            audit_id: decision.audit_id().clone(),
            change_id: change_id.clone(),
            seq: self.next_seq(),
            reason: None,
            effective_mode: None,
        }));
    }

    fn emit_action_request(&self, req: &ActionRequest, change_id: &ChangeId) {
        self.sink.emit(L5Event::ActionRequest(ActionRequestEvent {
            request_id: req.request_id.clone(),
            capability: req.capability.clone(),
            resource: req.resource.clone(),
            actor_persona: req.actor_persona.clone(),
            emitted_at: req.emitted_at,
            change_id: change_id.clone(),
            seq: self.next_seq(),
        }));
    }

    fn issue_and_emit_grant(
        &self,
        req: &ActionRequest,
        mode: ApprovalMode,
        duration: GrantDuration,
        scope: crate::capability::ResourceScope,
        issued_by: ActorRef,
        audit_id: AuditId,
        change_id: &ChangeId,
        preset_version: u32,
    ) -> crate::grants::GrantId {
        let new_grant = Grant {
            grant_id: self.next_grant_id(),
            capability: req.capability.clone(),
            resource_pattern: scope,
            persona_id: req.actor_persona.clone(),
            approval_mode: mode,
            duration: duration.clone(),
            issued_at: req.emitted_at,
            expires_at: None,
            preset_version_issued_under: preset_version,
        };
        let grant_id = new_grant.grant_id.clone();
        self.ledger.issue(new_grant.clone());
        self.sink.emit(L5Event::GrantIssued(GrantIssuedEvent {
            grant_id: grant_id.clone(),
            capability: new_grant.capability.clone(),
            resource_scope: new_grant.resource_pattern.clone(),
            approval_mode: new_grant.approval_mode,
            duration: new_grant.duration.clone(),
            issued_at: new_grant.issued_at,
            issued_by,
            audit_ref: audit_id,
            change_id: change_id.clone(),
            seq: self.next_seq(),
            preset_version_issued_under: preset_version,
        }));
        grant_id
    }
}

impl PolicyEngine for DefaultPolicyEngine {
    fn evaluate(&self, req: ActionRequest) -> Result<Decision, PolicyEngineError> {
        // Re-eval trigger 8 (TTL expiry) fires before any cover-check read.
        self.ledger.expire_ttl(req.emitted_at);

        let change_id = self.next_change();
        self.emit_action_request(&req, &change_id);

        let (degraded, policy, preset_version) = {
            let s = self.inner.lock().unwrap();
            (
                s.degraded,
                s.preset_defaults.get(&req.capability).copied(),
                s.preset_version,
            )
        };

        // Stage 1 — pre-gates: degraded mode denies everything.
        if let Some(mode) = degraded {
            return Err(PolicyEngineError::Degraded(mode));
        }

        // Stage 2 — feature: is capability in the active preset?
        let Some(policy) = policy else {
            let audit_id = self.write_audit(
                &req,
                DecisionKind::NeedsUpgrade,
                &change_id,
                Some(StaticReasonId(String::from("capability_not_in_preset"))),
            )?;
            let d = Decision::NeedsUpgrade {
                capability_path: CapabilityPath::for_capability(&req.capability),
                audit_id,
                suggested_preset: Some(PresetId(String::from("wave3.operator"))),
            };
            self.emit_decision_event(&req, &d, &change_id);
            return Ok(d);
        };

        // Stage 5 (mode-only fast paths) — Deny / DraftOnly short-circuit
        // before we consult the ledger.
        match policy.mode {
            ApprovalMode::Deny => {
                let audit_id = self.write_audit(
                    &req,
                    DecisionKind::Deny,
                    &change_id,
                    Some(StaticReasonId(String::from("mode_deny"))),
                )?;
                let d = Decision::Deny {
                    reason: DenyReason::ModeDeny,
                    audit_id,
                };
                self.emit_decision_event(&req, &d, &change_id);
                return Ok(d);
            }
            ApprovalMode::DraftOnly => {
                let audit_id = self.write_audit(
                    &req,
                    DecisionKind::DraftOnlySystem,
                    &change_id,
                    Some(StaticReasonId(String::from("mode_draft_only"))),
                )?;
                let d = Decision::DraftOnly {
                    audit_id,
                    source: DraftSource::System,
                    reason: Some(StaticReasonId(String::from("mode_draft_only"))),
                };
                self.emit_decision_event(&req, &d, &change_id);
                return Ok(d);
            }
            _ => {}
        }

        // Stage 3+4 — action / resource: does an active grant already cover?
        if let Some(grant_id) =
            self.ledger
                .covers(&req.capability, &req.resource, &req.actor_persona)
        {
            let audit_id = self.write_audit(&req, DecisionKind::Allow, &change_id, None)?;
            let d = Decision::Allow {
                grant_ref: Some(grant_id),
                audit_id,
            };
            self.emit_decision_event(&req, &d, &change_id);
            return Ok(d);
        }

        // No covering grant — mode decides.
        match policy.mode {
            ApprovalMode::Auto => {
                let audit_id = self.write_audit(&req, DecisionKind::Allow, &change_id, None)?;
                let grant_id = self.issue_and_emit_grant(
                    &req,
                    ApprovalMode::Auto,
                    GrantDuration::Session,
                    req.resource.clone(),
                    ActorRef::System,
                    audit_id.clone(),
                    &change_id,
                    preset_version,
                );
                let d = Decision::Allow {
                    grant_ref: Some(grant_id),
                    audit_id,
                };
                self.emit_decision_event(&req, &d, &change_id);
                Ok(d)
            }
            ApprovalMode::Ask | ApprovalMode::TaskScoped => {
                let ticket_id = self.next_ticket_id();
                let ticket = ApprovalTicket {
                    ticket_id: ticket_id.clone(),
                    request_id: req.request_id.clone(),
                    capability: req.capability.clone(),
                    resource: req.resource.clone(),
                    deadline_hint: None,
                    suggested_duration: Some(GrantDuration::TaskScoped(
                        req.task_id
                            .clone()
                            .unwrap_or_else(|| TaskId(String::from("default-task"))),
                    )),
                };
                {
                    let mut s = self.inner.lock().unwrap();
                    s.pending_tickets.insert(
                        ticket_id.clone(),
                        PendingTicket {
                            request: req.clone(),
                            risk: policy.risk,
                        },
                    );
                }
                let audit_id = self.write_audit(&req, DecisionKind::Ask, &change_id, None)?;
                self.sink
                    .emit(L5Event::ApprovalPending(ApprovalPendingEvent {
                        ticket_id,
                        request_id: req.request_id.clone(),
                        capability: req.capability.clone(),
                        resource: req.resource.clone(),
                        risk_class: policy.risk,
                        explanation: StaticReasonId(String::from("approval_required")),
                        change_id: change_id.clone(),
                        seq: self.next_seq(),
                    }));
                let d = Decision::Ask { ticket, audit_id };
                self.emit_decision_event(&req, &d, &change_id);
                Ok(d)
            }
            ApprovalMode::Deny | ApprovalMode::DraftOnly => {
                // Handled above. Unreachable only by construction; fall through
                // to an internal error instead of `unreachable!()` so a bad
                // refactor surfaces as a typed failure, not a panic.
                Err(PolicyEngineError::Internal(String::from(
                    "mode classification inconsistency",
                )))
            }
        }
    }

    fn subscribe(&self, _filter: EventFilter) -> EventStream<L5Event> {
        // Wave 3 uses the sync `L5EventSink` trait instead of a broadcast
        // receiver. Real broadcast subscription lands alongside the first
        // async consumer (Tauri bridge or L7 trust-center stream).
        EventStream::default()
    }

    fn emergency_revoke(
        &self,
        scope: EmergencyScope,
    ) -> Result<EmergencyReceipt, PolicyEngineError> {
        let change_id = self.next_change();
        let revoked = match &scope {
            EmergencyScope::All => self.ledger.revoke_all(RevokeReason::EmergencyRevoke),
            EmergencyScope::Category(_cap) => {
                // Wave 3 simplification — treat any non-All scope as All. A
                // narrower per-category implementation arrives in Wave 4.
                self.ledger.revoke_all(RevokeReason::EmergencyRevoke)
            }
            EmergencyScope::Persona(p) => {
                self.ledger.revoke_persona(p, RevokeReason::EmergencyRevoke)
            }
        };
        let audit_id = self.next_audit_id();
        self.sink
            .emit(L5Event::EmergencyRevokeAll(EmergencyRevokeAllEvent {
                initiated_by: ActorRef::User,
                scope,
                initiated_at: MonotonicTimestamp(0),
                completed_at: Some(MonotonicTimestamp(0)),
                revoked_count: Some(revoked),
                audit_ref: audit_id,
                change_id,
                seq: self.next_seq(),
            }));
        Ok(EmergencyReceipt {
            completed_ns: 0,
            revoked_count: revoked,
        })
    }

    fn snapshot_grants(&self, filter: GrantFilter) -> Vec<Grant> {
        self.ledger.snapshot(&filter)
    }

    fn capabilities(&self, _filter: CapabilityFilter) -> Vec<CapabilityInfo> {
        let s = self.inner.lock().unwrap();
        s.preset_defaults
            .iter()
            .map(|(cap, pol)| CapabilityInfo {
                capability: cap.clone(),
                label: "",
                risk_class: pol.risk,
                has_active_grant: false,
                as_of: MonotonicTimestamp(0),
            })
            .collect()
    }

    fn respond_approval(&self, response: ApprovalResponse) -> Result<ChangeId, PolicyEngineError> {
        let change_id = self.next_change();

        // Remove the ticket from pending before doing any side-effecting work.
        let (pending, preset_version) = {
            let mut s = self.inner.lock().unwrap();
            let Some(p) = s.pending_tickets.remove(&response.ticket_id) else {
                return Err(PolicyEngineError::TicketNotFound);
            };
            (p, s.preset_version)
        };

        match response.user_choice.clone() {
            UserChoice::Deny => {
                let audit_id = self.write_audit(
                    &pending.request,
                    DecisionKind::Deny,
                    &change_id,
                    Some(StaticReasonId(String::from("user_denied"))),
                )?;
                let d = Decision::Deny {
                    reason: DenyReason::ModeDeny,
                    audit_id,
                };
                self.emit_decision_event(&pending.request, &d, &change_id);
                Ok(change_id)
            }
            UserChoice::DeferToDraft => {
                let audit_id = self.write_audit(
                    &pending.request,
                    DecisionKind::DraftOnlyUserChoice,
                    &change_id,
                    Some(StaticReasonId(String::from("user_deferred"))),
                )?;
                let d = Decision::DraftOnly {
                    audit_id,
                    source: DraftSource::UserChoice,
                    reason: None,
                };
                self.emit_decision_event(&pending.request, &d, &change_id);
                Ok(change_id)
            }
            UserChoice::Allow
            | UserChoice::AllowScope(_)
            | UserChoice::AllowTask
            | UserChoice::AllowSession => {
                let scope = response
                    .scope_override
                    .clone()
                    .or_else(|| match &response.user_choice {
                        UserChoice::AllowScope(s) => Some(s.clone()),
                        _ => None,
                    })
                    .unwrap_or_else(|| pending.request.resource.clone());

                let duration = match &response.user_choice {
                    UserChoice::AllowSession => GrantDuration::Session,
                    UserChoice::AllowTask => GrantDuration::TaskScoped(
                        pending
                            .request
                            .task_id
                            .clone()
                            .unwrap_or_else(|| TaskId(String::from("default-task"))),
                    ),
                    _ => GrantDuration::Once,
                };

                let audit_id =
                    self.write_audit(&pending.request, DecisionKind::Allow, &change_id, None)?;

                let _grant_id = self.issue_and_emit_grant(
                    &pending.request,
                    ApprovalMode::Ask,
                    duration,
                    scope,
                    ActorRef::User,
                    audit_id.clone(),
                    &change_id,
                    preset_version,
                );

                let d = Decision::Allow {
                    grant_ref: Some(_grant_id),
                    audit_id,
                };
                self.emit_decision_event(&pending.request, &d, &change_id);
                Ok(change_id)
            }
        }
    }
}
