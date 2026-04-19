# Test Matrix Master — Aether

> Canonical test matrix consolidating per-layer testing plans, integration notes, and the red-team brief into a single verification contract for Aether.
>
> **Sources consolidated:**
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L1_interface_pack.md through L7_interface_pack.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md (§14)
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_memory_kernel_system_design.md (§16)
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L3_presence_engine_system_design.md (§14)
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L4_model_router_system_design.md (§17)
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md (§13)
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L6_persona_compiler_system_design.md (§15)
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L7_trust_ux_onboarding_system_design.md (§18)
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_L4_L5_L7_integration_notes.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_L3_L6_integration_notes.md
> - file:///C:/Users/dbhav/Projects/aether-planning/13_trust_security_redteam.md

---

## 1. Test philosophy

Trust is the product moat. Aether's entire thesis — a presence-first AI companion that a user can entrust with private memory, autonomous action, and long-lived personality — collapses the first time an invariant silently drifts, a permission gate silently regresses, or a degraded mode silently produces deceptive output. Every surface of the system either earns trust or squanders it. Interface tests and contract tests matter **here specifically** because:

- **Events cross typed-contract boundaries.** Layers are assembled from independently buildable crates (L1 orchestration, L2 memory, L3 presence, L4 routing, L5 policy, L6 persona, L7 shell). They communicate only through versioned events, IPC commands, and trait interfaces. A drift in field naming or semantics that compiles cleanly on each side can still silently break the integration — contract tests catch this before cross-layer integration.
- **Invariants are load-bearing.** The event contract doc specifies ten-plus global invariants (monotonic turn ids, append-only audit chain, persona precedence order, no-tool-without-grant, etc.). These cannot be enforced by types alone — they require property-based tests that fuzz inputs and assert invariants hold across every reachable state.
- **Degraded modes must be exercised, not assumed.** A tier downgrade, a vector index rebuild, a reflex classifier timeout, a BYOK auth failure, a cost cap hit — each of these is a plausible real-world path. If any degraded mode is only defined on paper, the product will ship with frozen UIs, deceptive operation, or silent data loss. Every degraded path has a corresponding test in the matrices below.
- **Trust demands auditability.** Every privileged action must produce an audit record. Replay tests verify that the event log alone is sufficient to reconstruct the privileged state of the system (grant ledger, memory, turn state, persona).
- **Security posture is adversarial.** Prompt injection, memory poisoning, crafted persona packs, and exfiltration through export are not hypothetical. A red-team matrix is included as a first-class test category, not a post-ship afterthought.

**Test categories.** The matrix organises verification into seven categories:

| Category | Purpose | Example |
|---|---|---|
| (a) Unit per-layer | Verify a single layer's module-level behavior in isolation | `L5::evaluate()` returns Ask when grant missing |
| (b) Contract | Verify interface shape, event schema, ts-rs binding round-trip | Every event in event_contracts_master deserializes cleanly into its TS type |
| (c) Integration | Verify cross-layer flows with real adapters where feasible | L1 → L5 → L7 approval flow end-to-end |
| (d) Property | Verify determinism, monotonicity, idempotency, and other invariants under fuzz | Persona compile is deterministic over the full input space |
| (e) Red-team | Verify defenses against adversarial inputs | Injected memory content cannot execute a privileged tool |
| (f) Replay | Verify that event logs reconstruct privileged state | Grant ledger rebuilt from `audit_record` stream matches live state |
| (g) Perf | Verify latency, throughput, and tier-fps budgets are met | T_first_state_change ≤250 ms at P95 under nominal load |

Tests below are tagged with the applicable categories.

---

## 2. Per-layer test matrices

Seven tables follow, one per layer. Priority: **P0** = must pass before any implementation merges; **P1** = before OSS Preview ship; **P2** = before Pro Phase 1 gate. "Depends on" references upstream test IDs or layers that must be green first.

### 2.1 L1 — Interaction Timing

