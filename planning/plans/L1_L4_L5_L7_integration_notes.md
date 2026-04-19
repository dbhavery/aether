# L1 + L4 + L5 + L7 Integration Notes

> Cross-layer composition reference. Reconciles L1 (interaction timing), L4 (model router), L5 (policy engine), L7 (trust/UX/onboarding).
> Source docs:
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L4_model_router_system_design.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L7_trust_ux_onboarding_system_design.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/00_ORCHESTRATION_MAP.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/X3_tauri_architecture.md

---

## 1. Purpose

This note captures how L1, L4, L5, L7 compose into the end-to-end trust + control + timing path. It is reference material for implementers stitching the four layers together. Each source doc is authoritative for its own internals; this note is authoritative for the shape of their interactions, the propagation of `change_id`/`ticket_id`, the composed budgets, and the invariants that the event bus must enforce across the seam.

---

## 2. End-to-end sequence: "open ~/Downloads/report.pdf and summarize it"

A tool-plan turn that exercises every seam (reflex classify → ActionRequest → Ask → user grant → route → optional re-gate → audit).

Notation: `[LAYER] step -> target` ; `evt:` event ; `cmd:` Tauri command.

1. `[MIC]` audio frame arrives → `[L1]` VAD fires → `[L1]` state: `Idle → Listening`.
   - evt: `turn_state_change { turn_id, state=Listening, ts }`
2. `[L1]` ASR streams partial → final transcript at endpoint.
3. `[L1]` embedded reflex classifier runs against transcript + persona defaults.
   - Classification: `tool-plan` (intent: `files.read + summarize`, target: `~/Downloads/report.pdf`).
   - `change_id := new_uuid()` assigned for the turn's causal chain.
4. `[L1]` builds `ActionRequest { change_id, turn_id, capability=files.read, resource=~/Downloads/report.pdf, persona_id, provenance=[reflex_classifier], requested_scope=session }` → sends to `[L5]` via typed bus.
5. `[L5]` runs 5-layer evaluator (preset → persona overrides → resource sensitivity → grant ledger lookup → cost/posture gates).
   - No matching grant. Preset = Copilot (default). Decision: `Ask { ticket_id, reason=NewCapabilityRequiresApproval }`.
   - evt: `approval_pending { ticket_id, change_id, capability, resource, persona_id, plain_language, choices=[Once, AllowSession, AllowAlways, Deny] }`
   - Audit row appended: `{ change_id, ticket_id, phase=requested, decision=ask }`.
6. `[L1]` subscribed to `approval_pending { change_id == current }` → state: `AwaitingPolicy`.
   - `[L1]` schedules secondary-ack at `T_approval_secondary_ack` (L1 §4): "Give me a moment." (first-ack ≤250 ms already emitted unconditionally if budget demanded it).
7. `[L7]` subscribed to `approval_pending` → renders approval modal with plain-language description, resource path, persona scope, 4 choice buttons, and the "Details / Audit rationale" expander.
8. User taps "Allow for session".
   - `[L7]` cmd: `policy.respond_approval { ticket_id, user_choice=AllowSession, scope={persona_id, session_id} }`.
9. `[L5]` resolves ticket → `Decision=Allow` → writes Grant `{ grant_id, capability, resource_pattern, scope=session, persona_id, ttl, change_id }`.
   - evt: `policy_decision { change_id, ticket_id, decision=Allow, grant_id }`
   - evt: `grant_issued { grant_id, capability, resource_pattern, scope, ttl }`
   - Audit row: `{ change_id, ticket_id, phase=resolved, decision=allow, user_choice=AllowSession, grant_id }`.
10. `[L1]` receives `policy_decision=Allow` → state: `AwaitingPolicy → RouteSelected`.
    - `[L1]` computes `latency_budget_remaining = T_turn_budget − elapsed − observed_L5_ms`.
    - `[L1]` → `[L4]` `RouteHint { change_id, turn_id, intent=tool-plan, steps=[read_file, summarize], persona_tier_pref, latency_budget_remaining, privacy_class }`.
11. `[L4]` composes inputs: `RouteHint` + memory hit from `[L2]` (if any) + persona tier preference → `RouteDecision { chosen_tier=main-local, tool_plan=[read_file(path), summarize(text)] }`.
    - evt: `route_decision { change_id, chosen_tier, tool_plan, rationale }`
12. `[L4]` executes step 1 (`files.read`):
    - Canonical rule (see §5 I1, §10 Q1): the initial `grant_issued` covers `files.read` for the declared `resource_pattern` and `scope=session`. `[L4]` does NOT round-trip `[L5]` again for reads that fall under that grant. `[L4]` MUST call `policy.evaluate` for any step whose capability or resource is not covered by an active grant.
    - `[L4]` performs read → returns `bytes / text`.
