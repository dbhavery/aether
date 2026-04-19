# 01 — Product Doctrine

This is the governing doctrine for the entire Aether product family. Every architecture decision, library choice, and roadmap item is evaluated against the rules here.

---

## The hard rules

### 1. No "close-enough" SaaS for core experience layers
Vendor-style close-enough SaaS behavior is **not acceptable** in any layer that defines the user relationship or the product moat. The flagship does not settle for commodity quality in conversation timing, memory, presence, permissions, or trust UX.

### 2. Bare-metal / custom creation is required for strategic subsystems
Core differentiators must be custom-built or deeply controlled at a low enough level to preserve the product ceiling. Off-the-shelf components may be used selectively — but only when they do **not** reduce the product ceiling and do **not** become the moat.

### 3. Highest-tier assistant/companion relationship is the north star
The flagship target is the highest believable assistant/companion relationship standard — operationalized through measurable elements (acknowledgment timing, memory continuity, presence quality, control transparency, graceful fallback, stable personalization), with an aspirational aim toward "indistinguishable from a real human companion."

Proof that this bar is reachable:
- AI-generated human-indistinguishable models exist.
- Human-indistinguishable AI video with natural movement exists.
- Real-time TTS-driven lip-sync with human-like motion exists.

These are **proven-possible** — the engineering work is in assembly, integration, and presence quality, not in inventing from zero.

### 4. User experience is the top-priority constraint
When architecture, model routing, rendering, permissions, or update behavior is evaluated, **the effect on perceived interaction quality, trust, and continuity outranks implementation convenience**. If a simpler implementation compromises the user experience on the flagship, it is the wrong implementation.

---

## Product-specific boundary

### Aether OSS Preview
- **Open-source and available-now components are acceptable** for speed to launch.
- Used as a wedge to demonstrate vision, gather community, and establish trust.
- Polish and experience quality still apply — no shallow quality acceptance.
- Preview may leverage: MuseTalk, TalkingHead, Wav2Lip-style primitives, Whisper/Parakeet STT, open TTS, Tauri shell, etc.
- **Goal:** Launch fast and prove the product family is being built to a serious quality bar.

### Aether Pro (flagship) and Isabelle (private)
- **We write our own software from here on.**
- Every must-own layer (see below) is custom-built.
- Borrowed primitives are permitted **only** where they do not cap the product ceiling or become the moat — and even then, must be isolated behind our own interfaces so they can be swapped or replaced later.
- Audio2Face, MetaHuman, Unreal rigs, WebRTC — studied as baselines and ceilings, not locked as dependencies.

---

## Must-own layers (custom-built, Aether Pro onward)

These are the layers that define the user relationship and the product moat. They are **non-negotiable custom-built** for Aether Pro. As of [DECIDED 2026-04-18] the planning model uses **seven** must-own layers (L1–L7); the reflex router remains a distinct *concept* embedded inside L1 Interaction Timing rather than a separate layer. See [`plans/00_ORCHESTRATION_MAP.md`](plans/00_ORCHESTRATION_MAP.md) §1 for the reconciliation and [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) for the live decision log.

1. **Interaction timing (L1)** — turn-state machine, acknowledgment phrase pool, timing contracts (250 ms / 800 ms / 2000 ms / 4000 ms behavior), and the **embedded reflex router**: the fast-path classifier that decides each turn (direct local / acknowledge-and-wait / search / tool plan / remote escalation / safety deflection / memory write). Reflex is tested against L1 acceptance criteria and sequenced with L1 across P0–P4; it is not demoted, only co-owned with timing.
2. **Companion memory kernel (L2)** — multimodal ingestion, novelty filtering, scoped recall, editable memories, provenance, confidence decay, user-enforced forgetting.
3. **Presence controller (L3)** — maps internal assistant state (listening / thinking / acknowledging / speaking / idle / waiting) to visible social behavior (gaze, blink, micro-motion, speaking emphasis, anti-uncanny stabilization).
4. **Model router (L4)** — latency-aware local-vs-remote decision engine; factors privacy, cost, task type, memory confidence, tool availability.
5. **Policy / authorization engine (L5)** — capability-based permissions, scoped resources, approval workflow, audit logs; the core of the trust moat.
6. **Persona compiler (L6)** — turns onboarding choices into system prompts, phrase pools, animation parameters, voice settings, memory salience rules.
7. **Onboarding / trust UX (L7)** — the user-visible surface that establishes trust; cannot be outsourced to generic components.

---

## Desktop framework doctrine

[DECIDED 2026-04-18] — see [`plans/00_ORCHESTRATION_MAP.md`](plans/00_ORCHESTRATION_MAP.md) §2 and [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).

- **UI stack:** HTML / CSS / JS across the Aether family. No Tkinter, no Qt for visual UI.
- **Family desktop default (long-term):** **Tauri.** Rust shell + WebView2; the signed-updater and native-integration path for Aether Pro and Isabelle.
- **pywebview:** tactical OSS-Preview-only exception, used only if speed-to-demo requires it. Explicitly **non-doctrinal**. Any reference to pywebview outside OSS Preview is a drift and must be flagged.

---

## Borrowable layers (selective, isolated, replaceable)

Layers where using external primitives is acceptable **if** they are isolated behind our own interfaces and do not cap the ceiling:

- Rendering surfaces (e.g. Unreal, custom GL/Vulkan pipelines) — the rig and the control layer on top stay ours.
- Transport (WebRTC baseline for avatar mode) — the control channel and event model stay ours.
- STT/TTS inference runtimes — but the streaming chunk model, interruption handling, and viseme timing stay ours.
- Local storage engines (SQLite, CRDT libraries) — schema, migration, and sync policy stay ours.
- Frontier LLM APIs for the deliberative path — routing, escalation policy, prompt compilation, and fallback stay ours.

---

## Doctrine interpretation

**"Custom" does not mean inventing every primitive from zero.** It means:
- Owning the integration logic and control plane.
- Owning the interfaces so borrowed parts are replaceable.
- Never letting a vendor decide the product's ceiling, behavior, or data boundaries.

**The strongest path is hybrid** — borrow primitives where they do not reduce the product ceiling; custom-build the layers that define the user relationship and the product moat.

---

## Applied to evaluation

Every proposed library, framework, or vendor dependency must be checked against:

1. Does it touch a must-own layer? → If yes, **it is a reference, not a dependency**.
2. If borrowable, is it isolated behind our own interface? → If no, fix the interface before adopting.
3. Does it cap the product ceiling? → If yes, reject or plan an explicit replacement date.
4. Does it degrade UX vs. what custom code could achieve? → If yes, it's wrong for the flagship.

---

## The bar

> "Close enough" is unacceptable for the flagship product wherever it compromises the intended user experience, social presence, trust model, or long-term moat.

> The product is judged as a conversation and as a relationship — not as a benchmark, not as a feature list, not as a demo.