| # | Scenario | Input | Expected output | Failure path | Depends on | Priority |
|---|---|---|---|---|---|---|
| L1-T01 | First-ack fires within 250 ms under normal load | New utterance event, L2/L4 nominal | `turn_state_change → Acknowledging` within 250 ms P95; ack phrase queued | If deadline missed, `late_ack` event emitted and UI degrades to typed ellipsis | — | P0 |
| L1-T02 | Reflex classifier SLA: late result discarded | Classifier returns at 200 ms (>150 ms budget) | Late result dropped; fallback routing path used | Orphaned classifier output never reaches router | L4 stubs | P0 |
| L1-T03 | Barge-in during Speaking cuts TTS within 150 ms | User speech detected mid-`Speaking` state | TTS buffer flushed; `barge_in` event; `turn_state_change → Listening` within 150 ms P99 | Residual audio after 150 ms flagged in perf test | L3 TTS mock | P0 |
| L1-T04 | L5 Deny → safety-deflection path, repair state | L5 emits `evaluate.Deny` mid-turn | L1 enters `Repairing`; persona-appropriate deflection phrase; no partial tool output surfaces | Tool output leakage = hard fail | L5, L6 | P0 |
| L1-T05 | Persona swap at end-of-utterance (safe boundary) | `persona_swap_begin` received mid-`Speaking` | Swap held until end-of-utterance boundary; `swap_commit` then applied | Mid-utterance swap = fail (inconsistent voice) | L6 | P0 |
| L1-T06 | L2 memory timeout → empty-memory path tagged | Memory retrieval does not return within 150 ms | Turn proceeds with `memory_empty=true` flag; response acknowledges absent recall | Hallucinated recall from timeout = hard fail | L2 stubs | P0 |
| L1-T07 | Turn-state monotonicity under event storm | Floods of reflex, memory, tool events across 1000 turns | Monotonic `turn_id`; no state inversion; all terminal states reached | Inverted state transitions caught by property test | — | P1 |
| L1-T08 | Coalescing under degraded tier | Event rate > Lite tier cap | Events coalesced by policy; no frozen UI; event integrity preserved | Dropped terminal state = fail | L3 | P1 |

### 2.2 L2 — Memory Kernel

| # | Scenario | Input | Expected output | Failure path | Depends on | Priority |
|---|---|---|---|---|---|---|
| L2-T01 | Retrieval respects policy denies | Query matches memory whose `privacy_class` is denied by current grant | Matching memory is suppressed; `memory_denied` event logged | Leak of denied content = hard fail | L5 | P0 |
| L2-T02 | Novelty filter deduplicates within 100-vector window | Near-duplicate embedding arrives within sliding window | Duplicate suppressed; provenance count on canonical entry increments | Duplicate-admitted = storage bloat + retrieval skew | — | P0 |
| L2-T03 | Deleting memory cascades provenance re-weighting | User deletes memory M; M was source for downstream summaries | Derived records re-weighted or marked `source_deleted`; `memory_cascade` event | Stale derived records surfacing next turn = fail | — | P0 |
| L2-T04 | Retention engine expires within 24h of expires_at | Memory with `expires_at = T` | Record removed within 24 h of T; tombstone audit record written | Long-lived expired record = privacy-posture breach | — | P0 |
| L2-T05 | Vector index rebuild → lexical-only fallback | Index file corrupted or rebuilding | Retrieval falls back to lexical/BM25; `retrieval_degraded` event | Silent empty results = deceptive operation | — | P1 |
| L2-T06 | `memory_hit` carries `privacy_class` on every hit | Any retrieval result | Every emitted `memory_hit` event has `privacy_class` set; property test verifies | Missing field on any hit = contract violation | — | P0 |
| L2-T07 | Edit cascades provenance re-evaluation | User edits memory; downstream persona `observed_style` referenced it | `observed_style` candidate re-evaluated; L6 notified | Stale learned style = fail | L6 | P1 |
| L2-T08 | Schema migration forward + backward compatibility | Old DB + new binary; new DB + old binary (rollback) | Migrations apply; rollback is clean; user data preserved | Data loss on migration = hard fail | — | P1 |

