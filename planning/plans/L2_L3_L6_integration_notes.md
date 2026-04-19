# L2 + L3 + L6 Integration Notes

> **Scope:** Data-plane / experience-plane composition between L2 (Memory Kernel), L3 (Presence Engine), and L6 (Persona Compiler).
> **Companion note:** file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_L4_L5_L7_integration_notes.md — covers the control-plane (L1 turn loop, L4 router, L5 policy, L7 trust/UX). Invariants established there are referenced rather than restated.
> **Orchestration map:** file:///C:/Users/dbhav/Projects/aether-planning/plans/00_ORCHESTRATION_MAP.md §6–7.

---

## 1. Purpose

This note captures how L2 (memory), L3 (presence), and L6 (persona compiler) compose. They share a tight coupling: persona drives salience + visual + phrase pools; memory retrieval feeds presence/language cues; hot-swap coordination touches all three. This note sits alongside file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_L4_L5_L7_integration_notes.md (which covers the control-plane). Where a concern spans both planes — e.g. persona-swap safe-boundary semantics, policy-gated memory reads, privacy-class routing — the control-plane note is authoritative for the gate; this note describes the data and behavior that flows through it.

---

## 2. Sequence flow 1 — "user asks a personal question requiring memory recall"

Participants: L1 (turn loop), L2 (memory), L3 (presence), L4 (router), L5 (policy), L6 (persona), L7 (trust UI).

1. **L1 — Listening → reflex classify.** User utterance arrives. L1's reflex classifier labels it `direct-local` with a `memory_query` slot ("what's my favorite coffee order").
2. **L1 emits `memory_query`.** Contract:
   - `scope = { DurableUserMemory, BehaviorMemory }`
   - `query = "what's my favorite coffee order"`
   - `threshold = 0.6`
   - `deadline = 150 ms`
   - `turn_id`, `change_id` for audit replay.
3. **L2 receives → L5 policy check.** L2 asks L5 for the `memory.read.user` capability on the candidate domain + privacy class. L5 evaluates precedence (hardcoded → privacy-posture → persona-defaults → session-overrides) and returns `Allow` with audit id.
4. **L2 ranks candidates.** Lexical + vector + structured retrieval merges candidates. Ranking function applies current `CompiledSalience` from L6 (persona-weighted boosts — e.g. "coffee preferences" domain may be boosted under a warm-assistant persona).
5. **L2 returns `MemoryHit[]`.** Each hit carries `privacy_class` tag (`public-ish`, `private`, `sensitive`), `confidence`, `provenance_chain`, `deadline_met=true`. L1 receives before deadline.
6. **L1 folds into turn context.** Hits become grounded references for drafting.
7. **L1 → L4 route.** `RouteHint` includes memory `confidence_summary` and max `privacy_class` across hits. L4 sees public-ish content, picks `local-main` tier (no remote escalation).
8. **L3 in parallel — behavior render.** Persona's `CompiledVisual` says `warmth=0.8` → gentle smile on the acknowledgment beat; `initiative=0.6` → slight forward lean. All stays within `CompiledVisual.intensity_bounds`.
9. **L3 language ack.** L1 picks an ack phrase from `CompiledLanguage.acknowledgment_pool` ("Oh, I remember — ...") with persona-weighted anti-repetition. L3's behavior scheduler aligns a nod + brow-raise to phrase boundary.
10. **Streaming speech.** L1 streams answer text; L3 consumes viseme ticks from the media engine; lip-sync aligned.
11. **`turn_end`.** TurnMemory flushed (ephemeral) or promoted per retention policy. DurableUserMemory access_count incremented. L5 records access audit.
12. **L7 audit surface.** Trust center's memory review lists the accessed item with change_id traceable to the audit record.

---

## 3. Sequence flow 2 — "assistant needs to acknowledge, retrieve memory, speak — all style-consistent"

This flow zooms in on the 150 ms overlap between ack, retrieval, and speaking — where persona style consistency is most visible.

1. **Turn begins.** L1 enters `AcknowledgeAndWait`. `T_ack_deadline` scheduled at 800 ms.
2. **Ack phrase chosen.** L1 queries L6's `CompiledLanguage.acknowledgment_pool` with persona-weighted anti-repetition selector. Returns one phrase plus phrase_id for cooldown bookkeeping.
3. **L3 Acknowledging behavior starts.** Behavior scheduler plays `Acknowledging` (nod + brow-raise) keyed to the ack phrase's prosodic boundary.
4. **L2 retrieval in parallel.** 150 ms budget. Lexical first-pass, vector second-pass, structured lookup if the query shape suggests it.
5. **Race resolution.**
   - If `memory_hit` arrives **before** ack completes → next speaking segment includes grounded reference.
   - If not → L1 falls back to ungrounded drafting; the outcome is still style-consistent because the language pool is already persona-compiled.
