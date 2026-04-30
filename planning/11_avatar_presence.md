# 11 — Avatar & Presence

The avatar subsystem and the presence controller. The presence controller is a **must-own custom-built moat layer** — it is the difference between "lip-sync with a face" and a believable companion.

---

## Target

### Goal
Persistent, photoreal, full-body, conversationally believable assistant avatar from launch (doctrine §5). Listens, speaks, moves, and responds naturally. No headshot intermediate.

### Clarification
**The user knows it is AI.** The goal is realism and social presence, not deception. The standard "highest-believable assistant/companion relationship" (per [01_product_doctrine.md](01_product_doctrine.md)) is about trust and emotional coherence, not identity fraud.

### Proof the bar is reachable
- Human-indistinguishable AI-generated models exist.
- Human-indistinguishable AI video with natural motion exists.
- Real-time TTS-driven lip-sync with human-like motion exists.

The engineering task is assembly, integration, and social timing — not inventing facial animation from zero.

---

## Launch scope

Companion ships as a single product (doctrine §6). The avatar at launch is:

- **Photoreal full-body** (doctrine §5; ADR-0014). No headshot-only release.
- **Real-time or near-real-time lip-sync.**
- **Speech-driven facial animation.**
- **Distinct listening / thinking / speaking states.**
- **Hardware-aware tiers** (Lite / Balanced / Full) — all tiers render the same photoreal full-body character; tiers trade animation richness, idle motion fidelity, and frame-rate budget, **not** body framing.

See [`roadmaps/aether_pro.md`](roadmaps/aether_pro.md) for the launch-track roadmap; [`roadmaps/aether_oss_preview.md`](roadmaps/aether_oss_preview.md) is tombstoned per doctrine §6.

---

## Avatar subsystem layers

The avatar is not one engine. It is a stack of distinct layers, each with its own ownership status:

### Layer 1 — Speech-to-face (visemes / mouth motion)
- Maps phonemes / audio chunks to mouth shapes.
- Runs in sync with TTS stream.
- **Custom Companion implementation** — streaming-aware, tightly timed with TTS chunks. Open-source references (MuseTalk / Wav2Lip-class) studied as baselines, isolated behind our own interface; not the shipping path.

### Layer 2 — Facial expression
- State-linked expressions (listening, thinking, answering, acknowledging).
- Speech-linked micro-expressions (emphasis, surprise, warmth).
- **Must-own.** This is part of persona expression, not a commodity.

### Layer 3 — Gaze and blink
- Eye direction, micro-saccades, blink cadence.
- State-linked: "thinking" gaze differs from "speaking" gaze differs from "listening" gaze.
- Natural blink variation (not metronomic).
- **Must-own.** Uncanny avatars are a gaze-failure problem as much as a rendering problem.

### Layer 4 — Listening / thinking posture
- Non-speaking state presence.
- Small head tilts, nods, lean variation.
- Distinct listening (attentive) vs thinking (inward) postures.
- **Must-own.**

### Layer 5 — Idle motion
- Subtle breath, weight shift, micro-motion.
- Prevents "frozen uncanny" state.
- Runs continuously even during thinking/waiting.
- **Must-own.**

### Layer 6 — Gesture / body scheduler (later)
- Hand gestures, torso shifts, emphasis beats.
- Full-body later in flagship roadmap.
- **Must-own.**

### Layer 7 — Cinematic stabilizer / anti-uncanny control
- Smooths transitions between states.
- Prevents over-animation and rapid state flicker.
- Suppresses features that commonly create uncanny feel.
- **Must-own.** Hardest and most important layer.

---

## The presence controller (key moat)

### What it is
A dedicated control layer that **maps internal assistant state to visible social behavior**. Distinct from pure lip-sync.

### What it controls
- Eye contact direction
- Blink timing and cadence
- Idle motion intensity
- Speaking emphasis (matched to intent)
- Listening cues
- Thinking behavior (gaze aversion, micro-motion change)
- State transition smoothing
- Fallback behavior during latency spikes

### Inputs
- Current assistant state (from Interaction engine)
- Current cognition state (reflex / deliberative / waiting / tool-running)
- Current media state (speaking / not speaking)
- Persona parameters (from Persona compiler)
- User attention signal (looking at avatar or not — if camera is permitted)

### Outputs
- Animation parameter streams to the rendering layer
- Anti-uncanny dampening signals
- Gesture / expression triggers

### Design philosophy
**Rule-based first, ML-assisted later.**

