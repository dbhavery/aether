# 11 — Avatar & Presence

The avatar subsystem and the presence controller. The presence controller is a **must-own custom-built moat layer** — it is the difference between "lip-sync with a face" and a believable companion.

---

## Long-term target

### Goal
Persistent, photorealistic, conversationally believable assistant avatar. Listens, speaks, moves, and responds naturally. Can extend to full-body in the final vision.

### Clarification
**The user knows it is AI.** The goal is realism and social presence, not deception. The standard "highest-believable assistant/companion relationship" (per [01_product_doctrine.md](01_product_doctrine.md)) is about trust and emotional coherence, not identity fraud.

### Proof the bar is reachable
- Human-indistinguishable AI-generated models exist.
- Human-indistinguishable AI video with natural motion exists.
- Real-time TTS-driven lip-sync with human-like motion exists.

The engineering task is assembly, integration, and social timing — not inventing facial animation from zero.

---

## MVP target (OSS Preview)

- **Scope:** Headshot or bust-level avatar
- **Real-time or near-real-time lip-sync**
- **Speech-driven facial animation**
- **Distinct listening / thinking / speaking states**
- **Open-source-compatible implementation** — MuseTalk / TalkingHead / Wav2Lip-style references acceptable at this tier
- **Degrades gracefully on weak hardware**

See [roadmaps/aether_oss_preview.md](roadmaps/aether_oss_preview.md).

---

## Avatar subsystem layers

The avatar is not one engine. It is a stack of distinct layers, each with its own ownership status:

### Layer 1 — Speech-to-face (visemes / mouth motion)
- Maps phonemes / audio chunks to mouth shapes.
- Runs in sync with TTS stream.
- **OSS Preview:** borrowable (MuseTalk / Wav2Lip-class).
- **Pro:** custom, streaming-aware, tightly timed with TTS chunks. Borrowed only as study reference.

### Layer 2 — Facial expression
- State-linked expressions (listening, thinking, answering, acknowledging).
- Speech-linked micro-expressions (emphasis, surprise, warmth).
- **Must-own (Pro).** This is part of persona expression, not a commodity.

### Layer 3 — Gaze and blink
- Eye direction, micro-saccades, blink cadence.
- State-linked: "thinking" gaze differs from "speaking" gaze differs from "listening" gaze.
- Natural blink variation (not metronomic).
- **Must-own (Pro).** Uncanny avatars are a gaze-failure problem as much as a rendering problem.

### Layer 4 — Listening / thinking posture
- Non-speaking state presence.
- Small head tilts, nods, lean variation.
- Distinct listening (attentive) vs thinking (inward) postures.
- **Must-own (Pro).**

### Layer 5 — Idle motion
- Subtle breath, weight shift, micro-motion.
- Prevents "frozen uncanny" state.
- Runs continuously even during thinking/waiting.
- **Must-own (Pro).**

### Layer 6 — Gesture / body scheduler (later)
- Hand gestures, torso shifts, emphasis beats.
- Full-body later in flagship roadmap.
- **Must-own (Pro).**

### Layer 7 — Cinematic stabilizer / anti-uncanny control
- Smooths transitions between states.
- Prevents over-animation and rapid state flicker.
- Suppresses features that commonly create uncanny feel.
- **Must-own (Pro).** Hardest and most important layer.

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

### OSS Preview
- Open-source / available-now rendering primitives
- 2D or simple 3D headshot
- Browser-compatible (TalkingHead-style) acceptable
- Target: credible, not photoreal

### Aether Pro
- Higher-fidelity rendering; 3D rigged head + shoulders minimum at launch
- Path toward photorealism through custom rendering stack or Unreal-class integration
- MetaHuman-class rigs may be referenced and studied; integration only if they don't cap the ceiling or lock us in
- **The rig is borrowable; the control layer on top stays ours.**

### Full-body (later milestone)
- Deferred until core avatar mode is stable and believable at head-and-shoulders.
- Adding full-body before reasoning and memory are solid makes the product feel impressive-but-unreliable (see [01_product_doctrine.md](01_product_doctrine.md) anti-patterns).

---

## Timing contracts for avatar

- **Lip-sync latency from TTS chunk to viseme display:** target under 80 ms
- **State transition render time:** under 100 ms
- **Blink cadence variation:** natural random (not fixed rate)
- **Frame rate target by tier:**
  - Lite: 24 fps minimum
  - Balanced: 30 fps
  - Full / Pro: 60 fps where possible

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

## OSS Preview vs Pro avatar scope

| Feature | OSS Preview | Pro |
|---------|-------------|-----|
| Avatar type | Headshot, 2D or simple 3D | 3D head+shoulders, photoreal path |
| Lip-sync | Open-source primitive (MuseTalk / Wav2Lip-class) | Custom, streaming-tight, chunk-synced |
| Facial expression | Basic state-linked | Rich, speech-linked, persona-tuned |
| Gaze / blink | Simple | Full presence-controller-driven |
| Idle motion | Minimal | Full subtle motion layer |
| Body / gesture | None | Limited at launch; expands in later phases |
| Presence controller | Lite (rule-based, minimal) | Full must-own implementation |
| Rendering | Browser-compatible | Native rendering surface, higher fidelity |

---

## Cross-references
- Doctrine (must-own status): [01_product_doctrine.md](01_product_doctrine.md)
- Architecture (engine split): [08_system_architecture.md](08_system_architecture.md)
- Realtime / timing: [09_realtime_interaction.md](09_realtime_interaction.md)
- Performance tiers: [14_performance_tiers_vram.md](14_performance_tiers_vram.md)
- Tech stack (rendering, lip-sync refs): [16_tech_stack.md](16_tech_stack.md)
