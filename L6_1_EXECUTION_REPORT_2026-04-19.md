# Wave L6.1 — First Persona Compiler Slice (Execution Report)

**Date:** 2026-04-19
**Branch:** `dev`
**Scope:** `packages/l6-persona/` only. L1/L4/L5 unchanged.
**Chosen engine:** **L6 Persona** (not L3 Presence).

---

## 1. APIs added

New modules in `packages/l6-persona/src/`:

- **`profile.rs`** — minimal typed input surface:
  - `PersonaProfile { persona_id, version, name, description, tone, verbosity, stance, humor }`
  - `Tone::{Formal, Neutral, Warm}`
  - `Verbosity::{Terse, Balanced, Verbose}`
  - `Stance::{Cautious, Balanced, Bold}`
  - `Humor::{Dry, Occasional, Playful}`
  - `PersonaProfile::simple(id, name)` convenience constructor.

- **`default_compiler.rs`** — `DefaultPersonaCompiler`:
  - `new()` → stateless compiler.
  - `compile(&self, &PersonaProfile) -> Result<CompiledPersona, L6Error>`.

All re-exported from the crate root (`aether_l6_persona`).

The Wave 4 stub types (`PersonaPack`, `PersonaCompiler` trait, `SwapState`, the 6 artifact structs) are untouched. The new slice composes with them: `DefaultPersonaCompiler::compile` returns the same `CompiledPersona` type the existing trait promised.

## 2. How persona is modeled

Five dials → seven typed artifacts:

| Dial        | Affects                                                                 |
|-------------|-------------------------------------------------------------------------|
| `tone`      | System prompt voice line; reflex-template wording; `voice.voice_id`.   |
| `verbosity` | System prompt length line; memory `recent_turns` salience; voice rate.  |
| `stance`    | Routing preferred/max tier; tool allow-list; policy privacy posture; memory `safety_notes` salience. |
| `humor`     | System prompt humor line; behavior `playfulness` intensity.            |
| `name` / `description` | Interpolated verbatim into the system prompt.                |

Every rule is a small `match` over the dials. No LLMs, no external files, no randomness. A guardrail line stating *"all side-effectful actions require L5 authorization"* appears in every compiled system prompt — the persona surface is explicit that it is not an escape hatch around L5.

Determinism is preserved by:
- Sorting all `Vec<(String, _)>` outputs (reflex templates, behavior intensities, memory salience, tool list).
- Using only ordered collections in the artifacts (the single `HashMap` — `PersonaCompiledPolicyDefaults::per_capability_defaults` — is a type pinned by L5 and is compared set-wise in the determinism test).

## 3. How other layers will consume persona

Future wire-up points, all **already typed** by the existing stub:

- **L1 (interaction):** turn framing could thread `CompiledPrompts.system` into the first prompt sent to the router; reflex templates feed `ReflexClassifier::AckOnly / ShortReply / Deflect` responses.
- **L3 (presence):** `CompiledBehaviorMap.intensities` shape avatar animation / visual weights.
- **L4 (router):** `CompiledRoutingRules.{preferred_tier, max_tier}` inform tier selection and cost caps.
- **L5 (policy):** `PersonaCompiledPolicyDefaults` is delivered on persona swap; the policy engine merges it under the preset's precedence ordering.
- **Media engine:** `CompiledVoiceConfig.{voice_id, rate}` drives TTS selection.
- **L2 (memory):** `CompiledMemoryHints.domain_salience` biases retrieval.

This slice does **not** wire into any of those yet — that's the next wave. L6 has no sibling-engine dependencies; the only external type it imports from L5 is `PersonaCompiledPolicyDefaults`, which was already present before this wave.

## 4. Tests & checks

`packages/l6-persona/tests/default_compiler.rs` — 8 tests:

| Test                                                      | Verifies                                                                 |
|-----------------------------------------------------------|--------------------------------------------------------------------------|
| `compilation_is_deterministic`                            | Two compiles of the same profile match field-by-field (HashMap compared set-wise). |
| `different_profiles_produce_different_outputs`            | `warm_bold` vs `formal_cautious` produce different prompts/routing/voice/tools. |
| `empty_name_is_rejected`                                  | Whitespace-only name → `L6Error::Schema`.                                 |
| `stance_shifts_routing_tier_up`                           | Cautious → `local-small` / `local-full`; Bold → `remote-standard` / `remote-premium`. |
| `system_prompt_includes_name_description_and_policy_guardrail` | Prompt contains name, description, and the L5 authorization line. |
| `cautious_persona_has_narrower_tool_allow_list`           | Cautious tools ⊂ Bold tools; `shell.exec` only on Bold.                  |
| `reflex_templates_are_sorted_and_non_empty`               | Templates sorted by reflex-class key, all non-empty.                     |
| `policy_defaults_never_auto_approve_shell_exec`           | Every profile yields `ShellExec = Deny`.                                 |

| Check                                                      | Result                 |
|------------------------------------------------------------|------------------------|
| `cargo fmt --all`                                          | clean                  |
| `cargo test -p aether-l6-persona`                          | 9 passed (8 + smoke)   |
| `cargo test --workspace`                                   | all green, 0 failures  |
| `python tools/lint-layer-boundaries/check.py`              | OK, 0 violations       |

## 5. Limitations & future work

- **Dials are ad-hoc.** Five enums instead of the full `17_persona_pack_schema.md` surface. YAML pack parsing, overlays, and signature verification remain for later waves.
- **Rules are hand-written.** No rule-inference, no schema-driven generation. Intentional for a transparent first slice.
- **`PersonaCompiler` trait** still unimplemented by `DefaultPersonaCompiler` — only the simpler `compile(&PersonaProfile)` inherent method. Plugging into the trait needs `begin_swap` / `commit_swap` state machine plumbing, which is a full wave on its own.
- **HashMap ordering.** `policy_defaults.per_capability_defaults` is a `HashMap` pinned by L5 — byte-level equality across runs would require swapping L5's type to `BTreeMap` or using a deterministic serialization pass. Compared set-wise for now.
- **No consumer wiring.** The L1 CLI demo still hard-codes persona name/session strings; L6.2 should wire `CompiledPrompts` / `CompiledRoutingRules` into the demo output.

## 6. Recommended next session

**L6.2 — wire persona into the L1 CLI demo.**

- Load a hard-coded `PersonaProfile` at app startup, compile it once via `DefaultPersonaCompiler`.
- Thread `CompiledRoutingRules.preferred_tier` through `ModelRouterAdapter` so the demo picks a tier from the persona rather than a constant.
- Print `CompiledPrompts.system` once at the banner so readers see the persona "voice" alongside the decision trace.
- Optionally alter `print_turn_result` verbosity based on `Verbosity`.

Alternative: **L3.1 — presence state machine.** Active/Idle/Away + a tiny scheduler. Useful alongside persona, but waiting to ride one demo pass with L6.2 lands more visible value in less time.

---

**Status:** L6.1 complete. Working tree ready for commit.
