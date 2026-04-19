---
status: draft
date: 2026-04-18
layer: L7 (trust UX + onboarding)
kind: implementation_prep / interface_pack
owner: implementation-prep agent
primary_source: plans/L7_trust_ux_onboarding_system_design.md
secondary_sources:
  - plans/L5_policy_engine_system_design.md (§4 events, §5 commands)
  - plans/X3_tauri_architecture.md (§2 IPC, §9 shell-agnostic)
  - plans/L6_persona_compiler_system_design.md (PersonaSummary)
  - plans/L1_L4_L5_L7_integration_notes.md
non_goals:
  - No code. No React/TSX files. No CSS. Contracts and interface signatures only.
  - No changes to other plans.
  - L7 never makes authorization decisions. Every authorization fact flows through L5.
---

# L7 — Interface Pack (implementation prep)

> Purpose of this file: give a frontend implementer (or stub-author for L1/L2/L4/L5/L6) the exact interface surface L7 renders against, without yet writing code. The primary source is `plans/L7_trust_ux_onboarding_system_design.md`; this pack compresses its 1012 lines into an implementer-facing contract pack.

---

## 1. Purpose

L7 is the **user-facing shell** for Aether. It renders onboarding, trust, permission approvals, cost, personas, and degraded-mode state. L7's single guiding contract is asymmetric:

- **L7 never decides. L7 renders.**
- Every capability-affecting action travels L5 → projected event → L7 UI → user choice → command back to L5.
- The same pattern repeats for router tier changes (L4), memory edits (L2), persona swaps (L6), BYOK changes (L4 + L5), and cost-cap mutations (L5).

This interface pack captures:

1. What L7 owns (responsibilities) and what it explicitly does not.
2. The event channels L7 subscribes to (inbound from L1/L2/L3/L4/L5/L6/Core).
3. The IPC commands L7 invokes (outbound to those same layers + its own orchestration helpers).
4. Sync/async boundaries and deadline semantics.
5. Typed contract suggestions — `ShellAdapter` interface + 13 component contracts.
6. Error vocabulary, transport error handling, secret-leak invariants.
7. Dependency expectations on other layers.
8. Monorepo / package implementation notes.

Load this file when starting frontend-scaffolding work on `packages/l7-onboarding`, `packages/l7-trust-center`, `packages/ui-kit`, or `packages/shell-adapter`.

Primary source: file:///C:/Users/dbhav/Projects/aether-planning/plans/L7_trust_ux_onboarding_system_design.md

---

## 2. Primary responsibilities

### 2.1 Owns

- **Onboarding wizard** — 8-screen flow (Welcome → Privacy & data → Assistant identity → Interaction mode → Hardware tier → LLM/BYOK or Guest → Permissions preset → Ready). Wizard is replayable; every step payload persists via `onboarding.save_step`.
- **Trust center** — "What Aether can do / will ask / will never do", recent activity, grant ledger, BYOK wallet, policy posture, model + source disclosure. 7 tabs (4 in OSS Preview).
- **Permission approval UX** — approval prompt modal, pending-approvals drawer (slide-out, `Ctrl+Shift+A`), resource-scope picker, risk pill, capability matrix.
- **Preset picker** — 5-preset ladder (Observer / Assistant / Operator / Power User / Custom) from L5 §6 surfaced during onboarding + Settings.
- **Action-history UI + replay** — timeline scrubber, state transitions, memory hits, tool calls. Read-only reconstitution driven by `trust.replay_action`.
- **Cost-visibility UX** — wallet view (daily/monthly meters), in-line turn cost hint (tier-aware), cap-hit modal, approaching-cap nudge.
- **Persona picker surface** — `persona.list` catalog, swap flow, disabled-during-utterance guardrail (L1-driven).
- **Degraded-mode banners** — one per upstream subsystem (L5 SafeMode / AuditBroken / LedgerCorrupt, L4 unreachable, L2 unreachable, L6 persona compile fail, Media stalled, `core.health` tier downgrade, `emergency_revoke_all` in progress).
- **Tutorial / help layer** — `InfoExplainer` primitive (5-section explainer), modular walkthroughs (first_run, permission_prompt_explainer, trust_center_tour, byok_setup, persona_picker, cost_cap_setup), searchable help index.
- **Consent revocation flow** — uniform across memory, permissions, integrations.
- **First-run checklist** — post-wizard non-modal panel.

