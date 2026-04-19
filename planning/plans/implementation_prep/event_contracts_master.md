---
status: draft
date: 2026-04-18
layer: cross-layer (L1–L7 + core.health + Media)
kind: implementation_prep / master event contract reference
primary_sources:
  - plans/implementation_prep/L1_interface_pack.md
  - plans/implementation_prep/L2_interface_pack.md
  - plans/implementation_prep/L3_interface_pack.md
  - plans/implementation_prep/L4_interface_pack.md
  - plans/implementation_prep/L5_interface_pack.md
  - plans/implementation_prep/L6_interface_pack.md
  - plans/implementation_prep/L7_interface_pack.md
  - plans/L5_policy_engine_system_design.md §4
  - plans/L1_interaction_timing_system_design.md §5
  - plans/L4_model_router_system_design.md §11
  - plans/L2_memory_kernel_system_design.md §9
  - plans/L3_presence_engine_system_design.md §8
  - plans/L6_persona_compiler_system_design.md
  - plans/X3_tauri_architecture.md §3
  - plans/L1_L4_L5_L7_integration_notes.md
  - plans/L2_L3_L6_integration_notes.md
non_goals:
  - No code. No .rs / .ts files.
  - No modifications to other plan files.
  - Does not resolve silently-drifting semantics; flags them.
---

# Aether — Master Event Contracts (cross-layer)

> Canonical cross-layer reference for every typed event that crosses an Aether
> layer boundary. This file is the single source of truth for event names,
> producers, consumers, synchronicity, projection status, payload field sets,
> versioning, and invariants.
>
> Planning root: file:///C:/Users/dbhav/Projects/aether-planning/
> Companion docs:
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/X3_tauri_architecture.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_L4_L5_L7_integration_notes.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_L3_L6_integration_notes.md

---

## 1. Purpose

This document is the **single source of truth for every typed event crossing
an Aether layer boundary**. It consolidates the event surfaces of L1
(interaction timing), L2 (memory kernel), L3 (presence engine), L4 (model
router), L5 (policy/authorization), L6 (persona compiler), L7 (trust UX),
plus shared core.health and media signals, into one canonical catalog with
producer/consumer mappings, sync/async boundaries, projection (Rust-internal
vs Tauri-bridge-to-webview) flags, typed payload field sets, version rules,
invariants, name-variant reconciliation, and open questions. Any layer
implementer MUST cite this document's event names verbatim; any divergence
either updates this file (with a version bump) or is rejected in review.

---

## 2. Event design principles

1. **Stable names — snake_case, present-tense verbs** (`turn_begin`,
   `policy_decision`, `memory_hit`). Never past tense (no `_ed`/`_completed`
   suffix unless semantically the event marks a completion distinct from a
   corresponding `_started`). Pair `_started` / `_completed` explicitly where
   both edges are observable (e.g. `tool_call_started` / `tool_call_completed`,
   `behavior_started` / `behavior_completed`, `repair_started` /
   `repair_resolved`).

2. **Typed payloads — Rust canonical, TS via `ts-rs`/`specta`.** The Rust
   event-bus enum (`L1Event | L2Event | L3Event | L4Event | L5Event | L6Event
   | CoreEvent`) is authoritative. TS bindings are generated, never
   hand-authored. A schema change in Rust forces a regeneration of the TS
   type file (CI gate).

3. **Projection flag — Rust-internal vs Tauri-bridged to webview.** Per X3
   §3.2, projection is *declared in Rust*; the webview subscribes to an
   allowlisted channel set. High-frequency events (e.g. `viseme_tick`,
   per-frame `avatar_frame_ready`) stay Rust-internal or go on a coalesced
   low-freq projection. Every row in the catalog below has a `Projected`
   column: `yes` / `no` / `yes-coalesced` / `summary` / `on-demand`.

4. **`change_id` correlation.** Every event in a causal chain carries the
   same `change_id` (ULID or UUID) so L5's audit record, L1's
   `turn_state_change`, L4's `route_decision`, and L7's UI row all tie back
   to the same user-visible action. Introduced at the point of first intent
   (typically L1's reflex classification or L7's command invocation).

5. **`seq` for drop detection.** Every event carries a single global
   monotonic `seq: u64` produced by the event bus (`AtomicU64`). Subscribers
   track per-channel high-water-mark `seq` and use `subscribe(...,
   { replayLastN })` or `{ cursor }` to recover from gaps. The UI shell
   adapter is explicitly required to detect drops and trigger replay (L7
   §7.1).

6. **`source_layer` for audit.** Every event carries a `source_layer:
   SourceLayer` tag (`L1 | L2 | L3 | L4 | L5 | L6 | L7 | Media | Core`). L5's
   audit chain uses this; L7 filters by it; cross-layer invariant checks
   assert on it.

7. **Idempotency per event family.**
   - `policy_decision`: idempotent on `audit_id`.
   - `grant_issued` / `grant_revoked`: idempotent on `grant_id` (revoke-once;
     second revoke is a logged no-op).
   - `approval_pending` / `approval_response`: idempotent on `ticket_id`
     (one-shot).
   - `memory_write_confirmed` / `memory_edit_confirmed` /
     `memory_delete_committed`: idempotent on `(item_id, version)`.
   - `turn_begin` / `turn_end`: idempotent on `turn_id` (both edges
     at-most-once per turn).
   - `cost_event`: at-least-once; idempotent on `(request_id, provider,
     timestamp_mono)`.
   - `audit_record`: append-only hash-chained; `prev_hash` + HMAC validate
     continuity. Never updated, never deleted.
   - `persona_swap_commit`: idempotent on `change_id`.
   - `emergency_revoke_all`: single in-flight; concurrent calls coalesce.
   - `compiled_persona_ready`: idempotent on `(persona_id, version,
     change_id)`.
   - Burst-class events (`partial_transcript`, `viseme_tick`,
     `avatar_frame_ready`): not idempotent — subscribers dedupe by their own
     rules (latest-wins or time-window).

8. **Envelope shape.** Every bus event, projected or not, carries the
   envelope:

   ```text
   Event {
     source_layer: SourceLayer,
     seq:          u64,
     change_id:    ChangeId,
     turn_id:      Option<TurnId>,   // present for turn-scoped events
     version:      SchemaVersion,    // (major, minor) — see §5
     emitted_at:   MonotonicTimestamp,
     payload:      <event-specific>,
   }
   ```

---

## 3. Master event catalog

Columns: **Event** | **Producer** | **Consumers** | **Sync/Async** |
**Projected to UI** | **Purpose** | **Version**.

Abbreviations in Consumers: `*` = all layers; `audit` = L5 audit writer;
`media` = media engine (TTS/STT/VAD).

### 3.1 L1 — Interaction Timing + Reflex Router

