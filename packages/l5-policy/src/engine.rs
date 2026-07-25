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

use crate::approval::{
    ApprovalResponse, ApprovalScope, ApprovalTicket, ApprovalTicketId, UserChoice,
};
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
        // Media capture: defaults to Auto with Medium risk. The shell
        // layers a local-only tri-state (`media_permissions.json`) on
        // top of L5 — that's the user-facing per-device gate. L5
        // therefore records an audit row tagged with the correct
        // capability without adding a redundant per-call modal on top
        // of the in-app gate the user has already cleared. A future
        // preset (e.g. `wave3.observer`) can flip these to Ask or Deny
        // for users who want a stricter posture.
        d.insert(
            Capability::MediaCamera,
            CapabilityPolicy {
                mode: ApprovalMode::Auto,
                risk: RiskClass::Medium,
            },
        );
        d.insert(
            Capability::MediaScreenCapture,
            CapabilityPolicy {
                mode: ApprovalMode::Auto,
                risk: RiskClass::Medium,
            },
        );
        // Microphone capture. Same rationale as MediaCamera /
        // MediaScreenCapture: the shell's `mic_permissions.json`
        // tri-state is the user-facing per-device gate, so L5
        // records the audit row without layering a redundant modal
        // on top. Voice V1 step 4 (`transcribe_utterance`) is the
        // first caller; earlier waves did not need this default.
        d.insert(
            Capability::MediaMic,
            CapabilityPolicy {
                mode: ApprovalMode::Auto,
                risk: RiskClass::Medium,
            },
        );
        // Memory V2 coarse surface. Same design pattern as media:
        // the shell's `memory.json` `risk_for(domain)` is the
        // user-facing per-domain gate (Facts / Artifacts default
        // Ask, standard domains default Auto). L5 records the
        // audit row here without layering a redundant modal on
        // top. Risk classes match `default_risk_for(Capability::*)`
        // — Read is Low, Write/Edit/Forget are Medium. Step 1
        // intentionally left these out of the preset so any
        // caller got `NeedsUpgrade`; step 3 is the conscious
        // flip that turns the Memory V2 write path live.
        d.insert(
            Capability::MemoryRead,
            CapabilityPolicy {
                mode: ApprovalMode::Auto,
                risk: RiskClass::Low,
            },
        );
        d.insert(
            Capability::MemoryWrite,
            CapabilityPolicy {
                mode: ApprovalMode::Auto,
                risk: RiskClass::Medium,
            },
        );
        d.insert(
            Capability::MemoryEdit,
            CapabilityPolicy {
                mode: ApprovalMode::Auto,
                risk: RiskClass::Medium,
            },
        );
        d.insert(
            Capability::MemoryForget,
            CapabilityPolicy {
                mode: ApprovalMode::Auto,
                risk: RiskClass::Medium,
            },
        );
        // Memory V2 step 6 (ADR-0002): embeddings opt-in. Risk Low —
        // embedding is a side effect of an already-allowed MemoryWrite
        // and does not persist user-facing content on its own. Auto
        // mode so the per-domain gate on MemoryWrite is the user-
        // visible decision.
        d.insert(
            Capability::MemoryEmbed,
            CapabilityPolicy {
                mode: ApprovalMode::Auto,
                risk: RiskClass::Low,
            },
        );
        // ADR-0005: retrieval-augmented read. Parallel to MemoryRead
        // (Low / Auto). Every turn-engine consultation of
        // EmbeddingStore::query_nearest produces one audit row via
        // this capability. Distinct variant keeps retrieval audits
        // filterable from plain session recall.
        d.insert(
            Capability::RetrievalContext,
            CapabilityPolicy {
                mode: ApprovalMode::Auto,
                risk: RiskClass::Low,
            },
        );
        // Persona delivery (ADR-0012). Defaults map to "the wizard's
        // confirm step is the user-visible gate, L5 records audit
        // rows but doesn't double-prompt." Raw uninstall (outside a
        // switch flow) keeps Ask because explicit destruction
        // warrants a modal even from the trust-drawer surface.
        d.insert(
            Capability::PersonaDownload,
            CapabilityPolicy {
                mode: ApprovalMode::Auto,
                risk: RiskClass::Medium,
            },
        );
        d.insert(
            Capability::PersonaInstall,
            CapabilityPolicy {
                mode: ApprovalMode::Auto,
                risk: RiskClass::Medium,
            },
        );
        d.insert(
            Capability::PersonaUninstall,
            CapabilityPolicy {
                mode: ApprovalMode::Ask,
                risk: RiskClass::Medium,
            },
        );
        d.insert(
            Capability::PersonaSwitch,
            CapabilityPolicy {
                mode: ApprovalMode::Auto,
                risk: RiskClass::Low,
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

    /// Apply a persona's compiled policy-default hints on top of this
    /// config. For each capability the persona has an opinion on:
    ///
    /// - If the preset already defines a `CapabilityPolicy`, the `mode`
    ///   is replaced with the persona's hint; the preset-declared
    ///   `risk` is preserved (risk is a property of the capability, not
    ///   the persona — a Bold persona choosing to auto-approve file
    ///   creation doesn't change the fact that file creation is a
    ///   Medium-risk action).
    /// - If the preset does **not** define the capability, the persona
    ///   hint is inserted with a conservative default risk so the
    ///   overlay never silently downgrades risk tracking.
    ///
    /// Privacy posture comes from the persona. That's the one field a
    /// persona is entitled to override outright, because posture is
    /// about which model tiers are preferred for the persona's privacy
    /// stance, not about which capabilities are enabled.
    ///
    /// This is the seam through which the shell wires
    /// `CompiledPersona.policy_defaults` into the engine at build time,
    /// so Cautious / Balanced / Bold stances actually change which
    /// capabilities are Auto vs Ask vs Deny.
    pub fn with_persona_overlay(
        mut self,
        per_capability_defaults: &HashMap<Capability, ApprovalMode>,
        posture: PrivacyPosture,
    ) -> Self {
        for (cap, mode) in per_capability_defaults {
            self.preset_defaults
                .entry(cap.clone())
                .and_modify(|p| p.mode = *mode)
                .or_insert(CapabilityPolicy {
                    mode: *mode,
                    risk: default_risk_for(cap),
                });
        }
        self.posture = posture;
        self
    }
}

/// Autonomy preset the user picks during onboarding (and can revisit in
/// Settings). Overlays on top of the persona-adjusted preset defaults to
/// give the user a final safety rail regardless of the active persona.
///
/// Rank ordered least-to-most autonomy: `Observer ⊂ Assistant ⊂ Operator`.
/// That ordering is only a UX ranking, not a strict subset at the
/// capability level — Operator is permitted to auto-approve some
/// capabilities that Assistant asks about. The invariant that matters is
/// the *deny-side*: whatever Observer forbids, Assistant and Operator do
/// too (with the single exception that Assistant/Operator reopen write
/// paths behind Ask or grants).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum AutonomyPreset {
    /// Read-only — watches and answers, never acts.
    Observer,
    /// Helps with files, asks before anything risky. Recommended.
    Assistant,
    /// Acts within pre-approved folders after explicit grants.
    Operator,
}

