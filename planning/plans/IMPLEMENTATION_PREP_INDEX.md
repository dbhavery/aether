# Implementation-Prep Index

> **Session:** 2026-04-18 system-design → implementation handoff
> **Owner:** Donald Havery
> **Status at write-time:** All 11 planned artifacts produced. No code scaffolded. No migrations run. No CI wired.

---

## 1. Purpose

This document is the entry point for the implementation-prep artifacts produced during the 2026-04-18 system-design-to-implementation session. Anyone picking up implementation work on Aether — whether starting a new crate, scaffolding the Tauri shell, wiring SQLite migrations, or drafting a layer's test harness — **starts here**. The index catalogues every output of the session, records per-layer readiness, consolidates the blocking open questions that Don must resolve before certain interfaces can freeze, and points at the correct reading order so that an implementer does not have to re-derive context from the 1000-line system-design documents.

---

## 2. Session scope

**Produced this session (11 artifacts):**

- Seven interface packs, one per architectural layer (L1 through L7). Each pack contains the layer's Rust trait surface, event shapes it emits and consumes, error vocabulary, persistence touchpoints, and three flagged open questions.
- One master event-contracts pack consolidating 74 events across 14 invariants, acting as the single source of truth for event names, payload shapes, producer/consumer routing, and versioning rules.
- One draft SQLite schema pack covering 18 tables (5 of them append-only), including DDL, indices, retention rules, and cross-layer ownership.
- One master test matrix: 8 per-layer unit/contract tests per layer, 8 end-to-end scenarios, 10 red-team attack scenarios.
- One implementation handoff notes document (written in parallel with this index) that narrates how the pieces fit together for an implementer starting cold.

**Explicitly NOT produced this session (do not assume these exist):**

- No scaffolded code in any language.
- No real Rust crates, no `Cargo.toml` files, no workspace layout committed.
- No real SQL migrations, no `sqlx` or `sea-orm` wiring, no embedded schema files.
- No CI configuration, no GitHub Actions, no pre-commit hooks.
- No UI components, no Tauri shell bootstrapping, no pywebview parity work.
- No BYOK credential-store implementation, no keyring integration.
- No vector-store vendor selection or embedding-model selection (open question in L2).

---

## 3. Artifact catalog

| Artifact | Path | Purpose | Primary audience | Line count |
|---|---|---|---|---|
| L1 interface pack | file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L1_interface_pack.md | Interaction-timing layer: turn state machine, barge-in, persona-swap at safe boundary, NeedsUpgrade handler surface | Implementer owning L1 crate | 520 |
| L2 interface pack | file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L2_interface_pack.md | Memory kernel: episodic, semantic, assistant-state stores; retrieval trait surface; memory events | Implementer owning L2 crate | 251 |
| L3 interface pack | file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L3_interface_pack.md | Presence engine: rendering-surface gate, anti-uncanny on Lite, presence.set_mode trait | Implementer owning L3 crate | 253 |
| L4 interface pack | file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L4_interface_pack.md | Model router: per-step re-eval, cost-cap re-arm, speculative payload policy, BYOK meta surface | Implementer owning L4 crate | 334 |
| L5 interface pack | file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L5_interface_pack.md | Policy engine: grants, audit log, cost counters, NeedsUpgrade encoding, AllowDraft | Implementer owning L5 crate (ready to begin) | 585 |
| L6 interface pack | file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L6_interface_pack.md | Persona compiler: safe-boundary strictness, tier_preference terminology, signing scheme, privileged-overlay path | Implementer owning L6 crate | 344 |
| L7 interface pack | file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L7_interface_pack.md | Trust/UX/onboarding: Draft-only encoding, export_audit + set_cost_cap commands, shell-adapter pywebview parity | Implementer owning L7 crate + Tauri shell | 537 |
| Event contracts master | file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/event_contracts_master.md | Canonical registry of all 74 events, 14 invariants, producer/consumer routing, versioning | All implementers; event-bus owner | 1258 |
| SQLite schema pack | file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/sqlite_schema_pack.md | 18-table draft schema (5 append-only), DDL, indices, retention rules, cross-layer ownership | Persistence owner; DBA-equivalent | 679 |
| Test matrix master | file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/test_matrix_master.md | 8 per-layer tests, 8 E2E scenarios, 10 red-team attacks | QA / test-harness owner | 314 |
| Implementation handoff notes | file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/implementation_handoff_notes.md | Narrative handoff for an implementer starting cold | Any implementer | (parallel write; assumed present) |