| Event | Producer | Consumers | Sync/Async | Projected to UI | Purpose | Version |
|---|---|---|---|---|---|---|
| `turn_begin` | L1 | L2, L3, L4, L5, L7, audit | async (emit-after-commit) | yes | First event of every turn; opens the causal chain | 1.0 |
| `turn_end` | L1 | L2, L3, L4, L5, L7, audit | async | yes | Final event of every turn; carries `TurnOutcome` | 1.0 |
| `partial_transcript` | L1 (re-emit from media) | L2, L4, L7 | async, high-freq | yes-coalesced (Lite debounced) | Streaming ASR partial text with stability score | 1.0 |
| `intent_hint` | L1 | L4, L7 | async, low-freq | yes | Classifier's coarse intent class for early L4 priming | 1.0 — **open emitter contradiction, §7** |
| `route_hint` | L1 | L4 | sync-fire (followed by async response) | no (internal) | Seed structure for L4's route decision | 1.0 |
| `ack_phrase` | L1 | media (TTS), L3, L7 | async | yes | Selected ack phrase for TTS enqueue + UI chrome | 1.0 |
| `turn_state_change` | L1 | L3 (primary), L7, L5 (audit) | async | yes | Transition between the 19 TurnStates | 1.0 |
| `reflex_classification` | L1 | L4, L7 (trust/debug) | async | yes | Which ReflexCategory fired; rationale tag | 1.0 |
| `action_request` | L1 (also L2, L4, media) | L5 | sync (L5 evaluates) | no (never raw) | Authorization request envelope; precedes every side-effect | 1.0 |
| `memory_query` | L1 | L2 | async, deadline-bound | no | Outbound query for memory context | 1.0 |
| `repair_started` | L1 | * | async | yes | Entered Repairing state; carries RepairCause | 1.0 |
| `repair_resolved` | L1 | * | async | yes | Repair resolved; carries RepairResolution | 1.0 |
| `barge_in_detected` | L1 | media (TTS), L3, L4, L7 | async, fast path | yes | User spoke over TTS/stream; cut signal | 1.0 |
| `tier_downgrade_notice` | L1 (forwarded from core) | * | async | yes | Tier switch affecting tick rate + phrase pool | 1.0 |

### 3.2 L2 — Memory Kernel

| Event | Producer | Consumers | Sync/Async | Projected to UI | Purpose | Version |
|---|---|---|---|---|---|---|
| `memory_hit` | L2 | L1, L4, L6, L7 | async, deadline-bound | yes | Per-hit retrieval result with `privacy_class`, score, provenance | 1.0 |
| `memory_query_empty` | L2 | L1 | async, deadline-bound | no | Empty-result completion signal for a `memory_query` | 1.0 |
| `memory_write_confirmed` | L2 | L5 (audit), L7 | async (ingestion commit) | yes | Write committed to persistent store | 1.0 |
| `memory_edit_confirmed` | L2 | L7 | async | yes | Edit committed; carries `version_before` / `version_after` | 1.0 |
| `memory_delete_pending` | L2 | L7, L5 audit | async (phase 1) | yes | Soft-delete accepted; grace window open | 1.0 |
| `memory_delete_committed` | L2 | L7, L5 audit | async (phase 2) | yes | Hard tombstone after grace or forced | 1.0 |
| `memory_retention_expired` | L2 | L5 audit | async (sweep) | summary | Retention policy triggered deletion | 1.0 |
| `provenance_update` | L2 | L5, L7 | async | on-demand | Extended provenance chain for an item | 1.0 |
| `memory_export_completed` | L2 | L7 | async | yes | Export finalized; carries URI | 1.0 |
| `memory_index_rebuild_started` | L2 | L1, L7 | async | summary | Vector index rebuild began; degraded-mode hinting | 1.0 |
| `memory_index_rebuild_completed` | L2 | L1, L7 | async | summary | Rebuild finished; stats included | 1.0 |
| `ingestion_candidate_rejected` | L2 | L5 audit | async | no | Candidate dropped (dedup / policy deny) | 1.0 |
| `ingestion_candidate_accepted` | L2 | L5 audit | async | no | **Proposed new** — paired with rejected for audit symmetry (see §7) | 0.1-proposed |

### 3.3 L3 — Presence Engine

| Event | Producer | Consumers | Sync/Async | Projected to UI | Purpose | Version |
|---|---|---|---|---|---|---|
| `presence_state` | L3 | L7 (low-freq) | async (on state change) | yes-coalesced | Current behavior class + intensity + tier + posture | 1.0 |
| `avatar_frame_ready` | L3 | rendering-surface, observers | async, per-frame | no | Frame pushed to surface (non-load-bearing observer) | 1.0 |
| `behavior_started` | L3 | L7 | async | summary | A BehaviorClass began playing | 1.0 |
| `behavior_cancelled` | L3 | L7 | async | summary | BehaviorClass cancelled mid-play | 1.0 |
| `behavior_completed` | L3 | L7 | async | summary | BehaviorClass finished cleanly | 1.0 |
| `anti_uncanny_correction_applied` | L3 | L7 (debug), audit | async | on-demand | Stabilizer clipped an intensity/field | 1.0 |
| `tier_downgrade_presence` | L3 | L7, core.health | async | yes | Presence-scoped tier downgrade (e.g. viseme desync) | 1.0 |
| `rendering_surface_error` | L3 | L7, core.health | async | yes | Surface crash / unrecoverable error | 1.0 |

### 3.4 L4 — Model Router

| Event | Producer | Consumers | Sync/Async | Projected to UI | Purpose | Version |
|---|---|---|---|---|---|---|
| `route_decision` | L4 | L1 (primary), L7 | sync-return + async projection | yes (summary) | Authoritative route selection; includes fallback chain | 1.0 |
| `escalation_reason` | L4 | L7 (trust center) | async | yes | Standalone `EscalationReason` event for UI explainers | 1.0 |
| `cost_event` | L4 | L5 (authoritative counter), L7 (wallet) | async, at-completion | yes (Lite coalesced) | Per-call cost emitted post-completion; never streaming | 1.0 |
| `tool_call_started` | L4 | L5 (audit), L7 (timeline) | async | yes | Start marker for a single tool step; correlates by `change_id` | 1.0 |
| `tool_call_completed` | L4 | L5, L7, L1 | async | yes | End marker; carries `ToolResult` variant | 1.0 |
| `provider_health` | L4 | L7 (health pane), L4 self | async, coalesced | summary | Rolling p95 + last-failure-reason per provider | 1.0 |
| `byok_credential_added` | L4 | L5 (audit), L7 (wallet) | async | yes | BYOK key added; metadata only (fingerprint, never key material) | 1.0 |
| `byok_credential_rotated` | L4 | L5, L7 | async | yes | Key rotated; old + new fingerprint | 1.0 |
| `byok_credential_removed` | L4 | L5, L7 | async | yes | Key removed | 1.0 |
| `fallback_triggered` | L4 | L7 (debug), L5 (audit) | async | yes | Fallback chain traversal; `from → to`, `reason` | 1.0 |
| `tier_preference_change` | L4 | L7, L6 (may recompile) | async | yes | core.health-driven tier shift affecting routing | 1.0 |

