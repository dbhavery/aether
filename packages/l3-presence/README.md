# @aether/l3-presence

**Status:** Wave 4 stub.

L3 owns presence — behavior scheduling, visemes, gaze/blink control. Borrowed rendering surface, custom control plane.

## References

- `ARCHITECTURE.md` — the L3 presence layer.

## Wave 4 contents (frame-rate engine stub)

- `PresenceTier` (3), `BehaviorClass` (9), `BehaviorFrame`.
- `PresenceEngine` + `RenderingSurface` traits.
- `L3Error`.

## L3.1 contents (`controller` module)

Narrow, session-scoped *macro presence* — distinct from the frame-rate `BehaviorClass` scheduler. Exposes the first visible signal of "what is Aether doing right now" that a CLI, desktop shell, or avatar can all bind to.

- `PresenceState { Quiet, Listening, Thinking, AwaitingApproval, Responding }`.
- `PresenceSnapshot { session_id, state, updated_at_ms, detail }`.
- `PresenceController` trait — `set_state`, `current`, `recent_transitions`, `clear_session`.
- `InMemoryPresenceController` — per-session state + bounded transition log (default cap 32).
- `render_presence(&PresenceSnapshot) -> String` — deterministic `[presence] <label>` / `[presence] <label> — <detail>` formatter.

The controller is caller-driven: it records whatever transitions the integration layer hands it and does not police ordering. That keeps L3.1 composable with future async paths (streaming tokens, barge-in, background tasks).

**Out of scope for L3.1:** idle timers, typing/speaking distinctions, avatar frames (already in `engine`), notification posture, multi-user switching.

## Next wave

Wave 5+ — behavior scheduler with the 30–60 Hz update loop, Three.js rendering surface for OSS Preview, viseme-sync against `packages/media-engine` TTS output, richer macro states (Speaking/Typing separation, barge-in, error/recovery), idle-timer transitions.
