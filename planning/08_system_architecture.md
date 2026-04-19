# 08 — System Architecture

The engines, event bus, and platform roles that make up the Aether system. Architecture is strictly separated so no single slow component breaks social presence.

---

## The six engines

The system is composed of six tightly-coupled but separately-owned engines. Each has its own timing contract, interface, and failure mode.

### 1. Interaction engine
- **Role:** Turn-taking, state machine, UI-visible status, acknowledgment timing, user intent framing.
- **Outputs:** visible assistant state (listening / thinking / acknowledging / speaking / idle), turn boundaries.
- **Latency budget:** instant (<100ms for state transitions).
- **Must-own layer:** yes.

### 2. Cognition engine
- **Role:** Reasoning, planning, routing, tool selection, local-vs-remote decisions, critic/verification.
- **Two paths internally:** reflex (local, fast) and deliberative (slow, deep). See [09_realtime_interaction.md](09_realtime_interaction.md).
- **Outputs:** route decisions, tool plans, completed answers.
- **Must-own layer:** yes (router and interaction logic; the underlying LLMs are swappable models).

### 3. Memory engine
- **Role:** Ephemeral / session / durable user / artifact / behavior memory. Semantic retrieval. Editing and governance.
- **Outputs:** memory hits, retrieval results, persisted memory writes.
- **Must-own layer:** yes. See [10_memory_architecture.md](10_memory_architecture.md).

### 4. Media engine
- **Role:** Audio capture, VAD, STT, TTS, lip-sync timing, viseme output, camera/audio handling, transport timing.
- **Outputs:** audio chunks, transcripts, synthesized speech, viseme streams.
- **Latency budget:** streaming — first audio out under target budget.
- **Ownership:** borrowable inference runtimes (STT/TTS models) behind our own streaming chunk model and interruption handler.

### 5. Presence / rendering engine
- **Role:** Avatar rendering, facial animation, eye behavior, idle motion, gesture scheduling, body motion (later).
- **Outputs:** rendered frames or animation data, state-linked behavior.
- **Ownership:** rendering surface borrowable; **presence controller must-own** (see [11_avatar_presence.md](11_avatar_presence.md)).

### 6. Policy / authorization engine
- **Role:** Permissions evaluation, capability checks, risk-class enforcement, approval workflow, logging, trust-center data.
- **Outputs:** allow / ask / deny decisions, audit events, logs.
- **Must-own layer:** yes. See [12_permissions_autonomy.md](12_permissions_autonomy.md).

---

## Engine separation principles

- **Each engine has its own timing budget.** Cognition's slow path never stalls Interaction's acknowledgment.
- **Engines communicate through the event bus**, not direct calls into each other.
- **No engine bypasses the Policy engine.** Tool calls, file access, browser actions — all routed through policy evaluation.
- **Swappable underlying primitives.** STT model, TTS model, LLM backend, rendering surface — replaceable.
- **Non-swappable control layers.** Presence controller, memory kernel, model router, reflex router, policy engine, persona compiler.

---

## The event bus

### Role
Internal pub/sub bus that preserves deterministic behavior under mixed local + remote timing. Every turn is a stream of events, not a blocking function call.

### Example event classes

| Event | Emitted by | Consumed by |
|-------|-----------|-------------|
| `speech_start` | Media | Interaction, Presence |
| `partial_transcript` | Media (STT) | Cognition, Interaction |
| `intent_hint` | Cognition (reflex) | Interaction |
| `memory_hit` | Memory | Cognition, Interaction |
| `route_decision` | Cognition | Interaction, Presence |
| `ack_phrase` | Cognition | Media (TTS), Presence |
| `tts_chunk` | Media (TTS) | Presence, audio out |
| `viseme_chunk` | Media | Presence |
| `gesture_state` | Presence | Rendering |
| `action_request` | Cognition | Policy |
| `action_approval` | Policy | Cognition, Interaction |
| `answer_commit` | Cognition | Interaction, Memory |
| `memory_write` | Cognition / Memory | Memory |
| `error_event` | any | Interaction, Presence, logs |

### Why event-driven
- Different engines complete at different speeds; blocking calls would mean silence.
- Events let the reflex path emit `ack_phrase` while the deliberative path still computes.
- Events let the presence controller decide what the avatar does while a tool is running.
- Events let the policy engine inject approval steps without rewriting the cognition path.