### 2.3 L3 — Presence Engine

| # | Scenario | Input | Expected output | Failure path | Depends on | Priority |
|---|---|---|---|---|---|---|
| L3-T01 | Behavior scheduler priority: safety > repair > barge-in > speaking > ambient | Simultaneous candidates across priority classes | Highest-priority behavior wins deterministically; others deferred or dropped | Wrong winner under ties = fail | — | P0 |
| L3-T02 | Anti-uncanny bounds never exceeded | Input stream that would produce out-of-bound expression params | Params clamped before render; `uncanny_clamp` event | Out-of-bound value reaches renderer = fail | — | P0 |
| L3-T03 | Rendering surface crash → offline indicator visible | Renderer panics mid-frame | Presence surface shows offline indicator within 1 s; no silent frozen frame | Frozen frame without indicator = deceptive operation | L7 | P0 |
| L3-T04 | Viseme drift > N ms → resync event | Audio/viseme alignment exceeds threshold | `viseme_resync` event; resync completes without visible glitch over 2 frames | Persistent drift = uncanny regression | L1 | P1 |
| L3-T05 | Tier downgrade mid-utterance smooth | `core.health.tier_downgrade` fires during Speaking | Fidelity reduced at next frame boundary; no visible pop | Pop/flash on downgrade = fail | — | P1 |
| L3-T06 | Persona hot-swap blends visual params over window | `persona_swap_commit` received | Visual params interpolate over blend window (e.g., 400 ms); no instantaneous jump | Instantaneous jump = uncanny | L6 | P1 |
| L3-T07 | Reduced-motion flag propagated from L7 | User toggles reduced-motion in shell | All non-essential motion disabled within one frame; essential cues retained | Motion continues = accessibility violation | L7 | P0 |
| L3-T08 | Tier-appropriate fps sustained 60 s under load | Lite/Balanced/Full runs respectively | 10/30/60 fps sustained over 60 s P95 | Sustained dips below target = perf fail | — | P1 |

### 2.4 L4 — Model Router

| # | Scenario | Input | Expected output | Failure path | Depends on | Priority |
|---|---|---|---|---|---|---|
| L4-T01 | Tool call gated by L5 (never bypasses) | Any tool invocation path | `evaluate` call precedes tool execution on every path; property-test across reachable states | Any path that skips L5 = hard fail | L5 | P0 |
| L4-T02 | Fallback chain triggers on provider rate-limit | Primary remote provider returns 429 | Chain falls back to next provider (local if posture allows); `route_fallback` event | Request dropped or infinite retry = fail | — | P0 |
| L4-T03 | Private memory blocked from remote route without waiver | Context contains `privacy_class=private`, route is remote, no waiver | Request denied at L5; fallback to local model or deflection | Private content leaves device = hard fail | L5, L2 | P0 |
| L4-T04 | BYOK auth failure surfaces to L7 | User-supplied key fails auth | `byok_auth_failed` event to L7; clear remediation surfaced | Silent fallback to anonymous = trust breach | L7 | P0 |
| L4-T05 | Multi-step plan gated step-by-step (or bundle grant per open rule) | Plan with N steps, each tool-gated | Every step has an L5 evaluation OR a bundle-grant covers them all per agreed rule | Any step without gate = fail | L5 | P0 |
| L4-T06 | `cost_event` emitted per request completion | Any completed request (local or remote) | Exactly one `cost_event` per request with monetary + token fields | Missing or duplicated event = accounting drift | — | P0 |
| L4-T07 | Streaming cancel on mid-flow revoke | Grant revoked during streamed response | Stream cancelled within 150 ms; partial tokens not persisted | Persistence of revoked-content tokens = fail | L5 | P1 |
| L4-T08 | Router selects local when tier = Lite and task fits | Lite tier + small-model-suitable task | Local model chosen deterministically; no remote call attempted | Remote call on Lite = fail | — | P1 |

