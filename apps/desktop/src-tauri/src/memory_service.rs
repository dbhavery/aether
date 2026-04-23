//! Memory V2 step 3 — shell-side per-domain write/forget/edit plumbing.
//!
//! Sits between the UI and `SessionMemoryStore`, consulting the user's
//! `memory.json` policy surface (`MemoryConfig::risk_for(domain)`) as
//! the per-domain gate, then routing through the L5 policy engine so
//! every allowed write produces an `AuditRecordEvent` tagged with the
//! appropriate `Capability` (`MemoryWrite` / `MemoryForget` /
//! `MemoryEdit` / `MemoryRead`). Mirrors the Media/Mic pattern: the
//! shell tri-state is the user-facing decision, L5 records the audit
//! row so the Trust drawer is always honest about what was attempted
//! and what was allowed. See `docs/MEMORY-V2-ARCHITECTURE.md` §§2, 4, 5.
//!
//! ## Scope (step 3)
//!
//! - `memory_write` — gate-aware write returning
//!   [`MemoryWriteOutcome`]. On `MemoryRisk::Auto` the item is
//!   persisted immediately; on `Ask` the call returns
//!   [`MemoryWriteOutcome::RequiresApproval`] without writing; on
//!   `Deny` the call short-circuits with
//!   [`MemoryWriteOutcome::Denied`]. The shell is expected to surface
//!   the approval modal between the two paths — this service does not
//!   own UI.
//! - `memory_write_after_approval` — the post-modal path. Emits
//!   `memory_write_asked` telemetry in addition to `memory_written`
//!   so the History tab can distinguish user-confirmed writes.
//! - `memory_forget` — per-domain forget of every record for a
//!   session. Same tri-state gate, separate capability
//!   (`MemoryForget`).
//! - `memory_edit` — same tri-state gate, separate capability
//!   (`MemoryEdit`). A proper per-item edit surface lands with the
//!   Memory tab (step 4); this module only wires the gate + audit +
//!   telemetry so step 4 can consume.
//! - `memory_read_audit_tick` — the sampled-read hook design doc §4
//!   calls for. Increments a per-(domain, session) counter; every
//!   100th tick it emits `memory_retrieval` telemetry + an L5 audit
//!   row. Callers invoke it after each `SessionMemoryStore::recent`
//!   that should participate in the sampling. Today only the two
//!   router types call `recent`; retrofitting those call sites is
//!   step-3-adjacent and tracked as a deferred item in the handoff.
//!
//! ## Out of scope (deferred)
//!
//! - Trust-drawer Memory tab (step 4) — no UI surface consumes this
//!   service yet.
//! - A durable domain-tagged memory store — today all writes go into
//!   the existing `SessionMemoryStore` as `TurnMemoryRecord`s. A
//!   domain-typed durable store arrives alongside the retention sweep
//!   (step 5) and embeddings (step 6).
//! - Per-turn retrofit of the existing `state.memory.append` call
//!   sites in `commands.rs` and `memory_router.rs`. Those remain
//!   trusted internal writes; step 3 only adds the gated path UI
//!   code will call explicitly.

use std::sync::atomic::Ordering;

use aether_l2_memory::{MemoryRole, TurnMemoryRecord};
use aether_l5_policy::{
    capability::{Capability, ResourceScope},
    common::{MonotonicTimestamp, RequestId, TurnId},
    decision::Decision,
    policy_engine::ActionRequest,
    PersonaId,
};

use crate::memory_config::{MemoryDomain, MemoryRisk};
use crate::state::{AppState, TelemetryEntry};