### 3.5 L5 — Policy / Authorization Engine

| Event | Producer | Consumers | Sync/Async | Projected to UI | Purpose | Version |
|---|---|---|---|---|---|---|
| `policy_decision` | L5 | L1, L2, L4, L7 | sync-committed (audit first) | yes (summary) | Authoritative `Decision` for every `action_request` | 1.0 |
| `approval_pending` | L5 | L1, L7 | sync-issue + async wait | yes | Ticket issued for user approval | 1.0 |
| `approval_response` | L5 (projection of L7 input) | L1, L7 | sync | yes | User's response echo projection | 1.0 |
| `grant_issued` | L5 | L1, L4, L7 | sync | yes | Allow decision produced a grant | 1.0 |
| `grant_revoked` | L5 | L1, L4, L7 | sync | yes | Grant invalidated (TTL / user / persona-swap / emergency) | 1.0 |
| `audit_record` | L5 | L7 (trust center), storage | sync-committed (mandatory) | summary (full on-demand) | Append-only hash-chained record with HMAC | 1.0 |
| `emergency_revoke_all` | L5 | L1, L2, L4, L7 | sync, ≤500 ms budget | yes | Big-red-button; cancels all in-flight side effects | 1.0 |
| `cost_threshold_hit` | L5 | L4 (deny-flag), L7 (banner) | async | yes | Provider counter crossed configured threshold | 1.0 |
| `policy_posture_changed` | L5 | L1, L4, L7 | async | yes | Preset switch, persona swap, degraded-mode entry/exit | 1.0 |

### 3.6 L6 — Persona Compiler

| Event | Producer | Consumers | Sync/Async | Projected to UI | Purpose | Version |
|---|---|---|---|---|---|---|
| `compiled_persona_ready` | L6 | L1, L2, L3, L4, L5, L7 | async (two-phase) | yes | Bundled six sub-artifacts ready for consumption | 1.0 |
| `persona_swap_begin` | L6 | L1, L2, L3, L4, L5, L7 | async, gated on L1 safe-boundary ack | yes | First half of two-phase hot-swap | 1.0 |
| `persona_swap_commit` | L6 | L1, L2, L3, L4, L5, L7 | sync-at-boundary | yes | Commit on L1 safe boundary; new persona is ACTIVE | 1.0 |
| `persona_swap_rollback` | L6 | L1, L2, L3, L4, L5, L7 | async (on NACK/timeout) | yes | Swap aborted; previous persona stays ACTIVE | 1.0 |
| `persona_compile_failed` | L6 | L7 (banner), L5 (audit) | async | yes | Compile failed; carries `PersonaError`-projected reason | 1.0 |
| `persona_observed_style_proposed` | L6 | L7 (confirmation UI), L5 (audit) | async | yes | Observed-style change proposed; requires explicit user confirm (I-8) | 1.0 |

### 3.7 Core / health

| Event | Producer | Consumers | Sync/Async | Projected to UI | Purpose | Version |
|---|---|---|---|---|---|---|
| `core.health.tier_change` | Core | L1, L3, L4, L6, L7 | async | yes | Tier moved between `Lite | Balanced | Full` (or Minimal for L3) | 1.0 |
| `core.health.degraded_subsystem` | Core | L1, L7 | async | yes | A subsystem reported degraded health | 1.0 |
| `core.health.reconnect` | Core | L7, all | async | yes | Subsystem/network came back online | 1.0 |
| `core.suspend_resume_detected` | Core | L1, L7 | async | yes | OS suspend/resume crossed threshold (>10 s) | 1.0 |
| `degraded_mode_entered` | L5 (primary), L1/L4 (self-mode) | L7 (banner), all | async | yes | **Proposed new** — entering SafeMode/AuditBroken/LedgerCorrupt/MinimumTrust/DegradedNoPolicy/etc.; consumed by L7 for banner (see §7) | 0.1-proposed |
| `degraded_mode_cleared` | L5 (primary), L1/L4 (self-mode) | L7 (banner), all | async | yes | **Proposed new** — exiting degraded mode; banner dismiss | 0.1-proposed |

### 3.8 Media engine (bus-projected subset)

Included for completeness; these are *inbound to L1* and *inbound to L3*,
but they cross the layer boundary so they belong in this catalog.

| Event | Producer | Consumers | Sync/Async | Projected to UI | Purpose | Version |
|---|---|---|---|---|---|---|
| `vad.speech_start` | Media | L1 | async, fast | no | VAD detected speech onset | 1.0 |
| `vad.speech_end` | Media | L1, L3 | async | no | VAD detected speech offset + tail silence | 1.0 |
| `final_transcript` | Media | L1, L2, L4 | async | yes (via L1 re-emit) | Endpointed ASR result | 1.0 |
| `tts_chunk_done` | Media | L1 | async, high-freq | no | TTS chunk finished playing | 1.0 |
| `tts_eos` | Media | L1 | async | no | TTS end-of-stream | 1.0 |
| `tts_stall` | Media | L1 | async | no | TTS stalled past watchdog | 1.0 |
| `viseme_tick` | Media | L3 (primary), L1 (re-emit opt) | async, high-freq (60 Hz+) | no (dedicated coalesced channel on Lite) | Viseme weight tick for lip-sync | 1.0 |

**Total rows:** 14 (L1) + 13 (L2, incl. 1 proposed) + 8 (L3) + 11 (L4) + 9
(L5) + 6 (L6) + 6 (Core, incl. 2 proposed) + 7 (Media) = **74 events.**

---

## 4. Payload drafts

Field-level pseudotype blocks for each major event family. Every payload
inherits the envelope from §2.8 (`source_layer`, `seq`, `change_id`,
optional `turn_id`, `version`, `emitted_at`). Fields shown here are the
payload body only.

### 4.1 L5 events

#### `action_request`
```text
required:
  request_id:    RequestId     // ULID, process-unique
  turn_id:       TurnId
  capability:    Capability    // typed dot-path enum — never stringly
  resource:      ResourceScope // typed variant matching capability family
  actor_persona: PersonaId
  emitted_at:    MonotonicTimestamp
optional:
  task_id:             Option<TaskId>
  provenance_tags:     Vec<ProvenanceTag>
  intended_route:      Option<RouteHint>   // LocalOnly | LocalPreferred | RemoteEscalation { provider }
  risk_class_hint:     Option<RiskClass>
  active_grants:       Snapshot<GrantLedger>
semantics:
  Idempotent on request_id. Duplicate request_id is a logged drop.
  Missing provenance_tags → treated as `untrusted_input`.
order:
  Must precede its matching `policy_decision` in seq order within a turn.
```

