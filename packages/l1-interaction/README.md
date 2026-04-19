# @aether/l1-interaction

**Status:** Wave 4 stub. Traits + key enums only.

L1 owns interaction timing, the turn state machine, and reflex routing.

## References

- `planning/plans/L1_interaction_timing_system_design.md`
- `planning/plans/implementation_prep/L1_interface_pack.md`

## Wave 4 contents

- `TurnId`, `TurnState` (19 variants), `ReflexClass`, `TimingBudgets`.
- `InteractionEngine` trait with 5 method signatures.
- 5 adapter traits: `ReflexClassifier`, `Stt`, `Tts`, `ModelRouterClient`, `PresenceClient`.
- `InteractionEvent` + `InteractionEventKind`.
- `L1Error`.

## Next wave

Wave 5 — turn loop implementation against `DefaultPolicyEngine`, STT/TTS adapter wiring, reflex classifier stub.
