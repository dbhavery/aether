# L6 — Persona Compiler

**Status:** draft
**Last updated:** 2026-04-18
**Layer type:** must-own (doctrine §1.6)
**Depends on:** L1 (consumes compiled ack / interruption phrase pools + timing hints), L2 (consumes memory salience rules + isolation flags), L3 (consumes avatar presence parameters + state transitions), L4 (consumes model-router tier preferences + temperature), L5 (consumes capability-matrix defaults + approval-mode preferences per persona), L7 (persona-picker UX + onboarding choices → compiler input).
**Blocked by:** persona pack schema lock (17_persona_pack_schema.md already v1), cross-layer parameter contract freeze.

---

## Purpose

Own the translation from persona packs + onboarding choices to runtime parameters consumed by every other layer. The compiler reads a validated persona pack (per `17_persona_pack_schema.md`), merges it with user onboarding selections and (for Isabelle) the privileged-profile overlay, and produces a typed, versioned `CompiledPersona` artifact: system prompts, phrase pools, animation parameters, voice settings, memory salience rules, privacy posture, and policy-matrix defaults. Hot-reload on persona change is a first-class path — switching persona must re-parameterize every consumer layer atomically.

## Why must-own

Personas are the product's identity surface; their behavior is the felt relationship (`01_product_doctrine.md §1.3`). A close-enough SaaS "character" library sets the ceiling of feel, timing, and trust. The compiler is the bridge between the authoring surface (persona packs, onboarding) and the runtime consumers — if any layer re-parses the YAML or interprets persona semantics itself, drift and inconsistency compound. One compiler, one typed artifact, every consumer pure downstream.

## Boundaries

**Owns:**
- Persona pack loader + validator (enforces `17_persona_pack_schema.md` rules; rejects malformed packs).
- Schema migration for forward-compat (v1 → vN filling defaults).
- Onboarding-choice merger (user-chosen persona + style overrides + preset selection → compiler input).
- `CompiledPersona` typed artifact emitted to the runtime (serde/TS-typed).
- Cross-layer parameter fan-out contract (each consumer layer has a named sub-struct).
- Hot-reload orchestration: emits `persona_swap_begin` / `persona_swap_commit` events; coordinates atomic re-parameterization.
- Privileged-profile overlay mechanism (Isabelle as overlay on top of a base public persona, not a separate codebase).
- Asset-provenance surfacing to L7 (metadata.yaml → trust-center disclosures).
- Persona-picker enumeration API (lists available packs + sample.wav preview refs).

**Does not own:**
- Persona authoring tools (scaffold CLI, inpaint pipeline — `17_* §generation pipeline`).
- The actual runtime use of parameters (each consumer layer owns its runtime).
- LLM inference (L4) or system-prompt execution semantics.
- Rendering the avatar (L3 / rendering engine).
- TTS synthesis (Media engine).
- Memory storage / retrieval mechanics (L2).
- Policy decision logic (L5); L6 only supplies the persona's default matrix — L5 decides.

## Dependencies

- **Persona pack schema** (`17_persona_pack_schema.md`) — canonical source of truth for pack format.
- **L1 timing** — consumes `ack_phrase_pool`, `interruption_phrase_pool`, pacing hints.
- **L2 memory kernel** — consumes `memory.isolation`, `retention_days`, `persona_can_forget`, salience rules.
- **L3 presence engine** — consumes `avatar.presence.*`, `idle_blink_rate_hz`, state transition clip manifest.
- **L4 model router** — consumes `llm_preferences.preferred_tier`, `temperature`, `max_output_tokens`.
- **L5 policy engine** — consumes persona-scoped approval-mode defaults + preset selection (Observer / Assistant / etc.).
- **L7 trust UX** — consumes `metadata.yaml` for disclosures; surfaces persona picker + sample previews.
- **Event bus** — for `persona_swap_*` coordination.

## Borrowable vs custom

