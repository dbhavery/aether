---
status: draft
date: 2026-04-18
layer: L1 (Interaction Timing + Reflex Router)
mode: interface pack (pre-implementation freeze)
upstream:
  - plans/L1_interaction_timing_system_design.md (authoritative system design; 1071 lines)
  - plans/L5_policy_engine_system_design.md (PolicyAdapter shape, Decision, ActionRequest)
  - plans/L4_model_router_system_design.md (RouteHint, RouteDecision)
  - plans/L2_memory_kernel_system_design.md (MemoryQuery, MemoryHit, time-bounded oracle)
  - plans/L6_persona_compiler_system_design.md (CompiledLanguage / CompiledPersona, phrase pools)
  - plans/L3_presence_engine_system_design.md (turn_state subscription contract)
  - plans/L1_L4_L5_L7_integration_notes.md
scope_of_this_document:
  - Concrete interface pack to unblock packages/l1-timing (Rust) + packages/l1-timing-ts (TS facade)
  - Freezes inbound / outbound event shapes, synchronous vs async boundaries, adapter traits, error vocabulary
non_goals:
  - Reimplementing §2-§16 of the L1 system design (see file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md)
  - Writing Rust crates or TS bindings
  - Resolving the open questions flagged in §10 (those need Don sign-off)
---

# L1 Interface Pack — Interaction Timing + Reflex Router

> Canonical system design: file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md
> Target packages (X1-dependent): file:///C:/Users/dbhav/Projects/aether/packages/l1-timing/ (Rust core event-loop thread) + file:///C:/Users/dbhav/Projects/aether/packages/l1-timing-ts/ (typed bindings / thin facade).
> Co-owned monorepo crate: file:///C:/Users/dbhav/Projects/aether/packages/event-bus/ (per monorepo §2).

---

## 1. Purpose

This document is the **contract freeze** for L1 — the Interaction Timing Engine with embedded reflex router. It translates the 1071-line system design into the narrow surface an implementer (or a cross-layer stub author for L2 / L3 / L4 / L5 / L6 / L7) needs to code against without re-reading the full design.

L1 is the **clock** and **classifier** for every conversational turn. It owns the turn-state machine, the reflex classifier (not executor), the acknowledgment phrase selection, the 12 timing budgets, and barge-in / repair flow. It does not own policy decisions, memory retrieval, routing execution, or presence animation. Those live in L5, L2, L4, and L3 respectively — L1 calls into them via adapter traits and subscribes to their events.

The package split mirrors the engine / facade split used elsewhere in the monorepo: the Rust `l1-timing` crate runs the authoritative event loop on a dedicated thread; `l1-timing-ts` is a thin typed facade over the Tauri IPC surface for the webview.

---

## 2. Primary responsibilities

### L1 owns

- **Turn-state machine** — the single source of truth for the felt state of a turn. 19 states: `Idle`, `Listening`, `PartialASR`, `ClassifyingIntent`, `AcknowledgingWait`, `Thinking`, `AwaitingPolicy`, `AwaitingApproval`, `RouteSelected`, `ExecutingDirect`, `ExecutingTool`, `Streaming`, `Speaking`, `Repairing`, `BargedIn`, `DegradedNoPolicy`, `DegradedNoMemory`, `DegradedNoRouter`, `Error`. All transitions are driven by a typed `(state, event) -> next_state` function; timers are events too.
- **Embedded reflex classifier** (classifier, NOT executor) — maps partial/final transcript + memory context + persona posture + budget remaining to one of eight categories: `DirectLocal`, `AcknowledgeAndWait`, `Search`, `ToolPlan`, `RemoteEscalation`, `SafetyDeflection`, `MemoryWrite`, `ClarifyBackToUser`. Every side-effecting category emits an `ActionRequest` for L5 and waits.
- **Ack-phrase selection** — pool structure, anti-repetition ring (N=5), weighted sampling with per-turn seed for replay. Phrase *content* comes from L6; L1 owns *selection* and *timing*.
- **Timing budgets** — enforcement of the 12 named budgets from §4 of the system design: `T_first_state_change` (250 ms), `T_ack_deadline` (800 ms), `T_reflex_sla` (150 ms), `T_memory_deadline` (150 ms), `T_soft_deadline` (2000 ms), `T_hard_deadline` (4000 ms), `T_barge_in_cut` (150 ms), `T_policy_wait` (shared with soft deadline), `T_approval_secondary_ack` (2000 ms), `T_tts_chunk_inactivity` (500 ms), `T_event_loop_tick` (5 ms / 10 ms on Lite), `T_repair_ack` (2000 ms).
- **Barge-in and repair flow** — VAD-driven cut with 150 ms firm budget; repair flow for hard-deadline miss / media stall / deny / unreachable / grant revoked / emergency revoke.

