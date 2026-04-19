---
status: draft
date: 2026-04-18
layer: L7 (trust UX + onboarding)
owner: Wave-2c agent
depends_on:
  - 01_product_doctrine.md (§"Must-own layers" #7, §"Desktop framework doctrine", §"Applied to evaluation")
  - MASTER_OUTLINE_TREE.md (§2 user modes, §3 UX principles, §9 permissions, §10 trust/security/red-team, §11 updates)
  - plans/00_ORCHESTRATION_MAP.md (§1, §6, §8 checkpoints)
  - plans/L7_trust_ux_onboarding.md (upstream plan — boundaries, acceptance criteria)
  - plans/L5_policy_engine_system_design.md (§4 events, §5 commands, §6 presets, §7 grant ledger, §8 audit log, §9 BYOK cap, §10 privacy gate, §11 degraded modes)
  - plans/L1_interaction_timing_system_design.md (turn-state events)
  - plans/X3_tauri_architecture.md (§2 IPC, §7 fs scopes, §9 OSS Preview / Pro divergence, §10 extensibility)
  - 05_ux_principles.md, 06_onboarding_spec.md, 07_tutorial_help_system.md, 12_permissions_autonomy.md, 13_trust_security_redteam.md
  - plans/03_content_lock_v1_port.md (8-screen wizard, Guest mode, cost visibility, distribution)
  - plans/L6_persona_compiler.md (persona picker + persona-scoped defaults)
non_goals:
  - No code, no React/TSX files. Contracts and sketches only.
  - No authorization logic — L5 owns it. L7 consumes events and renders UI.
  - No routing, turn state, memory-retrieval, or persona-compilation logic. Consumes, does not produce.
  - No design-system token authoring (consumed from `packages/ui-kit`).
---

# L7 — Trust UX & Onboarding (system design)

> Scope: the user-facing shell. Onboarding wizard, trust center, permission approval UX, cost visibility, persona picker surface, degraded-mode banners, tutorial/help, action-history replay. Shell-agnostic React components talking to Rust (Tauri) or Python (pywebview) through a single adapter.
>
> Guiding contract: **L7 never decides, it renders.** Every capability-affecting action travels L5 → event → L7 UI → user choice → command back to L5. This pattern is repeated for router tier changes, memory edits, persona swaps, BYOK changes. Read every section with that asymmetry in mind.

---

## 1. Purpose and scope

### 1.1 Owns
- **Onboarding wizard** (8-screen concrete flow per `plans/03_content_lock_v1_port.md §1`, reconciled with `06_onboarding_spec.md` 7-step outline; see §4).
- **Trust center** — "What Aether can / will ask / will never do", recent activity, grant ledger view, BYOK wallet, policy posture, model/source disclosure (§5).
- **Permission approval UX** — approval prompt modal, pending-approvals drawer, resource-scope picker, capability matrix surface (§3).
- **Preset picker** (5-preset ladder from L5 §6 surfaced during onboarding + Settings).
- **Action-history + replay UI** (§6).
- **Cost-visibility UX** — wallet view, in-line turn cost hints, cap-hit modal, approaching-cap nudge (§7).
- **Persona picker surface** — L6 `persona.list` rendering, swap-flow UI (§8).
- **Degraded-mode banners** — L5 / L4 / L2 / L6 / Media unreachable (§9).
- **Tutorial / help layer** — info-explainer primitive, modular walkthroughs, searchable help index (§12).
- **Consent revocation flow** — uniform across memory, permissions, integrations.
- **First-run checklist** post-wizard.

### 1.2 Does NOT own
- **Authorization decisions** → L5. L7 only renders `policy_decision` and posts `approval_response`.
- **Turn state** (typing → thinking → speaking → ack pool) → L1. L7 reflects `turn_state_change` events.
- **Routing decisions** (model choice, provider selection, tier routing) → L4. L7 surfaces `route_decision` in the audit UI.
- **Memory retrieval + storage** → L2. L7 proposes writes and queries, never stores.
- **Presence / avatar animation** → L3. L7 does not touch viseme / blend-shape streams.
- **Persona compilation** → L6. L7 renders the catalog and invokes compile/hot-reload.
- **Design tokens** → `packages/ui-kit`. L7 consumes.

### 1.3 Non-goals this session
- No styling, no Tailwind/CSS; component contracts only.
- No webview bundle layout; X1 owns monorepo structure.
- No help-center content authoring.

---

## 2. Shell-agnostic architecture

### 2.1 The rule

L7 React components import **only** from `packages/shell-adapter`. No component, hook, or store imports `@tauri-apps/api` directly. The adapter is the sole seam between UI and shell runtime. Violation lints fail the build. (`X3 §9.3`.)

### 2.2 Adapter pseudotype

```
// packages/shell-adapter — pure TS interface crate
interface ShellAdapter {
  // Typed command invocation. Generated client (ts-rs/specta) gives
  // per-command typed wrappers; invoke<T> is the escape hatch for dynamic
  // cases only. Every command returns either a value or a ChangeId that
  // later events will reference.
  invoke<TReq, TRes>(command: CommandName, req: TReq): Promise<TRes>;

  // Typed event subscription. Channels are declared in Rust; the UI
  // cannot invent a channel name. cb receives projected payloads with
  // {source_layer, change_id, seq} envelope. seq drops are detectable.
  subscribe<TPayload>(
    channel: ChannelName,
    cb: (evt: Projected<TPayload>) => void,
    opts?: { replayLastN?: number }
  ): Unsubscribe;

  // Open an OS resource (browser URL, file picker, external help page).
  // Never a filesystem side-effect — filesystem mutations go via commands.
  openNative(uri: NativeUri): Promise<void>;

  // Tiny local state store (window layout, panel sizes, wizard step
  // drafts). NOT for secrets, NOT for memory, NOT for grants. Backed by
  // tauri-plugin-store or pywebview JSON file.
  persistState<T>(key: StateKey, val: T): Promise<void>;
  loadState<T>(key: StateKey): Promise<T | undefined>;

  // Secret-field primitive. The user types a secret; the adapter forwards
  // it directly to Rust (OS keyring path) without the secret ever
  // appearing in React state, logs, or devtools. The adapter returns
  // only a SecretHandle opaque to the UI.
  captureSecret(
    purpose: SecretPurpose,
    prompt: SecretPromptSpec
  ): Promise<SecretHandle>;

  // Biometric / OS-unlock step. Mediates re-auth for capability-gated
  // L5 commands (X3 §5.3). Produces ephemeral command-token; token
  // travels only inside the next invoke().
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

### 2.3 Two implementations

| Implementation | Target | Command transport | Event transport | Secret handling |
|---|---|---|---|---|
| `shell-adapter-tauri` | Pro + OSS Tauri build | `@tauri-apps/api/tauri::invoke` | `@tauri-apps/api/event::listen` | Secret typed through Rust `#[tauri::command]` that writes directly to OS keyring; never returned |
| `shell-adapter-pywebview` | OSS Preview tactical only | `window.pywebview.api.<fn>` JSON bridge | Long-poll / injected event channel, seq-numbered | Secret sent via dedicated `secret_*` Python API that hands to `keyring` package |

Both must match shape for every command listed in §11. The component tree is **identical** — only the adapter differs. Cutover criterion is in `X3 §9.3` (OSS Preview Tauri build passes L7 onboarding happy-path + trust-center smoke tests).

### 2.4 Secret-handling rules (mandatory)

1. No secret value ever enters React state, React refs, context, redux, React Query, devtools.
2. `captureSecret` takes the user's input via a native-bridged field (Tauri window-owned input or pywebview overlay) and hands it directly to the Rust/Python side.
3. The UI receives only a `SecretHandle` — opaque, non-guessable, scoped to purpose.
4. Future commands reference the handle, not the secret.
5. Handles expire at session end or explicit revoke; revocation is an L5 grant-revoke.

### 2.5 IPC surface shape

Every command:
- Typed request + response (ts-rs / specta from Rust; mirrored Python docstrings on pywebview side).
- Typed error envelope (per layer; L5 uses `PolicyIpcError` per L5 §5.1).
- Write-class commands return a `ChangeId` the UI correlates to a follow-up projected event.
- **No "god" command.** `invoke("do_thing", ...)` is forbidden.
- Blocking vs non-blocking documented per command (§11).

### 2.6 Event subscription shape

- Channels declared in Rust, allowlisted in `tauri.conf.json`.
- Every projected event carries `{source_layer, change_id, seq}`.
- UI tracks per-channel high-water-mark `seq`; missing seq triggers `replayLastN` recovery on reconnect.
- Bursty channels (viseme on L3, presence) coalesced in Rust; L7 **does not** subscribe to viseme streams (that is L3's canvas).

---

## 3. Permission UI model

### 3.1 Capability taxonomy → UI mapping

L5's taxonomy (L5 §2.1) is flat; the UI groups it into 7 top-level accordions. Each accordion corresponds to one category in the taxonomy and is the **only** place that category's capabilities are configured outside the approval modal.

| UI category | Covers L5 capabilities |
|---|---|
| **Files** | `FilesRead`, `FilesCreate`, `FilesEdit`, `FilesRenameMove`, `FilesDelete`, `FilesBulkOp` |
| **Browser** | `BrowserOpen`, `BrowserReadPage`, `BrowserExtractData`, `BrowserFillForm`, `BrowserUpload`, `BrowserDownload`, `BrowserSubmit`, `BrowserLoginReuse` |
| **Email** | `EmailReadMetadata`, `EmailReadBody`, `EmailDraft`, `EmailEditDraft`, `EmailSend`, `EmailAttachmentAccess` |
| **System & Tools** | `ClipboardRead`, `ClipboardWrite`, `ShellExec`, `PackageInstall`, `NotificationRead`, `AutomationTrigger` |
| **Memory** | `MemoryRead`, `MemoryWriteSession`, `MemoryWriteDurable`, `MemoryWriteExtractedPref`, `MemoryUseInFutureTask`, `MemoryExport`, `MemoryDelete` |
| **Media** | `MediaMic`, `MediaCamera`, `MediaScreenCapture` |
| **Integrations** | `IntegrationUse(*)`, `IntegrationExternalApi(*)`, `IntegrationTriggerAutomation(*)` |
| **Router / cost** (advanced) | `RouterEscalateRemote`, `RouterOverrideTier`, `RouterAllowRemoteWithPrivate` |

The 8th category (Router/cost) sits under **Advanced** in the trust center — tier users don't see it until they expand.

### 3.2 Per-capability row — data contract

```
type CapabilityRow = {
  cap_id: CapabilityId;                // dot-path, e.g. "files.edit"
  human_label: string;                 // "Edit files"
  risk_class: "Low"|"Med"|"High"|"Critical";
  current_mode: "auto"|"task"|"ask"|"draft"|"deny"|"block";
  current_scope: ResourceScopeSummary; // display-only
  active_grants: GrantSummary[];       // from policy.list_grants filtered
  explainer_id: StaticCopyId;          // info-icon copy reference
  locked_by: "hardcoded_block"|"preset"|"persona"|null;
  hardcoded_block?: HardcodedBlockId;  // if locked_by = hardcoded_block
};
```

### 3.3 Approval prompt modal (wireframe)

```
+----------------------------------------------------------+
| (!) Approval requested                       [ close x ] |
|                                                          |
|  Edit file                                 [ HIGH ]      |
|  C:/Users/dbhav/Projects/aether-planning/plans/L7_*.md   |
|                                                          |
|  Aether wants to rewrite this file.                  (i) |
|  Persona: "Aether / Balanced"                            |
|  Reason: "apply user-requested section update"           |
|                                                          |
|  Scope this allow to:                                    |
|   ( ) This file only                                     |
|   (•) plans/ folder                                      |
|   ( ) All files in workspace root                        |
|   ( ) Let me type a pattern...                           |
|                                                          |
|  Duration:                                               |
|   ( ) Once   (•) This task   ( ) Session   ( ) Forever   |
|                                                          |
|  [ Deny ]  [ Draft only ]         [ Allow ] (enter)      |
|                                                          |
|  (i) Why am I being asked? -> policy.explain_decision    |
|  "Ask until dismissed" for this turn       [ ] pending   |
+----------------------------------------------------------+
```

### 3.4 Action → `approval_response` payload mapping

| UI action | `user_choice` posted (per L5 §4.2 `approval_response`) | Duration outcome |
|---|---|---|
| Allow once | `Allow` | `Once` grant, single action |
| Allow for this task | `AllowTask` | `TaskScoped(active_task_id)` |
| Allow for session | `AllowSession` | `Session` |
| Allow forever in scope | `AllowScope(resource_scope)` | `Persistent { ttl: preset_default }` |
| Draft only | `Deny` + UI flag emits `prefer_draft = true` (L7 hint to L1/cognition; L5 treats as `Deny`, the "draft-only" outcome actually comes from L5's `DraftOnly` decision branch — the user's manual "Draft only" choice is encoded as `Deny` with draft-preference hint) | no grant; cognition falls back to draft-only path |
| Deny | `Deny` | no grant |

**Contradiction flag:** L5 §4.2 defines `UserChoice` as `Allow | AllowScope | AllowTask | AllowSession | Deny`. No `Draft` variant exists. The "Draft only" button therefore must map to `Deny` plus a side-channel hint. Proposed fix (open question §20): extend `UserChoice` with `DeferToDraft` so the decision is first-class in the audit log instead of a hint. Flagged, not silently resolved.

### 3.5 NeedsUpgrade path

When `policy_decision = NeedsUpgrade { capability_path, suggested_preset }`:

```
+---------------------------------------------------+
|  This action needs a broader permission.          |
|                                                   |
|  Aether wants to: [cap description]               |
|  Your current preset "Observer" doesn't allow it. |
|                                                   |
|  Options:                                         |
|   [ Switch to "Assistant" preset ]                |
|      -> invokes policy.set_preset (re-auth)       |
|   [ Grant this once, keep preset ]                |
|      -> emits approval_response=AllowTask         |
|   [ Deny and keep preset ]                        |
|                                                   |
|  (i) What does "Assistant" allow that "Observer"  |
|      doesn't? -> policy.list_capabilities diff    |
+---------------------------------------------------+
```

### 3.6 Pending-approvals drawer

- Right-edge slide-out, badge count in main chrome.
- List of active `approval_pending` tickets sorted by `deadline_hint`.
- Each row: capability, resource, risk pill, countdown timer.
- Keyboard: `Ctrl+Shift+A` opens drawer; `J`/`K` navigate; `Enter` opens modal; `Esc` closes.
- On `approval_response` for a ticket, row removes with animation ≤120 ms.
- Idempotency: same `ticket_id` never renders twice (deduped on insert).
- Deadline pass (L1 stalls at 800 ms per L5 §4.2): row annotated "turn stalled — approve to resume" but does **not** auto-deny.

---

## 4. Onboarding flows

### 4.1 8-screen wizard (reconciled)

Reconciliation: `06_onboarding_spec.md` specifies 7 steps. `03_content_lock §1` says port forward the v1.0 8-screen concrete spec. We keep 8 screens because the v1.0 screens are more granular and the extra screen (disclosure split from welcome) helps comprehension.

| # | Screen | Purpose | Commands invoked | Events observed | Data captured → command |
|---|---|---|---|---|---|
| 1 | **Welcome** | One-sentence "what is Aether"; "I am an AI" disclosure up front; T&C plain-English summary + full text expand | `onboarding.save_step("welcome", {tc_accepted, disclosure_ack})` | none | consent flags |
| 2 | **Privacy & data** | What stays local, what can leave (privacy posture — L5 §10); category checkboxes; retention default | `onboarding.save_step("privacy", posture)` → `policy.set_preset_fragment` (internal) | `policy_decision` echo | privacy posture flags |
| 3 | **Assistant identity** | Name (optional), persona preset (Warm/Professional/Playful/Custom), optional voice, optional avatar preset; preview inline | `persona.list`, `persona.compile(id)` (dry-run preview), `onboarding.save_step("identity", {...})` | `persona_swap_commit` (on final confirm at end of wizard only) | persona_id, assistant_name |
| 4 | **Interaction mode** | Text / Text+Voice / Full Avatar; mic, voice output, avatar visibility toggles | `onboarding.save_step("interaction", {...})` | none | interaction flags |
| 5 | **Hardware tier** | Auto-detected tier badge, one-sentence meaning, storage preview, advanced override collapsed | `core.probe_hardware` (Rust), `onboarding.save_step("tier", tier_id)`, `router.set_tier_override(tier)` (L4, L5-gated) | `core.health tier` | tier_id |
| 6 | **LLM setup / BYOK** (Pro) or **Guest fallback** (OSS Preview) | Pick provider. Pro: BYOK entry via `captureSecret` → `router.set_byok_credential` (L4, L5-gated). OSS Preview: if no Ollama + no key, Guest mode card with disclosure | `router.list_providers`, `router.set_byok_credential`, `onboarding.save_step("llm", {...})` | `route_decision` (preview turn), `cost_threshold_hit` (only if existing usage) | provider, byok_handle, guest_optin |
| 7 | **Permissions preset** | 5-preset ladder (Observer / Assistant / Operator / Power User / Custom) with plain-language "will / will always ask / will never"; resource pickers for approved folders + domains; advanced matrix collapsed | `policy.list_capabilities`, `policy.set_preset(preset)` (requires re-auth), `onboarding.save_step("permissions", {...})` | `grant_issued` (preset-issued grants), `policy_decision` | preset_id, approved roots, approved domains |
| 8 | **Ready** | Summary of choices, first-run checklist (3–5 actions), offer showcase tour | `onboarding.save_step("ready", {})`, `onboarding.mark_complete` | none | completion flag |

### 4.2 Preset picker content (from L5 §6)

Each preset card shows:
- Name (plain-language)
- One-sentence summary
- 3 example actions it **allows** (auto or task-auto)
- 3 example actions it **asks** before doing
- 3 example actions it **never** does
- Risk-class footprint bar (count of Low/Med/High caps auto-approved)
- "Recommended for you" badge if matches persona default per L5 §6.4.

### 4.3 Performance-tier auto-detect flow

1. On Screen 1 load, L7 fires `core.probe_hardware` in background.
2. By Screen 5 render, `core.health tier` has emitted the recommendation.
3. Screen 5 shows detected tier + "Recommended for your system" badge.
4. User confirms or overrides. Override routes through `router.set_tier_override(tier)` which is L5-gated (`RouterOverrideTier` cap).
5. L5 issues a grant + `grant_issued` event; trust center reflects it.

### 4.4 BYOK setup (Pro)

1. User picks provider (OpenAI, Anthropic, etc.).
2. `captureSecret({purpose: "byok.<provider>", prompt: "Paste API key"})` → adapter returns `SecretHandle`.
3. UI calls `router.set_byok_credential({provider, handle})` — the Rust command uses the handle to read from OS keyring and validates the key.
4. Validation result is a `policy_decision` + `route_decision` preview.
5. Secret value never returned to React; only provider + masked fingerprint render.
6. `cost_threshold_hit` subscriptions start for that provider.

### 4.5 Guest mode (OSS Preview only)

- Forced preset: **Observer** (cannot be changed while Guest).
- No persona (hard-coded anonymous companion persona).
- No durable memory (session-only).
- Clearly labeled: "Guest mode — this conversation ends when the window closes."
- Banner on every turn: "Guest does not remember you. Install to keep this conversation."
- Rate-limit copy visible: "N/10 hourly turns used."
- Every turn: privacy disclosure reminder that bytes leave the machine (per `03_content_lock §2`).
- Guest → Pro upgrade path always one click away.

### 4.6 Privacy & disclosure screens (Screen 2 expansion)

Data categories (all checkboxes, defaulted to most-private):
- [ ] Allow durable memory on this device
- [ ] Allow Aether to use memories in future tasks
- [ ] Allow remote LLM calls when no private-tagged context is present
- [ ] Allow remote LLM calls even when private-tagged context is present (requires `RouterAllowRemoteWithPrivate`)
- [ ] Allow anonymous telemetry (error reports only)

Each has info-icon with the 5-part explainer (definition, why, recommended, example, impact).

### 4.7 Persona picker surface (Screen 3 expansion)

- `persona.list` → cards (persona_id, summary, class, default preset recommendation).
- Selecting a card shows preview (voice sample, example turn, avatar still).
- Confirmation defers compilation to end-of-wizard (Screen 8 commit) to avoid partial state.

### 4.8 First-run checklist post-wizard

Displayed as a non-modal panel on first app open after wizard completion:
- [ ] Try your first message
- [ ] Approve a file read (seeds first grant)
- [ ] Open trust center (1-click guided)
- [ ] Review what Aether will and won't do
- [ ] (Pro) Set a daily spend cap

### 4.9 Replayability

- `onboarding.replay({step?})` — launches wizard, optionally at a specific step.
- All captured data is editable from Settings under the same labels (06_onboarding_spec mandate).
- No state loss between wizard runs (step payloads persisted via `onboarding.save_step`).

---

## 5. Trust center — data + visual model

### 5.1 Sections (one surface, 7 tabs)

| Tab | Source | Data shape |
|---|---|---|
| **What Aether can do** | `policy.list_capabilities` filtered `mode != deny/block` | CapabilityRow[] |
| **Will always ask** | same, filtered `mode = ask` | CapabilityRow[] |
| **Will never do** | same, filtered `mode ∈ {deny, block}` + hardcoded block list from §2.3 | CapabilityRow[] (locked_by set) |
| **Recent activity** | `policy.get_audit_summary` + stream | AuditRow[] |
| **Granted scopes** | `policy.list_grants` | GrantCard[] |
| **BYOK wallet** | `router.list_providers` + L4 cost counters + L5 §9 caps | WalletMeter per provider |
| **Policy posture** | `policy.get_preset` + privacy flags + tier | PostureSummary |
| **Model + sources** | `router.list_providers` + `persona.list` active | DisclosurePanel |

Tabs are **keyboard-cycled**; default landing is "Recent activity" (most-answered question: "what just happened?").

### 5.2 Audit record — visual contract

```
+------------------------------------------------------------+
| 14:22:05  PERSONA "Balanced"  EDITED FILE         [ Allow ] |
| plans/L7_*.md  (resource scope: plans/**)                   |
| Reason: "apply user-requested section update"               |
| [ Expand raw ]  [ Replay ]  [ Revoke related grant ]        |
+------------------------------------------------------------+
```

Data contract:

```
type AuditRow = {
  audit_id: AuditId;
  timestamp_wall: WallClockTimestamp;    // local-formatted for display
  timestamp_mono_ns: u64;                // for stable sort
  actor_label: string;                   // "Persona 'Balanced'" | "You" | "System"
  capability_label: string;              // "Edited file"
  resource_display: string;              // truncated + tooltip for full
  decision: "Allow"|"Ask"|"DraftOnly"|"Deny"|"NeedsUpgrade";
  reason_copy: string | null;            // plain-language, NOT raw StaticReason
  related_grant_id: GrantId | null;
  redacted: boolean;                     // private-tagged; see §6.3
};
```

### 5.3 Filtering

- **Time range** — preset ranges (last hour / today / last 7d / custom).
- **Capability** — multi-select, grouped by the 7 top-level categories from §3.1.
- **Decision** — Allow / Ask / DraftOnly / Deny / NeedsUpgrade.
- **Resource pattern** — glob input; matched client-side against `resource_display` pre-fetch, then server-side via `policy.get_audit_summary` filter.
- **Persona** — multi-select from `persona.list`.

### 5.4 Search

- Free-text over `reason_copy`, `resource_display`, `capability_label`.
- Backed by `policy.stream_audit` with a `query` filter field (proposed extension; open question §20).
- Results paged (50/page).
- Never searches raw memory or turn content — audit rows only.

### 5.5 Export

- Button: "Export my audit log".
- Invokes `policy.export_audit` — a **capability-gated** command (proposed, open question §20: L5 §5.2 lists `stream_audit` but not `export_audit`). Requires re-auth.
- Output: JSONL file via OS native save dialog (`openNative` + `captureSavePath`).
- Successful export logs itself as an audit record (`MemoryExport`-like meta-audit).

---

## 6. Action history / replay UI

### 6.1 Replay invocation

```
invoke<ReplayRequest, ReplayHandle>("trust.replay_action", { action_id });
// Returns ReplayHandle with a streamed projection channel name.
// UI subscribes to `trust/replay/<handle_id>` for step events.
```

`trust.replay_action` shape per `X3 §2.2`. Handle is short-lived; ending the replay view releases it.

### 6.2 Replay visual

- Timeline scrubber across the top.
- Left column: state transitions (turn_state, policy decisions, route decisions).
- Right column: memory hits (ids + provenance class) and tool calls.
- Each node expandable to show the full record.
- Playback: step / play-all / pause.
- **Not** re-execution; read-only reconstitution from the audit log + bus replay.

### 6.3 Redaction rules

- Audit records tagged `private` by L2/L5 render as stubs: `<private — click to unmask>`.
- Unmasking invokes `requestReauth({purpose: "unmask_private_audit", scope: audit_id})`.
- Successful reauth grants a 60-second unmask window (visible countdown).
- Any unmask attempt (success or failure) is itself an audit record.
- Secret values inside a record (e.g. BYOK key fingerprint) are **never** unmaskable — they show redacted forever.

---

## 7. Cost-visibility UX

### 7.1 Wallet view (Trust Center → BYOK wallet tab)

Per-provider card:

```
+-------------------------------------------------+
|  OpenAI                           [ active ]    |
|  Today:   $0.42 / $2.00  [=====      ] 21%      |
|  Month:   $11.80 / $60.00 [===        ] 20%     |
|                                                 |
|  Next reset: Monthly 2026-05-01 00:00           |
|  [ Raise cap ]  [ Switch to local ]  [ Details ]|
+-------------------------------------------------+
```

Data contract:

```
type WalletMeter = {
  provider: ProviderId;
  daily_spent_cents: u32;    daily_cap_cents: u32|null;
  monthly_spent_cents: u32;  monthly_cap_cents: u32|null;
  trajectory_will_exceed: boolean;   // from L4 projection
  next_reset_wall_ms: i64;
  cap_hit: "none"|"daily"|"monthly";
  approaching: "none"|"daily_80pct"|"monthly_80pct";
};
```

### 7.2 In-line cost hint during turns (optional, tier-aware)

- Lite tier: no in-line cost hint (noise).
- Balanced/Full: small ghosted "~$0.003" after each remote turn, toggleable in Settings.
- Hint is driven by `route_decision.estimated_cost_cents`.

### 7.3 Cap-hit modal

On `cost_threshold_hit`:

```
+---------------------------------------------------+
|  You've hit your monthly cap for OpenAI.          |
|  ($60.00 spent; resets 2026-05-01)                |
|                                                   |
|  Aether will keep working, but remote OpenAI      |
|  calls are paused.                                |
|                                                   |
|  Options:                                         |
|   [ Raise cap ]        -> policy.set_cost_cap    |
|                          (L5-gated re-auth)      |
|   [ Switch to local ]  -> router.set_tier_override|
|                           (Lite/Balanced local)  |
|   [ Wait until reset ] -> close                  |
+---------------------------------------------------+
```

Raising cap is L5-gated (`RouterEscalateRemote`-adjacent; proposed new capability `policy.set_cost_cap` — open question §20). Requires re-auth.

### 7.4 Approaching-cap nudge

- When `approaching != "none"`, a small non-modal toast slides in at most once per day per provider per threshold.
- Dismissable; dismissal logged.
- Never blocks a turn.

---

## 8. Persona picker + hot-reload feedback

### 8.1 Picker surface

- Settings → Persona tab, and onboarding Screen 3.
- `persona.list` → card grid.
- Each PersonaCard: persona_id, display name, class, one-sentence summary, default-preset recommendation, "Selected" badge.

### 8.2 Swap flow

```
user clicks persona B
  └─> L7 disables swap button (prevent double-fire)
  └─> invoke("persona.compile", { persona_id: B })
         └─> returns CompiledPersonaHandle
  └─> L6 emits `persona_swap_begin` (projected)
         └─> UI shows "preparing persona..." banner + persona A greyed
  └─> L1 determines safe boundary (utterance end, no pending tool call)
  └─> L6 emits `persona_swap_commit`
         └─> UI transitions: avatar blend via L3, name/voice change,
             recent-activity strip appends "Persona swapped to B"
  └─> L5 emits `grant_revoked` for session grants incompatible with B
         └─> trust center grant list updates
```

### 8.3 Mid-utterance safety

- Swap button is **disabled** whenever `turn_state ∈ {speaking, thinking_with_commitment}` (per L1).
- Tooltip: "Wait for Aether to finish speaking."
- Attempted swap during a blocked window is rejected client-side (never invokes).
- L1 is the authority; L7 only mirrors its state.

---

## 9. Degraded-mode UX

### 9.1 Banner strip

- Top of main window, full-width, height clamped to 32 px (minimize visual cost when healthy).
- Severity colors: informational / warning / critical (tokens from ui-kit).
- Stackable: multiple banners visible if multiple subsystems degraded, ordered by severity.
- Always dismissable only when subsystem recovers (not by user click) — a degradation banner does not vanish on a click.

### 9.2 Per-failure banners

| Upstream failure (event) | Banner text (plain) | UI lockout |
|---|---|---|
| L5 unreachable / `DegradedMode::SafeMode` | "No automation mode — Aether can't act on your behalf right now." | All tool invocation UI disabled; memory-write disabled; approvals drawer shows "policy engine offline, pending approvals preserved" |
| L5 `AuditBroken` | "Audit log is unavailable. All actions are paused until it recovers." | Full write lockout; read-only allowed |
| L5 `LedgerCorrupt` | "Permissions in safe mode — only low-risk reads allowed." | Only `Low` risk auto-caps; else disabled |
| L4 unreachable | "Local-only mode — remote model calls are paused." | Remote-provider UI disabled; cost wallet shows "paused" |
| L2 unreachable | "No memory mode — Aether won't remember this session." | Memory-write UI disabled; memory-query greyed |
| L6 persona compile fail | "Minimum-trust persona active — your choices are still safe." | Persona picker shows error state for failing persona; all others selectable |
| Media engine stalled | "Repair in progress — audio/video pipeline restarting." (transient) | Mic/cam widgets show spinner; chat stays active |
| `core.health tier downgrade` | "Switched to Balanced tier to protect performance." | Avatar/effects step down; non-blocking |
| `emergency_revoke_all` in progress | "Emergency revoke in progress — all permissions are being revoked." | Every command except `policy.list_grants` (read) and re-auth disabled |
| `cost_threshold_hit` | Modal (not banner) — see §7.3. | Provider-specific; see §7.3 |

### 9.3 Never-blocked surfaces

The banner strip and any upstream-failure lockout **must not** disable:
- The "Emergency revoke all" button (`policy.emergency_revoke_all`).
- The trust center (read-only still viewable).
- The pending-approvals drawer (approving restores flow).
- The help / tutorial layer.
- The "Close window" affordance.

### 9.4 Recovery

- Banners auto-clear on recovery event (e.g. `core.health` tier returns to prior; L5 `PolicyDecision` flowing again).
- Recovery logs an audit entry summarizing the downtime.

---

## 10. Event subscription surface

L7 subscribes to the following projected channels. Each row states which UI surface updates and idempotency rules.

| Channel | Event | Source | UI surface updated | Idempotency |
|---|---|---|---|---|
| `policy/pending` | `approval_pending` | L5 | Pending-approvals drawer; approval prompt modal (focus) | `ticket_id` dedupe |
| `policy/response` | `approval_response` (confirmation projection) | L5 (echo) | Drawer row removal; recent-activity append | `ticket_id` one-shot |
| `policy/decision` | `policy_decision` | L5 | Recent activity row; any pending UI awaiting this `change_id` | `audit_id` dedupe |
| `policy/grant_issued` | `grant_issued` | L5 | Trust center grants tab; relevant capability row | `grant_id` dedupe |
| `policy/grant_revoked` | `grant_revoked` | L5 | Trust center grants tab; banner if `reason = persona_swap` | `grant_id` revoke-once |
| `policy/audit` | `audit_record` (summary) | L5 | Recent activity tab; history scrubber | `audit_id` dedupe; seq-ordered |
| `policy/emergency` | `emergency_revoke_all` | L5 | Banner (§9); full lockout overlay | single in-flight |
| `policy/cost` | `cost_threshold_hit` | L5 | Wallet; cap-hit modal (§7.3) | once per threshold window |
| `router/decision` | `route_decision` | L4 | Replay UI; in-line cost hint; model disclosure | `change_id` dedupe |
| `turn/*` | `turn_state_change` | L1 | Persona-swap button gate; chat chrome | seq-ordered |
| `presence/state` | `presence_state` (low-freq) | L3 | Avatar chrome (status dot only, not animation) | latest-wins |
| `persona/compiled` | `persona_swap_begin`, `persona_swap_commit` | L6 | Persona picker; swap banner | per-handle |
| `core/health` | tier downgrade / reconnect / resource pressure | Core | Degraded-mode banner; tier badge | latest-wins |

Seq drops on any channel trigger `subscribe(..., {replayLastN: N})` recovery.

---

## 11. IPC surface L7 consumes

Consolidated per owner. All commands typed per adapter §2.5. Blocking/non-blocking per L5 §5.2 or analogous.

### L5 (policy) — canonical per `plans/L5_policy_engine_system_design.md §5.2`
- `policy.evaluate(action) -> Decision`  *(rare from L7; cognition invokes; L7 observes)*
- `policy.request_approval(request_id) -> ApprovalTicket`
- `policy.respond_approval(ticket_id, user_choice) -> ChangeId`
- `policy.set_preset(preset) -> PresetSwitchReceipt`  **re-auth**
- `policy.get_preset() -> CurrentPreset`
- `policy.list_grants(filter?) -> Grant[]`
- `policy.revoke(target) -> RevokeReceipt`  **re-auth for All**
- `policy.list_capabilities(filter?) -> CapabilityInfo[]`
- `policy.explain_decision(audit_id) -> Explanation`
- `policy.preview_plan(plan) -> PlanPreview`  *(P2)*
- `policy.emergency_revoke_all(scope) -> EmergencyReceipt`  **re-auth**
- `policy.get_audit_summary(filter) -> AuditSummary[]`
- `policy.stream_audit(filter, cursor) -> EventStream<AuditRecordEvent>`
- `policy.export_audit(filter, dest) -> ChangeId`  *(proposed, open question §20)*
- `policy.set_cost_cap(provider, cap) -> ChangeId`  *(proposed, open question §20)*

### L2 (memory) — per `X3 §2.2`
- `memory.query(scope, query) -> MemoryHit[]`
- `memory.edit(memory_id, patch) -> ChangeId`  *(L5-gated)*
- `memory.export(scope) -> Uri`  *(L5-gated)*
- `memory.propose_write(draft) -> WriteProposal`  *(cognition invokes; L7 renders proposal)*

### L4 (router) — per `X3 §2.2`
- `router.route_preview(intent) -> RoutePlan`
- `router.list_providers() -> ProviderInfo[]`
- `router.set_byok_credential(provider, handle) -> ChangeId`  *(L5-gated)*
- `router.set_tier_override(tier) -> ChangeId`  *(L5-gated)*

### L6 (persona) — per `X3 §2.2`
- `persona.list() -> PersonaSummary[]`
- `persona.compile(persona_id) -> CompiledPersonaHandle`
- `persona.hot_reload(handle) -> ChangeId`

### L1 (turn) — per `X3 §2.2`
- `turn.begin_user_turn(input_kind) -> TurnId`
- `turn.submit_text(turn_id, text) -> ChangeId`
- `turn.cancel(turn_id) -> ChangeId`
- `turn.subscribe_state(turn_id) -> EventStream<TurnEvent>`

### L7-owned orchestration helpers (Rust services; L7 commands)
- `onboarding.save_step(step_id, payload) -> ChangeId`
- `onboarding.mark_complete() -> ChangeId`
- `onboarding.replay(step?) -> ChangeId`
- `trust.get_action_history(filter) -> Action[]`
- `trust.replay_action(action_id) -> ReplayHandle`
- `trust.get_pending_approvals() -> ApprovalTicket[]`  *(state-replay after webview reload; see §15.2)*
- `trust.first_run_checklist_state() -> ChecklistState`
- `trust.acknowledge_banner(banner_id) -> ChangeId`

### Shell / platform
- `core.probe_hardware() -> HardwareProfile`
- `core.health.subscribe() -> EventStream<HealthEvent>`

---

## 12. Tutorial / help layer

### 12.1 Info-explainer primitive (the `(i)` icon)

Single reusable component, used 100+ places. Data contract:

```
type InfoExplainerSpec = {
  explainer_id: StaticCopyId;      // keyed, not inlined — supports i18n
  // Each explainer renders 5 sections per 06 §"Mandatory rules":
  //  1. plain-language definition
  //  2. why this matters
  //  3. recommended default
  //  4. example use case
  //  5. impact summary (privacy/perf/trust/cost where relevant)
  learn_more_route?: HelpRoute;    // deep-link into help center
};
```

- 5-line cap on the popup body; deeper content behind "Learn more".
- Keyboard: tab-focus the `(i)`, Enter/Space opens, Esc closes.
- Every new form control fails the build lint without an `explainer_id`.

### 12.2 Modular walkthroughs

Walkthrough inventory (P0–P3):
- **first_run** — 3–5 beat inline tour immediately after onboarding.
- **permission_prompt_explainer** — fires first time user sees an approval modal.
- **trust_center_tour** — guided tour of the 7 tabs.
- **byok_setup** — guides BYOK key entry (Pro).
- **persona_picker** — explains persona selection + swap.
- **cost_cap_setup** — how to set + what happens when hit.

Each walkthrough:
- Skippable at any step.
- Replayable from Settings → Help.
- Progress persisted via `onboarding.save_step("walkthrough.<id>", {step})`.

### 12.3 Searchable help index (later milestone)

- Lunr / FlexSearch; decision low-stakes (open decision per upstream `L7_trust_ux_onboarding.md`).
- Index scoped to help content only — never indexes memory, audit, or turn content.

### 12.4 Skippable + replayable

- Every tutorial is skippable.
- Re-entry from Settings → Help → Tutorials.
- Dismissal state is per-walkthrough per-user.

---

## 13. Design-language bindings

### 13.1 Style posture

- Dark-theme monochrome neumorphic per `05_ux_principles.md` + Don's preferences.
- Motion discipline: reduced-motion honored; no parallax in core surfaces.
- Typography / color tokens live in `packages/ui-kit` — L7 imports, never defines.
- **No Tailwind-default purple / AI-slop gradients**; brief each UI-phase pass with Don's `ai-slop-audit-design` before sign-off.

### 13.2 Component inventory — data contracts only

| Component | Props contract summary | Consumed events |
|---|---|---|
| **Modal** | `{ title, severity, onClose, children, focusTrap }` | — |
| **ApprovalPrompt** | `{ ticket: ApprovalTicket, onRespond(user_choice, scope?) }` | `approval_pending` for the same ticket (cancel on external revoke) |
| **RiskPill** | `{ risk_class: "Low"|"Med"|"High"|"Critical", locked?: bool }` | — |
| **CapabilityRow** | `CapabilityRow` from §3.2 + `onConfigure(cap_id)` | `grant_issued`/`grant_revoked` for `cap_id` |
| **ScopePicker** | `{ capability, suggested_scopes, onPick(scope) }` | — |
| **GrantCard** | `{ grant: Grant, onRevoke(grant_id) }` | `grant_revoked` |
| **AuditRow** | `AuditRow` from §5.2 + `onExpand`, `onReplay`, `onRevokeRelated` | — |
| **WalletMeter** | `WalletMeter` from §7.1 + `onRaiseCap`, `onSwitchLocal` | `cost_threshold_hit` |
| **BannerStrip** | `{ banners: Banner[], onAcknowledge(id) }` | `core.health`, `policy/emergency`, degraded-mode signals |
| **WizardShell** | `{ steps: WizardStep[], current, onSave(step,payload), onComplete }` | — |
| **PersonaCard** | `PersonaSummary + selected + onSelect` | `persona_swap_commit` (selected badge) |
| **TierBadge** | `{ tier: "Lite"|"Balanced"|"Full", degraded?: bool }` | `core.health tier` |
| **InfoExplainer** | `InfoExplainerSpec` (see §12.1) | — |

Styling implementation deferred to UI-phase pass.

---

## 14. Accessibility and non-technical user comprehension

### 14.1 Plain-language translation table (L5 error vocab → user copy)

| L5 `DenyReason` / `PolicyIpcError` | User-facing copy | Surface |
|---|---|---|
| `HardcodedBlock(id)` | "Aether can't do that in any preset — it's a safety-locked action." + link to the block's explainer | Approval modal; recent activity |
| `FeatureDisabled` | "Your current preset doesn't allow this. You can switch presets or allow this once." | NeedsUpgrade modal |
| `ActionOutOfScope` | "This action isn't in your current permissions." | NeedsUpgrade modal |
| `ResourceOutOfScope` | "You haven't given Aether access to this folder/site yet." + "Add scope" button | Approval modal |
| `ModeDeny` | "You set this to never — Aether won't do it." | Recent activity |
| `GrantExpired` | "The earlier permission has expired. Approve again?" | Approval modal |
| `GrantRevoked` | "You revoked this permission." | Recent activity |
| `ProvenanceTaint(kind)` | "Aether won't act on information from an untrusted source without asking you first." | Approval modal |
| `PrivacyPostureViolation` | "This would send private information off your machine. Blocked by your privacy settings." | Approval modal; privacy tab |
| `CostCapHit(provider)` | "You've hit your cost cap for {provider}." | Cap-hit modal (§7.3) |
| `TierDowngradeStripped` | "Aether switched to a lighter tier — a few advanced actions are paused." | Banner |
| `LedgerCorrupt` | "Permissions in safe mode — only low-risk reads allowed." | Banner |
| `AuditWriteFailed` | "Audit log is unavailable. All actions paused until it recovers." | Banner |
| `PolicyIpcError::RequiresReauth` | "Confirm it's you to continue." | Re-auth modal |
| `PolicyIpcError::Conflict` | "This approval was already answered." | Toast |

### 14.2 Keyboard-first navigation

- All approval actions reachable without mouse: Tab → focus actions, Enter → primary, Esc → Deny.
- `Ctrl+Shift+A` → approvals drawer.
- `Ctrl+Shift+T` → trust center.
- `Ctrl+Shift+R` → emergency revoke all (with confirm).
- Visible focus ring per `05_ux_principles`; no focus-ring suppression.

### 14.3 Screen-reader labels

- Risk pills: `aria-label="{risk} risk"` + invisible description stating what that risk implies.
- Pending approvals list: `aria-live="polite"`, each row announces "pending approval, {capability}, {risk} risk".
- Banners: `role="alert"` on critical/warning, `role="status"` on informational.
- Every audit row announces decision first, then capability, then resource.

### 14.4 Comprehension tests

- Don's informal rubric (no target numbers this session). Rubric seeds:
  - Can a non-technical user say out loud what just happened after seeing an audit row?
  - Does the approval modal answer "what, why, how big a deal" in the first glance?
  - After onboarding, does the user know one way to revoke everything?

---

## 15. Failure / degraded modes inside L7

### 15.1 IPC transport failure

- Adapter detects transport failure (Tauri IPC disconnect, pywebview bridge drop).
- All pending `invoke` promises reject with a typed `IpcTransportLost` error.
- UI enters "Reconnecting..." state (BannerStrip informational).
- Auto-reconnect with exponential backoff (100 ms, 200 ms, 400 ms, capped at 3 s).
- On reconnect: replays subscribed channels via `subscribe(..., {replayLastN: 50})` per channel.

### 15.2 Component state loss on webview reload

- Webview reload (crash, hot-swap) loses all React state.
- On boot, L7 calls:
  - `trust.get_pending_approvals()` → re-hydrate approvals drawer.
  - `policy.get_preset()` → restore preset display.
  - `policy.list_grants()` → restore grants view.
  - `onboarding.state()` → if wizard in-progress, restore step.
  - Subscribed channels rehydrate via `replayLastN`.
- No user-visible loss if Rust side healthy.

### 15.3 Optimistic UI rollback

- On an approval response, UI optimistically marks the ticket "responding..." and the approval modal closes.
- If follow-up `policy_decision` arrives as `Deny` (e.g. hardcoded block caught after user chose Allow), UI:
  - Reopens the modal with a non-dismissable banner: "Your choice couldn't be applied: {plain-language reason}."
  - Shows the final decision; user can Dismiss.
  - Appends an audit row.

### 15.4 Secret-leak prevention

- Secrets never in React state (§2.4).
- Devtools capture of secret fields is blocked via native-bridged input overlay (Tauri) or webview-owned input intercept (pywebview).
- React error boundaries strip any field named `secret`, `api_key`, `token` from error payloads before sending to logs.
- Audit never records secret values (only masked fingerprints).

---

## 16. OSS Preview vs Pro divergence

Single codebase; divergence via build flags (`X3 §9`).

| Feature | OSS Preview | Pro |
|---|---|---|
| Onboarding wizard | 8 screens, simplified LLM step (Ollama / Guest / BYOK basic) | 8 screens, full BYOK + provider picker |
| Preset ladder | Observer / Assistant only (plus locked preview of others) | Full 5-preset ladder |
| Trust center | 4 tabs (Can do / Will ask / Will never / Recent activity) | Full 7 tabs |
| BYOK wallet | Not shown (Guest / Ollama `$0.00` only) | Full wallet + caps |
| Guest mode | Available | Not shown |
| Audit view | Last 7 days, no replay | Full history + replay |
| Persona picker | Fixed starter pack | Full persona catalog + custom |
| Banners | Same (L5/L4/L2 banners shipped in both) | Same |
| Help / tutorials | First-run, permission explainer | Full set including BYOK + cost-cap tutorials |
| Export audit | Not available | Available (re-auth) |

Divergence by **build-time feature flag**, not separate components. Components accept an `edition` prop or read a single `useEdition()` hook to conditionally render advanced affordances. This keeps the component tree identical so the shell-adapter story from §2 holds.

---

## 17. Stub interfaces for other layers

Enough surface that L1/L2/L4/L5/L6 can stub against L7 without L7 being finished.

### 17.1 L5 needs

- `ApprovalResponse { ticket_id, user_choice, responded_at }` payload shape exactly as L5 §4.2. L7 posts it via `policy.respond_approval`.
- **Contradiction flag**: if §20 open question on `DeferToDraft` is resolved, the `UserChoice` enum gains a variant; L5 §4.2 needs a corresponding edit.
- `trust.get_pending_approvals() -> ApprovalTicket[]` shape for state-replay after reload.

### 17.2 L1 needs

- `onboarding.mark_complete` emits a `core.event::onboarding_complete` that L1 listens for to start the first-run handoff (ack pool primed with greeting).
- `turn_state_change` L7 reflects but does not produce.

### 17.3 L4 needs

- `router.list_providers` shape consumed by wallet + BYOK screen.
- `route_decision` projected event consumed by replay UI + in-line cost hint.
- `captureSecret` → `SecretHandle` is the sole path BYOK keys enter the router; L4 needs to read keys from OS keyring by handle, never from IPC payload.

### 17.4 L2 needs

- `memory.propose_write` rendered as a modal; user Accept/Decline becomes an `approval_response` under the `MemoryWriteDurable` / `MemoryWriteExtractedPref` capability.
- `memory.export` triggers a native-save flow via `openNative`.

### 17.5 L6 needs

- `PersonaSummary` shape (id, display_name, class, summary, default_preset_recommendation) for picker stubbing.
- `persona_swap_begin` / `persona_swap_commit` event projection.
- `persona.compile` is the sole compile path — L7 never compiles personas itself.

---

## 18. Testing strategy (design level)

### 18.1 Comprehension tests (informal)

- Rubric: "after reading the modal, can the user say in their own words what Aether is asking to do, what happens if they say yes, and what happens if they say no?"
- 5 non-technical participants per milestone (Don's informal recruit).
- Pass/fail per screen is Don's call; no numeric target.

### 18.2 Accessibility audit checklist

- Keyboard-only traversal of onboarding wizard, trust center, approval modal.
- Screen reader (NVDA on Windows) traversal of the same.
- Color contrast ≥ WCAG AA across all tokens in `packages/ui-kit` (token-level assertion, not per-component).
- Reduced-motion: no tween > 150 ms under `prefers-reduced-motion`.
- Focus-ring visible on every interactive element.

### 18.3 Red-team UX tests

- Can a non-technical user be tricked into granting a risky capability by a prompt-injected plea? Simulate L5 `ProvenanceTaint` flows; verify draft-only fallback is clearly distinguished from normal allow.
- Decision-fatigue test: 20 low-stakes approvals in 10 minutes. Does the user start auto-clicking? Target: session grants should cover enough so low-stakes approvals are rare.
- Dark-pattern audit every release: no pre-checked consent boxes, no bundled permissions, no asymmetric button weights between Allow/Deny.

### 18.4 Visual regression hooks

- Per-component screenshot snapshots (Playwright + deterministic fixtures).
- Actual implementation deferred; contract hooks reserved in each component via `data-testid`.

---

## 19. Deliverables summary (what a frontend implementer builds first)

1. **`packages/shell-adapter` interface** (TS) + `shell-adapter-tauri` implementation. Pywebview adapter stubbed.
2. **Component inventory** — 13 components from §13.2 wired to contracts only (no styling).
3. **8-screen wizard skeleton** — navigable empty shell with `onboarding.save_step` wiring.
4. **Approval-prompt modal** wired to `approval_pending` / `approval_response`. Pending-approvals drawer driven by same channel.
5. **Trust center shell** — 4 tabs minimum (OSS Preview floor); the other 3 behind edition flag.
6. **Degraded-mode banner system** — BannerStrip + `core.health` + L5 degraded-mode subscription.

All six can be implemented against Rust stubs that return fixture data, so L7 does not block on L1–L6 completion.

---

## 20. Open questions

1. **`UserChoice::DeferToDraft` variant** — the "Draft only" action in the approval modal currently must round-trip as `Deny` + side-channel hint. Should L5 §4.2 add a first-class variant so the audit log captures user intent precisely? *(Blocks: clean audit trail of "user chose draft"; propose add.)*
2. **`policy.export_audit` command** — L5 §5.2 lists `stream_audit` but no file-export command. Trust center's "Export my audit log" needs one. Add to L5 command catalog with re-auth gate?
3. **`policy.set_cost_cap` command** — cap-hit modal's "Raise cap" action needs a command. L5 §9 defines counters + thresholds but no UI-facing cap-mutate command. Propose add with re-auth gate.
4. **pywebview adapter parity** — can we guarantee event-replay + seq-ordering semantics through pywebview's JSON bridge, or do we accept lossy behavior on OSS Preview and cap features accordingly? *(X3 §9.3 assumes yes; verify at adapter prototype.)*
5. **Guest mode infrastructure** — Cloudflare Worker + Groq free tier (per `03_content_lock §2`) vs. alternative provider vs. defer post-OSS-Preview? Upstream `L7_trust_ux_onboarding.md` flags this.
6. **Single main window vs dedicated trust-center / onboarding windows** — `X3 §10` raises this; L7 position: single window with routed panes for v1 (fewer capability-allowlist divergences). Confirm with Don.
7. **Second webview window for onboarding (X3 open question #6)** — same as #6 above, phrased from X3's side. L7 currently assumes single window.
8. **Search index for help center** — Lunr vs FlexSearch vs custom. Low-stakes; pick before P3.
9. **Keybinding collisions** — `Ctrl+Shift+R` (emergency revoke) overlaps browser refresh on some systems when a webview is focused; needs a chorded alternate.
10. **Comprehension-test target numbers** — Don prefers informal rubric. Should we formalize a minimum pass rate before ship? Leaving informal per Don's preference.
11. **`feedback_css_default_for_ui.md` vs Tauri lock** — upstream flagged contradiction (memory file says pywebview canonical; session doctrine locks Tauri). Spirit preserved (HTML/CSS/JS) but memory-file text is stale. Don decides whether to rewrite the memory entry.
12. **`InfoExplainer` build-time lint** — which lint rule and in which CI stage? Enforcement mechanism not yet specified.

---

## 21. Self-review checklist

- [x] Every L5 event projected to UI has a subscription entry in §10 (`approval_pending`, `approval_response` echo, `policy_decision`, `grant_issued`, `grant_revoked`, `audit_record`, `emergency_revoke_all`, `cost_threshold_hit` all present).
- [x] Every L5 command L7 invokes appears in §11 with the right layer owner, including proposed new ones flagged (§20).
- [x] Every capability in L5's taxonomy renders in §3 permission UI (7 + 1 accordion categories cover every enum variant).
- [x] §2 shell-adapter design works for BOTH Tauri and pywebview (§2.3 table).
- [x] §9 has a degraded-mode banner for each upstream failure (L5 SafeMode/AuditBroken/LedgerCorrupt, L4, L2, L6, Media, tier downgrade, emergency revoke).
- [x] §14 has an accessibility entry for every user-facing decision point (plain-language translation table, keyboard map, screen-reader labels, comprehension rubric).
- [x] §17 gives dependent layers enough stub surface (L1, L2, L4, L5, L6 each have a subsection).

---

## 22. Contradictions surfaced (flagged, not resolved)

1. **`UserChoice` missing `DeferToDraft`** — approval modal's "Draft only" action has no clean encoding. See §3.4 note + §20 item 1.
2. **No `policy.export_audit` in L5 §5.2** — trust center export requires it. §20 item 2.
3. **No `policy.set_cost_cap` in L5 §5.2** — cap-hit modal's "Raise cap" requires it. §20 item 3.
4. **`feedback_css_default_for_ui.md` vs Tauri lock** — session doctrine locks Tauri; user memory says pywebview canonical. Spirit preserved, text stale. Upstream `L7_plan §7.7` already flagged; reiterated here. §20 item 11.
5. **Wizard length**: `06_onboarding_spec.md` says 3–7 steps ("7 core steps"); `03_content_lock §1` and this doc say 8. Reconciled in §4.1 (8 kept for granularity); noted so anyone reading `06` alone sees the divergence.

---

## 23. Confidence per required section

| Section | Confidence | Rationale |
|---|---|---|
| §1 Purpose + scope | **High** | Directly mirrors `L7_trust_ux_onboarding.md` boundaries. |
| §2 Shell-agnostic architecture | **High** | `X3 §9.3` + §10 pin the shape; secret rules derived from §13 security posture. |
| §3 Permission UI model | **High** | Maps 1:1 onto L5 §2.1 + §4.2; one contradiction flagged (DeferToDraft). |
| §4 Onboarding flows | **High** | Reconciled 8-screen vs 7-step; BYOK + Guest explicit. |
| §5 Trust center | **High** | 7-tab model covers all L5/L4/L6 surfaces; export gap flagged. |
| §6 Action history / replay | **Medium-High** | Replay shape relies on `trust.replay_action` from X3 §2.2; deeper replay semantics await L5/L1 integration wave. |
| §7 Cost-visibility UX | **Medium** | Cap-raise command missing in L5 spec; flagged. |
| §8 Persona picker | **High** | L6 surface thin and stable. |
| §9 Degraded mode UX | **High** | Banner-per-failure enumerated; doctrine-aligned. |
| §10 Event subscriptions | **High** | Every projected L5 event mapped; cross-layer channels enumerated. |
| §11 IPC surface consumed | **High** | Consolidated from L5/L4/L2/L6/L1/X3; proposed additions flagged. |
| §12 Tutorial / help | **High** | InfoExplainer contract + walkthrough inventory concrete. |
| §13 Design-language bindings | **Medium** | Component contracts firm; styling deferred by design. |
| §14 Accessibility | **High** | Plain-language table keyed to L5 error vocab; keyboard + SR covered. |
| §15 Failure / degraded in L7 | **High** | Reconnect, replay, optimistic rollback, secret-leak all covered. |
| §16 OSS Preview vs Pro | **High** | Build-flag divergence table. |
| §17 Stub interfaces | **High** | Enough for L1/L2/L4/L5/L6 to stub against. |
| §18 Testing strategy | **Medium** | Design-level only; implementation deferred per scope. |
| §19 Deliverables | **High** | Concrete first-build list. |
| §20 Open questions | **High** | 12 items, each actionable. |