### 2.5 L5 — Policy Engine

| # | Scenario | Input | Expected output | Failure path | Depends on | Priority |
|---|---|---|---|---|---|---|
| L5-T01 | Evaluate a capability with no grant | Tool request, no matching grant | `Ask` ticket emitted; request pends | Auto-allow = hard fail | — | P0 |
| L5-T02 | Revoke grant mid-turn | Active in-flight tool call, user revokes grant | In-flight tool calls cancelled; `grant_revoked` + cancel cascade | Tool completes after revoke = hard fail | L4 | P0 |
| L5-T03 | Audit-chain tamper detection | Mutated audit record inserted | Integrity check fails; `audit_tamper` event; subsequent writes paused pending review | Tamper undetected = hard fail | — | P0 |
| L5-T04 | Cost threshold hit | Cost accumulates past configured cap | `cost_threshold_hit` event; subsequent cost-incurring requests denied until re-arm | Requests continue past cap = fail | L4 | P0 |
| L5-T05 | Emergency revoke-all | User invokes panic revoke | `EmergencyRevokeAll` event; all in-flight grants cleared; pending UI approvals wiped | Any residual grant after event = hard fail | L4, L7 | P0 |
| L5-T06 | Persona-scoped defaults applied | Persona with scoped defaults active | Precedence honored: hardcoded > user > persona > preset > system | Precedence inversion = fail | L6 | P0 |
| L5-T07 | Grant ledger append-only invariant | Attempt in-place mutation | Rejected; only append-with-supersede path succeeds | In-place mutation succeeds = fail | — | P0 |
| L5-T08 | Evaluate latency budget | 10k-grant ledger, random evaluate | P99 ≤200 ms worst case, P99 ≤20 ms typical | Regression = perf fail | — | P1 |

### 2.6 L6 — Persona Compiler

| # | Scenario | Input | Expected output | Failure path | Depends on | Priority |
|---|---|---|---|---|---|---|
| L6-T01 | Deterministic compilation given same inputs | Fixed persona + user overrides + preset | Byte-identical compiled artifact across runs | Non-determinism = fail | — | P0 |
| L6-T02 | Signature verification for privileged overlay | Overlay arrives without valid signature | Compilation rejected; `persona_sig_invalid` event | Unsigned overlay accepted = hard fail | — | P0 |
| L6-T03 | Schema migration round-trip | v(n) persona pack → v(n+1) → v(n) | Round-trip preserves all user-observable fields | Data loss on migration = fail | — | P1 |
| L6-T04 | Persona-swap rollback on compile fail | New persona fails to compile mid-swap | Previous persona retained; `persona_swap_failed` event; no partial state | Partial persona state = hard fail | L1, L3 | P0 |
| L6-T05 | Observed-style confirmation required before apply | Candidate observed style accumulated | Applied only after explicit user confirmation; no silent learning | Silent apply = trust breach | L7 | P0 |
| L6-T06 | Precedence: hardcoded > user > persona > preset > system | Conflicting values across sources | Higher-precedence value wins; property test over enumerated conflicts | Inversion = fail | L5 | P0 |
| L6-T07 | Compile latency budget | Typical persona pack | P95 under budget (TBD; e.g., 50 ms) | Regression = perf fail | — | P1 |
| L6-T08 | Diff-only emit on swap | Swap with unchanged sub-trees | Only changed sub-trees emitted downstream; consumers ignore unchanged | Full re-emit causes downstream churn = perf regression | — | P2 |

### 2.7 L7 — Trust UX / Onboarding / Shell

