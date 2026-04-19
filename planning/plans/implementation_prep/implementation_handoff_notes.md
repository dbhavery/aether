# Implementation Handoff Notes

> **Document:** file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/implementation_handoff_notes.md
> **Status:** Planning → Implementation handoff surface
> **Owner:** Don (coordinator) — engineers and coding agents consume this
> **Date of handoff:** 2026-04-18

---

## 1. Purpose

This document tells engineers and coding agents what is implementation-ready, what is not, and in what order to proceed. It is the primary handoff surface between the planning phase (7 layer system designs + X1/X3 cross-layer artifacts) and the implementation phase (monorepo, packages, apps). It is the single entry point: every other artifact (interface packs, event contracts master, SQLite schema pack, test matrix master, integration notes, OPEN_QUESTIONS) is referenced from here. Engineers should read this file first, then drill into the referenced artifacts for their work stream.

---

## 2. What Is Implementation-Ready Now

Concrete items available today. Grouped by work stream. Each bullet lists the authoritative source artifacts.

### 2.1 L5 — Policy Engine (chokepoint; gates everything downstream)

- `PolicyEngine` trait + `Decision` / `DenyReason` / `ApprovalMode` / `GrantDuration` / `Capability` enums.
- 9 policy events (grant lifecycle, approval flow, audit).
- 13 IPC commands (minus the 2 flagged as BLOCKS in §3).
- `grant_ledger` + `audit_log` DDL with append-only triggers and hash-chain pattern.
- Sources:
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L5_interface_pack.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/sqlite_schema_pack.md

### 2.2 L1 — Interaction / Timing Engine

- `InteractionEngine` + 5 adapter traits (reflex classifier, STT, TTS, model router client, presence client).
- 19-state `TurnState` enum.
- 14 interaction events.
- Reflex classifier pseudocode.
- 12 timing sub-budgets (defaults flagged DELAYS in §3).
- Sources:
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L1_interface_pack.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md

### 2.3 L4 — Model Router

- `ModelRouter` + `ProviderAdapter` traits.
- 7-tier abstraction (reflex → frontier).
- `ToolCall` / `ToolResult` / `ToolError` types.
- 10 router events.
- 12 IPC commands.
- Sources:
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L4_interface_pack.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/L4_model_router_system_design.md

### 2.4 L7 — Trust UX + Onboarding

- `ShellAdapter` interface + 2 implementations (Tauri primary, pywebview secondary).
- 13 UI components.
- 8-screen onboarding wizard.
- `approval_response` payload contract.
- Sources:
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L7_interface_pack.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/L7_trust_ux_onboarding_system_design.md

### 2.5 L2 — Memory Kernel

- `MemoryKernel` + `EmbeddingStore` traits.
- `MemoryItem` struct.
- 6 memory domains.
- 11 memory events.
- 11 IPC commands.
- SQLite DDL for memory tables.
- Sources:
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L2_interface_pack.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_memory_kernel_system_design.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/sqlite_schema_pack.md

### 2.6 L3 — Presence Engine

- `PresenceEngine` + `RenderingSurface` traits.
- 9 `BehaviorClass` variants.
- `BehaviorFrame` struct.
- Tier matrix (Lite / Balanced / Pro).
- Sources:
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L3_interface_pack.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/L3_presence_engine_system_design.md

### 2.7 L6 — Persona Compiler

- `PersonaCompiler` trait.
- `PersonaPack` schema.
- 6 `Compiled*` artifacts (prompts, routing rules, behavior map, memory hints, tool allow-list, voice config).
- Hot-reload state machine.
- 6 persona events.
- 9 IPC commands.
- `persona_profiles` + `compiled_persona_artifacts` DDL.
- Sources:
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L6_interface_pack.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/L6_persona_compiler_system_design.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/sqlite_schema_pack.md

### 2.8 Event Bus (cross-layer)

- 74-event catalog with typed payloads.
- Versioning rules.
- 14 cross-layer invariants.
- Ready to scaffold as `packages/event-bus`.
- Source: file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/event_contracts_master.md