### 2.2 Does NOT own

- **Authorization decisions** → L5. L7 only renders `policy_decision` and posts `approval_response`.
- **Turn state** → L1. L7 reflects `turn_state_change`; never produces it.
- **Routing / model choice / tier selection** → L4. L7 renders `route_decision` in audit UI and cost-hint.
- **Memory retrieval + storage** → L2. L7 proposes and queries; never stores.
- **Presence animation / visemes / blend-shapes** → L3. L7 uses only low-frequency `presence_state` for a status dot; never subscribes to viseme streams.
- **Persona compilation** → L6. L7 renders catalog and invokes `persona.compile`.
- **Design tokens** → `packages/ui-kit`. L7 imports; does not define colors, typography, or motion primitives.

---

## 3. Inbound interfaces (events subscribed)

Every projected event carries an envelope `{ source_layer, change_id, seq, payload }`. UI tracks per-channel high-water-mark `seq`; drops trigger `subscribe(..., { replayLastN: N })` recovery.

| Channel | Event | Source | UI surface | Idempotency |
|---|---|---|---|---|
| `policy/pending` | `approval_pending` | L5 | Pending-approvals drawer; approval prompt modal (focus) | `ticket_id` dedupe |
| `policy/response` | `approval_response` (echo projection) | L5 | Drawer row removal; recent-activity append | `ticket_id` one-shot |
| `policy/decision` | `policy_decision` | L5 | Recent activity row; any pending UI keyed to `change_id` | `audit_id` dedupe |
| `policy/grant_issued` | `grant_issued` | L5 | Trust center grants tab; capability row | `grant_id` dedupe |
| `policy/grant_revoked` | `grant_revoked` | L5 | Trust center grants tab; banner if `reason = persona_swap` | `grant_id` revoke-once |
| `policy/audit` | `audit_record` (summary) | L5 | Recent activity tab; history scrubber | `audit_id` dedupe; seq-ordered |
| `policy/emergency` | `emergency_revoke_all` | L5 | Banner (§9 of source); full lockout overlay | single in-flight |
| `policy/cost` | `cost_threshold_hit` | L5 | Wallet meter; cap-hit modal | once per threshold window |
| `router/decision` | `route_decision` | L4 | Replay UI; in-line cost hint; model disclosure panel | `change_id` dedupe |
| `turn/*` | `turn_state_change` | L1 | Persona-swap button gate; chat chrome | seq-ordered |
| `presence/state` | `presence_state` (low-freq only) | L3 | Avatar chrome status dot (not animation) | latest-wins |
| `persona/compiled` | `persona_swap_begin`, `persona_swap_commit` | L6 | Persona picker; swap banner | per-handle |
| `core/health` | tier downgrade, reconnect, resource pressure | Core | Degraded-mode banner; tier badge | latest-wins |

Subscribers **must** treat every payload as read-only and never mutate or re-emit into the bus.

### 3.1 Subscription discipline

- Channels are declared in Rust; UI cannot invent a channel name.
- Bursty channels (viseme, presence high-freq) are coalesced in Rust; L7 does not subscribe to them.
- Webview reload replays channels via `replayLastN: 50` per channel on reconnect (see §7.1 of this pack).

---

## 4. Outbound interfaces (IPC invocations + UI-originated events)

All command invocations go through the shell adapter. Each is either read-class (returns value), write-class (returns `ChangeId` and a projected event follows), or secret-class (requires `captureSecret` + `requestReauth`).

### 4.1 L5 (policy) commands L7 invokes