13. `[L4]` executes step 2 (`summarize`):
    - Case A (local main-tier satisfies): no new `ActionRequest`. Emit `cost_event { tokens_local }`.
    - Case B (escalation to remote BYOK): `[L4]` emits `ActionRequest { change_id, capability=router.remote_escalation, provider, privacy_class, persona_id, provenance=[summarize_step] }` → `[L5]` runs privacy-posture gate (L5 §10) → `Allow | Deny | Ask`. If `Allow`, `[L4]` dispatches to remote provider; if `Deny`, falls back to local tier or emits `degraded_summary`.
14. `[L4]` emits cumulative `cost_event { change_id, tokens, usd, provider }`.
15. `[L5]` updates rolling cost counter. If threshold crossed:
    - evt: `cost_threshold_hit { scope, threshold, current }`
    - `[L4]` MUST honor the threshold for remaining steps this turn and subsequent turns until re-armed (see I7).
    - `[L7]` wallet widget re-renders.
16. `[L4]` → `[L1]` result event with final text + `change_id`.
17. `[L1]` state: `RouteSelected → Streaming → Speaking` (TTS if voice turn) and `turn_state_change` events fire for each transition.
18. `[L7]` trust-center activity log appends a row keyed on `change_id`: `{ capability=files.read, resource, decision=Allow, grant_id, provider=local, tokens, usd, ts }`.
19. `[L1]` emits `turn_end { turn_id, change_id }`. Grant persists until TTL. `[L5]` audit log sealed for this `change_id`.

---

## 3. Shorter sequence: direct typed question, no tool needed

1. `[L7]` text input → `[L1]` direct transcript ingress (skips ASR).
2. `[L1]` reflex classifier → `direct-local` (no capability requested).
3. No `ActionRequest` emitted. Reflex direct-local is hardcoded-allowed doctrine — never touches `[L5]`.
4. `[L1]` → `[L4]` `RouteHint { intent=direct, persona_tier_pref, latency_budget }`.
5. `[L4]` → `RouteDecision { chosen_tier=main-local, tool_plan=[] }`. Streams answer.
6. `[L1]` transitions `Listening → Streaming → Speaking → Idle`.
7. No grant issued. No audit row beyond telemetry `turn_state_change`. `[L7]` activity view shows the turn but with no policy-decision column populated.

---

## 4. Shorter sequence: user wants email, preset is Observer (no email capability)

1. `[L1]` reflex classifier → `tool-plan (email.send)`.
2. `[L1]` → `[L5]` `ActionRequest { capability=email.send, ... }`.
3. `[L5]` evaluator: preset=Observer does not grant `email.send`. Decision: `Deny { reason=NotInPreset, upgrade_path=preset:Operator }` OR `NeedsUpgrade { required_preset=Operator, capability=email.send }` (pending lock — see §10 Q2).
4. evt: `policy_decision { change_id, decision=Deny|NeedsUpgrade, reason }`. Audit row recorded.
5. `[L1]` receives → state: `AwaitingPolicy → Repairing(safety_deflection | upgrade_path)` → selects ack-pool phrase: "That's outside what I'm set up to do right now."
6. `[L7]` subscribed to `policy_decision where decision in {Deny, NeedsUpgrade}` → renders the upgrade-UX card: "This action needs Operator preset. Upgrade preset?" with explanation + diff of capabilities gained.
7. User path A (upgrade): `[L7]` cmd: `policy.set_preset { target=Operator }` → this command is itself capability-gated (re-auth required, L5 §6). On success, `[L5]` re-evaluates the pending `change_id` or user re-issues the request.
8. User path B (cancel): turn ends. Audit retains the denial row.

---

## 5. Key invariants

