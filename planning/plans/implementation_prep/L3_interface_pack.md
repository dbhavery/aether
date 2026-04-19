# L3 Presence Engine — Interface Pack

> **Status:** Implementation-prep scaffold (interfaces only, no code).
> **Sources:** file:///C:/Users/dbhav/Projects/aether-planning/plans/L3_presence_engine_system_design.md, file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md, file:///C:/Users/dbhav/Projects/aether-planning/plans/L6_persona_compiler_system_design.md, file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md, file:///C:/Users/dbhav/Projects/aether-planning/plans/X3_tauri_architecture.md, file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_L3_L6_integration_notes.md
> **Scope:** Typed interface surface for the L3 behavior scheduler and its pluggable rendering-surface trait. Implementation specifics (shader code, animation blending math, asset pipelines) are out of scope.

---

## 1. Purpose

L3 is Aether's **Presence Engine** — the subsystem that turns higher-level conversational state (who is speaking, what turn phase we are in, what persona is loaded, what policy posture is active) into a continuous stream of **behavior frames** that a pluggable rendering surface (Unreal, WebGL, hybrid, or headless) consumes to produce an on-screen presence.

Presence is a *behavior* concern, not a *pixel* concern. L3 decides *what* the avatar should be doing (listening, micro-nodding, preparing to speak, holding for repair, etc.) and with what intensity bounds; it does **not** own the final rasterization. The rendering surface is a swappable trait so the same behavior schedule can be driven against Unreal in production, a WebGL shim in dev, or a null surface in tests.

This document defines the inbound events L3 consumes, the outbound events it emits, and the typed contracts (Rust-style pseudo-traits and structs) that implementers and adjacent layers should code against.

---

## 2. Primary responsibilities

**L3 owns:**
- **Behavior scheduler** — selects the active `BehaviorClass` per tick based on turn state, persona, policy posture, and health.
- **State → behavior mapping** — deterministic table (with persona-modulated intensity) from L1 turn states and L6 compiled-persona params to one of the 9 behavior classes (see `L3_presence_engine_system_design.md`).
- **Anti-uncanny stabilizer** — enforces intensity bounds, smoothing, and dwell-time minima so micro-behaviors do not jitter or exceed persona/policy ceilings. Emits `anti_uncanny_correction_applied` when clipping occurs.
- **Tier-aware frame emission** — runs at 60 fps on Full tier, 30 fps on Standard, 10 fps on Lite, and a still-frame/portrait-only mode on Minimal. Degrades smoothly on `tier_signal`.
- **Rendering-surface abstraction** — owns a single `RenderingSurface` trait object, forwards `BehaviorFrame`s to it, collects surface health back.

**L3 does NOT own:**
- **Turn state** — produced by L1 (`L1_interaction_timing_system_design.md §5`).
- **Persona compilation** — produced by L6 (`CompiledVisual` in `L6_persona_compiler_system_design.md`).
- **Audio synthesis / TTS / viseme generation** — produced by the media engine; L3 only *consumes* `viseme_tick`.
- **Policy decisions** — produced by L5 (`L5_policy_engine_system_design.md §10`); L3 consumes only the posture subset that affects visible behavior.

---

## 3. Inbound interfaces

Events L3 subscribes to on the core event bus.

**From L1 (interaction timing):**
- `turn_state_change` — `{ prev: TurnState, next: TurnState, at_ms, reason }`. Shape per `L1_interaction_timing_system_design.md §5`.
- `barge_in_detected` — `{ at_ms, source: "vad" | "keypress" }`.
- `repair_started` — `{ reason_code, at_ms }`.
- `repair_resolved` — `{ reason_code, resolved_by, at_ms }`.
- `ack_phrase` — `{ phrase_id, at_ms }` (drives micro-ack behaviors, not speech).

**From L6 (persona compiler):**
- `compiled_persona_ready` — `{ persona_id, compiled_visual: CompiledVisual, version }`.
- `persona_swap_begin` — `{ from_persona_id, to_persona_id, crossfade_ms }`.
- `persona_swap_commit` — `{ persona_id }`.