### L1 does NOT own

- **Policy decisions** (L5). L1 constructs `ActionRequest` envelopes but never self-authorizes.
- **Memory retrieval** (L2). L1 issues `MemoryQuery` with a deadline; must-respond-or-empty.
- **Routing execution** (L4). L1 builds `RouteHint`; L4 returns `RouteDecision`.
- **Presence animation** (L3). L3 subscribes to the turn-state bus; L1 never calls L3.
- **TTS / STT inference** (media engine). L1 owns the streaming-chunk + interrupt contract only.
- **Persona content** (L6). L1 consumes `CompiledLanguage` (phrase pools, ack style, reflex tuning).

---

## 3. Inbound interfaces

All inbound events carry `source_layer`, global monotonic `seq`, and `change_id` per the X3 §3.2 bus convention.

### 3.1 Media → L1 — VAD / ASR / TTS events

| Event | Producer | Required fields | Optional | Validation | Failure mode |
|---|---|---|---|---|---|
| `vad.speech_start` | media engine | `at: MonotonicTimestamp` | `source_mic_id` | `at` must be monotonically non-decreasing within a session | If L1 in Speaking/Streaming/AcknowledgingWait → `BargedIn`; late events past `T_barge_in_cut` are logged but still honored |
| `vad.speech_end` | media engine | `at: MonotonicTimestamp` | `tail_silence_ms` | same | Arms silence-tail timer; if missing, VAD timeout is L1's internal fallback |
| `partial_transcript` | media engine | `text: String`, `stability: f32 (0..1)`, `at: MonotonicTimestamp` | `confidence_per_token` | `stability` clamped; empty `text` allowed (silence re-estimate) | Dropped silently on Lite if event-bus is coalesced |
| `final_transcript` | media engine | `text: String`, `at: MonotonicTimestamp` | `alternatives: Vec<String>` | non-empty `text`; else treat as user-retracted turn | Triggers ClassifyingIntent |
| `tts_chunk_done` | media engine | `turn_id: TurnId`, `phrase_id: PhraseId`, `at: MonotonicTimestamp` | `audio_ts_ns` | correlate on `turn_id` | Missing → T_tts_chunk_inactivity watchdog |
| `tts_eos` | media engine | `turn_id: TurnId`, `phrase_id: PhraseId` | — | — | Missing → treat Speaking as stalled after T_tts_chunk_inactivity |
| `tts_stall` | media engine | `turn_id: TurnId`, `at` | `reason` | — | Enter Repairing if sustained 1500 ms |
| `viseme_tick` | media engine | `turn_id`, `audio_ts_ns`, `viseme_id` | — | pass-through only | L3 is the primary consumer; L1 re-emits with turn correlation |

### 3.2 L7 / webview → L1 — user text input

| Command | Producer | Required fields | Optional | Validation | Failure mode |
|---|---|---|---|---|---|
| `turn.begin_user_turn` | L7 facade / media | `input_kind: InputKind` | `persona_override: PersonaId` | `input_kind ∈ {Voice, Text, PushToTalk}` | Returns `L1Error::Degraded` if L5 unreachable and input_kind requires it |
| `turn.submit_text` | L7 facade | `turn_id: TurnId`, `text: String` | `intent_hint_override` | `turn_id` must exist; `text` non-empty | `L1Error::NotFound` / `L1Error::AlreadyEnded` |
| `turn.cancel` | L7 facade | `turn_id: TurnId` | — | — | `L1Error::NotFound` / `L1Error::AlreadyEnded` |

### 3.3 L5 → L1 — policy / approval events

| Event | Producer | Required fields | Optional | Validation | Failure mode |
|---|---|---|---|---|---|
| `policy_decision` | L5 | `request_id: RequestId`, `turn_id`, `decision: Decision` | `grant_ref`, `ticket`, `needs_upgrade_hint` | `Decision ∈ {Allow, Ask, DraftOnly, Deny{reason}, NeedsUpgrade{suggested_preset}}` | Missing past `T_policy_wait` → `policy_slow` telemetry (keep waiting; do NOT short-circuit) |
| `approval_pending` | L5 | `request_id`, `turn_id`, `ticket: ApprovalTicket` | `expected_latency_hint` | — | Enter AwaitingApproval; arm T_approval_secondary_ack |
| `approval_response` | L5 | `ticket`, `response: {Allow*, Deny}` | `user_override_note` | — | Subsequent `policy_decision` is the authoritative signal |
| `grant_revoked` | L5 | `grant_ref` | `cause` | — | If load-bearing for current turn → Repairing |
| `emergency_revoke_all` | L5 | `at: MonotonicTimestamp` | — | — | Abort ExecutingTool / Streaming; cut TTS; Repairing; Idle |
| `policy_engine.degraded` | L5 | `at`, `reason` | — | — | Enter DegradedNoPolicy (see §7) |