### Implementation direction
- Rust-based event bus for the realtime coordinator (low-latency, safe state machines).
- Typed events with schema; no untyped JSON dicts passed between engines.
- Event log persisted for audit / replay (see [13_trust_security_redteam.md](13_trust_security_redteam.md)).

---

## Platform split

### Desktop — primary control surface
- **Role:** Main control/configuration center. Primary daily-use surface.
- **Scope:** Full settings, full persona, memory editing, permission management, trust center, avatar mode, chat, voice.
- **Runtime:** Local-first. Local memory, local persona, local reflex path. Remote only where necessary (deliberative path, sync).

### Mobile — companion / use / capture
- **Role:** Companion use, consumption, quick capture.
- **Scope:** Chat, voice, lightweight avatar, memory view (not full edit), limited settings.
- **Not initially:** Full permission matrix, full persona edit, avatar pack management.
- **Post-Pro alpha.**

### Connectivity
- **Local-first** storage/sync. Desktop is the source of truth for user state.
- **Private network / Tailscale-style** connectivity considered for mobile ↔ desktop direct sync (privacy-preserving, avoids cloud round-trip).
- **Cloud** used for:
  - frontier LLM escalation (deliberative path)
  - optional sync relay (if private network unavailable)
  - no default silent data upload

### Sync philosophy
- Desktop owns canonical state.
- Mobile syncs *from* desktop, with conflict resolution (CRDT or op-log, TBD in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)).
- Sync is delta-based, encrypted, and battery-aware on mobile.
- Offline behavior: both sides remain fully usable with their local state.

---

## Layered system view

```
┌─────────────────────────────────────────────────────────┐
│                   User-facing surfaces                   │
│  Chat mode │ Settings/Sandbox │ Avatar mode │ Showcase  │
├─────────────────────────────────────────────────────────┤
│                  Presentation (UI shell)                 │
│          Desktop (Tauri + TS/React)  │  Mobile          │
├─────────────────────────────────────────────────────────┤
│                   Interaction engine                     │
│           Turn-taking, state, acknowledgment             │
├──────────┬───────────────┬──────────────┬──────────────┤
│ Cognition│    Memory     │  Presence    │   Policy     │
│  engine  │    engine     │   engine     │   engine     │
├──────────┴───────────────┴──────────────┴──────────────┤
│                      Media engine                        │
│     VAD │ STT │ TTS │ visemes │ audio I/O │ transport   │
├─────────────────────────────────────────────────────────┤
│                      Event bus                           │
│        typed events, persistent log, replay support      │
├─────────────────────────────────────────────────────────┤
│                    Local runtime core                    │
│   Local LLM (Gemma 4) │ local state │ local inference   │
├─────────────────────────────────────────────────────────┤
│              Remote services (optional)                  │
│  Frontier LLM │ Cloud sync relay │ External tools/APIs  │
└─────────────────────────────────────────────────────────┘
```

---

## Cross-cutting rules

### Every action through policy
- Cognition never calls a tool directly. It emits `action_request`; Policy evaluates; Interaction surfaces approval UI if needed; Cognition receives `action_approval` or denial.
- File I/O, browser navigation, email, system tools — all gated.

### Local-first for identity and state
- User identity, persona, permissions, memory state — canonical local.
- Never silently synced to a third party.
- Cloud is opt-in, explicit, scoped.

### Timing contracts are first-class
- Each engine publishes its timing SLA.
- The Interaction engine enforces acknowledgment timing (if Cognition exceeds reflex budget, acknowledgment fires automatically).
- See [09_realtime_interaction.md](09_realtime_interaction.md) for the two-speed cognition model.

### Observability and audit built in
- Every autonomous action is logged with timestamp, requester engine, policy decision, resource, outcome.
- Event log is replayable.
- Trust center surfaces human-readable action history.

---

## Cross-references
- Doctrine (must-own layers): [01_product_doctrine.md](01_product_doctrine.md#must-own-layers-custom-built-aether-pro-onward)
- Realtime / two-speed cognition: [09_realtime_interaction.md](09_realtime_interaction.md)
- Memory architecture: [10_memory_architecture.md](10_memory_architecture.md)
- Avatar / presence controller: [11_avatar_presence.md](11_avatar_presence.md)
- Permissions: [12_permissions_autonomy.md](12_permissions_autonomy.md)
- Trust / red-team / audit: [13_trust_security_redteam.md](13_trust_security_redteam.md)
- Tech stack: [16_tech_stack.md](16_tech_stack.md)
