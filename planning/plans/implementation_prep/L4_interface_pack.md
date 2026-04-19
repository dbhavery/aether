# L4 Model Router — Interface Pack

> **Layer:** L4 Model Router (Aether)
> **Canonical package:** file:///C:/Users/dbhav/Projects/aether/packages/l4-router/
> **Typed bindings:** file:///C:/Users/dbhav/Projects/aether/packages/l4-router-ts/
> **Remote plugin crates:** file:///C:/Users/dbhav/Projects/aether/crates/plugin-router-remote/
> **Primary source:** file:///C:/Users/dbhav/Projects/aether-planning/plans/L4_model_router_system_design.md
> **Cross-cut:** file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_L4_L5_L7_integration_notes.md
> **Status:** Wave A interface draft — contracts only, no code.

---

## 1. Purpose

L4 is the **tier-abstracted model and tool router** for Aether. Cognition, L1, and L7 never ask for a concrete model — they ask L4 for a **tier** (`fast-local | main-local | heavy-local | fast-remote | main-remote | heavy-remote | tool-plan-executor`) plus a typed `RouteHint`, and L4 maps that to a concrete `(provider, model, adapter)` selection, assembles tool plans, brokers BYOK credentials, tracks cost, and hands back a `RouteDecision`.

**Load-bearing invariant — reinforced:** *every* tool call, remote model call, and side-effecting provider action flows through L5's `PolicyEngine::evaluate` chokepoint. L4 has **no bypass path**. The only local short-circuit is a mirrored `CostCapHit` deny (L5 already denied once; L4 mirrors for latency and re-confirms on next evaluate). DegradedNoPolicy mode (L5 unavailable) emits `RouteDecision { chosen_tier: None, rationale: DegradedNoPolicy }` — never silent-allow.

---

## 2. Primary responsibilities

L4 **owns**:

- **Tier abstraction.** 7-tier taxonomy; `TierCapabilities` per `(tier, provider)` pair; capability-set advertising at plugin load.
- **Route selection.** Typed decision tree consuming `RouteHint` (L1) + `CompiledRouting` (L6) + `MemoryConfidenceSummary` (L2) + `core.health` signals, emitting `RouteDecision`.
- **Fallback chains.** Per-tier deterministic fallback order with circuit-breaker on repeat failure.
- **BYOK credential brokerage.** OS-keyring-backed vault; credentials never cross the webview; add / rotate / test / remove flows.
- **Cost accounting.** Per-provider rolling counters; `cost_event` emission on every completed call. *L5 owns cap enforcement* — L4 is the emitter and honors `CostThresholdHit` by flipping a local deny-flag.
- **Tool-plan orchestration.** Builds `ToolCall` envelopes, submits them through L5 (`ActionRequest`), assembles results, threads them into a final payload handed back to L1 via streaming pipeline. Orchestration is **subject to L5** — every step is gated.
- **Provider health telemetry.** Rolling p95 per `(tier, provider)` → routing input and L7 trust-center projection.

L4 explicitly **does NOT own**:

- **Policy decisions** → L5.
- **Memory retrieval** → L2 (L4 only consumes summaries).
- **Turn timing / barge-in detection** → L1 (L4 subscribes to cancel).
- **Presence / ambient state** → L3.
- **Persona compilation** → L6.
- **Inference runtimes or model weights** → borrowable deps behind `ProviderAdapter`.
- **Hard-cap enforcement** → L5 (L4 emits events, refuses to route post-threshold).

---

## 3. Inbound interfaces