6. **State transitions.** L3 moves `Acknowledging → Thinking → Speaking` as L1 `turn_state_change` events fire. Transitions blended per `CompiledVisual.transition_times`.
7. **Intensity bounds enforced.** Throughout, visual parameters stay within `CompiledVisual.intensity_bounds`. At `Balanced+` trust posture, the anti-uncanny stabilizer is active and clamps micro-expressions.
8. **Speaking.** L3 consumes `viseme_tick` from the media engine; lip-sync aligned; gesture emphasis (hand/head beats) scales with persona `expressiveness`.
9. **Safe boundary for swap.** End-of-utterance is a safe boundary for any pending persona swap (see §5).

---

## 4. Sequence flow 3 — "user edits a memory and the persona/presence implications update"

1. **L7 trust center.** User opens memory review, selects a memory, edits content (or deletes it).
2. **L7 → `memory.edit(memory_id, patch)`.** Call is policy-gated.
3. **L5 evaluation.** Returns `Allow` + audit record. (Edit/delete on user-owned memory is default-allow; sensitive memories may require an additional confirmation step owned by L7.)
4. **L2 applies patch.** Emits `memory_edit_confirmed { memory_id, change_id, patch_summary }`.
5. **Provenance cascade.** L2 walks provenance chain; memories that transitively depended on the edited one are re-weighted (confidence may decrease; some may be flagged `stale_pending_review`).
6. **L6 salience re-eval.** If the edited memory was high-salience for the current persona, L6 refreshes `CompiledSalience` **without** a full persona recompile (salience is a compiled sub-artifact and can be regenerated from rules + current memory index).
7. **Observed-style withdrawal.** If the user **deleted** a memory that informed an active `persona_observed_style_proposed` signal (BehaviorMemory-derived), L6 withdraws that proposal. User sees no silent learning — this is I5.
8. **L3 implication.** No direct action unless the deleted memory was referenced in the current in-flight turn. If it was, L3 stays consistent with L1's repair state (e.g. L1 may elect to not re-assert the now-deleted fact; L3 continues its current behavior sequence without flicker).
9. **L5 audit.** Edit + cascaded re-weighting + any withdrawn proposals all land in the audit log under the same `change_id` lineage.

---

## 5. Sequence flow 4 — "persona hot-swap mid-conversation"

1. **User action.** L7 persona picker: selects new persona.
2. **L7 → `persona.compile(new_id)`.** L6 loads pack from the persona repository.
3. **L6 compile pipeline.**
   - Validate schema.
   - Run compiler (visual, language, salience, routing, policy-defaults sub-artifacts).
   - Verify signature if pack is signed → sets `trust_tier`.
   - Hand off `CompiledPolicyDefaults` to L5 (L5 recomposes precedence but does not yet apply until commit).
4. **L6 emits `persona_swap_begin { old_persona, new_persona, change_id }`.** All layers receive.
5. **L1 schedules commit.** Commit point = next safe boundary (Idle, or end-of-utterance per L1 §7.5 / L6 §8). See §10 OQ-1.
6. **L7 picker state.** "Preparing persona" affordance on picker.
7. **L3 visual blend begins.** Visual params blend toward new persona's bounds across a blend window. Blend starts immediately; completion waits for commit so the crossover is perceptually continuous.
8. **L2 ingestion pauses.** Auto-saved ingestion paused during window. Session memory entries created during the window are tagged `pending_persona_rewrite` so they can be re-attributed after commit.
9. **Safe boundary reached.** L6 emits `persona_swap_commit` + `compiled_persona_ready`.
10. **Atomic swap.**
    - L1 swaps phrase pools (acknowledgment, clarification, repair) atomically.
    - L2 re-weights active retrieval caches per new `CompiledSalience`.
    - L3 finalizes visual transition; intensity_bounds now bind to new persona.
    - L5 applies new `CompiledPolicyDefaults` in the precedence chain.
    - L4 applies new `CompiledRouting` (tier prefs, escalation thresholds).
11. **L5 audit.** Persona-swap recorded. Any overrides that changed policy defaults trigger **separate** policy decisions logged individually.
12. **L7 picker → "active".**
13. **Failure path.** Any stage failure → L6 emits `persona_swap_rollback`; L1/L2/L3/L4/L5 revert; L7 surfaces the failure cause.

---

## 6. Key invariants

