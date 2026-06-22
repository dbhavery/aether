# @aether/media-engine

**Status:** Wave 1 placeholder — trait surface sketches only.

STT/TTS/VAD wrappers with Aether's custom chunk-timing and viseme-sync control plane. Borrowed inference models are isolated behind these traits; the control plane is custom (borrowable-but-isolated, per `ARCHITECTURE.md`).

## References

- `ARCHITECTURE.md` — the media surface and the L1/L3 layers it serves.
- `docs/ARCHITECTURE-V2.md` — current architecture detail.

## Wave 1 contents

- `SttChunk`, `TtsChunk`, `VadState` data shapes.
- `MediaError` placeholder.
- No adapters, no borrowed-model deps, no cargo features.

## Next wave

Wave 3+ lands `SttAdapter` / `TtsAdapter` / `VadAdapter` traits, feature-gated borrowed-model wrappers, and the chunk/interruption state machine consumed by L1 and L3.

## Deferred cargo.toml additions

See `Cargo.toml.extra` placeholder; Wave 3 will add feature flags and model deps.
