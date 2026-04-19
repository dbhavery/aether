---
status: draft
date: 2026-04-18
layer: L5 (policy / authorization engine)
mode: implementation prep — interface pack
primary_source: plans/L5_policy_engine_system_design.md
secondary_sources:
  - plans/L1_L4_L5_L7_integration_notes.md
  - plans/L1_interaction_timing_system_design.md §7.1
  - plans/L4_model_router_system_design.md §6
  - plans/L7_trust_ux_onboarding_system_design.md §3, §10
  - plans/X3_tauri_architecture.md §2
target_packages:
  - file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/          (Rust core)
  - file:///C:/Users/dbhav/Projects/aether/packages/l5-policy-ts/       (TS bindings — types only)
---

# L5 — Policy / Authorization Engine — Interface Pack

> This is an implementation-oriented distillation of `plans/L5_policy_engine_system_design.md` (1076 lines, authoritative). An implementer should be able to stand up the Rust trait crate and the TS bindings crate from this document alone. Where the source flags an open question, this pack re-flags it (does not silently resolve).
>
> Canonical planning root: file:///C:/Users/dbhav/Projects/aether-planning/
> Primary source: file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md

---

## 1. Purpose

L5 is the **single, non-bypassable authorization gate** for every autonomous action Aether takes. Nothing executes — no tool call, no memory write, no remote model route, no cost-bearing API hit — without L5 returning `Decision::Allow`. It owns the capability taxonomy, the five-layer evaluator, the grant ledger, the append-only hash-chained audit log, the BYOK hard-cap enforcement counter, and the privacy-posture gate.

Consumer layers (L1 reflex/turn loop, L2 memory, L4 model router, L7 trust UX) stub against the contracts frozen here and in the system-design source. The purpose of this pack is to give those stubs stable inbound/outbound shapes, typed error vocabulary, and a minimal `PolicyEngine` trait surface that CI can lint against (no executor may call a side-effectful API without holding an `Arc<dyn PolicyEngine>` handle and presenting a `Decision::Allow`).

---

## 2. Primary responsibilities

- Evaluate every `ActionRequest` synchronously through the 5-layer evaluator (pre-gates → feature → action → resource → mode → duration) and return a typed `Decision`.
- Maintain the grant ledger (active, expired, revoked) and drive TTL expiry.
- Append-only, hash-chained, HMAC-integrity audit log — every decision recorded before `Allow` returns.
- Emit the L5 event family on the Rust-internal event bus (`action_request`, `policy_decision`, `approval_pending`, `grant_issued`, `grant_revoked`, `audit_record`, `emergency_revoke_all`, `cost_threshold_hit`, `policy_posture_changed`).
- Expose the Tauri IPC command surface consumed by L7.
- Enforce BYOK cost caps per provider/window in Stage 0 (pre-evaluator).
- Enforce the privacy-posture gate (private-tagged context + remote route → deny unless explicit waiver).
- Drive degraded modes (`SafeMode`, `AuditBroken`, `MinimumTrust`) that deny-all or deny-almost-all rather than silent-allow.
- Service emergency revoke-all within the 500 ms budget.
- Keep the audit log and grant ledger in the shared SQLite DB (same file as the storage package) and key the audit HMAC with a per-install key from the OS keyring.

---

## 3. Inbound interfaces

Every inbound interface below is either a Rust-internal event (on the bus) or a Tauri IPC command. Producers are named by layer; "required fields" are the minimum an implementation must enforce on receipt; "validation rules" are what L5 verifies before accepting; "failure modes" are the typed responses when validation fails.

### 3.1 Summary table

| Interface | Producer | Transport | Sync/async | Failure mode on reject |
|---|---|---|---|---|
| `ActionRequest` | L1 (turn loop), L2 (memory write/read gate), L4 (router pre-dispatch), Media engines | internal bus / `policy.evaluate` command | **sync** (<20 ms typical for auto; returns ticket for Ask) | `PolicyIpcError::Invalid` / `PolicyEngineError::Internal` |
| `ApprovalResponse` | L7 webview → Rust via `policy.respond_approval` command | Tauri IPC command | sync (blocking with optimistic UI) | `PolicyIpcError::NotFound` / `Conflict` |
| `PersonaCompiledPolicyDefaults` | L6 persona compiler | internal bus (`persona_swap_commit` event + snapshot) | async (consumed on swap commit) | L5 falls back to `MinimumTrustPersona` (§11.4 source) |
| `CostEvent` | L4 model router | internal bus | async (fire-and-forget; counters update eventually) | dropped after `cost_event_malformed` audit row |
| `MemoryProvenanceUpdate` | L2 memory kernel | internal bus (attached to memory-hit events; also surfaced on `ActionRequest.provenance_tags`) | async (attached to each action request) | missing tags → treated as `untrusted_input` conservative default |

### 3.2 `ActionRequest` — from L1 / L2 / L4 / Media

- **Producer:** any action-initiating engine. L1 for tool plans. L2 for gated memory reads/writes. L4 for remote-route pre-dispatch. Media engines for mic/camera/screen-capture.
- **Required fields:**
  - `request_id: RequestId` — ULID, process-unique
  - `turn_id: TurnId` — correlates with L1 turn state machine
  - `capability: Capability` — typed dot-path enum, NEVER stringly
  - `resource: ResourceScope` — typed variant matching capability family
  - `actor_persona: PersonaId` — persona asking
  - `emitted_at: MonotonicTimestamp`
