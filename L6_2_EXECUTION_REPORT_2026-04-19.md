# Wave L6.2 — Persona Wired Into the L1 CLI Demo (Execution Report)

**Date:** 2026-04-19
**Branch:** `dev`
**Scope:** `apps/l1-cli/` only. L1, L4, L6 libraries unchanged.

---

## 1. How persona is compiled and applied

A new module `apps/l1-cli/src/persona.rs` owns all persona glue:

- `demo_profile()` — hard-coded `PersonaProfile` (name "Aurora", Warm tone, Balanced verbosity + stance, Occasional humor).
- `compile_demo_persona()` — calls `DefaultPersonaCompiler::new().compile(&demo_profile())`.
- `tier_from_rules(&str) -> RouterTier` — maps the string tier id produced by L6 (`"reflex"`, `"local-full"`, `"remote-standard"`, …) into L4's strongly-typed `RouterTier`, with unknown labels falling back to `Reflex`.
- `output_detail_from_persona(&CompiledPersona) -> OutputDetail` — reads `compiled.voice.rate` (which L6.1 derives from `Verbosity`) and maps it to `Terse`/`Balanced`/`Verbose`. Avoids extending any existing engine types.

`apps/l1-cli/Cargo.toml` now depends on `aether-l6-persona` alongside `aether-l1-interaction`, `aether-l4-router`, `aether-l5-policy`. `aether-l1-interaction` and `aether-l4-router` do **not** depend on L6 — the demo is the only crate in the tree that imports L1 + L4 + L6.

Startup flow (`main.rs`):

1. `compile_demo_persona()` (fail-fast if schema invalid).
2. `output_detail_from_persona(&compiled)` → pick verbosity mode.
3. `build_engine(&compiled)` — constructs `DefaultPolicyEngine` keyed on the persona id, wires a `ModelRouterAdapter` whose tier comes from `tier_from_rules(&compiled.routing.preferred_tier)`.
4. `print_banner(&compiled, detail)` — prints persona id, version, preferred tier, output mode, and the full compiled system prompt (unless Terse mode suppresses it).
5. Per-turn `TurnRequest.persona` is built from `compiled.persona_id`.
6. `print_turn_result(&result, detail)` — branches to Terse one-liner, Balanced multi-line with short policy label, or Verbose multi-line with full audit ids.

## 2. How routing now depends on persona

Previously `ModelRouterAdapter` was wrapped at a fixed `RouterTier::Reflex`. Now:

```rust
let tier = tier_from_rules(&compiled.routing.preferred_tier);
let adapter = ModelRouterAdapter::new(model_router, PROVIDER_LABEL, tier);
```

The mapping follows L6.1's rule table — `Cautious → local-small`, `Balanced → local-full`, `Bold → remote-standard` — and the actual string travels from `DefaultPersonaCompiler::compile_routing` all the way through to `RouteOutcome::tier` in the turn result. The CLI prints it verbatim, so a reader sees `tier=local-full` instead of the old constant `tier=reflex`.

Changing the profile in `persona::demo_profile()` (e.g. `stance = Stance::Bold`) immediately shifts the demo to `remote-standard` with no other code changes.

## 3. Persona-driven output formatting

`OutputDetail` gates three modes in `print_turn_result`:

- **Terse** (Verbosity::Terse) — one-line `turn-id [FinalState] → response` / `blocked: …`.
- **Balanced** (Verbosity::Balanced, default) — state trace, short decision label (`Allow`/`Ask`/`Deny`/`NeedsUpgrade`/`DraftOnly`), route, response or block.
- **Verbose** (Verbosity::Verbose) — everything above plus full decision detail with grant/audit/ticket ids.

Banner suppresses the compiled system prompt only in Terse mode so the demo stays useful as a quick sanity check while still exposing architecture detail when the persona invites it.

## 4. Tests & checks

New tests in `apps/l1-cli/src/persona.rs`:

| Test                                                            | Verifies                                                            |
|-----------------------------------------------------------------|----------------------------------------------------------------------|
| `tier_mapping_covers_all_seven_tiers`                           | Every `RouterTier` variant + unknown-label fallback.                |
| `balanced_persona_compiles_to_a_usable_local_full_tier`         | Demo profile → `preferred_tier = "local-full"` → `RouterTier::LocalFull`. |
| `balanced_persona_yields_balanced_output_detail`                | Demo profile → `OutputDetail::Balanced`.                            |
| `verbose_persona_yields_verbose_output_detail`                  | `Verbosity::Verbose` → `OutputDetail::Verbose`.                     |
| `terse_persona_yields_terse_output_detail`                      | `Verbosity::Terse` → `OutputDetail::Terse`.                         |

Updated engine tests in `apps/l1-cli/src/main.rs` now build the engine from the compiled persona and assert that `RouteOutcome.tier` equals `compiled.routing.preferred_tier` — i.e. persona-derived tier actually surfaces through the turn result.

| Check                                                           | Result                       |
|-----------------------------------------------------------------|------------------------------|
| `cargo fmt --all`                                               | clean                        |
| `cargo check --workspace`                                       | clean                        |
| `cargo test -p aether-l1-cli`                                   | 8 passed (5 new + 3 updated) |
| `cargo test --workspace`                                        | all green, 0 failures        |
| `python tools/lint-layer-boundaries/check.py`                   | OK, 0 violations             |

Manual REPL run confirmed: banner prints persona/version/tier + full system prompt; turn results show `tier=local-full` driven by the persona.

## 5. Limitations & TODOs

- **Hard-coded profile.** No config file, no env-var override, no `--persona <id>` flag. A 20-line `serde_yaml` load from `apps/l1-cli/personas/*.yaml` would close that out.
- **Tier mapping is a string match.** If L6 ever introduces new tier labels, `tier_from_rules` silently falls back to `Reflex`. Swapping L6's routing type to the L4 enum would remove the string bridge entirely (but would create a sibling-engine edge that L6 currently avoids — a deliberate deferral).
- **Policy defaults not yet installed.** `CompiledPersona.policy_defaults` is available but `DefaultPolicyEngine` is still built from `EngineConfig::wave3_default`. Wiring `policy_defaults.per_capability_defaults` into the `EngineConfig` would let the persona's stance actually alter Ask/Auto decisions.
- **No persona swap at runtime.** `PersonaCompiler`'s hot-reload state machine (begin_swap / commit_swap) is untouched.
- **Behavior map + voice config go nowhere.** `CompiledBehaviorMap` wants an L3 presence consumer; `CompiledVoiceConfig` wants media-engine TTS. Both are noops today.
- **Output detail is inferred from voice rate.** A cleaner signal would be a dedicated `CompiledPrompts.verbosity_level` field on L6's side — noted, not yet required.

## 6. Recommended next session

**L3.1 — presence state machine slice.**

- Add `Active / Idle / Away` states + a simple time-based scheduler in `packages/l3-presence/`.
- Print presence transitions in the CLI (persona-driven intensities from `CompiledBehaviorMap.intensities` would feed this naturally).
- Keep L3 engine-only; wiring stays in the demo.

Alternative: **persona policy defaults wiring.** Thread `CompiledPersona.policy_defaults.per_capability_defaults` into `EngineConfig` so the persona's stance actually influences evaluator outcomes (not just the tier the router picks).

I recommend **L3.1** — it adds the third engine to the demo surface and sets up a visible avatar dimension the README has promised since day one.

---

**Status:** L6.2 complete. Working tree ready for commit.