| # | Invariant |
|---|---|
| I1 | No tool runs without an `[L5]` `policy_decision=Allow` (or covering Grant) recorded in the audit log. |
| I2 | `[L1]` never commits side-effects on its own. The reflex router is a classifier only. All side-effects are executed by `[L4]`-mediated tool runners after the `[L5]` gate. |
| I3 | `[L7]` is a view + input surface. It NEVER makes authorization decisions. It forwards `approval_response` as an input to `[L5]`; the `Decision` is always `[L5]`'s. |
| I4 | Every `ActionRequest` and every `PolicyDecision` carries a `change_id` that appears in the audit log and in downstream `route_decision`, `cost_event`, and `turn_state_change` events. `change_id` is the correlation key across all four layers. |
| I5 | When `[L5]` is unreachable (DegradedNoPolicy), `[L1]` AND `[L4]` refuse all tool / memory-write / remote paths. No silent-allow. Reflex direct-local is the only surviving path. |
| I6 | Private-tagged context from `[L2]` never crosses into a remote-route call without an explicit per-turn waiver grant recorded in `[L5]`. `[L4]` must inspect privacy_class on every remote dispatch. |
| I7 | BYOK cost counters are owned by `[L5]`. `[L4]` emits `cost_event`; `[L5]` enforces threshold. `[L4]` MUST honor `cost_threshold_hit` for subsequent requests in the same turn AND future turns until `[L5]` re-arms the counter (user action via `[L7]`). |
| I8 | `[L1]` timing budgets are independent of `[L5]` decision time. An `Ask` ticket extends the deliberative window; `[L1]` emits a secondary ack so the UI never appears frozen. First-ack ≤250 ms is non-negotiable. |
| I9 | Persona hot-swap is safe-boundary only (L1 §7). It never occurs mid-utterance. `[L5]`'s per-persona defaults are re-applied at `persona_swap_commit`. Active grants scoped to the outgoing persona become dormant, not transferred. |
| I10 | Emergency-revoke-all from `[L5]` immediately invalidates active in-flight tool calls. `[L4]` MUST cancel in-flight executions; `[L1]` MUST enter `Repairing` with an "actions revoked" ack. All open `change_id` chains get an audit `revoked` row. |
| I11 | `[L7]` audit view respects privacy-class redaction by default. Unmasking requires re-auth via `policy.unmask_audit { ticket }` which is itself a capability-gated command. |
| I12 | Every update affecting trust/permissions/disclosures (preset change, grant issuance, posture change, BYOK cap change) carries a flag `[L7]` surfaces pre-apply (per X3 §6 pre-apply disclosure convention). No silent mutation of the trust surface. |

---

## 6. State/event causality table

| Scenario | User action | L1 state path | L5 decision | L4 route | L7 UI state | Audit record |
|---|---|---|---|---|---|---|
| Happy direct | types question | Idle→Listening→Streaming→Speaking→Idle | (none) | main-local, no tool | normal chat, activity row w/o policy col | telemetry only |
| Happy tool-plan | voices "open pdf" | Listening→AwaitingPolicy→RouteSelected→Streaming→Speaking | Ask→Allow (AllowSession) | main-local, tool_plan=[read,summarize] | approval modal→dismiss→activity row | requested + resolved(allow) + grant_issued |
| Ask + deny | voices "open pdf" | Listening→AwaitingPolicy→Repairing→Idle | Ask→Deny(user) | (no tool call) | approval modal→dismiss→denial row | requested + resolved(deny) |
| Preset block | voices "send email" (Observer) | Listening→AwaitingPolicy→Repairing→Idle | Deny or NeedsUpgrade | (no tool call) | upgrade-UX card | denial row w/ reason=NotInPreset |
| BYOK cap hit mid-turn | summarize escalates remote | Listening→AwaitingPolicy→RouteSelected→Streaming→Repairing | Allow (gate) then cost_threshold_hit | remote BYOK → fallback local | wallet widget turns amber; banner "cap reached" | cost_event + cost_threshold_hit |
| Revoke during turn | user hits "Revoke all" | AwaitingPolicy or Streaming → Repairing → Idle | emergency_revoke_all | in-flight tool cancelled | revoke banner + audit row | revoked row per open change_id |
| Barge-in | user speaks over TTS | Speaking→Listening (barge-in) | none (affects current turn only) | current tool plan cancelled if mid-exec (checks grant still valid for next step) | transcript updates; partial assistant turn preserved | turn_state_change(barge_in) |

---

## 7. Contract crosswalk — event and command ownership

### 7.1 Events

| Event | Emitter | Subscribers | Projected to UI |
|---|---|---|---|
| `turn_state_change` | L1 | L3, L7 (optional), telemetry | Yes (L3 presence; L7 activity feed) |
| `turn_end` | L1 | L5 (audit seal), L7 | Partial |
| `action_request` (bus internal) | L1, L4 | L5 | No |
| `approval_pending` | L5 | L1, L7 | Yes (approval modal) |
| `policy_decision` | L5 | L1, L4, L7 | Yes (audit row, UX branch) |
| `grant_issued` | L5 | L4 (caching), L7 (trust center) | Yes |
| `grant_revoked` | L5 | L1, L4, L7 | Yes |
| `emergency_revoke_all` | L5 | L1, L4, L7 | Yes (banner) |
| `cost_event` | L4 | L5 | No (aggregated by L5) |
| `cost_threshold_hit` | L5 | L4, L7 | Yes (wallet widget, banner) |
| `route_decision` | L4 | L1, L7 (activity) | Partial (activity only) |
| `provider_fallback` | L4 | L7 | Yes (banner) |
| `privacy_posture_change` | L5 | L4, L7 | Yes (banner per I12) |
| `persona_swap_commit` | L6 (consumed here) | L1, L5, L7 | Yes |
| `degraded_mode_enter/exit` | L1/L4/L5 | all | Yes (banner) |