- **Optional fields:**
  - `task_id: Option<TaskId>`
  - `provenance_tags: Vec<ProvenanceTag>` (L2 attaches; missing = treat as tainted)
  - `intended_route: Option<RouteHint>` (L4 attaches; `LocalOnly | LocalPreferred | RemoteEscalation { provider }`)
  - `risk_class_hint: Option<RiskClass>` (evaluator re-checks regardless)
  - `active_grants: Snapshot<GrantLedger>` (evaluator takes its own snapshot on entry; hint only)
- **Validation rules:**
  1. `request_id` unique within process lifetime (dedup on replay).
  2. `capability` is a known enum variant; parameterized variants (`IntegrationUse(id)`, etc.) must reference a registered id.
  3. `resource.kind` matches the capability family (e.g. `FilesRead` requires `ResourceScope::Path`).
  4. `actor_persona` is a live persona (post-compile).
  5. `emitted_at` monotonic-ordered relative to last accepted request on this turn; stale requests are rejected.
- **Failure modes:**
  - Unknown capability → `PolicyIpcError::Invalid("unknown_capability")`
  - Scope/capability mismatch → `PolicyIpcError::Invalid("resource_scope_kind_mismatch")`
  - Duplicate `request_id` → logged-drop, no evaluation
  - Persona unresolved → evaluator proceeds with `MinimumTrustPersona` + `DenyReason::FeatureDisabled`

### 3.3 `ApprovalResponse` — from L7

- **Producer:** L7 webview, mediated by the `policy.respond_approval` Tauri command. Never crosses the bridge as a raw event.
- **Required fields:**
  - `ticket_id: ApprovalTicketId`
  - `user_choice: UserChoice` (enum: `Allow | AllowScope(ResourceScope) | AllowTask | AllowSession | Deny`)
  - `responded_at: MonotonicTimestamp`
- **Optional fields:**
  - `scope_override: Option<ResourceScope>` (for `AllowScope`)
  - `duration_override: Option<GrantDuration>` (when L7 offers a TTL picker)
  - `reauth_token: Option<CommandToken>` (required for High/Critical confirmations)
- **Validation rules:**
  1. `ticket_id` corresponds to a live, unconsumed `approval_pending`.
  2. Ticket not already revoked (grant revoked mid-ask → rejected with `Conflict`).
  3. For High/Critical caps, `reauth_token` is present and unexpired.
  4. `user_choice` variant is compatible with the capability's permitted duration shapes (e.g. `AllowSession` invalid for once-only caps).
- **Failure modes:**
  - Unknown ticket → `PolicyIpcError::NotFound`
  - Double-response → `PolicyIpcError::Conflict("already_responded")`
  - Grant revoked mid-ask → `PolicyIpcError::Conflict("ticket_stale_grant_revoked")` (no auto-re-ask; prevents prompt loops)
  - Missing re-auth → `PolicyIpcError::RequiresReauth`

### 3.4 `PersonaCompiledPolicyDefaults` — from L6

- **Producer:** L6 persona compiler, delivered as a field of the `CompiledPersona` payload inside a `persona_swap_commit` bus event. L5 snapshots the policy-defaults section on commit.
- **Required fields:**
  - `persona_id: PersonaId`
  - `persona_version: u32`
  - `privacy_posture: PrivacyPosture` (`Strict | Balanced | Open`)
  - `per_capability_defaults: HashMap<Capability, ApprovalMode>` (persona overlay; layer 3 in §6.3 precedence)
  - `privileged_profile: bool` (Isabelle overlay flag; §14.10 source)
- **Optional fields:**
  - `recommended_preset: Option<PresetId>`
  - `strict_provenance_tags: BitSet<ProvenanceTagKind>` (tags this persona treats as tainted regardless of risk class)
- **Validation rules:**
  1. `persona_id` matches the persona that initiated the swap (no cross-persona injection).
  2. Every `Capability` key is a known enum variant.
  3. `per_capability_defaults` must not violate `block.auto_approve_high_critical` (invariant check; reject at compile time).
- **Failure modes:**
  - Invalid capability key → L5 rejects swap, emits `persona_swap_rejected`, falls back to `MinimumTrustPersona` (§11.4 source).
  - Invariant violation (auto on High/Critical) → swap rejected, audit row `persona_compile_invariant_violation`.

### 3.5 `CostEvent` — from L4

- **Producer:** L4 model router, emitted on every tool/model call completion (success or failure with partial token cost).
- **Required fields:**
  - `provider: ProviderId`
  - `tokens_in: u32`
  - `tokens_out: u32`
  - `dollars: Cents`
  - `request_id: RequestId` (correlates with the `ActionRequest` that authorized the call)
  - `timestamp_mono: MonotonicTimestamp`
- **Optional fields:**
  - `persona_id: Option<PersonaId>` (for per-persona windows)
  - `session_id: Option<SessionId>`
  - `failed: bool` (partial cost still counts)
- **Validation rules:**
  1. `provider` is a known provider (unknown → dropped after `unknown_provider_cost_event` audit row).
  2. `dollars` ≥ 0; `tokens_*` ≥ 0.
  3. `request_id` need not resolve to an active grant (router may emit post-revoke costs).
