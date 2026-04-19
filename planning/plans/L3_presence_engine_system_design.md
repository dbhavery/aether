# L3 — Presence Engine System Design

**Status:** draft (system-design, implementation-grade)
**Last updated:** 2026-04-18
**Layer type:** must-own (doctrine §1.1 "presence controller").
**Design stance:** L3 is a **behavior engine**, not a renderer. It owns the behavior scheduler that maps internal assistant state to visible social behavior. The rendering surface beneath it is a **swappable borrowable plugin**.

Upstream plan: file:///C:/Users/dbhav/Projects/aether-planning/plans/L3_presence_engine.md
Related specs:
- file:///C:/Users/dbhav/Projects/aether-planning/11_avatar_presence.md
- file:///C:/Users/dbhav/Projects/aether-planning/14_performance_tiers_vram.md
- file:///C:/Users/dbhav/Projects/aether-planning/01_product_doctrine.md
- file:///C:/Users/dbhav/Projects/aether-planning/MASTER_OUTLINE_TREE.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/00_ORCHESTRATION_MAP.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/X3_tauri_architecture.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L6_persona_compiler.md

---

## 1. Purpose and design stance

L3 consumes the Rust event bus (`turn_state_change`, persona compile events, policy posture, media viseme stream, core.health tier signals) and produces **timed, bounded, anti-uncanny behavior frames** that an adapter — the RenderingSurface plugin — translates into pixels.

Explicit stance:

- **L3 is a behavior engine.** Its product is a stream of `BehaviorFrame`s plus lifecycle events. Rendering surface selection (OSS preview 2D headshot, Pro custom GL, Pro Unreal-class, Pro hybrid) is Don's gate per orchestration map §9 and MUST NOT be baked into the scheduler.
- **Rendering-surface-agnostic.** The scheduler does not know what rig is downstream. It emits posture/gaze/blink/viseme/intensity; the plugin maps those onto its rig. This preserves the doctrine "the rig is borrowable; the control layer on top stays ours" (11 §Rendering strategy).
- **Deterministic-first, ML-augmented-later.** Rule-based scheduler (11 §Design philosophy) is the contract surface; future ML modules slot in as enrichment, never as replacement.
- **Graceful degradation across Lite / Balanced / Full** (14 §Three performance tiers, X3 §8.3).
- **Never deceive the user about liveness.** If the rendering surface is down, L3 MUST NOT pretend a live avatar is present; a degraded/offline indicator is emitted and L7 renders a visible banner.

Contradiction flags (not silently resolved):

