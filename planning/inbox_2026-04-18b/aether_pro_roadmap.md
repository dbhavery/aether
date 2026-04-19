# Aether Pro Specification and Roadmap

## Product doctrine

Aether Pro is not allowed to settle for commodity “close enough” SaaS behavior in any core experience layer. Off-the-shelf products, APIs, libraries, and engines may be used selectively as accelerators, but they are unacceptable as permanent substitutes wherever they limit the product’s intended ceiling in social presence, trust, memory quality, autonomy control, or user experience.[cite:193][cite:195][cite:200]

The flagship target is the highest-level assistant/companion relationship standard the platform can realistically build toward. That means the product should be architected for maximal control over the core user relationship, and user experience should outrank convenience when tradeoffs affect the defining experience of the assistant.[cite:189][cite:194][cite:196]

## Product purpose

Aether Pro is the full-performance public flagship platform in the Aether family. It should deliver the premium public realization of the vision: a multimodal, local-first, high-trust assistant with strong memory, configurable autonomy, and an avatar/presence layer that aims at the highest believable user experience standard rather than a merely acceptable synthetic interface.[cite:54][cite:43][cite:82]

The flagship product should be built as a platform, not a wrapper app. Roadmap and architecture guidance for large software systems strongly favors explicit subsystem ownership, measurable targets, and durable internal control where the product’s differentiators sit.[cite:155][cite:156][cite:188]

## Strategic architecture doctrine

### Core layers that must be owned or deeply controlled

The platform should treat the following as strategic moat layers that must be custom-built or custom-dominated over time:
- conversation timing and acknowledgment engine,
- memory kernel and memory governance,
- model router,
- policy/authorization engine,
- onboarding and trust UX system,
- persona compiler,
- presence controller.[cite:194][cite:196][cite:193]

### Layers where selective borrowing is acceptable

The platform may selectively borrow or integrate external primitives for rendering, speech models, transport, observability, databases, and infrastructure where those choices do not materially cap product quality or strategic control. Build-vs-buy guidance consistently supports using external primitives for non-differentiating layers while owning the layers that determine product value and defensibility.[cite:193][cite:195][cite:198]

## Recommended tech stack

### Desktop application

**Recommended:** Tauri + React/TypeScript front-end + Rust native services. Tauri remains attractive because of its smaller footprint and Rust integration, while React/TypeScript is still one of the most practical choices for building large, stateful desktop UI systems quickly.[cite:102][cite:105][cite:111][cite:202]

### Mobile application

**Recommended public path:** React Native for speed and shared product logic in early public mobile efforts, especially if fast time-to-market matters. Current mobile stack guidance still treats React Native as a strong default for first-generation cross-platform AI apps, while acknowledging that native stacks win when AI performance is the differentiator.[cite:203]

**Recommended high-performance alternative:** SwiftUI on iOS and Jetpack Compose/Kotlin on Android if mobile-side AI performance, media integration, and native responsiveness become core differentiators in later flagship phases.[cite:203][cite:205][cite:213]

### Core systems language

**Recommended:** Rust for real-time coordinator, policy layer, tool gateway, and lower-latency runtime services. Rust remains a strong fit for systems that need safety, concurrency, and performance without sacrificing long-term maintainability.[cite:207][cite:212]

### Experimental and model tooling

**Recommended:** Python for research pipelines, model evaluation, offline memory experiments, data prep, and early service adapters. Python remains the strongest default for model experimentation and rapidly changing ML integration work.[cite:54][cite:58]

### Avatar and rendering surface

**Recommended flagship rendering direction:** Unreal Engine-class rendering surface for high-end photoreal human presentation, with custom control systems layered around it rather than treating the engine itself as the product. Real-time MetaHuman-style conversational workflows and NVIDIA facial-animation primitives show that this remains one of the strongest paths for high-fidelity character presentation.[cite:47][cite:86][cite:43]

### Facial animation and avatar primitives

