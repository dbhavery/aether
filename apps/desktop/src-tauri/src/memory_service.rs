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

use aether_l2_memory::{
    embeddings::{EmbeddingRow, MemoryId as EmbedMemoryId, EMBED_ELIGIBLE_DOMAINS},
    MemoryRole, TurnMemoryRecord,
};
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
    /// Memory V2 step 6 (ADR-0002) — an embedding was produced + stored
    /// for an already-persisted memory item. Emitted only when
    /// `memory.json::embeddings.enabled` is true and the domain is
    /// embed-eligible (Durable / Projects / Artifacts).
    pub const EMBEDDED: &str = "memory_embedded";
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
    /// Per-item forget: the target row was not present (already
    /// evicted by retention, never existed, or raced with another
    /// forget). Distinct from `Denied` so the Trust drawer can
    /// render a softer "already gone" state instead of treating it
    /// as a policy refusal. Telemetry still fires under
    /// `memory_forgotten` so the audit trail reflects the attempt.
    NotFound,
}

/// Outcome of a gated memory edit. Step 4 wires the per-item
/// mutation through `SessionMemoryStore::update`; `Allowed` now
/// means the store was mutated successfully.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MemoryEditOutcome {
    /// Edit allowed and applied. `memory_id` is the target item.
    Allowed {
        /// Target item.
        memory_id: String,
        /// L5 audit row id.
        audit_id: String,
    },
    /// Domain posture is Ask.
    RequiresApproval,
    /// Denied — policy refused the edit.
    Denied {
        /// Stable grouping reason.
        reason: String,
    },
    /// Target row did not exist. Same rationale as
    /// `MemoryForgetOutcome::NotFound`: retention may have claimed
    /// it, or the Trust drawer may be holding a stale id. Softer
    /// surface than `Denied`.
    NotFound,
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
        audit_extras: None,
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
                emit_memory_telemetry(self, ts_ms, telemetry_kind::WRITE_DENIED, domain, None);
                Ok(MemoryWriteOutcome::Denied {
                    reason: "config_deny".to_string(),
                })
            }
            MemoryGate::Ask => Ok(MemoryWriteOutcome::RequiresApproval),
            MemoryGate::Auto => self.perform_memory_write(domain, session_id, content, role, false),
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
                // ADR-0004: route to the per-domain store. Session +
                // Durable have dedicated lanes today; other domains
                // fall back to the Session store with a warn (handled
                // inside `memory_for_domain`).
                let store = self.memory_for_domain(domain);
                // Append first so the assigned sequence is part of the
                // memory_id. On store failure we surface an error but
                // the L5 audit row remains — it records the attempt,
                // which matches design §4's "audit row per write".
                let pre_len = match store.recent(session_id) {
                    Ok(w) => w.records.len() as u64,
                    Err(e) => {
                        return Err(MemoryServiceError::Store(format!("pre-recall: {e}")));
                    }
                };
                // Snapshot the content for the optional embed path —
                // `record.content` is moved into the append below.
                let rec_content_snapshot = content.clone();
                let record = TurnMemoryRecord {
                    session_id: session_id.to_string(),
                    sequence: 0,
                    role,
                    content,
                    timestamp_ms: ts_ms,
                };
                store
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
                // Memory V2 step 6 (ADR-0002): best-effort embed.
                // Runs only when the user has opted in AND the
                // domain is embed-eligible. Failure never impacts
                // the primary write outcome.
                self.maybe_embed_on_write(domain, &memory_id, &rec_content_snapshot, ts_ms);
                Ok(MemoryWriteOutcome::Allowed {
                    memory_id,
                    turn_sequence: seq,
                    audit_id: audit_id.0,
                })
            }
            other => {
                emit_memory_telemetry(self, ts_ms, telemetry_kind::WRITE_DENIED, domain, None);
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
                emit_memory_telemetry(self, ts_ms, telemetry_kind::WRITE_DENIED, domain, None);
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
                        // ADR-0004: clear the lane that owns the domain.
                        let store = self.memory_for_domain(domain);
                        let pre_len = match store.recent(session_id) {
                            Ok(w) => w.records.len(),
                            Err(e) => {
                                return Err(MemoryServiceError::Store(format!("pre-recall: {e}")));
                            }
                        };
                        store
                            .clear_session(session_id)
                            .map_err(|e| MemoryServiceError::Store(format!("clear: {e}")))?;
                        emit_memory_telemetry(self, ts_ms, telemetry_kind::FORGOTTEN, domain, None);
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

    /// Gated per-item forget. Like `memory_forget` but targets a
    /// single `(session_id, sequence)` row instead of the whole
    /// session. Returns `NotFound` when the row is already gone.
    pub fn memory_forget_item(
        &self,
        domain: MemoryDomain,
        session_id: &str,
        sequence: u64,
    ) -> Result<MemoryForgetOutcome, MemoryServiceError> {
        let gate = self.evaluate_memory_gate(domain);
        match gate {
            MemoryGate::Deny => {
                let ts_ms = self.next_ts();
                emit_memory_telemetry(
                    self,
                    ts_ms,
                    telemetry_kind::WRITE_DENIED,
                    domain,
                    Some(&mk_memory_id(session_id, sequence)),
                );
                Ok(MemoryForgetOutcome::Denied {
                    reason: "config_deny".to_string(),
                })
            }
            MemoryGate::Ask => Ok(MemoryForgetOutcome::RequiresApproval),
            MemoryGate::Auto => self.perform_memory_forget_item(domain, session_id, sequence),
        }
    }

    /// Complete a `RequiresApproval` per-item forget after the shell
    /// has surfaced the approval modal and the user approved. Same
    /// persistence path as the Auto flow; no separate telemetry
    /// distinguishes it from `memory_forgotten` today (forget is
    /// terminal, unlike writes — there is no "forgot-after-ask" need
    /// for an extra tag beyond the audit row carrying the capability).
    pub fn memory_forget_item_after_approval(
        &self,
        domain: MemoryDomain,
        session_id: &str,
        sequence: u64,
    ) -> Result<MemoryForgetOutcome, MemoryServiceError> {
        self.perform_memory_forget_item(domain, session_id, sequence)
    }

    fn perform_memory_forget_item(
        &self,
        domain: MemoryDomain,
        session_id: &str,
        sequence: u64,
    ) -> Result<MemoryForgetOutcome, MemoryServiceError> {
        let (request, emitted_at) = build_action_request(self, Capability::MemoryForget);
        let decision = {
            let active = self.active.read().expect("active read lock");
            active
                .policy
                .evaluate(request)
                .map_err(|e| MemoryServiceError::Internal(format!("policy evaluate: {e}")))?
        };
        let ts_ms = emitted_at.0;
        let memory_id = mk_memory_id(session_id, sequence);
        match decision {
            Decision::Allow { audit_id, .. } => {
                // ADR-0004: per-item forget hits the domain-owning store.
                let store = self.memory_for_domain(domain);
                let removed = store
                    .remove(session_id, sequence)
                    .map_err(|e| MemoryServiceError::Store(format!("remove: {e}")))?;
                if !removed {
                    // Audit row still recorded the attempt; emit no
                    // forget telemetry since nothing was actually
                    // evicted. The L5 audit captures the authorised
                    // capability call regardless.
                    return Ok(MemoryForgetOutcome::NotFound);
                }
                emit_memory_telemetry(
                    self,
                    ts_ms,
                    telemetry_kind::FORGOTTEN,
                    domain,
                    Some(&memory_id),
                );
                // Memory V2 step 6: paired embedding delete. Silent
                // no-op if embeddings were never stored for this id.
                self.delete_embedding(domain, &memory_id);
                Ok(MemoryForgetOutcome::Allowed {
                    removed_count: 1,
                    audit_id: audit_id.0,
                })
            }
            other => Ok(MemoryForgetOutcome::Denied {
                reason: deny_reason(&other).to_string(),
            }),
        }
    }

    /// Gated per-item edit. `sequence` is the row to mutate and
    /// `new_content` replaces its text. Auto path calls
    /// `SessionMemoryStore::update`; Ask returns `RequiresApproval`
    /// so the shell can surface the modal and then call
    /// `memory_edit_after_approval`.
    pub fn memory_edit(
        &self,
        domain: MemoryDomain,
        session_id: &str,
        sequence: u64,
        new_content: String,
    ) -> Result<MemoryEditOutcome, MemoryServiceError> {
        let gate = self.evaluate_memory_gate(domain);
        match gate {
            MemoryGate::Deny => Ok(MemoryEditOutcome::Denied {
                reason: "config_deny".to_string(),
            }),
            MemoryGate::Ask => Ok(MemoryEditOutcome::RequiresApproval),
            MemoryGate::Auto => self.perform_memory_edit(domain, session_id, sequence, new_content),
        }
    }

    /// Post-approval edit path. Counterpart to
    /// `memory_write_after_approval`.
    pub fn memory_edit_after_approval(
        &self,
        domain: MemoryDomain,
        session_id: &str,
        sequence: u64,
        new_content: String,
    ) -> Result<MemoryEditOutcome, MemoryServiceError> {
        self.perform_memory_edit(domain, session_id, sequence, new_content)
    }

    fn perform_memory_edit(
        &self,
        domain: MemoryDomain,
        session_id: &str,
        sequence: u64,
        new_content: String,
    ) -> Result<MemoryEditOutcome, MemoryServiceError> {
        let (request, emitted_at) = build_action_request(self, Capability::MemoryEdit);
        let decision = {
            let active = self.active.read().expect("active read lock");
            active
                .policy
                .evaluate(request)
                .map_err(|e| MemoryServiceError::Internal(format!("policy evaluate: {e}")))?
        };
        let ts_ms = emitted_at.0;
        let memory_id = mk_memory_id(session_id, sequence);
        match decision {
            Decision::Allow { audit_id, .. } => {
                // ADR-0004: edit lands in the domain-owning store.
                let store = self.memory_for_domain(domain);
                let applied = store
                    .update(session_id, sequence, new_content)
                    .map_err(|e| MemoryServiceError::Store(format!("update: {e}")))?;
                if !applied {
                    return Ok(MemoryEditOutcome::NotFound);
                }
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
        emit_memory_telemetry(self, emitted_at.0, telemetry_kind::RETRIEVAL, domain, None);
    }

    /// Memory V2 step 5 — the retention sweep.
    ///
    /// Walks every known session, applies the per-domain
    /// `retention_days` from the persisted `MemoryConfig`, and prunes
    /// rows whose `timestamp_ms` predates the cutoff. Emits:
    ///
    /// - one `memory_forgotten` telemetry row per domain that actually
    ///   evicted ≥1 rows (aggregated per sweep to avoid flooding the
    ///   History tab; `memory_id` is left `None` because the sweep
    ///   operates on a set, not a single item),
    /// - one L5 audit row per sweep *invocation* (via the existing
    ///   `MemoryForget` capability), regardless of whether anything was
    ///   evicted. One row per sweep keeps the audit trail symmetric
    ///   with scheduled maintenance tasks like the presence tick.
    ///
    /// Today only the Session domain has a backing store
    /// (`SessionMemoryStore`). The other five domains are skipped with
    /// a trace note; a future domain-typed durable store will reuse
    /// this entry point. `retention_days = None` means "keep until
    /// forgotten" and also skips the domain.
    ///
    /// `now_ms` is supplied by the caller so the sweep stays pure and
    /// testable (no implicit clock). The boot sweep in `main.rs` uses
    /// `AppState::next_ts()`; the hourly tick uses the same.
    ///
    /// Returns the total number of rows evicted across all domains.
    pub fn run_retention_sweep(&self, now_ms: u64) -> Result<usize, MemoryServiceError> {
        // One L5 audit row per invocation. Use the MemoryForget
        // capability; the sweep is the automated counterpart to the
        // user-initiated per-item forget surface.
        let (request, emitted_at) = build_action_request(self, Capability::MemoryForget);
        let decision = {
            let active = self.active.read().expect("active read lock");
            active
                .policy
                .evaluate(request)
                .map_err(|e| MemoryServiceError::Internal(format!("policy evaluate: {e}")))?
        };
        // Policy denying a retention sweep is possible in principle
        // (a future Observer-like posture could refuse all
        // MemoryForget). Today no shipped posture does; when it does,
        // we trace and skip the evictions rather than override — the
        // user owns their memory.
        let proceed = matches!(decision, Decision::Allow { .. });
        if !proceed {
            tracing::warn!(
                "retention sweep skipped: policy returned non-Allow decision ({})",
                deny_reason(&decision)
            );
            return Ok(0);
        }

        let cfg = self.memory_config();
        let mut total_evicted: usize = 0;
        let mut total_sessions_walked: usize = 0;
        // ADR-0004: walk each domain that has a dedicated store and
        // prune with its own TTL. Domains without a store
        // (Projects / Artifacts / Facts / Preferences today) are
        // trace-skipped — ADR-0005 closes that gap.
        for domain in MemoryDomain::ALL {
            let Some(days) = cfg.retention_for(domain) else {
                // `None` = keep until forgotten — skip.
                continue;
            };
            if !self.has_domain_store(domain) {
                tracing::trace!(
                    "retention sweep: domain {} has retention but no backing store yet (ADR-0005); skipping",
                    domain.label()
                );
                continue;
            }
            let store = self.memory_for_domain(domain);
            let sessions = match store.list_sessions() {
                Ok(list) => list,
                Err(e) => {
                    tracing::warn!(
                        "retention sweep: list_sessions({}) failed: {e}; skipping domain",
                        domain.label()
                    );
                    continue;
                }
            };
            let cutoff_ms = now_ms.saturating_sub((days as u64) * 86_400_000);
            let mut domain_evicted: usize = 0;
            for session_id in &sessions {
                match store.prune_before(session_id, cutoff_ms) {
                    Ok(n) => domain_evicted = domain_evicted.saturating_add(n),
                    Err(e) => {
                        tracing::warn!(
                            "retention sweep: prune_before({} / {session_id}) failed: {e}",
                            domain.label()
                        );
                    }
                }
            }
            total_sessions_walked = total_sessions_walked.saturating_add(sessions.len());
            if domain_evicted > 0 {
                emit_memory_telemetry(self, emitted_at.0, telemetry_kind::FORGOTTEN, domain, None);
                total_evicted = total_evicted.saturating_add(domain_evicted);
            }
        }
        tracing::debug!(
            "retention sweep: evicted {} row(s) across {} session(s) in {} domain(s)",
            total_evicted,
            total_sessions_walked,
            Self::DOMAINS_WITH_STORE.len()
        );
        Ok(total_evicted)
    }

    // ---------------------------------------------------------------
    // Memory V2 step 6 (ADR-0002) — embeddings opt-in wiring
    // ---------------------------------------------------------------

    /// Best-effort embed + store for an already-persisted memory
    /// item. Runs only when:
    /// 1. `memory_config().embeddings.enabled == true`.
    /// 2. `domain` is one of `EMBED_ELIGIBLE_DOMAINS`
    ///    (Durable / Projects / Artifacts).
    ///
    /// On success: emits one L5 audit row via `MemoryEmbed` (via
    /// `build_action_request`), writes the vector to
    /// `self.embedding_store`, and emits one
    /// `memory_embedded` telemetry entry keyed to the same
    /// `memory_id` the primary write returned.
    ///
    /// On failure (provider unreachable, capability denied, store
    /// error): traces `warn!` and returns. The primary memory write
    /// has already landed; embeddings are additive signal, not
    /// required state.
    pub(crate) fn maybe_embed_on_write(
        &self,
        domain: MemoryDomain,
        memory_id: &str,
        content: &str,
        ts_ms: u64,
    ) {
        let cfg = self.memory_config();
        if !cfg.embeddings.enabled {
            return;
        }
        if !EMBED_ELIGIBLE_DOMAINS.contains(&domain) {
            return;
        }
        // L5 gate the embed path. A denying policy warns and skips;
        // no partial state is written.
        let (request, _) = build_action_request(self, Capability::MemoryEmbed);
        let decision = {
            let active = self.active.read().expect("active read lock");
            match active.policy.evaluate(request) {
                Ok(d) => d,
                Err(e) => {
                    tracing::warn!("embed policy evaluate: {e}");
                    return;
                }
            }
        };
        if !matches!(decision, Decision::Allow { .. }) {
            tracing::debug!("embed skipped: policy decision {}", deny_reason(&decision));
            return;
        }
        let provider = {
            let guard = self
                .embedding_provider
                .read()
                .expect("embedding provider read lock");
            guard.clone()
        };
        let vector = match provider.embed(content) {
            Ok(v) => v,
            Err(e) => {
                tracing::warn!("embed provider ({}): {e}", provider.label());
                return;
            }
        };
        let row = EmbeddingRow {
            memory_id: EmbedMemoryId::new(memory_id),
            domain,
            vector,
        };
        if let Err(e) = self.embedding_store.upsert(row) {
            tracing::warn!("embed store upsert: {e}");
            return;
        }
        emit_memory_telemetry(
            self,
            ts_ms,
            telemetry_kind::EMBEDDED,
            domain,
            Some(memory_id),
        );
    }

    /// Best-effort embedding deletion paired with any primary
    /// forget. Called from `memory_forget_item` paths. Unknown
    /// embeddings are a silent no-op — a row may have been evicted
    /// already, or the user may never have had embeddings enabled
    /// when the memory row was written.
    pub(crate) fn delete_embedding(&self, domain: MemoryDomain, memory_id: &str) {
        if !EMBED_ELIGIBLE_DOMAINS.contains(&domain) {
            return;
        }
        match self
            .embedding_store
            .delete(domain, &EmbedMemoryId::new(memory_id))
        {
            Ok(_) => {}
            Err(e) => tracing::warn!("embed store delete: {e}"),
        }
    }

    /// Read-only accessor for the embedding store — used by UI
    /// surfaces (Memory tab) and tests that need to assert on
    /// counts or run queries without touching the write path.
    pub fn embedding_store(&self) -> &dyn aether_l2_memory::EmbeddingStore {
        self.embedding_store.as_ref()
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
        cfg.default_risk
            .insert(MemoryDomain::Durable, MemoryRisk::Ask);
        cfg.default_risk
            .insert(MemoryDomain::Facts, MemoryRisk::Deny);
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
        // ADR-0004: Durable writes land in the Durable lane, not Session.
        let session_before = state.memory.recent("s1").expect("pre-recall").records.len();
        let durable_before = state
            .durable_memory
            .recent("s1")
            .expect("durable pre-recall")
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
                assert_eq!(turn_sequence, (durable_before as u64) + 1);
                assert!(memory_id.starts_with("mem-s1-"));
                assert!(!audit_id.is_empty(), "L5 must assign an audit id");
            }
            other => panic!("expected Allowed, got {other:?}"),
        }
        let session_after = state.memory.recent("s1").unwrap().records.len();
        let durable_after = state.durable_memory.recent("s1").unwrap().records.len();
        assert_eq!(
            session_after, session_before,
            "Session lane MUST be unchanged by a Durable write (ADR-0004 isolation)"
        );
        assert_eq!(
            durable_after,
            durable_before + 1,
            "Durable lane must grow by one"
        );
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
        cfg.default_risk
            .insert(MemoryDomain::Durable, MemoryRisk::Deny);
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

    // ---------- Edit (Auto) ----------

    #[test]
    fn edit_auto_domain_replaces_content_and_emits_edited_telemetry() {
        let state = setup_state();
        // Seed a Durable write so there's something to edit. Auto
        // domain, so the write persists immediately.
        let written = state
            .memory_write(
                MemoryDomain::Durable,
                "s1",
                "original".into(),
                MemoryRole::User,
            )
            .expect("seed write");
        let seq = match written {
            MemoryWriteOutcome::Allowed { turn_sequence, .. } => turn_sequence,
            other => panic!("expected Allowed, got {other:?}"),
        };
        let outcome = state
            .memory_edit(MemoryDomain::Durable, "s1", seq, "edited".into())
            .expect("edit call");
        match outcome {
            MemoryEditOutcome::Allowed { memory_id, .. } => {
                assert_eq!(memory_id, format!("mem-s1-{seq}"));
            }
            other => panic!("expected Allowed, got {other:?}"),
        }
        // Store actually mutated — ADR-0004 routes Durable edits to
        // the Durable lane.
        let w = state.durable_memory.recent("s1").expect("recent");
        assert_eq!(w.records[0].content, "edited");
        assert_eq!(w.records[0].sequence, seq);
        // Telemetry fired.
        let tel = state.telemetry_recent(20);
        assert!(tel.iter().any(|e| e.kind == telemetry_kind::EDITED));
    }

    #[test]
    fn edit_auto_domain_returns_not_found_when_row_missing() {
        let state = setup_state();
        let outcome = state
            .memory_edit(MemoryDomain::Durable, "s1", 999, "whatever".into())
            .expect("edit call");
        assert_eq!(outcome, MemoryEditOutcome::NotFound);
        // No `memory_edited` telemetry, because nothing was edited.
        let tel = state.telemetry_recent(20);
        assert!(!tel.iter().any(|e| e.kind == telemetry_kind::EDITED));
    }

    #[test]
    fn edit_ask_domain_returns_requires_approval_without_mutating() {
        let state = setup_state();
        // Facts is Ask by default; seeding via the gate would require
        // approval first, so go straight through the raw store.
        state
            .memory
            .append(TurnMemoryRecord {
                session_id: "s1".into(),
                sequence: 0,
                role: MemoryRole::User,
                content: "unchanged".into(),
                timestamp_ms: 1,
            })
            .unwrap();
        let outcome = state
            .memory_edit(MemoryDomain::Facts, "s1", 1, "EDITED".into())
            .expect("edit call");
        assert_eq!(outcome, MemoryEditOutcome::RequiresApproval);
        let w = state.memory.recent("s1").unwrap();
        assert_eq!(w.records[0].content, "unchanged");
    }

    #[test]
    fn edit_after_approval_persists_mutation_on_ask_domain() {
        let state = setup_state();
        state
            .memory
            .append(TurnMemoryRecord {
                session_id: "s1".into(),
                sequence: 0,
                role: MemoryRole::User,
                content: "v1".into(),
                timestamp_ms: 1,
            })
            .unwrap();
        let outcome = state
            .memory_edit_after_approval(MemoryDomain::Facts, "s1", 1, "v2".into())
            .expect("edit after approval");
        match outcome {
            MemoryEditOutcome::Allowed { memory_id, .. } => {
                assert_eq!(memory_id, "mem-s1-1");
            }
            other => panic!("expected Allowed, got {other:?}"),
        }
        let w = state.memory.recent("s1").unwrap();
        assert_eq!(w.records[0].content, "v2");
    }

    #[test]
    fn edit_deny_domain_short_circuits_without_mutating() {
        let state = setup_state();
        let mut cfg = MemoryConfig::defaults();
        cfg.default_risk
            .insert(MemoryDomain::Durable, MemoryRisk::Deny);
        state.set_memory_config(cfg).unwrap();
        // Seed via raw store so the Durable-deny gate doesn't block the
        // setup, then try to edit.
        state
            .memory
            .append(TurnMemoryRecord {
                session_id: "s1".into(),
                sequence: 0,
                role: MemoryRole::User,
                content: "locked".into(),
                timestamp_ms: 1,
            })
            .unwrap();
        let outcome = state
            .memory_edit(MemoryDomain::Durable, "s1", 1, "hijack".into())
            .expect("edit call");
        match outcome {
            MemoryEditOutcome::Denied { reason } => {
                assert_eq!(reason, "config_deny");
            }
            other => panic!("expected Denied, got {other:?}"),
        }
        let w = state.memory.recent("s1").unwrap();
        assert_eq!(w.records[0].content, "locked");
    }

    // ---------- Per-item forget ----------

    #[test]
    fn forget_item_auto_domain_removes_one_row_and_emits_telemetry() {
        let state = setup_state();
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
        // Target the middle row.
        let outcome = state
            .memory_forget_item(MemoryDomain::Durable, "s1", 2)
            .expect("forget item");
        match outcome {
            MemoryForgetOutcome::Allowed { removed_count, .. } => {
                assert_eq!(removed_count, 1);
            }
            other => panic!("expected Allowed, got {other:?}"),
        }
        // ADR-0004: Durable forget targets the Durable lane.
        let w = state.durable_memory.recent("s1").unwrap();
        assert_eq!(w.records.len(), 2);
        assert!(w.records.iter().all(|r| r.sequence != 2));
        let tel = state.telemetry_recent(30);
        assert!(tel.iter().any(|e| e.kind == telemetry_kind::FORGOTTEN));
    }

    #[test]
    fn forget_item_returns_not_found_when_row_missing() {
        let state = setup_state();
        let outcome = state
            .memory_forget_item(MemoryDomain::Durable, "s1", 999)
            .expect("forget item");
        assert_eq!(outcome, MemoryForgetOutcome::NotFound);
    }

    #[test]
    fn forget_item_ask_domain_returns_requires_approval() {
        let state = setup_state();
        let outcome = state
            .memory_forget_item(MemoryDomain::Facts, "s1", 1)
            .expect("forget item");
        assert_eq!(outcome, MemoryForgetOutcome::RequiresApproval);
    }

    #[test]
    fn forget_item_after_approval_removes_row() {
        let state = setup_state();
        state
            .memory
            .append(TurnMemoryRecord {
                session_id: "s1".into(),
                sequence: 0,
                role: MemoryRole::User,
                content: "sensitive".into(),
                timestamp_ms: 1,
            })
            .unwrap();
        let outcome = state
            .memory_forget_item_after_approval(MemoryDomain::Facts, "s1", 1)
            .expect("post-approval forget");
        match outcome {
            MemoryForgetOutcome::Allowed { removed_count, .. } => {
                assert_eq!(removed_count, 1);
            }
            other => panic!("expected Allowed, got {other:?}"),
        }
        assert!(state.memory.recent("s1").unwrap().records.is_empty());
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
        assert_eq!(
            count, 6,
            "each domain samples independently on its first tick"
        );
    }

    // ---------- Retention sweep (Memory V2 step 5) ----------

    fn seed_row(state: &AppState, sid: &str, content: &str, ts_ms: u64) {
        state
            .memory
            .append(TurnMemoryRecord {
                session_id: sid.into(),
                sequence: 0,
                role: MemoryRole::User,
                content: content.into(),
                timestamp_ms: ts_ms,
            })
            .unwrap();
    }

    #[test]
    fn sweep_no_retention_config_is_noop() {
        let state = setup_state();
        // Default config: Session retention = None → domain skipped.
        seed_row(&state, "s1", "keep-me", 1_000);
        let evicted = state.run_retention_sweep(9_999_999).expect("sweep");
        assert_eq!(evicted, 0);
        assert_eq!(state.memory.recent("s1").unwrap().records.len(), 1);
    }

    #[test]
    fn sweep_evicts_session_domain_when_retention_set() {
        let state = setup_state();
        // 1-day retention on Session.
        let mut cfg = MemoryConfig::defaults();
        cfg.retention_days.insert(MemoryDomain::Session, Some(1));
        state.set_memory_config(cfg).unwrap();
        // Row at ts=100 (ancient), row at ts= now - 1h (fresh).
        let day_ms: u64 = 86_400_000;
        let now_ms: u64 = 10 * day_ms;
        seed_row(&state, "s1", "ancient", 100);
        seed_row(&state, "s1", "fresh", now_ms - 3_600_000);
        let evicted = state.run_retention_sweep(now_ms).expect("sweep");
        assert_eq!(evicted, 1);
        let w = state.memory.recent("s1").unwrap();
        assert_eq!(w.records.len(), 1);
        assert_eq!(w.records[0].content, "fresh");
    }

    #[test]
    fn sweep_emits_memory_forgotten_telemetry_when_evicting() {
        let state = setup_state();
        let mut cfg = MemoryConfig::defaults();
        cfg.retention_days.insert(MemoryDomain::Session, Some(1));
        state.set_memory_config(cfg).unwrap();
        let day_ms: u64 = 86_400_000;
        let now_ms: u64 = 10 * day_ms;
        seed_row(&state, "s1", "old-a", 1);
        seed_row(&state, "s1", "old-b", 2);
        state.run_retention_sweep(now_ms).unwrap();
        let tel = state.telemetry_recent(200);
        let forgotten: Vec<_> = tel
            .iter()
            .filter(|e| e.kind == telemetry_kind::FORGOTTEN)
            .collect();
        // One aggregated telemetry row per domain per sweep.
        assert_eq!(forgotten.len(), 1);
        assert_eq!(
            forgotten[0].memory_domain.as_deref(),
            Some(MemoryDomain::Session.label())
        );
    }

    #[test]
    fn sweep_does_not_emit_telemetry_when_nothing_evicted() {
        let state = setup_state();
        let mut cfg = MemoryConfig::defaults();
        cfg.retention_days.insert(MemoryDomain::Session, Some(30));
        state.set_memory_config(cfg).unwrap();
        let day_ms: u64 = 86_400_000;
        let now_ms: u64 = 10 * day_ms;
        // Fresh row inside the 30-day window.
        seed_row(&state, "s1", "recent", now_ms - day_ms);
        state.run_retention_sweep(now_ms).unwrap();
        let tel = state.telemetry_recent(200);
        let forgotten = tel
            .iter()
            .filter(|e| e.kind == telemetry_kind::FORGOTTEN)
            .count();
        assert_eq!(forgotten, 0);
        assert_eq!(state.memory.recent("s1").unwrap().records.len(), 1);
    }

    #[test]
    fn sweep_walks_every_session() {
        let state = setup_state();
        let mut cfg = MemoryConfig::defaults();
        cfg.retention_days.insert(MemoryDomain::Session, Some(1));
        state.set_memory_config(cfg).unwrap();
        let day_ms: u64 = 86_400_000;
        let now_ms: u64 = 10 * day_ms;
        seed_row(&state, "s1", "old-a", 1);
        seed_row(&state, "s2", "old-b", 1);
        seed_row(&state, "s3", "fresh", now_ms - 1_000);
        let evicted = state.run_retention_sweep(now_ms).expect("sweep");
        assert_eq!(evicted, 2);
        assert!(state.memory.recent("s1").unwrap().is_empty());
        assert!(state.memory.recent("s2").unwrap().is_empty());
        assert_eq!(state.memory.recent("s3").unwrap().records.len(), 1);
    }

    #[test]
    fn sweep_skips_domains_without_a_backing_store_post_adr_0004() {
        // ADR-0004 gave Durable a real backing store. The remaining
        // four domains (Facts / Projects / Preferences / Artifacts)
        // still have none — ADR-0005 closes that gap. Setting a TTL
        // on one of those domains must not touch any other lane.
        let state = setup_state();
        let mut cfg = MemoryConfig::defaults();
        cfg.retention_days.insert(MemoryDomain::Projects, Some(1));
        cfg.retention_days.insert(MemoryDomain::Session, None);
        cfg.retention_days.insert(MemoryDomain::Durable, None);
        state.set_memory_config(cfg).unwrap();
        seed_row(&state, "s1", "ancient-session", 1);
        let evicted = state.run_retention_sweep(9_999_999).expect("sweep");
        assert_eq!(evicted, 0);
        assert_eq!(state.memory.recent("s1").unwrap().records.len(), 1);
    }

    // ---------- ADR-0004: per-domain lane isolation + Durable sweep ----------

    fn seed_durable_row(state: &AppState, sid: &str, content: &str, ts_ms: u64) {
        state
            .durable_memory
            .append(TurnMemoryRecord {
                session_id: sid.into(),
                sequence: 0,
                role: MemoryRole::User,
                content: content.into(),
                timestamp_ms: ts_ms,
            })
            .unwrap();
    }

    #[test]
    fn durable_writes_do_not_appear_in_session_lane() {
        // Core ADR-0004 invariant: a write tagged Durable must never
        // pollute the Session lane, and vice versa.
        let state = setup_state();
        state
            .memory_write(
                MemoryDomain::Durable,
                "s1",
                "durable-content".into(),
                MemoryRole::User,
            )
            .expect("durable write");
        state
            .memory_write(
                MemoryDomain::Session,
                "s1",
                "session-content".into(),
                MemoryRole::User,
            )
            .expect("session write");

        let session_window = state.memory.recent("s1").unwrap();
        let durable_window = state.durable_memory.recent("s1").unwrap();

        assert_eq!(session_window.records.len(), 1);
        assert_eq!(session_window.records[0].content, "session-content");
        assert_eq!(durable_window.records.len(), 1);
        assert_eq!(durable_window.records[0].content, "durable-content");
    }

    #[test]
    fn durable_sweep_prunes_durable_lane_without_touching_session() {
        // The single regression guard ADR-0004 was designed to buy:
        // running a retention sweep with a Durable TTL must evict
        // Durable rows and leave Session rows of the same age alone.
        let state = setup_state();
        let mut cfg = MemoryConfig::defaults();
        cfg.retention_days.insert(MemoryDomain::Durable, Some(1));
        cfg.retention_days.insert(MemoryDomain::Session, None);
        state.set_memory_config(cfg).unwrap();

        let day_ms: u64 = 86_400_000;
        let now_ms: u64 = 10 * day_ms;
        // Seed ancient rows — well before the Durable 1-day cutoff.
        seed_row(&state, "s1", "ancient-session", 1);
        seed_durable_row(&state, "s1", "ancient-durable", 1);

        let evicted = state.run_retention_sweep(now_ms).expect("sweep");
        assert_eq!(evicted, 1, "exactly the durable row evicts");
        assert_eq!(
            state.memory.recent("s1").unwrap().records.len(),
            1,
            "Session row of equal age MUST survive (no TTL set)"
        );
        assert!(
            state
                .durable_memory
                .recent("s1")
                .unwrap()
                .records
                .is_empty(),
            "Durable row evicted by 1-day TTL"
        );

        // Aggregated memory_forgotten telemetry fires exactly once
        // for the Durable domain (Decision #56 still applies).
        let tel = state.telemetry_recent(50);
        let durable_forgotten = tel
            .iter()
            .filter(|e| {
                e.kind == telemetry_kind::FORGOTTEN && e.memory_domain.as_deref() == Some("durable")
            })
            .count();
        assert_eq!(durable_forgotten, 1);
    }

    /// Belt-and-suspenders crash-safety guard for the retention sweep.
    ///
    /// Implementation note (Option 3 — synthetic crash via TempDir +
    /// reopen): we boot an `AppState` over a real on-disk SQLite file,
    /// seed three sessions of expired Session-lane rows + one fresh
    /// row, then **partially** prune by calling `prune_before` on
    /// session "s1" only — simulating "the process crashed after the
    /// first session was pruned but before the rest." We drop the
    /// `AppState` (releasing the SQLite handle), reopen a fresh
    /// `AppState` against the same file, and run the full retention
    /// sweep. End-state must be: every expired row gone across every
    /// session, the fresh row preserved.
    ///
    /// What this proves:
    ///   1. `prune_before` is durable — partial progress survives a
    ///      process restart (the SQL `DELETE` commits per call).
    ///   2. The sweep is idempotent against the post-crash state — re-
    ///      running it after the crash converges to the clean end-state
    ///      with no double-counted evictions or skipped rows.
    ///   3. `list_sessions()` after reopen still surfaces every session
    ///      that has surviving rows, so the second sweep visits s2/s3.
    ///
    /// Memory config is per-`AppState` (not persisted across reopen),
    /// so the second instance re-applies the Session retention. That's
    /// the realistic boot path: `main.rs` reloads config on startup
    /// before the boot sweep tick.
    #[cfg(feature = "sqlite-backend")]
    #[test]
    fn sweep_is_idempotent_across_simulated_mid_sweep_crash() {
        use tempfile::TempDir;

        let tmp = TempDir::new().expect("tempdir");
        let db_path = tmp.path().join("aether.db");

        let day_ms: u64 = 86_400_000;
        let now_ms: u64 = 10 * day_ms;
        // 1-day retention → cutoff = now - 1 day = 9 * day_ms.
        // Anything with ts_ms < cutoff_ms must be evicted.

        // ---- Phase 1: boot, seed, partial-prune (simulate crash) ----
        {
            let state =
                AppState::new_with_db_path(&db_path).expect("first AppState");
            // Only proceed if we actually got the durable backend.
            // If the temp-dir fallback to in-memory ever fires, this
            // test is a no-op against the wrong backend — bail loudly.
            assert!(
                state.durable_store().is_some(),
                "expected durable SQLite backend over temp file"
            );

            let mut cfg = MemoryConfig::defaults();
            cfg.retention_days.insert(MemoryDomain::Session, Some(1));
            state.set_memory_config(cfg).unwrap();

            // 3 sessions, each with one expired row (ts=1) and one
            // fresh row (well inside the 1-day window).
            for sid in ["s1", "s2", "s3"] {
                seed_row(&state, sid, "ancient", 1);
                seed_row(&state, sid, "fresh", now_ms - 3_600_000);
            }

            // Simulate "we crashed after pruning s1." Use the trait's
            // `prune_before` directly — same primitive the sweep calls
            // — but only against s1, then drop the AppState before
            // s2/s3 get touched.
            let cutoff_ms = now_ms.saturating_sub(day_ms);
            let session_store = state.memory_for_domain(MemoryDomain::Session);
            let pruned_s1 =
                session_store.prune_before("s1", cutoff_ms).expect("prune s1");
            assert_eq!(pruned_s1, 1, "s1 ancient row evicts pre-crash");

            // s1 fresh row survived; s2/s3 still have both rows each.
            assert_eq!(state.memory.recent("s1").unwrap().records.len(), 1);
            assert_eq!(state.memory.recent("s2").unwrap().records.len(), 2);
            assert_eq!(state.memory.recent("s3").unwrap().records.len(), 2);
            // AppState dropped at end of scope — releases SQLite handle.
        }

        // ---- Phase 2: reopen, run full sweep, assert clean state ----
        let state2 =
            AppState::new_with_db_path(&db_path).expect("second AppState");
        assert!(
            state2.durable_store().is_some(),
            "reopen must land on the durable backend, not the in-memory fallback"
        );

        // Re-apply retention (config is per-AppState, not persisted).
        let mut cfg = MemoryConfig::defaults();
        cfg.retention_days.insert(MemoryDomain::Session, Some(1));
        state2.set_memory_config(cfg).unwrap();

        // After reopen, all three sessions should still surface (each
        // has surviving rows) and the partial pre-crash state must be
        // exactly: s1 has the fresh row only, s2/s3 still have both.
        let session_store = state2.memory_for_domain(MemoryDomain::Session);
        let mut sessions = session_store.list_sessions().expect("list_sessions");
        sessions.sort();
        assert_eq!(sessions, vec!["s1".to_string(), "s2".into(), "s3".into()]);
        assert_eq!(state2.memory.recent("s1").unwrap().records.len(), 1);
        assert_eq!(state2.memory.recent("s2").unwrap().records.len(), 2);
        assert_eq!(state2.memory.recent("s3").unwrap().records.len(), 2);

        // Run the full sweep — it must pick up where the crash left
        // off without double-counting s1.
        let evicted = state2.run_retention_sweep(now_ms).expect("sweep");
        assert_eq!(
            evicted, 2,
            "exactly the s2 + s3 ancient rows evict (s1 already pruned pre-crash)"
        );

        // End-state: every ancient row gone, every fresh row kept.
        for sid in ["s1", "s2", "s3"] {
            let w = state2.memory.recent(sid).unwrap();
            assert_eq!(w.records.len(), 1, "session {sid} keeps its fresh row");
            assert_eq!(w.records[0].content, "fresh");
        }

        // Idempotency: running the sweep again is a clean no-op.
        let second_pass = state2.run_retention_sweep(now_ms).expect("re-sweep");
        assert_eq!(second_pass, 0, "repeat sweep over a clean store evicts nothing");
        for sid in ["s1", "s2", "s3"] {
            assert_eq!(state2.memory.recent(sid).unwrap().records.len(), 1);
        }
    }

    #[test]
    fn memory_for_domain_falls_back_to_session_for_unbacked_domains() {
        // Contract: Session + Durable get dedicated lanes; everything
        // else falls back to Session with a warn!. This test guards
        // against a silent regression where an unbacked domain starts
        // routing elsewhere without an ADR-0005.
        use std::sync::Arc as StdArc;
        let state = setup_state();
        let session_store = state.memory_for_domain(MemoryDomain::Session);
        let durable_store = state.memory_for_domain(MemoryDomain::Durable);
        let projects_store = state.memory_for_domain(MemoryDomain::Projects);
        let facts_store = state.memory_for_domain(MemoryDomain::Facts);

        // Session + Durable are distinct Arcs.
        assert!(
            !StdArc::ptr_eq(&session_store, &durable_store),
            "Session and Durable must be distinct stores"
        );
        // Unbacked domains alias the Session store.
        assert!(
            StdArc::ptr_eq(&session_store, &projects_store),
            "Projects currently falls back to Session (ADR-0005 pending)"
        );
        assert!(
            StdArc::ptr_eq(&session_store, &facts_store),
            "Facts currently falls back to Session (ADR-0005 pending)"
        );
    }

    #[test]
    fn domains_with_store_is_session_and_durable_only() {
        // Rot-guard constant: if ADR-0005 lands and Projects/Artifacts
        // gain stores, this assertion forces a deliberate update.
        assert_eq!(AppState::DOMAINS_WITH_STORE.len(), 2);
        assert!(AppState::DOMAINS_WITH_STORE.contains(&MemoryDomain::Session));
        assert!(AppState::DOMAINS_WITH_STORE.contains(&MemoryDomain::Durable));
    }

    // ---------- Embeddings (Memory V2 step 6, ADR-0002) ----------

    use aether_l2_memory::embeddings::StubEmbedder;
    use std::sync::Arc as StdArc;

    fn swap_stub_embedder(state: &AppState) {
        let stub: StdArc<dyn aether_l2_memory::EmbeddingProvider> =
            StdArc::new(StubEmbedder::new(16));
        *state
            .embedding_provider
            .write()
            .expect("embedding provider write lock") = stub;
    }

    fn enable_embeddings(state: &AppState) {
        let mut cfg = state.memory_config();
        cfg.embeddings.enabled = true;
        cfg.embeddings.provider = Some("stub:16".into());
        state.set_memory_config(cfg).expect("enable embeddings");
    }

    #[test]
    fn embed_disabled_produces_no_rows_and_no_telemetry() {
        let state = setup_state();
        swap_stub_embedder(&state);
        // Default memory_config has embeddings.enabled = false.
        state
            .memory_write(
                MemoryDomain::Durable,
                "s1",
                "the quick brown fox".into(),
                MemoryRole::User,
            )
            .expect("write");
        assert_eq!(
            state
                .embedding_store()
                .count(MemoryDomain::Durable)
                .unwrap(),
            0
        );
        let tel = state.telemetry_recent(200);
        assert_eq!(
            tel.iter()
                .filter(|e| e.kind == telemetry_kind::EMBEDDED)
                .count(),
            0
        );
    }

    #[test]
    fn embed_enabled_writes_a_row_and_emits_telemetry_for_durable() {
        let state = setup_state();
        swap_stub_embedder(&state);
        enable_embeddings(&state);
        state
            .memory_write(
                MemoryDomain::Durable,
                "s1",
                "remember this please".into(),
                MemoryRole::User,
            )
            .expect("write");
        assert_eq!(
            state
                .embedding_store()
                .count(MemoryDomain::Durable)
                .unwrap(),
            1
        );
        let tel = state.telemetry_recent(200);
        let embedded = tel
            .iter()
            .filter(|e| e.kind == telemetry_kind::EMBEDDED)
            .count();
        assert_eq!(embedded, 1);
    }

    #[test]
    fn embed_skipped_for_ineligible_domain_session() {
        let state = setup_state();
        swap_stub_embedder(&state);
        enable_embeddings(&state);
        state
            .memory_write(
                MemoryDomain::Session,
                "s1",
                "chat chat chat".into(),
                MemoryRole::User,
            )
            .expect("write");
        // Session is not embed-eligible.
        assert_eq!(
            state
                .embedding_store()
                .count(MemoryDomain::Durable)
                .unwrap(),
            0
        );
        // Ineligible domain still gets a memory_written row — just no
        // memory_embedded row.
        let tel = state.telemetry_recent(200);
        assert_eq!(
            tel.iter()
                .filter(|e| e.kind == telemetry_kind::EMBEDDED)
                .count(),
            0
        );
        assert!(tel.iter().any(|e| e.kind == telemetry_kind::WRITTEN));
    }

    #[test]
    fn embed_written_only_for_embed_eligible_domains() {
        let state = setup_state();
        swap_stub_embedder(&state);
        enable_embeddings(&state);
        // Write into each embed-eligible domain. Facts is Ask so we
        // use the post-approval path for it.
        state
            .memory_write(MemoryDomain::Durable, "s1", "a".into(), MemoryRole::User)
            .unwrap();
        state
            .memory_write(MemoryDomain::Projects, "s1", "b".into(), MemoryRole::User)
            .unwrap();
        state
            .memory_write_after_approval(
                MemoryDomain::Artifacts,
                "s1",
                "c".into(),
                MemoryRole::User,
            )
            .unwrap();
        assert_eq!(
            state
                .embedding_store()
                .count(MemoryDomain::Durable)
                .unwrap(),
            1
        );
        assert_eq!(
            state
                .embedding_store()
                .count(MemoryDomain::Projects)
                .unwrap(),
            1
        );
        assert_eq!(
            state
                .embedding_store()
                .count(MemoryDomain::Artifacts)
                .unwrap(),
            1
        );
    }

    #[test]
    fn forget_item_removes_paired_embedding_row() {
        let state = setup_state();
        swap_stub_embedder(&state);
        enable_embeddings(&state);
        // Durable auto-flow — single write lands row at sequence 1.
        state
            .memory_write(
                MemoryDomain::Durable,
                "s1",
                "forget-me".into(),
                MemoryRole::User,
            )
            .expect("write");
        assert_eq!(
            state
                .embedding_store()
                .count(MemoryDomain::Durable)
                .unwrap(),
            1
        );
        // Durable domain defaults to Auto posture.
        state
            .memory_forget_item(MemoryDomain::Durable, "s1", 1)
            .expect("forget item");
        assert_eq!(
            state
                .embedding_store()
                .count(MemoryDomain::Durable)
                .unwrap(),
            0
        );
    }

    #[test]
    fn embed_provider_failure_does_not_block_primary_write() {
        // Default OllamaEmbeddingProvider will fail when no daemon is
        // running — use that as a natural "provider unreachable" test.
        // Memory write must still succeed, just without an embedding.
        let state = setup_state();
        // NOTE: no swap_stub_embedder — keep the default Ollama provider.
        // Point it at a definitely-unreachable port so transport fails
        // fast rather than attempting a 30s connect.
        std::env::set_var("AETHER_EMBED_OLLAMA_BASE_URL", "http://127.0.0.1:1");
        let provider: StdArc<dyn aether_l2_memory::EmbeddingProvider> =
            StdArc::new(aether_l2_memory::OllamaEmbeddingProvider::from_env());
        *state
            .embedding_provider
            .write()
            .expect("embedding provider write lock") = provider;
        std::env::remove_var("AETHER_EMBED_OLLAMA_BASE_URL");
        enable_embeddings(&state);
        let outcome = state
            .memory_write(
                MemoryDomain::Durable,
                "s1",
                "primary write must succeed".into(),
                MemoryRole::User,
            )
            .expect("write");
        match outcome {
            MemoryWriteOutcome::Allowed { .. } => {}
            other => panic!("primary write must succeed, got {other:?}"),
        }
        // No embedding row landed — provider failed.
        assert_eq!(
            state
                .embedding_store()
                .count(MemoryDomain::Durable)
                .unwrap(),
            0
        );
    }
}