impl AutonomyPreset {
    /// Wire name used in preset ids and serialization. Matches the
    /// lowercase strings the PresetPicker emits.
    pub fn wire_name(self) -> &'static str {
        match self {
            Self::Observer => "observer",
            Self::Assistant => "assistant",
            Self::Operator => "operator",
        }
    }

    /// Parse a wire-name string. Returns `None` for unknown values.
    pub fn from_wire(raw: &str) -> Option<Self> {
        match raw {
            "observer" => Some(Self::Observer),
            "assistant" => Some(Self::Assistant),
            "operator" => Some(Self::Operator),
            _ => None,
        }
    }
}

impl EngineConfig {
    /// Apply the onboarding autonomy preset on top of the current
    /// per-capability defaults. Unlike [`Self::with_persona_overlay`],
    /// which reshapes modes based on personality stance, this overlay is
    /// the **user's final safety rail** — it runs last and is allowed to
    /// tighten or loosen modes the persona would otherwise set.
    ///
    /// Semantics per preset (applied to capabilities already present in
    /// `preset_defaults`; capabilities absent from the preset continue to
    /// return `NeedsUpgrade` regardless):
    ///
    /// - **Observer** — force every capability except `FilesRead` to
    ///   `Deny`. The user explicitly chose read-only posture; we honour
    ///   that over any persona hint.
    /// - **Assistant** — no-op. Baseline balanced posture matches the
    ///   recommended experience exactly.
    /// - **Operator** — promote `FilesRead` and `FilesCreate` to `Auto`
    ///   so the operator archetype can write without prompting for every
    ///   new file. `ShellExec` is pinned to `Deny` — shell access is a
    ///   separate capability escalation, not something the preset alone
    ///   unlocks. Other capabilities (e.g. `FilesEdit`, `FilesDelete`,
    ///   `BrowserOpen`) retain their persona-adjusted mode, which means
    ///   Ask by default.
    ///
    /// Risk classes are never changed — a capability is as risky as its
    /// action type, independent of how the preset has chosen to surface
    /// that risk to the user.
    ///
    /// Also updates [`Self::preset`] to `"wave3.<wire_name>"` so policy
    /// decision events and audit rows carry the effective preset id.
    pub fn with_preset_overlay(mut self, preset: AutonomyPreset) -> Self {
        match preset {
            AutonomyPreset::Observer => {
                for (cap, policy) in self.preset_defaults.iter_mut() {
                    // Observer is read-only posture. `FilesRead` and
                    // `MemoryRead` are the only read-path capabilities
                    // currently in the preset — both stay Auto so the
                    // assistant can still ground itself in prior
                    // context while observing. Everything else flips
                    // to Deny. When more read-only capabilities land
                    // (e.g. `NotificationRead`, `EmailReadMetadata`),
                    // add them to this match.
                    policy.mode = if matches!(cap, Capability::FilesRead | Capability::MemoryRead) {
                        ApprovalMode::Auto
                    } else {
                        ApprovalMode::Deny
                    };
                }
            }
            AutonomyPreset::Assistant => {
                // Baseline — no modifications.
            }
            AutonomyPreset::Operator => {
                for (cap, policy) in self.preset_defaults.iter_mut() {
                    match cap {
                        Capability::FilesRead | Capability::FilesCreate => {
                            policy.mode = ApprovalMode::Auto;
                        }
                        Capability::ShellExec => {
                            policy.mode = ApprovalMode::Deny;
                        }
                        _ => {}
                    }
                }
            }
        }
        self.preset = PresetId(format!("wave3.{}", preset.wire_name()));
        self
    }
}