| From | Contract | Purpose |
| --- | --- | --- |
| **L1 Interaction Timing** | `RouteHint` (shape frozen in L1 §7.4 + L4 §2.1) | Seed of every route request. Fields: `turn_id`, `reflex_category`, `tier_preference`, `memory_confidence_summary`, `tool_plan_sketch: Option<ToolPlanSketch>`, `provenance_tags`, `latency_budget_ms`, `T_hard_deadline`. |
| **L1 Interaction Timing** | `barge_in_detected { turn_id }` bus event | Cancel in-flight tool calls for that `turn_id`; emit `ToolCallCompleted { result: Cancelled { cause: BargeIn } }`. |
| **L6 Persona Compiler** | `CompiledRouting` (subset of `CompiledPersona`) | `preferred_tier`, `temperature`, `max_output_tokens`, `pinned_model?`, `privacy_posture: PrivacyPosture`, `system_prompt`, `safety_header`. |
| **L2 Memory Kernel** | `MemoryConfidenceSummary` (attached to `RouteHint`, not fetched) | `peak_confidence: f32`, `provenance_tag_rollup: Vec<ProvenanceTag>`, `below_remote_escalation_threshold: bool`. |
| **L5 Policy Engine** | `PolicyDecision { Allow / Ask / Deny / NeedsUpgrade }` (synchronous reply to `evaluate`) | Gate for every side-effecting case (4–9 in L4 §4.1). |
| **L5 Policy Engine** | `GrantIssued { grant_id, scope, expiry }` bus event | Refresh local `PolicySnapshot`; wake parked deferred plans. |
| **L5 Policy Engine** | `GrantRevoked { grant_id }` bus event | Invalidate cached grants; force next `evaluate` to re-ask. |
| **L5 Policy Engine** | `CostThresholdHit { provider, threshold_cents }` bus event | Flip local deny-flag for provider; future `route()` short-circuits to `CostCapHit` rationale until `re_armed`. |
| **L5 Policy Engine** | `re_armed { provider }` bus event | Clear local deny-flag. |
| **L5 Policy Engine** | `EmergencyRevokeAll` bus event | Cancel all in-flight tool calls; drop all grants; emit `FallbackTriggered { cause: EmergencyRevoke }`. |
| **core.health** | Tier signal: `PerfTier { Lite | Balanced | Full }`, `vram_pressure: VramPressure`, `network_state: NetworkState` | Trigger tier downgrade / force offline routing; emit `TierPreferenceChange`. |

---

## 4. Outbound interfaces

| Event / Return | Consumer | Purpose |
| --- | --- | --- |
| `RouteDecision` (return of `route`; also bus-projected to `router/decision`) | L1 (primary), L7 (projection) | Authoritative routing output. |
| `EscalationReason` (embedded in `RouteDecision.fallback_chain[*].reason_if_triggered` and standalone `escalation_reason` event) | L7 trust center | Tells user *why* fallback fired (`CostCapHit`, `PrivacyPosture`, `ProviderUnreachable`, `RateLimited`, `PinOverridden`, `CircuitOpen`). |
| `CostEvent { change_id, provider, tier, cents, tokens_in, tokens_out, ts }` | L5 (authoritative counter), L7 (live wallet widget) | Emitted at **request-completion**, not streaming. Cap enforcement is L5's. |
| `ToolCallStarted { change_id, tool_id, tier, provider, actor_persona }` | L5 (audit chain), L7 (timeline) | Start marker; correlates with `ChangeId`. |
| `ToolCallCompleted { change_id, result: ToolResult }` | L5, L7, L1 | End marker; carries `ToolResult` variant (`Ok / Err / PartialOk / Cancelled / PolicyDenied`). |
| `ProviderHealth { provider, state: ProviderHealthState, rolling_p95_latency_ms, last_failure_reason }` | L7 (health pane), L4 self (routing input) | Coalesced per provider per tick. |
| `BYOKCredentialAdded { provider, key_fingerprint }` | L5 (audit), L7 (wallet UI) | Never contains key material. |
| `BYOKCredentialRotated { provider, old_fingerprint, new_fingerprint }` | L5, L7 | Same — metadata only. |
| `BYOKCredentialRemoved { provider, fingerprint }` | L5, L7 | Same. |
| `FallbackTriggered { change_id, from: ProviderId, to: ProviderId, reason: EscalationReason }` | L7 (debug overlay), L5 (audit) | Surfaces the chain traversal. |
| `TierPreferenceChange { from: PerfTier, to: PerfTier, cause: TierChangeCause }` | L7, L6 (may recompile) | core.health-driven downgrades/upgrades. |