### 2.9 Storage Layer (cross-layer)

- 18 SQLite tables.
- 5 append-only tables with triggers.
- Hash-chain audit pattern.
- HMAC design (key in OS keyring).
- Retention engine design.
- Encryption approach (SQLCipher whole-DB or per-column — see DELAYS in §3).
- Ready to scaffold as `packages/storage`.
- Source: file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/sqlite_schema_pack.md

### 2.10 Test Harness (cross-layer)

- Contract-test recommendations (per-layer).
- Property tests.
- Red-team matrix (10 scenarios).
- Performance targets.
- Replay tests.
- Source: file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/test_matrix_master.md

---

## 3. What Is NOT Implementation-Ready

Grouped by severity. BLOCKS cannot be coded around. DELAYS will cause rework if we pick wrong. DEFERS are intentionally gated to later phases.

### 3.1 BLOCKS (implementation cannot begin on the affected surfaces)

| # | Item | Affected layers | Why blocking |
|---|------|-----------------|--------------|
| B1 | `NeedsUpgrade` decision encoding | L5 / L1 / L7 | Decision enum shape drives every downstream branch and UI flow |
| B2 | Draft-only approval encoding (`AllowDraft`) | L5 / L7 | Changes approval response payload and component state machine |
| B3 | Missing IPC commands: `policy.export_audit`, `policy.set_cost_cap` | L5 / L7 | L7 Trust Center and BYOK vault both call these |
| B4 | Per-step policy re-evaluation rule (single grant vs per-tool-call) | L4 / L5 | Tool-orchestration loop structurally different between the two |
| B5 | BYOK cost-cap re-arm flow | L4 / L5 / L7 | Determines whether cap is sticky, session-scoped, or user-re-armed |

**Action:** Don's answers on B1–B5 are prerequisites to freezing the L5 IPC surface.

### 3.2 DELAYS (can start; will rework if wrong)

- L1 sub-budget default millisecond values.
- Persona-swap safe-boundary strictness.
- Privacy-posture waiver scope.
- Vector-store vendor selection (L2) — can defer behind `EmbeddingStore` trait.
- Embedding model per tier (L2).
- Anti-uncanny behavior on Lite tier (L3).
- `AssistantStateMemory` domain status (L2) — in-scope or deferred.
- Privileged-overlay path mechanism (L6).
- Observed-style confirmation UI (L6 / L7).
- `presence.set_mode` — production exposure vs debug-only (L3).
- Encryption scheme — SQLCipher whole-DB vs per-column.

### 3.3 DEFERS (intentionally gated; not required now)