- `policy.request_approval(request_id) -> ApprovalTicket` — rare from L7; usually L7 receives a `approval_pending` event.
- `policy.respond_approval(ticket_id, user_choice) -> ChangeId` — **primary outbound from approval modal**.
- `policy.set_preset(preset) -> PresetSwitchReceipt` — **re-auth gated**.
- `policy.get_preset() -> CurrentPreset`.
- `policy.list_grants(filter?) -> Grant[]`.
- `policy.revoke(target) -> RevokeReceipt` — **re-auth gated when target = All**.
- `policy.list_capabilities(filter?) -> CapabilityInfo[]`.
- `policy.explain_decision(audit_id) -> Explanation`.
- `policy.emergency_revoke_all(scope) -> EmergencyReceipt` — **re-auth gated**.
- `policy.get_audit_summary(filter) -> AuditSummary[]`.
- `policy.stream_audit(filter, cursor) -> EventStream<AuditRecordEvent>`.
- `policy.export_audit(filter, dest) -> ChangeId` — **proposed, not in L5 §5.2; open item (see §10)**.
- `policy.set_cost_cap(provider, cap) -> ChangeId` — **proposed, not in L5 §5.2; open item (see §10)**.

### 4.2 L2 (memory) commands L7 invokes

- `memory.query(scope, query) -> MemoryHit[]`.
- `memory.edit(memory_id, patch) -> ChangeId` — L5-gated.
- `memory.export(scope) -> Uri` — L5-gated.
- `memory.delete(memory_id) -> ChangeId` — L5-gated.
- `memory.propose_write(draft) -> WriteProposal` — cognition normally invokes; L7 renders the proposal modal.

### 4.3 L4 (router) commands L7 invokes

- `router.route_preview(intent) -> RoutePlan`.
- `router.list_providers() -> ProviderInfo[]`.
- `router.set_byok_credential(provider, handle) -> ChangeId` — L5-gated; `handle` is a `SecretHandle` from `captureSecret`, never a raw key.
- `router.set_tier_override(tier) -> ChangeId` — L5-gated (`RouterOverrideTier` capability).

### 4.4 L6 (persona) commands L7 invokes

- `persona.list() -> PersonaSummary[]`.
- `persona.compile(persona_id) -> CompiledPersonaHandle`.
- `persona.hot_reload(handle) -> ChangeId`.

### 4.5 L1 (turn) commands L7 invokes

- `turn.begin_user_turn(input_kind) -> TurnId`.
- `turn.submit_text(turn_id, text) -> ChangeId`.
- `turn.cancel(turn_id) -> ChangeId`.
- `turn.subscribe_state(turn_id) -> EventStream<TurnEvent>`.

### 4.6 L7-owned orchestration commands (Rust services, L7 namespace)

- `onboarding.save_step(step_id, payload) -> ChangeId`.
- `onboarding.mark_complete() -> ChangeId` — also emits `core.event::onboarding_complete` that L1 listens for.
- `onboarding.replay(step?) -> ChangeId`.
- `onboarding.state() -> OnboardingState` — for webview-reload rehydration.
- `trust.get_action_history(filter) -> Action[]`.
- `trust.replay_action(action_id) -> ReplayHandle` — returns a short-lived handle + `trust/replay/<handle_id>` subscription channel.
- `trust.get_pending_approvals() -> ApprovalTicket[]` — for webview-reload rehydration.
- `trust.first_run_checklist_state() -> ChecklistState`.
- `trust.acknowledge_banner(banner_id) -> ChangeId`.

### 4.7 Shell / platform commands

- `core.probe_hardware() -> HardwareProfile` — used on wizard Screen 1 in background for Screen 5 tier recommendation.
- `core.health.subscribe() -> EventStream<HealthEvent>`.

### 4.8 `approval_response` payload shape (outbound to L5)

Canonical shape L7 posts via `policy.respond_approval`:

```text
ApprovalResponse {
  ticket_id: TicketId,
  user_choice: UserChoice,          // per L5 §4.2
  responded_at: MonoNs,
  // optional scope refinement when user_choice = AllowScope
  scope?: ResourceScope,
  // optional UI hint (NOT an authorization input)
  prefer_draft?: bool,              // "Draft only" button; open item §10
}

UserChoice = Allow | AllowScope(ResourceScope) | AllowTask | AllowSession | Deny
```

UI-button → `user_choice` mapping:

| Button | `user_choice` | Grant outcome |
|---|---|---|
| Allow once | `Allow` | Once grant |
| Allow for this task | `AllowTask` | `TaskScoped(active_task_id)` |
| Allow for session | `AllowSession` | Session grant |
| Allow forever in scope | `AllowScope(scope)` | `Persistent { ttl: preset_default }` |
| **Draft only** | `Deny` + `prefer_draft = true` hint | No grant; cognition falls back to draft-only path |
| Deny | `Deny` | No grant |

**Open item (§10 of this pack):** "Draft only" has no first-class `UserChoice` variant. Proposed extension `UserChoice::DeferToDraft` so audit log captures intent precisely.

### 4.9 UI-originated events (non-IPC)

L7 does not publish events into the layer bus. UI-internal events (component → component) are local React state only.

---

## 5. Synchronous vs asynchronous boundaries

| Operation class | Transport | Sync/async | UI treatment |
|---|---|---|---|
| Read-class command (`policy.get_preset`, `policy.list_grants`, `persona.list`, `router.list_providers`) | `invoke` | async Promise | Spinner on mount; results cached by React Query-equivalent but adapter-neutral |
| Write-class command (`policy.respond_approval`, `policy.set_preset`, `memory.edit`, `router.set_byok_credential`) | `invoke` returns `ChangeId` | async | **Optimistic UI**: modal closes and row marks "responding…" immediately. On matching projected event, UI converges. On `Deny`/rollback, §7.3 applies. |
| Secret-class command (`router.set_byok_credential`, `policy.set_cost_cap` raise) | `captureSecret` then `invoke(…, { handle })` | async, two-step | Secret never enters React; only `SecretHandle` + masked fingerprint render |
| Re-auth-gated command (`policy.set_preset`, `policy.revoke(All)`, `policy.emergency_revoke_all`, `policy.export_audit`, `policy.set_cost_cap`) | `requestReauth` then `invoke(..., { reauth_token })` | async, two-step | Re-auth modal blocks until OS unlock; token scoped to the single next command |
| Event subscription (all channels in §3) | `subscribe` | async, push | Adapter callback; components re-render on store update |
| Approval ticket | `approval_pending` event + `policy.respond_approval` | async with **deadline** | Ticket carries `deadline_hint`; UI renders countdown. L1 stalls at 800 ms per L5 §4.2. Past deadline, row annotates "turn stalled — approve to resume"; never auto-denies. |

### 5.1 Deadline semantics

- Approval tickets have deadlines (`deadline_hint` on the `ApprovalTicket`).
- Countdown visible in the approval modal and pending-approvals drawer.
- Deadline expiry does **not** auto-deny; it stalls the originating turn until user responds or cancels.
- Turn cancellation via `turn.cancel(turn_id)` is the user's escape hatch.

### 5.2 Streaming

- `policy.stream_audit`, `trust.replay_action` (via `trust/replay/<handle_id>`), and `turn.subscribe_state` all return event streams.
- Stream cursors resumed via `{ cursor }` on reconnect.
- Stream termination is explicit (component unmount) via `Unsubscribe` returned from `subscribe`.

---

## 6. Typed contract suggestions

TypeScript-oriented. These are **interface suggestions** — the canonical types are generated from Rust via `ts-rs` / `specta` (`X3 §2`). The contracts here are for reviewer comprehension.

### 6.1 `ShellAdapter`

```text
// packages/shell-adapter — pure TS interface crate.
// Two impls: shell-adapter-tauri (Pro + OSS Tauri), shell-adapter-pywebview (OSS Preview tactical only).
interface ShellAdapter {
  invoke<TReq, TRes>(command: CommandName, req: TReq): Promise<TRes>;

  subscribe<TPayload>(
    channel: ChannelName,
    cb: (evt: Projected<TPayload>) => void,
    opts?: { replayLastN?: number; cursor?: Cursor }
  ): Unsubscribe;

  openNative(uri: NativeUri): Promise<void>;

  persistState<T>(key: StateKey, val: T): Promise<void>;
  loadState<T>(key: StateKey): Promise<T | undefined>;

  captureSecret(
    purpose: SecretPurpose,
    prompt: SecretPromptSpec
  ): Promise<SecretHandle>;

  requestReauth(
    purpose: ReauthPurpose
  ): Promise<ReauthToken>;
}

type Projected<P> = {
  source_layer: "L1"|"L2"|"L3"|"L4"|"L5"|"L6"|"Media"|"Core";
  change_id: u64;
  seq: u64;
  payload: P;
};
```