#### `policy_decision`
```text
required:
  request_id:  RequestId
  decision:    Decision        // Allow | Ask | DraftOnly | Deny | NeedsUpgrade
  audit_id:    AuditId
  change_id:   ChangeId
  seq:         u64
optional:
  reason:             Option<StaticReason>
  effective_mode:     Option<ApprovalMode>
  precedence_source:  Option<PrecedenceSource>
idempotency:
  Idempotent on audit_id. Replay-safe.
ordering:
  Must follow its `action_request` in strict seq order.
invariant:
  If audit write fails, `Decision::Allow` MUST NOT be emitted; evaluator
  returns `Deny { AuditWriteFailed }` instead.
```

#### `approval_pending`
```text
required:
  ticket_id:   ApprovalTicketId
  request_id:  RequestId
  capability:  Capability
  resource:    ResourceScope
  risk_class:  RiskClass
  explanation: StaticCopyId
  change_id:   ChangeId
  seq:         u64
optional:
  deadline_hint:     Option<MonotonicTimestamp>
  suggested_duration: Option<GrantDuration>
  bundle_hint:       Option<BundleId>         // plan-preview P2
idempotency:
  One-shot per ticket_id. Deadline expiry emits `grant_revoked { reason:
  approval_timeout }`, not a synthetic decision.
ordering:
  Follows `policy_decision { decision: Ask }` with matching request_id.
```

#### `approval_response`
```text
required:
  ticket_id:    ApprovalTicketId
  user_choice:  UserChoice     // Allow | AllowScope(scope) | AllowTask | AllowSession | Deny
  responded_at: MonotonicTimestamp
optional:
  scope_override:     Option<ResourceScope>
  duration_override:  Option<GrantDuration>
  reauth_token:       Option<CommandToken>    // required for High/Critical
  prefer_draft:       Option<bool>            // UI hint only — see §7 Q3
semantics:
  One-shot per ticket_id. Double-response → `Conflict`.
  Ticket revoked mid-ask → `Conflict(ticket_stale_grant_revoked)`.
transport:
  Crosses only as a Tauri command from L7; NEVER raw from the webview onto
  the Rust event bus.
```

#### `grant_issued`
```text
required:
  grant_id:       GrantId
  capability:     Capability
  resource_scope: ResourceScope
  approval_mode:  ApprovalMode
  duration:       GrantDuration   // Once | TaskScoped | Session | Persistent { ttl }
  issued_at:      MonotonicTimestamp
  issued_by:      ActorRef
  audit_ref:      AuditId
  change_id:      ChangeId
  seq:            u64
optional:
  expires_at:                 Option<MonotonicTimestamp>
  task_id:                    Option<TaskId>
  preset_version_issued_under: u32
invariant:
  Follows `policy_decision { Allow }` with matching audit root.
  grant_id unique.
  Emission failure → the Allow is rolled back; evaluator returns Deny
  { Internal } and writes a corrective audit record.
```

#### `grant_revoked`
```text
required:
  grant_id:        GrantId
  revoked_at:      MonotonicTimestamp
  revoked_reason:  RevokeReason   // UserRevoke | Ttl | PersonaSwap | EmergencyRevoke | ApprovalTimeout | CostCapHit
  audit_ref:       AuditId
  change_id:       ChangeId
  seq:             u64
optional:
  cascade_batch_id: Option<BatchId>  // persona swap or emergency revoke groups
idempotency:
  Revoke-once. Second attempt is logged no-op.
```

#### `audit_record`
```text
required:
  audit_id:            AuditId
  timestamp_monotonic: MonotonicTimestamp
  timestamp_wall:      WallClockTimestamp
  actor:               ActorRef
  capability:          Capability
  resource:            ResourceScope
  decision:            DecisionKind
  change_id:           ChangeId
  prev_hash:           Hash       // SHA-256 of previous record's canonical serialization
  record_hmac:         Mac        // HMAC under per-install key
  key_id:              KeyId
  seq:                 u64
optional:
  reason:              Option<StaticReasonId>
  stage_trace:         Vec<StageTrace>
  privileged_profile:  bool
invariant:
  Append-only. SQLite triggers reject UPDATE/DELETE. Chain break →
  DegradedMode::AuditBroken → deny-all.
```

#### `emergency_revoke_all`
```text
required:
  initiated_by: ActorRef
  scope:        EmergencyScope   // All | Category(CapGroup) | Persona(PersonaId)
  initiated_at: MonotonicTimestamp
  audit_ref:    AuditId
  change_id:    ChangeId
  seq:          u64
optional:
  completed_at:   Option<MonotonicTimestamp>
  revoked_count:  Option<u32>
invariants:
  Single in-flight at a time; concurrent calls coalesce.
  Must complete ≤500 ms (acceptance criterion).
  Pre-empts all in-flight tool calls; L4 MUST cancel before next frame.
```

#### `cost_threshold_hit`
```text
required:
  provider:        ProviderId
  threshold:       CostThreshold    // Daily | Monthly | PerProvider | PerPersona
  dollars_hit:     Cents
  counter_window:  TimeWindow
  audit_ref:       AuditId
  change_id:       ChangeId
  seq:             u64
optional:
  warn_level:  Option<WarnLevel>    // emitted at warn_at_pct
idempotency:
  Once per threshold-crossing per window; re-arm resets the emitter.
```

#### `policy_posture_changed`
```text
required:
  prior_posture: PolicyPostureSummary
  new_posture:   PolicyPostureSummary
  trigger:       PostureTrigger    // PresetSwitch | PersonaSwap | DegradedEntry | DegradedExit | CapBlocklistUpdate
  change_id:     ChangeId
  seq:           u64
  audit_ref:     AuditId
optional:
  stripped_grants:     Vec<GrantId>   // on preset narrowing
  added_capabilities:  Vec<Capability>
invariant:
  Subscribers hash PolicyPostureSummary to detect drift on reconnect.
```

### 4.2 L1 events

#### `turn_begin`
```text
required:
  turn_id:     TurnId
  input_kind:  InputKind       // Voice | Text | PushToTalk
  started_at:  MonotonicTimestamp
  persona_id:  PersonaId
  tier:        PerfTier
ordering:
  First event per turn_id; strict monotonic within the turn.
```

#### `turn_end`
```text
required:
  turn_id:   TurnId
  ended_at:  MonotonicTimestamp
  outcome:   TurnOutcome       // Answered | Repaired | Denied | Cancelled | Error
ordering:
  Last event per turn_id; always emitted exactly once.
```

#### `partial_transcript`
```text
required:
  turn_id:    TurnId
  text:       String            // empty allowed (silence re-estimate)
  stability:  f32               // clamped [0,1]
  at:         MonotonicTimestamp
optional:
  confidence_per_token:  Vec<f32>
semantics:
  High-freq. Dropped silently on Lite if bus is coalesced.
```

#### `intent_hint`
```text
required:
  turn_id:      TurnId
  intent_class: IntentClass
  confidence:   f32
  derived_at:   MonotonicTimestamp
open_question:
  Emitter is contested (L1 interface pack §3.6 vs 08_system_architecture.md
  places it in Cognition). L1 design says L1-embedded reflex is the emitter.
  See §7 of this doc and §8 open questions.
```