### 3.4 L2 → L1 — memory events

| Event | Producer | Required fields | Optional | Validation | Failure mode |
|---|---|---|---|---|---|
| `memory_hit` | L2 | `query_id: QueryId`, `turn_id`, `hit: MemoryHit { id, text, scope, confidence, provenance }` | `rank_position` | `confidence ∈ [0,1]`; arrived on or before `deadline` | Late arrivals dropped; tag turn `memory_miss=true` |
| `memory_query_empty` | L2 | `query_id`, `turn_id` | — | — | Treat as empty context |
| `memory_write_confirmed` | L2 | `write_id`, `turn_id` | — | — | Non-blocking; recorded for turn-end audit |
| `memory.degraded` | L2 | `at`, `reason` | — | — | Enter DegradedNoMemory (transient) |

### 3.5 L4 → L1 — route events

| Event | Producer | Required fields | Optional | Validation | Failure mode |
|---|---|---|---|---|---|
| `route_decision` | L4 | `turn_id`, `decision: RouteDecision { chosen_tier, chosen_provider, tool_plan, fallback_chain, rationale, estimated_latency_ms, estimated_cost_cents }` | — | turn_id must match in-flight turn | Missing past T_soft_deadline → DegradedNoRouter |
| `escalation_reason` | L4 | `turn_id`, `reason: StaticReasonId` | — | — | Informational; attach to turn_end |
| `cost_event` | L4 | `turn_id`, `cents` | `provider` | — | Informational |
| `router.degraded` | L4 | `at`, `reason` | — | — | Enter DegradedNoRouter; fall back to direct-to-main local |

### 3.6 L6 → L1 — persona events

| Event | Producer | Required fields | Optional | Validation | Failure mode |
|---|---|---|---|---|---|
| `compiled_persona_ready` | L6 | `persona_id`, `compiled: CompiledLanguage { phrase_pool, ack_style, privacy_posture, safety_phrase_pool, hardcoded_allowed_deflections, reflex_tuning }` | `pool_version` | pools non-empty; safety pool distinct from normal | Missing → MinimumTrust fallback (§7.5) |
| `persona_swap_commit` | L6 | `from_persona_id`, `to_persona_id`, `at` | `strictness: {Strict, Relaxed}` | — | Hot-swap at next safe boundary (Idle, end-of-Speaking, end-of-AcknowledgingWait). **Open question — see §10** |
| `persona_compile_failed` | L6 | `persona_id`, `reason` | — | — | MinimumTrust fallback |

### 3.7 L3 → L1 — presence state (advisory only)

| Event | Producer | Required fields | Optional | Validation | Failure mode |
|---|---|---|---|---|---|
| `presence_state` | L3 | `mode: PresenceMode`, `at` | — | consistency-check only | On sustained mismatch with L1 `TurnState` → emit `presence_desync` telemetry. L1 does NOT reconcile; L3 is advisory. |

### 3.8 Core → L1 — health / tier signals

| Event | Producer | Required fields | Optional | Validation | Failure mode |
|---|---|---|---|---|---|
| `core.health.tier_change` | core | `from_tier`, `to_tier`, `reason` | `vram_pressure_pct` | — | Propagate as `tier_downgrade_notice`; switch phrase pool and tick rate on next safe boundary |
| `core.health.degraded_subsystem` | core | `subsystem_id`, `reason` | — | — | May short-circuit into L1's degraded modes |
| `core.suspend_resume_detected` | core | `pause_duration_ms` | — | `> 10_000` | Pending turn → Repairing |

---

## 4. Outbound interfaces

All outbound events carry `source_layer = L1`, global monotonic `seq`, `change_id`, and — when turn-scoped — `turn_id`. Field sets repeat the system design §5.2 with explicit `{ ... }` struct notation.