| # | Invariant |
|---|---|
| **I1** | **Persona proposes; L5 decides.** No persona-compiled field is applied to authorization before L5 evaluates it per the precedence rule in the L1/L4/L5/L7 note. |
| **I2** | **Salience ranks, it does not gate.** Memory retrieval is ranked using the current `CompiledSalience` from L6; salience rules cannot override L5 policy gates on read. |
| **I3** | **Visible behavior is L1-and-L6 bound.** L3 behavior must remain consistent with L1 turn state AND L6 `intensity_bounds`. L3 never exceeds persona's `intensity_bounds`. |
| **I4** | **Persona hot-swap is atomic at the L1 safe boundary.** No layer applies partial persona state mid-utterance. |
| **I5** | **No silent learning.** No layer learns from user behavior on its own. Observed-style signals become persona changes only after explicit user confirmation in L7. |
| **I6** | **Privacy-class tags propagate.** `privacy_class` tags on `MemoryHit`s propagate through L4 routing and L3 rendering — e.g. a `private` memory surfaced in an answer must not be verbalized through a remote-routed TTS without a privacy-posture waiver. |
| **I7** | **Delete cascades, auditably.** Deleting a memory cascades: L2 re-weights, L6 re-evaluates proposed observed-style updates tied to it, L5 audit log records cascade events. |
| **I8** | **Rendering surface is swappable; scheduler is not.** L3 rendering surface sits behind a trait and can be swapped (Unreal / custom GL / hybrid). L3's behavior scheduler is a must-own L3 internal and is not swappable. |
| **I9** | **Degraded mode is visible.** If L2 is down, L3 surfaces a "no memory mode" visual indicator (not just the L7 banner). The user must never be deceived about capability. |
| **I10** | **Signed packs earn privileged overlay.** Persona pack signature must be verified before a pack can take privileged-overlay status. Unsigned packs are allowed for standard personas with reduced trust. |
| **I11** | **Isabelle privileged overlay widens, never bypasses.** The Isabelle privileged overlay widens defaults but cannot bypass hardcoded-blocks, privacy-posture gates, or cost-caps — all L5-owned. |

---

## 7. Concrete coupling table — who reads what from whom

| From | To | Contract | Cadence |
|---|---|---|---|
| L6 | L1 | `CompiledLanguage` (ack/clarify/repair pools, style) | on `persona_swap_commit` + initial compile |
| L6 | L2 | `CompiledSalience` (domain weights, recency/freq rules, boost patterns) | on `persona_swap_commit`; used per retrieval |
| L6 | L3 | `CompiledVisual` (intensity_bounds, transition_times, expressive profile) | on `persona_swap_commit`; blend window active between begin/commit |
| L6 | L4 | `CompiledRouting` (tier prefs, escalation thresholds, privacy-class mapping) | on `persona_swap_commit` |
| L6 | L5 | `CompiledPolicyDefaults` (default allow/deny, overrideable flags) | on `persona_swap_commit`; L5 recomposes precedence |
| L6 | L7 | `PersonaSummary` (name, description, trust_tier, signed?) | on `persona_swap_commit` + initial |
| L2 | L1 | `MemoryHit[]` | per `memory_query` (150 ms budget) |
| L2 | L4 | `confidence_summary`, `max_privacy_class` | on request for routing decision |
| L2 | L7 | memory list / get / review data | on trust-center request |
| L1 | L3 | `turn_state_change` events | continuous |
| L3 | L1 | `presence_state` (advisory) | continuous |
| L5 | L2 | policy decisions (`memory.read`, `memory.write`, `memory.edit`, `memory.delete`) | per-op |
| L5 | L3 | policy decisions (privacy-class-aware TTS/visual gates) | per-op |
| L5 | L6 | policy decisions on persona compile / privileged overlay / signature-required paths | per-op |
| L7 | L2 | memory edit / delete / review actions | on user action |
| L7 | L6 | persona select / pack install / observed-style confirm | on user action |

---

## 8. Cross-cutting concerns

- **Observability.** Every L2/L3/L6 event carries `change_id` for replay. Audit log in L5 can be re-walked to reconstruct what the user saw and why.
- **Determinism.** L6 compilation + L2 ranking must be deterministic given the same inputs. Required for audit replay and reproducibility of trust-center explanations.
- **Anti-repetition.** L6 ack pool and L3 behavior cooldowns share the **objective** of avoiding mechanical repetition. They do **not** share state; each maintains its own cooldown window. Both fold persona-recency signals so that warm personas feel warmer on return engagements without parroting.
- **Privacy-class flow.** `privacy_class` flows L2 → L4 (routing) → L3 (TTS routing surface) → L7 (display). L6 **cannot** downgrade privacy-class; it can only propose display hints that L5 gates.
- **Change_id lineage.** Memory edits, persona swaps, and observed-style confirmations all share a single lineage id space so the audit view can show cause → cascade → effect.

---

## 9. Failure composition