| Piece | Decision |
|---|---|
| YAML parser | **Borrow** `serde_yaml` (Rust) — safe, typed. |
| Schema validation | **Custom (Rust)** — 17_* rules (landmark bounds, wav length, portrait square-ratio, id-matches-folder) encoded as typed validators. |
| Compiled-persona IDL | **Custom.** Typed Rust struct + serde → TS binding via `ts-rs` or similar. |
| TS binding generator | **Borrow** `ts-rs` or `specta`. |
| Hot-reload event plumbing | **Custom** on top of the shared event bus. |
| Prompt templating | **Custom** — persona `system_prompt` is literal; no Jinja-style runtime templating in P0–P2 (rejected: hidden templating is a red-team / drift risk). |
| Voice engine parameter resolution | **Custom adapter layer** — maps `voice.yaml` engine-agnostic knobs to active TTS engine (XTTS/Piper/Coqui) via named adapters. |
| Phrase-pool randomization | **Custom** — persona-scoped RNG with recency penalty (contract with L1). |
| Landmark extraction (preprocessing) | **Borrow** face-landmark library behind interface (not the compiler itself — `17_* generation pipeline`). |
| Metadata / license audit | **Custom** — must block ship if provenance missing. |
| Isabelle overlay | **Custom** — private overlay merged at compile time if privileged-profile flag present. |

## Key risks

1. **Schema drift between authoring and runtime.** Pack author edits YAML, compiler silently fills wrong default. **Mitigation:** strict enum validation, required fields explicit, unknown-field warnings logged; schema_version check at load; CI golden-file tests per shipped persona.
2. **Hot-reload races.** Layer A reads new persona, Layer B still on old, leading to mixed-state turn. **Mitigation:** two-phase swap — `persona_swap_begin` quiesces new turns, compiler publishes `CompiledPersona`, all consumers acknowledge, then `persona_swap_commit` releases turn intake; if any consumer fails to ack in 500 ms, rollback + error.
3. **Cross-layer parameter incompleteness.** A new consumer layer expects a field the compiler doesn't produce. **Mitigation:** typed contract, exhaustiveness test — compiler produces all fields for the full `CompiledPersona` struct; consumer layers fail closed on unknown missing fields; schema additions require matching compiler + consumer PR.
4. **Privileged-profile leakage.** Isabelle overlay merged into a public pack by mistake → private system prompt shipped. **Mitigation:** overlay path separate from public personas dir; `privileged_profile: true` flag required + audit-logged via L5; build-time lint prevents Isabelle assets from entering OSS Preview or Pro distributables.
5. **Phrase-pool repetition.** Compiler ships pool; L1 uses it; repetition still happens without recency state. **Mitigation:** compiler emits pool + recency-penalty config; L1 owns state but contract is L6's responsibility.
6. **Prompt-injection via persona system_prompt.** A user-imported community pack contains a jailbreak. **Mitigation:** signed first-party packs ship trusted; unsigned / imported packs flagged `unverified` in trust center; system_prompt size capped; untrusted-context tagging propagated to L4.
7. **License/provenance gap at ship.** `metadata.yaml` missing causes legal exposure. **Mitigation:** loader rejects packs with incomplete provenance; pre-ship audit check is a CI gate; aggregator generates `LICENSE-PERSONAS.md` automatically.
8. **Schema v1 → vN migration bug.** Old pack loaded, new field filled with wrong default. **Mitigation:** migration is explicit code per version bump; test fixtures for every historical schema version retained.

## Sequencing