- **CF-1 (19 L1 states vs 7 doctrine states).** Doctrine (01 §Must-own #3) enumerates 7 coarse presence states (listening / thinking / acknowledging / speaking / idle / waiting / "anti-uncanny stabilization"). L1 §2 defines 19 turn states. The mapping table in §3 projects 19 → a small behavior-class set; this is a deliberate projection, not a 1-to-1. Don to confirm whether degraded states should each have a distinct visible behavior or share a single "degraded" class.
- **CF-2 ("Anti-uncanny only on Balanced+" vs doctrine "hardest and most important layer").** 11 §Layer 7 calls anti-uncanny the hardest layer. X3 §8.3 implies minimal animation on Lite. We gate the stabilizer OFF on Lite — defensible because the Lite fidelity ceiling is too low to trigger uncanny-valley failure modes, but flagged for Don.
- **CF-3 (doctrine "waiting" presence state not matched by L1).** L1 has no `Waiting` turn state; the closest is `AwaitingPolicy` / `AwaitingApproval`. We route both to a single "thinking/waiting" behavior class; doctrine `waiting` collapses into `thinking`.
- **CF-4 (presence.set_mode existence).** X3 §2.2 exposes `presence.set_mode(mode)`; L1 §7.4 states L1 does NOT have a `presence.set_mode` dependency and L3 owns any forced-mode transitions internally. We define `presence.set_mode` as an **L7/debug-only** command — not an L1 coupling. Don to confirm.

---

## 2. State inputs

All inputs arrive via the Rust event bus (X3 §3).

| Source | Signal | Rate | Use |
|---|---|---|---|
| L1 | `turn_state_change { from, to, cause, at, change_id, seq }` — all 19 states (L1 §2) | event-driven; ≤1 render frame reflection target | Primary driver of behavior class selection |
| L1 | `barge_in_detected { cut_point, at }` | event-driven | Triggers barge-in behavior class |
| L1 | `repair_started { cause }` / `repair_resolved { resolution }` | event-driven | Triggers/clears repair behavior class |
| L1 | `ack_phrase { phrase_id }` (when L1 auto-acks) | event-driven | Couples to acknowledgment behavior |
| L6 | `compiled_persona_ready { persona_id, CompiledPersona }` | rare | Resets visual params, intensity bounds, expressiveness, boundaries, anti-uncanny settings |
| L6 | `persona_swap_begin` / `persona_swap_commit` | rare | Two-phase swap; L3 acks per L6 contract |
| L5 | policy posture changes (projected via `policy_decision` + `PrivacyPosture` from CompiledPersona; L5 §10) | rare | Strict / Balanced / Open posture modulates intensity; minimum-trust persona → muted presence |
| L5 | `emergency_revoke_all { scope }` | rare | Does **not** kill avatar; forces minimum-trust visual |
| Media / Audio | `viseme_tick { viseme, phone_ms, audio_clock }`, `tts_chunk`, `tts_chunk_done` | high-freq | Lip-sync alignment, speaking intensity |
| Media / Audio | VAD `speech_start` / `speech_end` (echoed for cross-check; L1 is authoritative) | event-driven | Listening-posture intensification |
| core.health | `tier_signal { Lite | Balanced | Full }` + dynamic downgrade/upgrade | rare + on pressure | Frame-rate, behavior richness, stabilizer gate |
| core.health | `rendering_surface_health { Up | Degraded | Down }` | rare | Triggers degraded/offline class |
| L7 | user accessibility flag `reduce_motion: bool` | rare | Collapses to minimal-posture set |
| (optional) Media | user-attention signal (camera-grant-gated; L5 capability `CameraRead`) | low-freq | Gaze biasing only; absence → natural-wander fallback |

---

## 3. Output behaviors — classes and taxonomy

L3 maintains an **active-behavior stack** (see §4). Each class has: name, priority, preemption policy, default duration, blend-in/out windows, persona-modulated intensity bounds.

| Class | Description | Triggering L1 states / events | Priority | Persona-modulated? |
|---|---|---|---|---|
| `Idle` | Breath, subtle weight shift, micro-saccades, gaze wander, natural blink | `Idle`, long silence in `Listening` | 1 | Yes (wander rate, breath depth) |
| `Listening` | Lean-in, sustained-but-not-fixed gaze, reduced blink rate, attentive head angle, micro-nods on partial transcripts | `Listening` | 3 | Yes (lean intensity, gaze-hold) |
| `Thinking` | Gaze shift (up/side), subtle micro-motion, occasional glance back to user, reduced facial tension | `Thinking`, `RouteSelected`, `ExecutingDirect`, `ExecutingTool`, `AwaitingPolicy`, `AwaitingApproval` (also doctrine "waiting") | 3 | Yes (aversion angle, glance cadence) |
| `Acknowledging` | Head nod, brow-raise, small smile cueing "I heard you"; synced with optional ack phrase | `AcknowledgingWait`, on `ack_phrase` event | 5 | Yes (nod amplitude, smile bound) |
| `Speaking` | Viseme-driven lip-sync, gesture emphasis beats, gaze anchors with natural breaks, suppressed blink during emphasis peaks | `Speaking`, `Streaming` (if audio present) | 6 | Yes (emphasis intensity, gesture library subset) |
| `Repair` | Brow furrow, slight head tilt, reduced motion intensity, softened gaze | `Repairing`, `repair_started` | 7 | Yes (apology tone dampening) |
| `BargeIn` | Gaze snap to user, mid-phrase cut with natural pause, shoulder settle, blink | `BargedIn`, `barge_in_detected` | 8 | Yes (snap speed, settle duration) |
| `Safety` | Reserved for L5-forced muted/minimum-trust visuals | `emergency_revoke_all`, minimum-trust persona active | 9 | No (bypasses persona intensity) |
| `Degraded` | Static or minimal-motion avatar + explicit visual "offline" indicator; NEVER full-liveness | `DegradedNoPolicy`, `DegradedNoMemory`, `DegradedNoRouter`, `Error`, rendering-surface down | 10 (sub-Safety semantics; exclusive mode) | No |

Priority: `Safety/Degraded` > `BargeIn` > `Repair` > `Speaking` > `Acknowledging` > `Thinking` > `Listening` > `Idle`.

Taxonomic notes:

- **Every L1 turn state has a behavior mapping** (self-review checklist item 1):

  | L1 state (§2) | Behavior class |
  |---|---|
  | 1 `Idle` | `Idle` |
  | 2 `Listening` | `Listening` |
  | 3 `Processing` (partial-transcript reflex prep) | `Listening` (blink suppressed, lean held) |
  | 4 `ReflexSelecting` | `Thinking` (short-cadence) |
  | 5 `AcknowledgingWait` | `Acknowledging` |
  | 6 `Thinking` | `Thinking` |
  | 7 `AwaitingPolicy` | `Thinking` (wait-variant) |
  | 8 `RouteSelected` | `Thinking` (transient) |
  | 9 `ExecutingDirect` | `Thinking` |
  | 10 `ExecutingTool` | `Thinking` (tool-variant: occasional confirmatory glance) |
  | 11 `AwaitingApproval` | `Thinking` (wait-variant; on secondary ack → `Acknowledging` pulse) |
  | 12 `Streaming` | `Speaking` (if audio) else `Thinking` |
  | 13 `Speaking` | `Speaking` |
  | 14 `Repairing` | `Repair` |
  | 15 `BargedIn` | `BargeIn` |
  | 16 `DegradedNoPolicy` | `Degraded` (partial — posture allowed, muted) |
  | 17 `DegradedNoMemory` | `Listening` with muted intensity (transient degraded) |
  | 18 `DegradedNoRouter` | `Degraded` (partial — posture allowed, muted) |
  | 19 `Error` | `Degraded` (full — explicit offline indicator) |

  Note: states 3 and 8 are not in L1 §2 exactly as numbered — L1 labels absent states may be elided; if a state name here does not exist in L1 §2, it is dropped and the nearest-neighbor mapping applies. This is a **known gap to reconcile with L1 §2 post-freeze**.

- **Every persona visual param has a consumer** (self-review checklist item 2). See §6 (L6 interface) and §4 table.

---

## 4. Behavior scheduler — the core L3 component

The scheduler is the moat. It takes `(turn_state, persona params, audio state, tier, active-behavior stack)` and produces the next `BehaviorFrame`.

### 4.1 Components

- **Active-behavior stack.** Ordered by priority; top of stack renders. Lower classes continue to run their slow channels (breath, micro-sway) if the top class doesn't own that channel — composited by the stack reducer.
- **Priority rules.** `Safety/Degraded > BargeIn > Repair > Speaking > Acknowledging > Thinking > Listening > Idle`. A higher-priority class pre-empts lower with a **blend-out window** on the preempted class (default 120 ms, persona-modulated 60–240 ms).
- **Interrupt rules.** Preemption is always allowed except for `Safety/Degraded`, which is exclusive. `BargeIn` specifically races against L1's `T_barge_in_cut = 150 ms` budget — L3 must begin its gaze-snap within 80 ms of `barge_in_detected`.
- **Cooldowns.** Per-behavior primitive cooldown tracker prevents repetition. Examples:
  - Same ack head-nod pattern within 6 s → substitute next pattern in ring.
  - Identical blink interval twice in a row → inject ±variance from persona's `blink_variance_bounds`.
  - Same gaze-aversion angle used twice within 10 s → rotate to next quadrant.
- **Anti-uncanny constraints (tier-gated).**
  - Blink rate: clamped to persona `blink_rate_bounds` (default 10–20/min per L3 plan acceptance criteria).
  - Saccade frequency: clamped.
  - Motion-rest ratio: enforce minimum rest windows.
  - Asymmetry injection: small left/right asymmetry to avoid mirror-perfect repeats.
  - Stabilizer ON for Balanced+; OFF for Lite (see CF-2).
- **Reduced-motion accessibility.** User flag collapses to: breath only, no saccades, slowest blink, no gesture library, lip-sync retained.

### 4.2 Pseudocode — scheduler main loop

```
loop @ tier_fps (10–15 Lite / 30 Balanced / 60 Full):
    inputs = drain_event_bus_since_last_tick()
    for ev in inputs:
        match ev:
            turn_state_change(to)      -> stack.request(map_state_to_class(to))
            barge_in_detected(cut)     -> stack.preempt(BargeIn, cut)
            repair_started(cause)      -> stack.preempt(Repair, cause)
            repair_resolved(_)         -> stack.release(Repair)
            ack_phrase(pid)            -> stack.pulse(Acknowledging, pid)
            compiled_persona_ready(p)  -> params.reload(p)
            persona_swap_begin         -> scheduler.quiesce(); ack()
            persona_swap_commit(p)     -> params.reload(p); scheduler.resume()
            viseme_tick(v)             -> viseme_buffer.push(v)
            tier_signal(t)             -> tier.set(t); rebind_fps_and_stabilizer(t)
            rendering_surface_health(h)-> if h != Up: stack.force(Degraded)
            emergency_revoke_all       -> stack.force(Safety)    # does NOT kill avatar
            reduce_motion(flag)        -> accessibility.set(flag)

    # Compose frame
    top = stack.top()
    channels = compose_channels(stack, params, tier, accessibility)   # breath, gaze, blink, viseme, gesture
    channels = apply_cooldowns(channels, cooldown_tracker)
    channels = apply_anti_uncanny(channels, tier)                     # no-op on Lite
    channels = clamp_to_persona_bounds(channels, params.intensity_bounds)

    frame = BehaviorFrame {
        posture: top.posture,
        gaze_target: channels.gaze,
        blink_phase: channels.blink,
        viseme_frame: viseme_buffer.drain_aligned_to(audio_clock, tier_coalesce),
        micro_motion_params: channels.micro,
        intensity: channels.intensity,
        tier: tier.current,
        seq: next_seq(),
        audio_clock_at_compose: audio_clock.now(),
    }

    rendering_surface.push_behavior_frame(frame)
    emit_lifecycle_events(stack.diff_since_last_tick())   # behavior_started/cancelled/completed/anti_uncanny_correction_applied
```

### 4.3 Invariants

- **I-1:** No two frames may claim the same `seq`.
- **I-2:** `Speaking` never runs without a non-empty viseme buffer or explicit no-audio fallback gesture plan.
- **I-3:** `Degraded` is exclusive; when active, no other class writes channels.
- **I-4:** `Safety` may only be released by L5 state change or persona recompile.
- **I-5:** Blink rate (measured over a 60 s sliding window) stays within persona bounds — violation emits `anti_uncanny_correction_applied`.
- **I-6:** Active behavior class MUST reflect within one render frame of `turn_state_change` arrival (L1 §4 `T_first_state_change` derived target).

---

## 5. Rendering abstraction

### 5.1 Trait

```
trait RenderingSurface {
    fn push_behavior_frame(frame: BehaviorFrame) -> Result<(), SurfaceError>;
    fn subscribe_frame_events() -> EventStream<RenderEvent>;
    fn get_capabilities() -> SurfaceCapabilities;
    fn set_quality(tier: Tier) -> Result<(), SurfaceError>;
    fn shutdown() -> Result<(), SurfaceError>;
}
```

Exactly **one** `RenderingSurface` plugin is loaded at runtime (per X3 §5.3 `aether-plugin-rendering-<surface>` pattern).

Candidate surfaces — interface is identical across all:

| Surface | Tier | Process | Notes |
|---|---|---|---|
| OSS Preview headshot (MuseTalk / TalkingHead / Wav2Lip-class) | Lite/Balanced | in-proc (webview canvas) | Borrowed stack; L3 controller in TS during P0, Rust by P1 |
| Pro custom GL | Full | out-of-proc | Don's gate |
| Pro Unreal-class | Full | out-of-proc | Don's gate |
| Pro hybrid (GL + photoreal compositing) | Full | out-of-proc | Don's gate |

### 5.2 `BehaviorFrame` pseudotype

```
struct BehaviorFrame {
    seq:                     u64,
    audio_clock_at_compose:  AudioClockNs,
    tier:                    Tier,

    posture:                 PostureTag,          // enum { Idle, Listening, Thinking, Ack, Speaking, Repair, BargeIn, Safety, Degraded }
    gaze_target:             GazeTarget,          // { user_eyes, user_offset(angle), aversion_up, aversion_side, wander_point, snap_to_user }
    blink_phase:             BlinkPhase,          // { open, closing(t), closed, opening(t), suppressed }
    viseme_frame:            Option<VisemeFrame>, // phoneme, envelope, audio_align_ns; None if non-speaking
    micro_motion_params:     MicroMotionParams,   // breath_phase, weight_bias, head_tilt, shoulder_settle
    gesture_event:           Option<GestureEvent>,// typed beat: nod, brow_raise, lean, emphasis_beat
    intensity:               IntensityVec,        // [0..1] per channel; clamped by persona bounds
    accessibility_flags:     AccessibilityFlags,  // reduce_motion mirrored here for surface sanity-check
    offline_indicator:       Option<OfflineBadge>,// non-None iff Degraded class active — visible "offline" cue
}
```

### 5.3 Frame rate

L3 emits BehaviorFrames at tier-appropriate rate:

- **Lite:** 10–15 fps (X3 §8.3); acceptance-criteria floor 24 fps from 11 §Timing applies to the **rendering** fps, not the behavior-frame cadence — the plugin may interpolate. Frame-rate coalescing contract defined in §7.
- **Balanced:** 30 fps.
- **Full:** 60 fps.

Rendering surface runs in-proc or out-of-proc (Don's gate). L3's trait contract is the same either way; out-of-proc uses a shared-memory or IPC pipe behind the trait.

---

## 6. Interfaces

### 6.1 To L1

- **Subscribes:** `turn_state_change`, `barge_in_detected`, `repair_started`, `repair_resolved`, `ack_phrase`.
- **L1 does not call into L3** (L1 §7.4). L3 infers behavior from events.
- **Optional `presence.set_mode(mode)`** — exposed via X3 §2.2 command surface for debug/forced-mode only. Not a production L1 dependency (CF-4).

### 6.2 To L6

- **Subscribes:** `compiled_persona_ready { CompiledPersona }`, `persona_swap_begin`, `persona_swap_commit`.
- **Per L6 §71–72 two-phase protocol:** on `persona_swap_begin`, L3 quiesces the scheduler (finishes current frame, blocks new behavior requests) and acks within 500 ms; on `persona_swap_commit`, it reloads params atomically.
- **CompiledPersona.L3 field set** (what L3 reads; exhaustiveness-tested per L6 §90):
  - `visual_params { rig_id, portrait_asset_refs, viseme_profile_id }`
  - `intensity_bounds { gaze, blink, motion, gesture, emphasis }` — each `{min, max, default}`
  - `expressiveness { warmth, formality, intensity }` scalars
  - `boundaries { max_asymmetry, max_lean, forbidden_gestures: Vec<GestureTag> }` — anti-uncanny + persona-coherence
  - `anti_uncanny { blink_rate_bounds, saccade_frequency_bounds, motion_rest_min_ratio, asymmetry_injection: bool }`
  - `muted_profile_ref` — pointer to the visual profile used when Safety class is forced
  - `reduce_motion_profile_ref` — used when accessibility flag on

### 6.3 To L5

- **Subscribes:** `policy_decision` projections that mention presence (e.g. `DenyReason` that should soften expression), `grant_revoked`, `emergency_revoke_all`.
- **Privacy posture behavior** (L5 §10): `Strict` → lower ceiling on intensity + gaze-hold bounds; `Balanced` → default; `Open` → full expressiveness within persona bounds.
- **Minimum-trust persona** (L5 §871): visual `Safety` class is forced; avatar remains present but muted; explicit trust-center banner from L7.
- **emergency_revoke_all behavior:** avatar persists (safety UX), visual forced to minimum-trust. L3 never kills the avatar on revoke.

### 6.4 To audio / media

- **Consumes:** `viseme_tick`, `tts_chunk`, `tts_chunk_done`, VAD signals (cross-check only; L1 is authoritative).
- **Lip-sync clock:** L3 aligns to the **audio clock**, not wall clock (per L3 plan risk #3). Desync rule: drop visemes older than N ms (default N=80 ms; tier-tunable). On desync, emit `anti_uncanny_correction_applied { cause: VisemeResync }` and `rendering_surface_error` if persistent.

### 6.5 To UI (L7)

- **Emits (projected to webview via X3 §3.2):** `presence_state { class, intensity, tier, offline_indicator }` at low frequency (coalesced on Lite — X3 §8.2).
- **L7 uses it to reflect presence in non-avatar views** — chat-bubble pulse during `Listening`, thinking indicator during `Thinking`, offline badge during `Degraded`.
- **Trust-center banner integration:** `rendering_surface_error` + `tier_downgrade_presence` feed L7's trust center.

### 6.6 From core.health

- **Subscribes:** `tier_signal` (Lite/Balanced/Full), dynamic downgrade/upgrade, `rendering_surface_health`.
- **Reaction:** rebind frame-rate and richness without reload (per 14 §Runtime tier behavior; see §12).

---

## 7. Performance tiers

### 7.1 Behavior class × tier matrix

| Behavior class | Lite | Balanced | Full |
|---|---|---|---|
| Idle | Simplified (breath + occasional glance; no full saccade field) | Standard (breath + saccades + wander) | Full (enrichment micro-motion, persona idiosyncrasies) |
| Listening | Simplified (lean-in + held gaze; reduced blink) | Standard (+ micro-nods on partials) | Full (+ warmth micro-expression, subtle head tilts) |
| Thinking | Simplified (single gaze-aversion point; minimal motion) | Standard (quadrant rotation, occasional glance-back) | Full (cadence-varied glances, thinking-specific micro-motion) |
| Acknowledging | Simplified (nod only) | Standard (nod + brow-raise) | Full (nod + brow + smile envelope + optional small lean) |
| Speaking | Simplified (coalesced visemes — multiple phonemes → longer frames) | Standard (full viseme stream, gesture emphasis) | Full (high-freq viseme channel per X3 §8.3, full gesture library) |
| Repair | Simplified (head tilt only) | Standard (head tilt + brow furrow) | Full (+ softened gaze + dampened motion envelope) |
| BargeIn | Enabled (gaze snap required on all tiers) | Enabled | Enabled (+ shoulder settle enrichment) |
| Safety | Enabled (muted visual) | Enabled | Enabled |
| Degraded | Enabled (static + offline badge) | Enabled | Enabled |
| Anti-uncanny stabilizer | **Disabled** (see CF-2) | Enabled | Enabled (max strength) |
| Reduced-motion accessibility | Enabled | Enabled | Enabled |

### 7.2 Frame rate by tier

- **Lite:** 10–15 fps behavior frames; 2D headshot; coalesced visemes.
- **Balanced:** 30 fps; standard gesture set; anti-uncanny enabled; standard viseme stream.
- **Full:** 60 fps; full gesture library; micro-motion enrichment; anti-uncanny at max; dedicated high-freq viseme channel (X3 §8.3).

---

## 8. Event contracts emitted

| Event | Payload | Consumers | Projected to UI? |
|---|---|---|---|
| `presence_state` | `class, intensity, tier, offline_indicator, persona_id, seq` | L7 (chat-bubble pulse, trust center), L1 (consistency check only) | yes (low-freq, coalesced on Lite) |
| `avatar_frame_ready` | `BehaviorFrame` | RenderingSurface plugin | no (Rust-internal or IPC to out-of-proc plugin) |
| `behavior_started` | `class, at, cause, seq` | L7 (debug), telemetry | no (debug projection only) |
| `behavior_cancelled` | `class, at, cause (preempted_by), seq` | telemetry | no |
| `behavior_completed` | `class, at, duration, seq` | telemetry | no |
| `anti_uncanny_correction_applied` | `correction_kind, bound_violated, at` | telemetry, L7 (aggregate) | no |
| `tier_downgrade_presence` | `from_tier, to_tier, reason` | L7 (trust-center notify), core.health | yes |
| `rendering_surface_error` | `kind { crash, desync, asset_missing, capability_mismatch }, at` | L7 (banner), core.health | yes |

---

## 9. Events subscribed to

(Summary — see §6 for per-interface detail.)

- **L1:** `turn_state_change`, `barge_in_detected`, `repair_started`, `repair_resolved`, `ack_phrase`.
- **L6:** `compiled_persona_ready`, `persona_swap_begin`, `persona_swap_commit`.
- **L5:** `policy_decision` (posture-affecting subset), `grant_revoked`, `emergency_revoke_all`.
- **Media:** `viseme_tick`, `tts_chunk`, `tts_chunk_done`, VAD events.
- **core.health:** `tier_signal`, `rendering_surface_health`, `downgrade_notice`.
- **L7:** accessibility flag `reduce_motion`, optional debug `presence.set_mode`.

---

## 10. Failure and degraded modes

Per failure class, a defined mode (self-review checklist item 4):

| Failure | Behavior |
|---|---|
| Missing avatar assets | Fallback to static persona portrait + emit `rendering_surface_error{asset_missing}`; L7 banner; scheduler remains alive and continues emitting `presence_state` so non-avatar surfaces still reflect state. |
| Desynced audio / animation | Drop visemes older than N ms (tier-tuned); emit `anti_uncanny_correction_applied{VisemeResync}`; if persistent >1 s, emit `rendering_surface_error{desync}` and transition `Speaking` → `Thinking` until resync. |
| Rendering surface crash | Scheduler keeps running; `rendering_surface_error{crash}` emitted; L7 banner "avatar unavailable"; chat/text modes continue unaffected. Auto-restart attempted per plugin policy (max 3 attempts, backoff). |
| Rendering surface down (hard) | Force `Degraded` class; visible `offline_indicator`; never pretend liveness. |
| Low-performance fallback | Auto-downgrade tier via core.health; emit `tier_downgrade_presence`; user sees smoother-but-simpler avatar; trust center explains. |
| Viseme stream stall (>500 ms during Speaking) | Hold last mouth pose briefly, then relax to neutral; suppress blink suppression; emit correction. |
| Persona swap timeout (L6 consumer ack >500 ms) | L6 rolls back per its contract; L3 remains on prior `CompiledPersona`; no mixed-state turn. |
| L5 `emergency_revoke_all` | Force `Safety` class using `muted_profile_ref`; avatar persists; explicit muted visual. Never kill the avatar. |
| Deceptive-state guard | If rendering surface reports `Down` or capability mismatch blocks BehaviorFrame rendering, L3 MUST emit `Degraded` and UI MUST NOT render any implied-liveness proxy. |

---

## 11. Privacy and safety considerations

- **No camera capture without L5 grant.** User-attention gaze-biasing requires `CameraRead` capability; absence → natural-wander fallback. L5 evaluates.
- **Avatar asset storage.** Persona visual assets are stored under `core.data`; loaded only on `compiled_persona_ready`. Assets on disk are not decrypted into memory until the plugin asks for them.
- **Emergency-revoke-all does NOT kill the avatar.** Safety UX rule: the user needs a visible, trustworthy interlocutor even when their tools are revoked. L3 forces the minimum-trust visual profile and an explicit muted indicator.
- **Offline honesty.** When degraded or surface-down, the user sees unambiguous offline signaling. No "looking lively while broken."
- **No recording side-channels.** BehaviorFrames are ephemeral; they are not persisted. Telemetry events (`behavior_*`, `anti_uncanny_correction_applied`) carry no PII.

---

## 12. Tier-aware runtime rules

- **In-session frame-rate adaptation.** `core.health` downgrade swaps tier binding atomically between frames; scheduler adjusts `tier_fps`, stabilizer on/off, viseme coalescing without reload. `tier_downgrade_presence` is emitted.
- **Viseme coalescing on Lite.** Multiple visemes within a coalescing window (default 66 ms on Lite) collapse into a longer-duration composite frame; phoneme fidelity sacrificed for frame-rate sustainability.
- **Anti-uncanny only on Balanced+** (see CF-2 flag). Lite relies on low fidelity as an implicit uncanny shield; if Don disagrees, promote to always-on with a simplified stabilizer.
- **Gesture library scaling.** Full tier loads full library; Balanced loads a curated subset; Lite disables `gesture_event` emission entirely (no beats, just posture + visemes).
- **Dedicated viseme channel** on Full per X3 §8.3 (bypasses the low-freq projection); on Lite visemes flow through the coalesced channel only.

---

## 13. Stub interfaces (unblock plugin authors + L1 stubs)

```
trait PresenceEngine {
    fn on_turn_state(ev: TurnStateChange);
    fn on_barge_in(ev: BargeInDetected);
    fn on_repair(ev: RepairEvent);         // started | resolved
    fn on_persona_compile(ev: CompiledPersonaEvent);   // ready | swap_begin | swap_commit
    fn on_policy(ev: PolicyPostureEvent);
    fn on_media(ev: MediaEvent);           // viseme_tick | tts_chunk | tts_chunk_done | vad
    fn on_health(ev: HealthEvent);         // tier_signal | rendering_surface_health
    fn on_accessibility(flags: AccessibilityFlags);

    fn emit_frame() -> BehaviorFrame;                     // driven by scheduler tick
    fn subscribe_presence() -> EventStream<PresenceStateEvent>;
    fn current_behavior() -> BehaviorSnapshot;            // { class, intensity, tier, seq, offline }
}

trait RenderingSurface { /* see §5.1 */ }

struct BehaviorFrame { /* see §5.2 */ }

enum SurfaceError { Crash, AssetMissing, CapabilityMismatch, Desync, Shutdown }

struct SurfaceCapabilities {
    supports_full_body: bool,
    supported_tiers: Vec<Tier>,
    max_fps: u16,
    supports_out_of_proc: bool,
    viseme_profile_ids: Vec<VisemeProfileId>,
    gesture_tags_supported: Vec<GestureTag>,
}
```

This stub set is sufficient for:

- L1 to emit a scripted turn-state sequence into a fake PresenceEngine (L1 §"L3 stubs against").
- A RenderingSurface plugin author to iterate against the trait in isolation.
- L6 to exercise the CompiledPersona → L3 reload path without an actual renderer.

---

## 14. Testing strategy (design-level)

### 14.1 Property tests

- **P-1 Priority invariant.** For any interleaving of events, the active behavior class is always the highest-priority class whose conditions hold. Counter-example → scheduler bug.
- **P-2 Cooldown determinism.** Given a fixed random seed and event log, the exact sequence of ack-nod patterns, blink intervals, and gaze angles is reproducible.
- **P-3 Anti-uncanny bounds.** Over any 60 s window, blink rate, saccade frequency, and motion-rest ratio stay within persona bounds. Violation → test fail.
- **P-4 Degraded exclusivity.** While `Degraded` is active, no channel is written by any other class.
- **P-5 Safety persistence.** While minimum-trust persona or `emergency_revoke_all` is active, `Safety` class cannot be released except by corresponding release event.

### 14.2 Perceptual tests (informal rubric — no target numbers)

Uncanny-valley avoidance checklist:

- [ ] Avatar never frozen for >2 s during any silent window.
- [ ] Blink neither metronomic nor absent.
- [ ] Gaze not fixed-stare; not darting.
- [ ] Mouth not locked open/closed between phonemes.
- [ ] No mirror-perfect repeated gestures within visible window.
- [ ] Transition from `Speaking` → `Listening` doesn't snap unnaturally.
- [ ] Repair behavior reads as apologetic, not glitched.

### 14.3 Red-team scenarios

- Mismatched audio / animation (inject 200 ms TTS delay).
- Missing avatar assets mid-session.
- Tier downgrade mid-utterance.
- Simultaneous persona swap + barge-in.
- `emergency_revoke_all` during `Speaking`.
- Rendering surface crash during `BargeIn`.
- VAD false-positive during `Speaking`.
- `reduce_motion` toggled mid-speaking.

### 14.4 Load tests

- 60 fps at Full tier under combined STT + TTS + vector-index (L2) + tool-execution (L4) load. Target: no dropped `BehaviorFrame`, p95 event-to-frame latency <1 render frame.
- Dynamic tier downgrade under VRAM pressure — scheduler must re-bind without dropping `presence_state` continuity.

---

## 15. Deliverables summary — what an implementer builds first

Implementation order (each unblocks the next):

1. **`BehaviorScheduler`** — priority queue + cooldown tracker + active-behavior stack + scheduler main loop (§4.2). Ship against a fake RenderingSurface that logs frames.
2. **`RenderingSurface` trait + reference headshot implementation** — OSS Preview MuseTalk/TalkingHead-class adapter (in-proc, webview canvas).
3. **`BehaviorFrame` pseudotype + event emission** — wire `presence_state`, `behavior_*`, `anti_uncanny_correction_applied`, `tier_downgrade_presence`, `rendering_surface_error` onto the Rust bus (X3 §3).
4. **Persona-visual-params consumer** — consume `CompiledPersona.L3` field set; exhaustiveness-tested per L6 §90.
5. **Anti-uncanny stabilizer module** — tier-gated; Lite off by default (CF-2); Balanced/Full on.

---

## 16. Open questions

1. **OQ-L3-1 Rendering surface gate.** Unreal-class vs custom GL vs hybrid for Pro (orchestration map §9). Behavior engine is decoupled, but out-of-proc IPC shape differs materially across choices.
2. **OQ-L3-2 CF-1 state projection.** Should `DegradedNoMemory` get a distinct visible behavior (currently collapses into muted `Listening`)?
3. **OQ-L3-3 CF-2 anti-uncanny on Lite.** Promote to always-on with a simplified stabilizer? Or keep Lite OFF under the "low fidelity is its own shield" theory?
4. **OQ-L3-4 CF-4 `presence.set_mode`.** Is this a production command (L7 accessibility / user preference), or strictly debug-only? L1 plan says debug-only.
5. **OQ-L3-5 User-attention (camera) signal.** Default off until Pro Phase 2+? Or offer as opt-in from OSS Preview with explicit L5 grant?
6. **OQ-L3-6 Persistence of presence for non-avatar views.** Should `presence_state` drive a chat-bubble pulse in text-only mode? Assumed yes — confirm with L7.
7. **OQ-L3-7 Style-envelope schema.** L3 plan §"Open decisions" — persona-to-motion mapping schema is not yet frozen. Needs a spec in L6.
8. **OQ-L3-8 N threshold for viseme drop.** 80 ms default cited; Don to confirm or tune per viseme profile.
9. **OQ-L3-9 Full-body roadmap slot.** Pro Phase 2 or Pro Phase 3+? L3 plan §"Open decisions."
10. **OQ-L3-10 L1 state-name reconciliation.** The mapping table in §3 references state labels that may not exactly match L1 §2 (e.g., `Processing`, `RouteSelected` extras). Reconcile post-L1 freeze.

---

## Self-review checklist (closing)

- [x] Every L1 turn state has an L3 behavior mapping (§3 taxonomy table — flagged L1 reconciliation gap in OQ-L3-10).
- [x] Every persona visual param has a defined consumer behavior (§6.2 field set; §4 intensity/cooldown wiring).
- [x] Every tier has an enabled/simplified/disabled matrix row (§7.1).
- [x] §10 has a degraded-mode entry per failure class.
- [x] Rendering surface is truly pluggable — swap without changing §6 interfaces (§5.1 trait is the seam; §6 interfaces describe events and command surfaces, none of which mention the surface implementation).

Contradictions explicitly flagged, not silently resolved: **CF-1, CF-2, CF-3, CF-4** (§1).
