# @aether/l3-presence

**Status:** Wave 4 stub.

L3 owns presence — behavior scheduling, visemes, gaze/blink control. Borrowed rendering surface, custom control plane.

## References

- `ARCHITECTURE.md` — the L3 presence engine layer.
- `docs/ARCHITECTURE-V2.md` — current architecture detail.

## Wave 4 contents

- `PresenceTier` (3), `BehaviorClass` (9), `BehaviorFrame`.
- `PresenceEngine` + `RenderingSurface` traits.
- `L3Error`.

## Next wave

Wave 5+ — behavior scheduler with the 30–60 Hz update loop, Three.js rendering surface for OSS Preview, viseme-sync against `packages/media-engine` TTS output.
