# 16 — Tech Stack

The technology stack for Companion. Companion ships as a single product (doctrine §6) — **primarily custom-written software** with borrowed primitives isolated behind our own interfaces and replaceable. The OSS-friendly engineering posture (clean Tauri shell, layer scaffolds, open-weights tooling) remains correct as engineering practice; it does not ship as a separate product.

---

## Language strategy

### Rust
**Primary language for realtime, latency-critical, and safety-critical code.**

Used for:
- Realtime event bus and coordinator
- Media pipeline control (timing, chunking, buffering)
- Policy engine
- Local storage and sync primitives
- Presence controller runtime
- Reflex router

Why: low-latency systems performance, strong type safety, memory safety, good FFI to Python / C++, mature async story, excellent WebRTC and audio ecosystems.

### C++ (selective)
Used where existing rendering or animation ecosystems demand it:
- Rendering pipeline integration (Unreal-class surfaces)
- GPU-heavy animation controls
- Bindings to media frameworks not yet mature in Rust

### TypeScript
**Primary language for UI, onboarding, settings, and desktop app shell.**

Used for:
- Desktop app shell (Tauri / Electron webviews)
- React-based UI components
- Onboarding flows
- Settings surfaces
- Trust center
- Showcase surfaces
- Mobile companion (React Native candidate — TBD in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md))

Why: fast iteration, mature ecosystem, excellent tooling, good fit for stateful UI with many panels.

### Python
**Experimentation, ML research, offline processing.**

Used for:
- Model experimentation (Gemma 4 variants, fine-tuning, evals)
- Embedding pipeline prototyping
- Offline memory tooling (bulk import, dedup, analysis)
- Avatar pipeline experimentation (during prototype phase)
- Training data prep (for Isabelle-specific tuning)

**Not** used in the hot-path runtime — Python is for offline experimentation, training, and batch tooling only. Hot-path code lives in Rust.

### Swift / Kotlin (later)
Native mobile where performance and platform integration require it. Cross-platform React Native is the likely default for the companion app, with native modules where needed. Final decision in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

---

## Desktop application shell

### Tauri (default)
**Tauri + Rust backend + TypeScript/React frontend.**

Why:
- Smaller distribution size than Electron
- Lower runtime overhead
- Rust backend aligns with the latency-critical hot-path code
- Native webview per-platform (no Chromium bundle)

Electron remains viable as a fallback but is heavier and less aligned with the Rust runtime story.

A custom shell is on the table only if concrete performance / integration constraints require it; Tauri scales cleanly into the flagship as default.

---

## Local LLM runtime

### Default: Gemma 4
**Gemma 4 is the default local LLM across all tiers.**

- Reflex path: always local Gemma 4
- Local deliberative path (Balanced and Full tiers): Gemma 4 (larger variant)
- Remote deliberative: frontier LLM (Anthropic / OpenAI / equivalent) for hardest tasks

Variant selection per tier is in [14_performance_tiers_vram.md](14_performance_tiers_vram.md).

### Inference runtime
Custom-wrapped inference surface — Rust-bound, streaming-aware, tightly integrated with the event bus. Borrowed inference engine (llama.cpp / ollama / transformers — TBD based on Gemma 4 support maturity), custom control surface on top.

---

## Speech stack

### STT (speech-to-text)

Borrowed inference model (candidates: Parakeet TDT for ultra-low-latency streaming; Whisper Large V3 Turbo / Distil-Whisper for throughput; Moonshine for edge/mobile path later). The streaming chunk model, interruption handling, and viseme timing are **custom** (our ownership).

### TTS (text-to-speech)

Borrowed inference model selected on quality + licensing + latency (candidates: XTTS-v2-class for expressive local speech with licensing reviewed; Piper / Coqui variants / Kokoro as open alternatives). **Our streaming, chunk timing, and viseme synchronization are custom.** TTS model is swappable.

### VAD and audio handling
- VAD: Silero VAD or WebRTC VAD class — borrowed
- Audio pipeline control (timing, interruption, echo cancellation, barge-in): **custom**

---

## Avatar stack

Companion ships with a photoreal full-body avatar at launch (doctrine §5; ADR-0014). The avatar pipeline is custom-built across the must-own layers, with selectively borrowed primitives below.

### Custom (must-own moat)
- **Presence controller** — custom (moat layer)
- **Facial expression layer** — custom
- **Gaze / blink layer** — custom
- **Listening / thinking posture** — custom
- **Idle motion** — custom
- **Lip-sync (speech-to-viseme)** — custom or tightly-integrated borrowed (streaming, chunk-timed)
- **Anti-uncanny stabilizer** — custom

### Studied as references (not shipping dependencies)
- **MuseTalk** — real-time lip-sync / talking-head benchmark
- **TalkingHead** — lightweight real-time 3D/browser avatar reference
- **Wav2Lip variants** — real-time forks for comparison

### Borrowed primitives (isolated behind our interfaces)
- **Rendering surface** — Unreal-class or custom GL/Vulkan; MetaHuman rigs studied as reference, not locked dependency

Direction: borrowed rendering surface + custom everything-on-top.

---

## Rendering

Native rendering surface for the full photoreal pipeline (doctrine §5). Candidates:
- Unreal Engine integration (highest fidelity, heaviest)
- Custom OpenGL / Vulkan / Metal pipeline (most control, most work)
- Hybrid: Unreal for the rig, custom control plane