- **Failure modes:**
  - Malformed event → logged to audit with `cost_event_malformed` reason; counters untouched.
  - Storage write failure on counter update → counter state held in-memory with a `cost_counter_persist_deferred` audit row; persistence retried on next tick.

### 3.6 `MemoryProvenanceUpdate` — from L2

- **Producer:** L2 memory kernel, attached to each memory hit that flows into a turn context. L5 consumes the tags on the `ActionRequest.provenance_tags` field. A separate bus event carries bulk updates when L2 recomputes provenance (e.g. after ingest).
- **Required fields:**
  - `memory_id: MemoryId`
  - `provenance_tags: Vec<ProvenanceTag>` (`public | session | durable | private | untrusted_input | scraped_content | extracted_preference | ...`)
  - `computed_at: MonotonicTimestamp`
- **Optional fields:**
  - `confidence: f32` (0..1; low-confidence untrusted tags may downgrade cap risk)
  - `source_ref: Option<SourceRef>` (URL / file / conversation turn)
- **Validation rules:**
  1. `memory_id` resolves in L2.
  2. Tags are known enum variants.
- **Failure modes:**
  - Unknown tag → treated as `untrusted_input` (conservative default).
  - Missing tags on an `ActionRequest` → treated as `untrusted_input`.

---

## 4. Outbound interfaces

All outbound events live on the Rust-internal event bus; a filtered subset is projected to the webview via the Tauri bridge (`X3 §3.2`). Every event carries `source_layer = SourceLayer::L5`, a monotonic `seq`, and a `change_id` (write-class command correlation).

### 4.1 Summary table

| Event | Emitted by L5 when | Primary subscribers | Projected to webview? |
|---|---|---|---|
| `PolicyDecision` | Every `evaluate` returns | L1, L2, L4, L7 | yes (summary) |
| `ApprovalPending` | Decision = `Ask` | L7 (render), L1 (stall-ack gate) | yes |
| `GrantIssued` | Decision = `Allow` with new or extended grant | L1, L4, L7 | yes |
| `GrantRevoked` | User/persona-swap/TTL/emergency revoke | L1, L4, L7 | yes |
| `AuditRecord` | Every decision (mandatory, sync-committed) | L7 (trust center), storage | yes (summary; full via `policy.stream_audit`) |
| `EmergencyRevokeAll` | Big-red-button, persona swap cascade, security trip | L1, L2, L4, L7 | yes |
| `CostThresholdHit` | Provider counter crosses configured threshold | L4 (deny-flag), L7 (banner) | yes |
| `PolicyPostureChanged` | Preset switch, persona swap, degraded-mode transition | L1, L4, L7 | yes |

### 4.2 `PolicyDecision`

- **Required fields:** `request_id`, `decision: Decision`, `audit_id: AuditId`, `change_id`, `seq`.
- **Optional fields:** `reason: Option<StaticReason>`, `effective_mode: Option<ApprovalMode>`, `precedence_source: Option<PrecedenceSource>`.
- **Validation rules (emitter-side invariants):** Must follow its `ActionRequest` in strict order per turn. Idempotent on `audit_id` (replay-safe).
- **Failure modes:** If audit write fails, no `PolicyDecision{Allow}` may be emitted — evaluator returns `Deny { AuditWriteFailed }` instead.

### 4.3 `ApprovalPending`

- **Required:** `ticket_id`, `request_id`, `capability`, `resource`, `risk_class`, `explanation: StaticCopyId`, `change_id`, `seq`.
- **Optional:** `deadline_hint: Option<MonotonicTimestamp>`, `suggested_duration: Option<GrantDuration>`, `bundle_hint: Option<BundleId>` (for plan-preview P2).
- **Validation:** Must follow `PolicyDecision{Ask}` with matching `request_id`.
- **Failure modes:** If L7 never responds within the deadline, L5 emits `ApprovalExpired` (reuses `GrantRevoked` with `reason = 'approval_timeout'`).

### 4.4 `GrantIssued`

- **Required:** `grant_id`, `capability`, `resource_scope`, `approval_mode`, `duration`, `issued_at`, `issued_by`, `audit_ref`, `change_id`, `seq`.
- **Optional:** `expires_at: Option<MonotonicTimestamp>`, `task_id: Option<TaskId>`, `preset_version_issued_under: u32`.
- **Validation:** Follows `PolicyDecision{Allow}` with matching audit root. `grant_id` unique.
- **Failure modes:** Emission failure → the `Allow` is rolled back; evaluator returns `Deny { Internal }` and writes a corrective audit record.

### 4.5 `GrantRevoked`

- **Required:** `grant_id`, `revoked_at`, `revoked_reason: RevokeReason`, `audit_ref`, `change_id`, `seq`.
- **Optional:** `cascade_batch_id: Option<BatchId>` (persona swap + emergency revoke group multiple into one batch).
- **Validation:** A grant may be revoked only once; subsequent attempts are logged no-ops.
- **Failure modes:** Same as `GrantIssued`.

### 4.6 `AuditRecord`