**From L5 (policy engine) — posture subset only:**
- `policy_decision` — filtered for fields affecting visible behavior: `{ presence_posture: "normal" | "restrained" | "masked" | "concealed", intensity_ceiling: f32, visible_identity_ok: bool }`.
- `grant_revoked` — `{ grant_id, scope }` (may force posture recompute).
- `emergency_revoke_all` — `{ at_ms }` (forces immediate `Concealed` posture + behavior halt).

**From media engine:**
- `viseme_tick` — `{ viseme_id, weight: f32, at_ms, deadline_ms }`.
- `tts_chunk_done` — `{ chunk_id, at_ms }`.
- `vad_state` — `{ speaking: bool, at_ms }`.

**From core:**
- `core.health.tier_signal` — `{ tier: Full | Standard | Lite | Minimal, reason }`.
- `rendering_surface_health` — `{ surface_id, state: Ok | Degraded | Crashed, last_frame_ms }`.

**From L7 (accessibility / onboarding):**
- `reduce_motion_toggle` — `{ enabled: bool }` (hard cap on intensity and frame rate).

---

## 4. Outbound interfaces

Events L3 publishes.

- `presence_state` — `{ behavior: BehaviorClass, intensity: f32, tier: TierLevel, posture: PresencePosture, at_ms }`. Broadcast on every state change.
- `avatar_frame_ready` — `{ frame_id, at_ms, tier }`. Emitted after a `BehaviorFrame` has been successfully pushed to the rendering surface (observers only; not load-bearing).
- `behavior_started` — `{ behavior: BehaviorClass, trigger, at_ms }`.
- `behavior_cancelled` — `{ behavior: BehaviorClass, reason, at_ms }`.
- `behavior_completed` — `{ behavior: BehaviorClass, duration_ms, at_ms }`.
- `anti_uncanny_correction_applied` — `{ field, requested: f32, clipped_to: f32, reason, at_ms }`.
- `tier_downgrade_presence` — `{ from: TierLevel, to: TierLevel, reason, at_ms }`.
- `rendering_surface_error` — `{ surface_id, error: PresenceError, at_ms }`.

---

## 5. Synchronous vs asynchronous boundaries

- **Frame emission is continuous.** `BehaviorFrame`s are pushed to the rendering surface at 60 / 30 / 10 fps per tier (Minimal = on-change only). This is a hot loop; the scheduler must not block on policy or persona IO inside a frame.
- **Turn-state handling is soft real-time.** A `turn_state_change` must result in the corresponding behavior transition being *scheduled* within one frame interval of the current tier (≤16.7 ms on Full, ≤100 ms on Lite). The visible transition may cross-fade over a longer window, but the scheduler commitment is one-frame.
- **Viseme alignment is deadline-bounded.** Each `viseme_tick` carries a `deadline_ms`; visemes older than this (N ms, tier-dependent, default 80 ms Full / 150 ms Standard / dropped-to-neutral on Lite) are discarded rather than applied late. Overruns emit `VisemeDesync`.
- **Persona swap is async with a deadline.** `persona_swap_begin` starts a crossfade; `persona_swap_commit` must arrive within `crossfade_ms + grace`. If not, L3 holds the destination persona and logs.
- **Policy `emergency_revoke_all` is synchronous.** Current-frame commit is cancelled; next frame is forced to `Concealed` posture with Neutral behavior.
- **Rendering-surface swap is async and gated.** Hot-swapping surfaces at runtime is deferred (see open questions).

---

## 6. Typed contract suggestions

Pseudo-Rust. Signatures only; bodies omitted.

### 6.1 `PresenceEngine` trait