/// Telemetry kinds the Memory V2 service emits. Kept in this module as
/// `pub const &str` so Rust callers and the TS mirror at
/// `apps/desktop/src/lib/memoryTurns.ts` share the exact same wire
/// tokens. Adding a new kind must update both sides in the same PR.
pub mod telemetry_kind {
    /// Durable item persisted (auto path).
    pub const WRITTEN: &str = "memory_written";
    /// User-sensitive write required approval and got it.
    pub const WRITE_ASKED: &str = "memory_write_asked";
    /// User-sensitive write required approval and was denied, OR a
    /// `Deny` posture refused the write outright.
    pub const WRITE_DENIED: &str = "memory_write_denied";
    /// User (or retention sweep) removed an item.
    pub const FORGOTTEN: &str = "memory_forgotten";
    /// User edited an existing item in place.
    pub const EDITED: &str = "memory_edited";
    /// Sampled read audit — one tick per ~100 reads per domain per
    /// session (plus on retrieval-burst flush).
    pub const RETRIEVAL: &str = "memory_retrieval";
}

/// The per-domain gate resolved from `MemoryConfig::risk_for(domain)`.
/// Parallel to `CaptureGate` for Media / Mic; named separately so the
/// `Ask` / `Deny` semantics don't silently inherit media wording.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MemoryGate {
    /// The domain's risk posture is `Auto`; writes proceed without a
    /// modal.
    Auto,
    /// The domain's risk posture is `Ask`; the shell must surface the
    /// approval modal before the write can land.
    Ask,
    /// The domain's risk posture is `Deny`; the write must be
    /// refused.
    Deny,
}

impl From<MemoryRisk> for MemoryGate {
    fn from(r: MemoryRisk) -> Self {
        match r {
            MemoryRisk::Auto => MemoryGate::Auto,
            MemoryRisk::Ask => MemoryGate::Ask,
            MemoryRisk::Deny => MemoryGate::Deny,
        }
    }
}

/// Outcome of a gated memory write.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MemoryWriteOutcome {
    /// The write was allowed and persisted. `memory_id` is a stable
    /// per-item id derived from the session sequence; callers pass
    /// it back to `memory_edit` / `memory_forget` to target one row.
    /// `audit_id` is the L5 audit row id.
    Allowed {
        /// Stable id: `"mem-{session_id}-{sequence}"`.
        memory_id: String,
        /// Session-store sequence number assigned at append time.
        turn_sequence: u64,
        /// L5 audit row id for the write.
        audit_id: String,
    },
    /// The domain policy is `Ask`. Nothing was persisted. The shell
    /// must surface the approval modal and then call
    /// `memory_write_after_approval` to complete the write.
    RequiresApproval,
    /// The write was denied — either by `MemoryRisk::Deny` or by L5
    /// posture (Observer preset, degraded mode, etc.). `reason` is a
    /// short, stable string intended for telemetry grouping, not for
    /// user display.
    Denied {
        /// Stable grouping reason (`"config_deny"`, `"l5_deny"`,
        /// `"l5_needs_upgrade"`, `"l5_error"`).
        reason: String,
    },
}

/// Outcome of a gated memory forget.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MemoryForgetOutcome {
    /// Forget completed. `removed_count` is the number of rows
    /// evicted from the session store.
    Allowed {
        /// Rows evicted.
        removed_count: usize,
        /// L5 audit row id.
        audit_id: String,
    },
    /// Domain posture is Ask — caller must surface the modal.
    RequiresApproval,
    /// Denied — same vocabulary as `MemoryWriteOutcome::Denied`.
    Denied {
        /// Stable grouping reason.
        reason: String,
    },
}

/// Outcome of a gated memory edit. Step 3 wires the gate and audit;
/// the actual per-item mutation arrives with the Memory tab (step 4).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MemoryEditOutcome {
    /// Edit allowed at the gate. `memory_id` is the target item;
    /// today the caller is responsible for mutating the underlying
    /// row — this service does not own domain-typed storage yet.
    Allowed {
        /// Target item.
        memory_id: String,
        /// L5 audit row id.
        audit_id: String,
    },
    /// Domain posture is Ask.
    RequiresApproval,
    /// Denied.
    Denied {
        /// Stable grouping reason.
        reason: String,
    },
}

