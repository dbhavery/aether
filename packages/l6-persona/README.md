# @aether/l6-persona

**Status:** Wave 4 stub.

L6 compiles persona packs into 6 typed artifacts consumed by L1/L3/L4/L5.

## References

- `planning/plans/L6_persona_compiler_system_design.md`
- `planning/plans/implementation_prep/L6_interface_pack.md`
- `planning/17_persona_pack_schema.md`

## Wave 4 contents

- `PersonaId`, `PersonaPack`, `CompiledPersona` + 6 artifact structs.
- `SwapState` (6 variants) for hot-reload.
- `PersonaCompiler` trait.
- `L6Error`.

## Next wave

Wave 5+ — deterministic compile pipeline (YAML → typed artifacts), signature verification for privileged overlays, hot-reload state machine driver, `persona_swap_commit` bus event emission.