| Event | Required fields | Primary subscribers | Projected to webview |
|---|---|---|---|
| `turn_begin` | `{ turn_id, input_kind: InputKind{Voice\|Text\|PushToTalk}, started_at: MonotonicTimestamp, persona_id: PersonaId, tier: PerfTier }` | L2, L3, L4, L5, L7 | yes |
| `turn_end` | `{ turn_id, ended_at: MonotonicTimestamp, outcome: TurnOutcome{Answered\|Repaired\|Denied\|Cancelled\|Error} }` | all | yes |
| `partial_transcript` | `{ turn_id, text: String, stability: f32, at: MonotonicTimestamp }` | L2, L4, L7 | yes (debounced on Lite) |
| `intent_hint` | `{ turn_id, intent_class: IntentClass, confidence: f32, derived_at: MonotonicTimestamp }` | L4, L7 | yes (low-freq) |
| `route_hint` | `{ turn_id, privacy_posture, tier_preference, tool_plan_sketch: Option<ToolPlanSketch>, latency_budget_remaining_ms: u32, intent_class, memory_confidence: f32, reflex_category }` | L4 | no (internal) |
| `ack_phrase` | `{ turn_id, phrase_id, text, intent_class: AckIntentClass, pool: AckPool{Normal\|Safety\|Clarify\|Repair}, scheduled_at }` | Media (TTS), L3, L7 | yes |
| `turn_state_change` | `{ turn_id, from: TurnState, to: TurnState, at: MonotonicTimestamp, cause: TransitionCause }` | L3 (primary), L7, L5 (audit) | yes |
| `reflex_classification` | `{ turn_id, category: ReflexCategory, confidence: f32, rationale_tag: StaticReasonId }` | L4, L7 | yes (trust / debug) |
| `action_request` (outgoing) | `{ request_id, turn_id, task_id, capability, resource, actor_persona, active_grants, session_context, provenance_tags, intended_route: Option<RouteHint>, risk_class_hint, emitted_at }` | L5 (authoritative), L7 (audit) | no (never raw) |
| `memory_query` (outgoing) | `{ query_id, turn_id, scope: MemoryScope, query_text: String, confidence_threshold: f32, deadline: MonotonicTimestamp, max_hits: u8 }` | L2 | no |
| `repair_started` | `{ turn_id, cause: RepairCause, at, needs_upgrade_hint: Option<NeedsUpgradeHint> }` | all | yes |
| `repair_resolved` | `{ turn_id, resolution: RepairResolution, at }` | all | yes |
| `barge_in_detected` | `{ turn_id, at, cut_point: CutPoint{EndOfWord\|MidWord\|EndOfSentence} }` | Media (TTS), L3, L7 | yes |
| `tier_downgrade_notice` | `{ from_tier: PerfTier, to_tier: PerfTier, reason: DowngradeReason, effective_at }` | all | yes |

Ordering guarantee: within a `turn_id`, strict monotonic `seq`; `turn_begin` is always first, `turn_end` always last. Across turns, `seq` is globally monotonic but turn events may interleave.

---

## 5. Synchronous vs asynchronous boundaries

Every boundary is explicitly one or the other. No undefined behavior.

### 5.1 Synchronous (in-process, within budget)

- **Reflex classification** — `ReflexClassifier::classify(inputs, deadline)` MUST return within `T_reflex_sla = 150 ms` firm. Runs on a dedicated worker thread; cancellation-safe. A late result is discarded without being observed. If the classifier misses the SLA, L1 forces `AcknowledgeAndWait` and lets the deliberative path take over (see §3.5 of the system design).
- **State-machine transition** — `transition(current_state, event) -> (next_state, side_effects)` is a pure synchronous function. Runs on the event-loop thread. Must complete within a single `T_event_loop_tick` (5 ms Balanced/Full, 10 ms Lite).
- **Phrase selection** — `select_phrase(pool, intent, budget_remaining, recency) -> PhraseId` is synchronous; deterministic with a per-turn seed captured in events for replay.

### 5.2 Asynchronous — must-respond-or-empty (with deadline)

- **Memory query** — `MemoryAdapter::query(q)` returns a stream. L2 MUST emit one-or-more `memory_hit` events OR a `memory_query_empty` completion on or before `q.deadline = turn_begin + T_memory_deadline (150 ms)`. On miss, L1 proceeds with empty context and tags the turn `memory_miss=true`. L1 does NOT retry. L1 does NOT hold a fallback query.

### 5.3 Asynchronous — await event (no L1-side deadline cancellation)