/// Errors surfaced by the service. Intentionally narrow — lock
/// poisoning is the only runtime failure today; everything else flows
/// through the outcome enums as explicit variants.
#[derive(Debug, thiserror::Error)]
pub enum MemoryServiceError {
    /// L2 store returned an error (lock poisoned, SQLite failure,
    /// etc.). The write did not persist.
    #[error("memory store error: {0}")]
    Store(String),
    /// Internal lock poisoned during gate resolution.
    #[error("memory service internal: {0}")]
    Internal(String),
}

/// Derive the `memory_id` for a fresh append.
fn mk_memory_id(session_id: &str, seq: u64) -> String {
    format!("mem-{session_id}-{seq}")
}

/// Build an `ActionRequest` suitable for L5 evaluation of a
/// memory-scoped capability. `ResourceScope` is `None` because
/// `AuditRecordEvent`'s wire shape is frozen for step 3 — a future
/// slice that adds a memory-domain scope variant (design §4 says
/// "scope = domain") will need its own additive change.
fn build_action_request(
    state: &AppState,
    capability: Capability,
) -> (ActionRequest, MonotonicTimestamp) {
    let ts_raw = state.next_ts();
    // The compiled persona id is an `aether_l6_persona::PersonaId`;
    // `ActionRequest::actor_persona` wants `aether_l5_policy::PersonaId`.
    // Unwrap and re-wrap via the inner `String` — same pattern commands.rs
    // uses when it rebuilds the engine config with `PersonaId(... .0.clone())`.
    let persona_id = {
        let a = state.active.read().expect("active read lock");
        PersonaId(a.compiled.persona_id.0.clone())
    };
    let emitted_at = MonotonicTimestamp(ts_raw);
    let req = ActionRequest {
        request_id: RequestId(format!("memory-{ts_raw}")),
        turn_id: TurnId(format!("memory-turn-{ts_raw}")),
        capability,
        resource: ResourceScope::None,
        actor_persona: persona_id,
        emitted_at,
        task_id: None,
        provenance_tags: Vec::new(),
        intended_route: None,
        risk_class_hint: None,
    };
    (req, emitted_at)
}

/// Emit a memory-scoped telemetry entry with domain + id context.
fn emit_memory_telemetry(
    state: &AppState,
    ts_ms: u64,
    kind: &str,
    domain: MemoryDomain,
    memory_id: Option<&str>,
) {
    let persona_id = {
        let a = state.active.read().expect("active read lock");
        a.compiled.persona_id.0.clone()
    };
    state.record_telemetry(TelemetryEntry {
        turn_id: memory_id
            .map(|id| id.to_string())
            .unwrap_or_else(|| format!("memory-{ts_ms}")),
        timestamp_ms: ts_ms,
        kind: kind.to_string(),
        persona_id,
        provider: None,
        tier: None,
        model: None,
        latency_ms: None,
        prompt_tokens: None,
        completion_tokens: None,
        memory_domain: Some(domain.label().to_string()),
        memory_id: memory_id.map(|s| s.to_string()),
    });
}

/// Extract an audit id out of a `Decision`, if any.
fn audit_id_of(decision: &Decision) -> Option<String> {
    match decision {
        Decision::Allow { audit_id, .. } => Some(audit_id.0.clone()),
        Decision::Deny { audit_id, .. } => Some(audit_id.0.clone()),
        Decision::Ask { audit_id, .. } => Some(audit_id.0.clone()),
        Decision::DraftOnly { audit_id, .. } => Some(audit_id.0.clone()),
        Decision::NeedsUpgrade { audit_id, .. } => Some(audit_id.0.clone()),
    }
}

/// Classify a `Decision` into the stable `reason` string used in
/// `MemoryWriteOutcome::Denied::reason`.
fn deny_reason(decision: &Decision) -> &'static str {
    match decision {
        Decision::Deny { .. } => "l5_deny",
        Decision::NeedsUpgrade { .. } => "l5_needs_upgrade",
        Decision::DraftOnly { .. } => "l5_draft_only",
        Decision::Ask { .. } => "l5_ask_unexpected",
        Decision::Allow { .. } => "l5_allow_unexpected",
    }
}