#### `route_hint`
```text
required:
  turn_id:                     TurnId
  privacy_posture:             PrivacyPosture
  tier_preference:             PerfTier
  latency_budget_remaining_ms: u32
  intent_class:                IntentClass
  memory_confidence:           f32
  reflex_category:             ReflexCategory
optional:
  tool_plan_sketch:  Option<ToolPlanSketch>
semantics:
  Not projected to webview. Internal bus only.
```

#### `ack_phrase`
```text
required:
  turn_id:        TurnId
  phrase_id:      PhraseId
  text:           String
  intent_class:   AckIntentClass   // Checking | Verifying | Thinking | ...
  pool:           AckPool          // Normal | Safety | Clarify | Repair
  scheduled_at:   MonotonicTimestamp
```

#### `turn_state_change`
```text
required:
  turn_id:   TurnId
  from:      TurnState
  to:        TurnState
  at:        MonotonicTimestamp
  cause:     TransitionCause      // Event | TimerFired | Deny | NeedsUpgrade | MediaStall | EmergencyRevoke | GrantRevoked | PersonaSwap | TierDowngrade
invariants:
  Strict seq monotonicity within turn_id.
  "Speaking" as `to` state corresponds to the user-requested
  `response_started` semantic — see §7.
```

#### `reflex_classification`
```text
required:
  turn_id:       TurnId
  category:      ReflexCategory   // DirectLocal | AcknowledgeAndWait | Search | ToolPlan | RemoteEscalation | SafetyDeflection | MemoryWrite | ClarifyBackToUser
  confidence:    f32
  rationale_tag: StaticReasonId
```

#### `repair_started` / `repair_resolved`
```text
repair_started {
  turn_id:             TurnId
  cause:               RepairCause   // HardDeadline | MediaStall | PolicyDeny | RouterUnreachable | GrantRevoked | EmergencyRevoke | NeedsUpgrade | ClockSkew
  at:                  MonotonicTimestamp
  needs_upgrade_hint:  Option<NeedsUpgradeHint>
}
repair_resolved {
  turn_id:     TurnId
  resolution:  RepairResolution
  at:          MonotonicTimestamp
}
```

#### `barge_in_detected`
```text
required:
  turn_id:    TurnId
  at:         MonotonicTimestamp
  cut_point:  CutPoint     // EndOfWord | MidWord | EndOfSentence
```

### 4.3 L2 events

#### `memory_hit`
```text
required:
  query_id:        QueryId
  turn_id:         TurnId
  item_id:         ItemId
  snippet:         String
  privacy_class:   PrivacyClass    // Public | Personal | Sensitive | Restricted | SelfReflective
  score:           f32
  confidence:      f32
  provenance_ref:  ProvenanceRef
optional:
  rank_position:       u8
  redactions_applied:  Vec<RedactionTag>
invariant:
  privacy_class stamped on EVERY hit. Never elided even under degraded mode.
ordering:
  Must arrive at or before MemoryQuery.deadline; late hits discarded.
```

#### `memory_write_confirmed` / `memory_edit_confirmed`
```text
memory_write_confirmed {
  candidate_id:   CandidateId
  item_id:        ItemId
  domain:         MemoryDomain
  privacy_class:  PrivacyClass
}
memory_edit_confirmed {
  item_id:         ItemId
  version_before:  u32
  version_after:   u32
}
```

#### `memory_delete_pending` / `memory_delete_committed`
```text
memory_delete_pending {
  item_id:            ItemId
  grace_expires_at:   MonotonicTimestamp
}
memory_delete_committed {
  item_id:       ItemId
  tombstone_id:  TombstoneId
}
idempotency:
  On (item_id, version). Restricted/LegalHold skip grace and commit
  immediately if policy permits.
```

#### `memory_retention_expired`
```text
required:
  item_id:  ItemId
  policy:   RetentionPolicy   // Ephemeral | ShortTerm | LongTerm | UserPinned | LegalHold | ExpireOnEvent
```

#### `provenance_update`
```text
required:
  item_id:     ItemId
  chain_ref:   ProvenanceChainRef
optional:
  extended_by: Option<ProvenanceLink>
```

#### `ingestion_candidate_rejected`
```text
required:
  candidate_id:  CandidateId
  reason:        IngestionRejectReason
```

#### `ingestion_candidate_accepted` *(proposed, §7)*
```text
required:
  candidate_id:  CandidateId
  item_id:       ItemId
  domain:        MemoryDomain
  privacy_class: PrivacyClass
note:
  Paired with `_rejected` for audit symmetry. Not yet in L2 interface pack §4.
```

### 4.4 L3 events

#### `presence_state`
```text
required:
  behavior:   BehaviorClass   // Neutral | Listening | MicroAck | PreparingToSpeak | Speaking | Thinking | Repairing | HoldingForUser | Concealed
  intensity:  f32
  tier:       TierLevel       // Full | Standard | Lite | Minimal
  posture:    PresencePosture // Normal | Restrained | Masked | Concealed
  at_ms:      u64
semantics:
  Broadcast on every state change; coalesced for webview.
correlation:
  presence_state events correspond to the same turn_id as L1 turn_state
  where applicable (invariant in §6).
```

#### `avatar_frame_ready`
```text
required:
  frame_id:  u64
  at_ms:     u64
  tier:      TierLevel
semantics:
  Observer-only; not load-bearing. Typically Rust-internal.
```

#### `behavior_started` / `behavior_completed`
```text
behavior_started {
  behavior: BehaviorClass
  trigger:  BehaviorTrigger
  at_ms:    u64
}
behavior_completed {
  behavior:    BehaviorClass
  duration_ms: u32
  at_ms:       u64
}
mapping:
  Name-variant: "avatar_behavior_changed" (user-requested name) maps to
  `behavior_started` + optional `behavior_completed` pair. See §7.
```

#### `anti_uncanny_correction_applied`
```text
required:
  field:      &'static str
  requested:  f32
  clipped_to: f32
  reason:     StaticReasonId
  at_ms:      u64
```

#### `tier_downgrade_presence`
```text
required:
  from:    TierLevel
  to:      TierLevel
  reason:  StaticReasonId
  at_ms:   u64
```

#### `rendering_surface_error`
```text
required:
  surface_id:  SurfaceId
  error:       PresenceError
  at_ms:       u64
```

### 4.5 L4 events

#### `route_decision`
```text
required:
  turn_id:                TurnId
  chosen_tier:            TierId
  chosen_provider:        ProviderId
  tool_plan:              Option<ToolPlan>
  fallback_chain:         Vec<FallbackStep>
  rationale:              Vec<StaticReasonId>
  estimated_latency_ms:   u32
  estimated_cost_cents:   Cents
invariant:
  In DegradedNoPolicy mode, emits `{ chosen_tier: None, rationale:
  DegradedNoPolicy }` — never silent-allow.
name_variant:
  "routing_decision_made" → canonical name is `route_decision`. See §7.
```