- **Policy evaluation** — `PolicyAdapter::evaluate(req)` kicks off an async evaluation. The authoritative decision arrives as a `policy_decision` event. L1 transitions to `AwaitingPolicy` and blocks the turn's deliberative progress until the event arrives. If the wait exceeds `T_soft_deadline = 2000 ms`, L1 emits `policy_slow` telemetry but keeps waiting — policy is load-bearing and MUST NOT be short-circuited. Exception: if L5 reports `policy_engine.degraded`, L1 enters `DegradedNoPolicy`.
- **Approval flow** — `ApprovalPending` → `ApprovalResponse` is bounded only by user attention. L1 arms `T_approval_secondary_ack = 2000 ms` for a secondary ack but never cancels from the L1 side.
- **Route decision** — `RouterAdapter::request_route(hint, turn_id)` returns a `ChangeId` immediately. The `route_decision` arrives as an event. Missing past `T_soft_deadline` → `DegradedNoRouter`.

### 5.4 Fire-and-forget (non-blocking)

- **TTS enqueue** — `MediaAdapter::tts_enqueue(req)` returns a `ChangeId` immediately. Chunk completion / EOS / stall arrive as events.
- **TTS cut** — `MediaAdapter::tts_cut(turn_id, cut_point)` is synchronous signal issuance; actual cut completion is observed via `tts_chunk_done` / absence.

---

## 6. Typed contract suggestions

Pseudo-Rust for the Rust core; a pseudo-TS mirror at the bottom for `l1-timing-ts`. These are contract signatures, not implementations.

### 6.1 `InteractionEngine` — the single entry-point trait

```rust
pub trait InteractionEngine: Send + Sync {
    /// Start a new turn. Called by media on `speech_start` or by L7 on text submit.
    fn begin_user_turn(&self, input_kind: InputKind) -> Result<TurnId, L1Error>;

    /// Submit text for a turn (text-mode / push-to-talk post-ASR).
    fn submit_text(&self, turn_id: TurnId, text: String) -> Result<ChangeId, L1Error>;

    /// Cancel an in-flight turn (user escape / panel close).
    fn cancel(&self, turn_id: TurnId) -> Result<ChangeId, L1Error>;

    /// Subscribe to turn-scoped events. None = all turns.
    fn subscribe_state(&self, turn_id: Option<TurnId>) -> EventStream<L1Event>;

    /// Snapshot current state for consistency checks (L3 desync detection).
    fn current_state(&self, turn_id: TurnId) -> Option<TurnState>;
}
```

### 6.2 Adapter traits L1 depends on

```rust
pub trait PolicyAdapter: Send + Sync {
    fn evaluate(&self, req: ActionRequest) -> Result<Decision, PolicyEngineError>;
    fn subscribe(&self, filter: EventFilter) -> EventStream<L5Event>;
    fn snapshot_grants(&self, filter: GrantFilter) -> Vec<Grant>;
}

pub trait MemoryAdapter: Send + Sync {
    fn query(&self, q: MemoryQuery) -> EventStream<MemoryHitOrDone>;
    fn query_blocking(&self, q: MemoryQuery) -> Vec<MemoryHit>;  // one-shot; times out to empty
}

pub trait RouterAdapter: Send + Sync {
    fn request_route(&self, hint: RouteHint, turn_id: TurnId) -> Result<ChangeId, RouterError>;
    fn cancel(&self, turn_id: TurnId);
    fn subscribe(&self) -> EventStream<L4Event>;
}

pub trait PersonaAdapter: Send + Sync {
    fn current(&self) -> Arc<CompiledLanguage>;
    fn subscribe_swaps(&self) -> EventStream<PersonaEvent>;
}

pub trait MediaAdapter: Send + Sync {
    fn subscribe_vad(&self) -> EventStream<VadEvent>;
    fn subscribe_asr(&self) -> EventStream<AsrEvent>;
    fn tts_enqueue(&self, req: TtsEnqueue) -> Result<ChangeId, MediaError>;
    fn tts_cut(&self, turn_id: TurnId, cut_point: CutPoint);
    fn subscribe_tts(&self) -> EventStream<TtsEvent>;
}
```

### 6.3 `TurnState` enum — all 19 states

```rust
pub enum TurnState {
    Idle,
    Listening,
    PartialASR,
    ClassifyingIntent,
    AcknowledgingWait,
    Thinking,
    AwaitingPolicy,
    AwaitingApproval,
    RouteSelected,
    ExecutingDirect,
    ExecutingTool,
    Streaming,
    Speaking,
    Repairing,
    BargedIn,
    DegradedNoPolicy,
    DegradedNoMemory,
    DegradedNoRouter,
    Error,
}
```