| # | Scenario | Input | Expected output | Failure path | Depends on | Priority |
|---|---|---|---|---|---|---|
| L7-T01 | `approval_pending` renders within 100 ms of event | L5 emits approval-pending | Approval modal visible within 100 ms P95 | Late render = perceived unresponsiveness | L5 | P0 |
| L7-T02 | Optimistic UI rolls back on late Deny | UI optimistically shows in-progress; L5 later denies | UI rolls back cleanly; no visible partial effect | Orphaned in-progress UI = fail | L5 | P0 |
| L7-T03 | Secret never appears in React state | BYOK flow, user pastes key | Key stored in shell-adapter secret field; never in component props, Redux, or devtools-visible state | Key visible in devtools = hard fail | — | P0 |
| L7-T04 | Reduced-motion flag propagates to L3 | User toggles reduced-motion | L3 receives flag; all non-essential motion disabled within one frame | Motion continues = accessibility fail | L3 | P0 |
| L7-T05 | Degraded-mode banner visible within one event | `core.health.degraded` received | Banner visible within one event cycle; clear explanation surfaced | Hidden degradation = deceptive operation | — | P0 |
| L7-T06 | Audit export gated by L5 | User requests audit export | Export command routed through L5 `pending export` flow; approved export produces tamper-evident bundle | Bypass of L5 on export = hard fail | L5 | P0 |
| L7-T07 | Onboarding persona-picker persists on swap | User selects persona in picker | Selection persists and survives restart; `persona_swap_begin` emitted | Selection reverts = trust breach | L6 | P1 |
| L7-T08 | Error boundaries isolate shell panics | React panic in one region | Panic contained to region; rest of shell functional; offline banner if core region affected | Whole-app crash = fail | — | P1 |

---

## 3. Cross-layer end-to-end scenarios

Each scenario exercises multiple layers in a realistic flow. Structured as: **Initial state → Steps → Layer-by-layer expectations → Pass criteria → Known risks**.

### 3.1 Scenario A — "Open ~/Downloads/report.pdf and summarize"

| Field | Detail |
|---|---|
| Initial state | Cold session, no prior file access grant; default privacy posture |
| Steps | 1. User utterance captured. 2. L1 routes to planner. 3. L4 proposes read-file tool. 4. L5 evaluates → Ask. 5. L7 shows approval modal. 6. User approves. 7. L5 issues grant. 8. L4 executes read. 9. L2 ingests content (if within user intent). 10. L4 summarises. 11. L1 returns Speaking. |
| Expected per layer | L1: states Acknowledging → Planning → Awaiting → Speaking. L4: tool call sequenced; cost_event emitted. L5: Ask then Allow; grant ledger appended; audit recorded each step. L7: modal <100 ms; no secret leakage. L2: ingestion respects privacy_class=local. |
| Pass criteria | Every step has an audit record; turn completes <6 s; no remote escalation unless BYOK+waiver; report.pdf content never leaves device |
| Known risks | Tool-plan re-eval rule (open) may over-request scope; L5 ticket latency under large ledger |

### 3.2 Scenario B — "Ask a personal question requiring memory recall"

| Field | Detail |
|---|---|
| Initial state | Session with warmed memory; persona active |
| Steps | 1. Utterance captured. 2. L1 reflex classifies as direct-local + memory query. 3. L2 retrieval fires. 4. L2 returns hit within 150 ms. 5. L1 grounds response with persona-weighted phrase. |
| Expected per layer | L1: ack within 250 ms; 150 ms memory deadline honored. L2: memory_hit with privacy_class. L6: persona style applied. No L4 remote call. |
| Pass criteria | 150 ms memory deadline honored; ack phrase persona-weighted; no remote escalation |
| Known risks | Vector-store vendor variance may shift ranking; reflex classifier false-negative routes remote unnecessarily |

### 3.3 Scenario C — "User revokes memory mid-session"

| Field | Detail |
|---|---|
| Initial state | Active session; memory M exists and has downstream references |
| Steps | 1. User opens memory editor (L7). 2. User deletes M. 3. L5 gates edit. 4. L2 emits edit_confirmed. 5. Provenance cascade runs. 6. L6 re-evaluates observed-style candidates dependent on M. 7. Next turn proceeds. |
| Expected per layer | L7: optimistic delete, rollback on denial. L5: audit record for edit. L2: cascade events. L6: style candidate invalidated or re-derived. L1: next retrieval does not return M. |
| Pass criteria | Audit record present; no stale memory resurfaces next turn; observed-style not silently retained |
| Known risks | Cascade coverage gaps (derived summaries may miss); latency spike during cascade |