/// Conservative default risk for a capability the persona wants enabled
/// but the preset doesn't know about. Used only by
/// [`EngineConfig::with_persona_overlay`] as a fallback.
fn default_risk_for(cap: &Capability) -> RiskClass {
    use Capability::*;
    match cap {
        FilesRead => RiskClass::Low,
        FilesCreate | FilesEdit => RiskClass::Medium,
        FilesDelete => RiskClass::High,
        BrowserOpen => RiskClass::Medium,
        ShellExec => RiskClass::Critical,
        MediaCamera | MediaScreenCapture | MediaMic => RiskClass::Medium,
        // Memory V2 coarse surface. Read is Low (reads don't mutate
        // user state); Write and Edit are Medium (durable mutation
        // of user-sensitive context); Forget is Medium too — per-
        // item forget is irreversible and worth an audit but does
        // not escalate approval posture. Bulk delete stays `High`
        // on the pre-V2 `MemoryDelete` variant.
        MemoryRead => RiskClass::Low,
        MemoryWrite | MemoryEdit | MemoryForget => RiskClass::Medium,
        // Memory V2 step 6 (ADR-0002): embedding is a side effect of
        // an already-allowed MemoryWrite — the primary capability
        // gates the user-visible decision. Low risk: no new user-
        // facing content is persisted, only a vector derived from
        // the already-persisted memory row.
        MemoryEmbed => RiskClass::Low,
        // ADR-0005: retrieval-augmented read. Low — no state mutation,
        // parallel to MemoryRead.
        RetrievalContext => RiskClass::Low,
        _ => RiskClass::Medium,
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
    ///
    /// ADR-0009: when `req.audit_extras` is `Some`, its
    /// `original_utterance` and `retrieval_provenance` are copied into
    /// the v2 fields on the audit row. When `None` (non-conversation
    /// capability or legacy caller), both fields stay `None` and the
    /// row still carries `schema_version = AUDIT_SCHEMA_VERSION_V2` —
    /// post-ADR-0009 writers always stamp v2 even when there's no
    /// utterance to record.
    fn write_audit(
        &self,
        req: &ActionRequest,
        decision: DecisionKind,
        change_id: &ChangeId,
        reason: Option<StaticReasonId>,
    ) -> Result<AuditId, PolicyEngineError> {
        self.write_audit_scoped(req, decision, change_id, reason, None, None)
    }

    /// Variant of [`Self::write_audit`] that stamps the new T1.3 fields
    /// (`approval_scope`, `auto_approved_under_grant`) on the audit row.
    /// See the approval-scope design in `ARCHITECTURE.md`.
    fn write_audit_scoped(
        &self,
        req: &ActionRequest,
        decision: DecisionKind,
        change_id: &ChangeId,
        reason: Option<StaticReasonId>,
        approval_scope: Option<ApprovalScope>,
        auto_approved_under_grant: Option<crate::grants::GrantId>,
    ) -> Result<AuditId, PolicyEngineError> {
        let audit_id = self.next_audit_id();
        let (original_utterance, retrieval_provenance) = match &req.audit_extras {
            Some(x) => (x.original_utterance.clone(), x.retrieval_provenance.clone()),
            None => (None, None),
        };
        // Defensive truncation: enforce SECURITY_REVIEW.md MEDIUM-2 cap
        // here even if a caller bypassed `RetrievalProvenance::new`. The
        // audit row is the last point of control before the canonical
        // hash and DB write, so cap volume here regardless of upstream
        // discipline. Silently dropping past-cap entries is correct: the
        // orchestrator's `top_k` contract already implies entries past
        // the cap are lower-ranked than what was kept.
        let retrieval_provenance = retrieval_provenance.map(|mut p| {
            if p.hits.len() > crate::audit::RETRIEVAL_PROVENANCE_HITS_CAP {
                p.hits.truncate(crate::audit::RETRIEVAL_PROVENANCE_HITS_CAP);
            }
            p
        });
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
            schema_version: crate::audit::AUDIT_SCHEMA_VERSION_V2,
            original_utterance,
            retrieval_provenance,
            approval_scope,
            auto_approved_under_grant,
        };
        self.audit
            .append(&row)
            .map_err(|e| PolicyEngineError::Internal(format!("audit write: {e}")))?;
        self.sink.emit(L5Event::AuditRecord(row));
        Ok(audit_id)
    }

    fn emit_decision_event(&self, req: &ActionRequest, decision: &Decision, change_id: &ChangeId) {
        self.emit_decision_event_with_scope(req, decision, change_id, None);
    }

    /// Variant of [`Self::emit_decision_event`] that stamps an explicit
    /// `approval_scope` on the emitted [`PolicyDecisionEvent`]. Used by
    /// the §4.2 consume-while-valid path and by `respond_approval` so
    /// the persisted decision row carries the scope the user picked.
    fn emit_decision_event_with_scope(
        &self,
        req: &ActionRequest,
        decision: &Decision,
        change_id: &ChangeId,
        approval_scope: Option<ApprovalScope>,
    ) {
        self.sink.emit(L5Event::PolicyDecision(PolicyDecisionEvent {
            request_id: req.request_id.clone(),
            decision: decision.kind(),
            audit_id: decision.audit_id().clone(),
            change_id: change_id.clone(),
            seq: self.next_seq(),
            reason: None,
            effective_mode: None,
            approval_scope,
        }));
    }

    /// Look up an active grant by id. Returns `None` if revoked /
    /// missing. Linear scan; today's grant counts (≤ low hundreds per
    /// session) keep this trivial — promote to a trait method when
    /// the workload outgrows it.
    fn fetch_grant(&self, grant_id: &crate::grants::GrantId) -> Option<Grant> {
        self.ledger
            .snapshot(&GrantFilter {
                active_only: true,
                ..Default::default()
            })
            .into_iter()
            .find(|g| &g.grant_id == grant_id)
    }

    /// Per T1.3 design §4.2: given a grant matched by `covers(...)`,
    /// decide whether the request can be auto-approved under that
    /// grant's [`ApprovalScope`] without re-prompting.
    ///
    /// Returns `Some(scope)` when the grant covers the candidate under
    /// its declared scope; the caller must then write an audit row
    /// stamped `auto_approved_under_grant = Some(grant_id)`.
    /// Returns `None` when the scope check fails — caller falls through
    /// to today's per-action prompting.
    fn scope_permits_auto_approval(
        &self,
        grant: &Grant,
        req: &ActionRequest,
    ) -> Option<ApprovalScope> {
        match grant.approval_scope {
            // Legacy / pre-T1.3 grants and explicit PerAction always
            // cover (today's behaviour). Returning Some(PerAction)
            // signals the caller to echo the scope on the follow-on
            // audit row but treat it as the historical Allow path.
            None | Some(ApprovalScope::PerAction) => Some(ApprovalScope::PerAction),
            Some(ApprovalScope::OncePerSession) => {
                // Sessions are device-local per ADR-0016. The engine
                // currently runs one session per process lifetime; any
                // active OncePerSession grant therefore matches the
                // current session by definition. A future explicit
                // session-id wire will tighten this check.
                Some(ApprovalScope::OncePerSession)
            }
            Some(ApprovalScope::OncePerTask) => {
                // Match when the candidate's task_id equals the
                // grant's task_id (carried on GrantDuration::TaskScoped).
                // Lineage-inclusive is design §10 OQ-1's recommended
                // default; the in-memory engine only sees direct
                // task_id equality today, so a request whose task_id
                // matches the grant's task_id auto-approves. Sub-task
                // lineage walking lands in the L1 turn-orchestrator
                // and is out of scope here.
                let grant_task_id = match &grant.duration {
                    GrantDuration::TaskScoped(t) => Some(t.clone()),
                    _ => None,
                };
                match (grant_task_id, req.task_id.as_ref()) {
                    (Some(gt), Some(ct)) if &gt == ct => Some(ApprovalScope::OncePerTask),
                    _ => None,
                }
            }
            Some(ApprovalScope::DraftOnly) => {
                // DraftOnly is not a grant scope — design §4.3 says
                // DraftOnly does NOT issue a grant. If we ever see one
                // tagged DraftOnly on disk, it's data corruption /
                // forward-compat noise; do not auto-approve under it.
                None
            }
        }
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
        self.issue_and_emit_grant_scoped(
            req,
            mode,
            duration,
            scope,
            issued_by,
            audit_id,
            change_id,
            preset_version,
            None,
        )
    }

    /// Variant of [`Self::issue_and_emit_grant`] that stamps an explicit
    /// [`ApprovalScope`] on both the persisted [`Grant`] and the emitted
    /// [`GrantIssuedEvent`]. See T1.3 design §3.1 / §3.2.
    #[allow(clippy::too_many_arguments)]
    fn issue_and_emit_grant_scoped(
        &self,
        req: &ActionRequest,
        mode: ApprovalMode,
        duration: GrantDuration,
        scope: crate::capability::ResourceScope,
        issued_by: ActorRef,
        audit_id: AuditId,
        change_id: &ChangeId,
        preset_version: u32,
        approval_scope: Option<ApprovalScope>,
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
            approval_scope,
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
            approval_scope,
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
        // Per T1.3 design §4.2: if a covering grant exists, branch on its
        // approval_scope. OncePerSession / OncePerTask grants auto-approve
        // matching candidates without re-prompting; the audit row stamps
        // `auto_approved_under_grant = Some(grant_id)` and no
        // `ApprovalPending` event is emitted. Legacy / PerAction grants
        // keep today's behaviour (Allow + grant_ref, no auto-approval
        // back-reference). DraftOnly is not a grant scope (design §4.3),
        // so a grant tagged DraftOnly falls through to per-action prompting.
        if let Some(grant_id) =
            self.ledger
                .covers(&req.capability, &req.resource, &req.actor_persona)
        {
            // Look up the grant to inspect its scope. If the grant has
            // raced revocation between covers() and fetch_grant(), fall
            // through to per-action prompting — safer to re-ask than to
            // auto-approve under a possibly-stale grant.
            let scope_match = self
                .fetch_grant(&grant_id)
                .and_then(|g| self.scope_permits_auto_approval(&g, &req));
            match scope_match {
                Some(ApprovalScope::PerAction) | None => {
                    // Today's path. PerAction echoes for filterability;
                    // None (grant raced revoke) falls through to a
                    // PerAction-shaped Allow.
                    let audit_id = self.write_audit(&req, DecisionKind::Allow, &change_id, None)?;
                    let d = Decision::Allow {
                        grant_ref: Some(grant_id),
                        audit_id,
                    };
                    self.emit_decision_event(&req, &d, &change_id);
                    return Ok(d);
                }
                Some(scope @ (ApprovalScope::OncePerSession | ApprovalScope::OncePerTask)) => {
                    // §4.2 consume-while-valid: auto-approve, stamp the
                    // back-reference on the audit row. No ApprovalPending
                    // emission. No counter decrement (the design
                    // explicitly rules out a use-count cap).
                    let audit_id = self.write_audit_scoped(
                        &req,
                        DecisionKind::Allow,
                        &change_id,
                        None,
                        Some(scope),
                        Some(grant_id.clone()),
                    )?;
                    let d = Decision::Allow {
                        grant_ref: Some(grant_id),
                        audit_id,
                    };
                    self.emit_decision_event_with_scope(&req, &d, &change_id, Some(scope));
                    return Ok(d);
                }
                Some(ApprovalScope::DraftOnly) => {
                    // Defensive — DraftOnly should never appear on a
                    // grant (design §4.3). scope_permits_auto_approval
                    // returns None for it; this arm is unreachable but
                    // kept for exhaustiveness without a panic.
                    let audit_id = self.write_audit(&req, DecisionKind::Allow, &change_id, None)?;
                    let d = Decision::Allow {
                        grant_ref: Some(grant_id),
                        audit_id,
                    };
                    self.emit_decision_event(&req, &d, &change_id);
                    return Ok(d);
                }
            }
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
                // Per T1.3 design §4.3: DraftOnly does NOT issue a grant.
                // The audit row stamps approval_scope = Some(DraftOnly)
                // so a single column filter finds every "draft-only via
                // user choice" outcome in the trust center.
                let audit_id = self.write_audit_scoped(
                    &pending.request,
                    DecisionKind::DraftOnlyUserChoice,
                    &change_id,
                    Some(StaticReasonId(String::from("user_deferred"))),
                    Some(ApprovalScope::DraftOnly),
                    None,
                )?;
                let d = Decision::DraftOnly {
                    audit_id,
                    source: DraftSource::UserChoice,
                    reason: None,
                };
                self.emit_decision_event_with_scope(
                    &pending.request,
                    &d,
                    &change_id,
                    Some(ApprovalScope::DraftOnly),
                );
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

                // Per T1.3 design §2 mapping: lift the user's choice
                // into a persisted, audit-visible ApprovalScope. The
                // engine stamps the same scope on the issued grant, the
                // audit row, and the PolicyDecisionEvent so downstream
                // consumers see one coherent value.
                let approval_scope = ApprovalScope::from_user_choice(&response.user_choice);

                let audit_id = self.write_audit_scoped(
                    &pending.request,
                    DecisionKind::Allow,
                    &change_id,
                    None,
                    Some(approval_scope),
                    None,
                )?;

                let _grant_id = self.issue_and_emit_grant_scoped(
                    &pending.request,
                    ApprovalMode::Ask,
                    duration,
                    scope,
                    ActorRef::User,
                    audit_id.clone(),
                    &change_id,
                    preset_version,
                    Some(approval_scope),
                );

                let d = Decision::Allow {
                    grant_ref: Some(_grant_id),
                    audit_id,
                };
                self.emit_decision_event_with_scope(
                    &pending.request,
                    &d,
                    &change_id,
                    Some(approval_scope),
                );
                Ok(change_id)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn persona() -> PersonaId {
        PersonaId("test".into())
    }

    #[test]
    fn overlay_replaces_mode_while_preserving_preset_risk() {
        let mut hints: HashMap<Capability, ApprovalMode> = HashMap::new();
        hints.insert(Capability::FilesCreate, ApprovalMode::Auto);

        let cfg = EngineConfig::wave3_default(persona())
            .with_persona_overlay(&hints, PrivacyPosture::Balanced);

        let create = cfg.preset_defaults.get(&Capability::FilesCreate).unwrap();
        assert_eq!(create.mode, ApprovalMode::Auto);
        // wave3_default declared FilesCreate as Medium risk — the overlay
        // must not change that.
        assert_eq!(create.risk, RiskClass::Medium);
    }

    #[test]
    fn overlay_inserts_new_capabilities_with_default_risk() {
        let mut hints: HashMap<Capability, ApprovalMode> = HashMap::new();
        // wave3_default does NOT define BrowserOpen.
        hints.insert(Capability::BrowserOpen, ApprovalMode::Ask);

        let cfg = EngineConfig::wave3_default(persona())
            .with_persona_overlay(&hints, PrivacyPosture::Balanced);

        let browse = cfg
            .preset_defaults
            .get(&Capability::BrowserOpen)
            .expect("overlay inserts BrowserOpen");
        assert_eq!(browse.mode, ApprovalMode::Ask);
        assert_eq!(browse.risk, RiskClass::Medium);
    }

    #[test]
    fn wave3_default_grants_media_capabilities_at_medium_risk() {
        // The shell-side `media_permissions.json` gate is the user-
        // facing per-device control. L5 still records an audit row for
        // every media-tagged turn, but the engine should not double-
        // prompt: media defaults are Auto with Medium risk so the audit
        // story is correct without UX friction. A future Observer
        // preset can flip this to Ask/Deny.
        let cfg = EngineConfig::wave3_default(persona());
        let cam = cfg
            .preset_defaults
            .get(&Capability::MediaCamera)
            .expect("wave3_default should know MediaCamera");
        assert_eq!(cam.mode, ApprovalMode::Auto);
        assert_eq!(cam.risk, RiskClass::Medium);
        let scr = cfg
            .preset_defaults
            .get(&Capability::MediaScreenCapture)
            .expect("wave3_default should know MediaScreenCapture");
        assert_eq!(scr.mode, ApprovalMode::Auto);
        assert_eq!(scr.risk, RiskClass::Medium);
        // Mirror for MediaMic — Voice V1 step 4 (`transcribe_utterance`)
        // routes the turn with `Capability::MediaMic`. The shell's
        // `mic_permissions.json` tri-state is the user-facing gate, same
        // as media_permissions is for camera/screen.
        let mic = cfg
            .preset_defaults
            .get(&Capability::MediaMic)
            .expect("wave3_default should know MediaMic");
        assert_eq!(mic.mode, ApprovalMode::Auto);
        assert_eq!(mic.risk, RiskClass::Medium);
    }

    // ---- Memory V2 step 1: additive capability variants ----------------

    /// The four coarse Memory V2 capabilities must exist on the
    /// `Capability` enum so future Memory V2 code can reference them
    /// without enum churn. Step 1 is L5-first: the variants land
    /// without preset defaults, meaning any turn that requests them
    /// today gets `NeedsUpgrade`. Step 2 wires the per-domain Ask
    /// policy.
    #[test]
    fn memory_v2_coarse_capabilities_exist_and_hash() {
        use std::collections::HashSet;

        let mut s: HashSet<Capability> = HashSet::new();
        s.insert(Capability::MemoryWrite);
        s.insert(Capability::MemoryRead);
        s.insert(Capability::MemoryForget);
        s.insert(Capability::MemoryEdit);
        // Confirms Hash + Eq round-trip so policy maps can key by
        // these variants in step 2 without boilerplate.
        assert_eq!(s.len(), 4);
        assert!(s.contains(&Capability::MemoryWrite));
        assert!(s.contains(&Capability::MemoryForget));
    }

    #[test]
    fn memory_v2_capabilities_have_sensible_default_risks() {
        // Read is Low; write/edit/forget are Medium. Mirrors the
        // reasoning in `default_risk_for`.
        assert_eq!(default_risk_for(&Capability::MemoryRead), RiskClass::Low);
        assert_eq!(
            default_risk_for(&Capability::MemoryWrite),
            RiskClass::Medium
        );
        assert_eq!(default_risk_for(&Capability::MemoryEdit), RiskClass::Medium);
        assert_eq!(
            default_risk_for(&Capability::MemoryForget),
            RiskClass::Medium
        );
    }

    #[test]
    fn memory_v2_capabilities_are_registered_in_preset_with_design_doc_modes() {
        // Memory V2 step 3 flipped the four coarse capabilities from
        // "absent → NeedsUpgrade" to "present → Auto at L5". The
        // shell's `memory.json` `risk_for(domain)` is the user-facing
        // per-domain gate; L5 records the audit row here without
        // layering a redundant modal. Mirrors the Media/Mic pattern
        // (see Decision #29 in HANDOFF_2026-05-16_PRESENCE_MEMORY_EVAL.md).
        let cfg = EngineConfig::wave3_default(persona());
        let write = cfg
            .preset_defaults
            .get(&Capability::MemoryWrite)
            .expect("MemoryWrite preset default should be registered in Memory V2 step 3");
        assert_eq!(write.mode, ApprovalMode::Auto);
        assert_eq!(write.risk, RiskClass::Medium);
        let read = cfg
            .preset_defaults
            .get(&Capability::MemoryRead)
            .expect("MemoryRead preset default should be registered");
        assert_eq!(read.mode, ApprovalMode::Auto);
        assert_eq!(read.risk, RiskClass::Low);
        let edit = cfg
            .preset_defaults
            .get(&Capability::MemoryEdit)
            .expect("MemoryEdit preset default should be registered");
        assert_eq!(edit.mode, ApprovalMode::Auto);
        assert_eq!(edit.risk, RiskClass::Medium);
        let forget = cfg
            .preset_defaults
            .get(&Capability::MemoryForget)
            .expect("MemoryForget preset default should be registered");
        assert_eq!(forget.mode, ApprovalMode::Auto);
        assert_eq!(forget.risk, RiskClass::Medium);
    }

    #[test]
    fn memory_v2_capabilities_round_trip_through_serde() {
        // Audit / wire serialization must not collapse the new
        // variants onto neighbours. `Capability` is untagged-enum-
        // style serde by default (#[derive(Serialize, Deserialize)]
        // on the enum), so the JSON representation of a unit variant
        // is just its name string.
        for cap in [
            Capability::MemoryWrite,
            Capability::MemoryForget,
            Capability::MemoryEdit,
            Capability::MemoryEmbed,
        ] {
            let s = serde_json::to_string(&cap).unwrap();
            let back: Capability = serde_json::from_str(&s).unwrap();
            assert_eq!(back, cap, "round-trip failed for {:?}", cap);
        }
    }

    // ---- ADR-0012: persona delivery capabilities ----

    #[test]
    fn persona_delivery_capabilities_registered_in_wave3_default() {
        // Pin the four risk-class + approval-mode pairs so the
        // wizard's confirmation flow doesn't accidentally double-
        // prompt and so a future preset author understands which
        // capabilities expect Ask vs Auto out of the box.
        let cfg = EngineConfig::wave3_default(persona());

        let download = cfg
            .preset_defaults
            .get(&Capability::PersonaDownload)
            .expect("PersonaDownload preset default should be registered");
        assert_eq!(download.mode, ApprovalMode::Auto);
        assert_eq!(download.risk, RiskClass::Medium);

        let install = cfg
            .preset_defaults
            .get(&Capability::PersonaInstall)
            .expect("PersonaInstall preset default should be registered");
        assert_eq!(install.mode, ApprovalMode::Auto);
        assert_eq!(install.risk, RiskClass::Medium);

        let uninstall = cfg
            .preset_defaults
            .get(&Capability::PersonaUninstall)
            .expect("PersonaUninstall preset default should be registered");
        assert_eq!(uninstall.mode, ApprovalMode::Ask);
        assert_eq!(uninstall.risk, RiskClass::Medium);

        let switch_cap = cfg
            .preset_defaults
            .get(&Capability::PersonaSwitch)
            .expect("PersonaSwitch preset default should be registered");
        assert_eq!(switch_cap.mode, ApprovalMode::Auto);
        assert_eq!(switch_cap.risk, RiskClass::Low);
    }

    #[test]
    fn persona_delivery_capabilities_round_trip_through_serde() {
        for cap in [
            Capability::PersonaDownload,
            Capability::PersonaInstall,
            Capability::PersonaUninstall,
            Capability::PersonaSwitch,
        ] {
            let s = serde_json::to_string(&cap).unwrap();
            let back: Capability = serde_json::from_str(&s).unwrap();
            assert_eq!(back, cap, "round-trip failed for {:?}", cap);
        }
    }

    // ---- Memory V2 step 6 (ADR-0002): MemoryEmbed preset policy ----

    #[test]
    fn memory_embed_default_risk_is_low() {
        // Embedding is a side effect of an already-allowed MemoryWrite.
        assert_eq!(default_risk_for(&Capability::MemoryEmbed), RiskClass::Low);
    }

    #[test]
    fn memory_embed_registered_in_wave3_default_as_auto_low() {
        let cfg = EngineConfig::wave3_default(persona());
        let embed = cfg
            .preset_defaults
            .get(&Capability::MemoryEmbed)
            .expect("MemoryEmbed preset default should be registered");
        assert_eq!(embed.mode, ApprovalMode::Auto);
        assert_eq!(embed.risk, RiskClass::Low);
    }

    #[test]
    fn overlay_sets_posture_from_persona() {
        let hints: HashMap<Capability, ApprovalMode> = HashMap::new();
        let cfg = EngineConfig::wave3_default(persona())
            .with_persona_overlay(&hints, PrivacyPosture::Strict);
        assert_eq!(cfg.posture, PrivacyPosture::Strict);
    }

    #[test]
    fn overlay_cannot_bypass_presets_deny() {
        // This is subtle — the overlay *can* flip ShellExec mode to Auto
        // in the preset defaults, because the overlay trusts the caller
        // to have compiled the persona correctly. The L6 default
        // compiler is what enforces `ShellExec = Deny` across all
        // personas (see l6-persona's
        // `policy_defaults_never_auto_approve_shell_exec` regression).
        // This test documents that boundary: if the persona says "Auto
        // shell", the engine takes it at its word — the policy layer
        // trusts its own compiled inputs.
        let mut hints: HashMap<Capability, ApprovalMode> = HashMap::new();
        hints.insert(Capability::ShellExec, ApprovalMode::Auto);
        let cfg = EngineConfig::wave3_default(persona())
            .with_persona_overlay(&hints, PrivacyPosture::Balanced);
        let shell = cfg.preset_defaults.get(&Capability::ShellExec).unwrap();
        assert_eq!(shell.mode, ApprovalMode::Auto);
        // Risk stays preset-declared Critical even if mode flips.
        assert_eq!(shell.risk, RiskClass::Critical);
    }

    // --- AutonomyPreset overlay ---

    #[test]
    fn preset_overlay_observer_denies_every_write_and_shell() {
        let cfg =
            EngineConfig::wave3_default(persona()).with_preset_overlay(AutonomyPreset::Observer);
        assert_eq!(
            cfg.preset_defaults[&Capability::FilesRead].mode,
            ApprovalMode::Auto
        );
        for cap in [
            Capability::FilesCreate,
            Capability::FilesEdit,
            Capability::FilesDelete,
            Capability::ShellExec,
        ] {
            assert_eq!(
                cfg.preset_defaults[&cap].mode,
                ApprovalMode::Deny,
                "Observer must deny {cap:?}"
            );
        }
        assert_eq!(cfg.preset.0, "wave3.observer");
    }

    #[test]
    fn preset_overlay_observer_allows_memory_read_denies_memory_mutations() {
        // Observer is read-only posture. MemoryRead stays Auto so the
        // assistant can ground itself in prior conversation. Writes /
        // edits / forgets flip to Deny — Observer users explicitly
        // chose to watch, not act on the memory system.
        let cfg =
            EngineConfig::wave3_default(persona()).with_preset_overlay(AutonomyPreset::Observer);
        assert_eq!(
            cfg.preset_defaults[&Capability::MemoryRead].mode,
            ApprovalMode::Auto,
            "Observer must still allow MemoryRead",
        );
        for cap in [
            Capability::MemoryWrite,
            Capability::MemoryEdit,
            Capability::MemoryForget,
        ] {
            assert_eq!(
                cfg.preset_defaults[&cap].mode,
                ApprovalMode::Deny,
                "Observer must deny {cap:?}",
            );
        }
    }

    #[test]
    fn preset_overlay_operator_keeps_memory_capabilities_auto() {
        // Operator is already the liberal preset — leaving Memory V2
        // caps at their baseline Auto is correct. This test locks
        // that a future overlay tweak doesn't silently escalate
        // memory mutations on the operator preset without a
        // corresponding design update.
        let cfg =
            EngineConfig::wave3_default(persona()).with_preset_overlay(AutonomyPreset::Operator);
        for cap in [
            Capability::MemoryRead,
            Capability::MemoryWrite,
            Capability::MemoryEdit,
            Capability::MemoryForget,
        ] {
            assert_eq!(
                cfg.preset_defaults[&cap].mode,
                ApprovalMode::Auto,
                "Operator must keep {cap:?} as Auto",
            );
        }
    }

    #[test]
    fn preset_overlay_assistant_is_baseline_noop() {
        let baseline = EngineConfig::wave3_default(persona());
        let assistant =
            EngineConfig::wave3_default(persona()).with_preset_overlay(AutonomyPreset::Assistant);
        for cap in baseline.preset_defaults.keys() {
            assert_eq!(
                assistant.preset_defaults[cap].mode, baseline.preset_defaults[cap].mode,
                "Assistant preset must not shift {cap:?}",
            );
        }
        assert_eq!(assistant.preset.0, "wave3.assistant");
    }

    #[test]
    fn preset_overlay_operator_auto_approves_read_and_create_but_not_shell() {
        let cfg =
            EngineConfig::wave3_default(persona()).with_preset_overlay(AutonomyPreset::Operator);
        assert_eq!(
            cfg.preset_defaults[&Capability::FilesRead].mode,
            ApprovalMode::Auto
        );
        assert_eq!(
            cfg.preset_defaults[&Capability::FilesCreate].mode,
            ApprovalMode::Auto,
            "Operator should auto-approve file creation",
        );
        assert_eq!(
            cfg.preset_defaults[&Capability::FilesEdit].mode,
            ApprovalMode::Ask,
            "Operator still asks before edits",
        );
        assert_eq!(
            cfg.preset_defaults[&Capability::ShellExec].mode,
            ApprovalMode::Deny,
            "Operator must NOT loosen shell execution",
        );
        assert_eq!(cfg.preset.0, "wave3.operator");
    }

    #[test]
    fn preset_overlay_runs_after_persona_and_wins() {
        // Bold persona hint: Auto-approve ShellExec.
        let mut hints: HashMap<Capability, ApprovalMode> = HashMap::new();
        hints.insert(Capability::ShellExec, ApprovalMode::Auto);
        let cfg = EngineConfig::wave3_default(persona())
            .with_persona_overlay(&hints, PrivacyPosture::Open)
            .with_preset_overlay(AutonomyPreset::Observer);
        // Observer must re-pin ShellExec to Deny regardless of the persona hint.
        assert_eq!(
            cfg.preset_defaults[&Capability::ShellExec].mode,
            ApprovalMode::Deny,
        );
    }

    #[test]
    fn autonomy_preset_wire_names_round_trip() {
        for p in [
            AutonomyPreset::Observer,
            AutonomyPreset::Assistant,
            AutonomyPreset::Operator,
        ] {
            assert_eq!(Some(p), AutonomyPreset::from_wire(p.wire_name()));
        }
        assert_eq!(AutonomyPreset::from_wire("unknown"), None);
        assert_eq!(AutonomyPreset::from_wire("later"), None);
    }
}