### 6.4 `ReflexCategory` enum

```rust
pub enum ReflexCategory {
    DirectLocal,           // pure-text; no L5 call
    AcknowledgeAndWait,    // ack pool; no L5 call (phrases are data)
    Search,                // side-effecting → ActionRequest{BrowserOpen, BrowserReadPage}
    ToolPlan,              // side-effecting → ActionRequest{first step's capability}
    RemoteEscalation,      // side-effecting → ActionRequest{RouterEscalateRemote | RouterAllowRemoteWithPrivate}
    SafetyDeflection,      // no L5 call; uses Safety pool
    MemoryWrite,           // side-effecting → ActionRequest{MemoryWriteSession | Durable | ExtractedPref}
    ClarifyBackToUser,     // no L5 call; uses Clarify pool
}
```

### 6.5 `RouteHint` struct

```rust
pub struct RouteHint {
    pub privacy_posture: PrivacyPosture,
    pub tier_preference: PerfTier,
    pub tool_plan_sketch: Option<ToolPlanSketch>,
    pub latency_budget_remaining_ms: u32,
    pub intent_class: IntentClass,
    pub memory_confidence: f32,
    pub reflex_category: ReflexCategory,
}
```

### 6.6 `MemoryQuery` struct

```rust
pub struct MemoryQuery {
    pub query_id: QueryId,
    pub turn_id: TurnId,
    pub scope: MemoryScope,
    pub query_text: String,
    pub confidence_threshold: f32,
    pub deadline: MonotonicTimestamp,   // = turn_begin + T_memory_deadline (150 ms)
    pub max_hits: u8,                   // default 5
}
```

### 6.7 Supporting typedefs (referenced above)

```rust
pub enum InputKind { Voice, Text, PushToTalk }
pub enum PerfTier { Lite, Balanced, Full }
pub enum AckPool { Normal, Safety, Clarify, Repair }
pub enum AckIntentClass {
    Checking, Verifying, Thinking, Researching, ToolRunning,
    LongTask, Stalling, Deflecting, Clarifying, Repairing,
}
pub enum CutPoint { EndOfWord, MidWord, EndOfSentence, Anywhere }
pub enum TurnOutcome { Answered, Repaired, Denied, Cancelled, Error }
pub enum TransitionCause {
    Event(EventId), TimerFired(TimerId), Deny, NeedsUpgrade, MediaStall,
    EmergencyRevoke, GrantRevoked, PersonaSwap, TierDowngrade,
}
pub enum RepairCause {
    HardDeadline, MediaStall, PolicyDeny, RouterUnreachable,
    GrantRevoked, EmergencyRevoke, NeedsUpgrade, ClockSkew,
}
```

### 6.8 TS facade mirror (packages/l1-timing-ts)

```ts
export type TurnState =
  | "Idle" | "Listening" | "PartialASR" | "ClassifyingIntent"
  | "AcknowledgingWait" | "Thinking" | "AwaitingPolicy" | "AwaitingApproval"
  | "RouteSelected" | "ExecutingDirect" | "ExecutingTool" | "Streaming"
  | "Speaking" | "Repairing" | "BargedIn"
  | "DegradedNoPolicy" | "DegradedNoMemory" | "DegradedNoRouter" | "Error";

export type ReflexCategory =
  | "DirectLocal" | "AcknowledgeAndWait" | "Search" | "ToolPlan"
  | "RemoteEscalation" | "SafetyDeflection" | "MemoryWrite" | "ClarifyBackToUser";

export interface InteractionEngineFacade {
  beginUserTurn(inputKind: InputKind): Promise<TurnId>;
  submitText(turnId: TurnId, text: string): Promise<ChangeId>;
  cancel(turnId: TurnId): Promise<ChangeId>;
  subscribeState(turnId?: TurnId): AsyncIterable<L1Event>;
  currentState(turnId: TurnId): Promise<TurnState | null>;
}
```

---

## 7. Error vocabulary

### 7.1 `L1Error` — returned from `InteractionEngine` methods