---

## 5. Synchronous vs asynchronous boundaries

| Surface | Mode | Notes |
| --- | --- | --- |
| `router.route_preview` | **Sync** (dry-run, read-only) | No `ActionRequest` emitted; no audit; no side effects. Returns a candidate `RouteDecision` *shape* plus `fallback_chain`. Ungated. |
| `router.request_route` | **Sync return of `RouteDecision`**; tool execution spawned async | Returns quickly with `ChangeId`; tool calls proceed on the tokio runtime. |
| Tool call dispatch (`submit_tool_call`) | **Async**, correlated by `ChangeId` | Progress via `ToolCallStarted` → `ToolCallCompleted`. Cancellation via `cancel(ChangeId)` or `barge_in_detected`. |
| `CostEvent` emission | **Async, at request-completion**, not real-time-streaming | Partial tokens do NOT emit incremental `CostEvent`s; Lite UI is coalesced per §15 default 500 ms; authoritative end-of-call event always fires. |
| `router.test_auth` / `list_providers` / `cost_snapshot` | **Sync**, read-only, ungated | No `ActionRequest`. |
| BYOK add/rotate/remove | **Sync** keyring write + async `BYOKCredentialAdded/Rotated/Removed` event | Keyring op returns before bus emission. |
| L5 `evaluate` call | **Sync** from L4's perspective (awaited) | L4 blocks the route decision on L5's verdict. |

---

## 6. Typed contract suggestions

> Pseudo-Rust. Field names lifted from L4 §2, §5, §7, §8, §9, §11. No code — shapes only.

### 6.1 Core trait — `ModelRouter`

```rust
pub trait ModelRouter: Send + Sync {
    /// Primary entry. Sync return; tool execution spawned async and correlated by ChangeId.
    fn route(
        &self,
        ctx: &RoutingContext,
        policy: &dyn PolicyAdapter,
    ) -> Result<RouteDecision, RouterIpcError>;

    /// Dispatches a tool call through L5. Returns correlation id; progress via events.
    fn submit_tool_call(
        &self,
        call: ToolCall,
        policy: &dyn PolicyAdapter,
    ) -> Result<ChangeId, RouterIpcError>;

    /// Cancel an in-flight tool call or plan (by ChangeId or turn_id).
    fn cancel(&self, target: CancelTarget) -> Result<(), RouterIpcError>;

    /// Read-only provider inventory (no key material).
    fn list_providers(&self) -> Vec<ProviderSummary>;

    /// Read-only cost projection cache (authoritative counters live in L5).
    fn cost_snapshot(&self, filter: Option<SnapshotFilter>) -> WalletState;

    /// Event subscription surface for L1 / L7.
    fn subscribe(&self, filter: L4EventFilter) -> EventStream<L4Event>;
}
```

### 6.2 Provider plugin trait — `ProviderAdapter`

```rust
pub trait ProviderAdapter: Send + Sync {
    fn manifest(&self) -> &ProviderManifest;
    fn supported_tiers(&self) -> &[TierId];
    fn tier_capabilities(&self, tier: TierId) -> Option<&TierCapabilities>;

    /// Perform a model call. MUST NOT be invoked without a preceding L5 Allow.
    fn invoke(
        &self,
        req: InvokeRequest,
        ctx: &InvokeContext,
    ) -> BoxFuture<'static, Result<InvokeResponse, ProviderError>>;

    /// Execute a single tool step. MUST NOT be invoked without a preceding L5 Allow.
    fn invoke_tool(
        &self,
        call: &ToolCall,
        ctx: &InvokeContext,
    ) -> BoxFuture<'static, ToolResult>;

    /// Liveness + auth + rate state.
    fn health_probe(&self) -> BoxFuture<'static, ProviderHealth>;

    /// Auth smoke test. Used by BYOK wizard.
    fn test_auth(&self, cred: &ByokCredentialRef) -> BoxFuture<'static, AuthTestOutcome>;
}
```