- **Required:** `audit_id`, `timestamp_monotonic`, `timestamp_wall`, `actor: ActorRef`, `capability`, `resource`, `decision: DecisionKind`, `change_id`, `prev_hash`, `record_hmac`, `key_id`, `seq`.
- **Optional:** `reason: Option<StaticReasonId>`, `stage_trace: Vec<StageTrace>`, `privileged_profile: bool`.
- **Validation:** Chain continuity — `prev_hash` equals SHA-256 of the previous record's canonical serialization. HMAC validates under `key_id`. SQLite triggers reject `UPDATE`/`DELETE`.
- **Failure modes:** Any chain break → `DegradedMode::AuditBroken` → deny-all.

### 4.7 `EmergencyRevokeAll`

- **Required:** `initiated_by: Actor`, `scope: EmergencyScope` (`All | Category(CapGroup) | Persona(PersonaId)`), `initiated_at`, `audit_ref`, `change_id`, `seq`.
- **Optional:** `completed_at: Option<MonotonicTimestamp>`, `revoked_count: Option<u32>`.
- **Validation:** Only one in-flight emergency at a time; concurrent calls coalesce. Must complete ≤ 500 ms (acceptance criterion).
- **Failure modes:** Timeout → `DegradedMode::SafeMode` engaged; banner surfaces.

### 4.8 `CostThresholdHit`

- **Required:** `provider`, `threshold: CostThreshold` (`Daily | Monthly | PerProvider | PerPersona`), `dollars_hit: Cents`, `counter_window: TimeWindow`, `audit_ref`, `change_id`, `seq`.
- **Optional:** `warn_level: Option<WarnLevel>` (emitted at `warn_at_pct`).
- **Validation:** Once per threshold-crossing window; re-arm resets the emitter.
- **Failure modes:** Counter persist failure → in-memory deny-flag still flips; persistence retried.

### 4.9 `PolicyPostureChanged`

- **Required:** `prior_posture: PolicyPostureSummary`, `new_posture: PolicyPostureSummary`, `trigger: PostureTrigger` (`PresetSwitch | PersonaSwap | DegradedEntry | DegradedExit | CapBlocklistUpdate`), `change_id`, `seq`, `audit_ref`.
- **Optional:** `stripped_grants: Vec<GrantId>` (on preset narrowing), `added_capabilities: Vec<Capability>`.
- **Validation:** `PolicyPostureSummary` is a hashable snapshot — subscribers use the hash to detect drift on reconnect.
- **Failure modes:** Emission is required on every posture change; failure engages `SafeMode`.

---

## 5. Synchronous vs asynchronous boundaries

| Boundary | Synchronicity | Budget / rule |
|---|---|---|
| `policy.evaluate` (auto decision) | **sync** | p95 < 10 ms; hard ceiling 20 ms typical (source §13.4) |
| `policy.evaluate` (Ask decision) | **sync** return with ticket | ticket issued ≤ 20 ms; user response arrives later via async `approval_response` |
| Audit write for Allow | **sync-committed before `Allow` returns** | non-negotiable zero-bypass invariant (source §11.1) |
| Audit write for Deny/Ask/Draft | **sync-committed before decision event emitted** | same invariant; deny-all if write fails |
| Approval flow end-to-end (`Ask` → user → `Allow`) | **async** | bounded by deadline_hint; no auto-re-ask on timeout |
| `CostEvent` ingest + counter update | **async** | fire-and-forget; counters eventually consistent with bus order |
| `MemoryProvenanceUpdate` bulk | **async** | attached to memory hits; missing tags → conservative default |
| Emergency revoke | **sync** | ≤ 500 ms with ≥10 000 active grants |
| Preset switch | **sync** | ≤ 100 ms for stripped-grant revocation cascade |
| Event projection to webview | async through bridge | at-least-once; subscribers idempotent on `audit_id` / `grant_id` / `request_id` |

**Key rule:** L5 is a **sync gate** for deciding and a **sync committer** for recording. Everything downstream of "Allow returned" is async. No `Allow` ever propagates without the matching audit record already committed to SQLite.

---

## 6. Typed contract suggestions

### 6.1 Rust trait (`packages/l5-policy/`)

