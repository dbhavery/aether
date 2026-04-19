---
status: draft
date: 2026-04-18
owner: X3 agent (Tauri architecture)
coordinator: Don
depends_on:
  - 01_product_doctrine.md (§"Desktop framework doctrine")
  - 08_system_architecture.md (six engines, event bus)
  - 14_performance_tiers_vram.md (Lite / Balanced / Full)
  - 15_updates_releases.md (stable/beta/experimental)
  - 16_tech_stack.md (Rust / TS / Python split)
  - plans/00_ORCHESTRATION_MAP.md (§2 Tauri-vs-pywebview reconciliation)
  - plans/03_content_lock_v1_port.md §5 (Inno → Tauri updater transition)
  - plans/L1..L7 (consumers of the IPC + event bus this plan defines)
assumptions:
  - X1 monorepo layout is not yet written; this plan marks every monorepo-path claim as "X1-dependent" and must be reconciled once `plans/X1_repo_restructure.md` lands.
  - WebView2 runtime is present or bootstrapped on all Windows targets; Edge Chromium is the only supported webview engine on Windows for Pro.
gates (human-in-the-loop):
  - G1 Rust↔TS boundary shape (commands + events) — APPROVED 2026-04-18 (Don)
  - G2 Plugin-vs-core allowlist — PENDING REVIEW
  - G3 Updater channel model + code-signing cert path — PENDING REVIEW
  - G4 IPC + filesystem scope defaults — PENDING REVIEW
---

# X3 — Tauri Architecture Plan (Aether Pro + shared family foundation)

> **Status: planning only.** No scaffolding until Don approves G1–G4.
>
> This document defines how the Aether Pro desktop app is built as a Tauri application: the Rust core / TS UI boundary, event-bus integration, plugin model, signed updater, code-signing path, IPC + filesystem defaults, WebView2 story, and the transition plan for OSS Preview's pywebview shortcut. It is compatible with the 7-layer planning model and the three performance tiers (Lite / Balanced / Full).

---

## 1. Architecture overview (prose diagram)

```
                       +-----------------------------------------------+
                       |                   Tauri app                   |
                       |                                               |
   +---------------+   |   +--------------------+   +---------------+  |
   | Local models  |<--+---+                    |   |   WebView2    |  |
   | (Gemma 4,     |   |   |    Rust core       |   |  (Chromium)   |  |
   |  STT, TTS)    |   |   |  (tauri::Builder)  |<->|   React/TS    |  |
   +---------------+   |   |                    |IPC|   UI          |  |
          ^            |   |  L1..L6 runtime    |   |   (L7 + slices|  |
          |            |   |  event bus         |   |    of L1..L6) |  |
   +---------------+   |   |  policy engine     |   +---------------+  |
   |  Local store  |<--+---+  storage drivers   |                      |
   |  (SQLite,     |   |   |  updater           |                      |
   |  vector idx,  |   |   |  plugin host       |                      |
   |  blobs)       |   |   +--------------------+                      |
   +---------------+   |           ^                                   |
                       |           |                                   |
                       +-----------|-----------------------------------+
                                   |
                       +-----------+-----------+
                       | Frontier LLM / sync   |  (opt-in, L4+L5 gated)
                       +-----------------------+
```

**Key property.** The **Rust core is the boundary of the product**. The WebView is a rendering surface for L7 and for user-visible slices of L1–L6. No business logic lives in the webview that cannot be re-derived, re-invoked, or re-authorized via Rust. Closing the webview and reopening it cannot leave Rust in an inconsistent state.

---

## 2. Rust core ↔ TS UI boundary

### 2.1 Boundary principle

1. **Rust owns truth.** Every must-own layer (L1–L6) runs in Rust. The UI observes state and requests transitions; it does not *hold* state authoritative to the product.
2. **The webview is a view, not a worker.** Heavy work (inference, memory IO, policy evaluation, media chunking) never runs in the webview. The UI schedules, renders, and collects user intent.
3. **Every Rust-exposed operation is a typed command.** No stringly-typed `invoke("do_thing", {...})` shape. Commands are declared in a single Rust crate (`core/ipc`) and mirrored into a generated TS client (`ts-rs` or equivalent, evaluated at G1).
4. **Every system-affecting command is a capability.** Once L5 is live, every command that mutates state, touches the filesystem, calls a tool, or escalates to remote is gated through the policy engine — no exceptions, no webview-side bypass. Design for this from day one even before L5 ships.
5. **Events are append-only.** The UI subscribes to typed events on the Tauri event bus; it cannot rewrite history. Replay and audit trails live in Rust.