```
trait PresenceEngine {
    fn on_turn_state(&mut self, ev: TurnStateChange) -> Result<(), PresenceError>;
    fn on_barge_in(&mut self, ev: BargeInDetected) -> Result<(), PresenceError>;
    fn on_repair(&mut self, ev: RepairEvent) -> Result<(), PresenceError>;
    fn on_persona_compile(&mut self, ev: CompiledPersonaReady) -> Result<(), PresenceError>;
    fn on_policy(&mut self, ev: PolicyDecisionPostureSubset) -> Result<(), PresenceError>;
    fn on_media(&mut self, ev: MediaEvent) -> Result<(), PresenceError>;     // viseme / tts / vad
    fn on_health(&mut self, ev: HealthSignal) -> Result<(), PresenceError>;   // tier + surface health
    fn on_accessibility(&mut self, ev: AccessibilityEvent) -> Result<(), PresenceError>;

    fn emit_frame(&mut self, now_ms: u64) -> Result<BehaviorFrame, PresenceError>;
    fn subscribe_presence(&self) -> PresenceEventStream;
    fn current_behavior(&self) -> (BehaviorClass, f32 /* intensity */);
}
```

### 6.2 `RenderingSurface` trait (pluggable)

```
trait RenderingSurface: Send + Sync {
    fn push_behavior_frame(&mut self, frame: &BehaviorFrame) -> Result<(), PresenceError>;
    fn subscribe_frame_events(&self) -> FrameEventStream;     // frame_ready, dropped, timing
    fn get_capabilities(&self) -> RenderingCapabilities;      // max_fps, supports_visemes, tier_floor, etc.
    fn set_quality(&mut self, q: QualityProfile) -> Result<(), PresenceError>;
    fn shutdown(&mut self) -> Result<(), PresenceError>;
}
```

### 6.3 `BehaviorFrame` struct

```
struct BehaviorFrame {
    frame_id: u64,
    at_ms: u64,
    tier: TierLevel,
    behavior: BehaviorClass,
    intensity: f32,                  // 0.0..=1.0, post-stabilizer
    bounds_applied: IntensityBounds, // what the stabilizer used
    posture: PresencePosture,
    persona_id: PersonaId,
    persona_version: u32,
    visual_params: CompiledVisualRef, // borrowed from L6 CompiledVisual
    viseme: Option<VisemeState>,      // weighted blend or None
    reduce_motion: bool,
    crossfade: Option<CrossfadeState>,
}
```

### 6.4 `BehaviorClass` enum (9 classes per L3 system design)

```
enum BehaviorClass {
    Neutral,
    Listening,
    MicroAck,
    PreparingToSpeak,
    Speaking,
    Thinking,
    Repairing,
    HoldingForUser,
    Concealed,
}
```

### 6.5 `IntensityBounds` struct

```
struct IntensityBounds {
    min: f32,
    max: f32,
    persona_ceiling: f32,        // from L6 CompiledVisual
    policy_ceiling: f32,         // from L5 posture
    accessibility_ceiling: f32,  // reduce_motion cap
    effective_ceiling: f32,      // min of the three ceilings
    smoothing_tau_ms: u32,
    dwell_min_ms: u32,
}
```

### 6.6 Supporting enums (sketch)

```
enum TierLevel     { Full, Standard, Lite, Minimal }
enum PresencePosture { Normal, Restrained, Masked, Concealed }
enum QualityProfile  { Ultra, High, Medium, Low, Portrait }
```

---

## 7. Error vocabulary

```
enum PresenceError {
    MissingAsset { asset_id: String, persona_id: PersonaId },
    RenderingSurfaceCrash { surface_id: String, last_ok_frame_ms: u64 },
    VisemeDesync { expected_ms: u64, actual_ms: u64, dropped: u32 },
    TierDowngradeFailed { from: TierLevel, to: TierLevel, reason: String },
    AntiUncannyOverlimit { field: String, requested: f32, ceiling: f32 },
}
```

Error handling policy:
- `MissingAsset` → fall back to Neutral behavior for the affected channel, emit `anti_uncanny_correction_applied` with `reason="missing_asset"`.
- `RenderingSurfaceCrash` → emit `rendering_surface_error`, attempt surface restart per capabilities, downgrade tier if restart fails.
- `VisemeDesync` → drop stale visemes, continue; repeated desyncs trigger `tier_downgrade_presence`.
- `TierDowngradeFailed` → escalate to core.health; presence continues at previous tier with degraded frame rate.
- `AntiUncannyOverlimit` → always clip, never propagate; log once per field per second.