```rust
#[derive(thiserror::Error, Debug)]
pub enum L1Error {
    #[error("no such turn: {0:?}")]
    NotFound(TurnId),

    #[error("turn already ended")]
    AlreadyEnded,

    #[error("reflex classifier exceeded T_reflex_sla")]
    ReflexTimeout,

    #[error("policy engine unreachable")]
    PolicyUnreachable,

    #[error("memory adapter missed T_memory_deadline")]
    MemoryTimeout,     // treated as empty; propagated as Error only on explicit query_blocking()

    #[error("router adapter unreachable")]
    RouterUnreachable,

    #[error("persona swap failed on safe boundary")]
    PersonaSwapFailed,

    #[error("media stalled past recovery budget")]
    MediaStalled,

    #[error("degraded: {0:?}")]
    Degraded(L1DegradedMode),

    #[error("internal: {0}")]
    Internal(String),
}
```

### 7.2 `L1DegradedMode` enum

```rust
pub enum L1DegradedMode {
    DegradedNoPolicy,   // L5 unreachable; only hardcoded-allowed reflex categories active
    DegradedNoMemory,   // L2 unreachable/slow; proceed with empty memory context
    DegradedNoRouter,   // L4 unreachable; fall back to direct-to-main local
    MinimumTrust,       // L6 compile fail; baked-in MinimumTrustPersona loaded
    Error,              // unrecoverable (ledger corrupt, clock critical)
}
```

Mapping invariant: every `L1DegradedMode` has a corresponding `TurnState` of the same name (except `MinimumTrust`, which is a persona-scoped state reflected via `compiled_persona_ready` payload and does not pin the turn-state machine in a single state).

---

## 8. Dependency expectations

### 8.1 L5 is load-bearing — never bypass

- Every side-effecting reflex category (Search, ToolPlan, RemoteEscalation, MemoryWrite, safety-deflection-with-tool) MUST emit an `ActionRequest` and wait for `policy_decision`. No exceptions.
- Only `DirectLocal` (pure text, local main model, no tools), `AcknowledgeAndWait` (ack pool is pre-approved data), `SafetyDeflection` (separate Safety pool), and `ClarifyBackToUser` (Clarify pool) short-circuit.
- If L5 is unreachable (`DegradedNoPolicy`), the side-effecting categories are rewritten to `SafetyDeflection` with `rationale_tag = PolicyUnavailable`. The side effect does NOT happen. Period.

### 8.2 L6 for phrase pools

- L1 consumes `CompiledLanguage` on `compiled_persona_ready`: `phrase_pool` (Normal), `safety_phrase_pool`, `hardcoded_allowed_deflections`, `ack_style`, `privacy_posture`, `reflex_tuning`.
- Persona drives phrase *content* and *tone*. L1 drives *selection* and *timing*.
- If L6 fails to deliver → MinimumTrustPersona baked into the build.

### 8.3 L4 for routing

