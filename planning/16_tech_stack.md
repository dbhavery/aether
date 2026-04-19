# 16 — Tech Stack

The technology stack for Aether across OSS Preview and Pro. **OSS Preview uses open-source/available-now components aggressively. Aether Pro is primarily custom-written software** — borrowed primitives are isolated behind our own interfaces and replaceable.

---

## Language strategy

### Rust
**Primary language for realtime, latency-critical, and safety-critical code.**

Used for:
- Realtime event bus and coordinator
- Media pipeline control (timing, chunking, buffering)
- Policy engine
- Local storage and sync primitives
- Presence controller runtime (Pro)
- Reflex router (Pro)

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

**Not** used in the hot-path runtime for Pro — Python sidecars acceptable for OSS Preview speed-to-launch, but moved into Rust for Pro.

### Swift / Kotlin (later)
Native mobile where performance and platform integration require it. Cross-platform React Native is the likely default for the companion app, with native modules where needed. Final decision in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

---

## Desktop application shell

### OSS Preview: Tauri
**Recommended: Tauri + Rust backend + TypeScript/React frontend.**

Why:
- Smaller distribution size than Electron (matters for open-source adoption)
- Lower runtime overhead
- Rust backend aligns with long-term latency-critical code
- Better fit for open-source packaging and fast desktop iteration
- Native webview per-platform (no Chromium bundle)

Electron remains viable as a fallback but is heavier and less aligned with the long-term Rust runtime story.

### Aether Pro: Tauri (or custom)
Tauri continues as the default for Pro unless concrete performance / integration constraints require a custom shell. The Rust + webview pattern scales into the flagship cleanly.

---

## Local LLM runtime

### Default: Gemma 4
**Gemma 4 is the default local LLM across all tiers and both products.**

- Reflex path: always local Gemma 4
- Local deliberative path (Balanced and Full tiers): Gemma 4 (larger variant)
- Remote deliberative: frontier LLM (Anthropic / OpenAI / equivalent) for hardest tasks

Variant selection per tier is in [14_performance_tiers_vram.md](14_performance_tiers_vram.md).

### Inference runtime
- **OSS Preview:** leverage existing runtime (llama.cpp / ollama / transformers — TBD based on Gemma 4 support maturity).
- **Aether Pro:** custom-wrapped inference surface — Rust-bound, streaming-aware, tightly integrated with the event bus. Borrowed inference engine, custom control surface.

---

## Speech stack

### STT (speech-to-text) candidates

**For OSS Preview:**
- **Parakeet TDT** — ultra-low-latency streaming use cases
- **Whisper Large V3 Turbo / Distil-Whisper** — faster throughput, broader flexibility
- **Moonshine** — edge/mobile-oriented path (later)

**For Aether Pro:**
- Inference model borrowed (Parakeet / Whisper variant); streaming chunk model, interruption handling, and viseme timing are **custom** (our ownership).

### TTS (text-to-speech) candidates

**For OSS Preview:**
- XTTS-v2-class experimentation for expressive local speech (licensing reviewed before any commercial carry-forward).
- Open TTS alternatives: Piper, Coqui variants, Kokoro — evaluated for voice quality, latency, licensing.

**For Aether Pro:**
- TTS model selection driven by quality + licensing + latency; **our streaming, chunk timing, and viseme synchronization are custom.** TTS model is swappable.

### VAD and audio handling
- VAD: Silero VAD or WebRTC VAD class — borrowed
- Audio pipeline control (timing, interruption, echo cancellation, barge-in): **custom**

---

## Avatar stack

### OSS Preview — open-source baselines
- **MuseTalk** — real-time lip-sync / talking-head benchmark
- **TalkingHead** — lightweight real-time 3D/browser avatar reference
- **Wav2Lip variants** — real-time forks for comparison/prototyping

These are acceptable direct dependencies in OSS Preview.

### Aether Pro — custom + selectively borrowed
- **Presence controller** — custom (moat layer)
- **Facial expression layer** — custom
- **Gaze / blink layer** — custom
- **Listening / thinking posture** — custom
- **Idle motion** — custom
- **Lip-sync (speech-to-viseme)** — custom or tightly-integrated borrowed (streaming, chunk-timed)
- **Rendering surface** — Unreal-class or custom GL/Vulkan; MetaHuman rigs studied as reference, not locked dependency
- **Anti-uncanny stabilizer** — custom

Direction: borrowed rendering surface + custom everything-on-top.

---

## Rendering

### OSS Preview
- Browser-compatible 3D (Three.js) or lightweight 3D shell — TalkingHead-class
- 2D avatar fallback for Lite tier

### Aether Pro
- Native rendering surface. Candidates:
  - Unreal Engine integration (highest fidelity, heaviest)
  - Custom OpenGL / Vulkan / Metal pipeline (most control, most work)
  - Hybrid: Unreal for the rig, custom control plane
- Rendering engine choice in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).
- Three.js is **not** the Pro rendering target — it's an OSS Preview tool.

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
- Avoid Redux-scale complexity — Aether UI is stateful but not enterprise-state-heavy

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

## Must-own layers (custom-built, Aether Pro onward)

Reiterating from [01_product_doctrine.md](01_product_doctrine.md#must-own-layers-custom-built-aether-pro-onward):

1. Presence controller
2. Companion memory kernel
3. Model router
4. Reflex router / interaction state machine
5. Policy / authorization engine
6. Persona compiler
7. Latency-aware social timing system
8. Onboarding / trust UX

**These are non-negotiable custom for Pro.** No vendor dependency for these layers.

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

## OSS Preview stack summary

```
Desktop shell:    Tauri + TypeScript/React
Local runtime:    Rust (core) + Python sidecar (transitional)
Local LLM:        Gemma 4 (smallest variant that fits tier)
STT:              Parakeet / Whisper variant
TTS:              XTTS / Piper / Coqui
Avatar:           MuseTalk / TalkingHead / Wav2Lip-class
Rendering:        Three.js or lightweight 3D
Storage:          SQLite
Sync:             N/A (OSS Preview is single-device)
```

---

## Aether Pro stack summary

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

Isabelle runs on the Aether Pro stack, **not a separate codebase**. Isabelle-specific additions:
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