```rust
pub trait PolicyEngine: Send + Sync {
    /// The only way for a Rust engine to request permission.
    /// Sync; returns before any side-effect is performed by caller.
    fn evaluate(&self, req: ActionRequest) -> Result<Decision, PolicyEngineError>;

    /// Subscribe to a category of events on the internal bus.
    /// At-least-once delivery; idempotent on `audit_id` / `grant_id` / `request_id`.
    fn subscribe(&self, filter: EventFilter) -> EventStream<L5Event>;

    /// Emergency revoke — usually invoked via Tauri command, occasionally from Rust.
    fn emergency_revoke(&self, scope: EmergencyScope)
        -> Result<EmergencyReceipt, PolicyEngineError>;

    /// Read-only snapshot of current grants.
    fn snapshot_grants(&self, filter: GrantFilter) -> Vec<Grant>;

    /// Enumerate capabilities — used by L4 to know what it may attempt.
    fn capabilities(&self, filter: CapabilityFilter) -> Vec<CapabilityInfo>;

    /// Ingest a user response to a pending approval ticket.
    /// Mirrors `policy.respond_approval` Tauri command for in-Rust test harnesses.
    fn respond_approval(&self, response: ApprovalResponse)
        -> Result<ChangeId, PolicyEngineError>;
}

#[derive(thiserror::Error, Debug)]
pub enum PolicyEngineError {
    #[error("degraded mode: {0:?}")]
    Degraded(DegradedMode),
    #[error("bus closed")]
    BusClosed,
    #[error("invalid request: {0}")]
    Invalid(&'static str),
    #[error("ticket not found")]
    TicketNotFound,
    #[error("ticket conflict: {0}")]
    TicketConflict(&'static str),
    #[error("requires re-auth")]
    RequiresReauth,
    #[error("audit blocked")]
    AuditBlocked,
    #[error("internal: {0}")]
    Internal(String),
}

pub enum Decision {
    Allow   { grant_ref: Option<GrantId>, audit_id: AuditId },
    Ask     { ticket: ApprovalTicket, audit_id: AuditId },
    DraftOnly { audit_id: AuditId, reason: StaticReason },
    Deny    { reason: DenyReason, audit_id: AuditId },
    NeedsUpgrade { capability_path: Capability, audit_id: AuditId,
                   suggested_preset: Option<PresetId> },
    // FLAGGED — see §14.8: AllowDraft { side_effects_inhibited: BitSet<SideEffectKind>, audit_id }
    //           pending lock. Not present in source §3.1 Decision enum. Do not implement
    //           until resolved.
}

pub enum DenyReason {
    HardcodedBlock(HardcodedBlockId),
    FeatureDisabled,
    ActionOutOfScope,
    ResourceOutOfScope,
    ModeDeny,
    GrantExpired,
    GrantRevoked,
    ProvenanceTaint(TaintKind),
    PrivacyPostureViolation,
    CostCapHit(ProviderId),
    TierDowngradeStripped,
    LedgerCorrupt,
    AuditWriteFailed,
    // FLAGGED — see §14.8: NeedsUpgrade may collapse here as an alternate encoding
    //           (integration-notes Q2). Decision-layer vs Deny-reason is unresolved.
}

pub enum ApprovalMode { Auto, TaskScoped, Ask, DraftOnly, Deny }

pub enum GrantDuration {
    Once,
    TaskScoped(TaskId),
    Session,
    Persistent { ttl: Option<Duration> },
}

pub enum Capability {
    // Files
    FilesRead, FilesCreate, FilesEdit, FilesRenameMove, FilesDelete, FilesBulkOp,
    // Browser
    BrowserOpen, BrowserReadPage, BrowserExtractData, BrowserFillForm,
    BrowserUpload, BrowserDownload, BrowserSubmit, BrowserLoginReuse,
    // Email
    EmailReadMetadata, EmailReadBody, EmailDraft, EmailEditDraft,
    EmailSend, EmailAttachmentAccess,
    // System & tools
    ClipboardRead, ClipboardWrite, ShellExec, PackageInstall,
    NotificationRead, AutomationTrigger,
    // Memory
    MemoryRead, MemoryWriteSession, MemoryWriteDurable, MemoryWriteExtractedPref,
    MemoryUseInFutureTask, MemoryExport, MemoryDelete,
    // Media
    MediaMic, MediaCamera, MediaScreenCapture,
    // Integrations
    IntegrationUse(IntegrationId),
    IntegrationExternalApi(ApiId),
    IntegrationTriggerAutomation(AutomationId),
    // Router / cost
    RouterEscalateRemote, RouterOverrideTier, RouterAllowRemoteWithPrivate,
    // FLAGGED — see §14.8: AuditExport is proposed in source §14.6 but not yet
    //           added to the canonical enum. Add only after §14.6 resolves.
}

pub struct EventFilter {
    pub kinds:         BitSet<L5EventKind>,
    pub actors:        Option<Vec<ActorRef>>,
    pub capabilities:  Option<Vec<Capability>>,
    pub since_seq:     Option<Seq>,
}

pub enum L5Event {
    ActionRequest(ActionRequestEvent),
    PolicyDecision(PolicyDecisionEvent),
    ApprovalPending(ApprovalPendingEvent),
    GrantIssued(GrantIssuedEvent),
    GrantRevoked(GrantRevokedEvent),
    AuditRecord(AuditRecordEvent),
    EmergencyRevokeAll(EmergencyRevokeAllEvent),
    CostThresholdHit(CostThresholdHitEvent),
    PolicyPostureChanged(PolicyPostureChangedEvent),
}
```

### 6.2 TS binding sketch (`packages/l5-policy-ts/`)

Types only — no logic. Generated via `ts-rs` or `specta` (locked at X3 G1).