---

## 4. Readiness table

| Layer | Interface pack | Schema pack | Test matrix | Status | Notes |
|---|---|---|---|---|---|
| **L5** Policy Engine | Ready | Ready (`policy_grants`, `policy_audit_log`, `cost_counters`) | Ready | **ready** | Blocked only by three documented open questions: NeedsUpgrade encoding, AllowDraft semantics, missing commands. All flagged in the pack; do not block scaffolding. |
| **L1** Interaction Timing | Ready | No direct ownership (uses L5's grants + cost counters) | Ready | **partially ready** | Open: sub-budget defaults need Don lock; persona-swap strictness (Strict vs Relaxed at safe boundary); NeedsUpgrade handler wiring. |
| **L4** Model Router | Ready | Ready (`routing_decisions`, `byok_credentials_meta`; shares `cost_counters` with L5) | Ready | **partially ready** | Open: per-step re-eval rule; speculative payload policy; cost-cap re-arm semantics. |
| **L7** Trust/UX/Onboarding | Ready | No direct ownership (reads from L5, L2, L6) | Ready | **partially ready** | Open: Draft-only encoding; `export_audit` + `set_cost_cap` commands; guest-mode infra deferral; shell-adapter pywebview parity. |
| **L2** Memory Kernel | Ready | Ready (`memory_*` tables) | Ready | **partially ready** | Open: vector-store vendor selection; embedding model per tier; AssistantStateMemory domain status. |
| **L3** Presence Engine | Ready | No direct ownership | Ready | **partially ready** | Open: rendering-surface gate deferred per orchestration map §9 (Don's gate at Pro Phase 2); anti-uncanny on Lite; `presence.set_mode` shape. |
| **L6** Persona Compiler | Ready | Ready (`persona_profiles`, `compiled_persona_artifacts`) | Ready | **partially ready** | Open: safe-boundary strictness; tier_preference terminology; signing scheme; privileged-overlay path; observed-style confirmation UI. |

---

## 5. Blocking-open-question summary

Consolidated from each interface pack's §10. Grouped by owning layer. "Blocks" = which portion of that layer's interface cannot be frozen until Don resolves.

| # | Layer | Question | Why it blocks | Proposed default |
|---|---|---|---|---|
| 1 | L5 | How is `NeedsUpgrade` encoded on the grant-decision envelope — distinct variant or flag on `Denied`? | Changes the Rust enum shape that L1/L4/L7 all match on | Distinct variant `Decision::NeedsUpgrade { required_tier, reason }` |
| 2 | L5 | What are the semantics of `AllowDraft` — draft-only output, watermark, or ephemeral? | Changes what L7 renders and what L2 persists | Draft-only, non-persisted, watermarked in UI |
| 3 | L5 | Which grant-management commands are missing from the trait (revoke, list, cap-adjust)? | Trait surface not yet complete for admin flows | Add `revoke_grant`, `list_grants`, `adjust_cost_cap` |
| 4 | L1 | Sub-budget defaults for each turn phase (deliberation, tool-use, render) | L1 cannot allocate budget or detect overrun without numbers | None — Don must lock |
| 5 | L1 | Persona-swap strictness at safe boundary — `Strict` (hard wait) or `Relaxed` (interruptible) | Determines whether hot-swap can pre-empt a Speaking state | `Strict` by default, `Relaxed` opt-in per swap |
| 6 | L1 | `NeedsUpgrade` handler wiring — does L1 render the upgrade prompt or delegate to L7? | Affects whether L1 holds UI state or is purely a controller | Delegate to L7 via event |
| 7 | L4 | Per-step re-evaluation rule — re-route mid-turn if cost-cap nears, or commit at turn start? | Changes router determinism and cost-attribution | Commit at turn start; cost-cap triggers abort not reroute |
| 8 | L4 | Speculative payload policy — cache speculative responses or discard on cancel? | Affects cost-counter accuracy and privacy surface | Discard on cancel; do not persist speculative payloads |
| 9 | L4 | Cost-cap re-arm semantics — when does a tripped cap reset (per day, per session, manual)? | Determines counter-reset trigger and grant re-issuance | Per-day UTC rollover; manual reset via L7 command |
| 10 | L7 | Draft-only encoding in UI — visual watermark, distinct surface, or both? | Affects render pipeline and user trust signalling | Both: distinct surface + watermark |
| 11 | L7 | `export_audit` command — full history, date-ranged, or filtered? | Changes command surface and L5 query pattern | Date-ranged, filterable by layer/event-type |
| 12 | L7 | `set_cost_cap` command — who can invoke, at what scope (session/persona/global)? | Affects L5 grant-issuance flow | Global only; gated behind Trust tier "Elevated" |
| 13 | L7 | Guest-mode infra deferral — where does guest state live, and when is it purged? | Blocks onboarding flow for non-logged-in use | Defer guest-mode to post-MVP; MVP requires local profile |
| 14 | L7 | Shell-adapter pywebview parity — does Tauri shell need to match pywebview surface exactly? | Determines whether shell-adapter trait is portable | Minimal shared surface; Tauri-native for MVP |
| 15 | L2 | Vector-store vendor — embedded (sqlite-vec, LanceDB) or external (Qdrant, Chroma)? | Blocks persistence crate selection and schema finalisation | sqlite-vec (keeps single-file invariant) |
| 16 | L2 | Embedding model per tier — which model for Lite, Standard, Pro? | Blocks retrieval code path and cost-counter calibration | Lite: `bge-small`; Std: `bge-base`; Pro: OpenAI `text-embedding-3-small` |
| 17 | L2 | AssistantStateMemory domain status — is this a real memory domain or a runtime cache? | Changes whether it hits SQLite or stays in-process | Runtime cache; persist snapshot on session-end only |
| 18 | L3 | Rendering-surface gate — when is the Pro-tier gate opened (Phase 1 or Phase 2)? | Deferred per orchestration map §9 — Don's gate. Blocks L3 Pro-tier code paths. | Phase 2 (per orchestration map §9) |
| 19 | L3 | Anti-uncanny behaviour on Lite — full suppress, degraded, or identical to Std? | Changes L3 output surface for cheapest tier | Degraded (reduced motion/micro-expressions) |
| 20 | L3 | `presence.set_mode` event payload — enum of modes or freeform config struct? | Changes event contract and L3 trait | Enum of named modes; no freeform config |
| 21 | L6 | Safe-boundary strictness for persona hot-swap — mirror L1's choice or independent? | Determines whether L6 can accept a swap that L1 would reject | Mirror L1 |
| 22 | L6 | `tier_preference` terminology — `preferred`, `required`, or `minimum`? | User-facing and API-surface wording | `minimum` (semantic: "at least this tier") |
| 23 | L6 | Persona-artifact signing scheme — Ed25519, HMAC, or unsigned in MVP? | Blocks persona-integrity invariant | Ed25519 with local keypair per install |
| 24 | L6 | Privileged-overlay path — filesystem location + permission model for privileged personas | Blocks L6 loader and L5 grant-check for overlays | `%LOCALAPPDATA%/Aether/personas/privileged/`, read-only + signature-verified |
| 25 | L6 | Observed-style confirmation UI — where does Don confirm captured style traits? | Blocks observed-style capture loop | L7 modal at session-end; never mid-turn |

---

## 6. Readiness interpretation notes

An interface pack is **READY** when it contains a complete Rust trait surface, the full set of event shapes (names, payload fields, producer, consumer), an error vocabulary sufficient for callers to handle failures distinctly, and any persistence touchpoints named against the schema pack. A ready pack is a sufficient basis for an implementer to scaffold the crate, stub the trait, and begin building against it — even if questions remain open.

A layer is **PARTIALLY READY** when it has a ready interface pack but also has live open questions whose resolution **may change the interface**. The stable portion of the interface is still safe to build against; the question-dependent portion is flagged in the pack's §10 and must be frozen before that sub-surface is committed.

Both states permit implementation to begin in parallel across layers. The only hard blocker in this batch is waiting on Don to resolve the 25 consolidated questions in §5 before freezing any sub-surface they touch. Scaffolding, trait stubs, schema migrations for append-only tables, and the event-bus wiring can all proceed today.

"Ready" (L5 only) signals that the open questions in L5's §10 are narrow — they modify enum variants and command surfaces but do not alter the core grant-decision flow. L5 can be built and the three open items resolved incrementally without re-architecting.

---

## 7. Dependencies between artifacts

- **event_contracts_master.md is the canonical reference** for every event name and shape used in any interface pack. Where an interface pack and a system-design doc disagree on an event name, the master pack wins. Name reconciliation across the 74 events sits here.
- **sqlite_schema_pack.md is the persistence ground-truth** for L5 (`policy_grants`, `policy_audit_log`, `cost_counters`), L2 (`memory_*` tables), L6 (`persona_profiles`, `compiled_persona_artifacts`), L4 (`routing_decisions`, `byok_credentials_meta`, shared `cost_counters`), plus cross-cutting tables (`sessions`, `approvals`, `degraded_mode`). All layers that persist state reference this pack for DDL, indices, and retention rules.
- **test_matrix_master.md references event names from event_contracts_master, Rust trait signatures from the interface packs, and schema DDL from the schema pack.** A failing test should be diagnosable by walking back through these three documents.
- **Interface packs reference event shapes from event_contracts_master.** They do not redefine events; they cite them by name.
- **implementation_handoff_notes.md pulls from all of the above** and narrates the pieces in build order.

---

## 8. Where to start as an implementer

Recommended reading order when starting cold:

1. file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/implementation_handoff_notes.md — the full picture and build-order narrative.
2. The interface pack for your target layer (§3 catalogue) — trait, events, errors.
3. file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/event_contracts_master.md — every event you emit or consume; authoritative shapes.
4. file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/sqlite_schema_pack.md — any persistence you touch; retention rules and append-only constraints.
5. file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/test_matrix_master.md — your layer's row plus the E2E scenarios your layer participates in.
6. The corresponding system-design document under file:///C:/Users/dbhav/Projects/aether-planning/plans/ (e.g. `L5_policy_engine_system_design.md`) for deeper context only when the interface pack is ambiguous.

---

## 9. What lives where in the monorepo (reference)

Per monorepo §2 mapping in file:///C:/Users/dbhav/Projects/aether-planning/plans/X3_tauri_architecture.md (layer → package). Brief table:

| Layer | Package (crate / module) | Notes |
|---|---|---|
| L1 Interaction Timing | `crates/aether-interaction` | Turn state machine, barge-in, safe-boundary gate |
| L2 Memory Kernel | `crates/aether-memory` | Episodic, semantic, assistant-state; owns vector store |
| L3 Presence Engine | `crates/aether-presence` | Rendering-surface gate, anti-uncanny, presence modes |
| L4 Model Router | `crates/aether-router` | Routing decisions, cost-counter updates, BYOK meta |
| L5 Policy Engine | `crates/aether-policy` | Grants, audit log, cost caps, NeedsUpgrade decisions |
| L6 Persona Compiler | `crates/aether-persona` | Persona profiles, compiled artifacts, signing |
| L7 Trust / UX / Onboarding | `crates/aether-trust` + `apps/aether-shell` (Tauri) | Commands, Trust-tier gating, shell-adapter |
| Event bus | `crates/aether-events` | Owns event-contracts master surface |
| Persistence | `crates/aether-db` | Owns SQLite schema, migrations, append-only enforcement |
| Shared types | `crates/aether-core` | Cross-layer types referenced by trait surfaces |

---

*End of index. Update this document whenever a new implementation-prep artifact is added or an existing one changes its §10 open-question list.*