Two implementations:

| Impl | Target | Command transport | Event transport | Secret handling |
|---|---|---|---|---|
| `shell-adapter-tauri` | Pro + OSS Tauri | `@tauri-apps/api/tauri::invoke` | `@tauri-apps/api/event::listen` | `#[tauri::command]` writes to OS keyring; never returned |
| `shell-adapter-pywebview` | OSS Preview tactical only | `window.pywebview.api.<fn>` JSON bridge | Long-poll / injected event channel, seq-numbered | `secret_*` Python API → `keyring` package |

Both must match shape for every command in §4.

### 6.2 Component contracts (13 components)

Only prop + consumed-event shapes. Styling deferred to UI-phase pass.

| Component | Props contract summary | Consumed events |
|---|---|---|
| **Modal** | `{ title, severity: "info"|"warn"|"critical", onClose, children, focusTrap: bool }` | — |
| **ApprovalPrompt** | `{ ticket: ApprovalTicket, onRespond(user_choice: UserChoice, scope?: ResourceScope, prefer_draft?: bool) }` | `approval_pending` (for this ticket — cancel on external revoke) |
| **RiskPill** | `{ risk_class: "Low"|"Med"|"High"|"Critical", locked?: bool }` | — |
| **CapabilityRow** | `CapabilityRow` data shape (§3.2 of source) + `onConfigure(cap_id: CapabilityId)` | `grant_issued` / `grant_revoked` for `cap_id` |
| **ScopePicker** | `{ capability: CapabilityId, suggested_scopes: ResourceScopeSummary[], onPick(scope: ResourceScope) }` | — |
| **GrantCard** | `{ grant: Grant, onRevoke(grant_id: GrantId) }` | `grant_revoked` |
| **AuditRow** | `AuditRow` data shape (§5.2 of source) + `onExpand`, `onReplay`, `onRevokeRelated` | — |
| **WalletMeter** | `WalletMeter` data shape (§7.1 of source) + `onRaiseCap`, `onSwitchLocal` | `cost_threshold_hit` |
| **BannerStrip** | `{ banners: Banner[], onAcknowledge(id: BannerId) }` | `core.health`, `policy/emergency`, per-layer degraded signals |
| **WizardShell** | `{ steps: WizardStep[], current: StepId, onSave(step_id, payload), onComplete }` | — |
| **PersonaCard** | `{ persona: PersonaSummary, selected: bool, onSelect(persona_id: PersonaId) }` | `persona_swap_commit` (selected badge) |
| **TierBadge** | `{ tier: "Lite"|"Balanced"|"Full", degraded?: bool }` | `core.health tier` |
| **InfoExplainer** | `InfoExplainerSpec { explainer_id: StaticCopyId, learn_more_route?: HelpRoute }` | — |

`InfoExplainer` note: build-time lint must reject any new form control without an `explainer_id` (enforcement mechanism open — §10 item 6).

### 6.3 Key data shapes (referenced above)

```text
CapabilityRow {
  cap_id: CapabilityId;                // dot-path, e.g. "files.edit"
  human_label: string;
  risk_class: "Low"|"Med"|"High"|"Critical";
  current_mode: "auto"|"task"|"ask"|"draft"|"deny"|"block";
  current_scope: ResourceScopeSummary;
  active_grants: GrantSummary[];
  explainer_id: StaticCopyId;
  locked_by: "hardcoded_block"|"preset"|"persona"|null;
  hardcoded_block?: HardcodedBlockId;
}

AuditRow {
  audit_id: AuditId;
  timestamp_wall: WallClockTimestamp;
  timestamp_mono_ns: u64;
  actor_label: string;
  capability_label: string;
  resource_display: string;
  decision: "Allow"|"Ask"|"DraftOnly"|"Deny"|"NeedsUpgrade";
  reason_copy: string | null;
  related_grant_id: GrantId | null;
  redacted: boolean;
}

WalletMeter {
  provider: ProviderId;
  daily_spent_cents: u32;    daily_cap_cents: u32|null;
  monthly_spent_cents: u32;  monthly_cap_cents: u32|null;
  trajectory_will_exceed: boolean;
  next_reset_wall_ms: i64;
  cap_hit: "none"|"daily"|"monthly";
  approaching: "none"|"daily_80pct"|"monthly_80pct";
}

PersonaSummary {
  persona_id: PersonaId;
  display_name: string;
  class: PersonaClass;
  summary: string;
  default_preset_recommendation: PresetId;
}

InfoExplainerSpec {
  explainer_id: StaticCopyId;  // keyed, not inlined — i18n-ready
  learn_more_route?: HelpRoute;
  // renders 5 sections: definition, why, recommended, example, impact
}
```