```ts
// Re-exported types; structure mirrors the Rust enums above.
export type Capability =
  | { kind: "FilesRead" } | { kind: "FilesCreate" } | { kind: "FilesEdit" }
  | { kind: "FilesRenameMove" } | { kind: "FilesDelete" } | { kind: "FilesBulkOp" }
  | { kind: "BrowserOpen" } | { kind: "BrowserReadPage" } | { kind: "BrowserExtractData" }
  | { kind: "BrowserFillForm" } | { kind: "BrowserUpload" } | { kind: "BrowserDownload" }
  | { kind: "BrowserSubmit" } | { kind: "BrowserLoginReuse" }
  | { kind: "EmailReadMetadata" } | { kind: "EmailReadBody" } | { kind: "EmailDraft" }
  | { kind: "EmailEditDraft" } | { kind: "EmailSend" } | { kind: "EmailAttachmentAccess" }
  | { kind: "ClipboardRead" } | { kind: "ClipboardWrite" } | { kind: "ShellExec" }
  | { kind: "PackageInstall" } | { kind: "NotificationRead" } | { kind: "AutomationTrigger" }
  | { kind: "MemoryRead" } | { kind: "MemoryWriteSession" } | { kind: "MemoryWriteDurable" }
  | { kind: "MemoryWriteExtractedPref" } | { kind: "MemoryUseInFutureTask" }
  | { kind: "MemoryExport" } | { kind: "MemoryDelete" }
  | { kind: "MediaMic" } | { kind: "MediaCamera" } | { kind: "MediaScreenCapture" }
  | { kind: "IntegrationUse"; id: string }
  | { kind: "IntegrationExternalApi"; id: string }
  | { kind: "IntegrationTriggerAutomation"; id: string }
  | { kind: "RouterEscalateRemote" } | { kind: "RouterOverrideTier" }
  | { kind: "RouterAllowRemoteWithPrivate" };

export type Decision =
  | { tag: "Allow"; grant_ref?: string; audit_id: string }
  | { tag: "Ask"; ticket: ApprovalTicket; audit_id: string }
  | { tag: "DraftOnly"; audit_id: string; reason: StaticReasonId }
  | { tag: "Deny"; reason: DenyReason; audit_id: string }
  | { tag: "NeedsUpgrade"; capability_path: Capability; audit_id: string;
      suggested_preset?: PresetId };

export type ApprovalMode = "Auto" | "TaskScoped" | "Ask" | "DraftOnly" | "Deny";
export type GrantDuration =
  | { tag: "Once" }
  | { tag: "TaskScoped"; task_id: string }
  | { tag: "Session" }
  | { tag: "Persistent"; ttl_ms?: number };

export type PolicyIpcError =
  | { code: "Degraded"; mode: DegradedMode }
  | { code: "RequiresReauth" }
  | { code: "NotFound"; msg: string }
  | { code: "Invalid"; msg: string }
  | { code: "Conflict"; msg: string }
  | { code: "AuditBlocked" }
  | { code: "Internal"; msg: string };

export type DegradedMode = "SafeMode" | "AuditBroken" | "LedgerCorrupt" | "MinimumTrust";

// Tauri invoke surface — mirrors §5 command catalog of source doc.
export interface PolicyCommands {
  "policy.evaluate":            (req: ActionRequest) => Promise<Decision>;
  "policy.request_approval":    (req: { request_id: string }) => Promise<ApprovalTicket>;
  "policy.respond_approval":    (req: ApprovalResponse) => Promise<void>;
  "policy.set_preset":          (req: { preset: PresetId }) => Promise<PresetSwitchReceipt>;
  "policy.get_preset":          () => Promise<CurrentPreset>;
  "policy.list_grants":         (req: { filter?: GrantFilter }) => Promise<Grant[]>;
  "policy.revoke":              (req: { target: RevokeTarget }) => Promise<RevokeReceipt>;
  "policy.list_capabilities":   (req: { filter?: CapabilityFilter }) => Promise<CapabilityInfo[]>;
  "policy.explain_decision":    (req: { audit_id: string }) => Promise<Explanation>;
  "policy.preview_plan":        (req: { plan: ActionRequest[] }) => Promise<PlanPreview>;
  "policy.emergency_revoke_all":(req: { scope: EmergencyScope }) => Promise<EmergencyReceipt>;
  "policy.get_audit_summary":   (req: { filter: AuditFilter }) => Promise<AuditSummary[]>;
  "policy.stream_audit":        (req: { filter: AuditFilter; cursor?: string })
                                  => AsyncIterable<AuditRecordEvent>;
  // FLAGGED — see §14.8: "policy.export_audit" and "policy.set_cost_cap" /
  //           "policy.reset_cost_counter" referenced by integration notes (Q5)
  //           and by source §9.4 respectively, but NOT present in source §5.2
  //           command catalog. Do not stub in TS bindings until reconciled.
}
```

### 6.3 Capability enum reference

Source of truth: `plans/L5_policy_engine_system_design.md` §2.1 and §2.2 (full defaults table, 7 capability groups, 45+ sub-capabilities). Pre-evaluator hardcoded blocks in §2.3. Implementers MUST treat the source enum as canonical; this pack surfaces the shape but not the defaults table.

---

## 7. Error vocabulary

Two enums cover every failure L5 emits across the IPC and Rust trait surfaces. Standardize these for every consumer stub and every test fixture.

### 7.1 `PolicyIpcError` — crosses the Tauri bridge

| Variant | When it fires | Recovery expectation |
|---|---|---|
| `Degraded(DegradedMode)` | Engine is in `SafeMode` / `AuditBroken` / `LedgerCorrupt` / `MinimumTrust` | L7 renders banner; user follows recovery action |
| `RequiresReauth` | Command capability-gated and no valid `CommandToken` presented | L7 triggers OS re-auth, retries with token |
| `NotFound(String)` | Ticket / grant / audit_id missing | L7 refreshes state |
| `Invalid(String)` | Malformed request payload (unknown capability, scope/kind mismatch, stale timestamp) | Caller fixes payload |
| `Conflict(String)` | Ticket already responded; grant already revoked; concurrent emergency revoke | L7 displays latest state |
| `AuditBlocked` | Audit writer unhealthy — deny-all in effect | Banner + diagnostic flow |
| `Internal(String)` | Uncategorized Rust-side error | Log + retry; surface in diagnostics |