### 3.4 Scenario D — "Low-performance degraded mode"

| Field | Detail |
|---|---|
| Initial state | Full tier running; GPU/CPU pressure spikes |
| Steps | 1. core.health emits tier_downgrade. 2. L3 simplifies behaviors (reduced fps, simpler shaders). 3. L4 prefers local models. 4. L1 coalesces events. 5. L7 surfaces banner. |
| Expected per layer | L3: smooth downgrade, no pop. L4: routing shifts. L1: coalescing honored. L7: banner within one event. |
| Pass criteria | No frozen UI; no deceptive operation; user informed of mode |
| Known risks | Anti-uncanny disabled on Lite (visible regression); tier flap if hysteresis insufficient |

### 3.5 Scenario E — "Cost threshold hit during multi-step task"

| Field | Detail |
|---|---|
| Initial state | Multi-step plan in flight; cost cap configured |
| Steps | 1. L4 emits cost_event per request. 2. Aggregate crosses cap. 3. L5 emits cost_threshold_hit. 4. Subsequent routes denied. 5. L7 shows cap-hit modal. 6. User re-arms cap. |
| Expected per layer | L4: cost_event per request; honors deny. L5: threshold event; subsequent denies. L7: cap-hit modal; re-arm flow. L1: task halts gracefully with repair message. |
| Pass criteria | Task halts gracefully; re-arm flow works; no silent continuation past cap |
| Known risks | Re-arm design (open) could create lockout loop; cost-event miscount causes early or late hit |

### 3.6 Scenario F — "Permission denied mid-flow"

| Field | Detail |
|---|---|
| Initial state | 3-step plan in flight; step 1 succeeded |
| Steps | 1. Step 2 requested. 2. L5 denies. 3. L4 cancels remaining plan. 4. L1 surfaces deflection. 5. L7 audit shows denial. |
| Expected per layer | L4: plan cancelled cleanly, no side effect from denied step. L1: Repairing → Speaking with deflection. L5: audit chain intact. L7: audit view reflects. |
| Pass criteria | No side effect from denied step; deflection persona-appropriate; audit complete |
| Known risks | Partial side effect if step 2 had non-reversible prep; deflection phrase off-persona |

### 3.7 Scenario G — "Persona hot-swap mid-conversation"

| Field | Detail |
|---|---|
| Initial state | Active conversation; persona P1 |
| Steps | 1. User selects P2 in L7 picker. 2. L6 compiles P2. 3. swap_begin emitted. 4. L1 waits for safe boundary (end-of-utterance). 5. swap_commit. 6. All layers consume new artifacts. |
| Expected per layer | L6: deterministic compile; signature verified. L1: holds swap to boundary. L3: blends visuals. L5: precedence re-applied with new persona. |
| Pass criteria | No partial persona state mid-utterance; L5 precedence honored; visuals blend smoothly |
| Known risks | Safe-boundary strictness vs perceived responsiveness; compile failure mid-swap; precedence re-application latency |

### 3.8 Scenario H — "Emergency revoke-all during active tool call"

| Field | Detail |
|---|---|
| Initial state | Tool call in flight; pending L7 approvals exist |
| Steps | 1. User invokes emergency revoke. 2. L5 emits EmergencyRevokeAll. 3. L4 cancels all in-flight. 4. L1 enters Repairing with "actions revoked" message. 5. L7 wipes pending approvals. |
| Expected per layer | L5: audit cascade recorded. L4: all streams cancelled within 150 ms. L1: repair state entered. L7: pending approvals cleared immediately. |
| Pass criteria | No tool side effect after event; audit records the cascade; UI reflects immediately |
| Known risks | Late-arriving tool output after cancellation; cancellation not propagating to subprocess tools |

