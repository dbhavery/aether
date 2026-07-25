# @aether/event-bus

**Status:** Wave 1 scaffold — shapes only, no runtime logic.

Typed cross-layer event substrate. Every layer (L1–L7, Media, Core) publishes through this bus; no sibling-layer imports.

## References

- `ARCHITECTURE.md` — the cross-layer event surface and the L1 interaction layer.

## Wave 1 contents

- `SourceLayer`, `Projected`, `EventEnvelope<P>`, `BusError` — shapes referenced by layer scaffolds.
- No channel, no subscribe/publish, no tokio runtime.

## Next wave

Wave 2 introduces per-layer payload enums (`L1Event`, `L2Event`, …), tokio broadcast channels per `SourceLayer`, replayable cursors, `ts-rs` derives for TS binding generation into `packages/types/`.