### 7.2 `PolicyEngineError` — in-process Rust callers

| Variant | When it fires | Recovery expectation |
|---|---|---|
| `Degraded(DegradedMode)` | Same as IPC | Caller bubbles to UI layer |
| `BusClosed` | Event bus torn down (shutdown in progress) | Caller exits cleanly |
| `Invalid(&'static str)` | Malformed `ActionRequest` | Caller fixes before retry |
| `TicketNotFound` | `respond_approval` with unknown ticket | Caller refreshes |
| `TicketConflict(&'static str)` | Double-response / stale / revoked | Caller refreshes |
| `RequiresReauth` | Capability-gated Rust-side call without token (rare) | Bubble to L7 |
| `AuditBlocked` | Audit writer unhealthy | Deny-all; caller halts |
| `Internal(String)` | Uncategorized | Log; do not retry blindly |

Every error in both enums is serializable to a stable machine-readable `code` field so the TS bindings and the Rust trait share one vocabulary.

---

## 8. Dependency expectations

L5 is a **dependency**, not a dependent. The layers below must never be bypassable.

- **L6 persona compiler** — L5 consumes `CompiledPersona.policy_defaults` on every `persona_swap_commit`. Fallback: `MinimumTrustPersona` (shipped with the build). Contract surface from §3.4 above must be frozen before L5 stable.
- **Storage package (SQLite)** — L5 owns two tables (`grants`, `audit_log`) and one cache table (`cost_counters`) in the **same SQLite DB file** as the storage package (source §7.2, §8.2, §9.3). Single-writer guaranteed via `tauri-plugin-single-instance` (X3 G2 pending). L5 never opens a distinct DB connection — it uses the storage package's pooled handle.
- **OS keyring** (`keyring-rs`) — holds the per-install HMAC key for audit-log integrity. Windows Credential Manager / macOS Keychain / Linux Secret Service. Key loss → chain verification fails at boot → user acknowledges → new genesis record (source §8.3).
- **OS clock** — monotonic for all TTL / expiry / precedence comparisons; wall-clock only for UX display and export timestamps. Suspicious wall-clock regression (> 60 s earlier than last boot) emits `clock_skew_detected` audit row (source §11.3).
- **Event bus** (from `08_system_architecture.md`) — single global monotonic `seq` counter per Rust process. L5 publishes its event family and subscribes to `cost_event`, `persona_swap_commit`, `memory_provenance_update`.
- **Tauri runtime** — IPC command surface; bridge filters which L5 events reach the webview (`X3 §3.2`).

**Invariants L5 enforces on dependents:**

- L1 MUST NOT dispatch a tool plan without holding an `Arc<dyn PolicyEngine>` and presenting `Decision::Allow`.
- L2 MUST NOT write memory (session / durable / preference) or serve gated reads without `Decision::Allow`.
- L4 MUST NOT route to a remote provider without `Decision::Allow`; MUST emit `CostEvent` on every completion.
- L7 MUST NOT render an Allow UX without a live `GrantIssued` event matching the ticket.
- CI lint (`tools/lint-policy-bypass/`, source §12.1) rejects direct executor calls that skip the trait.

---

## 9. Implementation notes

- **Package layout** (per `planning/monorepo_plan_draft.md §2`, referenced by source ADR block):
  - file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/ — Rust core: evaluator, grant ledger, audit writer, cost counters, trait, error enums, event types.
  - file:///C:/Users/dbhav/Projects/aether/packages/l5-policy-ts/ — TS bindings: types only, no logic. Generated from the Rust types via `ts-rs` or `specta`.
- **Database**: the `grants`, `audit_log`, `audit_checkpoints`, and `cost_counters` tables live in the **same SQLite file as the storage package** (single DB, single writer). Use the storage package's pool; do not open a second connection. Schema migrations are append-only-additive and coordinated with the Tauri signed updater (source §8.6).
- **Keyring**: HMAC key via `keyring-rs`. Service name `aether.l5.audit`; key id in keyring metadata supports rotation (source §8.3). Key rotation policy itself is open (§14.8 below — source §14.2).
- **Event bus**: use whatever primitive the monorepo settles on (tokio broadcast + a thin wrapper is the working assumption). `seq` is a single global `AtomicU64` in the L5 crate — exposed to subscribers but owned by the emitter side.
- **Linter**: ship `tools/lint-policy-bypass/` alongside L5; it scans Rust crates for direct calls to executors (`browser_tool::*`, `filesystem_plugin::*`, `email_tool::*`, `router::dispatch_remote`) that do not flow through a `Decision::Allow` branch. Fails CI if it finds any.
- **Tests** (source §13): red-team simulation matrix, property tests (monotonicity, revocation idempotency, audit-chain integrity, ledger-replay equivalence, deny-all-under-audit-failure), replay tests, perf tests against the 10 / 150 / 500 / 100 ms budgets.
- **Degraded-mode wiring**: `SafeMode`, `AuditBroken`, `MinimumTrust` are enum variants on `DegradedMode`. L5 emits `PolicyPostureChanged { trigger: DegradedEntry }` on entry and `DegradedExit` on recovery. L7 renders the banner; L1 pauses turn execution; L4 refuses all remote routes.
- **IPC command gating**: `set_preset`, `revoke { All }`, `emergency_revoke_all`, and any future `capabilities.unblock` require a re-auth `CommandToken` produced by L7. Re-auth is itself audited.