---

## 7. Error vocabulary

### 7.1 IPC transport errors

- Adapter detects Tauri IPC disconnect or pywebview bridge drop.
- All pending `invoke` promises reject with a typed `IpcTransportLost` error.
- UI enters "Reconnecting…" state via informational BannerStrip entry.
- Auto-reconnect: exponential backoff (100 ms, 200 ms, 400 ms, capped at 3 s).
- On reconnect, every active subscription replays via `subscribe(..., { replayLastN: 50 })`.
- Webview reload calls `trust.get_pending_approvals`, `policy.get_preset`, `policy.list_grants`, `onboarding.state` to rehydrate, then re-subscribes channels.

### 7.2 Optimistic-UI rollback

On `policy.respond_approval`:

1. UI optimistically closes modal and marks the pending row "responding…".
2. If the subsequent `policy_decision` arrives as `Deny` (e.g. late hardcoded-block catch):
   - Modal reopens with a non-dismissable banner: "Your choice couldn't be applied: {plain-language reason}."
   - Final decision shown; user Dismiss → audit row appended.
3. If `policy_decision` arrives as the expected `Allow`, row is removed.

### 7.3 Secret-leak prevention invariants (mandatory)

1. No secret value ever enters React state, refs, context, redux, React Query cache, or devtools.
2. `captureSecret` uses a native-bridged input overlay (Tauri window-owned input; pywebview webview-owned intercept).
3. UI receives only a `SecretHandle` — opaque, non-guessable, scoped to purpose.
4. Handles expire at session end or on explicit revoke (an L5 grant-revoke).
5. React error boundaries strip fields named `secret`, `api_key`, `token` from error payloads before logging.
6. Audit records redact secrets forever — only masked fingerprints shown; no unmask path.

### 7.4 Localized error codes from L5

Plain-language translation table (canonical list in source §14.1):

| L5 `DenyReason` / `PolicyIpcError` | User-facing copy surface |
|---|---|
| `HardcodedBlock(id)` | Approval modal; recent activity |
| `FeatureDisabled` | NeedsUpgrade modal |
| `ActionOutOfScope` | NeedsUpgrade modal |
| `ResourceOutOfScope` | Approval modal (with "Add scope" button) |
| `ModeDeny` | Recent activity |
| `GrantExpired` | Approval modal |
| `GrantRevoked` | Recent activity |
| `ProvenanceTaint(kind)` | Approval modal |
| `PrivacyPostureViolation` | Approval modal; privacy tab |
| `CostCapHit(provider)` | Cap-hit modal |
| `TierDowngradeStripped` | Banner |
| `LedgerCorrupt` | Banner |
| `AuditWriteFailed` | Banner |
| `PolicyIpcError::RequiresReauth` | Re-auth modal |
| `PolicyIpcError::Conflict` | Toast ("This approval was already answered.") |

### 7.5 Degraded-mode lockout rules

When a degradation banner is up, the following surfaces **must remain available**:

- Emergency revoke (`policy.emergency_revoke_all`).
- Trust center (read-only).
- Pending-approvals drawer (approving restores flow).
- Help / tutorial layer.
- Close-window affordance.

---

## 8. Dependency expectations

L7 depends on every other layer but authorizes nothing itself. The table below fixes the dependency direction and the contract L7 expects.