**Recommended primitive baseline:** NVIDIA Audio2Face-class speech-driven facial animation as a benchmark and potential lower-level runtime primitive. NVIDIA’s open-sourcing of Audio2Face materially improves the feasibility of building a custom avatar/presence stack with lower-level control rather than relying solely on black-box avatar SaaS.[cite:43][cite:53]

### STT stack

**Recommended tiered STT strategy:**
- Parakeet TDT for low-latency streaming reflex paths.[cite:64]
- Whisper Large V3 / Whisper Turbo / Distil-Whisper for broader multilingual or throughput-focused scenarios.[cite:64]
- Moonshine or similar edge-leaning model paths where smaller device targets matter.[cite:64]

### TTS stack

**Recommended TTS research direction:** use open and local-capable expressive TTS baselines for internal experimentation, while keeping the production stack flexible enough to mix local and premium remote voices. XTTS-v2-style expressive local cloning is a useful R&D reference point, though licensing must be handled carefully before production carry-forward.[cite:62]

### Local data layer

**Recommended local-first direction:** SQLite or Postgres-compatible local data foundation with a formal sync plan later. Current offline-first guidance points to structured local storage plus an explicit sync layer as the most coherent path for resilient local-first applications.[cite:206]

### Sync architecture

**Recommended direction:** local-primary data model with structured sync rather than cloud-primary truth. For broader local-first systems, current guidance points toward client-local databases combined with sync engines and explicit conflict handling, rather than treating offline as an exceptional state.[cite:206][cite:82][cite:84]

### Orchestration and observability

**Recommended:** custom orchestration core plus production observability for agent workflows, latency, cost, tool calls, and policy violations. Current agent stack guidance explicitly treats observability and governance as operational backbone layers for production AI systems.[cite:207][cite:210][cite:212]

## Recommended infrastructure

### Runtime infrastructure

The production system should separate:
- client runtime,
- local service layer,
- remote orchestration/control plane,
- premium model providers,
- storage/sync services,
- observability/governance plane.[cite:207][cite:212]

### Networking and transport

**Recommended real-time transport direction:** WebRTC-style low-latency transport for real-time audio/video/avatar streaming and timing-sensitive channels. Current real-time avatar and speech guidance continues to center WebRTC and related low-latency streaming approaches for interactive media flows.[cite:69][cite:72][cite:74]

### Cloud services

Remote services should be reserved for frontier reasoning, longer-running research, model fallback, account-linked sync support, and observability/governance layers. This preserves the local-first user experience while still enabling higher-end intelligence when local systems are insufficient.[cite:30][cite:212]

### Observability and governance

The production platform should capture traces for model routing, latency, cost, failures, approvals, tool use, policy denials, and user-visible outcomes. Current observability guidance for AI agent systems treats these traces as essential for trust, debugging, and production reliability.[cite:207][cite:210][cite:212]

## Core system architecture

### Interaction engine

This engine should own turn-taking, interruption handling, visible assistant state, acknowledgment timing, and repair flows. It is a strategic system because the assistant’s believability depends heavily on timing continuity and conversational coherence.[cite:30][cite:74]

### Cognition engine

This engine should handle intent interpretation, task planning, model routing, tool selection, verification, and output assembly. It should explicitly distinguish between local reflex answers and slower, deeper, or externally researched responses.[cite:30][cite:73]

### Memory engine

The memory engine should support turn memory, session memory, durable user memory, artifact memory, and behavior memory, with selective ingestion, novelty filtering, and user-editable governance. Recent research on lifelong multimodal memory directly supports this type of structured, selective design.[cite:54][cite:70]

### Presence engine

The presence engine should map internal assistant state to visible/avatar behavior: gaze, blink cadence, idle posture, emphasis, and waiting behavior. This layer is a major moat because believable social presence depends on controlled behavior fusion, not only visual fidelity.[cite:29][cite:43][cite:47]

### Policy engine

