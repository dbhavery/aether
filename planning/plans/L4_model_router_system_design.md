---
status: draft
date: 2026-04-18
layer: L4 (model router)
mode: system design (implementation-grade)
upstream:
  - 01_product_doctrine.md (§"Must-own layers" #4, §"Borrowable layers", §"Desktop framework doctrine")
  - MASTER_OUTLINE_TREE.md §5, §6, §12.4
  - plans/00_ORCHESTRATION_MAP.md §1, §6, §7
  - plans/L4_model_router.md (upstream plan this elaborates)
  - plans/L5_policy_engine_system_design.md (authoritative L5 contract: ActionRequest, Decision, events, BYOK hard-cap §9, privacy-posture gate §10)
  - plans/L1_interaction_timing_system_design.md (RouteHint shape §7.4 consumed by L4; RouteDecision shape §7.4 emitted back)
  - plans/X3_tauri_architecture.md §2 command surface, §3 event bus, §4 layer map (router row), §5.3 aether-plugin-router-remote, §8 tier compatibility
  - 18_model_router_spec.md (tier abstraction, fallback chains, BYOK keyring, wizard presets)
  - plans/L2_memory_kernel.md (memory-confidence signal, provenance tags)
  - plans/L6_persona_compiler.md (privacy posture + llm_preferences from CompiledPersona)
  - plans/03_content_lock_v1_port.md §4 (BYOK hard-cap is an L5 boundary; L4 emits cost_event, L5 enforces)
downstream_consumers:
  - plans/L1_interaction_timing_system_design.md (L1 consumes route_decision; L1 cancels via RouterAdapter::cancel)
  - plans/L5_policy_engine_system_design.md (L5 gates every L4 tool / remote / cost action; L5 enforces cap)
  - plans/L7_trust_ux_onboarding.md (router debug overlay, BYOK UX, wallet / cost visibility, fallback surfacing)
  - plans/L2_memory_kernel.md (L2 receives no direct calls from L4 but provenance tags flow through)
scope_of_this_document:
  - Implementation blueprint an engineer can start building against
  - Pseudotypes, pseudocode, tables, ASCII diagrams inside this markdown; no .rs / .sql files
  - Freezes the L4 contract that L1 / L5 / L7 stub against
non_goals:
  - Resolving final Gemma 4 variant names per tier (flagged; see §19)
  - Writing the BYOK UX (L7)
  - Implementing the router (no crates)
  - Choosing HTTP client / SDK crates (§19 open)
---

# L4 — Model Router — System Design

> The plan (file:///C:/Users/dbhav/Projects/aether-planning/plans/L4_model_router.md) says *what* L4 owns. This document says *how* L4 is built. Downstream layers (L1, L5, L7) should stub against the contracts frozen here (§5, §7, §11, §13, §16).
>
> Canonical planning root: file:///C:/Users/dbhav/Projects/aether-planning/
> Target package home (X1-dependent): file:///C:/Users/dbhav/Projects/aether/packages/l4-router/ (Rust) + file:///C:/Users/dbhav/Projects/aether/packages/l4-router-ts/ (typed bindings) + file:///C:/Users/dbhav/Projects/aether/crates/plugin-router-remote/ per X3 §5.3.

---

## 1. Purpose and scope

### 1.1 What L4 owns

- **Tier abstraction.** Cognition and L1 never ask for a model. They ask for a tier (fast / main / heavy) plus a side-channel of intent shape. L4 maps tier → concrete (provider, model, adapter) based on inputs in §2.
- **Route selection.** Decision tree that consumes a `RouteHint` from L1 plus signals from L2 / L5 / L6 / core.health and emits a `RouteDecision` (§4, §5).
- **Fallback chains.** Tier- and tier-downgraded-specific chains; deterministic order; circuit-breaker on repeat failure (§10).
- **BYOK credentials brokerage.** OS-keyring-backed vault; credentials never returned to the webview; rotation + test flows (§9).
- **Cost accounting.** Per-provider rolling counters emitted as `cost_event` events on every call. Cap **enforcement** is L5's; L4 is the emitter and honors `cost_threshold_hit` by refusing subsequent routes to the hit provider (§6, §9).
- **Tool-plan orchestration** — constructing `ToolCall` envelopes, threading them through L5's chokepoint (§6, §7), assembling results, and handing the final payload back to L1 via the `route_decision` / streaming pipeline.
- **Provider plugin host.** Loads local + remote adapters behind a single Rust trait (§8). Adds / removes a provider = capability mutation recorded in L5.
- **Provider health telemetry.** Rolling p95 per tier per provider feeds routing (latency-aware routing, `plans/L4_model_router.md` P3).
- **Prompt compilation handoff.** Takes the `CompiledPersona` system-prompt slice + a sanitized context pack from L2 and produces a provider-specific call payload. Sanitization applies at compile time (not at runtime in the provider adapter).

### 1.2 What L4 does NOT own

- **Policy decisions** (L5). L4 never decides `Allow` / `Ask` / `Deny`. L4 submits `ActionRequest`s and honors the `Decision`.
- **Hard-cap enforcement.** L4 emits `cost_event`. L5 maintains the rolling counter and emits `cost_threshold_hit` (L5 §9). L4 refuses to route once it has seen the threshold event.
- **Memory retrieval** (L2). L4 consumes memory-confidence *summaries* (peak confidence, provenance-tag roll-up) attached to `RouteHint`; L4 does not query L2 directly.
- **Turn timing** (L1). L4 reports `estimated_latency_ms` and honors deadlines but does not own the turn clock.
- **Presence animation** (L3). L4 never talks to L3.
- **Inference runtimes and model weights.** Borrowable per doctrine. L4 wraps them behind `ProviderAdapter`.
- **TTS / STT.** Media engine. L4 does not route speech.
- **The audit log.** L5. L4-emitted events carry `change_id` / `seq` so L5's `audit_record` join-table works.

### 1.3 Boundary invariants

1. **Every tool invocation and every remote call is preceded by a `PolicyEngine::evaluate` call.** No exceptions. L4 is the primary offender the chokepoint exists to catch (L5 §12 `PolicyAdapter`). Static-analysis lint rejects direct provider adapter calls from L4 code paths that did not come through the policy-checked dispatcher.
2. **No silent allow.** If L5 is unreachable (`PolicyEngineError::Degraded`), L4 enters `DegradedNoPolicy` and refuses every side-effecting path (§6.5, §14).
3. **No silent cost overrun.** Every completed call emits `cost_event` before the result stream completes. Aborted calls emit partial cost if any tokens were dispatched.
4. **Privacy posture is preemptive.** The privacy-posture gate (§6.3) is evaluated *before* a remote provider is selected, not after. No remote payload is constructed until posture passes.
5. **L4 never holds a user-authoritative grant.** It reads snapshots via `PolicyEngine::snapshot_grants` when it needs to know "do I have `RouterEscalateRemote` for this provider?"; but the evaluator is the gate.

---

## 2. Routing inputs

### 2.1 `RouteHint` — typed contract from L1

Matches `plans/L1_interaction_timing_system_design.md §7.4` exactly:

```rust
pub struct RouteHint {
    pub turn_id: TurnId,
    pub persona_id: PersonaId,
    pub privacy_posture: PrivacyPosture,            // Strict | Balanced | Open  (from L6)
    pub tier_preference: PerfTier,                  // Lite | Balanced | Full    (from core.health)
    pub tool_plan_sketch: Option<ToolPlanSketch>,   // from reflex
    pub latency_budget_remaining_ms: u32,
    pub intent_class: IntentClass,
    pub memory_confidence: f32,                     // peak confidence across L2 hits
    pub reflex_category: ReflexCategory,            // DirectLocal | Search | ToolPlan | RemoteEscalation | ...
    pub provenance_tags: Vec<ProvenanceTag>,        // rolled up across memory hits
}
```

### 2.2 Additional inputs L4 pulls

| Source | Field | Purpose |
|---|---|---|
| **L2** (via L1's aggregation) | `memory_confidence: f32`, `provenance_tags: Vec<ProvenanceTag>` | Low confidence → escalate; tainted provenance → force DraftOnly path (L5 §3.4 taint). |
| **L6** `CompiledPersona` (via `PersonaAdapter::current()`) | `llm_preferences { preferred_tier, temperature, max_output_tokens, pinned_model? }`, `privacy_posture: PrivacyPosture`, `system_prompt: String`, `safety_header: String` | Persona bias; hard privacy override; prompt assembly. |
| **L5** (via `PolicyAdapter::snapshot_grants` + subscription) | `denied_capabilities: Set<Capability>` (effective from preset × persona × hardcoded blocks), `active_grants: Vec<Grant>`, `cost_threshold_hit: Set<ProviderId>` | Eliminate routes that will deny up-front; skip providers at cap. |
| **core.health** | `PerfTier`, `vram_pressure: VramPressure { Ok, Warn, Critical }`, `network_state: NetworkState { Online, Metered, Offline }` | Trigger tier downgrade / force offline routing. |
| **L4 self — BYOK wallet state** | per-provider `cents_spent_today`, `hard_cap_cents`, `key_present: bool`, `last_auth_check: MonotonicTimestamp`, `rolling_p95_latency_ms` | Prune providers with missing / unauthorized keys; latency-aware bias. |
| **L4 self — provider health** | `circuit_breaker_state: { Closed | HalfOpen | Open }`, `last_failure_reason`, `rate_limit_reset_at` | Skip Open-circuit providers. |

### 2.3 Routing context pseudotype

```rust
pub struct RoutingContext {
    pub hint: RouteHint,
    pub persona: Arc<CompiledPersona>,
    pub policy_snapshot: PolicySnapshot,     // grants + denied capabilities + cost-capped providers
    pub health: CoreHealth,
    pub wallet: WalletState,
    pub provider_health: HashMap<ProviderId, ProviderHealth>,
    pub now_mono: MonotonicTimestamp,
}
```

---

## 3. Tier abstraction

### 3.1 Tier list (authoritative)

Seven typed tiers. Every decision case in §4 terminates on exactly one of these.

| Tier id | Purpose | Latency budget (first token) | VRAM budget (Balanced) | Default capability set | Default-available on Lite? | Balanced? | Full? |
|---|---|---|---|---|---|---|---|
| `fast-local` | Reflex classifier, intent hints, ultra-short acks. | <150 ms | ≤2 GB | Pure text only, no tools. | Yes | Yes | Yes |
| `main-local` | Conversational deliberation (most turns). | <1500 ms TTFT | ≤8 GB | Text + light grounding (RAG inputs), no tools. | Partial (smallest variant only) | Yes | Yes |
| `heavy-local` | Long reasoning, planning, hard tasks with data privacy. | <5 s TTFT | ≤16 GB (Full only) | Text + grounding; optional tool use via L5 chokepoint. | No | Partial | Yes |
| `fast-remote` | Remote classifier / backup for Lite reflex. | <400 ms TTFT (network + provider) | N/A | Pure text; provider-dependent. | Yes | Optional | Optional |
| `main-remote` | Remote conversational deliberation (frontier). | <2 s TTFT target | N/A | Text + grounding + (provider-permitting) tool use. | Yes (default) | Optional | Optional |
| `heavy-remote` | Long / hardest reasoning, multi-step tool plans. | <6 s TTFT budget | N/A | Text + tools + grounding. Highest capability. | Yes (explicit) | Yes (explicit) | Yes |
| `tool-plan-executor` | Meta-tier: a plan split across N steps; each step re-routes via §4 cases, but the plan envelope is the atomic unit L1/L7 see. | Sum of step budgets, bounded by `T_hard_deadline` | Variable | Any capability granted to underlying steps. | Yes | Yes | Yes |

### 3.2 Gemma 4 variant → tier mapping

| Tier | Lite variant | Balanced variant | Full variant |
|---|---|---|---|
| `fast-local` | Gemma 4 *smallest* | Gemma 4 *smallest* | Gemma 4 *small* |
| `main-local` | Gemma 4 *small* (degraded; prefer remote) | Gemma 4 *mid* | Gemma 4 *mid* |
| `heavy-local` | disabled (remote-forced) | Gemma 4 *large-if-fits* else fall back | Gemma 4 *largest-tier-appropriate* |

**Note.** Final model names are deferred per `OPEN_QUESTIONS.md` and the `plans/L4_model_router.md` "Open decisions for executing agent" list. This document uses `smallest/small/mid/large/largest` as stable placeholders; §19 open question 1 flags the pending lock.

### 3.3 Capability-set shape per tier

```rust
pub struct TierCapabilities {
    pub streaming: bool,
    pub grounding_input: bool,              // can accept retrieval-augmented context
    pub tool_use: bool,                     // can call tools (gated by L5 per call)
    pub vision_input: bool,                 // multimodal image input
    pub audio_input: bool,
    pub max_context_tokens: u32,
    pub max_output_tokens: u32,
}
```

Each `(tier, provider)` pair registers a `TierCapabilities` struct at provider-plugin load time; routing never attempts a capability the pair does not advertise.

---

## 4. Routing decisions

The router walks a typed decision tree. Every case ends with a typed `RouteDecision` (§5) and every case that would side-effect carries an explicit **policy checkpoint** column. A checkpoint is an `ActionRequest` submitted to L5 and a consequent `Decision` honored.

### 4.1 Decision case table

| # | Case | Triggering inputs | Chosen tier | Tool plan? | Policy checkpoint(s) | RouteDecision fields emphasized |
|---|---|---|---|---|---|---|
| 1 | **Direct-local answer** | `reflex_category = DirectLocal`; pure text; no tainted provenance; posture any | `main-local` (or `fast-local` if intent is trivial) | none | **None** — L1 already determined no side effect. (Pure-text local inference is *not* a capability boundary.) | `chosen_tier = main-local`, `requires_approval = false`, `cost_estimate = 0` |
| 2 | **Direct-remote answer** | `reflex_category ∈ {DirectLocal, RemoteEscalation}` but core.health flags VRAM pressure OR memory_confidence below `remote_escalation_threshold` AND private posture not triggered | `main-remote` (or `fast-remote` on Lite reflex-backup) | none | **`RouterEscalateRemote`** on `ResourceScope::Provider(provider)`; privacy-posture gate must pass (L5 §10) | `chosen_tier = main-remote`, `chosen_provider`, `privacy_posture_respected = true`, `cost_estimate > 0` |
| 3 | **Local-then-escalate-if-low-confidence** | `reflex_category = DirectLocal`; memory_confidence in (`remote_escalation_threshold` .. `local_sufficient_threshold`); Balanced/Full tier | Primary `main-local`; fallback `main-remote` (carried in `fallback_chain`) | none | **Deferred**: no remote call attempted initially. If fallback fires, a second evaluate on `RouterEscalateRemote` is emitted at that moment. | `chosen_tier = main-local`, `fallback_chain = [main-remote]`, `policy_decision_ref = None` initially |
| 4 | **Tool-plan (single-step)** | `reflex_category = ToolPlan`; `tool_plan_sketch.len() == 1` | `main-local` or `main-remote` depending on step capability set | `Some(ToolPlan { steps: [step0] })` | **Per-step**: capability of `step0` on its `resource_scope`. L5 returns Allow/Ask/DraftOnly/Deny/NeedsUpgrade. | `tool_plan`, `policy_decision_ref = Some(change_id)`, `requires_approval` if Ask |
| 5 | **Tool-plan (multi-step)** | `reflex_category = ToolPlan`; `tool_plan_sketch.len() > 1` | `tool-plan-executor` (envelope) | `Some(ToolPlan { steps: [..] })` | **Per-step** OR (P2+) **plan preview** via `policy.preview_plan` (L5 §5.2). Session-grant bundle possible. | `tool_plan`, `fallback_chain` per step, `requires_approval` sticky |
| 6 | **Search-then-answer** | `reflex_category = Search` | `main-remote` (search-grounded if provider supports) OR `main-local` + grounding tool | `Some(ToolPlan { steps: [BrowserOpen, BrowserReadPage, MainSynthesis] })` | Step-0: `BrowserOpen` on URL pattern. Step-1: `BrowserReadPage`. Step-2: synthesis (may trigger `RouterEscalateRemote`). | same as case 5 |
| 7 | **Needs-human-confirmation** | Any case where L5 returned `Decision::Ask` | Parked | Pending | Already checked; `ApprovalPending` in flight | `requires_approval = true`, `approval_ticket_id`, `chosen_tier = None` |
| 8 | **Safety-deflection (refuse route)** | L5 returned `Decision::Deny` with hardcoded-block reason OR `PrivacyPostureViolation`; OR reflex pre-classified `SafetyDeflection` | Refusal | none | Already checked | `chosen_tier = None`, `rationale = SafetyDeflection`, `requires_approval = false` |
| 9 | **Needs-upgrade (capability missing)** | L5 returned `Decision::NeedsUpgrade` | Parked | none | Already checked | `chosen_tier = None`, `rationale = NeedsUpgrade`, `upgrade_hint: Option<UpgradePath>` handed back to L7 via L1 |

### 4.2 Decision-tree pseudocode

```rust
fn route(ctx: &RoutingContext, policy: &dyn PolicyAdapter) -> RouteDecision {
    // Guard 1: L5 reachable? If not, we are in DegradedNoPolicy — deny tool/remote.
    if policy.is_degraded() && ctx.hint.reflex_category.is_side_effecting() {
        return deny_route(ctx, Rationale::DegradedNoPolicy);
    }

    // Guard 2: privacy-posture quick screen for remote-preferring cases.
    //   (Real L5 evaluation still happens per-call; this prunes choices up-front so
    //   we don't build a remote payload we will later throw away.)
    let remote_allowed_under_posture = posture_allows_remote(&ctx.hint, &ctx.persona);

    match ctx.hint.reflex_category {
        ReflexCategory::DirectLocal =>
            if needs_remote_escalation(ctx) && remote_allowed_under_posture {
                route_direct_remote(ctx, policy)           // Case 2
            } else if confidence_borderline(ctx) {
                route_local_with_remote_fallback(ctx, policy) // Case 3
            } else {
                route_direct_local(ctx)                    // Case 1
            },

        ReflexCategory::Search         => route_search_plan(ctx, policy),            // Case 6
        ReflexCategory::ToolPlan       => route_tool_plan(ctx, policy),              // Cases 4/5
        ReflexCategory::RemoteEscalation => {
            if !remote_allowed_under_posture {
                // Posture-Strict + private context: we MUST NOT attempt remote;
                // L5 would deny but we prune up-front so we do not leak "we tried".
                return route_direct_local(ctx).with_rationale(Rationale::PrivateForceLocal);
            }
            route_direct_remote(ctx, policy)               // Case 2
        }

        ReflexCategory::SafetyDeflection => deny_route(ctx, Rationale::SafetyDeflection),
        ReflexCategory::MemoryWrite     => {
            // L1 already turned this into an ActionRequest; L4 only routes a text answer if needed.
            route_direct_local(ctx)
        }
        ReflexCategory::AcknowledgeAndWait | ReflexCategory::ClarifyBackToUser => {
            // Ack / clarify phrases are data; no L4 route needed. Return a sentinel decision.
            RouteDecision::no_route_needed(ctx.hint.turn_id)
        }
    }
}
```

### 4.3 Per-case policy checkpoint shape

Every side-effecting branch terminates in a call to `policy.evaluate(action_req)`:

```rust
fn enforce_policy(policy: &dyn PolicyAdapter,
                  ctx: &RoutingContext,
                  capability: Capability,
                  resource: ResourceScope,
                  cost_estimate: Cents) -> PolicyOutcome {
    let req = ActionRequest {
        request_id: RequestId::new(),
        turn_id: ctx.hint.turn_id,
        task_id: ctx.task_id(),
        capability,
        resource,
        actor_persona: ctx.persona.persona_id,
        active_grants: policy.snapshot_grants(GrantFilter::persona(ctx.persona.persona_id)).into(),
        session_context: ctx.session_context(),
        provenance_tags: ctx.hint.provenance_tags.clone(),
        intended_route: Some(ctx.hint.clone()),
        risk_class_hint: None,
        emitted_at: now_monotonic(),
    };
    match policy.evaluate(req) {
        Ok(Decision::Allow { grant_ref, audit_id })       => PolicyOutcome::Allow { grant_ref, audit_id },
        Ok(Decision::Ask { ticket, audit_id })            => PolicyOutcome::Pending { ticket, audit_id },
        Ok(Decision::DraftOnly { audit_id, reason })      => PolicyOutcome::DraftOnly { audit_id, reason },
        Ok(Decision::Deny { reason, audit_id })           => PolicyOutcome::Deny { reason, audit_id },
        Ok(Decision::NeedsUpgrade { suggested_preset, audit_id, capability_path }) =>
            PolicyOutcome::NeedsUpgrade { suggested_preset, audit_id, capability_path },
        Err(PolicyEngineError::Degraded(m))               => PolicyOutcome::DegradedNoPolicy(m),
        Err(e)                                             => PolicyOutcome::InternalError(e.to_string()),
    }
}
```

The `PolicyOutcome::Pending` branch is what Case 7 and the multi-step Cases 5/6 produce.

---

## 5. `RouteDecision` event contract

### 5.1 Typed shape

```rust
pub struct RouteDecision {
    pub turn_id: TurnId,
    pub change_id: ChangeId,
    pub seq: Seq,

    // Null when route was refused (safety-deflection, needs-upgrade, pending-approval).
    pub chosen_tier: Option<TierId>,
    pub chosen_provider: Option<ProviderId>,

    pub rationale: RouteRationale,               // enum, stable static id + free-form static reason
    pub latency_budget_remaining_ms: u32,
    pub cost_estimate_cents: u32,
    pub requires_approval: bool,
    pub approval_ticket_id: Option<ApprovalTicketId>,

    // Carries the L5 audit trace id for any evaluate() called in this route.
    // - For multi-step plans, each step has its own policy_decision_ref; this field
    //   points at the *first* step's evaluate result so UIs can link into the audit.
    pub policy_decision_ref: Option<ChangeId>,

    pub privacy_posture_respected: bool,          // false only in Deny{PrivacyPostureViolation} cases — for debug surface
    pub tool_plan: Option<ToolPlan>,              // present for cases 4/5/6
    pub fallback_chain: Vec<FallbackStep>,        // deterministic order
    pub upgrade_hint: Option<UpgradePath>,        // for Case 9
    pub emitted_at: MonotonicTimestamp,
}

pub enum RouteRationale {
    DirectLocal,
    DirectRemote,
    LocalThenEscalate,
    ToolPlanSingleStep,
    ToolPlanMultiStep,
    SearchThenAnswer,
    NeedsApproval,
    SafetyDeflection,
    NeedsUpgrade,
    DegradedNoPolicy,
    DegradedNoRouter,       // self-emitted sentinel during recovery; never on happy path
    PrivateForceLocal,
    CostCapHit,
}

pub struct FallbackStep {
    pub tier: TierId,
    pub provider: ProviderId,
    pub reason_if_triggered: EscalationReason,
    pub cost_estimate_cents: u32,
}
```

### 5.2 Projection

Projected to the webview (X3 §3.2): the `RouteDecision` is emitted on `router/decision` channel with `source_layer = L4`. A **summary view** is projected; the full `ToolPlan` and `fallback_chain` are fetched on demand via `router.route_preview` or `trust.get_action_history`. L7 renders a **router debug overlay** (trust center) keyed on `policy_decision_ref`.

---

## 6. Policy integration — chokepoint design

This section is the heart of L4's design. Every side-effecting path must pass through one of the chokepoints documented here. **No silent-allow.** **No side channel.**

### 6.1 Tool invocation chokepoint

```
L1 reflex (tool-plan sketch) --> L4 route() --> build ToolCall --> L4 dispatcher:
   1. build ActionRequest { capability, resource_scope, actor_persona, provenance_tags, tier, cost_estimate }
   2. policy.evaluate(req)
   3. match Decision:
        Allow{ grant_ref }       -> dispatch adapter.invoke(call, grant_ref); await ToolResult
        Ask{ ticket }            -> park plan; emit RouteDecision{ requires_approval=true }; on ApprovalResponse{Allow*} resume
        DraftOnly{ reason }      -> adapter.draft_only(call); return ToolResult{ status=PartialOk(Draft), ... }
        Deny{ reason }           -> emit RouteDecision{ rationale=SafetyDeflection, chosen_tier=None }; hand deflection back to L1
        NeedsUpgrade{ path }     -> emit RouteDecision{ rationale=NeedsUpgrade, upgrade_hint=Some(path) }
```

**No executor is reachable except through the dispatcher.** A CI lint (`tools/lint-l4-bypass/` — shared with L5 §12) asserts that no `plugin-router-*` crate's `invoke` method is called from anywhere other than the dispatcher module.

### 6.2 Remote escalation chokepoint

Before a remote HTTP call is initiated:

1. **Privacy-posture gate** (L5 §10) is evaluated by a pre-flight `evaluate()` of `RouterEscalateRemote` OR — when private-tagged provenance is present — `RouterAllowRemoteWithPrivate` on `ResourceScope::Provider(provider)`.
2. **BYOK cost-cap gate** is evaluated implicitly: if L4 has seen `cost_threshold_hit { provider }` and no `re_armed` event since, L4 short-circuits with `Decision::Deny { reason: CostCapHit(provider) }` **without calling L5** (L5 already denied once; we mirror the decision locally for latency; L5 remains the source of truth on `re_arm`).
3. Only on `Allow` does L4 open a connection and serialize the payload. If the payload was already materialized speculatively (for latency), it is discarded on deny.

### 6.3 Privacy-posture pre-screen (L4 side)

Before step 1 of §6.2, L4 runs a **pre-screen** to avoid submitting `ActionRequest`s that are obviously doomed:

```rust
fn posture_allows_remote(hint: &RouteHint, persona: &CompiledPersona) -> bool {
    match (persona.privacy_posture, has_private_provenance(&hint.provenance_tags)) {
        (PrivacyPosture::Strict,  true)  => false,  // L5 would deny absent RouterAllowRemoteWithPrivate grant
        (PrivacyPosture::Strict,  false) => true,
        (PrivacyPosture::Balanced, true) => true,   // L5 decides per-call
        (PrivacyPosture::Balanced, false)=> true,
        (PrivacyPosture::Open,    _)     => true,
    }
}
```

Pre-screen is an **optimization only**; L5 is still called and is still authoritative. The pre-screen guarantees no payload is built that would fail the posture check when posture is Strict.

### 6.4 Cost-event emission (per call, always)

On every completed or cancelled provider call:

```rust
let ev = CostEvent {
    provider: adapter.provider_id,
    turn_id,
    request_id,
    tokens_in,       // counted from sanitized payload
    tokens_out,      // from stream completion or partial on cancel
    dollars_cents,   // provider pricing table × tokens
    call_started_at,
    call_ended_at,
    change_id,
    seq,
};
bus.emit(L4Event::CostEvent(ev));
```

L5 subscribes, updates counters (L5 §9), and may emit `cost_threshold_hit`. L4's `CostThresholdObserver` listens for that event and flips a local deny-flag for the provider (§9.4). The flag is advisory — the next evaluate() call confirms.

### 6.5 Never silent-allow — DegradedNoPolicy behavior

If `policy.evaluate` returns `Err(PolicyEngineError::Degraded(_))` OR if the L5 event-bus subscription drops and a health-tick heartbeat is missing for >500 ms:

- L4 transitions to `DegradedNoPolicy` internal state.
- Every side-effecting `route()` call returns `RouteDecision { chosen_tier: None, rationale: DegradedNoPolicy, requires_approval: false }`.
- `DirectLocal` pure-text routes remain allowed (no side effect, no memory/tool).
- Emits `tier_downgrade_notice { reason: PolicyUnavailable }` once per transition.
- On L5 recovery (first successful `evaluate`), exit `DegradedNoPolicy`; emit recovery telemetry.

---

## 7. Tool protocol — generic contract

### 7.1 `ToolCall` / `ToolResult` shapes

```rust
pub struct ToolCall {
    pub tool_id: ToolId,                   // stable, e.g. "browser.read_page.v1"
    pub capability: Capability,            // the L5 capability this step needs
    pub resource_scope: ResourceScope,
    pub input: ToolInput,                  // typed per-tool payload (bincode)
    pub deadline: MonotonicTimestamp,      // absolute; adapter must abort past this
    pub required_grants: Vec<GrantId>,     // from L5's Allow; propagated to adapter
    pub turn_id: TurnId,
    pub step_index: u16,                   // 0-based position in parent ToolPlan
    pub request_id: RequestId,
}

pub enum ToolResult {
    Ok       { tool_id: ToolId, output: ToolOutput, cost: Cents, change_id: ChangeId },
    Err      { tool_id: ToolId, err: ToolError, change_id: ChangeId },
    PartialOk{ tool_id: ToolId, output: ToolOutput, cost: Cents, reason: StaticReasonId, change_id: ChangeId },
    Cancelled{ tool_id: ToolId, cost_so_far: Cents, cause: CancelCause, change_id: ChangeId },
    PolicyDenied{ tool_id: ToolId, reason: DenyReason, audit_id: AuditId, change_id: ChangeId },
}
```

### 7.2 Error vocabulary (thiserror enum sketch)

```rust
#[derive(thiserror::Error, Debug, Clone)]
pub enum ToolError {
    #[error("tool unavailable: {0}")]
    ToolUnavailable(ToolId),

    #[error("policy denied: {0:?}")]
    PolicyDenied(DenyReason),

    #[error("timeout after {budget_ms} ms")]
    Timeout { budget_ms: u32 },

    #[error("provider rate-limited; retry after {retry_after_ms} ms")]
    ProviderRateLimited { provider: ProviderId, retry_after_ms: u32 },

    #[error("provider auth failed: {provider:?}")]
    ProviderAuthFailed { provider: ProviderId },

    #[error("provider unreachable: {provider:?}")]
    ProviderUnreachable { provider: ProviderId },

    #[error("invalid input: {0}")]
    InvalidInput(String),

    #[error("upstream malformed response")]
    UpstreamMalformed,
}
```

### 7.3 Multi-step orchestration rules

1. **Per-step policy gate.** Every step evaluates its own `ActionRequest`. A plan-wide `Allow` does **not** exist without the L5 `policy.preview_plan` + session-grant path (L5 §5.2, P2).
2. **User can approve step-by-step OR preset-session grant.** Step-by-step is the default; a session grant applies if one exists at evaluate-time.
3. **Partial results surface to L1 on cancel / barge-in.** On `RouterAdapter::cancel(turn_id)` (L1 §13.2):
    - In-flight step is `Cancelled` with `cost_so_far` charged and audited.
    - Future steps are skipped; plan terminates with aggregated `Cancelled` result.
    - L1 sees `route_decision` with `rationale = DegradedNoRouter` is **not** used here — barge-in uses a distinct `turn_end { outcome: Cancelled }` path.
4. **Deterministic step ordering.** Plan steps are numbered; a later step never dispatches before an earlier step completes. (Parallel steps are a future extension; not in P0–P2.)
5. **`PartialOk` semantics.** A step that runs in `DraftOnly` mode returns `PartialOk` with `output.kind = Draft`; the plan may still continue if the consuming step accepts a draft.

### 7.4 ToolPlan shape

```rust
pub struct ToolPlan {
    pub plan_id: PlanId,
    pub steps: Vec<PlanStep>,
    pub aggregate_risk: RiskClass,
    pub estimated_total_cost_cents: u32,
    pub estimated_total_latency_ms: u32,
}

pub struct PlanStep {
    pub index: u16,
    pub tool_id: ToolId,
    pub capability: Capability,
    pub resource_scope: ResourceScope,
    pub depends_on: Vec<u16>,            // indices into steps; empty for first step
    pub tier_hint: TierId,               // which tier the synthesis step expects to run on
    pub cost_estimate_cents: u32,
}
```

---

## 8. Provider / plugin model

### 8.1 Trait (aligned with X3 §5.3)

```rust
pub trait ProviderAdapter: Send + Sync {
    fn provider_id(&self) -> ProviderId;
    fn supported_tiers(&self) -> &[TierId];
    fn capabilities(&self, tier: TierId) -> &TierCapabilities;

    /// Text generation with streaming.
    fn generate(&self,
                req: GenerateRequest,
                deadline: MonotonicTimestamp) -> BoxStream<GenerateChunk>;

    /// Tool invocation (per-tool adapters may delegate to this).
    fn invoke_tool(&self,
                   call: ToolCall) -> BoxFuture<'static, ToolResult>;

    fn test_auth(&self) -> BoxFuture<'static, Result<AuthOk, ToolError>>;
    fn pricing_table(&self) -> &ProviderPricing;

    /// Health probe; called opportunistically by the health sampler.
    fn health_probe(&self) -> BoxFuture<'static, ProviderHealth>;
}
```

### 8.2 Plugin crate conventions (X3 §5.3)

- Local adapters: `aether-plugin-router-local-<runtime>` (e.g. `-ollama`, `-llamacpp`, `-vllm`).
- Remote adapters: `aether-plugin-router-remote-<provider>` (e.g. `-anthropic`, `-openai`, `-google`, `-groq`, `-openrouter`).
- Exactly one adapter crate per (runtime or provider). Crates register themselves with the router host at startup via a typed manifest.

### 8.3 Adding / removing a provider is a capability mutation

- **Adding a BYOK credential** for a new provider is itself an L5 capability mutation, routed through `policy.set_byok_credential` (§13). It:
  - Calls L5 `evaluate()` with capability `RouterEscalateRemote` on `ResourceScope::Provider(new_provider)` to confirm preset permits this provider family.
  - On Allow, stores the credential (§9).
  - Emits `byok_credential_added { provider_id }` event (§11).
- **Removing / rotating** is also an L5-gated command (§13 `router.rotate_byok`).

### 8.4 Provider registration manifest

```rust
pub struct ProviderManifest {
    pub provider_id: ProviderId,
    pub display_name: String,
    pub class: ProviderClass,               // LocalAlwaysOn | LocalOptional | RemoteBYOK | RemoteFreeTier
    pub supported_tiers: Vec<TierId>,
    pub pricing: ProviderPricing,
    pub adds_capabilities: Vec<Capability>, // e.g. vision, audio
    pub requires_network: bool,
    pub requires_byok: bool,
}
```

---

## 9. BYOK + wallet

### 9.1 Credential storage

- Backing store: OS keyring (Windows Credential Manager via `keyring-rs`; macOS Keychain; Linux Secret Service). Confirmed pattern per `18_model_router_spec.md` "Key storage" and consistent with L5 §8.3 HMAC-key pattern.
- **Never plaintext in config, env, logs, telemetry.**

### 9.2 Credential record shape (in-memory; stored in keyring opaque blob)

```rust
pub struct ByokCredential {
    pub provider_id: ProviderId,
    pub key_ref: KeyRef,                  // opaque handle into keyring; never returned to UI
    pub scope_limits: Vec<ScopeLimit>,    // e.g. endpoint allowlist, max tokens per request
    pub created_at_mono: MonotonicTimestamp,
    pub created_at_wall: WallClockTimestamp,
    pub rotation_due_at: Option<WallClockTimestamp>,
    pub last_auth_verified_at: Option<MonotonicTimestamp>,
    pub label: String,                    // user-facing label (e.g. "Personal Anthropic key")
}

pub enum KeyRef { KeyringEntry { service: String, account: String } }
```

The webview never sees `KeyRef`. The command `router.set_byok_credential` takes a secret payload, stores it in the keyring, and discards it in-process; responses return metadata only.

### 9.3 Wallet state

```rust
pub struct WalletState {
    pub per_provider: HashMap<ProviderId, ProviderWallet>,
    pub last_updated_mono: MonotonicTimestamp,
}

pub struct ProviderWallet {
    pub cents_spent_today: Cents,
    pub cents_spent_month: Cents,
    pub cents_spent_session: Cents,
    pub tokens_in_today: u64,
    pub tokens_out_today: u64,
    pub warn_at_cents: Option<Cents>,      // mirrors L5 §9.2 warn_at_pct resolved to absolute
    pub hard_cap_cents: Option<Cents>,     // mirrors L5 `per_provider_hard_cap_cents`
    pub hard_cap_hit: bool,                // local deny-flag; authoritative after re-arm is L5's
    pub rolling_p95_latency_ms: u32,
}
```

**Source of truth.** L5 owns the rolling counters (L5 §9.3 `cost_counters` table). L4's `WalletState` is a **projection cache** derived from the `cost_event`s it emits and the `cost_threshold_hit` + `re_armed` events it consumes. On boot, L4 rebuilds the cache from L5's canonical snapshot via `policy.get_audit_summary` filtered to cost events.

### 9.4 Local deny-flag mechanics

On `cost_threshold_hit { provider }`:
- L4 sets `wallet.per_provider[provider].hard_cap_hit = true`.
- `route()` for that provider returns `RouteDecision { rationale: CostCapHit, chosen_tier: None }`.
- Any in-flight call on that provider is allowed to *complete* but its cost is charged (L5 §9.4 grace behavior).

On `re_armed { provider }` (via `policy.reset_cost_counter` command flow):
- L4 clears the deny-flag.
- Subsequent routes for that provider call evaluate() normally.

### 9.5 Re-arm UX (flagged L5 open question §14.5)

- The UX of re-arming is **L5's open question**, not L4's (L5 §14.5). L4 simply honors the resulting event.
- L4 surfaces the need via `cost_threshold_hit` projected to L7, and via the `wallet` snapshot command.

---

## 10. Fallback chains

### 10.1 Per-tier fallback registry

```rust
pub struct FallbackRegistry {
    pub chains: HashMap<(TierId, PerfTier), Vec<FallbackStep>>,
    pub circuit_breakers: HashMap<ProviderId, CircuitBreaker>,
}
```

Chain examples (default; user-editable via settings later):

| Tier requested | Perf tier | Default chain |
|---|---|---|
| `main-local` | Lite | `main-local` → `main-remote` (posture permitting) → `fast-remote` → user-visible error |
| `main-local` | Balanced | `main-local` → `heavy-local` (if VRAM ok) → `main-remote` (posture permitting) → user-visible error |
| `main-local` | Full | `main-local` → `heavy-local` → `main-remote` (posture) → error |
| `heavy-remote` | any | `heavy-remote` → `main-remote` → `heavy-local` (posture + VRAM) → `main-local` → error |
| `fast-local` | Lite | `fast-local` → `fast-remote` → `main-local` (degraded) → error |

### 10.2 Trigger conditions

A fallback step fires when the primary returns any of:

- `ToolError::Timeout` (deadline exceeded).
- `ToolError::ProviderUnreachable`.
- `ToolError::ProviderRateLimited { retry_after_ms }` where `retry_after_ms > remaining_budget`.
- `ToolError::UpstreamMalformed`.
- `ToolError::ProviderAuthFailed` — except the chain skips all steps using that same credential (no repeated 401s).

A fallback step does **not** fire on `ToolError::PolicyDenied` — that is a deliberate deny, surfaced directly to L1/L7.

### 10.3 Circuit breaker

```rust
pub struct CircuitBreaker {
    pub state: BreakerState,               // Closed | HalfOpen | Open
    pub consecutive_failures: u8,
    pub opened_at: Option<MonotonicTimestamp>,
    pub cool_off_ms: u32,
}
```

Open after `consecutive_failures >= 3` in a 60-second window; HalfOpen after `cool_off_ms` (default 30 s); Closed after one successful call.

### 10.4 Fallback emits `escalation_reason`

Every time a chain step fires, L4 emits:

```rust
pub struct EscalationReasonEvent {
    pub turn_id: TurnId,
    pub from_tier: TierId,
    pub from_provider: ProviderId,
    pub to_tier: TierId,
    pub to_provider: ProviderId,
    pub reason: FallbackReason,         // PrimaryTimeout | RateLimit | Unreachable | AuthFailed | Malformed
    pub change_id: ChangeId,
    pub seq: Seq,
}
```

L7 trust-center renders this on the router debug overlay.

### 10.5 Tier-policy specifics

- **Lite:** fallback favors `*-remote` early (tiny local model is for reflex only). Remote first on `main-local` failure.
- **Balanced / Full:** fallback favors local (`heavy-local` next, then remote). Privacy-friendly by default.

---

## 11. Event contracts emitted

All events: `source_layer = SourceLayer::L4`, carry `change_id` and global monotonic `seq` (X3 §3.2).

### 11.1 Event catalog

```rust
pub enum L4Event {
    RouteDecision(RouteDecisionEvent),
    EscalationReason(EscalationReasonEvent),
    CostEvent(CostEventEvent),
    ToolCallStarted(ToolCallStartedEvent),
    ToolCallCompleted(ToolCallCompletedEvent),
    ProviderHealth(ProviderHealthEvent),
    ByokCredentialAdded(ByokCredentialAddedEvent),
    ByokCredentialRotated(ByokCredentialRotatedEvent),
    FallbackTriggered(FallbackTriggeredEvent),
    TierPreferenceChange(TierPreferenceChangeEvent),
}
```

### 11.2 Event table

| Event | Fields emphasized | Emitter | Subscribers | Idempotency | Projected to webview? |
|---|---|---|---|---|---|
| `route_decision` | `turn_id`, `chosen_tier`, `chosen_provider`, `rationale`, `cost_estimate_cents`, `requires_approval`, `fallback_chain`, `policy_decision_ref`, `privacy_posture_respected` | L4 | L1 (primary), L7 (debug overlay), L5 (audit correlation) | Unique per `turn_id` × `change_id` | **Yes** (summary) |
| `escalation_reason` | `turn_id`, `from_tier`, `from_provider`, `to_tier`, `to_provider`, `reason: FallbackReason` | L4 | L1 (attach to turn_end), L7 (trust center) | Unique per `(turn_id, seq)` | **Yes** |
| `cost_event` | `provider`, `turn_id`, `request_id`, `tokens_in`, `tokens_out`, `dollars_cents`, timing | L4 | **L5 (authoritative)**, L7 (live cost widget) | Idempotent on `request_id` | **Yes (summary)**; full via query |
| `tool_call_started` | `turn_id`, `step_index`, `tool_id`, `capability`, `resource_scope`, `deadline`, `grant_ref` | L4 | L1 (streaming progress), L7 | Unique per `request_id` | **Yes** |
| `tool_call_completed` | `turn_id`, `step_index`, `tool_id`, `result: ToolResultSummary { status, cost, cause? }` | L4 | L1, L7, L5 (audit correlation) | Unique per `request_id` | **Yes** |
| `provider_health` | `provider`, `state: ProviderHealthState`, `rolling_p95_latency_ms`, `last_failure_reason` | L4 | L7 (trust center health pane), L4 self (routing input) | Coalesced per provider per tick | **Yes (low-freq)** |
| `byok_credential_added` | `provider_id`, `label`, `created_at_wall` *(no secret)* | L4 | L5 (records as capability mutation), L7 (confirmation) | Unique per `provider_id × created_at` | **Yes** (no secret) |
| `byok_credential_rotated` | `provider_id`, `label`, `rotation_reason`, `rotated_at_wall` | L4 | L5, L7 | Unique | **Yes** |
| `fallback_triggered` | synonym of `escalation_reason` when the trigger is a **tier-level** step rather than provider-level; same payload shape plus `tier_step_index` | L4 | L7 | Unique | **Yes** |
| `tier_preference_change` | `from_tier`, `to_tier`, `cause: TierChangeCause`, `effective_at` | L4 | L1 (may emit its own tier_downgrade_notice), L7, core | Unique per change | **Yes** |

### 11.3 ChangeId / seq conventions

- Shared global monotonic `seq` counter with L1 / L5 (X3 §3.2).
- Every write-class command on L4's surface (§13) returns a `ChangeId` that correlates with the subsequent emitted event.

---

## 12. Events L4 subscribes to

| Event | Source | Handler action |
|---|---|---|
| `policy_decision` (L5) | L5 | Complete pending `PolicyOutcome`; resume parked plan step or abort per decision. |
| `approval_response` (L5, echoed internally as decision) | L5 | Handled via subsequent `policy_decision`. |
| `grant_issued` (L5) | L5 | Refresh local `PolicySnapshot`; may re-evaluate a deferred plan. |
| `grant_revoked` (L5) | L5 | If active call uses revoked grant → abort call with `ToolResult::PolicyDenied` + emit `tool_call_completed`; else record. |
| `cost_threshold_hit` (L5) | L5 | Flip local deny-flag for provider (§9.4). |
| `emergency_revoke_all` (L5) | L5 | Abort every in-flight call within 500 ms; emit `tool_call_completed { Cancelled { EmergencyRevoke } }` for each. |
| `route_hint` → actually delivered **as an argument to `router.request_route` command from L1**, not a bus event; L4 also subscribes to bus for pre-emptive hinting on partials (future). | L1 | Trigger `route()`. |
| `turn_state_change { BargedIn }` (L1) | L1 | Invoke internal `cancel(turn_id)` — abort in-flight tool calls + remote generations. |
| `barge_in_detected` (L1) | L1 | Same as above if not already cancelled. |
| `memory_hit` (L2, summary) | L2 | Update memory-confidence/provenance projection for subsequent routes in same turn. (L4 does not query L2 directly; L1 aggregates.) |
| `compiled_persona_ready` (L6) | L6 | Hot-reload persona tier preferences, privacy posture, llm_preferences. |
| `persona_swap_commit` (L6) | L6 | Swap active persona handle; any in-flight call finishes with old persona. |
| `core.health` tier downgrade | Core | Emit `tier_preference_change`; recompute fallback chain bindings. |
| `core.health` network_state change | Core | If Offline: deny remote tiers in `route()`; if back Online: re-enable. |

---

## 13. Tauri IPC commands (align with X3 §2.2)

Every command is a `#[tauri::command]` with typed request/response. Every write-class command returns `ChangeId`. Failure vocabulary is the `RouterIpcError` enum below; no untyped errors cross IPC.

```rust
#[derive(thiserror::Error, Debug)]
pub enum RouterIpcError {
    #[error("router degraded: {0:?}")]        Degraded(RouterDegradedMode),
    #[error("requires re-auth")]              RequiresReauth,
    #[error("policy denied: {0}")]            PolicyDenied(String),
    #[error("cost cap hit: {0}")]             CostCapHit(ProviderId),
    #[error("not found: {0}")]                NotFound(String),
    #[error("invalid: {0}")]                  Invalid(String),
    #[error("provider auth failed: {0}")]     ProviderAuthFailed(ProviderId),
    #[error("internal: {0}")]                 Internal(String),
}

pub enum RouterDegradedMode { DegradedNoPolicy, DegradedOffline, DegradedNoKeyring }
```

### 13.1 Command catalog

| Command | Request | Response | Failure vocab | Side effects | Capability-gated? |
|---|---|---|---|---|---|
| `router.route_preview` | `RouteHint` | `RoutePlan { preview_decision: RouteDecision, step_previews: Vec<StepPreview> }` | `Degraded`, `Invalid` | None (dry-run; per L5 §5.2 preview semantics — no grants issued) | No (read-only) |
| `router.request_route` | `RouteHint` | `ChangeId` | `Degraded`, `PolicyDenied`, `CostCapHit` | Triggers `route()` pipeline; emits `route_decision` event | No (the pipeline itself is the gate) |
| `router.set_tier_override` | `TierOverride { scope: OverrideScope { Session \| Persona \| Task }, tier: TierId }` | `ChangeId` | `Degraded`, `Invalid`, `RequiresReauth` | Evaluates `RouterOverrideTier` via L5; on Allow, persists | **Yes** (L5-gated per L5 §2.2 RouterOverrideTier) |
| `router.list_providers` | `()` | `Vec<ProviderSummary { id, display_name, class, supported_tiers, enabled, key_present, wallet_summary }>` | `Degraded` | None | No (read-only) |
| `router.set_byok_credential` | `ByokSetRequest { provider, key_payload: SecretString, label, scope_limits }` | `ByokSetReceipt { change_id, provider, label, created_at_wall }` *(no secret)* | `ProviderAuthFailed`, `RequiresReauth`, `Invalid`, `Degraded`, `PolicyDenied` | Evaluates policy (capability mutation); stores in keyring; runs `test_auth`; emits `byok_credential_added` | **Yes** (L5-gated; `SecretString` is never serialized back to UI) |
| `router.rotate_byok` | `RotateRequest { provider, new_key_payload: SecretString, reason }` | `ByokRotateReceipt { change_id }` | `ProviderAuthFailed`, `RequiresReauth`, `Degraded` | Same as set + emits `byok_credential_rotated` | **Yes** |
| `router.remove_byok` *(new)* | `RemoveRequest { provider }` | `ChangeId` | `RequiresReauth`, `Degraded`, `NotFound` | Deletes keyring entry; emits rotation-like event with `reason = Removed` | **Yes** |
| `router.test_byok` *(new)* | `TestRequest { provider }` | `TestReceipt { ok: bool, detail: Option<String> }` | `ProviderAuthFailed`, `Degraded` | Runs `adapter.test_auth`; no audit write beyond a low-class record | No |
| `router.cancel_tool_call` | `CancelRequest { turn_id }` | `ChangeId` | `NotFound`, `Degraded` | Aborts all in-flight tool calls + remote generations for the turn; emits `tool_call_completed { Cancelled }` per call | No |
| `router.get_cost_snapshot` | `SnapshotFilter { provider?: ProviderId, window?: TimeWindow }` | `WalletState` | `Degraded` | None | No (read-only) |
| `router.get_provider_health` | `()` | `Vec<ProviderHealthSummary>` | `Degraded` | None | No (read-only) |
| `router.set_fallback_chain` *(new, P2+)* | `ChainEdit { tier, perf_tier, chain: Vec<FallbackStep> }` | `ChangeId` | `RequiresReauth`, `Invalid`, `Degraded` | Evaluates policy (widens trust surface); persists | **Yes** |

### 13.2 Capability-gating

Per X3 §2.2 the one pre-frozen L4 gating rule is that `router.set_tier_override` is gated. This document extends the rule: any command that **widens trust surface, stores secrets, or mutates provider set** requires L5 re-auth:

- `router.set_tier_override`
- `router.set_byok_credential`
- `router.rotate_byok`
- `router.remove_byok`
- `router.set_fallback_chain`

`test_auth` / `list_providers` / `get_cost_snapshot` / `route_preview` are read-only and ungated.

---

## 14. Failure modes and degraded operation

### 14.1 Missing tool → `ToolError::ToolUnavailable`

- `route_tool_plan` detects no registered adapter for the required `tool_id`.
- Emit `tool_call_completed { Err(ToolUnavailable) }`.
- Parent plan aborts; `route_decision` rationale becomes `NeedsUpgrade` if a known install path exists (e.g. install browser plugin), else `SafetyDeflection`.

### 14.2 Policy denial

- On `Decision::Deny`:
  - Case 8: `route_decision { chosen_tier: None, rationale: SafetyDeflection }`.
  - L1 picks a Safety deflection phrase (L1 §7.1, §10.1).
  - `DenyReason::NeedsUpgrade` routes to Case 9 with `upgrade_hint` for L7.
- On `Decision::Ask`: plan parked; on `ApprovalResponse::Allow*` resume; on `Deny` emit route_decision Case 8.

### 14.3 L5 unreachable → `DegradedNoPolicy`

- Detection: `PolicyEngineError::Degraded(_)` **or** 500 ms heartbeat miss.
- Behavior: only `ReflexCategory::DirectLocal` pure-text calls allowed; all side-effecting routes return `route_decision { rationale: DegradedNoPolicy }`.
- Emit `tier_preference_change { cause: PolicyUnavailable }`.
- Recovery: on first successful `evaluate()`, exit.

### 14.4 Provider timeout / rate-limit

- Per §10.2 fallback triggers; chain walked in order.
- On chain exhaustion: emit `tool_call_completed { Err(Timeout) }` or equivalent; `route_decision` already emitted pointed at the original tier.
- Caller (L1) sees the terminal error via the streaming pipeline and transitions `Repairing`.

### 14.5 BYOK auth failure

- `ToolError::ProviderAuthFailed`.
- Disable provider in wallet (`key_present = false`).
- Emit `byok_credential_rotated { reason: AuthFailed }` *(pseudo-rotation event; payload field `requires_rotation = true`)*.
- L7 surfaces a "rotate credential" prompt via trust center.
- Fallback chain: skip any step using the same credential.

### 14.6 Cost-cap reached

- On `cost_threshold_hit { provider }` from L5: flip deny-flag.
- Subsequent `route()` returns `route_decision { chosen_tier: None, rationale: CostCapHit }`.
- L1 shows cap-hit message via the standard deflection path.
- Re-arm requires L5 `policy.reset_cost_counter` (L5 §9.4); on `re_armed` event, L4 clears the flag.

### 14.7 Memory unavailable (L2 `DegradedNoMemory`)

- L1 already handles this (L1 §10.3) by proceeding with empty context.
- L4 sees `RouteHint { memory_confidence: 0.0, provenance_tags: [] }`.
- **Effect on routing:** low confidence *would* normally escalate to remote; the L4 decision-tree adds a bias — if `DegradedNoMemory` is flagged in the hint (new field below), reduce remote bias to avoid sending low-signal prompts to paid providers on a known-degraded path.

```rust
pub struct RouteHint {
    // existing fields...
    pub memory_degraded: bool,    // new; L1 sets when memory_query missed deadline
}
```

### 14.8 Persona unavailable (L6 `MinimumTrust`)

- L4 swaps to the baked-in MinimumTrust persona (mirrors L5 §11.4): tier preference `main-local` only, posture `Strict`, `remote_bias = 0`.
- Remote tiers unavailable until `compiled_persona_ready` arrives.

### 14.9 Keyring unavailable → `DegradedNoKeyring`

- All BYOK-required remote tiers disabled; free-tier providers (OSS Preview Guest) still available.
- Emit `tier_preference_change { cause: KeyringUnavailable }`.
- L7 surfaces error; user prompted to fix keyring state.

### 14.10 Degraded-mode catalog

| Trigger | Mode | Allowed routes | Exit |
|---|---|---|---|
| L5 down | `DegradedNoPolicy` | DirectLocal pure-text only | L5 recovery |
| L2 down | (per-turn flag) | all, with empty context + remote-bias reduced | next L2-healthy turn |
| L6 compile fail | MinimumTrust | `main-local` only | `compiled_persona_ready` |
| Network offline | `DegradedOffline` | all local tiers; no remote | network restored |
| Keyring unavailable | `DegradedNoKeyring` | local + free-tier remote | keyring restored |
| Cost cap hit (provider) | per-provider deny-flag | all tiers minus that provider | L5 `re_armed` event |

---

## 15. Tier awareness

Maps to X3 §8.3 performance tiers.

| Dimension | Lite | Balanced | Full |
|---|---|---|---|
| **Default tier** | `main-remote` (BYOK or Guest OSS Preview) | `main-local` | `main-local` |
| **Fallback default** | `fast-remote` / `fast-local` | `main-remote` (posture permitting) | `heavy-local` |
| **Max concurrent tool calls per turn** | 1 | 2 | 4 |
| **`cost_event` emission frequency** | coalesce every 500 ms during streaming (end-of-call authoritative) | 250 ms | every chunk |
| **Heavy-remote availability when offline** | disabled | disabled | disabled |
| **Health probe cadence** | 60 s | 30 s | 15 s |
| **`provider_health` event projection to webview** | 1 per 30 s per provider | 1 per 10 s | live |
| **Concurrent streaming generations** | 1 | 2 | 4 |

On a mid-session tier downgrade from core.health: L4 drains current turn on old limits, applies new limits from next turn.

---

## 16. Stub interfaces (unblock L1 / L7 against L4)

### 16.1 Rust traits

```rust
pub trait ModelRouter: Send + Sync {
    /// Primary entry: synchronous route selection. Returns RouteDecision.
    /// Non-blocking wrt L5 auto-allow; parks on Ask.
    fn route(&self, hint: RouteHint) -> Result<RouteDecision, RouterError>;

    /// Submit a ToolCall for execution. Returns a job handle; results arrive via events.
    fn submit_tool_call(&self, call: ToolCall) -> Result<TurnJob, RouterError>;

    /// Cancel every in-flight job for a turn (barge-in, user escape).
    fn cancel(&self, turn_id: TurnId) -> Result<(), RouterError>;

    fn list_providers(&self) -> Vec<ProviderSummary>;
    fn cost_snapshot(&self, filter: Option<SnapshotFilter>) -> WalletState;

    fn subscribe(&self, filter: L4EventFilter) -> EventStream<L4Event>;
}

pub struct TurnJob {
    pub turn_id: TurnId,
    pub request_id: RequestId,
    pub change_id: ChangeId,
    pub stream: BoxStream<ToolCallChunk>,
}

#[derive(thiserror::Error, Debug)]
pub enum RouterError {
    #[error("degraded: {0:?}")] Degraded(RouterDegradedMode),
    #[error("policy denied: {0:?}")] PolicyDenied(DenyReason),
    #[error("cost cap hit: {0:?}")] CostCapHit(ProviderId),
    #[error("bus closed")] BusClosed,
    #[error("internal: {0}")] Internal(String),
}
```

### 16.2 Adapter traits L4 depends on (each layer implements one)

```rust
pub trait PolicyAdapter: Send + Sync {
    fn evaluate(&self, req: ActionRequest) -> Result<Decision, PolicyEngineError>;
    fn snapshot_grants(&self, filter: GrantFilter) -> Vec<Grant>;
    fn subscribe(&self, filter: EventFilter) -> EventStream<L5Event>;
    fn is_degraded(&self) -> bool;
}

pub trait PersonaAdapter: Send + Sync {
    fn current(&self) -> Arc<CompiledPersona>;
    fn subscribe_swaps(&self) -> EventStream<PersonaEvent>;
}

pub trait HealthAdapter: Send + Sync {
    fn current(&self) -> CoreHealth;
    fn subscribe(&self) -> EventStream<CoreHealthEvent>;
}
```

### 16.3 What each downstream stubs

| Consumer | Stubs against | Acceptable fake |
|---|---|---|
| **L1** | `RouterAdapter::request_route` → eventual `route_decision`; `RouterAdapter::cancel` | Always-direct-local adapter; variant that emits `escalation_reason` to exercise `tier_downgrade_notice`; variant that returns `DegradedNoPolicy` |
| **L5** | L4 consumes `PolicyEngine::evaluate`; L4 emits `cost_event`; L4 subscribes to `cost_threshold_hit` | L5 already exposes §12 stub matrix; L4 consumes directly |
| **L7** | `router.*` command surface; `route_decision`/`cost_event`/`provider_health` events | Scripted adapter that drives all 9 decision cases |

---

## 17. Testing strategy (design level)

### 17.1 Property tests

- **Routing idempotency.** For any `RoutingContext` with fixed inputs, `route(ctx)` returns identical `RouteDecision` fields (modulo `request_id` / `change_id` / `seq`). A deterministic per-turn seed is used for any tie-break randomness.
- **Fallback determinism.** For a fixed chain + fixed failure sequence, the fallback walk is identical across runs.
- **Tier monotonicity.** On tier downgrade, the set of allowed providers shrinks or stays the same — never grows.

### 17.2 Policy-gate red-team tests

- **No bypass.** For every side-effecting decision case (2, 4–9) fuzz asserts that no tool adapter is invoked and no remote HTTP connection is opened until a `policy.evaluate` returning `Allow` has been observed.
- **Silent-allow simulation.** With L5 stub set to `Err(Degraded)`, every side-effecting case must return `RouteDecision { rationale: DegradedNoPolicy }`. Pass criterion: zero adapter `invoke` calls, zero HTTP connections.
- **Chokepoint static lint.** A CI lint asserts that `ProviderAdapter::invoke_tool` and `ProviderAdapter::generate` are called from exactly one module (`dispatcher`), and that module's call sites are preceded by a `policy.evaluate` call on the same request path (enforced via type-system shape: the dispatcher accepts a proof-of-allow token struct only constructed from a `Decision::Allow`).

### 17.3 Privacy-posture leak tests

- For every `(PrivacyPosture, provenance_tag_set, intended_route)` tuple, assert: if posture is Strict and any tag is `private`, no remote payload is constructed, no remote HTTP connection is opened, and `route_decision.privacy_posture_respected = true`.
- Mutation tests flip a single provenance tag to `private` in an otherwise-permitted remote route and assert the decision flips to `PrivateForceLocal` (unless `RouterAllowRemoteWithPrivate` grant is active).

### 17.4 Cost-cap fire-time tests

- Seed a provider with cumulative cost just below `hard_cap_cents`. Fire a call whose estimate crosses the cap. Pass: current call completes (grace per L5 §9.4); next call returns `CostCapHit`; subsequent `route_decision` rationale is `CostCapHit` until `re_armed`.

### 17.5 Replay tests

- Given the captured event log (a sequence of `route_decision`, `cost_event`, `tool_call_started/completed`, `escalation_reason`, `fallback_triggered` events), the routing history can be deterministically reconstructed. Mutation of a single event causes replay to diverge with a specific diff location.

### 17.6 Cross-layer integration tests

- L4 + stub-L5 (allow-all) + stub-L1 (scripted route_hint cadence) + stub-L6 (static persona): every decision case hit at least once.
- L4 + real-L5 + stub-L1: end-to-end `ActionRequest → policy_decision → tool_call_started → tool_call_completed → cost_event` chain; assert `audit_record`s in L5 reference matching `request_id`s.

---

## 18. Deliverables summary — what an implementer builds first

In dependency order:

1. **`ModelRouter` trait + typed `RouteHint` / `RouteDecision`.** `l4-router-core` crate with no runtime dependencies beyond `serde` + `thiserror`. Unblocks L1 and L7 design against frozen contracts.
2. **Tool-call orchestration skeleton with L5 policy adapter.** `dispatcher` module: accepts `ToolCall`, calls `PolicyAdapter::evaluate`, routes on `Decision`. Proof-of-allow token struct only constructible from a `Decision::Allow` (compile-time bypass prevention).
3. **Tier abstraction + fallback chain registry.** `FallbackRegistry`, default chains per §10.1, circuit breaker.
4. **Provider plugin trait.** `ProviderAdapter` trait + `ProviderManifest` + registration host.
5. **BYOK credential vault (OS keyring adapter).** `ByokVault` trait + `keyring-rs` default impl + test impl.
6. **Cost-event emitter.** `CostEventEmitter` module; guarantees one event per completed/cancelled call; wallet cache updater.

What comes *after* first-action:

- Remote adapter crates (`aether-plugin-router-remote-anthropic`, `-openai`, `-google`, `-groq`, `-openrouter`).
- Local adapter crates (`aether-plugin-router-local-ollama`, `-llamacpp`).
- `policy.preview_plan` integration (P2) for multi-step plan approvals.
- Latency-aware rolling-p95 provider scoring (P3).

---

## 19. Open questions

Each: **Question** — why it matters — proposed default — impact if defaulted silently.

1. **Final Gemma 4 variant name per tier.** `18_model_router_spec.md` locks the concept; final model IDs are deferred.
   - **Why it matters:** affects every `fast-local` / `main-local` / `heavy-local` row.
   - **Proposed default:** ship placeholders; wire concrete names at first release gate; `OPEN_QUESTIONS.md` tracks.
   - **Impact if defaulted silently:** a model-name mismatch breaks local inference silently until first local call fires.

2. **BYOK cost-cap re-arm UX (flagged also in L5 §14.5).** L4 defers the UX to L5 but both docs flag.
   - **Why it matters:** a click-to-re-arm collapses the hard-cap.
   - **Proposed default:** L5's proposed default (re-auth + typed confirm + audited) accepted; L4 simply honors the resulting event.
   - **Impact if defaulted silently:** users rubber-stamp re-arm; cap becomes soft.

3. **Plan-preview (`policy.preview_plan`) P1 vs P2.** L5 defaults P2 (L5 §14.8). L4's multi-step orchestration is cleaner *with* preview.
   - **Why it matters:** without preview, multi-step plans per-step-ask → approval fatigue.
   - **Proposed default:** follow L5's P2 default; L4 ships per-step-ask for P0/P1 and bundles to preview at P2.
   - **Impact if defaulted silently:** P0/P1 Operator-preset users hit repeated asks on Search-then-answer.

4. **Speculative payload materialization.** To hit latency budgets, L4 may want to speculatively build a remote payload before the privacy-posture evaluate() returns.
   - **Why it matters:** if done wrong, memory-resident private content is prepared for a remote call that gets denied.
   - **Proposed default:** **no speculation** — always await policy decision before serializing. Accept 5–15 ms latency cost.
   - **Impact if defaulted silently:** a Deny after speculation leaves private content in a buffer destined for wire format; memory-leak class of concern.

5. **Streaming cost-event coalescing on Lite.** §15 defaults 500 ms coalescing; authoritative end-of-call event always fires.
   - **Why it matters:** Lite event bandwidth; UI smoothness.
   - **Proposed default:** 500 ms coalesce; end-of-call authoritative event irrespective of coalescing.
   - **Impact if defaulted silently:** trust-center live cost widget feels laggy on Lite, which is acceptable.

6. **Provider manifest signing.** Is the provider-plugin manifest signed at build (X3 §5.3)?
   - **Why it matters:** if a malicious third-party adapter is loaded, the whole chokepoint is in-proc.
   - **Proposed default:** first-party only for P0–P2; plugin signing deferred to Pro Phase 4+ when a plugin SDK ships.
   - **Impact if defaulted silently:** a future plugin SDK without signing opens supply-chain risk.

7. **Who owns the Guest-mode (OSS Preview) endpoint adapter?** `18_* §provider catalog` + `03_content_lock §2`.
   - **Why it matters:** Guest is a free-tier remote path that still consumes L5; its scope limits (rate / tokens) are enforced where?
   - **Proposed default:** Guest is an `aether-plugin-router-remote-guest` adapter; rate/token limits enforced at adapter level; L5 still gates `RouterEscalateRemote`; no BYOK key; never in Pro.
   - **Impact if defaulted silently:** rate-limit bypass if adapter is sloppy.

8. **Pinned-model override per persona.** `18_* §per-persona LLM preferences` allows a user to pin a specific model for a persona.
   - **Why it matters:** conflicts with tier abstraction if a pinned model is on a tier the posture blocks.
   - **Proposed default:** the pin is a **hint**; privacy posture and cost caps still win. If pin resolves to a disallowed provider under current posture, L4 falls back per §10 and emits `escalation_reason { reason: PinOverridden }`.
   - **Impact if defaulted silently:** user expects Claude Opus, gets local fallback with no visible reason.

9. **Doctrine 7-vs-8 layer count.** Same flag L1 §16.9 and L5 §14.11 raise. This doc uses 7-layer per `plans/00_ORCHESTRATION_MAP.md §1`.
   - **Why it matters:** implementer reading only `01_product_doctrine.md` would look for a separate reflex router.
   - **Proposed default:** 7-layer canonical; reflex inside L1.
   - **Impact if defaulted silently:** drift.

10. **`RouterAllowRemoteWithPrivate` grant scope shape.** L5 §14.12 defaults per-provider + task-scoped; this doc follows.
    - **Why it matters:** global waiver collapses privacy posture.
    - **Proposed default:** per-provider + task-scoped. L4 constructs the ActionRequest with `resource_scope = Provider(provider)` accordingly.
    - **Impact if defaulted silently:** single waiver opens all providers.

11. **Latency-aware routing data store.** Rolling p95 per (tier, provider) lives where? A `tauri-plugin-store` blob, an in-memory ring buffer, or an L5-coordinated aggregate?
    - **Why it matters:** persistence vs freshness.
    - **Proposed default:** in-memory ring buffer with periodic checkpoint to `core.cache`; no L5 coordination needed.
    - **Impact if defaulted silently:** cold-start has no latency data → routes on default tier preference for first N turns.

12. **HTTP client crate.** `reqwest` vs `hyper`-directly vs per-provider SDK.
    - **Why it matters:** supply-chain size, streaming semantics, TLS root handling.
    - **Proposed default:** `reqwest` with `rustls` for streaming HTTP; per-provider SDKs only if they wrap non-HTTP transport (rare).
    - **Impact if defaulted silently:** fragmented TLS config surface per provider.

13. **Contradiction with `plans/L4_model_router.md` P0 scope.** The upstream plan says P0 ships "fast + main tiers only, local Gemma 4, single optional BYOK to frontier." This document enumerates seven tiers including `heavy-*` as first-class. Not a contradiction for contracts (trait is tier-generic) but a scoping note — P0 ships `fast-local`, `main-local`, `main-remote` adapters; `heavy-*` tiers exist in the type system but have no registered adapter.
    - **Why it matters:** an implementer could ship heavy-* adapters in P0 against doctrine.
    - **Proposed default:** tier type system shipped complete in P0; adapter registration is gated by the P0 scope (only `fast-local`, `main-local`, `main-remote`).
    - **Impact if defaulted silently:** P0 scope bloat.

14. **`policy.preview_plan` dry-run audit.** L5 §14.9 defaults dry-run for interactive previews. L4's `router.route_preview` parallels this.
    - **Why it matters:** if route_preview writes audit records, every hover over a plan step bloats the log.
    - **Proposed default:** `router.route_preview` is **dry-run only**; no `ActionRequest` emitted; no audit. Actual execution via `router.request_route` writes normal audit chain.
    - **Impact if defaulted silently:** log bloat or blind spot.

15. **Contradiction between `18_model_router_spec.md` "Anti-patterns" and the tool-use roadmap.** `18` says tool calling is "Aether Pro phase 4+" but this document's §7 (tool protocol) is a P0–P2 concern for Search-then-answer and tool plans. Reconciliation: the **contract** exists from P0 (so L1 / L5 can stub), but the *adapter implementations* arrive at Pro Phase 4. Not a contradiction in doctrine; a sequencing note.

---

## 20. Self-review checklist

- [x] §4: Every routing decision case has a policy checkpoint column (table §4.1; pseudocode §4.2; §4.3 explicit `enforce_policy` wrapper).
- [x] §6: Every tool-call path goes through the chokepoint design (tool §6.1; remote §6.2; privacy §6.3; cost §6.4; DegradedNoPolicy §6.5).
- [x] §11: Every emitted event has typed fields + projection flag (§11.2 table).
- [x] §13: Every command marks capability-gating (§13.1 "Capability-gated?" column; §13.2 rule).
- [x] §14: Degraded-mode entry for each upstream — L5 (§14.3), L1 (barge-in handled §12 subscription + §7.3), L2 (§14.7), L6 (§14.8); plus keyring (§14.9), network-offline (§14.10), cost (§14.6). Catalog §14.10.
- [x] §16: Stub surface for L1 (`RouterAdapter` trait-equivalent via `request_route` + `cancel` + event subscription) and L7 (command catalog + event projection). L5 uses its own §12 matrix.
- [x] No path in this document bypasses L5: every side-effecting case (4–9) runs through `enforce_policy`; §6.5 DegradedNoPolicy prevents silent-allow; §17.2 red-team tests codify the invariant.

---

## 21. Closing notes

- **Contracts frozen in this document:** §2 `RouteHint` shape (matches L1 §7.4); §3 tier set; §5 `RouteDecision` shape; §7 `ToolCall` / `ToolResult` / `ToolPlan`; §8 `ProviderAdapter` trait; §9 `WalletState` + `ByokCredential` shapes; §11 L4 event catalog; §13 Tauri command surface; §16 `ModelRouter` trait + `RouterAdapter` adapter traits.
- **Canonical package home** (X1-dependent): file:///C:/Users/dbhav/Projects/aether/packages/l4-router/ (Rust) + file:///C:/Users/dbhav/Projects/aether/packages/l4-router-ts/ (typed bindings) + file:///C:/Users/dbhav/Projects/aether/crates/plugin-router-remote/ per X3 §5.3.
- **Immediately adjacent layer to design next:** L7 trust UX / onboarding — it consumes every L4 event projection, owns the BYOK wizard, and renders the router debug overlay. L2 memory kernel is the other candidate because it supplies the memory-confidence + provenance-tag contract that feeds `RouteHint`.
