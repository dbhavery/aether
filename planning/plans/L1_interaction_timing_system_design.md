---
status: draft
date: 2026-04-18
layer: L1 (interaction timing + embedded reflex router)
mode: system design (implementation-grade)
upstream:
  - 01_product_doctrine.md (§"Must-own layers" #1, §"Desktop framework doctrine")
  - MASTER_OUTLINE_TREE.md §5 "Real-time interaction strategy", §6 "Core system architecture"
  - plans/00_ORCHESTRATION_MAP.md (§1 7-layer reconciliation, §6 dependency DAG)
  - plans/L1_interaction_timing.md (upstream plan this doc elaborates)
  - plans/L5_policy_engine_system_design.md (authoritative policy contract: PolicyEngine trait, Decision, ActionRequest, events)
  - plans/X3_tauri_architecture.md §2 command surface, §3 event bus bridge, §4 layer map, §8 tier compat
  - 09_realtime_interaction.md (timing targets, reflex/deliberative split)
  - 08_system_architecture.md (six engines, event bus)
  - 18_model_router_spec.md + plans/L4_model_router.md (tier abstraction, routing inputs)
  - plans/L2_memory_kernel.md (memory_hit event shape, <150 ms reflex hit budget)
  - plans/L3_presence_engine.md (consumer of turn-state bus)
downstream_consumers:
  - plans/L2_memory_kernel.md (L1 is a memory-query caller with a deadline contract)
  - plans/L3_presence_engine.md (subscribes to turn_state_change, never called directly by L1)
  - plans/L4_model_router.md (consumes route_hint, returns route_decision)
  - plans/L6_persona_compiler.md (L1 consumes compiled phrase pools, acknowledgment style)
  - plans/L7_trust_ux_onboarding.md (L1's DegradedNoPolicy / repair UI surfaces)
scope_of_this_document:
  - Implementation blueprint for the L1 engine: turn-state machine, reflex classifier, ack phrase pool, timing budgets, adapter traits
  - Typed pseudocode + state diagrams INSIDE this markdown; no .rs / .sql files
  - Freezes the L1 contract that L2 / L3 / L4 / L7 stub against
non_goals:
  - Writing Rust crates, scaffolding, migrations, or tests
  - Resolving doctrine conflicts (flagged in §16 Open Questions)
  - Owning policy decisions (L5), memory retrieval (L2), routing execution (L4), presence animation (L3)
---

# L1 — Interaction Timing Engine (with embedded reflex router) — System Design

> The plan (file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing.md) says *what* L1 owns. This document says *how* L1 is built. Downstream layers (L2, L3, L4, L7) should stub against the contracts frozen here (§5, §6, §7, §13).
>
> Canonical planning root: file:///C:/Users/dbhav/Projects/aether-planning/
> Target package home (X1-dependent): file:///C:/Users/dbhav/Projects/aether/packages/l1-interaction/ (Rust) + file:///C:/Users/dbhav/Projects/aether/packages/l1-interaction-ts/ (typed event/command bindings)

---

## 1. Purpose and scope

### 1.1 What L1 owns

- **Turn-state machine.** The single source of truth for the felt state of a turn (Idle / Listening / Thinking / Speaking / Repairing / ...). Every other engine reads this bus; no engine mutates it.
- **Embedded reflex router.** The fast-path classifier that decides per-turn category (direct-local, acknowledge-and-wait, search, tool-plan, remote-escalation, safety-deflection, memory-write, clarify-back-to-user). Reflex is *inside* L1 per canonical 7-layer model (plans/00_ORCHESTRATION_MAP.md §1).
- **Acknowledgment phrase pool.** Structure, selection algorithm, anti-repetition counters. Phrase *content* comes from L6's compiled persona; L1 owns the scheduling and the pool mechanics.
- **Timing contracts and budget enforcement.** The 250 ms / 800 ms / 2000 ms / 4000 ms doctrine budgets (09_realtime_interaction.md). Budget-breach triggers: auto-ack on 800 ms, secondary-ack on 2000 ms, repair on 4000 ms.
- **Turn-boundary / VAD integration, barge-in, and repair.** L1 schedules TTS chunks against the audio clock and owns the graceful-cut rules.
- **Emission of the turn-state bus.** `turn_begin`, `turn_end`, `partial_transcript`, `intent_hint`, `route_hint`, `ack_phrase`, `turn_state_change`, `reflex_classification`, `repair_started`, `repair_resolved`, `barge_in_detected`, `tier_downgrade_notice`.
- **Construction of L5 `ActionRequest` envelopes** for every reflex category that would side-effect (tool-plan, memory-write, remote-escalation, safety-deflection-with-tool). Construction only — L5 decides.

### 1.2 What L1 does NOT own

- **Policy decisions.** L5 owns `evaluate()`, `Decision`, `DenyReason`, approval workflow. L1 calls into `PolicyEngine::evaluate` and honors the result.
- **Memory retrieval.** L2 owns ranking, storage, provenance. L1 issues time-bounded `MemoryQuery` and consumes `memory_hit`.
- **Routing execution.** L4 owns tier selection, fallback, cost accounting. L1 builds a `RouteHint` and consumes `route_decision`.
- **Presence animation.** L3 subscribes to L1's turn-state bus and maps to avatar behavior. L1 never calls L3.
- **TTS synthesis / STT inference.** Media engine. L1 owns only the streaming-chunk and interrupt-handling *contract*.
- **Persona content.** L6 compiles personas and delivers phrase pools + acknowledgment style to L1.
- **Audit log.** L5 owns it. L1 tags every emitted event with `change_id` so audit can join back.

### 1.3 Boundary invariants

1. **Every side-effecting reflex category MUST produce an `ActionRequest` and wait for `PolicyDecision`.** No exceptions. Direct-local (pure text) and safety-deflection using a hardcoded-allow phrase pool are the only categories that can short-circuit.
2. **L1 never holds an authoritative copy of a grant.** It reads snapshots via `PolicyEngine::snapshot_grants` if needed, but the evaluator is the gate.
3. **L1 owns the turn clock.** All timing budgets are measured against a single `MonotonicTimestamp` taken at turn_begin. Wall-clock is cosmetic.
4. **L1 runs in Rust core** (per X3 §4). The webview observes turn state; it does not drive it.

---

## 2. Turn-state machine

### 2.1 State list

Each state has **entry conditions**, **exit conditions**, **allowed transitions**, **timers running**, **events emitted on entry**, and **events emitted on exit**.

| # | State | Entry | Exit | Timers running | Events on entry |
|---|---|---|---|---|---|
| 1 | `Idle` | Boot, or `turn_end` observed | `speech_start` / `text.submit` command / push-to-talk | none | `turn_state_change{Idle}` |
| 2 | `Listening` | `speech_start` (VAD) or mic-open | `final_transcript` OR silence > VAD tail | none initially; turn-clock starts on first partial | `turn_begin`, `turn_state_change{Listening}` |
| 3 | `PartialASR` | first `partial_transcript` event from media | every new partial OR `final_transcript` | **T_first_ack (250 ms)** target for visible state transition | `partial_transcript` forwarded to bus |
| 4 | `ClassifyingIntent` | `final_transcript` OR confident partial | reflex verdict emitted | **T_reflex_sla (150 ms)** hard cap on classifier | none (internal) |
| 5 | `AcknowledgingWait` | reflex chose `acknowledge-and-wait` OR budget-breach auto-ack (800 ms without direct answer) | ack phrase TTS completed OR interrupted | **T_ack_deadline (800 ms since turn_begin)** | `ack_phrase`, `turn_state_change{AcknowledgingWait}` |
| 6 | `Thinking` | reflex issued a deliberative path (directly or post-ack) | `route_decision` received from L4 | **T_soft_deadline (2000 ms)**, **T_hard_deadline (4000 ms)** | `turn_state_change{Thinking}` |
| 7 | `AwaitingPolicy` | L1 emitted `ActionRequest` and is blocked on `PolicyDecision` | `PolicyDecision{Allow\|Deny\|DraftOnly\|NeedsUpgrade}` OR `ApprovalPending` received | policy-wait timer (budget-shared with T_soft_deadline) | `turn_state_change{AwaitingPolicy}` |
| 8 | `RouteSelected` | `PolicyDecision{Allow}` received AND `route_decision` received | transitions to Executing* | none | `turn_state_change{RouteSelected}` |
| 9 | `ExecutingDirect` | RouteSelected with direct-local route | answer streaming begins | T_hard_deadline still running | `turn_state_change{ExecutingDirect}` |
| 10 | `ExecutingTool` | RouteSelected with tool-plan route AND L5 Allow | tool execution reports completion OR error OR user barge-in | T_hard_deadline still running | `turn_state_change{ExecutingTool}` |
| 11 | `AwaitingApproval` | L5 emitted `ApprovalPending` (synonym path from AwaitingPolicy) | `ApprovalResponse` arrives | approval-wait timer (indefinite but bounded by user intent); **secondary ack fires at 2000 ms** | `turn_state_change{AwaitingApproval}`, (may emit `ack_phrase` "still waiting on your go-ahead") |
| 12 | `Streaming` | first token / audio chunk produced | EOS / barge-in / cancel | streaming inactivity timer (500 ms) | `turn_state_change{Streaming}` |
| 13 | `Speaking` | TTS producing audio for current answer | TTS EOS OR barge-in | viseme-alignment timer | `turn_state_change{Speaking}` |
| 14 | `Repairing` | T_hard_deadline elapsed without result, OR media stall, OR L5 `Deny`, OR L4 unreachable | repair phrase TTS completes AND new user input OR auto-resolved | repair budget (2000 ms to emit repair phrase) | `repair_started`, `turn_state_change{Repairing}` |
| 15 | `BargedIn` | VAD `speech_start` during Speaking OR Streaming OR AcknowledgingWait | TTS cut completed AND back to Listening | barge-in cut budget (150 ms max) | `barge_in_detected`, `turn_state_change{BargedIn}` |
| 16 | `DegradedNoPolicy` | L5 heartbeat missed OR `PolicyEngineError::Degraded` | L5 recovery event | degraded-mode indicator | `turn_state_change{DegradedNoPolicy}`, `tier_downgrade_notice` |
| 17 | `DegradedNoMemory` | L2 unresponsive past deadline OR L2 `Degraded` | L2 recovery | none | `turn_state_change{DegradedNoMemory}` |
| 18 | `DegradedNoRouter` | L4 unresponsive OR no `route_decision` | L4 recovery | none | `turn_state_change{DegradedNoRouter}`, `tier_downgrade_notice` |
| 19 | `Error` | unrecoverable local fault (ledger corrupt, clock skew critical) | user dismiss + reinit | none | `turn_state_change{Error}`, `repair_started` |

### 2.2 Transition diagram (ASCII)

```
                        [Idle]
                          | speech_start / text.submit
                          v
                     [Listening]
                          | first partial
                          v
                    [PartialASR]----(reflex can fire on partial)
                          | final_transcript
                          v
                  [ClassifyingIntent]
                 /     |      |         \
                /      |      |          \
  reflex=direct-local  |      |        reflex=tool-plan / remote / memory-write / safety-deflection
                |      |      |                             |
                |      |      | reflex=acknowledge-and-wait |
                |      |      v                             v
                |      |  [AcknowledgingWait]--->[AwaitingPolicy]<---(emit ActionRequest to L5)
                |      |        |                   |         \
                |      |        | ack TTS done      |          +--> [AwaitingApproval] (ApprovalPending)
                |      |        v                   |                        |
                |      |     [Thinking]<------------+ (PolicyDecision{Allow})
                |      |        |                                            |
                |      |        | route_decision arrives                     |
                |      +------> [RouteSelected] <----------------------------+
                |               /       \
                v              v         v
        [ExecutingDirect]  [ExecutingTool]
                \              /
                 v            v
                  [Streaming] --> [Speaking] --> (EOS) --> [Idle]
                       ^              |
                       |              v
                       +-------- [BargedIn] --> [Listening]

  Any state: T_hard_deadline elapsed || media_stall || L5 Deny || L4 unreachable
       ==> [Repairing] ==> (user input) ==> [ClassifyingIntent]

  Any state: L5 Degraded      ==> [DegradedNoPolicy]  (restricted surface)
  Any state: L2 Degraded      ==> [DegradedNoMemory]  (tag turn, continue)
  Any state: L4 Degraded      ==> [DegradedNoRouter]  (tier_downgrade_notice)
```

### 2.3 Allowed transitions (table, partial — exhaustive table lives in the implementation)

| From | To | Trigger |
|---|---|---|
| Idle | Listening | `speech_start` or `turn.submit_text` |
| Listening | PartialASR | first `partial_transcript` |
| PartialASR | ClassifyingIntent | `final_transcript` or confident partial + VAD silence |
| ClassifyingIntent | AcknowledgingWait | reflex = acknowledge-and-wait, OR T_ack_deadline hits before reflex finishes |
| ClassifyingIntent | ExecutingDirect | reflex = direct-local AND no side-effect |
| ClassifyingIntent | AwaitingPolicy | reflex = {tool-plan, remote-escalation, memory-write, safety-deflection-with-tool} |
| AcknowledgingWait | Thinking | ack TTS done AND deliberative path chosen |
| AwaitingPolicy | RouteSelected | `PolicyDecision{Allow}` |
| AwaitingPolicy | AwaitingApproval | `ApprovalPending` |
| AwaitingPolicy | Repairing | `PolicyDecision{Deny}` |
| AwaitingApproval | RouteSelected | `ApprovalResponse{Allow*}` |
| AwaitingApproval | Repairing | `ApprovalResponse{Deny}` OR `GrantRevoked` on the pending grant |
| RouteSelected | ExecutingDirect | `route_decision.tier ∈ {fast, main}` AND no tool |
| RouteSelected | ExecutingTool | `route_decision.tool_plan.is_some()` |
| ExecutingDirect | Streaming | first token emitted |
| ExecutingTool | Streaming | tool result ready for answer synthesis |
| Streaming | Speaking | first TTS chunk emitted |
| Speaking | Idle | TTS EOS + answer committed |
| Speaking | BargedIn | VAD `speech_start` |
| BargedIn | Listening | TTS cut complete |
| Any | Repairing | hard deadline elapsed / media stall / deny / unreachable |
| Repairing | ClassifyingIntent | repair resolved + new user input |
| Any | Error | unrecoverable fault |

### 2.4 Determinism rules

- **Single authoritative transition function.** Every transition is driven by a typed event + current state. No ambient reads. A property test (§14) asserts: for any `(state, event)` pair, `transition(state, event)` returns the same next-state deterministically.
- **Timers are events too.** Timer expiry produces an internal event (`TimerFired(TimerId)`), which feeds the same transition function. This preserves replayability.
- **Turn-scoped state only.** L1 does not carry cross-turn state except the ack-phrase recency ring (§8).

---

## 3. Embedded reflex router

### 3.1 Inputs

```rust
pub struct ReflexInputs {
    pub turn_id: TurnId,
    pub partial_or_final_text: String,         // from media engine
    pub is_final: bool,
    pub short_memory_context: Vec<MemoryHit>,  // L2 hits received within T_memory_deadline
    pub active_persona_posture: PersonaPosture,// from L6 (privacy posture, tone, caution)
    pub current_policy_posture: PolicyPosture, // from L5 (preset, active grants snapshot hash)
    pub budget_remaining: Duration,            // = T_hard_deadline - (now - turn_begin)
    pub tier: PerfTier,                        // Lite / Balanced / Full
}
```

### 3.2 Decision categories → L5 capability mapping

| Reflex category | Side-effecting? | Capability emitted in `ActionRequest` | Notes |
|---|---|---|---|
| `DirectLocal` | No | none (no L5 call) | Pure-text reply using local main model; never touches files, browser, memory-write. |
| `AcknowledgeAndWait` | No | none (ack uses pre-approved phrase pool) | Ack phrases are *data*, not tools. The ack itself is not side-effecting. |
| `Search` | Yes | `BrowserOpen` + `BrowserReadPage` at minimum (scope narrowed by route) | Exact capability set depends on source (web vs local corpus). |
| `ToolPlan` | Yes | first step's capability (e.g. `FilesRead`, `EmailDraft`) | Multi-step plans may use `policy.preview_plan` (L5 §5.2, P2) to bundle. |
| `RemoteEscalation` | Yes | `RouterEscalateRemote` (+ possibly `RouterAllowRemoteWithPrivate` if private context present) | L5 privacy-posture gate runs here (L5 §10). |
| `SafetyDeflection` | No (uses separate safety phrase pool, §8.3) | none | A deflection is an L1 decision to *not* act. It still emits `reflex_classification{SafetyDeflection}` for audit. |
| `MemoryWrite` | Yes | `MemoryWriteSession` / `MemoryWriteDurable` / `MemoryWriteExtractedPref` | L1 classifies *intent*; actual write is L2 post-`Allow`. |
| `ClarifyBackToUser` | No | none | Uses a pre-approved clarification phrase from the persona pool. |

Invariant: if the category is side-effecting, L1 MUST NOT dispatch the action. L1 constructs the `ActionRequest`, emits it, transitions to `AwaitingPolicy`, and waits.

### 3.3 Classifier implementation

Two interchangeable strategies behind one trait:

```rust
pub trait ReflexClassifier: Send + Sync {
    fn classify(&self, inputs: &ReflexInputs, deadline: MonotonicTimestamp) -> ReflexVerdict;
}

pub struct ReflexVerdict {
    pub category: ReflexCategory,
    pub confidence: f32,                         // 0.0..1.0
    pub rationale_tag: StaticReasonId,           // for audit/explain
    pub suggested_route_hint: RouteHint,         // handed to L4
    pub memory_write_proposal: Option<MemoryWriteProposal>,
    pub ack_intent_class: Option<AckIntentClass>,// drives phrase pool selection
}
```

**Strategies:**
1. **Rule-only (P0):** hand-coded patterns + keyword + memory-confidence heuristics. Non-ML. Predictable. Wins on latency.
2. **Distilled classifier head (P1+):** small local head (classifier on top of Gemma 4 2B embeddings, or distilled task-specific model). Runs under T_reflex_sla.
3. **Hybrid (P2+):** rules run first; if confidence < threshold, distilled head tie-breaks — *but only if budget remains*.

### 3.4 Pseudocode

```rust
fn classify(inputs: &ReflexInputs, deadline: MonotonicTimestamp) -> ReflexVerdict {
    // Stage 0 — budget check. If we've already blown the reflex SLA, force acknowledge-and-wait.
    if now_monotonic() >= deadline {
        return ReflexVerdict {
            category: ReflexCategory::AcknowledgeAndWait,
            confidence: 1.0,
            rationale_tag: StaticReasonId::ReflexBudgetExceeded,
            suggested_route_hint: RouteHint::default_for_tier(inputs.tier),
            memory_write_proposal: None,
            ack_intent_class: Some(AckIntentClass::Thinking),
        };
    }

    // Stage 1 — safety pre-screen. Hardcoded rules only; no remote call.
    if matches_safety_rule(&inputs.partial_or_final_text, &inputs.active_persona_posture) {
        return verdict(ReflexCategory::SafetyDeflection, 1.0, StaticReasonId::SafetyPrescreen);
    }

    // Stage 2 — intent inference (rule or classifier).
    let intent = infer_intent(inputs);

    // Stage 3 — map intent to category, with memory + posture modifiers.
    match intent {
        Intent::Greeting | Intent::SmallTalk | Intent::SimpleFactFromMemory
            => verdict(ReflexCategory::DirectLocal, intent.confidence, StaticReasonId::DirectLocal),

        Intent::SearchNeeded => verdict(ReflexCategory::Search, intent.confidence, StaticReasonId::SearchNeeded),

        Intent::ToolTask(plan_sketch)
            => verdict_with_plan(ReflexCategory::ToolPlan, plan_sketch),

        Intent::HardReasoning | Intent::LongDraft => {
            // Privacy posture gate: if private context present and persona = Strict, stay local.
            if has_private_context(&inputs.short_memory_context)
               && inputs.active_persona_posture.privacy == PrivacyPosture::Strict {
                return verdict(ReflexCategory::DirectLocal, intent.confidence,
                               StaticReasonId::PrivateForceLocal);
            }
            verdict(ReflexCategory::RemoteEscalation, intent.confidence, StaticReasonId::HardEscalate)
        }

        Intent::MemoryCommit => verdict(ReflexCategory::MemoryWrite, intent.confidence, StaticReasonId::MemoryIntent),

        Intent::Ambiguous => verdict(ReflexCategory::ClarifyBackToUser, 1.0, StaticReasonId::AmbiguousInput),

        _ if intent.confidence < REFLEX_MIN_CONFIDENCE
            => verdict(ReflexCategory::AcknowledgeAndWait, 1.0, StaticReasonId::LowConfidence),

        _ => verdict(ReflexCategory::AcknowledgeAndWait, 0.5, StaticReasonId::Fallback),
    }
}
```

### 3.5 Classifier SLA

- **T_reflex_sla = 150 ms firm.** If exceeded, the scheduler forces `AcknowledgeAndWait` and lets the deliberative path take over. Ack fires at ≤800 ms since `turn_begin`.
- The classifier runs on a dedicated worker; it is cancellation-safe. A classification that finishes late after the budget elapsed is discarded (its verdict is never observed).

### 3.6 Explicit rule

**Reflex is a classifier, not an executor.** Every side-effecting category produces an `ActionRequest` for L5. L1 MUST NOT run a tool, write memory, or call a remote provider directly — even inside P0. The one exception is the ack/safety phrase pools, which are *data* pre-approved at persona-compile time.

---

## 4. Timing contracts and budgets

All budgets measured from `turn_begin` unless stated. Every budget has a label (firm vs best-effort) and a missed-trigger.

| Budget | Value | Label | What triggers when missed |
|---|---|---|---|
| **T_first_state_change** | 250 ms | firm | On miss, emit `turn_state_change{Thinking}` immediately; log p95-watch event. L3 must reflect transition in ≤1 render frame. |
| **T_ack_deadline** | 800 ms | firm | If no `direct-local` answer and no ack yet → auto-select ack phrase and emit `ack_phrase` + `turn_state_change{AcknowledgingWait}`. Zero-silent-turn invariant. |
| **T_reflex_sla** | 150 ms | firm | Force `AcknowledgeAndWait` category; discard late classifier result. |
| **T_memory_deadline** | 150 ms | firm | L2 must respond with `memory_hit` or empty. On miss, L1 proceeds with empty context and tags turn `memory_miss=true`. |
| **T_soft_deadline** | 2000 ms | best-effort | Emit secondary ack ("still looking — almost there") using a different intent class. Avatar holds Working state. |
| **T_hard_deadline** | 4000 ms | firm | Enter `Repairing` OR emit explicit progress update; user can interrupt. `repair_started` event emitted. |
| **T_barge_in_cut** | 150 ms | firm | VAD speech-start → TTS mute complete within budget. On miss, emit `barge_in_miss` telemetry; force cut anyway. |
| **T_policy_wait** | shared with T_soft_deadline | best-effort | If `PolicyDecision` not received by 2000 ms, L1 emits `policy_slow` telemetry and keeps waiting (policy is load-bearing; don't short-circuit). Approval flow explicitly excepted — user attention drives it. |
| **T_approval_secondary_ack** | 2000 ms after `ApprovalPending` | best-effort | Emit "still waiting on your go-ahead" ack. |
| **T_tts_chunk_inactivity** | 500 ms | best-effort | Emit `media_stall` telemetry; if sustained 1500 ms, transition to Repairing. |
| **T_event_loop_tick** | 5 ms | firm | Scheduler wakeup; late ticks logged (jitter probe). On sustained overrun, emit `tier_downgrade_notice`. |
| **T_repair_ack** | 2000 ms | firm (inside Repairing) | Repair phrase MUST complete within 2000 ms of `repair_started`. If exceeded, cut to blunt fallback ("Sorry — let's try that again.") |

Notes:
- All firm budgets include watchdog timers that write a structured warning event on overrun; the budget still applies.
- T_hard_deadline is the trigger for `repair_started`, not for cancellation. Cancellation of the deliberative path is a separate concern owned by L4; L1 emits `turn.cancel` via L4's command surface.
- Lite tier coalesces the event-loop tick to 10 ms (§11); firm budgets still apply.

---

## 5. Event contracts L1 emits

All events live on the Rust-internal bus (08_system_architecture.md) with the X3 §3.2 projection convention: every event carries `source_layer`, `change_id`, `seq`.

### 5.1 Event catalog

```rust
pub enum L1Event {
    TurnBegin(TurnBeginEvent),
    TurnEnd(TurnEndEvent),
    PartialTranscript(PartialTranscriptEvent),   // forwarded with L1 timing annotation
    IntentHint(IntentHintEvent),
    RouteHint(RouteHintEvent),
    AckPhrase(AckPhraseEvent),
    TurnStateChange(TurnStateChangeEvent),
    ReflexClassification(ReflexClassificationEvent),
    ActionRequestOutgoing(ActionRequestOutgoingEvent),  // L1 submits, L5 receives
    MemoryQueryOutgoing(MemoryQueryOutgoingEvent),
    RepairStarted(RepairStartedEvent),
    RepairResolved(RepairResolvedEvent),
    BargeInDetected(BargeInDetectedEvent),
    TierDowngradeNotice(TierDowngradeNoticeEvent),
}
```

### 5.2 Per-event shape

| Event | Fields | Emitter | Subscribers | Projected to webview? |
|---|---|---|---|---|
| `turn_begin` | `turn_id: TurnId`, `input_kind: InputKind{Voice\|Text\|PushToTalk}`, `started_at: MonotonicTimestamp`, `persona_id: PersonaId`, `tier: PerfTier`, `change_id`, `seq` | L1 | L2, L3, L4, L5 (for `turn_id` correlation), L7 | yes |
| `turn_end` | `turn_id`, `ended_at`, `outcome: TurnOutcome{Answered\|Repaired\|Denied\|Cancelled\|Error}`, `change_id`, `seq` | L1 | all | yes |
| `partial_transcript` | `turn_id`, `text: String`, `stability: f32`, `at: MonotonicTimestamp`, `change_id`, `seq` | L1 (forwarded from media; L1 adds turn correlation) | L2, L4, L7 | yes (debounced on Lite) |
| `intent_hint` | `turn_id`, `intent_class: IntentClass`, `confidence: f32`, `derived_at`, `change_id`, `seq` | L1 reflex | L4 (routing input), L7 (debug overlay) | yes (low-freq) |
| `route_hint` | `turn_id`, `privacy_posture: PrivacyPosture`, `tier_preference: PerfTier`, `tool_plan_sketch: Option<ToolPlanSketch>`, `latency_budget_remaining_ms: u32`, `change_id`, `seq` | L1 | L4 | no (internal, L4 consumes then emits `route_decision`) |
| `ack_phrase` | `turn_id`, `phrase_id: PhraseId`, `text: String`, `intent_class: AckIntentClass`, `pool: AckPool{Normal\|Safety}`, `scheduled_at`, `change_id`, `seq` | L1 | Media (TTS), L3 (presence), L7 | yes |
| `turn_state_change` | `turn_id`, `from: TurnState`, `to: TurnState`, `at: MonotonicTimestamp`, `cause: TransitionCause`, `change_id`, `seq` | L1 | L3 (primary), L7, L5 (audit correlation) | yes |
| `reflex_classification` | `turn_id`, `category: ReflexCategory`, `confidence: f32`, `rationale_tag: StaticReasonId`, `change_id`, `seq` | L1 | L4, L7 | yes (trust center / debug) |
| `action_request_outgoing` | `request_id: RequestId`, `turn_id`, `capability: Capability`, `resource: ResourceScope`, `actor_persona: PersonaId`, `provenance_tags: Vec<ProvenanceTag>`, `intended_route: RouteHint`, `emitted_at`, `change_id`, `seq` | L1 | L5 (authoritative consumer), L7 (audit) | no (L5 rules — never projected raw) |
| `memory_query_outgoing` | `query_id: QueryId`, `turn_id`, `scope: MemoryScope`, `query_text: String`, `confidence_threshold: f32`, `deadline: MonotonicTimestamp`, `change_id`, `seq` | L1 | L2 | no |
| `repair_started` | `turn_id`, `cause: RepairCause`, `at: MonotonicTimestamp`, `change_id`, `seq` | L1 | all | yes |
| `repair_resolved` | `turn_id`, `resolution: RepairResolution`, `at`, `change_id`, `seq` | L1 | all | yes |
| `barge_in_detected` | `turn_id`, `at`, `cut_point: CutPoint{EndOfWord\|MidWord}`, `change_id`, `seq` | L1 | Media (TTS), L3, L7 | yes |
| `tier_downgrade_notice` | `from_tier: PerfTier`, `to_tier: PerfTier`, `reason: DowngradeReason`, `effective_at`, `change_id`, `seq` | L1 (on sustained tick overrun; cooperatively with `core.health`) | all | yes |

### 5.3 ChangeId / seq / source_layer conventions

Per X3 §3.2:
- `source_layer = SourceLayer::L1` on every event.
- Global monotonic `seq` counter per Rust process (shared with L5 and other engines).
- Every write-class command to L1 (`turn.begin_user_turn`, `turn.submit_text`, `turn.cancel`) returns a `ChangeId` the UI can correlate against the subsequent event.

### 5.4 Ordering guarantees

- Within a `turn_id`: strict monotonic `seq`. `turn_begin` precedes any other L1 event for that turn; `turn_end` is the last.
- Across turns: `seq` is globally monotonic but turn events can interleave (multiple pending turns in text mode).
- `action_request_outgoing → policy_decision` is strictly ordered by the bus (L5 §4.2).

---

## 6. Events L1 subscribes to

| Event | Source | Handler action |
|---|---|---|
| `policy_decision` (L5) | L5 | If `Allow`: transition AwaitingPolicy → RouteSelected, carry `grant_ref`. If `Deny{reason}`: transition to Repairing, emit deflection phrase (pool=Safety if reason is hardcoded-block). If `DraftOnly`: route to draft path (Streaming with `is_draft=true`). If `NeedsUpgrade`: transition to Repairing with resolution hint for L7 upgrade-UX. |
| `approval_pending` (L5) | L5 | AwaitingPolicy → AwaitingApproval. Arm T_approval_secondary_ack. |
| `approval_response` (L5, internal echo) | L5 | Re-evaluate; handled transparently via subsequent `policy_decision`. |
| `grant_revoked` (L5) | L5 | If the revoked grant is load-bearing for the current turn → Repairing; else record and continue. |
| `emergency_revoke_all` (L5) | L5 | Abort ExecutingTool / Streaming immediately, cut TTS, emit `repair_started{EmergencyRevoke}`, transition Idle. |
| `memory_hit` (L2) | L2 | If arrived within T_memory_deadline → feed into `ReflexInputs.short_memory_context`. If late → discard; tag turn. |
| `memory_write_confirmed` (L2) | L2 | Record confirmation for turn-end audit; do not block state machine. |
| `route_decision` (L4) | L4 | RouteSelected; carry tier / provider / plan. If L4 returns `fallback` → emit `tier_downgrade_notice`. |
| `escalation_reason` (L4) | L4 | Informational; attach to `turn_end` outcome. |
| `cost_event` summary (L4) | L4 | Informational; no state change. |
| `persona_swap_commit` (L6) | L6 | On safe boundary (between turns, OR after current ack completes) swap phrase pools. Never mid-utterance. |
| `compiled_persona_ready` (L6) | L6 | Hot-reload phrase pool + ack-style parameters. If L6 fails to deliver → MinimumTrust fallback (§10). |
| `presence_state` (L3) | L3 | Consistency check only — L3 state must correspond to L1 turn state (modulo animation smoothing). On sustained mismatch → emit `presence_desync` telemetry. |
| `vad.speech_start` (Media) | Media | If in Speaking/Streaming/AcknowledgingWait → `BargedIn`. |
| `vad.speech_end` (Media) | Media | Mark end of user turn candidate; arm silence-tail timer. |
| `partial_transcript` (Media) | Media | Into PartialASR state updates. |
| `final_transcript` (Media) | Media | Into ClassifyingIntent transition. |
| `tts_chunk_done` (Media) | Media | Schedule next chunk or EOS → Speaking exit. |
| `viseme_tick` (Media) | Media | Re-emit with turn correlation for L3 (L3 is the primary consumer; L1 passes through only the timing contract signal). |
| `core.health` tier downgrade (Core) | Core | Propagate as `tier_downgrade_notice`; adjust phrase-pool size / tick rate. |

### 6.1 Handler invariants

- Every handler is a pure function of `(current_state, event) → (next_state, side_effects)` plus the transition function (§2.4).
- Handlers never block. A handler that needs to wait emits the relevant outgoing event and transitions to the appropriate Waiting state.
- At-least-once delivery (per L5 §12.2): handlers are idempotent on `request_id` / `query_id` / `turn_id`.

---

## 7. Interfaces (typed pseudotype)

### 7.1 To L5 — `ActionRequest` construction

L1 constructs exactly the `ActionRequest` defined in L5 §3.1. Reflex-category → capability mapping:

```rust
fn build_action_request(turn_id: TurnId, verdict: &ReflexVerdict, ctx: &L1Context) -> ActionRequest {
    let (capability, resource) = match verdict.category {
        ReflexCategory::Search => (Capability::BrowserOpen, ResourceScope::Url(ctx.search_url_pattern())),
        ReflexCategory::ToolPlan => {
            let step0 = verdict.memory_write_proposal.as_ref()
                .map(|_| Capability::MemoryWriteSession)
                .unwrap_or_else(|| verdict.suggested_route_hint.first_step_capability());
            (step0, verdict.suggested_route_hint.first_step_resource())
        }
        ReflexCategory::RemoteEscalation => {
            let cap = if ctx.has_private_context() {
                Capability::RouterAllowRemoteWithPrivate
            } else {
                Capability::RouterEscalateRemote
            };
            (cap, ResourceScope::Provider(ctx.candidate_provider()))
        }
        ReflexCategory::MemoryWrite => {
            let cap = match verdict.memory_write_proposal.as_ref().unwrap().kind {
                MemoryWriteKind::Session => Capability::MemoryWriteSession,
                MemoryWriteKind::Durable => Capability::MemoryWriteDurable,
                MemoryWriteKind::ExtractedPref => Capability::MemoryWriteExtractedPref,
            };
            (cap, ResourceScope::MemoryScope(ctx.active_memory_scope()))
        }
        _ => unreachable!("category is not side-effecting"),
    };

    ActionRequest {
        request_id: RequestId::new(),
        turn_id,
        task_id: ctx.active_task_id,
        capability,
        resource,
        actor_persona: ctx.persona_id,
        active_grants: ctx.policy.snapshot_grants(GrantFilter::persona(ctx.persona_id)).into(),
        session_context: ctx.session_context.clone(),
        provenance_tags: ctx.provenance_tags_for_turn(turn_id),
        intended_route: Some(verdict.suggested_route_hint.clone()),
        risk_class_hint: None,
        emitted_at: now_monotonic(),
    }
}
```

**Wait rules (on `policy.evaluate` return OR emitted `PolicyDecision` event):**

| Decision | L1 action |
|---|---|
| `Allow { grant_ref }` | Fast-path to RouteSelected; attach `grant_ref` to tool-execution envelope. |
| `Ask { ticket }` | Enter AwaitingApproval; block until `approval_response` arrives. Arm T_approval_secondary_ack. |
| `DraftOnly` | Route to draft path; mark output `is_draft=true`; never auto-execute side effect. |
| `Deny { reason: HardcodedBlock \| ActionOutOfScope \| ... }` | Enter Repairing; select deflection phrase (pool=Safety); emit `turn_end{Denied}`. |
| `Deny { reason: NeedsUpgrade }` | (synonym of NeedsUpgrade) route to L7 upgrade-UX via `turn_state_change{Repairing, cause=NeedsUpgrade}`. |
| `NeedsUpgrade { suggested_preset }` | Same as above; forward suggestion to L7. |

L1 calls `PolicyEngine::evaluate` as a non-blocking request (per L5 §5.2 — the call itself returns immediately; the decision arrives as an event). Where L5's IPC model prefers return-value style, L1 uses the trait method directly inside Rust.

### 7.2 To L2 — `MemoryQuery`

```rust
pub struct MemoryQuery {
    pub query_id: QueryId,
    pub turn_id: TurnId,
    pub scope: MemoryScope,              // session, durable, persona-scoped, etc.
    pub query_text: String,              // partial or final transcript
    pub confidence_threshold: f32,       // drop hits below this
    pub deadline: MonotonicTimestamp,    // = turn_begin + T_memory_deadline (150 ms)
    pub max_hits: u8,                    // default 5
}
```

**Contract (must-respond-or-empty):** L2 MUST respond with either `memory_hit` events (one or more, up to `max_hits`) or a `memory_query_empty { query_id }` completion, on or before `deadline`. If L2 misses the deadline, L1 treats it as empty and tags the turn `memory_miss=true`.

L1 treats L2 as a **time-bounded oracle**. L1 does not retry. L1 does not hold a fallback query.

### 7.3 To L3 — turn-state bus (publish only; never call)

L1 publishes `turn_state_change` on the bus; L3 subscribes. **L1 does not call into L3.** For rare forced-escalation cases (repair, barge-in, emergency-revoke), L1 emits a distinguished event (`repair_started`, `barge_in_detected`, `turn_state_change{Repairing}`) and L3 owns the response — possibly by calling its own `presence.set_mode` internal path. L1 does not have a `presence.set_mode` dependency.

### 7.4 To L4 — `RouteHint` / `route_decision`

```rust
pub struct RouteHint {
    pub privacy_posture: PrivacyPosture,         // from persona
    pub tier_preference: PerfTier,
    pub tool_plan_sketch: Option<ToolPlanSketch>,// from reflex
    pub latency_budget_remaining_ms: u32,
    pub intent_class: IntentClass,
    pub memory_confidence: f32,                  // from L2 hits (peak confidence)
    pub reflex_category: ReflexCategory,
}
```

L4 responds with `route_decision`:

```rust
pub struct RouteDecision {
    pub turn_id: TurnId,
    pub chosen_tier: PerfTier,
    pub chosen_provider: ProviderId,
    pub tool_plan: Option<ToolPlan>,             // materialized
    pub fallback_chain: Vec<FallbackStep>,
    pub rationale: StaticReasonId,
    pub estimated_latency_ms: u32,
    pub estimated_cost_cents: u32,
}
```

### 7.5 To L6 — persona consumption

L1 subscribes to `compiled_persona_ready`. From `CompiledPersona`, L1 consumes:

- `phrase_pool: AckPhrasePool` (§8 structure).
- `ack_style: AckStyle { warmth, brevity, formality, filler_density }`.
- `privacy_posture: PrivacyPosture`.
- `safety_phrase_pool: AckPhrasePool` (separate from normal — §8.3).
- `hardcoded_allowed_deflections: Vec<PhraseId>` (used in DegradedNoPolicy, §10).
- `reflex_tuning: ReflexTuning { min_confidence, remote_bias, caution_multiplier }`.

**On `persona_swap_commit`:** hot-swap happens at the next safe boundary — defined as either (a) entry to `Idle`, (b) end of current `Speaking`, or (c) end of current `AcknowledgingWait`. Never mid-word, never mid-classification. If the current turn is mid-flight, the *current turn* uses the old persona; the *next turn* uses the new persona.

### 7.6 To media engine

L1 owns the contract, not the implementation:

- **VAD:** subscribes to `vad.speech_start` / `vad.speech_end`. On `speech_start` during any speaking-adjacent state → `BargedIn`.
- **STT:** subscribes to `partial_transcript` / `final_transcript`. Re-emits with L1 turn correlation.
- **TTS scheduling:** L1 schedules TTS chunks via `media.tts.enqueue(phrase, turn_id)` with the viseme-timing contract:
  ```rust
  pub struct TtsEnqueue {
      pub turn_id: TurnId,
      pub phrase_id: PhraseId,
      pub text: String,
      pub style: TtsStyle,
      pub interruptible_at: InterruptionPolicy { EndOfWord | EndOfSentence | Anywhere },
      pub expect_viseme_stream: bool,
  }
  ```
- **Viseme timing:** L1 owns only the *contract* — viseme chunks arrive on their own channel and carry `audio_ts_ns` anchored to the TTS audio clock; L1 forwards the timing signal; L3 consumes visemes for rendering. Rendering is not L1's concern.

---

## 8. Ack phrase pool

### 8.1 Structure

```rust
pub struct AckPhrasePool {
    pub persona_id: PersonaId,
    pub pool_kind: AckPool,                    // Normal | Safety | Clarify | Repair
    pub entries: Vec<AckPhraseEntry>,
    pub pool_version: u32,                     // bumps on persona recompile
}

pub struct AckPhraseEntry {
    pub phrase_id: PhraseId,
    pub text: String,                          // "Let me check that — one moment."
    pub ack_intent_class: AckIntentClass,      // Checking | Verifying | Thinking | Researching | ToolRunning | LongTask | Stalling | Deflecting | Clarifying | Repairing
    pub persona_posture: PersonaPosture,       // warmth/formality vector
    pub tone_tag: ToneTag,                     // Warm | Dry | Playful | Cautious
    pub last_used_at: Option<MonotonicTimestamp>,
    pub use_count: u32,
    pub min_budget_remaining_ms: u32,          // don't pick long phrases under tight budget
}
```

### 8.2 Selection algorithm (weighted, anti-repetition)

```rust
fn select_phrase(pool: &AckPhrasePool,
                 intent: AckIntentClass,
                 budget_remaining_ms: u32,
                 recency: &RecencyRing) -> PhraseId {
    let candidates: Vec<&AckPhraseEntry> = pool.entries.iter()
        .filter(|e| e.ack_intent_class == intent)
        .filter(|e| e.min_budget_remaining_ms <= budget_remaining_ms)
        .collect();

    if candidates.is_empty() {
        // Fallback: intent-agnostic filler from persona's default-intent bucket.
        return pool.fallback_phrase();
    }

    // Weight = base 1.0 - recency_penalty - repetition_penalty + tone_match_bonus.
    let now = now_monotonic();
    let mut weighted: Vec<(PhraseId, f32)> = candidates.iter().map(|e| {
        let recency_penalty = recency.penalty_for(e.phrase_id, now);  // 0.0..1.0
        let repetition_penalty = match recency.last_phrase_id() {
            Some(pid) if pid == e.phrase_id => 0.9,
            _ => 0.0,
        };
        let w = (1.0 - recency_penalty - repetition_penalty).max(0.05);
        (e.phrase_id, w)
    }).collect();

    weighted_sample(&weighted)  // deterministic with a per-turn seed for replay
}
```

**Anti-repetition invariants:**
- Never emit the same `phrase_id` twice in a row from the same pool.
- Recency ring holds the last N=5 phrase_ids; their weights decay linearly over ~10 turns.
- Acceptance criterion: <5% repetition over 100 consecutive turns (per L1 plan).

### 8.3 Interaction with L6 (persona)

- L6 delivers the pool at `compiled_persona_ready`. L1 swaps atomically.
- Persona drives phrase *content*, *tone*, and *ack_style*. L1 drives *selection* and *timing*.
- Pool size varies by tier (§11): Lite personas ship a smaller pool (fewer variants, more likely repetition — acceptable on Lite per tier-awareness rules).

### 8.4 Interaction with L5 (safety deflection pool is separate)

**Hard rule:** the `AckPool::Safety` pool is distinct from `AckPool::Normal`. It is populated from a hardcoded-allowed set at persona-compile time and ships with the build. A Safety phrase is used when:
- Reflex classified `SafetyDeflection`.
- L5 returned `Deny { HardcodedBlock | PrivacyPostureViolation }`.
- L1 is in `DegradedNoPolicy` and must deflect a side-effecting request.

Safety phrases are never mixed into Normal selection, even if the persona is identity-styled similarly. This ensures that a prompt-injection that coerces the persona to be "playful" cannot leak a playful ack into a safety denial.

The Safety pool has its own anti-repetition ring but no ToneTag bonus — neutrality is enforced.

### 8.5 Clarify / Repair pools

Two additional scoped pools:
- `AckPool::Clarify` — reflex category `ClarifyBackToUser`. Phrase examples: "Say more?" / "Which one?"
- `AckPool::Repair` — entering `Repairing`. Phrase examples: "Let's try that again." / "Hit a snag — one moment."

Same selection algorithm; separate recency ring per pool.

---

## 9. Barge-in and repair

### 9.1 Barge-in

- **Trigger:** media emits `vad.speech_start` while L1 is in Speaking / Streaming / AcknowledgingWait.
- **Action:**
  1. Within **T_barge_in_cut = 150 ms**, issue `media.tts.cut(turn_id, cut_point)`.
  2. `cut_point` policy (from `InterruptionPolicy` set at enqueue):
     - `EndOfWord` (default for acks): cut at next word boundary if within 80 ms; else cut mid-word.
     - `EndOfSentence` (default for long answers): cut at next sentence boundary if within 200 ms; else cut mid-sentence.
     - `Anywhere`: cut immediately.
  3. Emit `barge_in_detected{ cut_point: Resolved }`.
  4. If current answer was from ExecutingDirect / ExecutingTool, emit `turn.cancel` to L4 (L4 cancels the deliberative call).
  5. Transition to `Listening`.
- **Viseme rollback:** L3 receives `barge_in_detected` and interrupts its viseme pipeline. L1 does not manage rollback; it guarantees the cut signal is timely.

### 9.2 Repair

- **Triggers:**
  - `T_hard_deadline` elapsed with no streaming.
  - Media stall sustained > 1500 ms.
  - `PolicyDecision{Deny}` (non-hardcoded reason that cannot be turned into a direct answer).
  - `L4` unreachable (`DegradedNoRouter`).
  - `grant_revoked` on the active grant.
  - `emergency_revoke_all`.
- **Flow:**
  1. Emit `repair_started { turn_id, cause }`.
  2. Select phrase from `AckPool::Repair` (`T_repair_ack = 2000 ms`).
  3. If cause permits reclassification (e.g. hard-deadline, media stall) → after repair phrase, transition to `ClassifyingIntent` to reclassify with the existing final transcript (or re-prompt user if transcript is empty).
  4. If cause is `Deny` → emit `turn_end { outcome: Denied }`; return to `Idle`; L7 surfaces approval-needed prompt.
  5. If cause is `EmergencyRevoke` → emit `turn_end { outcome: Cancelled }`; return to `Idle` hard.
  6. Emit `repair_resolved { resolution }`.
- **Turn continuity:** the same `turn_id` is preserved across repair *unless* the resolution requires a new user input (in which case a fresh `turn_begin` is emitted on the new input).

### 9.3 Repair budgets

- `T_repair_ack`: 2000 ms firm. On miss, emit a hardcoded blunt fallback.
- Repair re-classification: reuses `T_reflex_sla` (150 ms). A second reclassification miss inside the same turn forces `turn_end{Repaired}` with a generic fallback answer.

---

## 10. Failure modes and degraded operation

### 10.1 L5 unreachable → `DegradedNoPolicy`

- **Detection:** `PolicyEngine::evaluate` returns `Err(PolicyEngineError::Degraded(_))`, OR a `core.health` event reports L5 unavailable.
- **Behavior:**
  - Only the **deny-unknown reflex categories** remain active. Concretely: only `DirectLocal` using hardcoded-allowed model calls (local main, no tools), `AcknowledgeAndWait`, `SafetyDeflection` (using hardcoded Safety pool), and `ClarifyBackToUser`.
  - Any reflex category that would produce an `ActionRequest` (Search, ToolPlan, RemoteEscalation, MemoryWrite) is rewritten to `SafetyDeflection` with `rationale_tag = PolicyUnavailable`.
  - A Safety-pool deflection phrase is emitted ("I can't do that right now — my guardrails are offline.").
  - L1 emits `turn_state_change{DegradedNoPolicy}` and `tier_downgrade_notice{reason: PolicyUnavailable}`.
- **Invariant:** L1 NEVER silent-allows a tool, memory write, or remote escalation without a recorded `policy_decision`. If L5 is down, the side-effect doesn't happen. Period.
- **Recovery:** on next successful `PolicyEngine::evaluate`, exit DegradedNoPolicy; emit recovery telemetry.

### 10.2 L5 denies

- See §7.1 and §9.2. Phrase pool = Safety. L7 is signaled via `turn_state_change{Repairing, cause=Deny}` + the underlying `PolicyDecision{Deny}` event it already sees. L7 renders the approval-needed prompt if `NeedsUpgrade`.

### 10.3 L2 unreachable or slow past deadline → `DegradedNoMemory`

- **Detection:** `T_memory_deadline` elapsed with no `memory_hit` / `memory_query_empty`; OR `memory_query` returns `Err(Degraded)`.
- **Behavior:** proceed with empty memory context. Tag turn `memory_miss=true`. Reflex uses persona-default behavior without memory signal. Emit `turn_state_change{DegradedNoMemory}` (may be transient — does not stay in degraded state across turns unless recurring).
- **Interaction with reflex:** missing memory lowers confidence on many intents → more turns fall to `AcknowledgeAndWait` than normal.

### 10.4 L4 unreachable → `DegradedNoRouter`

- **Detection:** `T_policy_wait`/`T_soft_deadline` elapsed with no `route_decision`, OR L4 returns `Err(Degraded)`.
- **Behavior:**
  - Fall back to **direct-to-main local model** (per L4 contingency in 00_ORCHESTRATION_MAP §7).
  - Emit `tier_downgrade_notice{reason: RouterUnavailable}`.
  - Still emit `action_request` if side-effecting — a direct-to-main call that uses *tools* still needs L5 gating. A direct-to-main call that is pure text skips the gate.
- **Recovery:** on next `route_decision` from a subsequent turn, exit DegradedNoRouter.

### 10.5 L6 persona compile fail → MinimumTrust fallback

- **Detection:** absence of `compiled_persona_ready` at startup, OR a `persona_compile_failed` event.
- **Behavior:** load baked-in **MinimumTrustPersona**, consistent with L5 §11.4:
  - Phrase pool: tiny hardcoded Safety + Clarify + minimal Normal-intent set shipped with the build.
  - Ack style: neutral / cautious.
  - Privacy posture: Strict.
  - Reflex tuning: `min_confidence = 0.9` (forces more `AcknowledgeAndWait`), `remote_bias = 0` (no remote escalation), `caution_multiplier = 2`.
  - Hardcoded-allowed deflections: 8-phrase set.
- **Interaction with L5:** MinimumTrust is L5's `MinimumTrustPersona`; L1's behavior mirrors it so the two agree on what's allowed.

### 10.6 Media engine stalls

- **Detection:** `T_tts_chunk_inactivity` (500 ms) breached repeatedly OR sustained 1500 ms.
- **Behavior:** enter `Repairing` with `cause = MediaStall`. Emit `repair_started`. L3 receives and suppresses mouth animation.

### 10.7 Clock skew / monotonic-clock inconsistency

- **Invariant:** all TTL-bound timing promises use `MonotonicTimestamp` (tokio monotonic clock). Wall-clock is cosmetic only.
- **On boot:** if the monotonic clock appears to have reset (process restart is fine; genuine reset would be odd), emit `clock_skew_detected` telemetry and start fresh.
- **On suspend/resume:** measured pauses > 10 s trigger a `suspend_resume_detected` event; any pending turn transitions to Repairing on resume.
- Never promise a TTL measured against wall clock.

### 10.8 Catalog

| Trigger | Degraded mode | Allowed reflex categories | Exit |
|---|---|---|---|
| L5 down | `DegradedNoPolicy` | DirectLocal, AcknowledgeAndWait, SafetyDeflection, ClarifyBackToUser | L5 evaluate succeeds |
| L5 denies | (per-turn, not sticky) | N/A | Turn ends in Repairing → Denied |
| L2 down / slow | `DegradedNoMemory` | all (with empty memory context) | next L2-successful turn |
| L4 down | `DegradedNoRouter` | all; routes coerced to direct-to-main | next `route_decision` |
| L6 compile fail | MinimumTrust | reduced (Strict posture) | `compiled_persona_ready` |
| Media stall | Repairing | N/A | next user input |
| Clock skew | telemetry + per-turn Repairing if affected | N/A | resume |

---

## 11. Tier awareness

### 11.1 What L1 simplifies on Lite

- **Event-bridge coalescing.** Per X3 §8.3, `turn_state_change` and `partial_transcript` are coalesced at a lower rate on Lite; UI receives debounced updates. The Rust-internal bus still sees every transition.
- **Fewer phrase variants.** Lite persona pool ships ~1/3 the variants of Full. Acceptance criterion relaxes from 5% repetition to 10% on Lite.
- **No reflex-level memory preloading.** On Lite, L1 issues only on-demand memory queries; no pre-warm.
- **Coarser timing tick.** `T_event_loop_tick` = 10 ms on Lite (vs 5 ms on Balanced/Full).
- **Classifier strategy forced to rule-only or distilled-small.** Hybrid reflex is off on Lite — budget too tight to run both.

### 11.2 What L1 preserves across all tiers

- **First-ack budget (800 ms).** Firm on every tier.
- **Policy gating.** Every side-effecting reflex → `ActionRequest`, always.
- **Repair.** Full state machine and budgets preserved.
- **Zero silent turns.** Every turn emits either a direct answer or an ack within 800 ms.
- **Barge-in cut (150 ms).** Firm on every tier.

### 11.3 Dynamic downgrades

- On `core.health` tier demotion mid-session (e.g. VRAM pressure), L1:
  1. Emits `tier_downgrade_notice { from, to, reason }`.
  2. Switches phrase pool to the smaller variant (next safe boundary).
  3. Coarsens tick rate.
  4. Current in-flight turn is allowed to finish under the old tier's budgets.

---

## 12. Replay and audit

L1 does not own the audit log — L5 does. But every L1-emitted event carries:
- `change_id` (unique per write).
- `source_layer = L1`.
- `seq` (global monotonic).
- `turn_id` (when turn-scoped).

Every `action_request_outgoing` from L1 has a `request_id`; the corresponding L5 `audit_record` carries that same `request_id` in its `actor` field. This closes the audit loop:

> L5's `audit_record { request_id, change_id, ... }` joins back to L1's `action_request_outgoing { request_id, turn_id, ... }` which joins back to L1's `turn_begin { turn_id, ... }` — full turn-level trace.

### 12.1 Turn-level replay

Given the event log filtered to a `turn_id`, the following reconstruction is deterministic:

1. Start in `Idle`.
2. Apply events in `seq` order. Each event feeds the transition function; the resulting state sequence is the turn's state history.
3. The final event for the turn is `turn_end`; final state must be `Idle`.

Property test (§14): for any captured turn log, `replay(log) == recorded_state_history`.

### 12.2 What L1 logs but does not own

- **Reflex verdicts** — emitted as `reflex_classification`. L5's `action_request → audit_record` chain records the downstream decision. Together they answer: "what category did reflex pick, and did L5 allow it?"
- **Timing annotations** — every `turn_state_change` carries `at: MonotonicTimestamp`. A replay can reconstruct latency stats.
- **Phrase selection** — `ack_phrase` carries `phrase_id`. Replay can check anti-repetition.

---

## 13. Stub interfaces (unblock L2 / L4 / L7 against L1)

### 13.1 Rust traits L1 exposes

```rust
/// The single entry point Rust callers use to drive L1.
/// Commands ultimately flow through Tauri's IPC (X3 §2.2), but the trait is the contract.
pub trait InteractionEngine: Send + Sync {
    /// Start a new turn (called by media on speech_start, or by L7 on text submit).
    fn begin_user_turn(&self, input_kind: InputKind) -> Result<TurnId, L1Error>;

    /// Submit text for a turn (text mode / push-to-talk post-ASR).
    fn submit_text(&self, turn_id: TurnId, text: String) -> Result<ChangeId, L1Error>;

    /// Cancel an in-flight turn (user pressed escape / closed panel).
    fn cancel(&self, turn_id: TurnId) -> Result<ChangeId, L1Error>;

    /// Subscribe to turn-scoped events (L3's primary path into L1).
    fn subscribe_state(&self, turn_id: Option<TurnId>) -> EventStream<L1Event>;

    /// Read-only snapshot of the current turn's state (for consistency checks).
    fn current_state(&self, turn_id: TurnId) -> Option<TurnState>;
}

#[derive(thiserror::Error, Debug)]
pub enum L1Error {
    #[error("no such turn: {0:?}")] NotFound(TurnId),
    #[error("turn already ended")] AlreadyEnded,
    #[error("degraded: {0:?}")] Degraded(L1DegradedMode),
    #[error("internal: {0}")] Internal(String),
}

pub enum L1DegradedMode { DegradedNoPolicy, DegradedNoMemory, DegradedNoRouter, MinimumTrust, Error }
```

### 13.2 Adapter traits L1 depends on (each layer implements one)

```rust
pub trait PolicyAdapter: Send + Sync {
    fn evaluate(&self, req: ActionRequest) -> Result<Decision, PolicyEngineError>;
    fn subscribe(&self, filter: EventFilter) -> EventStream<L5Event>;
    fn snapshot_grants(&self, filter: GrantFilter) -> Vec<Grant>;
}

pub trait MemoryAdapter: Send + Sync {
    fn query(&self, q: MemoryQuery) -> EventStream<MemoryHitOrDone>;
    // One-shot convenience; may time out on deadline and return empty.
    fn query_blocking(&self, q: MemoryQuery) -> Vec<MemoryHit>;
}

pub trait RouterAdapter: Send + Sync {
    fn request_route(&self, hint: RouteHint, turn_id: TurnId) -> Result<ChangeId, RouterError>;
    fn cancel(&self, turn_id: TurnId);
    fn subscribe(&self) -> EventStream<L4Event>;
}

pub trait PersonaAdapter: Send + Sync {
    fn current(&self) -> Arc<CompiledPersona>;
    fn subscribe_swaps(&self) -> EventStream<PersonaEvent>;
}

pub trait MediaAdapter: Send + Sync {
    fn subscribe_vad(&self) -> EventStream<VadEvent>;
    fn subscribe_asr(&self) -> EventStream<AsrEvent>;
    fn tts_enqueue(&self, req: TtsEnqueue) -> Result<ChangeId, MediaError>;
    fn tts_cut(&self, turn_id: TurnId, cut_point: CutPoint);
    fn subscribe_tts(&self) -> EventStream<TtsEvent>;    // chunk_done, eos, stall
}
```

### 13.3 Minimal event contracts consumers can code against

- **L3 stubs against:** `turn_state_change`, `ack_phrase`, `barge_in_detected`, `repair_started`, `repair_resolved`. A fake L1 emitting a scripted sequence of these events is enough to exercise L3's presence scheduler.
- **L4 stubs against:** `route_hint` (consumed) + produces `route_decision`. A fake L1 that emits a `route_hint` stream at scripted cadences exercises L4's routing policy + fallback.
- **L2 stubs against:** `memory_query_outgoing` (consumed). A fake L1 that issues queries at various `deadline` offsets exercises L2's time-bounded-oracle contract.
- **L7 stubs against:** all `turn_state_change` + `turn_begin` + `turn_end` + `ack_phrase` + `tier_downgrade_notice` + the degraded-mode transitions. Plus the command surface in §13.1.

### 13.4 Per-consumer stub table

| Consumer | Stub surface | Acceptable fake |
|---|---|---|
| **L2** | `MemoryAdapter` implemented against L1; L1 emits `memory_query_outgoing` with deadlines | Always-empty adapter that respects deadline; a variant that returns 1–3 hits at T-50 ms |
| **L3** | Subscribe to `turn_state_change` + `ack_phrase` + `barge_in_detected` | Scripted-L1 harness that cycles through all states at configurable cadences |
| **L4** | Subscribe to `route_hint`; deliver `route_decision` back | Always-local-main adapter; a variant that emits `Err(Degraded)` to exercise DegradedNoRouter |
| **L5** | L1 calls `PolicyAdapter::evaluate`; L1 subscribes to L5 events | L5 already publishes a stub matrix (L5 §12.4) — L1 consumes it directly |
| **L6** | `PersonaAdapter::current()` returns a default persona; swap events scripted | Static persona; later a variant that delivers persona_swap_commit mid-turn for tests |
| **L7** | `InteractionEngine` command surface + event subscription | A harness script that exercises the entire command surface via the Tauri bridge |

---

## 14. Testing strategy (design level)

### 14.1 Property tests (state machine)

- **Determinism.** For any `(state, event)` pair, `transition(state, event) == transition(state, event)` across runs; no hidden randomness. Phrase selection uses a per-turn seed captured in events for replay.
- **Timer monotonicity.** Timer events always fire in non-decreasing `MonotonicTimestamp` order; expired timers never fire twice.
- **Zero-silent-turn invariant.** For any turn that enters Listening, within 800 ms of `turn_begin` either a direct answer has started streaming OR an `ack_phrase` has been emitted. Fuzz with randomized L2/L4/L5 latencies.
- **Reflex-never-executes invariant.** For every reflex category marked side-effecting, fuzz asserts: no tool call / memory write / remote call leaves L1 before a `PolicyDecision{Allow}` is received.
- **Barge-in bound.** For any VAD speech_start during Speaking, `tts_cut` issued within 150 ms.
- **Anti-repetition.** Over 100 random turns with a fixed persona, same-phrase-in-a-row count = 0; phrase repetition rate < 5% (Full tier) / < 10% (Lite tier).

### 14.2 Timing-budget harness

- Synthetic turns with injected latency profiles for L2 / L4 / L5 / Media.
- Asserts p95 of `turn_begin → first_ack_or_answer` ≤ 800 ms across 10 000 turns.
- Asserts p99 of `vad.speech_start → tts_cut` ≤ 150 ms.
- Exercises T_soft_deadline and T_hard_deadline triggers at the exact boundary ±5 ms.

### 14.3 Red-team scenarios

- **Reflex classifier bypass attempts.** Prompt-crafted partial transcripts designed to coerce `DirectLocal` on actually-side-effecting intents (e.g. "pretend to book a flight"). Pass criterion: classifier stays in `AcknowledgeAndWait` or routes through L5 for the real action.
- **Barge-in during AwaitingPolicy.** User speaks while waiting on approval. Pass: L1 cuts any in-flight ack, transitions to Listening, cancels the pending `action_request` via a typed `L1CancelRequest` that L5 accepts (ticket auto-closes).
- **Persona-swap mid-turn.** `persona_swap_commit` fires during ExecutingTool. Pass: current turn continues with old persona; next turn uses new persona; no phrase-pool crossover mid-utterance.
- **Memory-hit arrives after deadline.** L2 delivers at T+200 ms. Pass: L1 discards the hit for that turn; subsequent turn queries fresh.
- **L5 Deny mid-stream.** `grant_revoked` arrives during Streaming. Pass: L1 halts stream, enters Repairing, emits deflection.
- **Clock skew mid-session.** Monotonic clock unchanged but wall clock jumps -1h. Pass: no TTL violations; cosmetic timestamps shift only.
- **MinimumTrust coverage.** L6 fails to compile. Pass: L1's allowed reflex categories match L5's MinimumTrust allowed capabilities exactly (no drift).

### 14.4 Replay tests

- Capture event logs from live sessions; replay against the reference state machine. Asserts: reconstructed state history matches recorded.
- Mutation tests: alter one event in a captured log; assert replay fails deterministically with a specific reason.

### 14.5 Cross-layer integration tests

- End-to-end: L1 + stub-L5 (allow-all) + stub-L4 (local-main) + stub-L2 (empty) + real Media. Assert all acceptance criteria from plans/L1_interaction_timing.md hold.
- End-to-end with L5 ask-mode: every turn asks; assert no silent allow, approval prompts timed correctly.

---

## 15. Deliverables summary — what a future implementer builds first

In dependency order:

1. **State machine crate with typed events.** `l1-core` crate: `TurnState` enum, `L1Event` enum, `transition(state, event) -> (next_state, effects)`, timer abstraction. Zero dependencies on L2/L4/L5 — just the event shapes.
2. **Ack-phrase pool structure.** `AckPhrasePool`, `AckPhraseEntry`, selection algorithm, recency ring. A hardcoded default persona's pool ships for bring-up.
3. **Reflex classifier skeleton with pluggable strategies.** `trait ReflexClassifier` + a rule-only implementation for P0. Distilled head plugs in at P1 behind the same trait.
4. **Adapter traits for L2 / L4 / L5 / L6 / Media.** As defined in §13.2. Fake implementations live in `l1-test-stubs`.
5. **Timing-budget harness.** Synthetic-turn generator + latency-injected adapters; produces the CSV/event log for property tests in §14.

What comes *after* first-action:
- Distilled classifier training pipeline (P1+).
- Full persona pool ingestion pipeline (waits on L6 compiler freeze).
- Tauri command-surface wiring (X3 §2.2 `turn.*` commands) — thin; delegates to `InteractionEngine` trait.

---

## 16. Open questions

Each item: **Question** — why it matters — proposed default — impact if defaulted silently.

1. **Reflex strategy for P0.** Rule-only vs distilled-head. Upstream plan calls for "hand-coded reflex rules" at P0; this doc defaults rule-only at P0 and distilled at P1.
   - **Why it matters:** determines whether P0 ships without an ML dependency.
   - **Proposed default:** rule-only at P0 behind `ReflexClassifier` trait; distilled plug-in at P1.
   - **Impact if defaulted silently:** fine — rule-only is Don's stated P0 shortcut (plans/L1_interaction_timing.md §"Open decisions").

2. **P0 language.** Rust vs Python/TS (plans/L1_interaction_timing.md lists this as open).
   - **Why it matters:** Rust P0 means the typed event bus is ready on day one; Python/TS means a shim layer.
   - **Proposed default:** Rust from P0 to avoid a rewrite. Accept this lengthens P0; the state-machine crate is small.
   - **Impact if defaulted silently:** if Python/TS is chosen later, the shim re-implements every adapter trait in a second language.

3. **Exact ms values for budgets.** The 250 / 800 / 2000 / 4000 doctrine is locked; *sub-budgets* (T_reflex_sla = 150 ms, T_memory_deadline = 150 ms, T_barge_in_cut = 150 ms) are this doc's defaults — they need Don's sign-off.
   - **Why it matters:** these feed OPEN_QUESTIONS evaluation metrics.
   - **Proposed default:** values in §4; revisit after the timing-budget harness produces real data.
   - **Impact if defaulted silently:** if too tight, everything falls to `AcknowledgeAndWait`; too loose, we miss the 800 ms firm budget.

4. **Who cancels the deliberative path on barge-in.** L1 emits a cancel signal; L4 executes. Is the cancel command on L4's surface frozen?
   - **Why it matters:** without a cancel path, a barged-in call's answer can still arrive late.
   - **Proposed default:** `RouterAdapter::cancel(turn_id)` as in §13.2.
   - **Impact if defaulted silently:** a late answer arrives after the user's new turn began — a doctrine violation.

5. **Pre-emptive memory queries.** Should L1 fire `memory_query` on partial transcripts or only on final?
   - **Why it matters:** pre-emptive halves effective memory latency but increases L2 load.
   - **Proposed default:** fire on first partial with stability > 0.6; replace on each more-stable partial; discard all but the final result.
   - **Impact if defaulted silently:** missing the <150 ms memory-hit budget more often → more turns in AcknowledgeAndWait.

6. **L7 approval-needed surface contract.** When L5 returns `NeedsUpgrade`, L1 transitions to Repairing; what exactly does L7 render?
   - **Why it matters:** L7's contract with L1 on repair UI isn't frozen.
   - **Proposed default:** L1 emits `turn_state_change{Repairing, cause=NeedsUpgrade}` + includes `NeedsUpgradeHint` in the `repair_started` payload; L7 renders its upgrade UX.
   - **Impact if defaulted silently:** inconsistent user experience on deny vs upgrade-required.

7. **Persona-swap safe-boundary strictness.** Should swap wait only for `Idle` (strict), or also for ack/utterance ends (relaxed)?
   - **Why it matters:** strict = predictable but sometimes seconds-delayed; relaxed = snappier but mid-turn style drift possible.
   - **Proposed default:** relaxed — swap at `Idle`, end-of-Speaking, or end-of-AcknowledgingWait (this doc's §7.5).
   - **Impact if defaulted silently:** if strict is required for L5 (grant revocation coupling), relaxed leaks a stale-persona evaluation.

8. **Clarification loop depth.** How many consecutive `ClarifyBackToUser` turns before L1 forces a different tactic?
   - **Why it matters:** reflex that keeps asking "which one?" is its own failure mode.
   - **Proposed default:** max 2 consecutive clarifies; 3rd turn forces `AcknowledgeAndWait` + deliberative path.
   - **Impact if defaulted silently:** a clarification loop with no exit.

9. **Doctrine contradiction — 7 vs 8 layers.** Resolved in plans/00_ORCHESTRATION_MAP.md §1 (7-layer is canonical; reflex folded into L1) but 01_product_doctrine.md has not yet been updated. This document assumes the 7-layer model per the orchestration map.
   - **Why it matters:** an implementer reading only 01 would expect a separate reflex-router layer.
   - **Proposed default:** follow 00_ORCHESTRATION_MAP §1. No reflex-router crate; reflex lives inside `l1-core`.
   - **Impact if defaulted silently:** drift (same flag L5 system design raised, §14.11).

10. **Doctrine contradiction — L1 event naming vs 08_system_architecture.md.** `08` lists `intent_hint` emitted by Cognition; this doc has L1's embedded reflex emit `intent_hint` + a new `reflex_classification`. Per 00_ORCHESTRATION_MAP §1, reflex is inside L1, so the emitter is L1. Flagged here, not silently resolved.
   - **Why it matters:** wire-level event ownership.
   - **Proposed default:** L1 emits both. `08`'s "Cognition" emitter label is an artifact of the pre-7-layer doc.
   - **Impact if defaulted silently:** two engines may both claim to emit `intent_hint`; bus duplication.

11. **L5 `Decision::Deny { reason: NeedsUpgrade }` vs `Decision::NeedsUpgrade`.** L5 defines both a `Deny` variant with reason and a top-level `NeedsUpgrade` variant. Which one arrives in practice?
    - **Why it matters:** L1's handler needs to match on exactly one.
    - **Proposed default:** honor `Decision::NeedsUpgrade` as the canonical variant; never synthesize it from a `Deny` with an uplift hint.
    - **Impact if defaulted silently:** upgrade UX may not trigger when it should.

12. **Budget sharing between AwaitingPolicy and AwaitingApproval.** The approval wait is bounded only by user attention, but a secondary ack is scheduled at 2000 ms. Does this also apply to AwaitingPolicy that never transitions to AwaitingApproval (i.e. pure auto-allow that is just slow)?
    - **Why it matters:** differentiating "policy engine is just slow" from "user is thinking".
    - **Proposed default:** secondary-ack fires at 2000 ms in both sub-states; distinct intent class per state (Thinking vs Stalling).
    - **Impact if defaulted silently:** user hears the same "still waiting" phrase for two very different reasons.

13. **Event projection policy.** Which L1 events are projected to the webview (per X3 §3.2)? This doc defaults the `Projected?` column in §5.2; Don / L7 should confirm.
    - **Why it matters:** webview event volume on Lite tier.
    - **Proposed default:** as in §5.2; coalesce `partial_transcript` and `turn_state_change` on Lite.
    - **Impact if defaulted silently:** webview event storm on fast-typing text turns.

14. **Does repair keep the same `turn_id`?** This doc says yes unless repair requires new user input. L7 may need a distinct signal for "same turn, retrying" vs "new turn, user re-prompted".
    - **Why it matters:** UI continuity.
    - **Proposed default:** same `turn_id` across repair; fresh `turn_id` only on user re-input.
    - **Impact if defaulted silently:** UI may show two separate turn bubbles for one repaired turn.

---

## Self-review checklist

- [x] Every state in §2 has entry/exit/transitions defined (§2.1 and §2.3 tables).
- [x] Every reflex category in §3 maps to an L5 capability (or is hardcoded-allowed). See §3.2 table; `DirectLocal`, `AcknowledgeAndWait`, `SafetyDeflection`, `ClarifyBackToUser` are hardcoded-allowed (data, not tools).
- [x] Every timing budget in §4 has a firm/best-effort label and a missed-trigger.
- [x] Every emitted event in §5 has typed fields (§5.2 table).
- [x] Every consumed event in §6 has a documented handler (§6 table + §6.1 invariants).
- [x] §7 interfaces match L5's Rust trait shape (`PolicyEngine::evaluate` / `subscribe`) — see §7.1 and §13.2 `PolicyAdapter`.
- [x] §10 has a degraded-mode entry for each upstream: L5 (§10.1), L2 (§10.3), L4 (§10.4), L6 (§10.5), media (§10.6), plus clock skew (§10.7). Catalog in §10.8.
- [x] §13 gives L2 / L4 / L7 enough stub surface to design against (§13.4 per-consumer table).

---

## Closing notes

- **Contracts frozen in this document:** §2 turn-state machine, §4 timing budgets, §5 emitted event shapes, §6 consumed-event handlers, §7 interfaces to L2/L3/L4/L5/L6/Media, §8 ack phrase pool structure, §13 `InteractionEngine` trait + adapter traits.
- **Immediately adjacent layer to design next:** L6 persona compiler — L1 consumes `CompiledPersona` (phrase pools, ack style, reflex tuning) and the contract isn't frozen yet. L4 is the other candidate because it consumes `RouteHint` and delivers `route_decision`.
- **Canonical package home** (X1-dependent): file:///C:/Users/dbhav/Projects/aether/packages/l1-interaction/ (Rust) + file:///C:/Users/dbhav/Projects/aether/packages/l1-interaction-ts/ (typed bindings).