### 7.2 Tauri commands

| Command | Owning layer | Invoker layer(s) | Capability-gated |
|---|---|---|---|
| `policy.evaluate` | L5 | L1, L4 | No (internal eval) |
| `policy.respond_approval` | L5 | L7 | Yes (tied to ticket + session) |
| `policy.set_preset` | L5 | L7 | Yes (re-auth) |
| `policy.revoke_grant` | L5 | L7 | Yes |
| `policy.emergency_revoke_all` | L5 | L7 | Yes (re-auth) |
| `policy.unmask_audit` | L5 | L7 | Yes (re-auth) |
| `policy.export_audit` | L5 (pending — see §10 Q5) | L7 | Yes |
| `policy.rearm_cost_cap` | L5 | L7 | Yes |
| `router.submit` | L4 | L1 | No (L4 internally gates via L5) |
| `router.cancel` | L4 | L1, L7 | No |
| `router.list_providers` | L4 | L7 | No |
| `router.set_byok_cap` | L4 (stores) / L5 (enforces) | L7 | Yes |
| `turn.begin` / `turn.end` | L1 | L7 (text entry path) | No |
| `turn.barge_in` | L1 | L7 | No |
| `ui.show_toast` / `ui.open_trust_center` | L7 | L1, L4, L5 (via event→UI) | No |

---

## 8. Timing — composed budgets

- `T_first_ack ≤ 250 ms` (L1) is hard and independent of `[L5]` decision time. `[L1]` emits first-ack without waiting on `[L5]`.
- `T_policy_evaluate` typical `< 20 ms` for non-Ask decisions (L5 §3). Ask decisions stall on user; `[L1]` schedules `T_approval_secondary_ack` (L1 §4) to keep UI alive.
- `[L4]` tier-latency budget (L4 §3) does NOT include `[L5]` evaluation overhead. When `[L1]` forwards `RouteHint`, it subtracts observed `[L5]` time from the turn budget:
  - `route_hint.latency_budget_remaining = T_turn_budget − T_elapsed − T_L5_observed`
- If `latency_budget_remaining < T_min_tier_budget`, `[L4]` must either down-tier or return `degraded_latency` rather than blow the budget.
- `cost_threshold_hit` is fire-and-forget from `[L5]`; `[L4]` applies it on the NEXT dispatch. In-flight step completes without cancel (unless revoke-all).

---

## 9. Degraded-mode composition

| Failed layer | L1 behavior | L4 behavior | L5 behavior | L7 banner/UX |
|---|---|---|---|---|
| L5 down (DegradedNoPolicy) | reflex direct-local only; all AwaitingPolicy transitions fail closed → Repairing | refuses all tool + remote routes; main-local only for direct | N/A | "No automation mode — policy engine unavailable" |
| L2 down | empty-memory path; no recency hits | reduces heavy-tier preference (no memory to justify); unchanged otherwise | unaffected | "No memory mode" |
| L4 down | direct-to-main-local fallback (L1 has a minimal inline adapter) | N/A | unaffected; still gates any direct attempts | "Local-only mode — router unavailable" |
| L7 down | queues `approval_pending` in L5; blocks on AwaitingPolicy with timeout → Repairing | refuses ask-requiring routes until L7 reconnects | queues pending tickets with TTL; emergency-revoke-all accessible via IPC | N/A (UI gone); system tray or relaunched window shows recovery |
| Provider down (BYOK) | unchanged | fallback chain per L4 §10 | unchanged | provider_fallback banner |

Composed rule: degraded modes stack. If both L5 and L4 are down, only `[L1]` direct-local survives; if L1 is down, the app is non-interactive (UI can still show trust center in read-only via L5 direct IPC).

---

## 10. Open integration questions

Consolidated from L1 §16, L4 §19, L5 §14, L7 §20/§22. Not silently resolved.