---

## 4. Contract-testing recommendations

What can be verified **before** full cross-layer integration is stood up:

- **Event schema round-trip.** Every event declared in the event_contracts_master must have a serialize → deserialize round-trip test in both Rust (serde) and TypeScript (via ts-rs generated bindings). A property test generates arbitrary valid instances and asserts `deserialize(serialize(x)) == x` in both languages. Regression guards against silent field-rename or enum-shape drift.
- **IPC command surface.** Every Tauri/IPC command must have a paired request/response type check: L7 invocation site typed against the same schema as the L5/L4/L2/L6 handler. CI verifies both sides import the same generated binding, not parallel hand-written copies.
- **Rust trait conformance.** Each layer exposes one or more traits (`PolicyEngine`, `MemoryStore`, `ModelRouter`, `PersonaCompiler`, `PresenceSurface`, `TimingOrchestrator`). Mock adapters must implement the full trait; a conformance test suite exercises every trait method at least once, verifying signatures and basic invariants (e.g., `evaluate` is idempotent for read-only capabilities).
- **DDL stability.** Schema migrations for SQLite/memory-store must have forward tests (old DB + new binary) and backward tests (new DB + old binary rollback). Data preservation is asserted field-by-field.
- **Invariant assertions.** Property-based tests (proptest) cover the 10+ global invariants in event_contracts_master (monotonic turn id, append-only audit, persona precedence, no-tool-without-grant, unique event id, cost_event per request, etc.) and the 12 cross-cut invariants in the L1/L4/L5/L7 integration notes. Each invariant has a dedicated property test name prefixed `inv_`.

Contract tests must run in CI on every commit and gate all PR merges.

---

## 5. Red-team scenarios

| # | Attack | Layer(s) | Defense | Test evidence |
|---|---|---|---|---|
| R-01 | Prompt injection via retrieved memory content | L2 → L4 → model | Retrieved content tagged as data not instruction; model prompt scaffolding isolates; any tool call from injected content still hits L5 | Injection corpus test; assert no tool invocation from injected memory without explicit user grant |
| R-02 | Memory poisoning (fake provenance injected) | L2 | Provenance is write-once with signed ingestion source; novel ingestion requires trusted path | Crafted ingestion test attempts to set provenance directly via IPC and is rejected |
| R-03 | Browser misuse (tool drives harmful navigation) | L4 + L5 | Browser tool gated per-origin; high-risk origins require explicit grant; audit per navigation | Origin-escalation test verifies grant-per-origin and audit completeness |
| R-04 | File/data exfiltration via export | L5 | Export command gated; export bundles are tamper-evident; export audit logged | Exfil attempt via crafted export request without grant = Deny; tampered bundle fails verify |
| R-05 | Permission bypass via crafted event | L5 | L5 is the single chokepoint; no tool path exists without evaluate | Property test enumerates all tool-invocation code paths; each has a preceding evaluate call |
| R-06 | Harmful autonomous action (unattended destructive tool) | L5 | Hardcoded blocks on destructive categories regardless of user override (hardcoded > user precedence) | Enumerate destructive categories; verify each is blocked even with permissive grant |
| R-07 | Logging/audit completeness | L5 | Append-only ledger + hash chain; tamper detection on startup and periodic | Tamper test mutates a record; integrity check fails and raises audit_tamper |
| R-08 | Privilege escalation via crafted persona pack | L6 + L5 | Persona pack must be signed for privileged overlays; L5 precedence means persona cannot override hardcoded | Unsigned privileged overlay = compile reject; persona attempt to elevate hardcoded = Deny |
| R-09 | Privacy leak via remote route without waiver | L4 + L5 | Privacy-posture gate on every route decision; private class blocked from remote without explicit waiver | Private-content routing test on all providers verifies denial + fallback path |
| R-10 | Secret exfiltration via UI state | L7 | Shell-adapter secret-field pattern; secrets never reach React state / devtools / redux | Devtools snapshot test under BYOK paste; grep for key substring yields zero matches |

