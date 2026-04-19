---
status: draft
date: 2026-04-18
layer: L5 (policy / authorization engine)
mode: system design (implementation-grade)
upstream:
  - plans/L5_policy_engine.md
  - 01_product_doctrine.md (§"Must-own layers" #5, §"Desktop framework doctrine")
  - 12_permissions_autonomy.md
  - 13_trust_security_redteam.md
  - 08_system_architecture.md
  - plans/00_ORCHESTRATION_MAP.md
  - plans/X3_tauri_architecture.md (G1 APPROVED 2026-04-18)
  - planning/monorepo_plan_draft.md (§2: packages/l5-policy/ + l5-policy-ts/)
  - plans/03_content_lock_v1_port.md §4 (BYOK hard-cap enforcement belongs to L5)
downstream_consumers:
  - plans/L1_interaction_timing.md (policy gate before tool plan execution)
  - plans/L2_memory_kernel.md (gated memory reads/writes; provenance input)
  - plans/L4_model_router.md (routes only after policy allow; cost_event emitter)
  - plans/L7_trust_ux_onboarding.md (renders approval surfaces + trust center)
scope_of_this_document:
  - Implementation blueprint an engineer can start building against
  - DDL and pseudotypes INSIDE this markdown; no .rs or .sql artifacts
  - Freezes the L5 contract that L1/L2/L4/L7 stub against
non_goals:
  - Resolving doctrine conflicts (flagged in §14, not decided here)
  - Writing the trust-center UI (L7)
  - Implementing the engine (no crates, no migrations)
  - BYOK cert-class / HSM choice (X3 G3)
---

# L5 — Policy / Authorization Engine — System Design

> This document is the engineering blueprint. The plan (`plans/L5_policy_engine.md`) says *what* L5 owns. This document says *how* L5 is built. Downstream layers (L1, L2, L4, L7) should stub against the contracts frozen here (§4, §5, §12).
>
> Canonical planning root: file:///C:/Users/dbhav/Projects/aether-planning/
> Target package home (X1-dependent): file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/ + file:///C:/Users/dbhav/Projects/aether/packages/l5-policy-ts/

---

## 1. Scope recap + non-goals

### Owns (mirrors `plans/L5_policy_engine.md` "Boundaries — Owns")

- The capability taxonomy (Files / Browser / Email / System / Memory / Media / Integrations) and every sub-capability typed identifier.
- Five-layer permission evaluator (feature → action scope → resource scope → approval mode → grant duration).
- Four risk classes (Low / Medium / High / Critical) with default approval mapping per autonomy preset.
- Five autonomy presets (Observer / Assistant / Operator / Power User / Custom) compiled into capability × risk-class matrices.
- Approval workflow state machine (`Allow` / `Ask` / `DraftOnly` / `Deny` / `NeedsUpgrade`).
- Grant ledger (active temporary grants, TTL, revocation semantics).
- Append-only, hash-chained, HMAC-integrity audit log.
- Non-negotiable hardcoded blocks (finance / healthcare / password-mgr domains; unrestricted disk; silent upload).
- Policy decision events on the bus: `action_request`, `policy_decision`, `approval_pending`, `approval_response`, `grant_issued`, `grant_revoked`, `audit_record`, `emergency_revoke_all`, `cost_threshold_hit`.
- BYOK hard-cap **enforcement** (rolling counters + deny-on-threshold). Cost *accounting* stays in L4; L5 only enforces.
- Privacy-posture gate (private-tagged context + remote-route → deny unless explicit grant).
- Emergency-revoke-all primitive.

### Does not own (mirror)

- Approval UI rendering (L7 subscribes to `approval_pending`, renders, posts `approval_response`).
- Tool execution (engines emit `action_request`; executors only run after `allow`).
- Memory content/retrieval (L2).
- Which model answers (L4).
- Persona-specific approval tuning values (L6 compiles; L5 consumes).
- Cost *measurement* (L4 emits `cost_event`; L5 maintains thresholds + deny).
- OS-level sandboxing of the Tauri process (X3 / platform concern).
- The webview. The webview never holds a policy decision; L5 is Rust-only except for its TS bindings crate (`l5-policy-ts`) which re-exports **types**, not logic.

### Non-goals for this session (reinforced)

- No code. No DDL materialized into `.sql`. No trait files. Everything stays inside this document as pseudotype and schema text.
- No resolution of the rendering-surface, sync-transport, or mobile-stack gates.
- No decisions about the HSM / code-signing cert class (X3 G3).
- No doctrine rewrites — §14 flags, never resolves, contradictions.

---

## 2. Capability taxonomy — concrete

Capabilities are the **stable identifiers** that gate every action. Every sub-capability listed in `12_permissions_autonomy.md §"Capability groups"` appears below. Identifiers follow a `group.action[.qualifier]` dot-path. The evaluator never matches on prose — only on the typed identifier.

### 2.1 Pseudotype (Rust-leaning)

```rust
// Stable identifier for a capability. Serde-serializable as its dot-path.
pub enum Capability {
    // --- Files ---
    FilesRead,
    FilesCreate,
    FilesEdit,
    FilesRenameMove,
    FilesDelete,
    FilesBulkOp,

    // --- Browser ---
    BrowserOpen,            // navigate to an allowed site
    BrowserReadPage,
    BrowserExtractData,
    BrowserFillForm,
    BrowserUpload,
    BrowserDownload,
    BrowserSubmit,          // click / submit action
    BrowserLoginReuse,      // reuse stored session

    // --- Email ---
    EmailReadMetadata,
    EmailReadBody,
    EmailDraft,
    EmailEditDraft,
    EmailSend,
    EmailAttachmentAccess,

    // --- System & tools ---
    ClipboardRead,
    ClipboardWrite,
    ShellExec,              // terminal / script
    PackageInstall,
    NotificationRead,
    AutomationTrigger,

    // --- Memory ---
    MemoryRead,             // policy-gated reads (provenance-sensitive)
    MemoryWriteSession,
    MemoryWriteDurable,
    MemoryWriteExtractedPref,
    MemoryUseInFutureTask,
    MemoryExport,
    MemoryDelete,

    // --- Media ---
    MediaMic,
    MediaCamera,
    MediaScreenCapture,

    // --- Integrations (Pro) ---
    IntegrationUse(IntegrationId),
    IntegrationExternalApi(ApiId),
    IntegrationTriggerAutomation(AutomationId),

    // --- Router / cost ---
    RouterEscalateRemote,       // L4 routes a turn to a remote frontier LLM
    RouterOverrideTier,         // user / persona forces a tier change
    RouterAllowRemoteWithPrivate, // waiver capability for privacy-posture gate (§10)
}

pub enum ResourceScope {
    Path(PathGlob),             // e.g. "C:/Users/dbhav/Aether_Workspace/**"
    Url(UrlPattern),            // e.g. "https://*.github.com/**"
    Mailbox { account: String, folder: String },
    MemoryScope(MemoryScopeId), // e.g. "session", "project:<id>", "persona:<id>"
    Provider(ProviderId),       // for router + cost-cap scopes
    Any,                        // explicit "unscoped" — only valid for a few low-risk caps
    None,                       // capability is inherently resource-less (e.g. ClipboardWrite)
}
```

### 2.2 Capability table — defaults

Columns: **Cap** (id), **Risk** (default class), **Default mode** per preset (O=Observer, A=Assistant, Op=Operator, PU=Power User), **Dur** (default grant duration), **Scope shape**, **Executor** (which layer/engine actually runs it post-allow).

Default modes: `auto` = auto-allow within scope, `ask` = ask every time, `task` = ask once per task, `draft` = draft-only (never auto-execute), `deny` = default-denied, `block` = hardcoded block (only via explicit Custom unblock). Power User widens Operator defaults; Custom inherits user's matrix.

| Cap | Risk | O | A | Op | PU | Dur | Scope | Executor |
|---|---|---|---|---|---|---|---|---|
| FilesRead | Low | deny | auto-in-scope | auto | auto | session | Path glob | L2 / filesystem plugin |
| FilesCreate | Med | deny | task | auto | auto | task | Path glob | filesystem plugin |
| FilesEdit | Med | deny | task | auto | auto | task | Path glob | filesystem plugin |
| FilesRenameMove | Med | deny | ask | task | auto | task | Path glob | filesystem plugin |
| FilesDelete | High | deny | ask | ask | task | once | Path glob | filesystem plugin |
| FilesBulkOp | High | deny | ask | ask | ask | once | Path glob | filesystem plugin |
| BrowserOpen | Low | deny | auto-in-scope | auto | auto | session | URL pattern | L4 / browser tool |
| BrowserReadPage | Low | deny | auto | auto | auto | session | URL pattern | browser tool |
| BrowserExtractData | Med | deny | task | auto | auto | task | URL pattern | browser tool |
| BrowserFillForm | Med | deny | ask | task | auto | task | URL pattern | browser tool |
| BrowserUpload | High | deny | ask | ask | ask | once | URL pattern | browser tool |
| BrowserDownload | Med | deny | task | task | auto | task | URL pattern | browser tool |
| BrowserSubmit | High | deny | ask | ask | ask | once | URL pattern | browser tool |
| BrowserLoginReuse | High | deny | deny | ask | ask | once | URL pattern | browser tool |
| EmailReadMetadata | Low | deny | task | auto | auto | session | mailbox | email tool |
| EmailReadBody | Med | deny | task | task | auto | task | mailbox | email tool |
| EmailDraft | Low | deny | auto | auto | auto | session | mailbox | email tool |
| EmailEditDraft | Low | deny | auto | auto | auto | session | mailbox | email tool |
| EmailSend | High | deny | ask | ask | ask | once | mailbox | email tool |
| EmailAttachmentAccess | High | deny | ask | ask | ask | once | mailbox | email tool |
| ClipboardRead | Low | ask | auto | auto | auto | session | none | system plugin |
| ClipboardWrite | Low | ask | auto | auto | auto | session | none | system plugin |
| ShellExec | Critical | block | block | ask | ask | once | none | shell plugin |
| PackageInstall | Critical | block | block | block | ask | once | none | shell plugin |
| NotificationRead | Low | deny | auto | auto | auto | session | none | system plugin |
| AutomationTrigger | High | deny | ask | ask | ask | once | AutomationId | automation plugin |
| MemoryRead | Low | auto | auto | auto | auto | session | MemoryScope | L2 |
| MemoryWriteSession | Low | auto | auto | auto | auto | session | MemoryScope | L2 |
| MemoryWriteDurable | Med | deny | task | auto | auto | task | MemoryScope | L2 |
| MemoryWriteExtractedPref | Med | deny | ask | task | auto | task | MemoryScope | L2 |
| MemoryUseInFutureTask | Low | deny | auto | auto | auto | persistent | MemoryScope | L2 |
| MemoryExport | High | deny | ask | ask | ask | once | MemoryScope | L2 |
| MemoryDelete | Med | deny | ask | ask | task | once | MemoryScope | L2 |
| MediaMic | Med | ask | task | auto | auto | session | none | media engine |
| MediaCamera | High | ask | ask | ask | ask | session | none | media engine |
| MediaScreenCapture | High | deny | ask | ask | ask | once | none | media engine |
| IntegrationUse(id) | Med | deny | task | auto | auto | session | Integration | integrations plugin |
| IntegrationExternalApi(id) | Med | deny | task | task | auto | task | Api | integrations plugin |
| IntegrationTriggerAutomation(id) | High | deny | ask | ask | ask | once | Automation | integrations plugin |
| RouterEscalateRemote | Med | deny | ask | task | auto | task | Provider | L4 |
| RouterOverrideTier | Low | deny | auto | auto | auto | session | Provider | L4 |
| RouterAllowRemoteWithPrivate | High | deny | ask | ask | ask | once | Provider | L4 (waiver into §10 gate) |

**Preset semantics:**
- **Observer** is default-deny for anything autonomous; only read/draft with explicit scope, and only clipboard + memory-session as auto.
- **Assistant** is the recommended default: reads/drafts auto in scope, sensitive acts ask or task-bounded.
- **Operator** widens Medium actions to auto-in-scope; High still asks.
- **Power User** widens further but **never** auto-approves High/Critical per `12 §"Anti-patterns"`.
- **Custom** lets the user override anything except hardcoded blocks (which require explicit Custom unblock with per-category confirmation).

### 2.3 Hardcoded non-negotiable blocks (from `13 §"Red-team focus areas"` #3, #5, #6 and `12 §"Non-negotiable blocks"`)

These are evaluated **before** the 5-layer evaluator runs. They cannot be allowed by any preset; in Custom they require an explicit per-category unblock plus per-action confirmation, and the unblock itself is an audited capability mutation.

| Block | Rule | Rationale | Unblock path |
|---|---|---|---|
| `block.finance_domains` | Deny `Browser*` + `Email*` + `Integration*` targeting finance-category domains (bank, brokerage, payments). | `13 §3` Browser misuse; `12 §"Non-negotiable"`. | Custom + per-category confirm + per-action ask. |
| `block.healthcare_domains` | Deny `Browser*` + `Email*` + `Integration*` targeting healthcare category. | Same. | Same. |
| `block.password_manager_domains` | Deny `Browser*` + `Integration*` targeting password-manager domains (1Password, Bitwarden, LastPass, etc.). | Same. | Same. |
| `block.government_domains` | Deny `Browser*` targeting government domains (tax, benefits, voter, court) in consumer-safe presets. | `12 §"Non-negotiable"` extended category. | Same. |
| `block.unrestricted_disk` | Deny any `Files*` capability with `ResourceScope::Any` or a glob that resolves above the user-approved roots. | `12`. | Custom + explicit root expansion in onboarding. |
| `block.silent_upload` | Deny any action that both (a) reads user data and (b) submits to a remote endpoint **in the same task** unless both caps are explicitly granted. | `13 §4` Data exfiltration. | Both caps granted + per-task ask. |
| `block.shell_in_consumer_presets` | `ShellExec` + `PackageInstall` default-blocked in O / A / Op presets regardless of per-capability override. | `12`. | Power User or Custom. |
| `block.email_send_default` | `EmailSend` default-blocked until enabled per-account. | `12`. | Per-account onboarding step. |
| `block.auto_approve_high_critical` | No preset may auto-approve High or Critical; the evaluator rejects an attempt to configure this. | `12 §"Anti-patterns"`. | None — configuration-layer invariant. |
| `block.private_context_remote` | See §10 privacy-posture gate. | Privacy contract. | `RouterAllowRemoteWithPrivate` explicit grant. |

The blocks are defined as data (a typed `HardcodedBlock` list shipped in the build), not as imperative code paths. They are evaluated in a **pre-evaluator** stage that runs before any preset/persona/user override can see the request.

---

## 3. Five-layer permission evaluator — state machine + pseudocode

### 3.1 Inputs & outputs

```rust
pub struct ActionRequest {
    pub request_id: RequestId,
    pub turn_id: TurnId,
    pub task_id: Option<TaskId>,
    pub capability: Capability,
    pub resource: ResourceScope,
    pub actor_persona: PersonaId,
    pub active_grants: Snapshot<GrantLedger>,   // snapshot at evaluator entry
    pub session_context: SessionContext,        // includes tier, preset, current preset version
    pub provenance_tags: Vec<ProvenanceTag>,    // from L2 (trusted / untrusted / private / ...)
    pub intended_route: Option<RouteHint>,      // L4's preview: local vs remote
    pub risk_class_hint: Option<RiskClass>,     // L4/L1 may annotate; evaluator re-checks
    pub emitted_at: MonotonicTimestamp,
}

pub enum Decision {
    Allow { grant_ref: Option<GrantId>, audit_id: AuditId },
    Ask { ticket: ApprovalTicket, audit_id: AuditId },
    DraftOnly { audit_id: AuditId, reason: StaticReason },
    Deny { reason: DenyReason, audit_id: AuditId },
    NeedsUpgrade { capability_path: Capability, audit_id: AuditId, suggested_preset: Option<PresetId> },
}

pub enum DenyReason {
    HardcodedBlock(HardcodedBlockId),
    FeatureDisabled,
    ActionOutOfScope,
    ResourceOutOfScope,
    ModeDeny,
    GrantExpired,
    GrantRevoked,
    ProvenanceTaint(TaintKind),      // e.g. untrusted context invoking medium+ risk
    PrivacyPostureViolation,
    CostCapHit(ProviderId),
    TierDowngradeStripped,
    LedgerCorrupt,                    // safe-mode — see §11
    AuditWriteFailed,                 // deny-all when we can't record — see §11
}
```

### 3.2 State machine (ASCII)

```
                      ActionRequest arrives
                              |
                              v
                    [0] Pre-evaluator gates
                     - Audit-log health check (if broken: Deny AuditWriteFailed, surface banner)
                     - Ledger integrity (if corrupt: Safe-Mode; only hardcoded-allow low-risk reads)
                     - Hardcoded blocks                (Deny if match)
                     - Privacy-posture gate (§10)      (Deny if violation, unless waiver grant)
                     - Provenance taint check         (Deny or DraftOnly if tainted + Medium+)
                     - Cost cap (§9)                  (Deny CostCapHit if hit)
                              |
                              v
                    [1] Feature enabled?
                     - Is the capability family enabled for this preset/persona?
                     - No -> NeedsUpgrade(capability_path)
                              |
                              v
                    [2] Action in scope?
                     - Is this specific action allowed in the preset × persona × user-override matrix?
                     - No -> Deny ActionOutOfScope (or NeedsUpgrade if there's an uplift path)
                              |
                              v
                    [3] Resource in scope?
                     - Does `resource` match a granted ResourceScope under this capability?
                     - No -> Deny ResourceOutOfScope (L7 offers "add scope" flow)
                              |
                              v
                    [4] Approval mode?
                     - Look up the effective mode (precedence in §6.3).
                       auto   -> fall to [5]
                       task   -> active task grant? yes -> [5]; no -> emit Ask
                       ask    -> emit Ask
                       draft  -> DraftOnly
                       deny   -> Deny ModeDeny
                              |
                              v
                    [5] Grant duration / TTL?
                     - If an existing grant covers this (cap, resource, task), validate not expired/revoked.
                     - If no grant but mode == auto, synthesize an ephemeral grant (once-scope) and record it.
                              |
                              v
                    Emit policy_decision{Allow}, write audit record, return Decision::Allow
```

Failure-class short-circuits at each stage record an audit entry **before** returning the deny. No deny goes unrecorded (see §11 — audit-write failure forces deny-all).

### 3.3 Evaluator pseudocode

```rust
fn evaluate(req: ActionRequest, ctx: &PolicyContext) -> Decision {
    // --- Stage 0: pre-evaluator gates (ordered; first hit wins) ---
    if !ctx.audit_log.healthy() {
        // Never silent-allow when we can't record.
        return Decision::Deny {
            reason: DenyReason::AuditWriteFailed,
            audit_id: AuditId::NULL,
        };
    }
    if ctx.ledger.is_corrupt() {
        // Safe-mode: allow only the hardcoded-safe read-only set; deny anything else.
        if !ctx.safe_mode_allowlist.contains(&req.capability) {
            return audit_and_deny(DenyReason::LedgerCorrupt, &req, ctx);
        }
    }
    if let Some(block) = ctx.hardcoded_blocks.match_against(&req) {
        return audit_and_deny(DenyReason::HardcodedBlock(block.id), &req, ctx);
    }
    if let Err(privacy_err) = evaluate_privacy_posture_gate(&req, ctx) {
        return audit_and_deny(DenyReason::PrivacyPostureViolation, &req, ctx);
    }
    if let Some(taint) = taint_from_provenance(&req, ctx) {
        // Tainted + risk >= Medium: downgrade to DraftOnly or Deny per policy.
        return audit_and_tainted(taint, &req, ctx);
    }
    if let Some(provider) = ctx.cost_caps.provider_over_threshold(&req) {
        return audit_and_deny(DenyReason::CostCapHit(provider), &req, ctx);
    }

    // --- Stage 1: feature enabled ---
    if !ctx.preset.feature_enabled(&req.capability, &req.actor_persona) {
        return audit_and_needs_upgrade(&req, ctx);
    }

    // --- Stage 2: action in scope ---
    if !ctx.preset.action_in_scope(&req.capability, &req.actor_persona) {
        return audit_and_deny(DenyReason::ActionOutOfScope, &req, ctx);
    }

    // --- Stage 3: resource in scope ---
    if !ctx.grants.resource_allowed(&req.capability, &req.resource, &req.actor_persona) {
        return audit_and_deny(DenyReason::ResourceOutOfScope, &req, ctx);
    }

    // --- Stage 4: approval mode ---
    let mode = ctx.effective_mode(&req);   // precedence per §6.3
    match mode {
        ApprovalMode::Auto => {}, // fall through
        ApprovalMode::TaskScoped => {
            if !ctx.grants.has_task_grant(&req) {
                return audit_and_ask(&req, ctx);
            }
        }
        ApprovalMode::Ask => return audit_and_ask(&req, ctx),
        ApprovalMode::DraftOnly => return audit_and_draft(&req, ctx),
        ApprovalMode::Deny => return audit_and_deny(DenyReason::ModeDeny, &req, ctx),
    }

    // --- Stage 5: grant duration / TTL ---
    match ctx.grants.validate_or_issue(&req) {
        Ok(grant_id) => audit_and_allow(grant_id, &req, ctx),
        Err(GrantError::Expired)  => audit_and_deny(DenyReason::GrantExpired,  &req, ctx),
        Err(GrantError::Revoked)  => audit_and_deny(DenyReason::GrantRevoked,  &req, ctx),
        Err(GrantError::Downgrade) => audit_and_deny(DenyReason::TierDowngradeStripped, &req, ctx),
    }
}
```

### 3.4 Edge cases (explicit handling)

- **Persona hot-swap mid-evaluation.** The evaluator reads `active_grants` as a **snapshot** taken at entry. If a `persona_swap_commit` event arrives while an evaluation is in flight, the decision proceeds against the snapshot but any resulting grant is annotated `stale_persona = true` and **not** issued — instead the decision is rewritten to `Ask` with reason `"persona_swapped_during_decision"`. L6's swap protocol (`grant_revoke_all_session` before the new persona accepts requests) makes this a narrow race; the annotation exists so post-mortems can find it.
- **Expired grant.** A grant whose `expires_at_monotonic < now_monotonic` is invalid regardless of wall-clock. Cross-check with wall-clock on boot to detect system-clock shenanigans (see §11 clock skew).
- **Revoked-during-ask.** If a grant is revoked after `approval_pending` is emitted but before `approval_response` arrives, the response is rejected with `DenyReason::GrantRevoked` and a new ask is not auto-emitted (avoid prompt loops).
- **Tainted provenance.** `L2` annotates memory hits with `provenance_tags` — `untrusted_input`, `scraped_content`, `private_context`, etc. Medium+ requests touching untrusted-tainted context are demoted to `DraftOnly`; High/Critical are denied. See `13 §2` memory poisoning.
- **Tier-downgrade stripping a capability.** On `core.health` tier demotion (e.g. VRAM pressure), the router (L4) may cut remote-escalation. A grant issued under the higher tier is marked `strip-on-demote` by capability; the next evaluation in the demoted tier returns `TierDowngradeStripped` and surfaces a trust-center notice.
- **Multi-step plan chain.** The evaluator is per-call. At Pro Phase 2 (`plans/L5_policy_engine.md §"Sequencing"` P2) a `policy_preview(plan)` command (§5) evaluates the whole plan up front and emits a `PlanPreview` so the user sees Medium+ chains before approving.

---

## 4. Event contracts — typed

All events live on the Rust-internal event bus (`08_system_architecture.md §"The event bus"`). A **filtered subset** is projected to the webview via the Tauri bridge (`X3 §3.2`). Every projected event carries `source_layer`, `change_id`, and monotonic `seq`.

### 4.1 Event types

```rust
pub struct ChangeId(pub u64);
pub struct Seq(pub u64);
pub enum SourceLayer { L1, L2, L3, L4, L5, L6, L7, Media, Core }

pub enum L5Event {
    ActionRequest(ActionRequestEvent),
    PolicyDecision(PolicyDecisionEvent),
    ApprovalPending(ApprovalPendingEvent),
    ApprovalResponse(ApprovalResponseEvent),
    GrantIssued(GrantIssuedEvent),
    GrantRevoked(GrantRevokedEvent),
    AuditRecord(AuditRecordEvent),
    EmergencyRevokeAll(EmergencyRevokeAllEvent),
    CostThresholdHit(CostThresholdHitEvent),
}
```

### 4.2 Per-event fields, emitter, subscribers, idempotency, ordering, projection

| Event | Fields (Rust types) | Emitter | Subscribers | Idempotency | Ordering | Projected to webview? |
|---|---|---|---|---|---|---|
| `action_request` | `request_id: RequestId`, `turn_id: TurnId`, `task_id: Option<TaskId>`, `capability: Capability`, `resource: ResourceScope`, `actor_persona: PersonaId`, `provenance_tags: Vec<ProvenanceTag>`, `intended_route: Option<RouteHint>`, `emitted_at: MonotonicTimestamp`, `seq: Seq` | Any action-initiating engine (Cognition / L2 write path / L4 router / Media) | L5 evaluator only | `request_id` is unique; duplicate → dropped after logging | Strict per `turn_id`; may interleave across turns | **No** (internal only) |
| `policy_decision` | `request_id: RequestId`, `decision: Decision`, `audit_id: AuditId`, `reason: Option<StaticReason>`, `change_id: ChangeId`, `source_layer: L5`, `seq: Seq` | L5 | L1 (gate tool plan), L4 (route ok?), L2 (write ok?), L7 (render decision) | `audit_id` unique; idempotent on re-emit (same audit_id wins) | Strict after the corresponding `action_request` | **Yes** (summary form) |
| `approval_pending` | `ticket_id: ApprovalTicketId`, `request_id: RequestId`, `capability: Capability`, `resource: ResourceScope`, `risk_class: RiskClass`, `explanation: StaticCopyId`, `deadline_hint: Option<MonotonicTimestamp>`, `change_id`, `seq` | L5 | L7 (render), L1 (stall ack @ 800ms per `L5_plan §Key risks §8`) | `ticket_id` unique | Strict after `policy_decision{Ask}` | **Yes** |
| `approval_response` | `ticket_id`, `user_choice: UserChoice { Allow \| AllowScope(ResourceScope) \| AllowTask \| AllowSession \| Deny }`, `responded_at: MonotonicTimestamp`, `change_id`, `seq` | L7 (webview → Rust via `policy.respond_approval` command; event re-emitted inside Rust) | L5 | `ticket_id` accepts exactly one response; later responses rejected | Strict after `approval_pending` | **No** (command, not projected event) |
| `grant_issued` | `grant_id: GrantId`, `capability`, `resource_scope: ResourceScope`, `approval_mode: ApprovalMode`, `duration: GrantDuration`, `issued_at: MonotonicTimestamp`, `expires_at: Option<MonotonicTimestamp>`, `issued_by: IssuedBy`, `audit_ref: AuditId`, `change_id`, `seq` | L5 | L7 (trust center), L1 (task-state annotation), L4 (route permission) | `grant_id` unique | Strict after its `policy_decision{Allow}` | **Yes** |
| `grant_revoked` | `grant_id`, `revoked_at: MonotonicTimestamp`, `revoked_reason: RevokeReason`, `audit_ref: AuditId`, `change_id`, `seq` | L5 (user action, persona swap, TTL expiry, emergency revoke) | L7, L1, L4 | `grant_id` may only be revoked once (subsequent = no-op + log) | After any pending emissions referencing that grant | **Yes** |
| `audit_record` | `audit_id: AuditId`, `timestamp_monotonic: MonotonicTimestamp`, `timestamp_wall: WallClockTimestamp`, `actor: ActorRef`, `capability`, `resource: ResourceScope`, `decision: DecisionKind`, `reason: Option<StaticReason>`, `change_id: ChangeId`, `prev_hash: Hash32`, `record_hmac: Hmac32`, `seq` | L5 (append-only writer) | L7 (summary projection), storage | Append-only; hash chain enforces no retro-editing | Strictly monotonic within the log | **Yes (summary projection)** — full record fetched by query |
| `emergency_revoke_all` | `initiated_by: Actor`, `scope: EmergencyScope { All \| Category(CapGroup) \| Persona(PersonaId) }`, `initiated_at`, `completed_at: Option<MonotonicTimestamp>`, `audit_ref` | L5 (triggered by L7 "big red button" command or by L6 swap) | L1 (abort in-flight tool calls), L4 (abort routes), L2 (abort writes), L7 (render status), storage | One in-flight at a time; concurrent calls coalesce | Strictly ordered; no events may be reordered around it | **Yes** |
| `cost_threshold_hit` | `provider: ProviderId`, `threshold: CostThreshold { Daily \| Monthly \| PerProvider \| PerPersona }`, `dollars_hit: Cents`, `counter_window: TimeWindow`, `audit_ref`, `change_id`, `seq` | L5 (from §9 counters) | L4 (deny future routes to provider), L7 (trust center banner) | Once per threshold-crossing window; re-arm resets | Strict after the triggering `cost_event` from L4 | **Yes** |

### 4.3 ChangeId / seq / source_layer conventions (from X3 §3.2)

- `source_layer` = `SourceLayer::L5` for every event L5 emits.
- `seq` is a single global monotonic counter per Rust process, guaranteeing the UI can detect drops.
- `change_id` is assigned by the write path. Every write-class command returns a `ChangeId`; the subsequent event with that `change_id` is the confirmation. For L5, the `policy.request_approval` / `policy.revoke` / `policy.set_preset` commands return `ChangeId`s that map to the emitted event.
- Events that do not originate from a command (e.g. TTL expiry → `grant_revoked`) still carry a `change_id` drawn from the same counter so the UI can treat them uniformly.

### 4.4 Rust-internal only (not projected)

- `action_request` — internal; the webview never sees raw action requests, only the decision. (Prevents UI from attempting to "pre-approve" off-bus.)
- `approval_response` — modeled as a **command** (§5), not a projected event. It never crosses the bridge as an event.

All other L5 events are projected, either full or in summary form. Full-fidelity audit records are fetched via `trust.get_action_history` (L7-owned command that L5 services).

---

## 5. Tauri IPC command surface for L5

Fleshes out `X3 §2.2` "L5 — policy". Every command is a `#[tauri::command]` with typed request/response; no stringly-typed shapes. Every write-class command returns a `ChangeId`. Error vocabulary uses `thiserror` enums; no untyped errors cross IPC.

### 5.1 Request/response types

```rust
// Shared error envelope for L5 commands.
#[derive(thiserror::Error, Debug)]
pub enum PolicyIpcError {
    #[error("policy engine unavailable (degraded mode: {0:?})")]
    Degraded(DegradedMode),
    #[error("capability-gated command requires re-auth")]
    RequiresReauth,
    #[error("not found: {0}")]
    NotFound(String),
    #[error("invalid request: {0}")]
    Invalid(String),
    #[error("conflict: {0}")]
    Conflict(String),            // e.g. ticket already responded
    #[error("audit write failed; all writes blocked")]
    AuditBlocked,
    #[error("internal: {0}")]
    Internal(String),
}

pub enum DegradedMode { SafeMode, AuditBroken, LedgerCorrupt }
```

### 5.2 Command catalog

| Command | Request | Response | Failure vocab | Side effects | UI semantics | Capability-gated? |
|---|---|---|---|---|---|---|
| `policy.evaluate` | `ActionRequest` | `Decision` | `Invalid`, `Degraded`, `AuditBlocked` | Writes `audit_record`; may emit `policy_decision` / `approval_pending` / `grant_issued` | **Non-blocking** for Ask/DraftOnly (returns immediately with a ticket or reason); Allow returns the `grant_ref` to the caller. Returns `ChangeId`. | No (the evaluator is the gate itself) |
| `policy.request_approval` | `request_id: RequestId` (refers to a pending evaluation) | `ApprovalTicket { ticket_id, deadline_hint }` | `NotFound`, `Conflict`, `Degraded` | Emits `approval_pending` | Webview listens for the corresponding event; returns `ChangeId` | No |
| `policy.respond_approval` *(new — proposed)* | `ticket_id`, `user_choice: UserChoice` | `()` | `NotFound`, `Conflict` (already responded / revoked), `Degraded` | Triggers re-evaluation; emits `policy_decision` + possibly `grant_issued` | Blocking w/ optimistic UI; returns `ChangeId` that maps to the follow-up decision event | No |
| `policy.set_preset` | `preset: PresetId` | `PresetSwitchReceipt { change_id, stripped_grants: Vec<GrantId> }` | `RequiresReauth`, `Invalid`, `Degraded` | Revokes incompatible session grants (≤100 ms per `L5_plan §"Acceptance criteria"`); emits `grant_revoked` for each; emits `audit_record` | **Blocking** on re-auth modal | **Yes** (per `X3 §2.2`) — requires re-auth |
| `policy.get_preset` *(new)* | `()` | `CurrentPreset { id, overlaid_persona: PersonaId, version }` | `Degraded` | None | Non-blocking; cacheable | No |
| `policy.list_grants` | `filter: Option<GrantFilter>` | `Vec<Grant>` | `Degraded` | None | Non-blocking; returns snapshot | No (read-only) |
| `policy.revoke` *(new)* | `target: RevokeTarget { Single(GrantId) \| ByCapability(Capability) \| ByPersona(PersonaId) \| All }` | `RevokeReceipt { change_id, revoked: Vec<GrantId> }` | `NotFound`, `Degraded` | Emits `grant_revoked` for each; may emit `emergency_revoke_all` if `All` | Blocking; returns `ChangeId` | **Yes** — the `All` variant requires the "big red button" confirm flow |
| `policy.list_capabilities` *(new)* | `filter: Option<CapabilityFilter>` | `Vec<CapabilityInfo>` (id, risk class, current default per preset, human-readable explainer id) | `Degraded` | None | Non-blocking; used by settings UX | No |
| `policy.explain_decision` *(new)* | `audit_id: AuditId` | `Explanation { stages_evaluated: Vec<StageTrace>, effective_mode: ApprovalMode, precedence_path: Vec<PrecedenceSource>, reason: Option<StaticReason> }` | `NotFound`, `Degraded` | None | Non-blocking; powers "why was this asked?" trust-center link (`13 §"Trust center"`) | No (but: explaining a block that reveals a hardcoded-block catalog is fine; blocks are not secret) |
| `policy.preview_plan` *(new, P2 per `L5_plan` P2)* | `plan: Vec<ActionRequest>` | `PlanPreview { per_step: Vec<Decision>, aggregate_risk: RiskClass, suggested_bundle_approval: Option<ApprovalTicket> }` | `Invalid`, `Degraded` | Does not issue grants or write audit records (dry-run) | Non-blocking | No |
| `policy.emergency_revoke_all` *(new)* | `scope: EmergencyScope` | `EmergencyReceipt { change_id }` | `Degraded` | Emits `emergency_revoke_all`; revokes all matching grants ≤500 ms (per `L5_plan §"Acceptance criteria"`) | Blocking with "are-you-sure" + haptic/audio cue | **Yes** — triggers re-auth; all in-flight tool calls aborted |
| `policy.get_audit_summary` *(read helper, L7-facing)* | `filter: AuditFilter` | `Vec<AuditSummary>` (summaries only; full records via a streaming API) | `Degraded` | None | Non-blocking; paged | No (read-only) |
| `policy.stream_audit` *(streaming)* | `filter`, `cursor` | `EventStream<AuditRecordEvent>` | `Degraded` | None | Streaming; UI uses for trust-center history | No (read-only) |

### 5.3 Capability-gating of L5's own commands

Per `X3 §2.2`, `set_preset` requires re-auth. We extend the rule: any L5 command whose effect would widen the trust surface or revoke a broad scope (`set_preset`, `revoke{All}`, `emergency_revoke_all`, any future `capabilities.unblock` for Custom hardcoded overrides) requires re-auth. Re-auth is a biometric / OS-unlock step mediated by L7; it produces an ephemeral **command token** that the Rust side verifies before the command runs. The re-auth step is itself audited.

---

## 6. Autonomy presets — compiled matrix

### 6.1 Preset × capability compiled form

Each preset is data, not code. The compiler takes a `PresetSpec` + a `CompiledPersona` (from L6) + user overrides and produces a `CompiledMatrix` the evaluator reads in O(1) per capability.

```rust
pub struct CompiledMatrix {
    pub preset_id: PresetId,
    pub preset_version: u32,                       // bumped on any preset-rule change
    pub per_capability: HashMap<Capability, CapabilityRule>,
    pub persona_overlay: PersonaOverlayRef,
    pub user_overrides_hash: Hash32,
    pub compiled_at: MonotonicTimestamp,
}

pub struct CapabilityRule {
    pub feature_enabled: bool,
    pub default_mode: ApprovalMode,
    pub default_duration: GrantDuration,
    pub per_risk_class_override: [ApprovalMode; 4],   // by RiskClass index
    pub resource_scope_template: Option<ResourceScope>,
}
```

### 6.2 Preset × risk-class matrix

Compact summary (full per-capability defaults are in §2.2; this is the *when a capability of class X appears in this preset, what does it default to?* rollup):

| Preset | Low | Medium | High | Critical |
|---|---|---|---|---|
| Observer | ask (read-only set); others deny | deny | deny | block |
| Assistant | auto (in-scope reads + drafts) | task | ask | block |
| Operator | auto | auto (in-scope) | ask | block |
| Power User | auto | auto (in-scope) | ask | ask (explicitly never auto — `12 §"Anti-patterns"`) |
| Custom | user-defined per capability | user-defined | user-defined (clamped by `block.auto_approve_high_critical`) | blocked except Custom per-category unblock + per-action confirm |

### 6.3 Precedence (order a rule wins)

For a given `(capability, persona, user)`:

1. **Hardcoded blocks** (§2.3) — win over everything; cannot be overridden except via Custom per-category unblock with explicit per-action confirm.
2. **User override** — a user-set rule for this capability in their compiled preset.
3. **Persona default** — `CompiledPersona` from L6 carries persona-specific approval-mode defaults (e.g. a "Cautious" persona may force Low → ask).
4. **Preset default** — the autonomy preset's rule for the capability (§2.2).
5. **System default** — the last-resort default shipped with the build (almost always `deny` / `ask`).

The evaluator's `effective_mode(req)` walks this list top-down and returns the first match. The precedence path is recorded in the audit record (via `StageTrace`) so `policy.explain_decision` can render it.

### 6.4 Persona default mapping

Persona class (from `17_persona_pack_schema.md`) → default preset recommendation. This is a **recommendation** surfaced during onboarding (Step 5); the user always chooses:

| Persona class | Default preset recommendation |
|---|---|
| Cautious companion / first-time users | Observer |
| Balanced assistant (default) | Assistant |
| Productivity operator | Operator |
| Developer / builder | Power User |
| Custom / Isabelle privileged profile | Custom (with `privileged_profile = true` explicit audit tag) |

---

## 7. Grant ledger — data model

### 7.1 Record schema

```rust
pub struct Grant {
    pub grant_id: GrantId,                   // ULID
    pub capability: Capability,
    pub resource_scope: ResourceScope,
    pub approval_mode: ApprovalMode,
    pub duration: GrantDuration,             // Once | TaskScoped(TaskId) | Session | Persistent { ttl: Option<Duration> }
    pub issued_at_mono: MonotonicTimestamp,
    pub issued_at_wall: WallClockTimestamp,
    pub expires_at_mono: Option<MonotonicTimestamp>,
    pub issued_by: IssuedBy,                 // Preset | ExplicitPrompt { ticket_id } | PersonaDefault | EmergencyWaiver
    pub actor_persona: PersonaId,
    pub audit_ref: AuditId,
    pub revoked_at_mono: Option<MonotonicTimestamp>,
    pub revoked_reason: Option<RevokeReason>,
    pub preset_version_issued_under: u32,    // enables strip-on-preset-change
}
```

### 7.2 SQLite DDL

```sql
-- grants: mutable table (but mutation is strictly append-only for revocation; rows never deleted)
CREATE TABLE IF NOT EXISTS grants (
  grant_id                BLOB PRIMARY KEY,          -- 16 bytes ULID
  capability_id           TEXT NOT NULL,             -- dot-path, e.g. "files.read"
  capability_payload      BLOB,                      -- optional serde-bincode payload for parameterized caps
  resource_scope_kind     TEXT NOT NULL,             -- 'path' | 'url' | 'mailbox' | 'memory' | 'provider' | 'any' | 'none'
  resource_scope_value    TEXT NOT NULL,             -- canonicalized (glob / URL pattern / etc.)
  approval_mode           TEXT NOT NULL,             -- 'auto' | 'task' | 'ask' | 'draft' | 'deny'
  duration_kind           TEXT NOT NULL,             -- 'once' | 'task' | 'session' | 'persistent'
  duration_ttl_ms         INTEGER,                   -- nullable; only for persistent
  task_id                 BLOB,                      -- nullable; only for task-scoped
  issued_at_mono_ns       INTEGER NOT NULL,
  issued_at_wall_ms       INTEGER NOT NULL,
  expires_at_mono_ns      INTEGER,
  issued_by_kind          TEXT NOT NULL,
  issued_by_ref           TEXT,                      -- ticket_id / preset_id / persona_id
  actor_persona_id        BLOB NOT NULL,
  audit_ref               BLOB NOT NULL,             -- FK audit_log.audit_id
  revoked_at_mono_ns      INTEGER,
  revoked_reason          TEXT,
  preset_version          INTEGER NOT NULL
);

CREATE INDEX idx_grants_by_cap_actor        ON grants(capability_id, actor_persona_id, revoked_at_mono_ns);
CREATE INDEX idx_grants_by_task             ON grants(task_id);
CREATE INDEX idx_grants_by_expiry           ON grants(expires_at_mono_ns);
CREATE INDEX idx_grants_active              ON grants(revoked_at_mono_ns) WHERE revoked_at_mono_ns IS NULL;
CREATE INDEX idx_grants_by_persona          ON grants(actor_persona_id, revoked_at_mono_ns);
CREATE INDEX idx_grants_by_audit_ref        ON grants(audit_ref);
```

### 7.3 Canonical queries

- **Is this (capability, resource, persona) currently allowed?** → `SELECT 1 FROM grants WHERE capability_id = ? AND actor_persona_id = ? AND revoked_at_mono_ns IS NULL AND (expires_at_mono_ns IS NULL OR expires_at_mono_ns > ?) AND scope_covers(resource_scope_kind, resource_scope_value, ?)` — `scope_covers` is an application-side matcher (no SQL glob evaluation; SQL just narrows candidates).
- **All grants for trust center.** → `SELECT * FROM grants WHERE revoked_at_mono_ns IS NULL ORDER BY issued_at_mono_ns DESC`.
- **Task-end revoke.** On `task_end(task_id)`: `UPDATE grants SET revoked_at_mono_ns = ?, revoked_reason = 'task_end' WHERE task_id = ? AND revoked_at_mono_ns IS NULL`.
- **Emergency revoke all.** `UPDATE grants SET revoked_at_mono_ns = ?, revoked_reason = 'emergency' WHERE revoked_at_mono_ns IS NULL` — bounded by the 500 ms acceptance criterion; in-flight tool calls aborted via `emergency_revoke_all` event.

### 7.4 Relationship to audit log

- **Grants reference audit records, not the reverse.** `grants.audit_ref` points at the `audit_log.audit_id` row that recorded the issuing decision. The audit log is the source of truth; the grants table is a **materialized view** derived from the log (§8.3 replay).
- On replay from log, we deterministically reconstruct the grants table by iterating audit records and applying issue/revoke/expire operations.

### 7.5 Revocation semantics

- **Idempotent.** Revoking a grant that is already revoked is a no-op that still writes an audit record noting the attempt.
- **Cascading persona swap.** `L6` emits `persona_swap_begin` → L5 issues a batch revoke of all session-duration grants belonging to the swapping persona, with `revoked_reason = 'persona_swap'`. Only after the batch completes does L5 accept post-swap `action_request`s.
- **Preset change.** On `set_preset`, grants whose `preset_version_issued_under` capability rule is incompatible with the new matrix are revoked with `revoked_reason = 'preset_change'`. Compatible grants survive.
- **TTL.** A background tick scans `idx_grants_by_expiry` every 1 s (or on `now_monotonic` threshold crossings) and revokes expired grants with `revoked_reason = 'ttl_expired'`.

---

## 8. Audit log — append-only, tamper-evident

### 8.1 Record schema

```rust
pub struct AuditRecord {
    pub audit_id: AuditId,                       // ULID, monotonic within process
    pub timestamp_monotonic_ns: u64,
    pub timestamp_wall_ms: i64,
    pub actor: ActorRef,                         // engine / persona / user
    pub capability: Capability,
    pub resource: ResourceScope,
    pub decision: DecisionKind,
    pub reason: Option<StaticReasonId>,
    pub change_id: ChangeId,
    pub prev_hash: Hash32,                       // 32-byte SHA-256 of prior record's serialized form
    pub record_hmac: Hmac32,                     // HMAC-SHA256 over (prior chain root || this record fields) keyed by active HMAC key
    pub key_id: HmacKeyId,                       // allows rotation
    pub stage_trace: Vec<StageTrace>,            // for explain_decision
    pub seq: Seq,
}
```

### 8.2 SQLite DDL

```sql
CREATE TABLE IF NOT EXISTS audit_log (
  audit_id             BLOB PRIMARY KEY,               -- 16 bytes ULID (monotonic)
  timestamp_mono_ns    INTEGER NOT NULL,
  timestamp_wall_ms    INTEGER NOT NULL,
  actor_kind           TEXT NOT NULL,
  actor_ref            BLOB NOT NULL,
  capability_id        TEXT NOT NULL,
  capability_payload   BLOB,
  resource_scope_kind  TEXT NOT NULL,
  resource_scope_value TEXT NOT NULL,
  decision             TEXT NOT NULL,                  -- 'allow' | 'ask' | 'deny' | 'draft' | 'needs_upgrade'
  reason               TEXT,
  change_id            INTEGER NOT NULL,
  prev_hash            BLOB NOT NULL,                  -- 32 bytes
  record_hmac          BLOB NOT NULL,                  -- 32 bytes
  key_id               INTEGER NOT NULL,
  stage_trace          BLOB NOT NULL,                  -- serde-bincode
  seq                  INTEGER NOT NULL UNIQUE
);
CREATE INDEX idx_audit_by_mono ON audit_log(timestamp_mono_ns);
CREATE INDEX idx_audit_by_cap  ON audit_log(capability_id, timestamp_mono_ns);
CREATE INDEX idx_audit_by_actor ON audit_log(actor_kind, actor_ref);

-- checkpoint table: periodic chain-HMAC checkpoints signed by the keyring-held master key.
CREATE TABLE IF NOT EXISTS audit_checkpoints (
  checkpoint_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  up_to_audit_id  BLOB NOT NULL,
  chain_root_hash BLOB NOT NULL,                       -- 32 bytes
  checkpoint_hmac BLOB NOT NULL,
  key_id          INTEGER NOT NULL,
  created_at_ms   INTEGER NOT NULL
);
```

**No `UPDATE` statements are emitted against `audit_log` ever.** The only legal operations are `INSERT` and `SELECT`. A SQLite trigger enforces this at the DB layer:

```sql
CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log BEGIN
  SELECT RAISE(FAIL, 'audit_log is append-only');
END;
CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log BEGIN
  SELECT RAISE(FAIL, 'audit_log is append-only');
END;
```

### 8.3 Hash chain + HMAC rules

- Each record's `prev_hash` = SHA-256 of the previous record's canonical serialization (fields in fixed order, excluding `record_hmac` itself).
- `record_hmac` = HMAC-SHA256(key = active HMAC key, message = `prev_hash || serialize(fields minus record_hmac)`).
- Genesis record at install time has `prev_hash = 0x00..00` and a sentinel capability marker.
- **HMAC key handling** (high-level; detailed signing plan deferred to `X3 G3`):
  - Single per-install key stored in the OS keyring (Windows: Credential Manager via `keyring-rs`; macOS: Keychain; Linux: Secret Service).
  - Key rotation adds a new `HmacKeyId`; prior records retain their `key_id` so verification uses the key active at the time of the write. The rotation event itself is audited.
  - Key loss (user reinstalls OS without backup) → chain verification fails at boot → hard-blocking trust-center warning; user must acknowledge to continue, and a new genesis record is appended with a `"key_rotation_reset"` reason. This does **not** erase prior records; it just starts a new chain segment after an explicit acknowledgement audited with `privileged_profile = false`.
- **Checkpoints** every N records (default N = 1000) and every M seconds (default M = 3600). The checkpoint itself is HMAC'd and used for fast boot-time verification (verify latest checkpoint; spot-check a sample of records between checkpoints; full-scan weekly).

### 8.4 Replay semantics

Given `audit_log` + genesis state + the compiled preset matrix:

1. Iterate records in `seq` order.
2. For each `allow` with `issued_by` kind matching preset/explicit, insert a row into the reconstructed `grants` table.
3. For each `revoke` (distinguishable via `decision = 'revoke'` + `reason`), mark the matching grant row revoked.
4. For each `preset_change` record, re-apply the strip rules.
5. Final state = current grants table.

A property-based test (`§13`) asserts: for any audit-log prefix, the reconstructed ledger equals the live ledger after replaying those events.

### 8.5 Export policy

- **Local-canonical.** The audit log never leaves the machine by default.
- **Export command** (`trust.export_audit` — L7-owned, L5-services) is itself a capability: `MemoryExport`-adjacent, but named separately as `AuditExport` in the taxonomy (pending §14 decision). Default-denied; Custom-only enable + per-export ask + explicit destination path.
- Exported form is signed with the checkpoint HMAC so a recipient (e.g. a security researcher Don chooses to share with) can verify integrity against Don's shared checkpoint. The HMAC key itself is **not** exported.

### 8.6 Updater coordination

Per `X3 §6.2`, audit-log schema migrations are coordinated with the Tauri signed updater:
- Migrations are append-only additive (new columns with defaults); never drop columns.
- Schema version is in the updater manifest's `minimum-supported-version` gate.
- A migration that touches the chain must preserve hash continuity — we append a `"schema_migration"` sentinel record written by the old binary on shutdown, and the new binary verifies the chain from that sentinel.

---

## 9. BYOK hard-cap — enforcement path

Per `plans/03_content_lock_v1_port.md §4`, hard caps are an L5 capability boundary, not an L4 accounting vanity feature.

### 9.1 Data flow

1. **L4 emits `cost_event`** on every tool / model call: `{ provider: ProviderId, tokens_in: u32, tokens_out: u32, dollars: Cents, request_id: RequestId, timestamp_mono: MonotonicTimestamp }`.
2. **L5 subscribes** and maintains per-provider rolling counters (`daily`, `monthly`, `session`, `per_persona`).
3. Counters are written to a small **cost-counters** table (below), separate from the audit log because they mutate. (Counter state is also derivable from `cost_event`s — the table is a cache.)
4. On **threshold crossing**, L5 emits `cost_threshold_hit` and flips an in-memory deny-flag for that provider. The next `action_request` that would route through that provider returns `Decision::Deny { reason: CostCapHit(provider), ... }`.
5. The denial flag is **not** global: providers under the cap still work.

### 9.2 Threshold data model

```rust
pub struct CostThresholds {
    pub daily_usd_cents: HashMap<ProviderId, Cents>,       // wallet-per-day
    pub monthly_usd_cents: HashMap<ProviderId, Cents>,
    pub per_provider_hard_cap_cents: HashMap<ProviderId, Cents>,  // absolute, re-armable
    pub per_persona_daily_cents: HashMap<(PersonaId, ProviderId), Cents>,
    pub warn_at_pct: u8,                                   // emit soft warning at this % of cap
}
```

### 9.3 DDL

```sql
CREATE TABLE IF NOT EXISTS cost_counters (
  provider_id        TEXT NOT NULL,
  window_kind        TEXT NOT NULL,         -- 'daily' | 'monthly' | 'session' | 'per_persona'
  window_key         TEXT NOT NULL,         -- e.g. '2026-04-18' / '2026-04' / session-ulid / persona-ulid
  cents_spent        INTEGER NOT NULL DEFAULT 0,
  tokens_in          INTEGER NOT NULL DEFAULT 0,
  tokens_out         INTEGER NOT NULL DEFAULT 0,
  threshold_cents    INTEGER,
  threshold_hit_at   INTEGER,               -- nullable; set when exceeded
  re_armed_at        INTEGER,               -- nullable; audit-logged separately
  PRIMARY KEY (provider_id, window_kind, window_key)
);
```

### 9.4 Grace behavior

- **Hard cap** = deny immediately on the next request (default). Current in-flight request is **allowed to complete** if already dispatched, but its completion cost is charged and logged; no new requests are issued once the cap is hit.
- **Soft warn** at `warn_at_pct` (default 80%) emits a trust-center notification but does not deny.
- **Re-arm** is an explicit user action via `policy.reset_cost_counter` (requires re-auth; capability-gated). Re-arming is audit-logged with `reason = 'user_rearm'`.
- **Rollover**: daily counters reset at the user's local midnight per the system wall clock; monthly at 1st-of-month local. Rollover itself is audit-logged (zero-value record) so counters are reconstructable.

### 9.5 Interaction with evaluator

Cost cap evaluation lives in **Stage 0 (pre-evaluator gates)** of the state machine (§3.2). A cost-capped action is denied regardless of preset or persona. Denials are always audited (§8) so Don can see every blocked call.

---

## 10. Privacy-posture gate

### 10.1 Inputs

- **Persona privacy posture** — from L6's `CompiledPersona`: `PrivacyPosture { Strict | Balanced | Open }`. Strict is the default for cautious personas.
- **Provenance tags on memory hits** — from L2: tags include `public`, `session`, `durable`, `private`, `untrusted_input`, `scraped_content`, `extracted_preference`, etc.
- **Intended route** — from L4's `RouteHint`: `LocalOnly`, `LocalPreferred`, `RemoteEscalation { provider }`.

### 10.2 Rule

If **any** `private`-tagged (or persona-Strict-tagged) context appears in the prompt payload **and** the `intended_route` is `RemoteEscalation { provider }`, then `action_request` is denied with `PrivacyPostureViolation` unless the actor persona has an active `RouterAllowRemoteWithPrivate` grant **scoped to that provider**.

### 10.3 Evaluation order

Privacy-posture sits in **Stage 0 (pre-evaluator gates)** of the state machine (§3.2), immediately **after** hardcoded blocks and **before** the 5-layer evaluator proper. Rationale: a remote-route with private context is a contract violation, not a preset choice; no preset or persona overlay should be able to flip it except the explicit waiver capability.

### 10.4 Waiver

- `RouterAllowRemoteWithPrivate` is itself a High-risk capability (§2.2); it requires explicit approval, scoped to a specific `ProviderId`, and ideally task-scoped.
- Granting the waiver audits with `privileged_profile = false` and a distinct reason code so trust-center filtering can surface it.

---

## 11. Failure and degraded-mode behavior

### 11.1 Audit-log write failure

- **Effect:** deny-all until resolved. Every `evaluate` returns `Deny { reason: AuditWriteFailed }`.
- **User surface:** a hard-blocking banner in the trust center ("Aether is paused: cannot record actions. Check disk / keyring.") with Don-only dismissal after diagnostics.
- **Rationale:** `L5_plan §"Acceptance criteria"` — zero-bypass invariant requires every decision be logged; silent allow when we can't record is the exact failure mode we exist to prevent.
- **Recovery:** on next successful write, emit a recovery audit record with an explicit `"audit_recovery"` capability marker and resume normal evaluation.

### 11.2 Grant ledger corruption

- **Detection:** at boot, verify grants table against the latest audit checkpoint replay. Mismatch → `ledger.is_corrupt() = true`.
- **Effect (safe mode):** only the hardcoded-safe allowlist (read-only config reads, read-only trust-center queries) is allowed. Every other capability returns `Deny { reason: LedgerCorrupt }`.
- **User surface:** trust-center banner + guided "Rebuild ledger from audit log" action (which triggers replay).
- **Recovery:** user confirms rebuild → L5 replays the audit log in order → new ledger written → banner cleared (all audited).

### 11.3 Clock skew

- **Monotonic timestamps** are used for all TTL comparisons.
- **Wall-clock** is recorded alongside for UX display, never for invariants.
- On boot, detect suspicious wall-clock regression (> 60 s earlier than last boot's wall clock): log a `clock_skew_detected` audit record and flag the session; monotonic comparisons proceed normally.

### 11.4 L6 persona-compile failure

- **Effect:** fall back to the baked-in **"minimum-trust" persona** — a static `MinimumTrustPersona` shipped with the build that maps every capability to `deny` except the following tiny read-only set: `MemoryRead(session)`, `ClipboardRead`, `BrowserReadPage` within any currently granted URL pattern.
- **User surface:** trust-center banner explains "persona failed to compile; minimum-trust mode active"; Don can continue chatting in a degraded form.
- **Recovery:** on successful re-compile, a `persona_swap_commit` event triggers normal operation.

### 11.5 Catalog of degraded-mode entry points

| Trigger | DegradedMode | Allowed capabilities | Exit path |
|---|---|---|---|
| Audit-write fails | `AuditBroken` | None (deny-all) | Disk/keyring fix + retry |
| Ledger corrupt | `SafeMode` | Hardcoded-safe read-only set | User-confirmed rebuild from audit log |
| Persona compile fails | `MinimumTrust` | Tiny read-only set | Successful re-compile |

---

## 12. Interfaces for stubs (unblock L1 / L2 / L4 / L7)

Downstream layers can freeze their system designs against the shapes below. When L5 ships, these are the trait / event interfaces already implemented.

### 12.1 Rust trait — the single L5 entry point (for in-process Rust callers: L1, L2, L4)

```rust
pub trait PolicyEngine: Send + Sync {
    /// The only way for a Rust engine to request permission.
    fn evaluate(&self, req: ActionRequest) -> Result<Decision, PolicyEngineError>;

    /// Subscribe to a category of events.
    fn subscribe(&self, filter: EventFilter) -> EventStream<L5Event>;

    /// Emergency revoke (rarely called from Rust; usually from L7 command).
    fn emergency_revoke(&self, scope: EmergencyScope) -> Result<EmergencyReceipt, PolicyEngineError>;

    /// Typed snapshot of current grants (read-only).
    fn snapshot_grants(&self, filter: GrantFilter) -> Vec<Grant>;

    /// Enumerate capabilities — used by L4 to know what it may attempt.
    fn capabilities(&self, filter: CapabilityFilter) -> Vec<CapabilityInfo>;
}

#[derive(thiserror::Error, Debug)]
pub enum PolicyEngineError {
    #[error("degraded mode: {0:?}")] Degraded(DegradedMode),
    #[error("bus closed")] BusClosed,
    #[error("internal: {0}")] Internal(String),
}
```

Every in-process engine holds an `Arc<dyn PolicyEngine>` — they cannot call a tool, write memory, or route remotely without going through this trait. Static-analysis lint in CI (`tools/lint-policy-bypass/`) rejects direct executor calls (`L5_plan §"Key risks"` #1).

### 12.2 Event subscription shape

```rust
pub struct EventFilter {
    pub kinds: BitSet<L5EventKind>,        // e.g. only ActionRequest + PolicyDecision
    pub actors: Option<Vec<ActorRef>>,
    pub capabilities: Option<Vec<Capability>>,
    pub since_seq: Option<Seq>,            // for replay on reconnect
}
```

Each subscriber pins a `since_seq` and can request a backfill after reconnect (UI webview reload, etc.). The bus guarantees **at-least-once** delivery; handlers must be idempotent on `audit_id` / `grant_id` / `request_id`.

### 12.3 TS binding surface (`packages/l5-policy-ts/`)

Generated via `ts-rs` or `specta` (choice locked at X3 G1). Exports:

- `Capability`, `ResourceScope`, `ActionRequest`, `Decision`, `ApprovalTicket`, `Grant`, `L5Event` (all kinds), `PolicyIpcError`, `DegradedMode`.
- No logic — only types. L7 calls `invoke("policy.*", ...)` through the `shell-adapter` (Tauri + pywebview implementations per `X3 §9.3`); the bindings crate guarantees payload shape.

### 12.4 What each downstream stubs

| Consumer | Stub against | Acceptable fake |
|---|---|---|
| **L1** | `PolicyEngine::evaluate` for pre-tool-plan gate; subscribe to `PolicyDecision` / `ApprovalPending` for turn-state | Always-allow fake with a controllable delay to exercise the 800 ms stall-ack path |
| **L2** | `PolicyEngine::evaluate` for gated reads / writes; `ProvenanceTag` emit on memory hits | Always-allow fake; `MemoryWriteDurable` forced `task` for workflow testing |
| **L4** | `PolicyEngine::evaluate` for tool / remote-route gating; emits `cost_event`; subscribes to `cost_threshold_hit` | Fake evaluator that toggles cost-cap to exercise deny path |
| **L7** | Tauri commands in §5; subscribes to `approval_pending`, `grant_issued`, `grant_revoked`, `audit_record` (summary) | A scripted mock that emits a sequence of approval prompts to test UI |

Every stub is retired the day L5 lands; the contracts here are the freeze point.

---

## 13. Testing strategy (design-level)

### 13.1 Red-team attack surfaces to simulate (from `13 §"Red-team focus areas"`)

| Class | Simulation | Pass criterion |
|---|---|---|
| Prompt injection coercing tool use (`13 §1`) | Drive an action_request from a scraped-content-tainted context at Medium risk | DraftOnly or Deny; never Allow |
| Memory poisoning (`13 §2`) | Inject a low-confidence memory with `provenance_tags: [untrusted_input]`; request `MemoryWriteDurable` from it | Deny with taint reason; audit records the taint |
| Browser-to-forbidden-domain (`13 §3`) | `BrowserOpen { resource: finance-category URL }` under Assistant preset | Hardcoded block hit; denied pre-evaluator |
| File exfiltration (`13 §4`) | Read in-scope file then attempt `BrowserUpload` to out-of-scope URL in same task | `block.silent_upload` triggers; denied |
| Permission-bypass via chain (`13 §5`) | Compose low-risk actions whose joint effect is High-risk | Each call re-evaluated at its own risk class; High step asks (multi-step plan preview surfaces the chain at P2) |
| Destructive-action (`13 §6`) | `FilesDelete` bulk under Operator | Ask emitted; no auto-approve |
| Audit tampering (`13 §7`) | External SQL update on `audit_log` | Trigger blocks; chain verification fails if bypassed at FS level |
| Failure / recovery (`13 §8`) | Kill audit writer mid-session | Deny-all engaged; banner; recovery record on restart |
| Session-grant abuse | Persona swap with active session grants | All session grants for old persona revoked atomically before first post-swap evaluate |
| Silent capability escalation | Mid-task tier downgrade | Tier-stripped grants honored on next call; decision surfaces |

### 13.2 Property-based tests for the evaluator

- **Monotonicity under preset upgrade.** Upgrading preset (Observer → Assistant → Operator → Power User) never turns a previously-denied safe action into something less safe; any new allows are strictly in the widened category.
- **Revocation idempotency.** Revoking a grant N times leaves the grants table in the same state as revoking it once; each call beyond the first logs but is a no-op.
- **Audit-chain integrity.** For any sequence of inserts, chain verification of the final log succeeds; tampering with any single record or omitting any record causes verification to fail with a specific `TamperedAt(audit_id)` output.
- **Grant-ledger = log replay.** For any prefix of the audit log, replaying it deterministically reconstructs the grants table that was live at that prefix.
- **Deny-all under audit failure.** For any `ActionRequest` while `audit.healthy == false`, `evaluate` returns `Deny { AuditWriteFailed }`.

### 13.3 Replay tests

- Given a saved audit log from a session, replay it with an empty grants table and assert the resulting state matches the recorded `grants_snapshot` at session end.
- Replay across a simulated `schema_migration` sentinel record to prove the new-schema replay handles mixed-chain segments.

### 13.4 Performance tests (tie to `L5_plan §"Acceptance criteria"`)

- `p95(action_request → policy_decision)` ≤ 10 ms for auto-decisions.
- `p95(action_request → approval_pending rendered)` ≤ 150 ms.
- `emergency_revoke_all` completes ≤ 500 ms with ≥ 10 000 active grants.
- Preset-switch revokes incompatible grants ≤ 100 ms.

---

## 14. Open questions surfaced by design

Each item: **Question** — why it matters — proposed default — impact if defaulted silently.

1. **`§9.4` in `12_permissions_autonomy.md` does not exist.** The prompt references a `§9.4` capability enumeration that I cannot find in `12`. The doc instead enumerates capabilities under `"Capability groups"` (sections Files / Browser / Email / etc.). This taxonomy treats the top-level groups as the canonical enumeration.
   - **Why it matters:** the self-review checklist asks whether "every capability in `§9.4`" appears in §2. If §9.4 is a planned-but-unwritten section in `12`, the table in §2 is complete against the current doc but may need expansion later.
   - **Proposed default:** treat `12 §"Capability groups"` as authoritative; any future `§9.4` additions flow in via an amendment to this document.
   - **Impact if defaulted silently:** a late-added capability could ship without a default-mode row in §2.2 — a trust gap.

2. **HMAC key rotation policy for the audit log.** Single per-install key vs rotation on major version vs user-initiated rotation?
   - **Why it matters:** determines whether the rotation event is a deployment concern (updater) or a user concern (settings UX).
   - **Proposed default:** single per-install key in OS keyring; rotate on major version bump; user-initiated rotation possible from Custom preset with re-auth. Rotation is always audited and preserves historical `key_id`.
   - **Impact if defaulted silently:** if forgotten, a stolen HMAC key could be used forever to forge chain-valid records.

3. **Whether P0 ships the hash-chain + HMAC, or only at P1.** (`L5_plan §"Open decisions for executing agent"`.)
   - **Why it matters:** P0 scope vs trust story. Skipping the chain in P0 weakens the OSS Preview trust pitch but speeds delivery.
   - **Proposed default:** ship the chain in P0 (acceptance criterion "every decision recorded" requires integrity to be meaningful); checkpoint signing can defer to P1.
   - **Impact if defaulted silently:** OSS Preview audits become tamper-prone; a red-team demo writes a one-line SQL UPDATE to alter history.

4. **Exact TTL defaults** for `TaskScoped` and `Session` grants. (`L5_plan §"Open decisions"`.)
   - **Why it matters:** too-short TTLs cause approval fatigue; too-long TTLs widen trust surface.
   - **Proposed default:** `Task = until task-end event OR 30 minutes without a heartbeat`; `Session = process lifetime OR 12 hours, whichever first`.
   - **Impact if defaulted silently:** inconsistent behavior across engines (task grants surviving the task).

5. **BYOK cost-cap re-arm UX flow.** Does re-arming require re-auth, a typed confirmation ("type RE-ARM"), or a simple click?
   - **Why it matters:** a clicked re-arm is the exact failure mode that makes hard-caps soft.
   - **Proposed default:** re-auth + typed confirmation + audited. Re-arming within 1 hour of a hit requires double re-auth.
   - **Impact if defaulted silently:** users rubber-stamp a re-arm when they hit the cap and lose the trust surface.

6. **Audit export capability identifier.** Is `MemoryExport` the same as `AuditExport`, or is it a distinct capability?
   - **Why it matters:** they have different resource-scope shapes (memory vs. audit log) and different risk framings.
   - **Proposed default:** distinct capability `AuditExport`; Critical risk class (never auto-allow). Add it to §2.2 in a follow-up pass.
   - **Impact if defaulted silently:** conflating them means granting `MemoryExport` accidentally includes audit-log export — a red-team finding.

7. **`§10.3` reference in `13_trust_security_redteam.md` does not exist.** The prompt cites `13 §10.3` as "non-negotiable blocks". The nearest canonical source is `12 §"Non-negotiable blocks (hardcoded platform rules)"` plus `13 §3, §4, §5, §6`. This doc treats those as the source.
   - **Why it matters:** same as §14.1 — we may be missing a red-team block class.
   - **Proposed default:** use `12 §"Non-negotiable"` + `13 §3–§6` as canonical; flag for Don.
   - **Impact if defaulted silently:** a future `13 §10.3` red-team case arrives without a matching hardcoded block row.

8. **Plan-level `policy_preview`: P1 or P2?** (`L5_plan §"Open decisions"`.)
   - **Why it matters:** depends on L7's UX for chain approval, which needs the preview command to exist.
   - **Proposed default:** P2 — UX review first; stub the command surface in P0 but return `NotImplemented`.
   - **Impact if defaulted silently:** multi-step chains at Operator+ get per-step asks → approval fatigue.

9. **`policy_preview` dry-run and audit logging.** Should plan previews write to the audit log, or be dry-run only?
   - **Why it matters:** dry-run keeps the log clean; audited previews let red-teams inspect what the engine considered.
   - **Proposed default:** dry-run for interactive previews; a one-line `plan_preview` audit record (without per-step entries) on actual plan commit. Each per-step evaluation is audited normally when executed.
   - **Impact if defaulted silently:** log bloat or blind spot.

10. **Isabelle privileged profile mechanics.** `L5_plan §"Key risks"` #7 mentions a `privileged_profile` flag. Is it (a) a persona property, (b) a preset, (c) a separate `PrivilegedProfileId` stored in the ledger, or (d) a build flag?
    - **Why it matters:** determines whether Isabelle's overlay is a persona variant or a distinct code path.
    - **Proposed default:** it is a **persona property** compiled into `CompiledPersona` by L6; L5 mirrors it as an `actor_persona.privileged_profile: bool` field surfaced in every audit record. No distinct code path.
    - **Impact if defaulted silently:** Isabelle overlay quietly uses a parallel evaluator → cross-product drift (`L5_plan §"Key risks"` #7).

11. **Doctrine conflict flagged (but not resolved here):** `01_product_doctrine.md §"Must-own layers"` enumerates **8** layers; `plans/00_ORCHESTRATION_MAP.md §1` reconciles to **7** layers (reflex folded into L1). Doctrine has not yet been updated to reflect the 7-layer split.
    - **Why it matters:** an implementer reading only `01` would expect a reflex-router package distinct from L1.
    - **Proposed default:** this document uses the 7-layer model per `00_ORCHESTRATION_MAP §1` (canonical working truth). Doctrine update is pending per Don's §9 "Human decision gates" list.
    - **Impact if defaulted silently:** drift.

12. **`RouterAllowRemoteWithPrivate` capability shape.** Is the waiver a per-provider grant (proposed) or a global waiver?
    - **Why it matters:** a global waiver collapses the privacy posture; a per-provider waiver is the safer surface.
    - **Proposed default:** per-provider + task-scoped.
    - **Impact if defaulted silently:** a global waiver is a single-point trust failure.

13. **`X3 G2 / G3 / G4` dependency.** L5 assumes `tauri-plugin-store` for the cost-counters cache and `tauri-plugin-single-instance` for DB ownership. These are G2-pending.
    - **Why it matters:** if G2 rejects either plugin, L5 needs an in-crate alternative.
    - **Proposed default:** design for both (abstract the counter store behind a trait) so G2 can swap.
    - **Impact if defaulted silently:** G2 rejection forces a late redesign.

---

## Self-review checklist

- [x] Every capability in `12_permissions_autonomy.md §"Capability groups"` appears in §2's table. (`§9.4` specifically is flagged as non-existent in §14.1.)
- [x] Every event in `plans/L5_policy_engine.md` "Owns" bullet appears in §4 with typed fields: `action_request`, `policy_decision`, `approval_pending`, `grant_issued`, `grant_revoked`, `audit_record`. Added: `approval_response` (§4 as a command), `emergency_revoke_all`, `cost_threshold_hit`.
- [x] Every command in `plans/X3_tauri_architecture.md §2.2` "L5" appears in §5 with typed request/response: `policy.evaluate`, `policy.request_approval`, `policy.set_preset`, `policy.list_grants`. Additional proposed commands: `policy.respond_approval`, `policy.get_preset`, `policy.revoke`, `policy.list_capabilities`, `policy.explain_decision`, `policy.preview_plan`, `policy.emergency_revoke_all`, `policy.get_audit_summary`, `policy.stream_audit`.
- [x] Every non-negotiable block from `13_trust_security_redteam.md` §"Red-team focus areas" (#3 Browser, #4 Exfil, #5 Bypass, #6 Harmful) is either addressed in §2.3 / §10 / §13.1 or flagged in §14 (§14.7 flags the missing `§10.3` citation).
- [x] §12 gives L1 / L2 / L4 / L7 enough to stub against: a single `PolicyEngine` trait, a typed event subscription shape, a TS bindings surface, and a per-consumer stub table.
- [x] Open questions in §14 do not silently resolve doctrine conflicts. §14.11 explicitly flags the 7-vs-8-layer unresolved doctrine state and defers to Don.

---

## Closing notes

- **Contracts frozen in this document:** §4 event types, §5 command surface, §7 grant record, §8 audit record, §12 `PolicyEngine` trait + `EventFilter`. Downstream layers (L1 / L2 / L4 / L7) can start their own system-design work today.
- **Canonical package home** (X1-dependent): file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/ (Rust) + file:///C:/Users/dbhav/Projects/aether/packages/l5-policy-ts/ (typed bindings).
- **Immediately adjacent layer to design next:** L6 persona compiler — L5 consumes `CompiledPersona` (§6.3 precedence, §10 privacy posture, §11.4 minimum-trust fallback) and the contract isn't frozen yet. L1 reflex is the other candidate, because it is the first consumer of `policy_decision` in the turn loop.