- Rendering-surface choice — Pro Phase 2 (see file:///C:/Users/dbhav/Projects/aether-planning/plans/00_ORCHESTRATION_MAP.md §9).
- Sync architecture — CRDT vs op-log — Pro Phase 5 (orchestration map §9).
- Mobile stack — open.
- Hosted frontier-LLM acceptable-use rules — open.

All items above live in:
- file:///C:/Users/dbhav/Projects/aether-planning/OPEN_QUESTIONS.md

---

## 4. Recommended Implementation Order

Proposed sequence. This is a working proposal; Don ratifies before work starts.

| # | Step | Rationale | Suggested owner | Rough size |
|---|------|-----------|-----------------|-----------|
| 1 | **X1 Wave 0** — monorepo genesis | Unblocks every package | Coordinator + X1 | ~1 session |
| 2 | **packages/event-bus + packages/types** | Typed Rust event bus + ts-rs bindings harness. Every layer's adapter depends on this | Core infra | ~2–3 sessions |
| 3 | **packages/storage + SQLite schema** | Connection management, migration runner, append-only triggers, HMAC scaffold. Single-writer plumbing | Core infra | ~2 sessions |
| 4 | **packages/l5-policy** | Grants + audit + evaluator + IPC. Chokepoint must exist before other layers stub safely. Resolve B1–B5 before freezing IPC surface | Policy owner | ~3–4 sessions |
| 5 | **packages/l6-persona** | Schema + loader + compiler + hot-reload. L1/L2/L3/L4/L5/L7 all consume compiled artifacts | Persona owner | ~3 sessions |
| 6 | **packages/l1-timing** | State machine + reflex adapter stubs + timing harness. Parallelizable with L6 | L1 owner | ~3 sessions |
| 7 | **packages/l4-router** | Tier abstraction + tool orchestrator + provider plugin trait + BYOK vault. Parallelizable with L1 once L5/L6 adapter stubs land | L4 owner | ~3 sessions |
| 8 | **packages/l2-memory** | SQLite + vector-store trait + ingestion + retrieval. Vendor choice deferred behind trait | L2 owner | ~3 sessions |
| 9 | **packages/l3-presence + packages/l3-avatar-ui** | Behavior scheduler + reference headshot plugin. Rendering-surface choice deferred | L3 owner | ~3 sessions |
| 10 | **packages/shell-adapter + packages/l7-onboarding + packages/l7-trust-center + packages/ui-kit** | L7 components + shell-adapter-tauri first, pywebview later | L7 owner | ~4–5 sessions |
| 11 | **apps/desktop (Tauri shell)** | Composes packages; single-instance plugin, filesystem scopes, IPC wiring | App owner | ~2 sessions |
| 12 | **Contract-test harness + red-team scenarios** | Cross-layer. Runs on every PR | Test owner | ~2 sessions |
| 13 | **OSS Preview build flag + Pro flag divergence** | Per X3 §9 | App owner | ~1 session |

**Total step count:** 13.

---

## 5. Suggested Crate / Package Starting Points

Reference: file:///C:/Users/dbhav/Projects/aether-planning/planning/monorepo_plan_draft.md §2.

| Package | Language | Primary deliverable | Ready to scaffold? | Prerequisites |
|---|---|---|---|---|
| packages/types | Rust + ts-rs | Shared type definitions, ts-rs bindings | Yes | — |
| packages/event-bus | Rust | Typed event bus, versioning | Yes | packages/types |
| packages/storage | Rust | SQLite connection, migrations, append-only triggers, HMAC scaffold | Yes | packages/types |
| packages/l5-policy | Rust | PolicyEngine + grant ledger + audit log + IPC | **Partial** (needs B1–B5) | event-bus, storage |
| packages/l6-persona | Rust | PersonaCompiler + schema + hot-reload | Yes | event-bus, storage, l5-policy |
| packages/l1-timing | Rust | InteractionEngine + TurnState machine + adapters | Yes | event-bus, l5-policy, l6-persona |
| packages/l4-router | Rust | ModelRouter + ProviderAdapter + tool orchestrator + BYOK | **Partial** (needs B4, B5) | event-bus, l5-policy, l6-persona |
| packages/l2-memory | Rust | MemoryKernel + EmbeddingStore trait + ingestion/retrieval | Yes | event-bus, storage, l5-policy |
| packages/l3-presence | Rust | PresenceEngine + scheduler | Yes | event-bus, l1-timing, l6-persona |
| packages/l3-avatar-ui | TS | Reference headshot plugin + RenderingSurface impl | Yes | l3-presence, shell-adapter |
| packages/shell-adapter | TS | ShellAdapter interface + Tauri impl | Yes | packages/types bindings |
| packages/shell-adapter-pywebview | TS / Python | pywebview impl | Deferred | shell-adapter |
| packages/ui-kit | TS | Shared components, tokens | Yes | — |
| packages/l7-onboarding | TS | 8-screen wizard | **Partial** (needs B1–B3) | ui-kit, shell-adapter, l5-policy bindings |
| packages/l7-trust-center | TS | 13 components incl. grant center, audit export, BYOK | **Partial** (needs B3) | ui-kit, shell-adapter, l5-policy bindings |
| apps/desktop | Rust + TS | Tauri shell composing all packages | No | all packages above |

---

## 6. Risks to Watch

Named list with mitigations. Engineers should treat these as live hazards throughout implementation.

| # | Risk | Mitigation |
|---|------|-----------|
| R1 | **Boundary bypass** — a tool path routed without an L5 gate | Compile-time proof-of-allow token pattern (L4); `tools/lint-policy-bypass` CI lint |
| R2 | **Schema drift** — L5/L2/L6 schemas evolve out of sync | `schema_versions` table + migration runner in packages/storage; shared DDL in one place |
| R3 | **Event version drift** — Rust and TS bindings diverge | ts-rs regenerated on every Rust struct change; CI check |
| R4 | **UI diverging from policy truth** — L7 displays stale grant state | Invariant I3 from integration notes; L7 never caches grant decisions; subscribes to `grant_issued` / `grant_revoked` |
| R5 | **Memory overreach** — L2 surfaces content to wrong posture | `privacy_class` on every `MemoryHit`; L4 + L5 enforce on downstream routing |
| R6 | **Uncanny behavior from presence timing mismatch** — L3 viseme drift, anti-uncanny disabled | L3 §10 resync rule; anti-uncanny ON at Balanced+; perceptual red-team scenarios |
| R7 | **Audit-log tamper** — hash-chain/HMAC broken | Append-only triggers; periodic `integrity_check` + checkpoints; HMAC key in OS keyring |
| R8 | **BYOK leak** — secret material in Rust logs or UI state | OS keyring exclusively; `captureSecret` shell-adapter pattern; grep-forbidden lint |
| R9 | **Isabelle asset leak into public distributable** — private overlay accidentally packaged | Build-time `lint-private-asset-leak`; separate overlay path outside repo |

**Total risk count:** 9.

---

## 7. Coordination Pattern for Implementation

- Don remains the coordinator.
- Agents and engineers work from interface packs (per-layer) plus briefing prompts (per-task).
- When an agent proposes a new package, a new cross-layer event, or a new cross-layer dependency, it **files a proposal and does not unilaterally create**. Per file:///C:/Users/dbhav/Projects/aether-planning/planning/monorepo_plan_draft.md §4.2.
- One module per session (cross-project rule; see file:///C:/Users/dbhav/Projects/CLAUDE.md).
- Commits and pushes happen after every meaningful change, not at session end.
- Session logs document what actually happened — decisions, deviations, surprises.

---

## 8. Open-Question Tracking

All outstanding decisions live in:

- file:///C:/Users/dbhav/Projects/aether-planning/OPEN_QUESTIONS.md

This handoff document points back. It does not duplicate. When a question is resolved, update OPEN_QUESTIONS.md and note the resolution in the next session log. Do not update this handoff doc for normal question churn — only when the implementation-order or risk picture shifts materially.

---

## 9. What "Ready to Build" Means for This Project

A surface is **ready to build** when all 5 of the following hold:

1. **Interface pack exists** for the layer (or a cross-layer artifact is explicitly scoped).
2. **Event contracts** for the surface's inbound and outbound events exist in file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/event_contracts_master.md.
3. **Persistence** (if any) exists in file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/sqlite_schema_pack.md.
4. **Tests** for the surface exist in file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/test_matrix_master.md.
5. **No BLOCKS-severity open questions** are outstanding on the surface being built.

Decision rule:

- If all 5 hold → **begin**.
- If 1–4 hold but a BLOCKS open question touches the surface → **wait for Don**.
- If 1–4 hold and only DELAYS apply → begin, but flag the delay-sensitive code paths so rework is scoped.
- If a DEFER applies → do not build; wait for the gating phase.

---

## 10. Primary Artifact Index

Entry points for every implementer:

- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L1_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L2_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L3_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L4_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L5_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L6_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L7_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/event_contracts_master.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/sqlite_schema_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/test_matrix_master.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_L4_L5_L7_integration_notes.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_L3_L6_integration_notes.md
- file:///C:/Users/dbhav/Projects/aether-planning/planning/monorepo_plan_draft.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/X3_tauri_architecture.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/00_ORCHESTRATION_MAP.md
- file:///C:/Users/dbhav/Projects/aether-planning/OPEN_QUESTIONS.md

---

**End of handoff notes.**