impl AppState {
    /// Resolve the per-domain gate from the current `MemoryConfig`.
    /// Mirrors `evaluate_media_permission` / `evaluate_mic_permission`.
    pub fn evaluate_memory_gate(&self, domain: MemoryDomain) -> MemoryGate {
        self.memory_config().risk_for(domain).into()
    }

    /// Attempt a gated write. On `Auto`, routes through L5 and
    /// persists. On `Ask`, returns `RequiresApproval` without
    /// persisting. On `Deny`, emits `memory_write_denied` telemetry
    /// and returns `Denied`.
    ///
    /// This is the primary Memory V2 write API. The existing
    /// `state.memory.append` path remains untouched for legacy
    /// trusted-internal writes (turn engine, vision early-exit
    /// notes, etc.) per step 3's scope note.
    pub fn memory_write(
        &self,
        domain: MemoryDomain,
        session_id: &str,
        content: String,
        role: MemoryRole,
    ) -> Result<MemoryWriteOutcome, MemoryServiceError> {
        let gate = self.evaluate_memory_gate(domain);
        match gate {
            MemoryGate::Deny => {
                let ts_ms = self.next_ts();
                emit_memory_telemetry(
                    self,
                    ts_ms,
                    telemetry_kind::WRITE_DENIED,
                    domain,
                    None,
                );
                Ok(MemoryWriteOutcome::Denied {
                    reason: "config_deny".to_string(),
                })
            }
            MemoryGate::Ask => Ok(MemoryWriteOutcome::RequiresApproval),
            MemoryGate::Auto => {
                self.perform_memory_write(domain, session_id, content, role, false)
            }
        }
    }

    /// Complete a `RequiresApproval` write after the shell has
    /// surfaced the approval modal and the user approved. Emits
    /// `memory_write_asked` *and* `memory_written` so the Trust drawer
    /// History tab can tell user-confirmed writes apart from auto
    /// writes.
    pub fn memory_write_after_approval(
        &self,
        domain: MemoryDomain,
        session_id: &str,
        content: String,
        role: MemoryRole,
    ) -> Result<MemoryWriteOutcome, MemoryServiceError> {
        self.perform_memory_write(domain, session_id, content, role, true)
    }

    /// Shared write implementation. `after_approval` flag only
    /// controls telemetry — the persistence path is the same.
    fn perform_memory_write(
        &self,
        domain: MemoryDomain,
        session_id: &str,
        content: String,
        role: MemoryRole,
        after_approval: bool,
    ) -> Result<MemoryWriteOutcome, MemoryServiceError> {
        let (request, emitted_at) = build_action_request(self, Capability::MemoryWrite);
        let decision = {
            let active = self.active.read().expect("active read lock");
            active
                .policy
                .evaluate(request)
                .map_err(|e| MemoryServiceError::Internal(format!("policy evaluate: {e}")))?
        };
        let ts_ms = emitted_at.0;
        match decision {
            Decision::Allow { audit_id, .. } => {
                // Append first so the assigned sequence is part of the
                // memory_id. On store failure we surface an error but
                // the L5 audit row remains — it records the attempt,
                // which matches design §4's "audit row per write".
                let pre_len = match self.memory.recent(session_id) {
                    Ok(w) => w.records.len() as u64,
                    Err(e) => {
                        return Err(MemoryServiceError::Store(format!("pre-recall: {e}")));
                    }
                };
                let record = TurnMemoryRecord {
                    session_id: session_id.to_string(),
                    sequence: 0,
                    role,
                    content,
                    timestamp_ms: ts_ms,
                };
                self.memory
                    .append(record)
                    .map_err(|e| MemoryServiceError::Store(format!("append: {e}")))?;
                let seq = pre_len + 1;
                let memory_id = mk_memory_id(session_id, seq);
                if after_approval {
                    emit_memory_telemetry(
                        self,
                        ts_ms,
                        telemetry_kind::WRITE_ASKED,
                        domain,
                        Some(&memory_id),
                    );
                }
                emit_memory_telemetry(
                    self,
                    ts_ms,
                    telemetry_kind::WRITTEN,
                    domain,
                    Some(&memory_id),
                );
                Ok(MemoryWriteOutcome::Allowed {
                    memory_id,
                    turn_sequence: seq,
                    audit_id: audit_id.0,
                })
            }
            other => {
                emit_memory_telemetry(
                    self,
                    ts_ms,
                    telemetry_kind::WRITE_DENIED,
                    domain,
                    None,
                );
                let reason = deny_reason(&other).to_string();
                let _ = audit_id_of(&other); // side-effect-free read for future debugging.
                Ok(MemoryWriteOutcome::Denied { reason })
            }
        }
    }

