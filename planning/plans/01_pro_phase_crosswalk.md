# 01 — Pro-Phase Crosswalk

**Status:** draft
**Last updated:** 2026-04-18
**Axis:** secondary (per Don's 2026-04-18 lock — primary axis is per-must-own-layer; this crosswalk is the phase-indexed view of the same work).
**Depends on:** L1..L7 layer plans, `roadmaps/aether_pro.md`.

---

## Why this view matters

The primary planning axis is per-must-own-layer (L1..L7) — each layer has an owning agent and a sequenced P0..P4/P5 build-out. That axis answers "who owns this and in what order do they build it?" It does **not** answer "what lands in Pro Phase 2?" — a question release planning, roadmap communication, and dependency tracking all need.

This crosswalk maps L1..L7 × Pro Phase 0..6. Each cell describes what lands in that phase for that layer. Where a cell is blocked by another layer's prior phase, the blocker is noted. Critical-path cells — the ones whose slip cascades across the most other cells — are called out after the matrix.

Phase structure from `file:///C:/Users/dbhav/Projects/aether-planning/roadmaps/aether_pro.md`: Phase 0 doctrine/architecture lock → Phase 1 platform core → Phase 2 conversation core → Phase 3 avatar & presence → Phase 4 tools & autonomy → Phase 5 memory & continuity → Phase 6 highest-tier companion quality.

The 7-layer split folds doctrine's reflex router into L1 (interaction timing) per this session's planning decision. Doctrine's 8 must-own layers are unchanged; only the planning split is 7 rows.

---

## The matrix

| Layer | Phase 0 (doctrine/arch lock) | Phase 1 (platform core) | Phase 2 (conversation core) | Phase 3 (avatar & presence) | Phase 4 (tools & autonomy) | Phase 5 (memory & continuity) | Phase 6 (companion quality) |
|---|---|---|---|---|---|---|---|
| **L1 Interaction timing & reflex router** | Event-bus contract design; timing budgets fixed (250/800/2000/4000 ms); reflex classifier scope locked | Rust state machine; typed events on bus; basic VAD-wrapped barge-in; hand-coded reflex rules carried from OSS Preview | Distilled reflex classifier integrated; persona-driven ack pool wired (dep: L6 P1); timing SLA instrumentation; routing handoff to L4 (dep: L4 P2) | Ack timing coupled to presence state transitions (dep: L3 P2) | Reflex classifies tool-plan intents to policy gate (dep: L5 P3) | Longer-session timing (re-greet, absence-awareness) | Context-conditioned phrase selection; mood-linked pacing; Isabelle phrase pack |
| **L2 Memory kernel** | Five-layer memory architecture locked; novelty/salience/confidence/provenance schema frozen | SQLite + vector schema; turn + session memory; write path; basic recall; encryption at rest | Durable memory layer; memory-hit feed to L1 <150 ms; memory-write events to L7 (dep: L7 P3) | -- (nothing — avatar doesn't consume memory directly) | Artifact memory (browser/file outputs); tool-output provenance tagging (dep: L5 P3) | Multimodal ingestion (images, files); behavior memory; memory-editing API; sync-ready schema | Cross-session continuity refinements; Isabelle-scope overlays (cross-project linkage) |
| **L3 Presence engine** | Presence state model locked; state → visible behavior map drafted; rendering-surface shortlist (Unreal / custom GL / hybrid) | -- (nothing — deferred to Phase 3) | State cues in chat/voice modes (no avatar yet) — "listening/thinking/speaking" indicator strip | Presence controller v1 rule-based; gaze/blink/idle; anti-uncanny stabilizer v1; rendering surface chosen and integrated | Presence-linked tool indication ("reading your file…" with avatar-state fusion) | -- (nothing significant) | Richer motion scheduling; gesture; photoreal path (stretch); full-body (stretch) |
| **L4 Model router** | Tier abstraction (fast/main/heavy) locked per `18_model_router_spec.md`; fallback policy designed; BYOK scope locked | Gemma 4 integration (fast tier); local-only routing; stub remote escalation | Router v1: local-vs-remote decision; latency-aware escalation; route_decision event to L7 (dep: L7 P3) + L1 handoff | -- (nothing — router is speech/text-centric) | Task-type routing (tool plans → main; research → heavy); escalation policy maturity | Memory-confidence-weighted routing; sync-aware (mobile-companion decisions) | Cost/quality tuning; model-pack aware routing for Isabelle's hardware class |
| **L5 Policy engine** | Capability model locked; 4 risk classes + 5 autonomy presets finalized; audit-log format frozen | Policy evaluator v1 (capability checks + scope); append-only audit log; approval event contract for L7 | Trust center v1 consumes audit log (dep: L7 P3); scope-picker integration | -- (nothing significant) | Full 5-preset ladder; tool-call gating non-bypassable; session grants; red-team suite v1 | Scope-aware sync (permissions travel with data); revocation propagates across devices | Isabelle-private preset; advanced approval workflows; red-team suite v2 |
| **L6 Persona compiler** | Persona-pack schema locked per `17_persona_pack_schema.md`; compiler I/O contract designed | Compiler v1 (pack → system prompt + phrase pool + voice settings); onboarding step 2 handoff (dep: L7 P1) | Phrase pool emitted to L1 (dep: L1 P2); voice settings emitted to Media engine | Appearance params emitted to L3 (dep: L3 P2) | Memory-salience rules emitted to L2 | Behavior-memory overlay → persona drift protection | Isabelle persona pack; private overrides; 12-archetype catalog finalized |
| **L7 Trust UX & onboarding** | Design-system foundation; component tokenization; onboarding wizard spec locked (7-step, info-explainer mandate); disclosure copy drafted | Onboarding wizard shell (Tauri + React); info-explainer primitive; disclosures flow; simplified permissions UI (Observer/Assistant presets) | Full trust center v1 (permissions + recent actions + memory-review + model disclosure); info-explainer populated; approval prompt UI wired to L5 | -- (nothing — presence is the Phase 3 story) | Routing-decision audit UI; tool-approval UI; action-history replay; red-team copy review | Consent-revocation uniformity; sync-aware permission UI (mobile companion trust surface) | Isabelle-private trust surfaces; cross-project memory review; accessibility re-audit |

Legend: "(dep: Lx Py)" means this cell is blocked by that layer's prior-phase output. "--" means nothing lands in that phase for that layer.

---

## Phase-by-phase narrative

**Phase 0 — doctrine/architecture lock.** Every layer freezes its contracts. Nothing ships to a user; everything that ships later is gated on getting the interfaces right here. The biggest artifacts are L2's memory schema, L5's capability/risk model, and L7's design-system foundation. If any of these three slip, Phase 1 cannot start cleanly.

**Phase 1 — platform core.** The reflex path works end-to-end: Gemma 4 answers, the state machine fires, the onboarding wizard completes, the policy engine gates, basic memory persists, the persona compiler emits a system prompt. No avatar, no remote models, no tools. The product is a premium-feeling local text chat with trust scaffolding.

**Phase 2 — conversation core.** Voice in, voice out, streaming ack, router escalation, durable memory, full trust center v1. This is the "companion product shape" milestone — the first release where Aether Pro feels like the vision. L3 is still absent (state indicator strip, no avatar).

**Phase 3 — avatar & presence.** Presence engine lands. Rendering surface decision is committed. Avatar mode is a separate mode, not a default. No new memory/router/policy work — this is the presence sprint.

**Phase 4 — tools & autonomy.** Browser, files, tool-plan gating, approval UI, audit replay. Policy and router mature together; L7 surfaces the routing-decision audit UI. Red-team suite v1 runs here.

**Phase 5 — memory & continuity.** Multimodal memory, sync architecture, mobile companion, behavior memory. L2 + L4 + L5 + L7 all move together; sync crosses all four.

**Phase 6 — companion quality.** Richer presence, Isabelle persona pack, Isabelle-private trust surfaces, photoreal/full-body stretch work. The product becomes a companion, not an assistant.

---

## Critical-path call-out

Cells whose slip cascades across the most other work:

1. **L2 Phase 0 (memory schema freeze).** Blocks L2 Phase 1, L1 Phase 2 (memory-hit feed), L7 Phase 2 (memory-review UI), L6 Phase 4 (salience rules), and the entire sync story in Phase 5. Single biggest upstream dependency.
2. **L5 Phase 0 (capability/risk model).** Blocks every tool call forever; L7 cannot render permission UI without it; L4 cannot gate tool plans; L2 cannot tag provenance. If this isn't right, Phase 4 cannot ship.
3. **L7 Phase 0 (design-system foundation).** Blocks every user-visible surface in every other layer. L3's avatar mode, L5's approval prompts, L2's memory-review, L4's routing-audit UI all depend on it.
4. **L1 Phase 1 (Rust state machine + event bus).** Every other layer emits events here; slip kills Phase 2 for all downstream layers.
5. **L4 Phase 2 (local-vs-remote router).** Blocks Phase 2 for Aether Pro as a product — the "feels like the vision" milestone can't hit without it.
6. **L3 Phase 3 (rendering-surface decision committed).** The single longest-leaving Phase-0/1 open question. If it slips into Phase 3 unresolved, Phase 3 itself slips.

---

## Open decisions

- **L3 rendering surface** (Unreal-class / custom GL / hybrid) — slated for Phase 0 close but still an open question in `OPEN_QUESTIONS.md`. Must close before Phase 2 or Phase 3 cannot scope.
- **L1 Phase 0 reflex classifier choice** (distilled Gemma 4 vs. classifier head vs. rules-only for P0/P1) — must close in Phase 0 to set Phase 1 scope.
- **L2 + L5 Phase 5 sync architecture** (CRDT vs op-log) — explicitly deferred per `OPEN_QUESTIONS.md`. Must close before Phase 5 start; affects L2, L5, and L7 simultaneously.
- **Ms budgets** for L1 SLA instrumentation in Phase 2 — 250/800/2000/4000 is the framework; exact per-device targets not locked.
- **L7 OSS-Preview shell vs Pro-Phase-1 shell** — whether the same React component tree runs under pywebview (OSS Preview tactical) and Tauri (Pro). Cross-cuts the locked `feedback_css_default_for_ui.md` memory; flag for Don.
- **L4 BYOK UX** — where cost-visibility lands. Pro Phase 2 (alongside router v1) or Phase 4 (alongside tool audits). Currently drawn at Phase 4 in the matrix; may move left.
- **Inbox vs canonical roadmap reconciliation** — inbox Pro roadmap (`inbox_2026-04-18b/aether_pro_roadmap.md`) lists 7 moat layers (folds reflex router into timing) while canonical doctrine lists 8. The 7-layer planning split matches the inbox fold but the doctrine count is authoritative; surfaced here so the executing agent does not re-open.