### 6.3 `TierCapabilities`

```rust
pub struct TierCapabilities {
    pub tier: TierId,
    pub provider: ProviderId,
    pub supports_text:            bool,
    pub supports_tool_use:        bool,
    pub supports_grounding:       bool,
    pub supports_vision_in:       bool,
    pub supports_audio_in:        bool,
    pub supports_streaming:       bool,
    pub max_context_tokens:       u32,
    pub max_output_tokens:        u32,
    pub privacy_class:            PrivacyClass,   // Local | Guest | RemoteFrontier
    pub cost_model:               CostModel,
}
```

### 6.4 `ProviderManifest`

```rust
pub struct ProviderManifest {
    pub id:                ProviderId,
    pub display_name:      String,
    pub class:             ProviderClass,         // Local | GuestRemote | FrontierRemote
    pub supported_tiers:   Vec<TierId>,
    pub requires_byok:     bool,
    pub keyring_slot:      Option<KeyringSlotId>,
    pub default_fallback_from: Option<ProviderId>,
    pub privacy_class_max: PrivacyClass,
    pub signed_build_hash: Option<BuildHash>,     // open — see §8
}
```

### 6.5 Tool protocol structs

```rust
pub struct ToolCall {
    pub change_id:      ChangeId,
    pub turn_id:        TurnId,
    pub tool_id:        ToolId,
    pub tier_hint:      TierId,
    pub inputs:         ToolInputs,
    pub provenance:     Vec<ProvenanceTag>,
    pub actor_persona:  PersonaId,
    pub cost_estimate:  Cents,
    pub deadline:       MonotonicTimestamp,
}

pub enum ToolResult {
    Ok        { tool_id: ToolId, output: ToolOutput, cost: Cents, change_id: ChangeId },
    Err       { tool_id: ToolId, err: ToolError, change_id: ChangeId },
    PartialOk { tool_id: ToolId, output: ToolOutput, cost: Cents, reason: StaticReasonId, change_id: ChangeId },
    Cancelled { tool_id: ToolId, cost_so_far: Cents, cause: CancelCause, change_id: ChangeId },
    PolicyDenied { tool_id: ToolId, reason: DenyReason, audit_id: AuditId, change_id: ChangeId },
}

pub enum ToolError {
    ToolUnavailable,
    PolicyDenied       { audit_id: AuditId, reason: DenyReason },
    Timeout            { elapsed_ms: u32 },
    ProviderRateLimited{ retry_after_ms: Option<u32> },
    ProviderAuthFailed { provider: ProviderId },
    ProviderUnreachable{ provider: ProviderId, cause: StaticReasonId },
    InvalidInput       { field: &'static str, reason: StaticReasonId },
    UpstreamMalformed  { provider: ProviderId, schema_ref: StaticReasonId },
}
```

### 6.6 Fallback + circuit breaker

```rust
pub struct FallbackRegistry {
    pub chains_by_tier:   HashMap<TierId, Vec<FallbackStep>>,
    pub circuit_breakers: HashMap<ProviderId, CircuitBreaker>,
}

pub struct FallbackStep {
    pub provider:          ProviderId,
    pub tier:              TierId,
    pub reason_if_triggered: EscalationReason,
}

pub struct CircuitBreaker {
    pub provider:          ProviderId,
    pub state:             BreakerState,   // Closed | Open | HalfOpen
    pub failures_in_window: u16,
    pub window_ms:         u32,
    pub opened_at:         Option<MonotonicTimestamp>,
    pub cooldown_ms:       u32,
}
```