| Layer | What L7 needs | What L7 does NOT do |
|---|---|---|
| **L1 (turn)** | `turn_state_change` events; `turn.begin_user_turn`, `turn.submit_text`, `turn.cancel`, `turn.subscribe_state` commands | Never produces turn state |
| **L2 (memory)** | `memory.query`, `memory.edit`, `memory.export`, `memory.delete`, `memory.propose_write`; renders write proposals as approval modals | Never stores memory; never decides what's memorable |
| **L3 (presence)** | Low-freq `presence_state` for status dot | Never consumes viseme/blend-shape streams; never drives avatar animation |
| **L4 (router)** | `router.list_providers`, `router.route_preview`, `router.set_byok_credential` (via `SecretHandle`), `router.set_tier_override`; `route_decision` events | Never chooses a model or tier |
| **L5 (policy)** | Every authorization event (`approval_pending`, `policy_decision`, `grant_issued`, `grant_revoked`, `audit_record`, `emergency_revoke_all`, `cost_threshold_hit`); every command in §4.1 | **Never makes authorization decisions locally.** Every Allow/Deny is L5's |
| **L6 (persona)** | `persona.list`, `persona.compile`, `persona.hot_reload`; `persona_swap_begin` / `persona_swap_commit` events; `PersonaSummary` shape | Never compiles personas; never owns PersonaSummary shape |
| **Core / platform** | `core.probe_hardware`, `core.health.subscribe` | — |

Hard rule: if an L7 surface needs to know whether an action is allowed, it **asks L5 via event subscription or explicit command**. It does not pattern-match on grants locally to decide.

---

## 9. Implementation notes

### 9.1 Monorepo layout

Per X3 §9.3 and source §2:

- `packages/shell-adapter/` — pure TS interface crate. No Tauri or pywebview imports.
- `packages/shell-adapter-tauri/` — Tauri impl. Only package that imports `@tauri-apps/api`.
- `packages/shell-adapter-pywebview/` — pywebview JSON-bridge impl (OSS Preview tactical only).
- `packages/ui-kit/` — shared design tokens, primitive components (Modal, RiskPill, TierBadge, InfoExplainer). No business logic.
- `packages/l7-onboarding/` — 8-screen wizard, first-run checklist, onboarding orchestration. Imports from `ui-kit` + `shell-adapter` only.
- `packages/l7-trust-center/` — 7-tab trust center, approval modal, pending-approvals drawer, wallet, audit UI, replay UI, banners. Imports from `ui-kit` + `shell-adapter` only.

### 9.2 React import hygiene

- **Never** import `@tauri-apps/api` from any component, hook, or store. ESLint rule + CI lint.
- **Never** import `window.pywebview` directly from any component. Same rule.
- Both are only allowed inside `shell-adapter-tauri` / `shell-adapter-pywebview`.
- Violation fails the build.

### 9.3 Build-flag divergence (OSS Preview vs Pro)

Single codebase, build-time feature flag `edition`:

- Components accept an `edition` prop or call `useEdition()` to conditionally render advanced affordances.
- Component tree is identical across editions — the shell-adapter contract must not vary by edition.
- OSS Preview defaults: 4 trust-center tabs, Observer+Assistant preset floor, Guest mode visible, no BYOK wallet.
- Pro: full 7 tabs, full 5-preset ladder, BYOK wallet, audit export, full walkthrough set.

### 9.4 Deliverable order (first-build sequence)

Per source §19:

1. `packages/shell-adapter` interface (TS) + `shell-adapter-tauri` implementation; pywebview adapter stubbed.
2. 13-component inventory wired to contracts only (no styling).
3. 8-screen wizard skeleton — navigable empty shell with `onboarding.save_step` wiring.
4. Approval-prompt modal + pending-approvals drawer, wired to `approval_pending` / `approval_response`.
5. Trust center shell — 4 tabs minimum (OSS Preview floor); 3 behind edition flag.
6. Degraded-mode banner system — BannerStrip + `core.health` + L5 degraded-mode subscription.

All six can be built against Rust stubs returning fixture data; L7 does not block on L1–L6 completion.

### 9.5 Accessibility must-haves at scaffold time

