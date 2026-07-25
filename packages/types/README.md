# @aether/types

**Status:** Wave 1 scaffold — hand-written placeholders. **Do not extend by hand after Wave 2.**

Single canonical TypeScript types surface for the Companion monorepo. Everything here will be generated from Rust structs in `packages/event-bus`, `packages/storage`, and the layer crates via `ts-rs` / `specta` through `tools/ts-bindings-gen/`.

## References

- `ARCHITECTURE.md` — the cross-layer event surface and type contracts.

## Wave 1 contents

- `SourceLayer`, `Projected`, `EventEnvelope<P>` mirroring `aether-event-bus` Rust types.

## Next wave

Wave 2 adds `ts-rs` derives to every Rust event/payload struct, wires the generator, and replaces this file wholesale.