#### `escalation_reason`
```text
required:
  turn_id:  TurnId
  reason:   EscalationReason   // CostCapHit | PrivacyPosture | ProviderUnreachable | RateLimited | PinOverridden | CircuitOpen
```

#### `cost_event`
```text
required:
  change_id:       ChangeId
  provider:        ProviderId
  tier:            TierId
  cents:           Cents
  tokens_in:       u32
  tokens_out:      u32
  ts:              MonotonicTimestamp
  request_id:      RequestId   // correlates with authorizing ActionRequest
optional:
  persona_id:  Option<PersonaId>
  session_id:  Option<SessionId>
  failed:      bool            // partial cost still counts
ordering:
  cost_event emission order matches tool_call_completed order per provider
  (invariant §6).
idempotency:
  At-least-once; L5 dedupes on (request_id, provider, ts).
```

#### `tool_call_started` / `tool_call_completed`
```text
tool_call_started {
  change_id:      ChangeId
  tool_id:        ToolId
  tier:           TierId
  provider:       ProviderId
  actor_persona:  PersonaId
}
tool_call_completed {
  change_id: ChangeId
  result:    ToolResult    // Ok | Err | PartialOk | Cancelled | PolicyDenied
}
```

#### `provider_health`
```text
required:
  provider:                  ProviderId
  state:                     ProviderHealthState   // Ok | Degraded | Unreachable | AuthFailed
  rolling_p95_latency_ms:    u32
optional:
  last_failure_reason: Option<StaticReasonId>
semantics:
  Coalesced per provider per tick.
```

#### `byok_credential_added` / `_rotated` / `_removed`
```text
byok_credential_added {
  provider:         ProviderId
  key_fingerprint:  Fingerprint
}
byok_credential_rotated {
  provider:         ProviderId
  old_fingerprint:  Fingerprint
  new_fingerprint:  Fingerprint
}
byok_credential_removed {
  provider:         ProviderId
  fingerprint:      Fingerprint
}
invariant:
  NEVER contains key material. Fingerprint-only.
```

#### `fallback_triggered`
```text
required:
  change_id:  ChangeId
  from:       ProviderId
  to:         ProviderId
  reason:     EscalationReason
```

### 4.6 L6 events

#### `compiled_persona_ready`
```text
required:
  persona_id:         PersonaId
  version:            SemVer
  change_id:          ChangeId
  compiled_at:        MonotonicTimestamp
  artifact_ref:       CompiledPersonaRef   // points to { CompiledLanguage, CompiledSalience, CompiledVisual, CompiledRouting, CompiledPolicyDefaults, PersonaSummary }
  provenance_status:  ProvenanceStatus     // Trusted | Unverified | PrivilegedOverlay
mapping:
  Name-variant: "persona_compiled" → canonical `compiled_persona_ready`.
```

#### `persona_swap_begin` / `persona_swap_commit` / `persona_swap_rollback`
```text
persona_swap_begin {
  persona_id:      PersonaId
  previous_id:     PersonaId
  change_id:       ChangeId
  compile_time_ms: u32
}
persona_swap_commit {
  persona_id: PersonaId
  change_id:  ChangeId
}
persona_swap_rollback {
  persona_id: PersonaId
  reason:     StaticReasonId
  change_id:  ChangeId
}
invariant:
  persona_swap_commit fires only at L1 safe boundary (Idle or end-of-Speaking /
  end-of-AcknowledgingWait; strictness open — §8).
  If safe boundary not reached within 500 ms → rollback.
```

#### `persona_compile_failed`
```text
required:
  persona_id: PersonaId
  version:    SemVer
  reason:     PersonaErrorProjected
  change_id:  ChangeId
```

#### `persona_observed_style_proposed`
```text
required:
  persona_id:      PersonaId
  field_path:      String
  proposed_value:  Value
  evidence_ref:    EvidenceRef
  proposal_id:     ProposalId
invariant (I-8):
  NO silent learning. Persona does not apply the change until L7 fires
  `persona.observed_style.confirm`. Decays if unconfirmed.
```

### 4.7 Core events

#### `core.health.tier_change` / `core.health.reconnect`
```text
core.health.tier_change {
  from_tier:          PerfTier     // Lite | Balanced | Full (L3 adds Minimal)
  to_tier:            PerfTier
  reason:             DowngradeReason
  vram_pressure_pct:  Option<u8>
}
core.health.reconnect {
  subsystem_id:  SubsystemId
  at:            MonotonicTimestamp
}
```

### 4.8 Proposed new events — degraded mode

#### `degraded_mode_entered` *(proposed)*
```text
required:
  mode:            DegradedMode      // SafeMode | AuditBroken | LedgerCorrupt | MinimumTrust | DegradedNoPolicy | DegradedNoMemory | DegradedNoRouter
  source_layer:    SourceLayer       // typically L5; may be L1/L4 for their self-modes
  reason:          StaticReasonId
  at:              MonotonicTimestamp
  change_id:       ChangeId
  seq:             u64
consumers:
  L7 (banner), all layers (for behavior clamp)
invariant:
  degraded_mode_entered MUST precede any refuse-class `policy_decision`
  triggered by that mode (invariant §6 row 9).
rationale:
  L5's policy_posture_changed { trigger: DegradedEntry } is too coarse for
  L7's per-banner UI and for L1's per-mode degraded TurnState selection.
  Integration notes §7.1 already lists a `degraded_mode_enter/exit` event
  pair with producer "L1/L4/L5"; this formalizes it.
```

#### `degraded_mode_cleared` *(proposed)*
```text
required:
  mode:          DegradedMode
  source_layer:  SourceLayer
  at:            MonotonicTimestamp
  change_id:     ChangeId
  seq:           u64
semantics:
  Fires when the originating condition is remedied; L7 dismisses the
  corresponding banner. Pair with `degraded_mode_entered` on (mode,
  source_layer).
```

### 4.9 User-requested name-variant mapping to canonical payloads

The user's prompt referenced several event names that are not verbatim in
the source design docs. They are reconciled here (full table in §7) and
their payloads are covered by the canonical event above:

- `acknowledgment_started` → canonical `ack_phrase` (payload in §4.2).
- `response_started` → canonical `turn_state_change { to: Speaking }`
  (payload in §4.2).
- `avatar_behavior_changed` → canonical `behavior_started` (payload in §4.4).
- `routing_decision_made` → canonical `route_decision` (payload in §4.5).
- `interaction_state_changed` → canonical `turn_state_change`.
- `persona_compiled` → canonical `compiled_persona_ready`.
- `memory_candidate_created` → partially covered by
  `ingestion_candidate_rejected`; the accepted path is **proposed new**
  `ingestion_candidate_accepted` (§4.3).
