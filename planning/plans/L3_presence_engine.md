# L3 — Presence Engine (controller, not renderer)

**Status:** draft
**Last updated:** 2026-04-18
**Layer type:** must-own (doctrine §1.1 — "presence controller")
**Depends on:** L1 (consumes interaction state), L6 (persona parameters), Media engine (visemes, tts chunks).
**Blocked by:** rendering-engine choice (borrowable surface; TBD in OPEN_QUESTIONS).

---

## Purpose

The presence **controller** — the layer that maps assistant internal state to visible, felt social behavior. Gaze, blink, micro-motion, speaking emphasis, idle breathing, anti-uncanny stabilization. This is not the rendering layer; the renderer is borrowable. The controller is not.

## Why must-own

The difference between "uncanny valley" and "companion-grade" is entirely in the control layer — not the rendering fidelity. Anyone can license MetaHuman. Nobody has a convincing social presence scheduler. This is a moat layer, full stop.

## Boundaries

**Owns:**
- Presence state machine (linked to but distinct from L1 interaction state).
- Gaze scheduler (look-at-user / look-away / down-think / joint-attention).
- Blink generator (rate, variance, suppression during speaking emphasis).
- Micro-motion scheduler (idle breathing, weight shift, small head motion).
- Speaking emphasis planner (consuming visemes + prosody envelope).
- Anti-uncanny stabilization (smoothing, jitter, motion-rest tradeoff).
- Gesture abstraction layer (typed gesture events → renderer-specific actions).

**Does not own:**
- Rendering surface (Unreal / custom GL / Three.js / Live2D — borrowable).
- Rig itself (MetaHuman, custom, or otherwise).
- TTS or viseme generation (Media engine).
- Avatar asset pack format (L6 persona compiler contributes).

## Dependencies

- **L1** — subscribes to turn-state transitions.
- **Media engine** — consumes `viseme_chunk`, `tts_chunk`, VAD events.
- **L6** — avatar pack supplies rig parameters and style envelope.
- **Rendering surface** — downstream consumer of typed gesture events.

## Borrowable vs custom

| Piece | Decision |
|---|---|
| Rendering surface | **Borrow.** WebGL/Three.js for OSS Preview; Unreal-class / custom GL for Pro (TBD). |
| Rig format | **Borrow** standards (GLTF + custom extensions for visemes). |
| Controller state machine | **Custom.** Non-negotiable. |
| Blink/gaze/micro-motion schedulers | **Custom.** |
| Viseme timing adapter | **Custom.** |
| Anti-uncanny stabilizer | **Custom.** Doctrine surface. |

## Key risks

1. **Uncanny valley.** Too much motion = creepy; too little = dead. Mitigation: rest-state default + motion budget + usability testing loop.
2. **Renderer lock-in creep.** Unreal convenience tempts Pro toward dependency. Mitigation: controller outputs typed gesture events; renderers are adapters.
3. **Viseme-audio drift.** TTS latency variance desyncs lips. Mitigation: controller buffers and schedules against audio clock, not wall clock.
4. **Performance budget blowout.** Full avatar pegs GPU on Lite tier. Mitigation: tier-aware motion budget (Lite = headshot + low frame count).
5. **Idle-creepiness.** Avatar staring blankly between turns. Mitigation: idle micro-animation + gaze-wander profile per persona.

## Sequencing

1. **P0 (OSS Preview)** — headshot-level avatar, borrowed lip-sync stack (MuseTalk / TalkingHead / Wav2Lip), simple gaze + blink. Controller in TypeScript. Goal: prove the feel.
2. **P1 (Pro Phase 0)** — controller in Rust; typed gesture events; adapter for OSS Preview renderer.
3. **P2 (Pro Phase 1)** — custom blink/gaze/micro-motion schedulers; anti-uncanny stabilizer v1.
4. **P3 (Pro Phase 2)** — Pro-grade rendering surface (Unreal-class or custom GL — decision point); full-body later.
5. **P4 (Pro Phase 3+)** — mood/presence coupling with memory state; Isabelle-specific presence profile.

## Acceptance criteria

- Idle loop never freezes — avatar alive across any 60 s silent window.
- Blink rate between 10–20 per minute with natural variance; suppressed during speaking emphasis peaks.
- Viseme-to-audio alignment within ±40 ms p95.
- Framerate targets: Lite 24 fps, Balanced 30 fps, Full 60 fps — maintained under typical CPU/GPU load.
- Rendering surface swap (OSS Preview → Pro) does not require controller changes.
- Zero uncanny failures in structured user-testing checklist (gaze fixation, staring, mouth-frozen, etc.).

## Open decisions for executing agent

- Rendering engine for Pro avatar — surfaces in OPEN_QUESTIONS.
- Whether full-body is a Pro Phase 2 or Pro Phase 3+ target.
- Style envelope schema (how persona expresses in motion).

## Reference specs

- `file:///C:/Users/dbhav/Projects/aether-planning/11_avatar_presence.md`
- `file:///C:/Users/dbhav/Projects/aether-planning/14_performance_tiers_vram.md`
- `file:///C:/Users/dbhav/Projects/aether-planning/01_product_doctrine.md`