### 2.2 Command surface (illustrative, to be frozen at G1)

Grouped by L-layer; each command is a `#[tauri::command]` with a typed request/response struct.

```
# L1 — interaction timing
turn.begin_user_turn(input_kind) -> TurnId
turn.submit_text(turn_id, text) -> ()
turn.cancel(turn_id) -> ()
turn.subscribe_state(turn_id) -> EventStream<TurnEvent>

# L2 — memory kernel
memory.query(scope, query) -> Vec<MemoryHit>
memory.propose_write(draft) -> WriteProposal     # gated by L5
memory.edit(memory_id, patch) -> ()              # gated by L5
memory.export(scope) -> Uri                      # gated by L5

# L3 — presence (thin surface; renderer mostly autonomous)
presence.set_mode(mode) -> ()                    # e.g. listening/speaking
presence.subscribe_state() -> EventStream<PresenceState>

# L4 — model router
router.route_preview(intent) -> RoutePlan        # shows the user what will happen
router.set_tier_override(tier) -> ()             # gated by L5

# L5 — policy
policy.evaluate(action) -> Decision
policy.request_approval(action) -> ApprovalTicket
policy.set_preset(preset) -> ()                  # gated: requires re-auth
policy.list_grants() -> Vec<Grant>

# L6 — persona compiler
persona.list() -> Vec<PersonaSummary>
persona.compile(persona_id) -> CompiledPersonaHandle
persona.hot_reload(handle) -> ()

# L7 — trust + onboarding (UI orchestration helpers)
trust.get_action_history(filter) -> Vec<Action>
trust.replay_action(action_id) -> ReplayHandle
onboarding.save_step(step_id, payload) -> ()
```

Rules for the surface:
- **No "god" command.** `invoke("run", ...)` is forbidden.
- **Every command has a written failure vocabulary.** No untyped errors cross the IPC boundary.
- **Every write-class command returns a `ChangeId`** the UI can use to correlate the subsequent event.

### 2.3 What the UI actually holds

- Ephemeral UI state only: panel selections, scroll position, in-progress form drafts, optimistic UI hints.
- A **short-lived view cache** of Rust state, invalidated on each relevant event.
- No persisted secrets. No policy decisions. No memory contents beyond what the current view needs.

---

## 3. Event-bus integration pattern

### 3.1 Two buses, one direction of truth

- **Rust-internal event bus** (see `08_system_architecture.md`): the canonical, typed, persistent, replayable bus. All L1–L6 events live here. L1 is the heaviest consumer.
- **Tauri `emit` / `listen` bridge**: a **filtered projection** of the Rust bus to the webview. Not every internal event is projected; many are internal-only (inference step traces, low-level timing beats).

### 3.2 Rules for the bridge

1. Projection is **declared in Rust**, not chosen by the webview. The webview subscribes to allowlisted channels.
2. Projected events are **typed** (shared structs via `ts-rs` or equivalent).
3. Every projected event carries a `source_layer`, `change_id`, and monotonic `seq`. The UI can detect drops.
4. The bridge is **back-pressure-safe**: bursty sources (e.g. viseme streams) are either coalesced on the Rust side or moved to a dedicated high-frequency channel that the UI can opt out of on low tiers.
5. Events cross the bridge **one-way** (Rust → UI). UI-originated intent always travels as a command, not an event.
6. Bridge output is **replayable**: the UI can ask Rust to re-emit the last N events for a given channel after reconnect (webview reloads).

### 3.3 Channels (first pass, to be frozen at G1)

| Channel | Source layer | Projected? | Notes |
|---|---|---|---|
| `turn/*` | L1 | yes | state transitions, ack phrases, deadlines |
| `memory/hit` | L2 | yes | salient recall notifications to UI |
| `memory/write` | L2 | yes | confirmations only; bodies via query |
| `presence/*` | L3 | yes (low-freq) | visemes on a dedicated high-freq channel |
| `router/decision` | L4 | yes | so trust center / debug overlays can show it |
| `policy/decision` | L5 | yes | approvals, denials, audit hooks |
| `policy/audit` | L5 | yes (summaries) | full audit log via query |
| `persona/compiled` | L6 | yes | hot-reload notifications |
| `media/*` | Media | mixed | only timing-relevant events projected |
| `core/health` | core | yes | reconnect, resource pressure, tier downgrade |