---

## 6. Performance / timing tests

| Metric | Target | Measurement |
|---|---|---|
| `T_first_state_change` | ≤250 ms P95 | Time from utterance event received to first `turn_state_change` emitted |
| `T_ack_deadline` | ≤800 ms P99 | Time from utterance to audible/visible ack |
| Memory retrieval | ≤150 ms P95 over 10k items | End-to-end L2 query latency at corpus size 10k |
| Reflex classifier | ≤150 ms P99 | Classifier callback latency; late results discarded |
| L5 evaluate | ≤20 ms P99 typical; <200 ms worst-case with DB lookup | Evaluate call latency at nominal + 10k-grant ledger |
| Barge-in TTS cut | ≤150 ms P99 | Time from detected barge-in to silenced output |
| Tier-appropriate fps | Lite 10 / Balanced 30 / Full 60 fps sustained 60 s under load | Renderer fps sampled at 1 Hz across window |
| Approval modal render | ≤100 ms P95 | Time from `approval_pending` event to first paint of modal |

Performance tests run nightly against reference hardware and gate OSS Preview ship.

---

## 7. Replay tests

Given the event log, the following privileged states must be reconstructable **without** consulting live in-memory state. Each replay test starts from an empty state and replays events from a recorded session:

| State | Replay source | Assertion |
|---|---|---|
| Grant ledger | `audit_record` stream (grant issue/revoke/supersede events) | Reconstructed ledger == live ledger at session end (field-by-field) |
| Memory state | `memory_*` events + ingestion log | Reconstructed memory content, provenance, and expiry metadata match live store |
| Turn-state history | `turn_state_change` stream | Reconstructed per-turn state machine trace matches live history; monotonic turn ids preserved |
| Persona effective state | `persona_swap_commit` + `user_override` sequence | Reconstructed effective persona (after precedence resolution) matches live effective persona |

Replay tests double as disaster-recovery verification: if the DB is lost, can the event log alone reconstitute privileged state? If any state cannot be rebuilt from the log, a gap in event coverage exists and must be closed before ship.

---

## 8. Open risks

Areas likely to fail without tighter specification. Each is tracked back to the open-questions log and should have a decision before the relevant priority gate.

| Risk | Impact if unresolved | Affects gate |
|---|---|---|
| Multi-step policy re-eval rule (open) | Tool plans may over-request scope or leak through bundle grants | P0 |
| NeedsUpgrade encoding (open) | L7 upgrade UX may mis-render; user stuck in ambiguous state | P1 |
| Persona-swap safe-boundary strictness | Trade-off between mid-utterance risk and perceived responsiveness | P1 |
| Vector-store vendor choice | Retrieval ranking may vary; test corpus becomes vendor-coupled | P1 |
| Anti-uncanny on Lite tier | Visible regression if disabled outright; needs tier-specific policy | P1 |
| Audit export command missing | Trust-center feature gap; blocks trust-posture messaging | P1 |
| Cost-cap re-arm flow | User lockout risk on mis-design; re-arm UX not yet speced | P0 |

---

## 9. Priority guidance

- **P0 — must pass before any implementation merges.** These protect the core trust posture: single-chokepoint permissioning (L5-T01..T07), contract round-trips, audit chain integrity, secret handling, degraded-mode honesty, and the critical timing budgets (first-ack, barge-in, L5 evaluate). A P0 regression blocks merge to main.
- **P1 — must pass before OSS Preview ship.** These cover integration correctness, tier-aware performance, persona and memory cascades, and the full red-team matrix. A P1 regression blocks the OSS Preview release candidate.
- **P2 — must pass before Pro Phase 1 gate.** These cover advanced optimisations (diff-only persona emit, coalescing under extreme load) and polish-tier perf targets. A P2 regression blocks the Pro ship but not OSS Preview.

All three tiers are re-run nightly; any regression must be triaged before next-day work proceeds.