- `memory_promoted` → **not yet defined; flagged §8.**
- `memory_revoked` → reconciled as the pair `memory_delete_committed` +
  `grant_revoked` keyed on the same `change_id` (§7).
- `observed_style_confirmed` → not an L6-emitted event; the confirmation
  travels as L7 command `persona.observed_style.confirm`. L6 only emits
  `persona_observed_style_proposed` (§4.6). Flagged §8.

---

## 5. Versioning rules

1. **SemVer (major.minor) on event schema.** Every event carries a
   `version: (u16, u16)` in its envelope. The event bus enforces that
   subscribers declare the major version they accept; a producer emitting a
   higher major version is a hard incompatibility.

2. **Minor bump — new optional fields.** Adding an optional field is a
   minor bump (`1.0 → 1.1`). Existing consumers keep working (§5.6 — unknown
   optional fields tolerated). Required field additions are a major bump.

3. **Major bump — rename / remove / retype.**
   - Rename: old name deprecated, new name introduced under a new major; old
     retained for one release cycle with a duplicate emit where feasible.
   - Remove: explicit deletion; producers stop emitting at major boundary.
   - Retype: any change to a field's type (including enum variant removal)
     is major. Enum variant *addition* is minor only if the field is opaque
     to existing consumers (they must treat unknown variants as "unknown").

4. **Compatibility expectations.**
   - Rust canonical: the `L{n}Event` enum in the `event-bus` crate is the
     source of truth. Major bumps require a Rust crate major version bump.
   - TS bindings: regenerated via `ts-rs` on every Rust schema change. A
     regeneration without a Rust change is a CI failure (signals drift).

5. **ts-rs regeneration gate.** CI MUST regenerate TS types on any Rust
   event-shape commit and fail if the diff is non-empty but no
   `packages/*-ts/` change is included. This is the drift gate.

6. **Consumer tolerance rule.** Consumers MUST:
   - Ignore unknown optional fields (forward-compat).
   - Match enum variants by name; treat unknown variants as opaque pass-through
     (never panic).
   - Reject major-version mismatches at subscription time, not mid-stream.

7. **Version field in every payload root.** `version: SchemaVersion { major,
   minor }` present on every emitted event; bus layer stamps it from the
   producing crate's declared version.

8. **At-start-of-stream version handshake.** On `subscribe`, the subscriber
   receives a `stream_manifest` metadata event declaring the producer's
   current schema version for each event kind; version renegotiation on
   producer upgrade is explicit.

---

## 6. Invariants

1. **No tool/action event bypasses L5 `policy_decision`.** Every
   `tool_call_started`, `route_decision` with non-empty `tool_plan`, remote
   invocation, and gated memory op has a preceding `policy_decision` in seq
   order for the same `change_id`. CI lint (`tools/lint-policy-bypass/`)
   enforces at compile time; bus-level invariant checker enforces at
   runtime.

2. **Every `grant_issued` has a corresponding allow-class
   `policy_decision`.** For any `grant_issued { audit_ref }`, there exists a
   prior `policy_decision { decision: Allow, audit_id = audit_ref }` in the
   audit chain. Replay-tests assert this on full event logs.

3. **L7 UI reflects L5's authoritative grant state — never its own cache.**
   L7 MUST NOT pattern-match on local grant cache to make authorization
   decisions; every render of an "Allowed" UX must trace to a live
   `grant_issued` event whose `grant_id` is not shadowed by a later
   `grant_revoked`.

4. **`presence_state` events correspond to L1 `turn_state_change` within
   the same `turn_id`.** For every `turn_state_change { to: Speaking }`
   there is a `presence_state { behavior: Speaking }` within one frame
   interval of the active tier. Desync (>1 frame) emits `presence_desync`
   telemetry; L1 does not reconcile (L3 is advisory for consistency).

5. **`cost_event` emission order matches `tool_call_completed` order per
   provider.** For any provider, the sequence of `cost_event`s in seq order
   matches the sequence of `tool_call_completed` events for that provider.
   Partial-cost failures still emit a `cost_event` with `failed: true`.

6. **`memory_hit` events carry `privacy_class` on every hit.** No
   exceptions, including under `DegradedNoPolicy` or audit-broken modes.
   A `memory_hit` without a `privacy_class` is a schema-violation error and
   the consumer rejects it.

7. **`persona_swap_commit` fires only at L1 safe boundary.** Never
   mid-utterance. `persona_swap_begin` without a matching `_commit` or
   `_rollback` within 500 ms is an error (swap times out → rollback).

8. **`audit_record` is append-only; no update/delete event exists.** The
   `AuditRecord` family has no `_updated` or `_deleted` sibling. Corrective
   records are new appends with a reference to the prior `audit_id`. SQLite
   triggers reject UPDATE/DELETE on the audit table at the storage layer.

9. **`degraded_mode_entered` precedes any refuse-class `policy_decision`
   triggered by that mode.** A `Deny { reason: LedgerCorrupt }` or similar
   system-triggered deny MUST be preceded in seq order by the
   `degraded_mode_entered { mode: AuditBroken | LedgerCorrupt | SafeMode
   }`, so L7's banner is up before the user sees the deny row.

10. **`change_id` is unique per event and referenced consistently across
    correlated events.** For a given `change_id`, every event in the chain
    (`action_request` → `policy_decision` → `grant_issued` → `route_decision`
    → `tool_call_started` → `tool_call_completed` → `cost_event` →
    `turn_state_change` → `audit_record`) carries the same value. Replay
    tests (L5 §13) assert this across full event logs.

11. **`emergency_revoke_all` pre-empts all in-flight tool calls; L4 must
    cancel before the next frame.** On receipt, L4 MUST emit
    `tool_call_completed { result: Cancelled { cause: EmergencyRevoke } }`
    for every in-flight tool before processing any further bus event; L1
    transitions any executing turn to `Repairing` with cause
    `EmergencyRevoke`; L7 banner overlay locks the UI.

12. **No secret material ever crosses the bridge.** BYOK events
    (`byok_credential_added/_rotated/_removed`) carry `Fingerprint` only.
    Static type-level check: the `Fingerprint` type does not implement any
    serialization path that round-trips to key material.

13. **Private-tagged context never reaches remote routes without an explicit
    waiver grant.** If a `route_decision` selects a remote tier and the
    inbound `RouteHint` carries `privacy_posture: Strict` with
    `memory_confidence > 0` on private-class hits, L4 MUST have a grant
    `RouterAllowRemoteWithPrivate` recorded in the chain; else
    `policy_decision { Deny: PrivacyPostureViolation }` interrupts the
    chain.

14. **`turn_begin` is always first, `turn_end` always last in a turn.** No
    event with `turn_id = T` may have a `seq` outside `[seq(turn_begin_T),
    seq(turn_end_T)]`.

---

## 7. Name-variant reconciliation

The user's prompt (and integration notes) reference several event names
that are not verbatim in the source design docs. Canonical mapping:

| User-requested name | Canonical event | Notes / discrepancy |
|---|---|---|
| `acknowledgment_started` | `ack_phrase` | Same event. L1 emits `ack_phrase` with `pool` and `intent_class`; "acknowledgment_started" is not a distinct lifecycle beat. |
| `response_started` | `turn_state_change { to: Speaking }` | Not a standalone event — it is a state transition. UI treats the Speaking transition as "response started." |
| `avatar_behavior_changed` | `behavior_started` (+ optional prior `behavior_cancelled` / `behavior_completed`) | L3 emits per-lifecycle edges, not a single "changed" event. `avatar_behavior_changed` is a composite the UI can synthesize from the pair. |
| `routing_decision_made` | `route_decision` | L4 interface pack and integration notes §7.1 both use `route_decision`. |
| `memory_candidate_created` | `ingestion_candidate_accepted` (proposed, §4.3) | Not currently emitted; L2 only emits `ingestion_candidate_rejected`. Proposed addition for audit symmetry. |
| `memory_promoted` | **Not yet defined.** | Flagged §8. Possibly "a session-memory item promoted to durable memory" — needs L2 definition. |
| `memory_revoked` | `memory_delete_committed` + `grant_revoked` keyed on the same `change_id` | No single "memory_revoked" event. The pair captures (a) the item's removal from storage and (b) any capability grant tied to it being revoked. |
| `interaction_state_changed` | `turn_state_change` | Identical; "interaction_state" is a higher-doc synonym for "turn_state." |
| `persona_compiled` | `compiled_persona_ready` | L6 canonical name. |
| `observed_style_confirmed` | **Not an event.** | The confirmation travels as the L7→L6 Tauri command `persona.observed_style.confirm`. L6 re-emits `compiled_persona_ready` after applying. Flagged §8. |
| `degraded_mode_entered` / `degraded_mode_cleared` | Proposed new pair, §4.8 | Not in any source doc. Integration notes §7.1 references `degraded_mode_enter/exit` informally. Proposed as first-class events here. |

### 7.1 Explicit contradiction — `intent_hint` emitter

- **L1 interface pack §3.6 / §4 (Outbound interfaces)** lists `intent_hint`
  as emitted by L1 (L1-embedded reflex classifier).
- **`08_system_architecture.md`** (per the user's prompt) places
  `intent_hint` production in Cognition.

**This doc's canonical position:** producer is **L1** (L1-embedded reflex
classifier). Rationale: the L1 system design explicitly freezes the
classifier inside L1 and ties `intent_hint` to `reflex_classification`
timing. Resolving this formally requires Don to reconcile
`08_system_architecture.md`. Flagged §8.

### 7.2 Explicit contradiction — `NeedsUpgrade` encoding

- **L5 interface pack §6.1** lists both `Decision::NeedsUpgrade {
  suggested_preset }` (top-level) and `Decision::Deny { reason: NeedsUpgrade
  }` — then flags the contradiction (integration notes Q2).
- **L1 interface pack §7.1 / §10.1** proposes honoring top-level
  `Decision::NeedsUpgrade` as canonical and never synthesizing from
  `Deny`.

**This doc's canonical position:** top-level `Decision::NeedsUpgrade` is
canonical; `Deny { reason: NeedsUpgrade }` is deprecated. Any consumer
receiving `Deny { reason: NeedsUpgrade }` should treat it as equivalent to
`NeedsUpgrade` during the deprecation window. Flagged §8.

---

## 8. Open questions

1. **`intent_hint` emitter (L1 vs Cognition).** Blocks: L7 trust-debug
   view label; event-bus producer declaration. Canonical proposal: L1.
   Resolution: Don reconciles `08_system_architecture.md` against L1
   interface pack §3.6.

2. **`NeedsUpgrade` encoding (top-level Decision vs Deny-reason).** See
   §7.2. Blocks: L7 upgrade card, L1 Repairing branch. Integration notes
   Q2.

3. **`memory_promoted` definition.** User prompt lists this as an expected
   event. L2 does not currently define it. Candidates: (a) a new event
   fired when a `SessionMemory` item is upgraded to `DurableUserMemory`; or
   (b) a subclass of `memory_edit_confirmed` with a domain shift. Needs
   L2 author input.

4. **`observed_style_confirmed` vs `persona_observed_style_proposed`.** L6
   emits the proposal; L7 confirms via command. Is there a downstream
   `observed_style_confirmed` event (distinct from the next
   `compiled_persona_ready`) that L5 audits? Current position: no separate
   event — L5 audit captures the L7 command invocation and the subsequent
   `compiled_persona_ready`. Needs explicit confirmation.

5. **`ingestion_candidate_accepted` (proposed).** Symmetry with
   `ingestion_candidate_rejected` for audit completeness. Needs L2 author
   ratification.

6. **`acknowledgment_started` vs `ack_phrase` naming.** Renaming
   `ack_phrase` → `acknowledgment_started` was implicit in the prompt. This
   doc keeps `ack_phrase` as canonical (shorter, existing in L1 §4). If
   Don prefers the longer form, this is a minor-major event-rename (§5
   rules apply).

7. **Audit semantics for `barge_in_detected` mid-tool-call.** Integration
   notes Q9: does the plan cancel immediately, finish the current step, or
   mark the `change_id` as "abandoned"? Affects `tool_call_completed`
   result variant and audit row shape. Not a new event — a payload
   semantics open question.

8. **Cost-cap `re_armed` event shape.** L4 interface pack §3 references
   `re_armed { provider }` as an inbound bus event from L5, but L5
   interface pack §4 does not list it as an outbound. Current position:
   add `cost_cap_rearmed { provider, at, audit_ref, change_id, seq }` to
   L5's outbound family. Flagged for L5 author confirmation.

9. **Plan-preview bundle event.** L5 `policy.preview_plan` command exists
   at P1/P2 — does it emit a bus event (`plan_preview_ready { bundle_id,
   steps, aggregate_decision }`), or is it purely a command return? If the
   former, add to the catalog.

10. **`degraded_mode_entered` / `_cleared` — producer ownership.** L5
    certainly owns it for policy-engine degraded states. L1 owns
    `DegradedNoPolicy | DegradedNoMemory | DegradedNoRouter | MinimumTrust`
    for its self-modes (which are distinct from L5's `SafeMode`). Should a
    single catalog event support multiple producers (with `source_layer`
    disambiguating), or should each producer emit its own variant? Current
    proposal: single event, `source_layer` disambiguates. Needs sign-off.

---

## 9. Cross-references

- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L1_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L2_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L3_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L4_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L5_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L6_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L7_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_memory_kernel_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L3_presence_engine_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L4_model_router_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L6_persona_compiler_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L7_trust_ux_onboarding_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/X3_tauri_architecture.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_L4_L5_L7_integration_notes.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_L3_L6_integration_notes.md

---

*End of Aether Master Event Contracts — Draft 1.*