1. **P0 (OSS Preview)** — loader + validator for schema v1; compile to a minimal `CompiledPersona` covering system prompt, phrase pools, voice params, avatar portrait + states; single active persona at runtime (hot-swap optional); ship 2–3 public packs; metadata audit gate enforced.
2. **P1 (Pro Phase 0)** — full `CompiledPersona` struct covering every consumer layer; TS bindings emitted; persona picker enumeration API; onboarding-choice merger wired into L7 onboarding flow.
3. **P2 (Pro Phase 1)** — hot-reload two-phase swap protocol live; recency-penalty config for L1; privacy-posture + memory salience rules fanned to L2; policy-matrix defaults fanned to L5.
4. **P3 (Pro Phase 2)** — Isabelle privileged-profile overlay mechanism; build-time lint preventing private-asset leak; signed-pack verification for first-party distribution; unverified-pack sandboxing.
5. **P4 (Pro Phase 3+)** — pack marketplace adapter (read-only initially), per-persona affect curves, multi-voice support, gesture-library fields (schema v2 with migration path); cross-device persona sync contract (with L-sync).

## Acceptance criteria

- **Schema validation coverage:** 100% of `17_persona_pack_schema.md` REQUIRED fields + validation rules enforced; malformed packs rejected with actionable error messages (tested via fuzz + golden fixtures).
- **Cross-layer parameter completeness:** `CompiledPersona` struct exposes a named field set for each of L1, L2, L3, L4, L5, L7; exhaustiveness test asserts no consumer reads an unmapped field.
- **Hot-reload atomicity:** persona swap produces zero mixed-persona turns; verified by event-log audit — every post-`persona_swap_commit` `turn_start` carries the new persona id; p95 swap time ≤500 ms including consumer ack.
- **Hot-reload rollback:** if any consumer fails to ack within 500 ms, swap aborts and old persona remains active; tested.
- **Provenance gate:** no pack with incomplete `metadata.yaml` compiles; CI blocks ship.
- **Privileged-profile isolation:** OSS Preview and Pro public distributables contain zero Isabelle overlay artifacts; verified by build-time lint + manifest diff.
- **Golden-file stability:** each shipped persona produces a byte-identical `CompiledPersona` across builds; detects accidental default drift.
- **Schema migration correctness:** every historical schema version loads and produces a valid `CompiledPersona`; regression-tested.
- **Persona-picker enumeration:** API returns pack id, display_name, tagline, sample.wav path, archetype for every installed pack in ≤50 ms for up to 50 packs.
- **Unverified-pack handling:** imported unsigned packs load in `unverified` state; surfaced to trust center; system_prompt treated as untrusted-context for L4.

## Open decisions for executing agent

- TS-binding generator choice (`ts-rs` vs `specta` vs hand-written); recommend `ts-rs` for tighter Rust coupling.
- Hot-reload transport: is `persona_swap_begin` a blocking event-bus call with consumer ack, or a best-effort broadcast with timeout? Recommend blocking with 500 ms timeout.
- First-party signing scheme for trusted packs (Ed25519 + key pinned in build vs keychain-managed).
- Whether P0 ships with hot-reload or single-persona-at-start-up (trade-off: OSS Preview scope).
- Exactly which sub-structs L7 consumes vs. reads directly from `metadata.yaml`.
- How persona-scoped RNG seeding interacts with memory-layer reproducibility (L2 coordination).

## Reference specs

- file:///C:/Users/dbhav/Projects/aether-planning/17_persona_pack_schema.md
- file:///C:/Users/dbhav/Projects/aether-planning/04_user_modes.md
- file:///C:/Users/dbhav/Projects/aether-planning/05_ux_principles.md
- file:///C:/Users/dbhav/Projects/aether-planning/09_realtime_interaction.md
- file:///C:/Users/dbhav/Projects/aether-planning/10_memory_architecture.md
- file:///C:/Users/dbhav/Projects/aether-planning/11_avatar_presence.md
- file:///C:/Users/dbhav/Projects/aether-planning/18_model_router_spec.md
- file:///C:/Users/dbhav/Projects/aether-planning/01_product_doctrine.md
- file:///C:/Users/dbhav/Projects/aether-planning/inbox_2026-04-18b/aether_cross_systems_spec.md