---

## 4. Mapping the 7 layers into the Tauri app

| Layer | Primary home | Crosses the boundary for | UI responsibility |
|---|---|---|---|
| **L1 Interaction timing (+ reflex)** | **Rust.** Turn state machine, reflex classifier, ack pool, timing contracts. | Turn state events; ack phrase strings; deadlines. | Render conversation state; honor ack timing in UI (no independent clock). |
| **L2 Memory kernel** | **Rust.** Ingestion, novelty, retrieval, storage, governance. | Memory hits, write confirmations; query results on demand. | Memory review/edit UI; propose writes via commands. |
| **L3 Presence engine** | **Rust + rendering surface.** Presence controller in Rust; rendering engine (Unreal/custom GL/hybrid — Don's gate) runs out-of-process or in-proc with its own harness. | Presence state, viseme timing. | Avatar canvas; host-side camera/mic widgets; tier-aware fallback UI. |
| **L4 Model router** | **Rust.** Tier abstraction, Gemma 4 routing, fallback chains, BYOK credentials. | Route decisions, tier-change notices. | Router debug/audit overlay; BYOK entry forms (secrets never returned to UI). |
| **L5 Policy / authorization** | **Rust.** Capability model, risk classes, autonomy presets, audit log. | Approval requests, decisions, audit summaries. | Approval dialogs; trust center views; preset pickers. Every UI command that mutates state passes through L5. |
| **L6 Persona compiler** | **Rust core + TS tooling.** Compiler in Rust for hot-reload determinism; authoring/validation helpers may live in TS for onboarding. | Compiled persona handle; hot-reload events. | Persona picker, authoring UI, preview surfaces. |
| **L7 Trust UX + onboarding** | **TS/React.** The user-facing shell. | Calls every other layer's commands; subscribes to audit + state events. | Wizard, trust center, permissions UX, cost visibility, guest mode. Must remain shell-agnostic (no Tauri-only APIs in L7 components — see §10). |

Layers that **straddle**:
- **L3** (Rust state machine + external rendering surface).
- **L6** (Rust compiler + TS authoring tools).
- **Media engine** (not an L-layer but relevant): inference runtimes borrowable, streaming/interrupt logic custom Rust, UI owns only the capture/playback widgets.

---

## 5. Plugin vs core split

### 5.1 Definitions

- **Core** — shipped in every Aether build, required for the product to function, frozen by doctrine. L1–L7 runtime, event bus, policy engine, updater, storage drivers, persona compiler, default model router.
- **Tauri plugin** — a Rust crate exposing additional commands/events behind a capability. Swappable, optional, and **gated by L5** once L5 ships.
- **Webview-side "plugin"** — explicitly **not a thing** in Aether. The UI does not load third-party JS bundles at runtime. All extension happens on the Rust side.

### 5.2 First-party Tauri plugins we will use (candidates, verify against current Tauri v2 docs before G2)

- `tauri-plugin-updater` — signed updater (required; see §6).
- `tauri-plugin-fs` — filesystem access, **scope-locked** at build and runtime (see §7).
- `tauri-plugin-dialog` — native file pickers (read-only surface into fs scope).
- `tauri-plugin-shell` — **default-denied**; only enabled behind an L5 capability.
- `tauri-plugin-os` / `tauri-plugin-process` — read-only metadata used by hardware auto-detection (§8).
- `tauri-plugin-store` — small config store (preferences only; no memory, no secrets).
- `tauri-plugin-window-state` — window layout persistence.
- `tauri-plugin-single-instance` — prevents two desktop instances racing the same SQLite + vector store.
- `tauri-plugin-autostart` — opt-in from onboarding; L5-gated.
- `tauri-plugin-log` — structured logs written to Rust side only.

Explicitly **not** adopted without a second look:
- `tauri-plugin-http` — we prefer our own HTTP client inside L4 so routing/escalation policy is enforced in one place.
- `tauri-plugin-notification` — evaluate after L7 gets its trust-center notification model.

### 5.3 First-party Aether plugins (our own)

Treat these as Rust crates behind the plugin boundary so they can be swapped per tier or per product (Pro vs OSS Preview vs Isabelle overlay):

- `aether-plugin-router-remote` — frontier-LLM adapters. Pro only; OSS Preview uses a simpler adapter set.
- `aether-plugin-media-<runtime>` — adapters for each STT/TTS runtime; the streaming chunk contract is core.
- `aether-plugin-rendering-<surface>` — adapter for each rendering surface (L3 external engine). Exactly one loaded at runtime.
- `aether-plugin-sync-<transport>` — CRDT vs op-log is Don's gate at Phase 5; keep the transport behind a plugin interface until then.

### 5.4 Allowlist policy (to be locked at G2)

- Default-deny on all Tauri v2 capabilities.
- Capabilities declared per-window (the onboarding wizard window has strictly less than the main app window).
- Every capability widening is a **reviewed policy change** — once L5 lands, widening is a capability mutation recorded in the audit log.

---

## 6. Updater channel model + code signing

### 6.1 Channels (from `15_updates_releases.md`)

| Channel | Default audience | Update behavior |
|---|---|---|
| **Stable** | Default for Pro | Recommended-on, non-nagging; critical fixes forced |
| **Beta** | Opt-in | Recommended-on; forced only for beta-critical fixes |
| **Experimental** | Opt-in | Manual only; user-triggered updates |

OSS Preview may expose only Stable initially and **does not share signing material** with Pro (see §9).

### 6.2 Updater flow

1. Client posts `{channel, current_version, platform, arch}` to the update endpoint.
2. Endpoint returns a signed manifest: target version, release notes URL, signature, SHA-256, delta vs full, minimum-supported-version gate, optional "forced" flag (only for critical security / compatibility / trust fixes per doctrine).
3. Tauri updater verifies the signature against a public key embedded in the binary **at build time** (not fetched at runtime).
4. Download → verify signature → verify hash → stage → apply on next launch (or immediately on user confirmation).
5. **Rollback:** failed post-update launch triggers an automatic rollback to the prior version slot. Rollback is deterministic: previous binary + previous DB snapshot tag are retained for N versions.
6. **Trust-affecting updates** (permissions / policy / disclosures) carry a flag that the trust center surfaces before applying.

### 6.3 Code-signing plan (to be locked at G3)

- **Windows (Authenticode)**: EV code-signing cert (OV acceptable for v0 but prolongs SmartScreen reputation warm-up). Hardware token or cloud HSM (Azure Key Vault / DigiCert KeyLocker) required for EV. CI signs release artifacts — developer machines never hold the cert.
- **macOS**: Apple Developer ID + notarization. Entitlements kept minimal (no hardened-runtime exceptions without explicit justification). Defer until macOS becomes a supported target.
- **Linux**: AppImage or tarball with detached GPG signature; deb/rpm later. Defer until Linux is a supported target.
- **Updater key**: separate Ed25519 key used by `tauri-plugin-updater`, independent of Authenticode cert. Public key baked into each build; rotation requires a staged release whose prior version trusts both old and new keys.
- **Secret handling**: no cert material or updater private key enters the repo. CI reads from a secret store (to be named at G3). Local dev uses unsigned builds tagged "not for distribution".
- **WebView2 gating**: installer bootstraps WebView2 Evergreen runtime if absent (Windows 10 1803+). Pro hard-requires it; OSS Preview may ship a more permissive path.

### 6.4 Transition from OSS Preview (Inno Setup + GitHub Releases) to Pro (Tauri updater)

Per `plans/03_content_lock_v1_port.md` §5:
- **Ported forward (OSS Preview only)**: Inno Setup scaffold, install-time model download, WebView2 check, GitHub-Releases update-source pattern.
- **Explicitly retired (Pro)**: Inno Setup installer, custom GitHub-Releases poller. Pro uses Tauri's signed updater end-to-end.
- Shared: the `{channel, version, platform}` query shape, release-notes copy conventions, and the "forced-update" flag semantics.

---

## 7. IPC + filesystem scope defaults

### 7.1 IPC

- **Default-deny** on every Tauri command: allowlist is per-window in `tauri.conf.json` / capabilities.
- **CSP** is strict: no `unsafe-inline`, no `unsafe-eval`; asset URLs whitelisted; hashes for any inline script that cannot be avoided.
- **No remote URL loading into the main window.** Remote content (docs, blog) opens in the OS browser via a narrowly-scoped shell command.
- **No `shell.open` on arbitrary URIs.** L5-gated; default denied.

### 7.2 Filesystem scope (locked at G4)

Default scopes at first launch:

| Scope | Path | Permissions |
|---|---|---|
| `core.config` | `%APPDATA%/Aether/Pro/config/` | read/write |
| `core.data` | `%APPDATA%/Aether/Pro/data/` (SQLite, vector index, audit log) | read/write |
| `core.cache` | `%LOCALAPPDATA%/Aether/Pro/cache/` | read/write |
| `core.models` | user-chosen, default `%LOCALAPPDATA%/Aether/Pro/models/` | read/write |
| `core.logs` | `%APPDATA%/Aether/Pro/logs/` | read/write |
| `user.inbox` | user-picked folder (onboarding) | read only, ask per-file |
| everything else | none | denied by default |

Rules:
- **No global read/write.** `$HOME/**` style scopes are not used.
- **User-picked folders** go through native OS file pickers (`tauri-plugin-dialog`), which produce scoped capabilities recorded by L5 once live.
- **No scope widening via the webview** — widening is a command invoked from an approval dialog, recorded in the audit log.
- **Symlink traversal is blocked** at the Rust side; even if the OS allows it, the plugin rejects paths that escape the granted scope.

---

## 8. Local-first and performance-tier compatibility

### 8.1 Local models, memory, storage

- **Models**: loaded and hosted by the Rust core. Inference adapters are Rust plugins (`aether-plugin-media-*`, `aether-plugin-router-*`). The webview never holds a model handle.
- **Memory kernel**: L2 owns a SQLite database (encrypted at rest) plus a vector index (format TBD; kept behind an L2 interface so swap is cheap). All IO is async on the Rust side; the UI never blocks on memory queries.
- **Storage**: single Rust process owns all DB handles. `tauri-plugin-single-instance` guarantees no second app races the DB.
- **Network**: optional, always gated by L5 once live. Default-offline — the product boots, onboards, and chats locally without any network round-trip (doctrine §6).

### 8.2 Keeping the UI responsive under load

- **No blocking IPC.** Every command that can take >50 ms returns a `ChangeId` and follows up via events. The UI shows pending state, not a frozen frame.
- **Tier-aware UI.** UI reads `core.health` tier notifications and demotes effects (animations, high-freq presence updates, viseme channel frame rate) without requiring a reload.
- **Backpressure on the event bridge.** Viseme and presence channels coalesce in Rust before crossing to the webview on Lite tier.
- **Hard webview budgets.** Main thread work per frame capped; any layout beyond budget triggers a tier-warning in trust center, not silent jank.

### 8.3 Performance tiers

| Tier | Model loadout | Webview effects | Event bridge |
|---|---|---|---|
| **Lite** | Smallest Gemma 4; remote assist favored | Minimal animation; 2D avatar; no high-freq presence channel | Coalesced events; 10–15 fps presence max |
| **Balanced** | Mid Gemma 4; mixed local/remote | Standard effects; gaze/blink; 30 fps presence | Full low-freq projection; throttled high-freq |
| **Full** | Largest Gemma 4 tier-appropriate variant; local preferred | Full effects; anti-uncanny stabilizer; 60 fps presence | Full projection; dedicated viseme channel |

Tier is detected at onboarding (L7) and runtime-adjusted under VRAM pressure; the webview must accept downgrades during a session without a reload.

---

## 9. Cross-product reuse — OSS Preview shares the foundation (except where it doesn't)

### 9.1 Shared

- React/TS component library and design tokens (shell-agnostic).
- Command + event shape conventions (even when OSS Preview's underlying transport is pywebview's JSON bridge rather than Tauri's IPC — see 9.3).
- Policy engine interface (OSS Preview may ship a simpler default preset, but the interface is identical).
- Memory kernel schema (subset).
- Persona compiler I/O format.

### 9.2 Intentionally different

- **OSS Preview uses Inno Setup + GitHub-Releases poller** (tactical shortcut), not the signed Tauri updater.
- **OSS Preview may run on pywebview** if speed-to-demo requires it. This is explicitly non-doctrinal and scoped to OSS Preview only.
- **OSS Preview does not share signing material** with Pro. Separate keys; separate update endpoints.
- **OSS Preview may lack** the full L5 capability surface, the Pro trust center, Isabelle overlay, and remote router adapters.

### 9.3 pywebview → Tauri transition plan (L7 coordination)

- L7 React components must stay **shell-agnostic**: no `@tauri-apps/api` imports inside presentational components; all IPC goes through a thin **shell adapter** (`packages/shell-adapter` — X1-dependent) with two implementations: `shell-adapter-tauri` and `shell-adapter-pywebview`.
- Commands and events are defined in **one place** (the generated TS client from Rust command definitions). pywebview exposes the same shape via its JSON bridge for the features OSS Preview supports.
- **Cutover signal**: when OSS Preview's Tauri build passes L7's onboarding happy path + trust-center smoke tests on Windows with WebView2 bootstrap working, the pywebview build is retired. Target: end of Pro Phase 0 / start of Phase 1, subject to X1.

---

## 10. Extensibility — adding tools, models, and surfaces without breaking boundaries

- **New tool (browser/file/email/etc.)**: add a capability to the L5 taxonomy; add a Rust plugin implementing the tool; expose typed commands and events; surface in trust center. UI picks up the new capability through L5's capability-listing command — no webview-only changes.
- **New model (local or remote)**: add a Rust adapter behind `aether-plugin-router-*`; register it with the tier abstraction; L4 routes to it based on privacy/cost/latency. UI sees it through router debug/preview commands. No webview change required beyond listing.
- **New rendering surface** (e.g. Unreal-class instead of custom GL): implement a new `aether-plugin-rendering-*`; swap at build or runtime (exactly one active). L3 presence controller stays unchanged because the rendering-surface interface is the seam.
- **New persona / persona-pack format evolution**: L6 compiler versions the format; hot-reload events carry a version field; the UI gracefully handles unknown fields (ignore + warn).
- **New webview window** (e.g. a dedicated trust center or onboarding window): declared in `tauri.conf.json` with its own capability list — *always smaller* than the main window's.

Non-goals for extensibility:
- **No third-party webview JS bundles loaded at runtime.** Extensibility is a Rust-side concern.
- **No user-authored Rust plugins loaded at runtime** in Pro v1. Revisit post-Phase 4 once L5 has matured a signed-plugin story.

---

## 11. Dependency inventory (candidates — verify against current Tauri v2 docs before adoption)

**Build/runtime**
- `tauri` v2 (Rust + JS bindings)
- `tauri-build` v2
- `serde` / `serde_json` (command payloads)
- `ts-rs` or `specta` (Rust → TS type generation — pick one at G1)
- `tokio` (async runtime; Tauri-compatible)
- `tracing` / `tracing-subscriber` (structured logs)
- `thiserror` / `anyhow` (error vocabulary)

**Tauri v2 plugins (candidates from §5.2)**
- `tauri-plugin-updater`, `tauri-plugin-fs`, `tauri-plugin-dialog`, `tauri-plugin-shell` (default-denied), `tauri-plugin-os`, `tauri-plugin-process`, `tauri-plugin-store`, `tauri-plugin-window-state`, `tauri-plugin-single-instance`, `tauri-plugin-autostart`, `tauri-plugin-log`

**Storage**
- `rusqlite` or `sqlx` (pick at L2 contract freeze)
- SQLCipher or libsql-crypto (encryption at rest)
- Vector index: `hnswlib-rs` / `usearch` / custom — L2 decides

**UI**
- React (version per L7)
- Vite (bundler)
- `@tauri-apps/api` consumed **only inside `shell-adapter-tauri`** (not in components)

**Out of scope for X3 to pick**: UI state library, styling system, component library — L7's call.

---

## 12. Proposed repo location (X1-dependent — mark as assumption)

Assuming the X1 monorepo adopts a standard `apps/` + `packages/` + `crates/` layout:

```
/apps
  /aether-pro-desktop        # the Tauri app shell (bin)
  /aether-oss-preview        # OSS Preview shell (Tauri; pywebview tactical variant lives here)
/crates
  /core                      # L1..L6 runtime, event bus, policy engine
  /ipc                       # typed commands + events (source of truth)
  /updater                   # updater integration + channel routing
  /plugin-router-remote
  /plugin-media-<runtime>
  /plugin-rendering-<surface>
  /plugin-sync-<transport>
/packages
  /ui                        # React component library (shell-agnostic)
  /shell-adapter             # interface crate (TS)
  /shell-adapter-tauri
  /shell-adapter-pywebview   # OSS Preview only
/planning                    # moved from aether-planning/
/research                    # moved from aether-planning/inbox*/archive
```

This is a **recommendation only**; X1 owns the final layout. When `plans/X1_repo_restructure.md` lands, this section must be reconciled in a follow-up commit.

---

## 13. Security posture summary

- **Default-deny** IPC, filesystem, shell, network.
- **Strict CSP**; no `unsafe-inline`/`unsafe-eval`; no remote content in the main window.
- **All widening is a policy event** once L5 ships.
- **All secrets in OS keyring** (BYOK model keys, updater private key on CI, code-signing cert material on CI / HSM). Never in repo, never in the webview.
- **Supply-chain discipline**: pin Tauri + plugin versions; `cargo deny` / `cargo audit` in CI before release.
- **WebView2 version gate**: below a pinned floor → updater refuses to apply the new version and guides the user to update WebView2 runtime.

---

## 14. Acceptance (what "X3 first-action deliverable done" means)

- [x] Rust↔TS boundary principle + illustrative command surface drafted (§2)
- [x] Event-bus bridge pattern drafted (§3)
- [x] 7-layer mapping drafted (§4)
- [x] Plugin vs core split drafted (§5)
- [x] Updater channel model + signing plan drafted (§6)
- [x] IPC + filesystem scope defaults drafted (§7)
- [x] Local-first runtime + tier compatibility drafted (§8)
- [x] OSS-Preview-pywebview → Pro-Tauri transition plan drafted (§9)
- [x] Extensibility story drafted (§10)
- [x] Dependency inventory drafted (§11)
- [x] Proposed repo location drafted (X1-dependent, §12)
- [x] **G1** Rust↔TS boundary — APPROVED 2026-04-18 (Don)
- [ ] **G2** Plugin vs core allowlist — PENDING REVIEW
- [ ] **G3** Updater channel model + signing path — PENDING REVIEW
- [ ] **G4** IPC + filesystem scope defaults — PENDING REVIEW

G1 status: APPROVED 2026-04-18 (Don) — Rust owns truth; webview is a view, not a worker; every Rust-exposed operation is a typed command; every system-affecting command is a capability; events are append-only (§2 principles ratified). Section 2.2 command surface and §3 event-bus bridge pattern are the working baseline for implementation; refinements land via follow-up revision, not new gates.

G2–G4 remain pending; no project scaffolded. Awaiting Don's approval on G2–G4.

---

## 15. Open questions (surfaced, not decided)

1. **Rust↔TS type-generator**: `ts-rs` vs `specta` vs in-house. Decision impacts every command; needs to be locked at G1.
2. **Rendering surface**: Unreal-class / custom GL / hybrid (Don's gate). Affects the `aether-plugin-rendering-*` interface shape and process model (in-proc vs out-of-proc).
3. **Sync transport** (CRDT vs op-log — Don's gate, Phase 5). Affects `aether-plugin-sync-*` interface and whether sync events are first-class on the event bus.
4. **Code-signing cert class** (EV vs OV) and HSM provider (Azure Key Vault / DigiCert KeyLocker / other). Affects CI topology and cost.
5. **Linux and macOS target timing** — defer now, but the updater + signing design must not lock us out.
6. **Second webview window** for onboarding vs single-window multi-route React app. L7's call; capability list diverges either way.
7. **BYOK secret storage**: OS keyring (`keyring-rs`) vs encrypted in `core.config`. L4/L5 coordination needed.
8. **Audit-log storage format** (L5's canonical artifact) — will determine whether updater-applied migrations touch it.
9. **Fate of the user memory note `feedback_css_default_for_ui.md`** (references pywebview as canonical). Doctrine lock already reconciles it; Don decides whether to rewrite the memory entry itself.
10. **OSS-Preview-only Tauri build**: do we ship OSS Preview on Tauri from day one (retiring pywebview earlier) or keep pywebview until Pro Phase 1? L7 + X4 coordination.

---

## 16. How this plan reports back

Per the X3 briefing, each unit returns:
- **What changed.**
- **Which gate advanced (G1 / G2 / G3 / G4).**
- **Open questions surfaced.**
- **What's next.**

Target end-state (working toward):
- A running Tauri shell with a typed Rust↔TS command surface and stubs for every L1–L7 event.
- Signed updater proven end-to-end on a test channel (v0.0.1 → v0.0.2 signed update).
- IPC + filesystem scope tight by default; every widening a recorded policy decision.
- Documented handoff for OSS Preview's pywebview → Pro Tauri transition so L7 knows when the shortcut ends.
