# Open Questions — Aether Planning

Live list of unresolved decisions. Each entry should be marked **[OPEN]**, **[DECIDED]** (with date + decision), or **[DEFERRED]** (with trigger condition).

Cross-reference: [MASTER_OUTLINE_TREE § 14](MASTER_OUTLINE_TREE.md#14-open-questions--to-define-later) and [NUMBERED_SPEC § 18.0](NUMBERED_SPEC.md#180-open-questions).

---

## Decision summary — 2026-04-18b planning session

Seven decisions locked this session. All have authority Don, date 2026-04-18. Detailed provenance blocks follow each decision body below.

1. **Segmentation axis** → per-must-own-layer primary + per-Pro-phase crosswalk secondary.
2. **Desktop framework** → Tauri long-term; pywebview tactical OSS Preview only.
3. **Isabelle migration** → phased with short parallel overlap, then cutover.
4. **Repo structure** → monorepo with strong internal boundaries.
5. **Prompt/coordinator model** → self-contained briefing packs + task one-shots; Don is coordinator.
6. **v1.0 content port** → port now (tracked in [plans/03_content_lock_v1_port.md](plans/03_content_lock_v1_port.md)).
7. **Layer count** → 7-layer planning model (reflex embedded in L1), canonical doctrine to be updated.

References:
- [plans/00_ORCHESTRATION_MAP.md](plans/00_ORCHESTRATION_MAP.md)
- [plans/L1_interaction_timing.md](plans/L1_interaction_timing.md) through [plans/L7_trust_ux_onboarding.md](plans/L7_trust_ux_onboarding.md)
- [plans/01_pro_phase_crosswalk.md](plans/01_pro_phase_crosswalk.md)
- [plans/02_oss_preview_alignment_map.md](plans/02_oss_preview_alignment_map.md)
- [roadmaps/aether_oss_preview.md](roadmaps/aether_oss_preview.md), [roadmaps/aether_pro.md](roadmaps/aether_pro.md), [roadmaps/isabelle_private.md](roadmaps/isabelle_private.md)

---

## Planning-session decisions (2026-04-18)

### Segmentation axis — [DECIDED 2026-04-18]

**Decision:** Primary planning axis is **per-must-own-layer** (L1–L7). Secondary view is **per-Pro-phase crosswalk** (see [plans/01_pro_phase_crosswalk.md](plans/01_pro_phase_crosswalk.md)). Per-product and per-engine are not the spine.

- **Date locked:** 2026-04-18
- **Authority:** Don
- **Rationale:** The moat lives in the owned layers; planning should reflect what must be custom-controlled. Per-product/per-phase views are derivative.
- **Impacted files:** all `plans/L*.md`, `plans/01_pro_phase_crosswalk.md`, `plans/02_oss_preview_alignment_map.md`, `plans/00_ORCHESTRATION_MAP.md`, roadmaps.

### Desktop framework — [DECIDED 2026-04-18]

**Decision:** **Tauri is the long-term desktop default** across the Aether family. **pywebview** is a tactical, OSS-Preview-only shortcut if speed-to-demo requires it; it is explicitly non-doctrinal. Locked memory `feedback_css_default_for_ui.md` remains valid in spirit ("HTML/CSS/JS for UI, never Tkinter/Qt") — Tauri is a webview shell, so the intent is preserved; only the framework specificity (pywebview) is superseded.

- **Date locked:** 2026-04-18
- **Authority:** Don
- **Rationale:** Tauri is better aligned with a Rust-native, lower-overhead, serious desktop foundation; pywebview does not cap the ceiling for an OSS Preview demo but cannot serve Pro.
- **Impacted files:** `plans/L7_trust_ux_onboarding.md`, `plans/02_oss_preview_alignment_map.md`, `plans/00_ORCHESTRATION_MAP.md`, `prompts/X3_tauri_architecture.md`, `16_tech_stack.md`, user memory `feedback_css_default_for_ui.md` (scheduled for rewrite after this session).

### Isabelle migration — [DECIDED 2026-04-18]

**Decision:** **Phased migration with short parallel overlap, then cutover per domain.** No hard cutover baseline. No indefinite parallelism. Each domain has a planned overlap end date and a verification gate.

- **Date locked:** 2026-04-18
- **Authority:** Don
- **Rationale:** Isabelle_Kunstig is live with 548+ passing tests; phased migration preserves continuity while verifying parity, and bounded overlap avoids two-system drift.
- **Impacted files:** `prompts/X2_isabelle_migration.md`, `roadmaps/isabelle_private.md`, `plans/00_ORCHESTRATION_MAP.md`. Future: `plans/X2_isabelle_inventory.md` (X2 agent's first deliverable).

### Repo structure — [DECIDED 2026-04-18]

**Decision:** **Monorepo with strong internal boundaries** (`apps/`, `packages/`, `planning/`, `research/`, `infra/`, `tools/`). Scattered `aether/`, `aether-desktop-voice/`, `aether-frontend-ux/`, `aether-personas/` consolidated into the monorepo. Boundaries enforced by build-system config, not convention.

- **Date locked:** 2026-04-18
- **Authority:** Don
- **Rationale:** Shared systems, shared doctrine, and AI-assisted development all benefit from unified context; internal-boundary enforcement preserves ownership without fragmenting the tree.
- **Impacted files:** `prompts/X1_repo_restructure.md`, `plans/00_ORCHESTRATION_MAP.md`. Future: `MIGRATION_PLAN.md` at new monorepo root.

### Prompt / coordinator model — [DECIDED 2026-04-18]

**Decision:** **Self-contained briefing packs + task-specific one-shot prompts.** Don is the human coordinator. No free-running meta-agent. Each agent begins from a concise briefing pack; execution prompts are focused and task-bounded.

- **Date locked:** 2026-04-18
- **Authority:** Don
- **Rationale:** The project depends on quality ceiling, taste, and doctrine enforcement — not just task completion. Centralized coordination preserves human oversight over quality-sensitive decisions.
- **Impacted files:** all `prompts/*.md`, `plans/00_ORCHESTRATION_MAP.md`.

### v1.0 content port — [DECIDED 2026-04-18]

**Decision:** **Port valuable v1.0 content now**, before final segmented plans are declared complete. Port manifest is canonical in [plans/03_content_lock_v1_port.md](plans/03_content_lock_v1_port.md). Priority items: 8-screen wizard, Guest mode, distribution playbook, cost-visibility UX, Inno Setup scaffold (OSS Preview only).

- **Date locked:** 2026-04-18
- **Authority:** Don
- **Rationale:** Planning quality improves when scope-defining product content is stabilized before deeper architecture segmentation; prevents future agents from blocking on retrieval against retired v1.0 docs.
- **Impacted files:** `plans/03_content_lock_v1_port.md`, `prompts/X4_v1_content_port.md`, `plans/L4_model_router.md`, `plans/L5_policy_engine.md`, `plans/L7_trust_ux_onboarding.md`.

### Layer-count model — [DECIDED 2026-04-18]

**Decision:** The working planning model uses **7 layers**, with the reflex router conceptually embedded inside **L1 Interaction Timing** rather than as a separate planning layer. Canonical doctrine ([01_product_doctrine.md](01_product_doctrine.md) currently lists 8 must-own layers) will be updated in the next pass to reflect the 7-layer split while preserving reflex as a distinct concept inside L1. All layer plans, the Pro-phase crosswalk, the OSS alignment map, and the inbox Pro roadmap already converge on 7 layers.

- **Date locked:** 2026-04-18
- **Authority:** Don
- **Rationale:** Planning, roadmaps, and agent outputs already converge on 7 layers. Keeping two different counts (8 in doctrine, 7 in plans) creates persistent confusion and risks silent drift. Reflex is not losing status — it remains an explicit sub-system owned by L1, tracked distinctly in the plan and in acceptance criteria.
- **Impacted files:** `01_product_doctrine.md` (pending doctrine-update pass), `MASTER_OUTLINE_TREE.md` (pending), all `plans/L*.md`, roadmaps, `plans/00_ORCHESTRATION_MAP.md`, `plans/01_pro_phase_crosswalk.md`.

---

### X3 Tauri architecture — G1 approval — [DECIDED 2026-04-18]

**Decision:** G1 of [plans/X3_tauri_architecture.md](plans/X3_tauri_architecture.md) (Rust↔TS boundary shape: typed commands, append-only events, webview-as-view, capability-gated system-affecting commands) is **APPROVED** 2026-04-18 by Don. G2 (plugin-vs-core allowlist), G3 (updater channel model + code-signing path), and G4 (IPC + filesystem scope defaults) remain **PENDING REVIEW** until a later gate pass.

- **Date locked:** 2026-04-18
- **Authority:** Don
- **Rationale:** Boundary principles in §2 + event-bridge pattern in §3 are sufficient to unblock L1–L7 agents designing against a typed Rust core without committing to plugin allowlists, signing path, or filesystem scope widths.
- **Impacted files:** `plans/X3_tauri_architecture.md` (G1 marker + acceptance section), downstream L1/L4/L5/L7 prompts that reference the boundary.

### Monorepo plan — working-baseline acceptance — [DECIDED 2026-04-18]

**Decision:** [planning/monorepo_plan_draft.md](planning/monorepo_plan_draft.md) is accepted as the **working baseline** for X1 (canonical planning basis until superseded). No alternate monorepo structures are to be planned elsewhere unless Don explicitly requests them. The plan's top-level layout, 7-layer-to-package mapping, shared-infra packages, guardrails, and migration waves are the single source of truth for X1 execution.

- **Date locked:** 2026-04-18
- **Authority:** Don
- **Rationale:** Plan is sufficient to anchor X1 and downstream dependent agents; remaining open questions (sibling-repo fate, Isabelle physical location, canonical repo name, history-preservation policy) are enumerated inside the plan and tracked, not blocking acceptance as the baseline.
- **Impacted files:** `planning/monorepo_plan_draft.md` (status: working), `prompts/X1_repo_restructure.md` (reads this plan as upstream), `plans/00_ORCHESTRATION_MAP.md` §4 X1 row.

### Doctrine follow-up items (residual inconsistencies) — [OPEN]

Residual artifacts that still need doctrine-alignment edits after the 2026-04-18 doctrine pass. These are tracked as follow-ups; do not block current work:

- **[FOLLOW-UP]** `16_tech_stack.md` — §Desktop app does not yet state the Tauri / pywebview doctrine in the 2026-04-18 form (long-term Tauri default across family; pywebview tactical OSS-Preview-only, explicitly non-doctrinal). Owner: coordinator.
- **[FOLLOW-UP]** `roadmaps/aether_pro.md` — verify no lingering "8 moat layers" enumeration; reconcile to 7 layers + reflex-inside-L1. Owner: coordinator.
- **[FOLLOW-UP]** `NUMBERED_SPEC.md` — verify the must-own layers enumeration matches the 7-layer model; reconcile if an 8-item list remains. Owner: coordinator.
- **[FOLLOW-UP]** User memory `feedback_css_default_for_ui.md` (lives outside this repo, in `C:/Users/dbhav/.claude/projects/.../memory/`) — rewrite to preserve "HTML/CSS/JS for UI; never Tkinter/Qt" and supersede the pywebview specificity with Tauri as the family long-term default; note pywebview as OSS-Preview-only tactical exception. Owner: Don (memory files are user-owned).

### System-design session outputs (2026-04-18) — [INFO]

Seven system-design documents and two cross-layer integration notes produced in this session:

- `plans/L5_policy_engine_system_design.md` (1076 lines) — chokepoint.
- `plans/L1_interaction_timing_system_design.md` (1071 lines).
- `plans/L4_model_router_system_design.md` (1141 lines).
- `plans/L7_trust_ux_onboarding_system_design.md` (1012 lines).
- `plans/L2_memory_kernel_system_design.md` (819 lines).
- `plans/L3_presence_engine_system_design.md` (504 lines).
- `plans/L6_persona_compiler_system_design.md` (820 lines).
- `plans/L1_L4_L5_L7_integration_notes.md` (244 lines) — 12 invariants, 10 integration OQs.
- `plans/L2_L3_L6_integration_notes.md` (211 lines) — 11 invariants, 9 integration OQs.

All seven must-own layers now have implementation-grade system designs. Typed event contracts, IPC command surfaces, Rust trait sketches, DDL, and failure/degraded-mode rules are specified per layer. No doctrine was re-opened. No code was scaffolded. Open questions surfaced below are additive.

### New integration-level open questions surfaced by system-design pass — [OPEN]

Decisions needed from Don before implementation can begin. These are integration-level; layer-internal open questions remain inside each layer's design doc.

- **[DECIDED 2026-04-18]** Per-step policy re-evaluation for multi-step tool plans — **grant-scope with 8-trigger re-eval list.** L4 skips re-eval for steps whose `(capability, resource, persona)` fall inside the grant; must re-eval on: (1) different capability/sub-capability, (2) resource outside pattern, (3) persona swap, (4) remote-tier escalation (privacy-posture gate), (5) provenance class elevation, (6) cost_threshold_hit since grant, (7) GrantRevoked/EmergencyRevokeAll since grant, (8) TTL expiry. See [DECISION_LOCK_PASS_2026-04-18c.md §Decision 4](DECISION_LOCK_PASS_2026-04-18c.md).
- **[DECIDED 2026-04-18]** `NeedsUpgrade` encoding — **top-level `Decision::NeedsUpgrade(CapabilityPath)`.** Peer variant of Allow/Ask/DraftOnly/Deny. L1 + L7 pattern-match without unpacking nested reason. See [DECISION_LOCK_PASS_2026-04-18c.md §Decision 1](DECISION_LOCK_PASS_2026-04-18c.md).
- **[DECIDED 2026-04-18]** Draft-only encoding — **single `Decision::DraftOnly { source: System | UserChoice }`** discriminated by inner source field; L7 adds `UserChoice::DeferToDraft` to approval-response payload. L4 side-effect inhibition is a single branch regardless of source. See [DECISION_LOCK_PASS_2026-04-18c.md §Decision 2](DECISION_LOCK_PASS_2026-04-18c.md).
- **[DECIDED 2026-04-18]** Missing L5 IPC commands — **add all three:** `policy.export_audit`, `policy.set_cost_cap`, `policy.reset_cost_counter`. Two new capabilities: `System.ExportAudit`, `System.CostCapAdmin` (risk class High, default Ask + re-auth). `cost_cap_rearmed` event promoted from proposed to confirmed (L5 emitter). See [DECISION_LOCK_PASS_2026-04-18c.md §Decision 3](DECISION_LOCK_PASS_2026-04-18c.md).
- **[DECIDED 2026-04-18]** BYOK cost-cap re-arm UX flow — **explicit user-initiated re-arm with re-auth; parked plans NOT auto-resumed.** Cap-hit modal surfaces 4 actions: Raise cap / Reset counter / Switch to local / Wait until reset. `cost_cap_rearmed` is the shared unblock signal. User must re-initiate tasks after cap raise. See [DECISION_LOCK_PASS_2026-04-18c.md §Decision 5](DECISION_LOCK_PASS_2026-04-18c.md).

### Follow-up mechanical edits from decision-lock pass — [FOLLOW-UP]

The 5 locks above require small mechanical updates to downstream files. Non-blocking for X1 Wave 0; can happen inside the L5 scaffold session:
- `plans/L5_policy_engine_system_design.md` §2, §3, §4, §5, §7, §9 — reflect all 5 locks.
- `plans/implementation_prep/L5_interface_pack.md` — reflect all 5 locks (Decision enum variants, new commands, new capabilities, event confirmations).
- `plans/implementation_prep/L4_interface_pack.md` — reflect Decision 4 (re-eval triggers) + Decision 5 (cap-hit flow).
- `plans/implementation_prep/L7_interface_pack.md` — reflect Decision 2 (UserChoice::DeferToDraft) + Decision 5 (4-action cap-hit modal).
- `plans/implementation_prep/event_contracts_master.md` — promote `cost_cap_rearmed` to confirmed; update `policy_decision` + `approval_response` payloads to reflect locks 1 + 2.
- **[OPEN]** Privacy-posture waiver scope — per-provider vs global vs per-task. L5 §10 flags; L4 §19 proposes per-provider + task-scoped default.
- **[OPEN]** Persona-swap safe boundary — Idle-only (strict) vs end-of-utterance (relaxed). L1 §16, L6 §18, L2/L3/L6 integration §10 all flag. Affects hot-swap user experience.
- **[OPEN]** Speculative payload materialization during Ask → Allow — no speculation (safe, 5–15 ms latency) vs buffer while awaiting user approval (faster, private-content buffer risk). L4 §19 proposed default: no speculation.
- **[OPEN]** AssistantStateMemory as a distinct memory domain vs subtype of SessionMemory. L2 §20 contradiction flag.
- **[OPEN]** `presence.set_mode` — production IPC surface (X3 §2.2) vs debug/test-only (L1 §7.4 says L1 does not depend on it). L3 OQ-L3-4.
- **[OPEN]** Anti-uncanny stabilizer enabled on Lite tier. L3 OQ-L3-3; informs minimum-acceptable Lite quality.
- **[OPEN]** Privileged-overlay path mechanism (Isabelle) — env var vs signed manifest entry vs build flag. L6 §18 OQ9; gates I10/I11 of L2/L3/L6 integration note.
- **[OPEN]** Observed-style confirmation UI — L6 emits `persona_observed_style_proposed`; L7 needs a confirmation surface or the "no silent learning" invariant (I5) remains theoretical.
- **[OPEN]** Vector-store vendor + embedding model per tier — L2 §19 OQ1/OQ2. Blocks hardened retrieval pipeline.
- **[OPEN]** Doc-anchor drift — prompt citations `12_permissions_autonomy.md §9.4` and `13_trust_security_redteam.md §10.3` do not exist in those files. L5 §14 flagged; either the anchors get added to `12` / `13` or the citations get updated.
- **[OPEN]** Rendering surface choice (Unreal / custom GL / hybrid) — deferred per orchestration map §9 (Don's gate, Pro Phase 2); logged here so system-design files that mark "rendering-surface-agnostic" remain traceable.

### Implementation-prep session outputs (2026-04-18) — [INFO]

Eleven implementation-prep artifacts produced in the second session of 2026-04-18:

- `plans/IMPLEMENTATION_PREP_INDEX.md` (157 lines) — top-level entry point.
- `plans/implementation_prep/L{1..7}_interface_pack.md` — seven interface packs (520 / 251 / 253 / 334 / 585 / 344 / 537 lines).
- `plans/implementation_prep/event_contracts_master.md` (1258 lines) — 74-event catalog, 14 invariants, versioning rules, name-variant reconciliation.
- `plans/implementation_prep/sqlite_schema_pack.md` (679 lines) — 18 DRAFT SQLite tables, 5 append-only, hash-chain + HMAC, migration + encryption plan.
- `plans/implementation_prep/test_matrix_master.md` (314 lines) — 8 per-layer tests × 7 layers + 8 E2E scenarios + 10 red-team attacks + perf/replay tests.
- `plans/implementation_prep/implementation_handoff_notes.md` (304 lines) — 13-step implementation order, 9 named risks.

Readiness snapshot: **L5 ready** for scaffolding; **L1/L2/L3/L4/L6/L7 partially ready** (interfaces stable on most of each surface, specific surfaces blocked by open questions listed below).

### Additional open questions surfaced by implementation-prep pass — [OPEN]

Additive to prior pass; non-duplicates only.

- **[OPEN]** L1 sub-budget ms values — `T_reflex_sla`, `T_memory_deadline`, `T_barge_in_cut`, `T_tts_chunk_inactivity`, `T_repair_ack`, `T_event_loop_tick` all currently proposed-defaults (150 / 150 / 150 / 500 / 2000 / 5 ms). Need Don sign-off before property-test thresholds and tier-downgrade triggers freeze.
- **[OPEN]** L6 `tier_preference` terminology overload — same name used for perf tier (L4 §87) and model tier (17_persona_pack_schema.md). Compiler currently emits both under distinct names; recommend schema v2 rename. Not done this pass per no-doctrine-edits rule.
- **[OPEN]** L6 persona-pack signing scheme — Ed25519 + pinned public key vs OS-keychain-backed. Blocks signature verifier implementation.
- **[OPEN]** L7 pywebview shell-adapter event-replay parity — Tauri's seq-ordered event bus is trivial; pywebview may be lossy. Decide: feature-cap OSS Preview (no strict ordering) or build ordering shim.
- **[OPEN]** L7 keybinding collision audit across wizard / trust-center / persona picker — no systematic inventory yet.
- **[OPEN]** L7 single-window multi-route vs multi-window for onboarding — Tauri capability list differs either way.
- **[OPEN]** L7 guest-mode infrastructure (Cloudflare Worker + Groq endpoint) — ship for OSS Preview or defer until Pro Phase 1?
- **[OPEN]** L2 contradiction-ranker tiebreaker — recency vs confidence vs provenance vs user-pin precedence when two memories conflict. Needs L6/L7 input.
- **[OPEN]** Newly-proposed events from event_contracts_master — `degraded_mode_entered` / `degraded_mode_cleared` / `ingestion_candidate_accepted` / `cost_cap_rearmed` / `memory_promoted` / `plan_preview_ready`. Each needs author confirmation from the owning layer before schema lock.
- **[OPEN]** Storage encryption scheme — SQLCipher whole-DB vs per-column encryption on sensitive fields. Affects dependency pinning, key handling, build toolchain. Recommend whole-DB; Don locks.
- **[OPEN]** Audit DB isolation — single `aether.db` vs separate `aether_audit.db`. Separate enables stricter append-only isolation but doubles WAL overhead.
- **[OPEN]** HMAC key rotation cadence for audit log — no policy set. Propose annual with dual-epoch transition window.
- **[OPEN]** Memory tombstone grace period — how long between soft-delete (tombstoned=1) and hard-delete (content removed). Propose 7 days; Don locks.
- **[OPEN]** HMAC key rotation epoch-transition mechanics — how the audit DB remains verifiable across rotation (pre-rotation records signed by old key; post-rotation by new). Design sketch exists in sqlite_schema_pack §6; needs implementation-level spec before L5 ships.

## Pull decisions (2026-04-18)

- **[DECIDED 2026-04-18]** v1.0 fate → **PULLED.** GitHub release `v1.0.0-pre` deleted (tag + release); `dbhavery/aether` repo set to PRIVATE; portfolio Aether content removed (commit `d4cde07` on portfolio `feature/portfolio/cinematic-redesign`). New Aether OSS Preview will be a rebuild per `01_product_doctrine.md` — not a continuation of v1.0. See [archive/PULL_STATUS_2026-04-18.md](archive/PULL_STATUS_2026-04-18.md).
- **[DECIDED 2026-04-18]** `dbhavery/aether` repo visibility → **PRIVATE**.
- **[DECIDED 2026-04-18]** Portfolio Aether entry → **REMOVED** (all 59 files, including `public/aether/`, `public/anima/`, demo HTMLs, components).
- **[PENDING MANUAL]** LinkedIn post from 2026-04-18 — still live; Don must delete manually (morning-intel doesn't persist URN).

---

## Naming

- **[OPEN]** Final public flagship name — Aether Pro / Aether Core / Aether One (or new)
- **[OPEN]** Final OSS preview naming — "Aether OSS Preview" vs shorter
- **[OPEN]** Final Isabelle formal naming — Isabelle / Isabelle_Kunstig / another private brand
- **[OPEN]** Alt umbrella names considered if Aether is dropped: Astrae, Vesper, Eidolon, Lumen, Serein, Auralis

## Scope boundaries

- **[OPEN]** Exact OSS Preview MVP cut line — which features ship in hours/days vs. are teaser-only
- **[OPEN]** Exact first Pro milestone cut line
- **[OPEN]** When full-body avatar becomes an actual target milestone (not MVP)
- **[OPEN]** Desktop-first vs mobile parity timing for Pro

## Tech decisions

- **[DECIDED 2026-04-18]** Final desktop framework — **Tauri long-term across the family**; pywebview tactical OSS-Preview-only. See Decision summary above.
- **[OPEN]** Final mobile stack — React Native / native / cross-platform Rust core
- **[OPEN]** Final local model stack — per-tier model choices
- **[OPEN]** Final rendering stack for Pro avatar — Unreal-class, custom, or hybrid
- **[OPEN]** Final sync architecture — CRDT / op-log / custom
- **[OPEN]** Transport for avatar mode — WebRTC baseline vs custom

## Trust / legal

- **[OPEN]** Final disclosure copy
- **[OPEN]** Terms and conditions scope
- **[OPEN]** Data retention defaults (per memory layer)
- **[OPEN]** Consent patterns (onboarding, ongoing, revocation)
- **[OPEN]** Account / data policy details

## Evaluation metrics (target values to define)

- **[OPEN]** Time to first acknowledgement — target ms budget
- **[OPEN]** Time to useful answer — target ms budget
- **[OPEN]** Avatar smoothness under load — framerate target by tier
- **[OPEN]** Permission trust comprehension — measurement method
- **[OPEN]** Onboarding completion rate — target %
- **[OPEN]** Tutorial completion / skip rate — target %
- **[OPEN]** Crash/performance stability by tier — thresholds
- **[OPEN]** User trust and retention signals — which to instrument

## Architecture decisions deferred

- **[DEFERRED — after OSS Preview ships]** When to begin Aether Pro custom memory kernel implementation
- **[DEFERRED — after OSS Preview ships]** When to begin custom presence scheduler implementation
- **[DEFERRED — after Pro alpha]** Whether Isabelle ever diverges into its own codebase or stays a privileged profile

## Repo/folder structure decisions

- **[DECIDED 2026-04-18]** How many repos — **monorepo with strong internal boundaries**. See Decision summary above.
- **[PARTIAL 2026-04-18]** `dbhavery/aether` on GitHub is now PRIVATE (pull). Local `file:///C:/Users/dbhav/Projects/aether/` still on disk.
- **[OPEN]** Fate of local `aether/`, `aether-desktop-voice/`, `aether-frontend-ux/`, `aether-personas/` directories — confirmed local-only (not on GitHub) but still contain v1.0 code. Archive to `_deprecated/`, leave, or delete?
- **[OPEN]** Fate of existing `Isabelle_Kunstig/` repo — migrate into new structure, archive, or keep in parallel

## Doctrine application edge cases

- **[OPEN]** Which open-source primitives (if any) are acceptable to carry into Aether Pro as temporary accelerators vs. must be replaced before Pro ships
- **[OPEN]** Acceptable use of hosted frontier LLMs (Anthropic/OpenAI/etc) for the deliberative path — scope, privacy, fallback rules
