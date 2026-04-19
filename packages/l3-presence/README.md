# @aether/l3-presence

**Status:** Wave 4 stub.

L3 owns presence — behavior scheduling, visemes, gaze/blink control. Borrowed rendering surface, custom control plane.

## References

- `planning/plans/L3_presence_engine_system_design.md`
- `planning/plans/implementation_prep/L3_interface_pack.md`

## Wave 4 contents

- `PresenceTier` (3), `BehaviorClass` (9), `BehaviorFrame`.
- `PresenceEngine` + `RenderingSurface` traits.
- `L3Error`.

## Next wave

Wave 5+ — behavior scheduler with the 30–60 Hz update loop, Three.js rendering surface for OSS Preview, viseme-sync against `packages/media-engine` TTS output.
