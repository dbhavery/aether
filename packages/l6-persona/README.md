# @aether/l6-persona

**Status:** Wave 4 stub.

L6 compiles persona packs into 6 typed artifacts consumed by L1/L3/L4/L5.

## References

- `ARCHITECTURE.md` — the L6 persona compiler layer.
- `docs/PERSONA-SCHEMA.md` — the persona pack schema.
- `docs/adr/ADR-0012-persona-delivery-download-on-demand.md` — persona delivery.

## Wave 4 contents

- `PersonaId`, `PersonaPack`, `CompiledPersona` + 6 artifact structs.
- `SwapState` (6 variants) for hot-reload.
- `PersonaCompiler` trait.
- `L6Error`.

## Wave L6.1 — first deterministic compilation slice

`DefaultPersonaCompiler` + `PersonaProfile` land a minimal typed input
that compiles deterministically into all six artifacts plus L5 policy
defaults. No LLM calls, no network, no policy decisions — rules are
small `match` statements over five dials (name, tone, verbosity, stance,
humor).

```rust
use aether_l6_persona::{DefaultPersonaCompiler, PersonaProfile, Stance, Tone};

let mut profile = PersonaProfile::simple("aurora", "Aurora");
profile.tone = Tone::Warm;
profile.stance = Stance::Bold;

let compiled = DefaultPersonaCompiler::new().compile(&profile)?;
println!("{}", compiled.prompts.system);
println!("{}", compiled.routing.preferred_tier);  // "remote-standard"
```

Invariants this slice enforces:

- Compilation is deterministic — same `PersonaProfile` → structurally
  identical `CompiledPersona` across runs.
- `ShellExec` defaults to `Deny` on every persona; L5 has the final say
  but L6 never proposes Auto for it.
- Reflex templates are sorted so downstream consumers don't depend on
  insertion order.
- Empty-name profiles are rejected at compile time.

## Next wave

Wire this compiler into the L1 CLI demo (L6.2) so the demo's reply
formatting and reflex banners pick up the compiled persona. After that,
Wave 5+ — full YAML pack parsing, signature verification for privileged
overlays, hot-reload state machine driver, `persona_swap_commit` bus
event emission.