    /// Gated forget of every record for `session_id`. Today this
    /// delegates to `SessionMemoryStore::clear_session`; a future
    /// slice can target single `memory_id`s once a domain-typed store
    /// lands.
    pub fn memory_forget(
        &self,
        domain: MemoryDomain,
        session_id: &str,
    ) -> Result<MemoryForgetOutcome, MemoryServiceError> {
        let gate = self.evaluate_memory_gate(domain);
        let ts_ms = self.next_ts();
        match gate {
            MemoryGate::Deny => {
                emit_memory_telemetry(
                    self,
                    ts_ms,
                    telemetry_kind::WRITE_DENIED,
                    domain,
                    None,
                );
                Ok(MemoryForgetOutcome::Denied {
                    reason: "config_deny".to_string(),
                })
            }
            MemoryGate::Ask => Ok(MemoryForgetOutcome::RequiresApproval),
            MemoryGate::Auto => {
                let (request, _) = build_action_request(self, Capability::MemoryForget);
                let decision = {
                    let active = self.active.read().expect("active read lock");
                    active.policy.evaluate(request).map_err(|e| {
                        MemoryServiceError::Internal(format!("policy evaluate: {e}"))
                    })?
                };
                match decision {
                    Decision::Allow { audit_id, .. } => {
                        let pre_len = match self.memory.recent(session_id) {
                            Ok(w) => w.records.len(),
                            Err(e) => {
                                return Err(MemoryServiceError::Store(format!("pre-recall: {e}")));
                            }
                        };
                        self.memory
                            .clear_session(session_id)
                            .map_err(|e| MemoryServiceError::Store(format!("clear: {e}")))?;
                        emit_memory_telemetry(
                            self,
                            ts_ms,
                            telemetry_kind::FORGOTTEN,
                            domain,
                            None,
                        );
                        Ok(MemoryForgetOutcome::Allowed {
                            removed_count: pre_len,
                            audit_id: audit_id.0,
                        })
                    }
                    other => Ok(MemoryForgetOutcome::Denied {
                        reason: deny_reason(&other).to_string(),
                    }),
                }
            }
        }
    }

    /// Gated edit. Step 3 wires the gate + audit + telemetry; the
    /// actual per-item mutation of memory content arrives with the
    /// Memory tab (step 4), at which point this function will grow a
    /// new-content parameter.
    pub fn memory_edit(
        &self,
        domain: MemoryDomain,
        memory_id: String,
    ) -> Result<MemoryEditOutcome, MemoryServiceError> {
        let gate = self.evaluate_memory_gate(domain);
        let ts_ms = self.next_ts();
        match gate {
            MemoryGate::Deny => Ok(MemoryEditOutcome::Denied {
                reason: "config_deny".to_string(),
            }),
            MemoryGate::Ask => Ok(MemoryEditOutcome::RequiresApproval),
            MemoryGate::Auto => {
                let (request, _) = build_action_request(self, Capability::MemoryEdit);
                let decision = {
                    let active = self.active.read().expect("active read lock");
                    active.policy.evaluate(request).map_err(|e| {
                        MemoryServiceError::Internal(format!("policy evaluate: {e}"))
                    })?
                };
                match decision {
                    Decision::Allow { audit_id, .. } => {
                        emit_memory_telemetry(
                            self,
                            ts_ms,
                            telemetry_kind::EDITED,
                            domain,
                            Some(&memory_id),
                        );
                        Ok(MemoryEditOutcome::Allowed {
                            memory_id,
                            audit_id: audit_id.0,
                        })
                    }
                    other => Ok(MemoryEditOutcome::Denied {
                        reason: deny_reason(&other).to_string(),
                    }),
                }
            }
        }
    }