- Keyboard-first: approval Allow = Enter, Deny = Esc, drawer = `Ctrl+Shift+A`, trust = `Ctrl+Shift+T`, emergency revoke = `Ctrl+Shift+R` (with confirm; collision open — §10 item 5).
- `aria-live="polite"` on pending-approvals list.
- `role="alert"` on critical/warning banners; `role="status"` on informational.
- `prefers-reduced-motion` honored; no tween > 150 ms under reduced-motion.
- Visible focus ring everywhere; no focus-ring suppression.

### 9.6 Testing hooks at scaffold time

- `data-testid` on every interactive element for Playwright visual-regression + keyboard-traversal tests.
- Comprehension rubric (informal, per Don): can a non-technical user, after seeing an audit row, say aloud what happened, who did it, and to what?

---

## 10. Open items (flagged, not resolved)

1. **`UserChoice::DeferToDraft` variant** — "Draft only" action in the approval modal currently round-trips as `Deny` + `prefer_draft` side-channel hint because L5 §4.2 `UserChoice` enum lacks a draft variant. Propose adding `DeferToDraft` so the audit log captures user intent as a first-class decision instead of reconstructing it from a hint. Source §3.4, §20 item 1, §22 item 1.
2. **`policy.export_audit` command missing from L5 §5.2** — trust center's "Export my audit log" requires a capability-gated, re-auth-gated command. L5 §5.2 defines `stream_audit` but no file-export. Propose adding to L5 command catalog; payload shape proposed here as `(filter, dest) -> ChangeId`. Source §5.5, §11, §20 item 2, §22 item 2.
3. **`policy.set_cost_cap` command missing from L5 §5.2** — cap-hit modal's "Raise cap" action needs a command. L5 §9 defines counters + thresholds but no UI-facing cap-mutate command. Propose adding with re-auth gate; payload `(provider, cap) -> ChangeId`. Source §7.3, §11, §20 item 3, §22 item 3.
4. **Guest-mode infrastructure deferral** — Cloudflare Worker + Groq free tier (per `03_content_lock §2`) vs. alternative provider vs. defer post-OSS-Preview. L7 UI for Guest is specified (forced Observer preset, no durable memory, N/10 hourly turns banner); the hosting decision is deferred. Source §4.5, §20 item 5.
5. **Keybinding collision `Ctrl+Shift+R`** — emergency revoke conflicts with browser-refresh inside the webview on some systems; needs a chorded alternate. Source §20 item 9.
6. **`InfoExplainer` build-time lint mechanism** — which lint rule, in which CI stage, enforces that every form control has an `explainer_id`. Not yet specified. Source §20 item 12.
7. **pywebview adapter event-replay + seq-ordering parity** — X3 §9.3 assumes yes; not yet verified at adapter prototype. May cap OSS Preview features if lossy. Source §20 item 4.
8. **Single main window vs dedicated onboarding/trust-center windows** — X3 §10 raises; L7 position is single window with routed panes for v1. Confirm with Don. Source §20 item 6 + item 7.

---

## 11. Confidence

| Section | Confidence | Rationale |
|---|---|---|
| §1 Purpose | High | Mirrors source §1 directly. |
| §2 Responsibilities | High | Owns/Does-NOT-own lifted from source §1.1 + §1.2. |
| §3 Inbound events | High | Full channel table from source §10. |
| §4 Outbound commands | High | Full IPC surface from source §11; proposed commands flagged. |
| §5 Sync/async boundaries | High | Optimistic rollback + deadline semantics locked from source §15.3 + §3.6. |
| §6 Typed contracts | High | ShellAdapter + 13 components direct from source §2.2 + §13.2. |
| §7 Error vocabulary | High | Plain-language table direct from source §14.1; secret-leak rules from §2.4 + §15.4. |
| §8 Dependencies | High | Dependency table locks the "L7 never decides" invariant. |
| §9 Implementation notes | High | Monorepo + import hygiene + deliverable order pinned from source §2 + §19. |
| §10 Open items | High | Each item traces to specific source sections. |

---

Primary source: file:///C:/Users/dbhav/Projects/aether-planning/plans/L7_trust_ux_onboarding_system_design.md
Secondary sources:
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/X3_tauri_architecture.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L6_persona_compiler_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_L4_L5_L7_integration_notes.md