The policy engine should sit between cognition and all tool/action surfaces, evaluating permissions, scopes, risk classes, approvals, and audit requirements before any consequential behavior occurs. This is essential for a premium high-trust assistant product.[cite:123][cite:126][cite:121]

## Product experience

### UX priority

User experience is the top priority for the flagship. Every architectural decision should be judged by its effect on perceived responsiveness, trust, continuity, clarity, and relationship quality rather than by implementation convenience alone.[cite:189][cite:194][cite:196]

### Experience target

The flagship target is a highest-tier assistant/companion relationship standard, operationalized through measurable elements such as acknowledgment timing, memory continuity, presence quality, control transparency, graceful fallback behavior, and stable personalization.[cite:194][cite:196]

## Performance model

### Tiered runtime profiles

Aether Pro should support Lite, Balanced, and Full profiles with downloadable asset/model packs, tier-aware local inference, and hardware-specific defaults. Public GPU planning guidance continues to show that local AI experiences differ sharply across consumer hardware classes, making tiered architecture essential.[cite:103][cite:109][cite:136]

### VRAM budget rule

The full installed Pro product should target roughly 50% of available VRAM as its default local budget. This leaves room for rendering, framework overhead, fragmentation, spikes, and other system activity, which current VRAM guidance identifies as necessary for practical stability.[cite:133][cite:136][cite:139]

### Auto-recommendation

Onboarding and settings should detect likely hardware capacity and recommend the correct profile automatically, with expert override available later. This keeps the product accessible to mainstream users while preserving advanced control for power users.[cite:127][cite:136]

## Trust, permissions, and audits

### Permission architecture

The platform should implement capability-based permissions covering files, browser, email, memory, system tools, and future integrations. Each permission should be scoped by feature, action, resource, approval mode, and grant duration.[cite:123][cite:124][cite:126]

### Red-team readiness

The flagship should be built to survive serious red-team and trust review with threat models, scenario-based testing, visible audit trails, replayable action logs, and strong recovery/containment behavior. Current AI security guidance consistently emphasizes that production agent safety requires verifiable evidence and lifecycle testing.[cite:132][cite:135][cite:138]

## Roadmap phases

### Phase 0: doctrine and architecture lock

- Finalize product doctrine.
- Lock strategic moat layers.
- Define platform boundaries.
- Finalize architecture ownership map.
- Define evaluation metrics.[cite:155][cite:188]

### Phase 1: platform core

- Desktop shell.
- Local runtime.
- Reflex path.
- Settings/control center.
- Identity/persona foundations.
- Permission framework v1.
- Local-first state layer.[cite:102][cite:206]

### Phase 2: conversation core

- Text chat.
- STT/TTS integration.
- acknowledgment engine.
- routing engine.
- basic memory system.
- trust center v1.[cite:64][cite:74][cite:135]

### Phase 3: avatar and presence

- higher-quality facial animation.
- gaze/blink system.
- listening/thinking/speaking state behaviors.
- presence controller v1.
- stronger voice-avatar timing.[cite:43][cite:47]

### Phase 4: tools and autonomy

- browser and file workflows.
- safer automation.
- action approval framework.
- audit/replay surfaces.
- model escalation logic.[cite:123][cite:126][cite:207]

### Phase 5: memory and continuity

- richer multimodal memory.
- memory editing/governance.
- sync architecture.
- mobile companion rollout.
- longer-session continuity improvements.[cite:54][cite:82][cite:206]

### Phase 6: expansion to highest-tier companion quality

- deeper presence realism.
- richer motion scheduling.
- improved relationship continuity.
- advanced personal workflows.
- tighter human-standard UX refinement loops.[cite:194][cite:196]

## Success criteria

Aether Pro is successful when it is clearly not a wrapper product, when its core user-relationship layers are custom-controlled, when the assistant feels premium and socially coherent under real use, when trust and permissions are legible and auditable, and when hardware adaptation allows the product to scale from mainstream systems to high-performance installations without losing its core identity.[cite:193][cite:194][cite:196]