---

## 8. Dependency expectations

**Load-bearing:**
- **L1 (turn-state)** — no L3 behavior selection happens without a turn model. L1 must be up before L3 leaves Neutral.
- **L6 (persona compiler)** — `CompiledVisual` supplies visual params and persona intensity ceilings. Without L6, L3 runs a "default persona" Neutral loop only.
- **media engine (visemes)** — optional for Listening/Thinking; required for Speaking. Absence downgrades Speaking to lip-closed + intensity-reduced mouth motion.
- **core.health (tier)** — required for correct frame rate selection.

**Pluggable:**
- **Rendering surface** — exactly one `RenderingSurface` impl loaded at runtime via the Tauri plugin system (`aether-plugin-rendering-unreal`, `aether-plugin-rendering-webgl`, `aether-plugin-rendering-null`, etc., per `X3_tauri_architecture.md §5.3`). Selection is made at process start based on capabilities and config; runtime hot-swap is deferred (see open questions).

**Soft dependencies:**
- **L5 (policy)** — absence implies `Normal` posture default. L3 must not hard-fail if L5 is slow; it uses last-known posture and recomputes on next decision.
- **L7 (accessibility)** — absence implies `reduce_motion = false`.

---

## 9. Implementation notes

Per monorepo layout in `X3_tauri_architecture.md §2`:

- **`packages/l3-presence/`** — Rust crate, the behavior scheduler, anti-uncanny stabilizer, `PresenceEngine` trait impl, `BehaviorFrame` assembly. No rendering code; talks only to a `Box<dyn RenderingSurface>`.
- **`packages/l3-avatar-ui/`** — TypeScript / React package containing the WebGL shim (`aether-plugin-rendering-webgl`) and any in-app presence controls (debug overlay, tier indicator). Loaded by the Tauri frontend.
- **`packages/aether-plugin-rendering-unreal/`** — Rust crate that bridges to the Unreal process (pixel-streaming or local IPC, per X3 §5.3). Production target on Full/Standard tiers.
- **`packages/aether-plugin-rendering-webgl/`** — TS crate wrapping the UI-side WebGL renderer. Dev target and fallback for Lite.
- **`packages/aether-plugin-rendering-null/`** — Rust crate, no-op surface for headless tests and CI.

Selection logic lives in `core` at startup; it queries `RenderingCapabilities` from each available plugin, cross-references `core.health` tier floor, and loads exactly one. L3 itself is surface-agnostic.

Testing expectations:
- Unit tests in `packages/l3-presence` cover state→behavior mapping, anti-uncanny clipping, and tier downgrade transitions against the `null` surface.
- Integration tests drive L1/L6/L5 fixtures through L3 and assert on `presence_state` stream ordering and `BehaviorFrame` timing.

---

## 10. Open questions

1. **Rendering-surface hot-swap gate (deferred).** Should L3 support swapping `RenderingSurface` impls at runtime (e.g., Unreal crash → fall back to WebGL without restart), or is startup-only selection acceptable for v1? Current assumption: startup-only; crash triggers process-level recovery. Needs a decision before `aether-plugin-rendering-*` crate APIs are frozen.
2. **Anti-uncanny behavior on Lite tier.** At 10 fps the stabilizer has much less signal to smooth, and portrait-like stillness on Minimal may itself feel uncanny to some users. Open: do we ship a distinct "Lite intensity curve" (flatter ceiling, longer dwell) or fold it into the same `IntensityBounds` with tier-derived defaults? L7 accessibility input needed.
3. **`presence.set_mode` — production vs debug.** L3 system design mentions a mode switch for showing behavior-scheduler internals (active class, queued transitions, clip events) in a debug overlay. Open: is this a first-class API on `PresenceEngine` (e.g., `set_mode(Production | Debug)`) or a side-channel on the rendering plugin only? Implications for where debug state lives and whether it can leak into production builds.