- End-to-end generative control over all visible social behavior is unstable and hard to debug.
- A deterministic, composable state-behavior mapping is maintainable and predictable.
- ML may augment (e.g., learned micro-expression generation) once the rule-based spine is solid.

### Why this is the moat
- Every competitor can buy lip-sync.
- Very few have a presence controller that makes the avatar feel alive during **silence** and **waiting**.
- Being alive during silence is what turns "impressive demo" into "believable companion."

---

## State-behavior mapping (partial)

| Assistant state | Gaze | Blink | Motion | Speaking |
|-----------------|------|-------|--------|----------|
| Idle | Natural wander, occasional glance at user | Normal cadence | Subtle breath + weight shift | No |
| Listening | Sustained eye contact with micro-nods | Slightly slower | Slight forward lean | No |
| Thinking (reflex) | Brief upward glance, returns to user | Normal | Subtle head tilt | No |
| Working (deliberative) | Gaze aversion, glance back periodically | Normal | Small position shift, occasional nod | No |
| Acknowledging | Eye contact | Natural | Slight head lift | Yes (short phrase) |
| Speaking | Eye contact with natural breaks | Matched to speech rhythm | Emphasis-linked | Yes |
| Yielding | Soft gaze, slight recline | Relaxed | Returns to listening posture | Ending |

This is the rule-based spine. The presence controller implements it; persona parameters modulate it.

---

## Rendering strategy

### Companion (single product)
- Photoreal full-body rendering at launch (doctrine §5).
- Per-persona character pipeline produces stills and video drawn from the same identity (ADR-0014).
- Pre-generated motion clip library + runtime blend + lip-sync overlay (ADR-0013).
- MetaHuman-class rigs and open-source rendering primitives may be studied as references; integration only if they do not cap the ceiling or lock us in.
- **The rig is borrowable; the control layer on top stays ours.**
- Reliability under load is non-negotiable: a photoreal character that freezes, drifts identity, or breaks lip-sync is a doctrine §5 violation, not an acceptable trade.

---

## Timing contracts for avatar

- **Lip-sync latency from TTS chunk to viseme display:** target under 80 ms
- **State transition render time:** under 100 ms
- **Blink cadence variation:** natural random (not fixed rate)
- **Frame rate target by tier:**
  - Lite: 24 fps minimum
  - Balanced: 30 fps
  - Full: 60 fps where possible

Specific ms targets to lock in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

---

## Failure modes & graceful degradation

| Failure | Behavior |
|---------|----------|
| Rendering framerate drops | Reduce motion complexity; maintain lip-sync |
| TTS chunk late | Presence holds pre-speech posture; does not freeze |
| Avatar render stalls entirely | Chat mode remains responsive; avatar shows "reconnecting" state, not frozen face |
| Camera input lost (user attention tracking) | Default to natural gaze rotation |
| VRAM pressure | Downgrade avatar tier dynamically; warn user in trust center |

---

## Avatar capability by hardware tier

Companion ships with the full avatar capability set (doctrine §6). Hardware tiers (Lite / Balanced / Full) trade animation richness and frame-rate budget — not body framing or feature presence. All tiers render the same photoreal full-body character (doctrine §5).

| Capability | Lite | Balanced | Full |
|------------|------|----------|------|
| Avatar type | Photoreal full-body | Photoreal full-body | Photoreal full-body |
| Lip-sync | Custom, streaming-tight, chunk-synced (reduced cadence) | Custom, full cadence | Custom, full cadence + emphasis-linked detail |
| Facial expression | State-linked, simplified palette | Rich, speech-linked | Rich, speech-linked, persona-tuned |
| Gaze / blink | Presence-controller-driven, simplified | Full presence-controller-driven | Full presence-controller-driven |
| Idle motion | Subtle motion (reduced frequency) | Full subtle motion layer | Full subtle motion layer |
| Body / gesture | Reduced gesture set | Standard gesture set | Full gesture / body movement |
| Presence controller | Full must-own implementation | Full must-own implementation | Full must-own implementation |
| Rendering | Native, lower fidelity | Native, mid fidelity | Native, full fidelity |

---

## Cross-references
- Doctrine (must-own status): [01_product_doctrine.md](01_product_doctrine.md)
- Architecture (engine split): [08_system_architecture.md](08_system_architecture.md)
- Realtime / timing: [09_realtime_interaction.md](09_realtime_interaction.md)
- Performance tiers: [14_performance_tiers_vram.md](14_performance_tiers_vram.md)
- Tech stack (rendering, lip-sync refs): [16_tech_stack.md](16_tech_stack.md)