---

## 10. Flagged contradictions (do not silently resolve)

These are the open items blocking stand-up. Each one has a ticket in `plans/L1_L4_L5_L7_integration_notes.md §10`:

1. **`Decision::NeedsUpgrade` encoding (Q2).** Source §3.1 lists `NeedsUpgrade` as a top-level `Decision` variant; integration notes §10 Q2 flags that L1 and L5 may collapse it to `Decision::Deny { reason: NeedsUpgrade }`. UX differs (upgrade card vs. deflection). **Must lock before L7 implements the upgrade card.**
2. **`Decision::AllowDraft` variant (Q3).** L7 proposes a "Draft only" approval choice that produces artifacts without commit/send side effects. Source `Decision` enum has `DraftOnly` (a decision), not `AllowDraft` (a user-choice path). Requires either a new `Decision::AllowDraft { side_effects_inhibited }` variant OR confirmation that the existing `DraftOnly` is the correct encoding plus L4 side-effect inhibition plumbing. **Must lock before L7 builds approval-choices UI.**
3. **Per-step re-evaluation rule (Q1).** Multi-step plans at Operator+ — does every step re-evaluate, or does the initial grant cover the chain? Source §3.4 edge cases and §14.8 (`preview_plan` P1/P2) both touch this but neither locks it. Canonical rule is pending. **Blocks L1 tool-plan loop contract and L7 chain-approval UX.**
4. **BYOK cost-cap re-arm flow (Q4).** Re-arm mechanics (user button / period rollover / re-auth requirement / typed-confirmation) are proposed in source §9.4 but not locked. Counter persistence across restart is referenced but the schema (source §9.3) does not explicitly reconcile with the "re-arm within 1 hour requires double re-auth" proposal. **Blocks L7 wallet widget interactivity.**
5. **Missing commands `policy.export_audit` and `policy.set_cost_cap` / `policy.reset_cost_counter` (Q5).** Integration notes §7.2 and source §9.4 reference these commands, but the canonical command catalog in source §5.2 does **not** list them. Must be added to the IPC surface before L7 can implement the export flow or the re-arm button.
6. **Doc-anchor drift (source §14.1, §14.7).** Source cites `12_permissions_autonomy.md §9.4` and `13_trust_security_redteam.md §10.3`, neither of which exist in the referenced files. Source treats the nearest canonical sections as authoritative but flags for Don. A late-added capability or red-team block could ship without a matching row here. **Blocks self-review sign-off.**
7. **HMAC key rotation policy (source §14.2).** Single per-install vs rotation-on-major-version vs user-initiated. Affects updater coordination and Custom-preset UX.
8. **`AuditExport` capability identifier (source §14.6).** Distinct from `MemoryExport`? Proposed distinct + Critical; not yet in the canonical `Capability` enum. Blocks L7 trust-center export UX.
9. **Plan-preview scope (P1 vs P2) (source §14.8).** Whether `policy.preview_plan` ships P0 stubbed as `NotImplemented`, P1, or P2. Integration-notes §10 implicitly depends on the preview for chain-approval UX. Locks L7's chain-UX timeline.
10. **Isabelle `privileged_profile` mechanics (source §14.10).** Proposed as a persona property. Not yet ratified. Affects audit-record shape (extra field) and posture summary.
11. **Doctrine layer-count drift (source §14.11).** `01_product_doctrine.md` says 8 layers; `00_ORCHESTRATION_MAP §1` reconciles to 7. This pack uses 7 per the orchestration map. Doctrine update pending Don's sign-off.

Implementers: do not resolve these inside the crate. Flag to Don; block the relevant downstream consumer; pin the open-question ticket in the PR description.

---

## 11. Self-review checklist

- [x] Inbound shapes for `ActionRequest`, `ApprovalResponse`, `PersonaCompiledPolicyDefaults`, `CostEvent`, `MemoryProvenanceUpdate` each have producer, required fields, optional fields, validation rules, failure modes.
- [x] Outbound events (`PolicyDecision`, `ApprovalPending`, `GrantIssued`, `GrantRevoked`, `AuditRecord`, `EmergencyRevokeAll`, `CostThresholdHit`, `PolicyPostureChanged`) each have emitter-side invariants and failure modes.
- [x] Sync vs async boundaries explicit; audit-write-before-Allow-returns invariant stated.
- [x] `PolicyEngine` trait surface includes `evaluate`, `subscribe`, `emergency_revoke`, `snapshot_grants`, `capabilities`, `respond_approval`.
- [x] `Decision`, `DenyReason`, `ApprovalMode`, `GrantDuration`, `Capability` enums referenced with all variants from source §2.1 / §3.1.
- [x] Error vocabulary standardized into `PolicyIpcError` + `PolicyEngineError`.
- [x] Dependencies on L6, storage, keyring, clock, bus, Tauri named; invariants on L1/L2/L4/L7 enumerated.
- [x] Implementation notes point to `packages/l5-policy/` + `packages/l5-policy-ts/`; audit log and grant ledger confirmed to live in the same SQLite DB as storage.
- [x] Contradictions flagged, not resolved (11 open items in §10 above).