---

## 7. Error vocabulary

```rust
pub enum RouterIpcError {
    Degraded        { cause: DegradedCause },       // L5 down, keyring locked, network off
    InvalidRequest  { field: &'static str, reason: StaticReasonId },
    UnknownProvider { provider: ProviderId },
    UnknownTool     { tool_id: ToolId },
    NotAuthorized   { scope: ResourceScope },       // capability-gated command w/o grant
    Internal        { reason: StaticReasonId },
}
```

Tool-layer errors are **not** carried in `RouterIpcError`; they are surfaced as `ToolError` variants inside `ToolResult::Err` / `PartialOk`:

- `ToolUnavailable` — tool_id not registered for this persona/tier.
- `PolicyDenied` — L5 returned `Decision::Deny`; carries `audit_id`.
- `Timeout` — per-step `T_hard_deadline` or provider timeout.
- `ProviderRateLimited` — upstream 429 / equivalent.
- `ProviderAuthFailed` — BYOK key invalid / revoked.
- `ProviderUnreachable` — DNS/TLS/transport failure.
- `InvalidInput` — schema validation pre-dispatch.
- `UpstreamMalformed` — provider returned a response that fails the adapter's schema.

---

## 8. Dependency expectations

- **L5 Policy Engine** — **load-bearing**. Every side-effecting route case (L4 §4.1 cases 2–6) calls `PolicyEngine::evaluate`. Every `submit_tool_call` gates on `evaluate`. L4 honors `cost_threshold_hit`, `grant_issued`, `grant_revoked`, `emergency_revoke_all`. **No bypass under any condition.** DegradedNoPolicy (L5 unavailable) emits refusal, never silent-allow.
- **L6 Persona Compiler** — consumed via `PersonaAdapter::current() -> CompiledRouting` for `preferred_tier`, `temperature`, `max_output_tokens`, `pinned_model?`, `privacy_posture`, `system_prompt`, `safety_header`. L6 is not queried per-call; current compile is cached.
- **L1 Interaction Timing** — supplies `RouteHint` as the argument to `router.request_route`; supplies `barge_in_detected` for cancellation.
- **L2 Memory Kernel** — L4 never queries L2 directly. L2 attaches `MemoryConfidenceSummary` to the `RouteHint` L1 hands down.
- **core.health** — tier signal + VRAM pressure + network state.

**Forbidden dependency paths:** L4 MUST NOT call provider adapters' `invoke` / `invoke_tool` without a preceding L5 `Allow`. L4 MUST NOT read or decrypt BYOK key material on behalf of the webview. L4 MUST NOT persist cost counters as the source of truth (that's L5 §9.3); the `WalletState` is a projection cache.

---

## 9. Implementation notes