- L1 builds `RouteHint`, calls `RouterAdapter::request_route(hint, turn_id)`, awaits `route_decision`.
- L4 owns tier selection, fallback, cost accounting. L1 consumes only the decision.
- On barge-in, L1 calls `RouterAdapter::cancel(turn_id)` to terminate the deliberative path (see open question §10.4 — cancel path must be frozen on L4's surface).

### 8.4 L2 for memory — time-bounded oracle

- L1 issues `MemoryQuery` with `deadline = turn_begin + T_memory_deadline (150 ms)`.
- L2 MUST respond with `memory_hit`(s) or `memory_query_empty` on or before deadline.
- Late hits are discarded; L1 does NOT retry.

### 8.5 Media engine for VAD / ASR / TTS

- L1 owns the contract, not the implementation.
- VAD drives `Listening` entry and `BargedIn` transitions.
- ASR drives `PartialASR` and `ClassifyingIntent` transitions.
- TTS receives enqueues with `InterruptionPolicy` and emits chunk/eos/stall events.

### 8.6 Never bypass L5

This is the single hardest invariant in L1. Every code path that constructs an `ActionRequest` MUST end with either (a) `policy_decision` observed, or (b) degraded-mode rewrite to a non-side-effecting category. There is no third path.

---

## 9. Implementation notes

### 9.1 Package layout

- **packages/l1-timing/** (Rust) — the authoritative event-loop thread. Contains `l1-core` (state machine + transition function + typed events), `l1-reflex` (classifier strategies: rule-only P0, distilled head P1), `l1-phrases` (ack pool + selection + recency ring), `l1-adapters` (trait definitions), `l1-test-stubs` (fake adapters for cross-layer integration tests).
- **packages/l1-timing-ts/** (TS) — thin typed facade over the Tauri IPC surface. Mirrors `InteractionEngine` as `InteractionEngineFacade`; re-exports `TurnState` / `ReflexCategory` / `L1Event` shapes. No business logic.
- **packages/event-bus/** (co-owned) — per monorepo §2, L1 co-owns this crate with L5. Hosts the typed `Event` enum, `source_layer` / `seq` / `change_id` conventions, projection rules for the webview.

### 9.2 Threading model

- Single event-loop thread runs the state machine. All `transition()` calls happen here.
- Reflex classifier runs on a dedicated worker thread; cancellation-safe; late results discarded.
- Adapter event streams (`PolicyAdapter::subscribe`, `MemoryAdapter::query`, `RouterAdapter::subscribe`, `MediaAdapter::subscribe_*`) feed the event-loop thread via a multi-producer queue.
- Timer events are scheduled via `tokio::time::sleep` and delivered into the same queue as `TimerFired(TimerId)` events, preserving replayability.

### 9.3 Clock discipline

- All TTL-bound timing uses `MonotonicTimestamp` (tokio monotonic clock). Wall clock is cosmetic.
- On suspend/resume > 10 s, pending turns transition to Repairing.
- Per-turn seed for phrase selection is captured in the event log; replay reconstructs selections deterministically.

### 9.4 Tauri bridge

- `turn.*` commands (`begin_user_turn`, `submit_text`, `cancel`) route through X3 §2.2 command surface; each returns a `ChangeId` for UI correlation against the subsequent event.
- Webview event projection is coalesced on Lite per X3 §8.3 (`partial_transcript` and `turn_state_change` specifically).

### 9.5 Build-order — first action

1. `l1-core` state machine crate + `L1Event` enum + `transition()` pure function. Zero adapter deps.
2. `AckPhrasePool` + selection + recency ring. Default persona's pool ships hardcoded for bring-up.
3. `ReflexClassifier` trait + rule-only strategy (P0). Distilled head plugs in at P1.
4. Adapter traits (§6.2) + fake impls in `l1-test-stubs`.
5. Timing-budget harness: synthetic-turn generator + latency-injected adapters.

---

## 10. Open items blocking implementation

These are flagged per the caller's constraint. Each must be resolved before the contract in §6 can be declared frozen.

1. **`NeedsUpgrade` encoding on `Decision`.** L5 defines both `Decision::Deny { reason: NeedsUpgrade }` and a top-level `Decision::NeedsUpgrade { suggested_preset }`. Which arrives in practice? L1's handler must pattern-match exactly one. **Proposed default:** honor top-level `Decision::NeedsUpgrade` as canonical; never synthesize from `Deny`. **Blocks:** §7.1 handler logic in L1 for `Repairing{cause=NeedsUpgrade}` and L7 upgrade-UX trigger.

2. **Persona-swap safe-boundary strictness.** Strict (only `Idle`) vs Relaxed (Idle + end-of-Speaking + end-of-AcknowledgingWait). Strict = predictable but sometimes seconds-delayed. Relaxed = snappier but mid-turn style drift possible. **Proposed default:** Relaxed, per system design §7.5. **Blocks:** `PersonaAdapter::subscribe_swaps` contract, `L1Error::PersonaSwapFailed` semantics, L5 coupling for grant-revocation consistency.

3. **Sub-budget defaults.** The doctrine budgets (250 / 800 / 2000 / 4000 ms) are locked. The sub-budgets — `T_reflex_sla = 150 ms`, `T_memory_deadline = 150 ms`, `T_barge_in_cut = 150 ms`, `T_tts_chunk_inactivity = 500 ms`, `T_repair_ack = 2000 ms`, `T_event_loop_tick = 5 ms / 10 ms` — are this document's defaults and need Don's sign-off. **Proposed default:** values as listed. **Blocks:** property-test thresholds in §14 of the system design, acceptance-criteria evaluation, and tier-awareness downgrade triggers.

---

## Cross-references

- System design: file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md
- L5 policy contract: file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md
- L4 routing: file:///C:/Users/dbhav/Projects/aether-planning/plans/L4_model_router_system_design.md
- L2 memory: file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_memory_kernel_system_design.md
- L6 persona: file:///C:/Users/dbhav/Projects/aether-planning/plans/L6_persona_compiler_system_design.md
- L3 presence: file:///C:/Users/dbhav/Projects/aether-planning/plans/L3_presence_engine_system_design.md
- Integration notes: file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_L4_L5_L7_integration_notes.md
- Target package: file:///C:/Users/dbhav/Projects/aether/packages/l1-timing/
- TS facade: file:///C:/Users/dbhav/Projects/aether/packages/l1-timing-ts/
- Co-owned event bus: file:///C:/Users/dbhav/Projects/aether/packages/event-bus/