Rendering engine choice in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

Three.js / TalkingHead-class browser 3D may be used as **prototyping references** during development; they are not the shipping rendering target.

---

## Transport (avatar mode, sync)

### WebRTC (baseline)
- **Candidate transport** for real-time avatar mode (audio + video + data channel)
- Borrowable (standard implementations); custom control channel + viseme metadata on top

### Local-first sync
- Desktop is canonical state store
- Mobile syncs via encrypted delta
- CRDT or operation-log replication — choice in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)
- Transport: private network (Tailscale-class) preferred over cloud relay

---

## Local storage

### Primary store
- **SQLite** for structured state (settings, persona, permissions, audit logs, session memory)
- **Vector index** for semantic memory — candidates: sqlite-vss, Qdrant-embedded, custom Rust implementation for Pro
- **Encryption at rest** for durable memory
- Schema, migration policy, sync semantics — **custom**

---

## Frontend / UI

### Framework
- **React + TypeScript**
- Reasons: mature ecosystem, composable components, good fit for many panels / dialogs / stateful flows

### Component system
- **Custom design system** — not template UI (see [05_ux_principles.md](05_ux_principles.md#component-system))
- Tokenized: colors, spacing, type, motion
- Dark-first; Don's aesthetic: deep 3D neumorphic monochrome
- Accessible by default (keyboard, contrast, screen-reader labels)

### State management
- React Query / TanStack Query for server state
- Zustand or equivalent for local UI state
- Avoid Redux-scale complexity — Companion UI is stateful but not enterprise-state-heavy

### Motion
- Framer Motion or equivalent for UI animations
- GSAP for showcase cinematic surfaces (where justified)
- Reduced-motion respected throughout

---

## Mobile companion (later)

### Candidate stack
- **React Native** with shared TypeScript core — default candidate
- **Native modules** for audio / avatar / system integration where needed
- **Shared Rust core** (via FFI) for sync, crypto, and local reasoning primitives

Decision in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) — pending Pro alpha phase.

---

## Must-own layers (custom-built)

Reiterating from [01_product_doctrine.md](01_product_doctrine.md#must-own-layers-custom-built-aether-pro-onward):

1. Presence controller
2. Companion memory kernel
3. Model router
4. Reflex router / interaction state machine
5. Policy / authorization engine
6. Persona compiler
7. Latency-aware social timing system
8. Onboarding / trust UX

**These are non-negotiable custom for Companion.** No vendor dependency for these layers.

---

## Borrowable (but isolated)

| Layer | Borrowed from | Our control plane |
|-------|--------------|-------------------|
| Local LLM inference | Gemma 4 runtime (llama.cpp / ollama / custom) | Streaming wrapper, quantization config, memory allocation |
| STT | Parakeet / Whisper variant | Streaming chunks, interruption, VAD integration |
| TTS | XTTS / Piper / Coqui | Chunk timing, viseme sync, interruption |
| VAD | Silero / WebRTC VAD | Integration with turn-taking state machine |
| Rendering surface | Unreal / custom GL | Rig control, animation graph, presence controller binding |
| Transport | WebRTC | Control channel, viseme metadata, reconnection logic |
| Storage | SQLite + vector lib | Schema, migrations, sync semantics |
| CRDT (if chosen) | Automerge / Yjs / custom | Conflict resolution policy, merge rules |

---

## Companion stack summary

```
Desktop shell:    Tauri (or custom) + TypeScript/React
Mobile shell:     React Native + native modules + Rust core (FFI)
Local runtime:    Rust (all hot paths), Python for offline tooling only
Local LLM:        Gemma 4 (Lite/Balanced/Full variants)
Remote LLM:       Frontier (Anthropic/OpenAI/equivalent) for deliberative escalation
STT:              Streaming model (Parakeet/Whisper), our chunk + interrupt layer
TTS:              Streaming model, our viseme sync + chunk timing
VAD:              Silero/WebRTC, our turn-taking integration
Avatar:           Custom presence controller + borrowed rendering surface
Rendering:        Unreal / custom GL (TBD in OPEN_QUESTIONS.md)
Transport:        WebRTC (avatar + sync), private network preferred
Storage:          SQLite + vector index, encrypted at rest
Sync:             CRDT or op-log (TBD), desktop-canonical, encrypted delta
Moat layers:      Custom (presence, memory, router, reflex, policy, persona, timing, trust UX)
```

---

## Isabelle stack notes

Isabelle runs on the Companion stack, **not a separate codebase**. Isabelle-specific additions:
- Custom persona compile pack
- Custom voice pack
- Custom avatar appearance pack
- Wider memory ingestion (Don's projects, workflows, preferences)
- Private integrations (Tailscale, existing project tooling)
- Wider autonomy presets

No separate runtime, no separate shell, no separate models. See [roadmaps/isabelle_private.md](roadmaps/isabelle_private.md).

---

## Cross-references
- Doctrine (custom vs borrowed boundary): [01_product_doctrine.md](01_product_doctrine.md)
- Architecture: [08_system_architecture.md](08_system_architecture.md)
- Realtime model: [09_realtime_interaction.md](09_realtime_interaction.md)
- Performance tiers (Gemma 4 variant per tier): [14_performance_tiers_vram.md](14_performance_tiers_vram.md)
- Open decisions: [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)