| Failure | L1 | L2 | L3 | L6 | L7 |
|---|---|---|---|---|---|
| **L2 down** | Empty-memory path; answers ungrounded | — | "No memory mode" visual indicator | Salience rules still active but ineffectual (nothing to rank) | Banner |
| **L6 compile fail** | Uses baked-in phrase pool | Uses system-default salience | Uses minimum visual params | Falls back to minimum-trust persona | "Minimum-trust persona" banner |
| **L3 rendering surface crash** | Unaffected (text path still works) | Unaffected | Behavior scheduler keeps state; rendering dead | — | "Avatar unavailable" banner; text-mode affordance surfaced |
| **L6 + L2 both down** | Bare-local-reflex mode | Down | Clear multi-failure degraded state | Down | Stacked banners; no hidden capability degradation |
| **Signature verify fail on privileged overlay** | — | — | — | Rejects privileged overlay status; pack may still run as standard | "Signature unverified — reduced trust" banner |
| **Swap rollback** | Reverts phrase pools | Reverts salience | Reverts visual blend | Reverts to old persona | Picker shows rollback reason |

No deceptive silent operation anywhere. The user always sees a truthful capability state.

---

## 10. Open integration questions (surfaced, not resolved here)

Consolidated from the L2, L3, L6 system designs and cross-plane notes. Each needs a Don decision or a design follow-up before implementation closes on that surface.

1. **Persona-swap safe-boundary strictness.** Idle-only vs end-of-utterance. Referenced in L1 §16 and L6 §18. End-of-utterance reduces friction; Idle-only is safer for complex swaps that touch voice model.
2. **`AssistantStateMemory` as distinct domain vs subtype of `SessionMemory`.** L2 §20 flags this as an internal contradiction item.
3. **Rendering-surface choice.** Unreal / custom GL / hybrid. L3 OQ-L3-1. Don's gate — defer; trait boundary already lets implementation proceed.
4. **Anti-uncanny stabilizer on Lite posture.** ON/OFF. L3 OQ-L3-3.
5. **`presence.set_mode` — production vs debug-only.** L3 OQ-L3-4. X3 and L1 disagree; needs adjudication.
6. **Privileged-overlay path mechanism.** L6 §18 OQ9. How Isabelle's overlay is installed + signed + scoped.
7. **Observed-style confirmation UI.** L6 emits `persona_observed_style_proposed` but the L7 UI flow is not yet designed. Blocks I5's user-facing half.
8. **Vector-store vendor + embedding model per tier.** L2 OQ1 + OQ2.
9. **Provenance-chain merge strategy for cross-device sync.** CRDT vs op-log. L2 OQ5. Don's Phase 5 gate.

---

## 11. Implementation readiness summary

### L2 (Memory Kernel)
- **Ready:** SQLite DDL, `MemoryKernel` trait scaffolding, ingestion pipeline, retrieval pipeline (lexical + structured), TurnMemory/SessionMemory/DurableUserMemory/BehaviorMemory domain shells.
- **Pending on L5:** policy-adapter for `memory.read/write/edit/delete` gates — trait stub fine; real evaluator lands with L5.
- **Pending decisions:** vector vendor + embedding model (OQ-8); provenance sync strategy (OQ-9, Phase 5 gate).

### L3 (Presence Engine)
- **Ready:** `BehaviorScheduler` (must-own), `RenderingSurface` trait, reference headshot plugin behind the trait, viseme tick consumer, state machine `Idle/Acknowledging/Thinking/Speaking`, intensity-bounds clamp, anti-uncanny stabilizer.
- **Deferrable:** actual rendering-surface choice (OQ-3). Trait boundary lets implementation proceed.
- **Pending decisions:** anti-uncanny on Lite (OQ-4); `presence.set_mode` production-vs-debug (OQ-5).

### L6 (Persona Compiler)
- **Ready:** persona pack schema + YAML loader, validator, compiler core (visual/language/salience/routing/policy-defaults sub-artifacts), hot-reload state machine (`begin / commit / rollback`), signature verifier scaffold, `PersonaSummary` emitter.
- **Pending decisions:** privileged-overlay mechanism (OQ-6); observed-style confirmation UI (OQ-7, cross-team with L7).

### Shared — event bus
- Typed contracts for `persona_swap_begin`, `persona_swap_commit`, `persona_swap_rollback`, `compiled_persona_ready`, `memory_query`, `memory_hit`, `memory_edit_confirmed`, `memory_delete_confirmed`, `persona_observed_style_proposed`, `presence_state`, `turn_state_change` can land in `packages/event-bus`. No blockers.

---

## 12. Reference links

- file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_memory_kernel_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L3_presence_engine_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L6_persona_compiler_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L4_model_router_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L7_trust_ux_onboarding_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_L4_L5_L7_integration_notes.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/00_ORCHESTRATION_MAP.md