1. **Q1 — Per-step re-evaluation vs trust initial grant.** L4 §6 and L5 §7 differ on phrasing. *Canonical proposal in this note:* grant covers its declared `capability + resource_pattern + scope`; L4 skips re-eval within the grant; L4 MUST re-eval for any step whose capability OR resource pattern is not covered (notably remote escalation). **Don must ratify.**
2. **Q2 — NeedsUpgrade representation.** L1 §16 treats it as a top-level `Decision::NeedsUpgrade`; L5 §14 flags it as possibly `Decision::Deny { reason: NeedsUpgrade }`. UX differs (upgrade card vs deflection). Lock shape before L7 implements the upgrade card.
3. **Q3 — Draft-only approval choice.** L7 proposes a "Draft only" approval option (produce artifact but do not send/commit). L5 currently has no encoding for this. Requires new `Decision::AllowDraft { side_effects_inhibited }` + L4 awareness.
4. **Q4 — BYOK cost-cap re-arm flow.** Who re-arms (user via L7 button? auto on period rollover? per-provider?); where is the counter persisted across restart; does re-arm require re-auth. L4 §9, L5 §9, L7 §7 all touch it.
5. **Q5 — `policy.export_audit` command.** L7 trust center requires export (CSV/JSON, redaction-aware). L5 §5 does not yet list this command. Must be added to L5 IPC surface.
6. **Q6 — Speculative payload materialization.** L4 may prefetch/warm remote providers for latency. If payload contains private-class content and user denies, the buffer risk is real. Needs policy: either no spec materialization of private content, or mandatory scrub-on-deny.
7. **Q7 — Privacy-posture waiver scope.** Per-provider, global, or per-task waivers? Current L5 §10 is ambiguous. L7 UX must match whatever is chosen.
8. **Q8 — Persona-swap strictness.** L1 §7 allows end-of-utterance swap; some L5 notes imply Idle-only. Affects mid-plan swaps and grant carryover. Lock before L6 integration.
9. **Q9 — Barge-in + in-flight tool call.** If user barges while L4 is executing step N of a plan, does the plan cancel immediately, finish the current step, or mark the change_id as "abandoned"? Audit semantics need a rule.
10. **Q10 — Approval TTL when L7 is down.** If L7 cannot render, when does a queued `approval_pending` expire? Must not accumulate unbounded. Proposal: 60 s default, configurable.

---

## 11. Implementation readiness summary

### 11.1 Unblocked work

- **L5**: policy evaluator state machine (5-layer), grant ledger schema, audit log DDL (append-only, hash-chained), BYOK cost counter + threshold logic, privacy-posture gate, IPC commands listed in §7.2 (except `policy.export_audit` pending Q5).
- **L1**: turn-state machine (Idle / Listening / AwaitingPolicy / RouteSelected / Streaming / Speaking / Repairing), reflex classifier with typed adapters, first-ack + secondary-ack scheduler, barge-in handler.
- **L4**: tier abstraction, tool-plan orchestrator, provider plugin trait, fallback chain, cost_event emitter, router.submit/cancel IPC.
- **L7**: shell-adapter architecture (X3 §2–3), approval prompt modal, trust center skeleton (grants list, audit viewer, preset switcher, wallet widget), degraded-mode banner slots.
- **Shared**: typed event-bus contracts (pull into `packages/event-bus` per monorepo §2). Every event in §7.1 gets a Rust struct + TS type mirror; `change_id` is a newtype.

### 11.2 Blocked on Don-locked decisions

- Q1 canonical per-step rule (blocks L4 policy-chokepoint finalization).
- Q2 `NeedsUpgrade` shape (blocks L7 upgrade card + L1 Repairing branch).
- Q3 `AllowDraft` variant (blocks L7 approval choices list + L4 side-effect inhibition).
- Q4 cost-cap re-arm UX (blocks L7 wallet widget interactivity).
- Q7 privacy-posture waiver scope (blocks L5 §10 finalization).

---

## Reporting summary (for caller)

- **File**: file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_L4_L5_L7_integration_notes.md
- **Invariants established**: 12
- **Open integration questions consolidated**: 10
- **Unblocked implementation tasks**: L5 evaluator + ledger + audit; L1 state machine + reflex; L4 tier abstraction + orchestrator; L7 shell adapter + approval modal + trust center skeleton; shared typed event-bus package.
- **Top Don-locked decisions required**:
  1. Q1 — per-step re-evaluation vs trust initial grant (canonical rule)
  2. Q2 — `NeedsUpgrade` as top-level Decision vs Deny-reason
  3. Q3 — `AllowDraft` approval variant (add or drop)
  4. Q4 — BYOK cost-cap re-arm UX + persistence
  5. Q7 — privacy-posture waiver scope (per-provider / global / per-task)