    /// Sampled-read hook for design §4. Callers invoke this after
    /// each `SessionMemoryStore::recent` that should participate in
    /// the sampling. One audit row + one `memory_retrieval`
    /// telemetry entry is produced every `READ_AUDIT_SAMPLE_RATE`
    /// calls per domain per session. Cheap — bumps an atomic and
    /// short-circuits 99% of the time.
    pub fn memory_read_audit_tick(&self, domain: MemoryDomain) {
        const SAMPLE_RATE: u64 = 100;
        let counter = self.memory_read_counter(domain);
        // `fetch_add` returns the value *before* the add, so the
        // first call returns 0 and triggers the first audit row.
        // That's the desired behaviour: the design says "one row per
        // ~100 reads", not "the first 99 reads are silent".
        let prev = counter.fetch_add(1, Ordering::Relaxed);
        if prev % SAMPLE_RATE != 0 {
            return;
        }
        let (request, emitted_at) = build_action_request(self, Capability::MemoryRead);
        let active = self.active.read().expect("active read lock");
        // Policy failure on the read path is silently swallowed —
        // failing to audit a read must not take down the consumer
        // (the turn engine) that triggered it. A tracing WARN is
        // enough visibility for now.
        if let Err(e) = active.policy.evaluate(request) {
            tracing::warn!("memory read audit sample failed: {e}");
            return;
        }
        drop(active);
        emit_memory_telemetry(
            self,
            emitted_at.0,
            telemetry_kind::RETRIEVAL,
            domain,
            None,
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::memory_config::MemoryConfig;

    fn setup_state() -> AppState {
        AppState::new().expect("test AppState")
    }

    // ---------- per-domain gate routing ----------

    #[test]
    fn gate_resolves_from_config_risk() {
        let state = setup_state();
        // Defaults: Facts/Artifacts = Ask; Session/Durable/Projects/Preferences = Auto.
        assert_eq!(
            state.evaluate_memory_gate(MemoryDomain::Facts),
            MemoryGate::Ask
        );
        assert_eq!(
            state.evaluate_memory_gate(MemoryDomain::Artifacts),
            MemoryGate::Ask
        );
        assert_eq!(
            state.evaluate_memory_gate(MemoryDomain::Session),
            MemoryGate::Auto
        );
        assert_eq!(
            state.evaluate_memory_gate(MemoryDomain::Durable),
            MemoryGate::Auto
        );
        assert_eq!(
            state.evaluate_memory_gate(MemoryDomain::Projects),
            MemoryGate::Auto
        );
        assert_eq!(
            state.evaluate_memory_gate(MemoryDomain::Preferences),
            MemoryGate::Auto
        );
    }

    #[test]
    fn gate_follows_config_updates() {
        let state = setup_state();
        let mut cfg = MemoryConfig::defaults();
        cfg.default_risk.insert(MemoryDomain::Durable, MemoryRisk::Ask);
        cfg.default_risk.insert(MemoryDomain::Facts, MemoryRisk::Deny);
        state.set_memory_config(cfg).expect("update config");
        assert_eq!(
            state.evaluate_memory_gate(MemoryDomain::Durable),
            MemoryGate::Ask
        );
        assert_eq!(
            state.evaluate_memory_gate(MemoryDomain::Facts),
            MemoryGate::Deny
        );
    }

    // ---------- Auto-flow round trip (Durable) ----------

    #[test]
    fn auto_flow_durable_write_persists_and_audits() {
        let state = setup_state();
        let before = state
            .memory
            .recent("s1")
            .expect("pre-recall")
            .records
            .len();
        let outcome = state
            .memory_write(
                MemoryDomain::Durable,
                "s1",
                "hello from durable".into(),
                MemoryRole::User,
            )
            .expect("write call");
        match outcome {
            MemoryWriteOutcome::Allowed {
                memory_id,
                turn_sequence,
                audit_id,
            } => {
                assert_eq!(turn_sequence, (before as u64) + 1);
                assert!(memory_id.starts_with("mem-s1-"));
                assert!(!audit_id.is_empty(), "L5 must assign an audit id");
            }
            other => panic!("expected Allowed, got {other:?}"),
        }
        let after = state.memory.recent("s1").unwrap().records.len();
        assert_eq!(after, before + 1, "item must be persisted");
        // Telemetry: one memory_written entry.
        let tel = state.telemetry_recent(10);
        let written = tel
            .iter()
            .filter(|e| e.kind == telemetry_kind::WRITTEN)
            .count();
        assert_eq!(written, 1, "exactly one memory_written telemetry");
        let e = tel
            .iter()
            .find(|e| e.kind == telemetry_kind::WRITTEN)
            .unwrap();
        assert_eq!(e.memory_domain.as_deref(), Some("durable"));
        assert!(e.memory_id.is_some());
    }

    // ---------- Ask-flow round trip (Facts) ----------

    #[test]
    fn ask_flow_facts_write_requires_approval_first() {
        let state = setup_state();
        let outcome = state
            .memory_write(
                MemoryDomain::Facts,
                "s1",
                "my name is Don".into(),
                MemoryRole::User,
            )
            .expect("gate call");
        assert_eq!(outcome, MemoryWriteOutcome::RequiresApproval);
        // Nothing persisted.
        assert!(state.memory.recent("s1").unwrap().records.is_empty());
        // No memory_written telemetry — only the approval-gated path
        // emits that, and we haven't approved yet.
        let tel = state.telemetry_recent(10);
        assert!(
            !tel.iter().any(|e| e.kind == telemetry_kind::WRITTEN),
            "must not emit memory_written before approval"
        );
    }

    #[test]
    fn ask_flow_facts_write_after_approval_persists_and_emits_asked_telemetry() {
        let state = setup_state();
        let outcome = state
            .memory_write_after_approval(
                MemoryDomain::Facts,
                "s1",
                "my name is Don".into(),
                MemoryRole::User,
            )
            .expect("approval write");
        match outcome {
            MemoryWriteOutcome::Allowed { memory_id, .. } => {
                assert!(memory_id.starts_with("mem-s1-"));
            }
            other => panic!("expected Allowed, got {other:?}"),
        }
        let tel = state.telemetry_recent(10);
        let asked_count = tel
            .iter()
            .filter(|e| e.kind == telemetry_kind::WRITE_ASKED)
            .count();
        let written_count = tel
            .iter()
            .filter(|e| e.kind == telemetry_kind::WRITTEN)
            .count();
        assert_eq!(asked_count, 1, "memory_write_asked must fire once");
        assert_eq!(written_count, 1, "memory_written must still fire");
    }

    // ---------- Deny path ----------

    #[test]
    fn config_deny_short_circuits_with_denied_telemetry() {
        let state = setup_state();
        let mut cfg = MemoryConfig::defaults();
        cfg.default_risk.insert(MemoryDomain::Durable, MemoryRisk::Deny);
        state.set_memory_config(cfg).unwrap();
        let outcome = state
            .memory_write(
                MemoryDomain::Durable,
                "s1",
                "rejected".into(),
                MemoryRole::User,
            )
            .expect("gate call");
        match outcome {
            MemoryWriteOutcome::Denied { reason } => {
                assert_eq!(reason, "config_deny");
            }
            other => panic!("expected Denied, got {other:?}"),
        }
        assert!(state.memory.recent("s1").unwrap().records.is_empty());
        let tel = state.telemetry_recent(10);
        assert!(tel.iter().any(|e| e.kind == telemetry_kind::WRITE_DENIED));
    }

    // ---------- Forget ----------

    #[test]
    fn forget_auto_domain_clears_session_and_emits_telemetry() {
        let state = setup_state();
        // Seed some rows.
        for i in 0..3 {
            state
                .memory_write(
                    MemoryDomain::Durable,
                    "s1",
                    format!("row {i}"),
                    MemoryRole::User,
                )
                .unwrap();
        }
        let outcome = state
            .memory_forget(MemoryDomain::Durable, "s1")
            .expect("forget call");
        match outcome {
            MemoryForgetOutcome::Allowed { removed_count, .. } => {
                assert_eq!(removed_count, 3);
            }
            other => panic!("expected Allowed, got {other:?}"),
        }
        assert!(state.memory.recent("s1").unwrap().records.is_empty());
        let tel = state.telemetry_recent(20);
        assert!(tel.iter().any(|e| e.kind == telemetry_kind::FORGOTTEN));
    }

    #[test]
    fn forget_ask_domain_returns_requires_approval() {
        let state = setup_state();
        let outcome = state
            .memory_forget(MemoryDomain::Facts, "s1")
            .expect("forget call");
        assert_eq!(outcome, MemoryForgetOutcome::RequiresApproval);
    }

    // ---------- Edit ----------

    #[test]
    fn edit_auto_domain_allowed_and_emits_edited_telemetry() {
        let state = setup_state();
        let outcome = state
            .memory_edit(MemoryDomain::Durable, "mem-s1-1".to_string())
            .expect("edit call");
        match outcome {
            MemoryEditOutcome::Allowed { memory_id, .. } => {
                assert_eq!(memory_id, "mem-s1-1");
            }
            other => panic!("expected Allowed, got {other:?}"),
        }
        let tel = state.telemetry_recent(10);
        assert!(tel.iter().any(|e| e.kind == telemetry_kind::EDITED));
    }

    // ---------- Sampled read audit ----------

    #[test]
    fn read_audit_tick_samples_every_100_calls() {
        let state = setup_state();
        // First tick = sample (prev was 0, 0 % 100 == 0).
        state.memory_read_audit_tick(MemoryDomain::Durable);
        let tel = state.telemetry_recent(200);
        let first_sample = tel
            .iter()
            .filter(|e| e.kind == telemetry_kind::RETRIEVAL)
            .count();
        assert_eq!(first_sample, 1, "first tick samples");
        // Next 99 ticks are silent.
        for _ in 0..99 {
            state.memory_read_audit_tick(MemoryDomain::Durable);
        }
        let tel = state.telemetry_recent(400);
        let after_100 = tel
            .iter()
            .filter(|e| e.kind == telemetry_kind::RETRIEVAL)
            .count();
        assert_eq!(after_100, 1, "ticks 2..100 must not sample");
        // Tick 101 samples (prev was 100, 100 % 100 == 0).
        state.memory_read_audit_tick(MemoryDomain::Durable);
        let tel = state.telemetry_recent(400);
        let after_101 = tel
            .iter()
            .filter(|e| e.kind == telemetry_kind::RETRIEVAL)
            .count();
        assert_eq!(after_101, 2, "tick 101 samples again");
    }

    #[test]
    fn read_audit_counters_are_per_domain() {
        let state = setup_state();
        // Tick once on each domain; each should sample its own first
        // tick independently.
        for d in [
            MemoryDomain::Session,
            MemoryDomain::Durable,
            MemoryDomain::Facts,
            MemoryDomain::Projects,
            MemoryDomain::Preferences,
            MemoryDomain::Artifacts,
        ] {
            state.memory_read_audit_tick(d);
        }
        let tel = state.telemetry_recent(200);
        let count = tel
            .iter()
            .filter(|e| e.kind == telemetry_kind::RETRIEVAL)
            .count();
        assert_eq!(count, 6, "each domain samples independently on its first tick");
    }
}