- **Canonical crate:** file:///C:/Users/dbhav/Projects/aether/packages/l4-router/ (Rust, per monorepo §2). Typed bindings in file:///C:/Users/dbhav/Projects/aether/packages/l4-router-ts/.
- **Remote provider plugins:** one crate per remote provider as `aether-plugin-router-remote-*` (e.g. `-anthropic`, `-openai`, `-guest`), per X3 §5.3. First-party only for P0–P2; plugin signing deferred to Pro Phase 4+ (see open item).
- **BYOK vault:** file:///C:/Users/dbhav/Projects/aether/packages/storage/ via OS keyring (Windows Credential Manager, macOS Keychain, libsecret on Linux). Key material never crosses the Tauri IPC boundary; the webview only ever sees fingerprints.
- **P0 adapter scope:** only `fast-local`, `main-local`, `main-remote` adapters registered; `heavy-*` tiers exist in the type system but gate at registration. Full 7-tier type set ships in P0.
- **HTTP client:** `reqwest` + `rustls` (per open item #12 in source doc).
- **Latency telemetry:** in-memory ring buffer, periodic checkpoint to `core.cache`; no L5 coordination.
- **Tauri command surface:** every write-class command returns `ChangeId`; every command's failure surface is `RouterIpcError`; capability-gating marked per command table in source §13.

---

## 10. Open questions — FLAGGED, blocking implementation

> Forwarded from source §19 and L1↔L4↔L5↔L7 integration notes. These must be closed (or explicitly deferred with recorded defaults) before L4 code lands.

### 10.1 Per-step re-evaluation rule for tool plans
When `ToolPlan { steps: [..] }` is approved as a bundle (L5 `preview_plan` at P2), does each step re-enter L5 `evaluate` or does the bundle grant cover all steps for the plan's lifetime? Source doc §4.1 row 5 defaults "per-step OR plan-preview bundle" but leaves the re-eval trigger conditions (grant expiry mid-plan, upstream `ProviderHealth` flip, mid-plan posture change from L6 recompile) unspecified.
**Decision needed:** re-eval triggers. **Proposed default:** bundle grant covers steps; re-eval forced on (a) `GrantRevoked`, (b) `TierPreferenceChange` crossing Local↔Remote, (c) `PrivacyPosture` change from L6 recompile, (d) any `CostThresholdHit`.
**Impact if unflagged:** either approval fatigue (per-step re-ask) or stealth posture bypass mid-plan.

### 10.2 Speculative payload materialization
To meet Lite latency budgets L4 *could* serialize a remote payload before `evaluate` returns. Source §19 item 4 proposes **no speculation** as default. Unresolved: whether Balanced/Full tiers with higher budgets *should* speculate for TTFT wins, and where the speculated buffer lives (process memory vs `core.cache`) to avoid private content leaking into a post-Deny buffer.
**Decision needed:** speculation policy per `PerfTier`; buffer residency; erase-on-Deny semantics.
**Proposed default:** no speculation on any tier for P0–P2; re-evaluate at Pro Phase 3 with encrypted scratch buffer.
**Impact if unflagged:** a Deny after speculation leaves private content in a buffer destined for wire format — memory-leak class of concern.

### 10.3 Cost-cap re-arm (`re_armed`) flow
L5 owns the re-arm UX (L5 §14.5). L4 mirrors the deny-flag locally for latency. Unresolved: (a) whether `re_armed` re-arms the cap immediately or requires the next `evaluate` to confirm, (b) what happens to deferred/parked plans waiting on the cap — auto-resume, re-route, or surface to L7 for user action, (c) whether a re-arm during an in-flight plan retroactively permits the already-denied step or starts a new `ChangeId`.
**Decision needed:** re-arm semantics for L4's local deny-flag and parked plans.
**Proposed default:** re-arm clears the flag; parked plans are re-routed (not auto-resumed) with a fresh `ChangeId` and new `evaluate` call; L7 surfaces a `FallbackTriggered { reason: CostCapReArm }` notice.
**Impact if unflagged:** either silent resumption (defeats the cap's friction purpose) or stale-denial lockout after legitimate re-arm.

> Additional open items inherited from source §19: Gemma 4 variant names, plan-preview P1-vs-P2, streaming cost coalescing, provider manifest signing, Guest-mode adapter ownership, pinned-model override, doctrine 7-vs-8 layer count, `RouterAllowRemoteWithPrivate` grant scope shape, latency telemetry store, HTTP client crate, P0 scope vs 7-tier type system, `route_preview` audit behavior, tool-use roadmap sequencing.

---

## 11. Invariant restatement (do not remove)

> **Every tool call and every remote model call flows through L5's `PolicyEngine::evaluate`. L4 has no bypass path. The only local short-circuit is a mirrored `CostCapHit` deny that L5 has already issued. DegradedNoPolicy emits refusal, never allow. No `ProviderAdapter::invoke` / `invoke_tool` executes without a preceding `Decision::Allow`.**
