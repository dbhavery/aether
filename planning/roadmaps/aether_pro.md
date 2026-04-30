# Companion — Specification & Roadmap

> **Renamed 2026-05-18.** Public product = **Companion**. Internal codename / repo / database / Tauri identifier / Cargo workspace remain `aether`. The "Aether OSS Preview" wedge thesis was retired in the same doctrine pass — see `aether_oss_preview.md` tombstone and `01_product_doctrine.md` §6.

## Purpose

Companion is the **full-performance multimodal AI assistant product**. Photoreal full-body characters, deep memory, advanced avatar presence, multi-tier performance, strong permissions, mobile continuity, premium trust posture.

**Companion ships once — when it is complete.** No early-launch wedge. No headshot-only intermediate. No voice-only or chat-only release. See doctrine §5+§6+§7.

**Borrowed primitives are isolated behind our own interfaces and replaceable. The must-own moat layers are all custom-built.**

---

## Product doctrine (Companion context)

### Not a wrapper product
Companion is explicitly not:
- A ChatGPT wrapper
- A thin shell over avatar SaaS
- A "close enough" SaaS feature matcher
- A demo with settings

### Bar
- **"Close enough" is unacceptable** in any layer that defines the user relationship or product moat.
- **Bare-metal / custom creation is required** for strategic subsystems.
- **Highest-tier companion relationship** is the experience north star.
- **User experience outranks implementation convenience** in architecture decisions.
- **Photoreal full-body characters from the start — no headshot intermediate** (doctrine §5).
- **Single product, ships when complete — no interim release** (doctrine §6).
- **Self-test before Don review — visual artifacts via multimodal vision; frontend via use-as-user** (doctrine §8).

### Must-own moat layers (custom-built)
1. Presence controller
2. Companion memory kernel
3. Model router
4. Reflex router / interaction state machine
5. Policy / authorization engine
6. Persona compiler
7. Latency-aware social timing system
8. Onboarding / trust UX

See [../01_product_doctrine.md](../01_product_doctrine.md).

---

## Experience target

The flagship target is the **highest-tier assistant/companion relationship** the product can realistically build toward. Aspirational framing: "indistinguishable from a real human companion." North star, not SLA.

Operationalized through measurable elements:
- Acknowledgment timing (ms to first visible + audible response)
- Memory continuity (recall precision across sessions)
- Presence quality (believability under load)
- Control transparency (user always knows what's happening)
- Graceful fallback (network loss, model slow, tool failure)
- Stable personalization (no drift, no forgetting)

**Every architectural decision is judged by its effect on perceived responsiveness, trust, continuity, clarity, and relationship quality — not by implementation convenience.**

---

## Product scope (target end-state)

### Interaction
- Text chat (primary)
- Voice in / voice out
- Avatar mode (face-to-face)
- All modes interoperable — not artificial "mode switches"

### Avatar
- **Photoreal full-body characters from the start** (doctrine §5; ADR-0014 7-step pipeline; ADR-0013 runtime architecture).
- Rich facial animation (state-linked + speech-linked).
- Full presence controller (must-own; L3 Presence V1 DONE 2026-05-17 as state machine; renderer extension per ADR-0013).
- Gaze / blink / idle / listening / thinking / speaking / yielding states.
- 9-persona public cast — Aurora vertically first (recipe-proving), then 8 batched horizontally (per ADR-0014 sequencing).
- Pre-generated motion clip library + runtime blend + lip-sync overlay (per ADR-0013 — option chosen over on-demand video gen for latency, determinism, GPU-saturation discipline).

### Cognition
- Two-speed: reflex (local Gemma 4) + deliberative (local Gemma 4 large variant OR remote frontier)
- Model router decides dynamically
- Tool use: browser, files, email, system (scoped), integrations
- Planning, multi-step tasks, research

### Memory
- Five-layer architecture (ephemeral / session / durable / artifact / behavior)
- Multimodal ingestion (text + images + optional audio + files)
- Selective ingestion with novelty + salience filter
- Full governance (review / edit / revoke / delete / export)
- Confidence-weighted, provenance-tracked

### Permissions
- Capability-based, resource-scoped, time-limited
- Full 5-preset ladder (Observer / Assistant / Operator / Power User / Custom)
- Four risk classes with default approval behaviors
- Non-bypassable policy engine

### Performance
- Three tiers (Lite / Balanced / Full)
- 50% VRAM default policy
- Modular model / voice / avatar / tool packs
- Dynamic runtime adjustment
- Hardware auto-detection with override

### Sync
- Desktop canonical source of truth
- Mobile companion syncs via encrypted delta
- Private-network preferred (Tailscale-class); cloud relay as fallback
- Local-first — both sides usable offline

### Trust
- Full trust center (permissions, action history, memory, model disclosures, safety docs)
- Red-team-ready (threat modeling, scenario tests, audit logs, replay)
- Updates: recommended-on by default; mandatory only for critical fixes
- Three release channels (Stable / Beta / Experimental)

---

## Functional architecture

### Six engines (see [../08_system_architecture.md](../08_system_architecture.md))
1. Interaction engine
2. Cognition engine
3. Memory engine
4. Media engine
5. Presence / rendering engine
6. Policy / authorization engine

### Event-driven bus
- Typed events
- Append-only audit log
- Replay support
- Deterministic behavior under mixed local/remote timing

### Platform
- Desktop primary (Tauri or custom shell + React/TypeScript UI + Rust core)
- Mobile companion (React Native + native modules + Rust core via FFI, post-alpha)
- Local-first state; cloud opt-in, scoped

---

## Performance model

### Tiered runtime profiles
- **Lite / Balanced / Full** with downloadable asset and model packs
- Tier-aware local inference
- Hardware-specific defaults

### VRAM budget rule
**50% of available VRAM default** for the Full tier of the installed product. Leaves headroom for rendering, framework overhead, fragmentation, spikes. Expert override available with warnings.

### Auto-recommendation
Onboarding and settings detect likely hardware capacity and recommend profile automatically. Expert override available.

### Dynamic adjustment
Runtime can downgrade fidelity temporarily under VRAM pressure. Trust center surfaces the adjustment.

See [../14_performance_tiers_vram.md](../14_performance_tiers_vram.md).

---

## Trust, permissions, and audits

### Permission architecture
- Capability-based across files, browser, email, memory, system tools, integrations
- Each permission scoped by feature / action / resource / approval / duration
- Full 5-preset ladder + custom
- Non-bypassable policy engine

See [../12_permissions_autonomy.md](../12_permissions_autonomy.md).

### Red-team readiness
Built to survive serious red-team review:
- Threat modeling per release
- Scenario-based testing
- Visible audit trails
- Replayable action logs
- Strong recovery / containment behavior

See [../13_trust_security_redteam.md](../13_trust_security_redteam.md).

### Trust center
Full in-product trust surface:
- Permissions summary
- Full action history
- Memory controls
- Model / source disclosures
- Safety / privacy explanations
- Update / version info

---

## Tech stack (Companion)

```
Desktop shell:    Tauri (or custom) + TypeScript/React
Mobile shell:     React Native + native modules + Rust core (FFI)
Local runtime:    Rust (all hot paths), Python for offline tooling only
Local LLM:        Gemma 4 (Lite/Balanced/Full variants per tier)
Remote LLM:       Frontier (Anthropic/OpenAI/equivalent) for deliberative escalation
STT:              Streaming model + custom chunk/interrupt layer
TTS:              Streaming model + custom viseme sync + chunk timing
VAD:              Silero/WebRTC + custom turn-taking integration
Avatar:           Custom presence controller + borrowed rendering surface
Rendering:        Unreal / custom GL (TBD)
Transport:        WebRTC (avatar + sync), private network preferred
Storage:          SQLite + vector index, encrypted at rest
Sync:             CRDT or op-log (TBD), desktop-canonical, encrypted delta
Moat layers:      All custom
```

See [../16_tech_stack.md](../16_tech_stack.md).

---

## Release and update strategy

### Update policy
- **Recommended-on by default**
- Mandatory only for critical security / compatibility / trust fixes
- User-controllable; opt-in to channels

### Release channels
- **Stable** — default, conservative
- **Beta** — verified, newer features
- **Experimental** — advanced, can break

### Trust-affecting promotions
Any change to permissions, policy, logging, disclosures receives **additional review** before stable promotion.

See [../15_updates_releases.md](../15_updates_releases.md).

---

## UI and design direction

### Standard
State-of-the-art AI-native interface:
- Emotionally warm in identity surfaces
- Restrained and precise in settings
- Clear in permission flows
- Cinematic where avatar interaction benefits

### Principles
- Personalization
- Modular design systems
- Conversational UX
- No generic dashboard patterns
- No neon "AI aesthetic"
- Don's preference: deep 3D neumorphic monochrome

### Onboarding and settings
- Approachable for all skill levels
- Recommended presets
- Inline explainers on every option
- Progressive disclosure
- Scales from beginner-safe to power-user tooling

See [../05_ux_principles.md](../05_ux_principles.md).

---

## Operating model — GPU long-arc + parallel software (added 2026-05-18)

The character pipeline (ADR-0014 Steps 1–7 across 9 personas) is the dominant GPU workload from Phase 3 onward. The operating discipline:

- **GPU axis** — single sequential queue per `planning/plans/gpu_queue.md`. Pinned near 100% utilization. As one job finishes, output is staged and the next starts. **No parallel GPU jobs.**
- **Software axis** — runs in parallel on CPU per `planning/plans/parallel_software_tracks.md`. Sessions never wait on GPU; they claim from the parallel-track list. Tier 1 (close moat layers), Tier 2 (long-arc software), Tier 3 (finish-line work), Tier 4 (hygiene/governance).
- **Self-test gate** (doctrine §8) — every visual artifact and every frontend change is self-tested before reaching Don. Frontend = used-as-user via automation. Visual = multimodal vision evaluation against acceptance criteria. Failed self-tests do not reach Don.

This operating model holds through Phase 6 unless explicitly amended by a follow-up ADR.

---

## Roadmap phases

### Phase 0 — Doctrine and architecture lock
- Finalize product doctrine (done — see [../01_product_doctrine.md](../01_product_doctrine.md))
- Lock strategic moat layers (done — see doctrine)
- Define platform boundaries
- Finalize architecture ownership map
- Define evaluation metrics
- Decide monorepo vs multi-repo (see [../OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md))
- Build custom design system foundation

### Phase 1 — Platform core
- Desktop shell (Tauri)
- Rust local runtime
- Event bus (typed, persistent)
- Reflex path (Gemma 4 integration)
- Settings / control center
- Identity / persona foundations
- Permission framework v1 (policy engine)
- Local-first state layer (SQLite + vector index)
- Persona compiler v1

### Phase 2 — Conversation core
- Text chat (full UI)
- STT integration (custom chunk layer)
- TTS integration (custom streaming + chunk timing)
- Acknowledgment engine (phrase pool + timing)
- Model router v1 (local vs remote)
- Basic memory system (session + durable)
- Trust center v1 (permissions + action history)
- Info-explainer system on all settings

### Phase 3 — Avatar and presence (REVISED 2026-05-18)
**Status note:** L3 Presence V1 already DONE rot-guarded as state machine + bridge events (2026-05-17). Phase 3 from here forward = visual rendering + photoreal character delivery via the GPU long-arc.

- ADR-0013 runtime architecture: pre-generated motion clip library + runtime blend + lip-sync overlay.
- ADR-0014 per-persona character pipeline (7 steps): reference gen → identity LoRA → voice clone → video LoRA → motion library → lip-sync fine-tune → quality eval.
- ADR-0015 reference-gen lives inside Companion (not in CIGE/Forge).
- Aurora end-to-end first; remaining 8 batched horizontally after recipe locks.
- L3 Presence renderer scaffold (consumes motion library when it lands; logs state transitions until then) — claimable software work per `parallel_software_tracks.md` T1.4.
- Anti-uncanny stabilizer in clip-curation criteria + lip-sync model selection per ADR-0013 bake-off.
- **GPU pipeline is the long pole** — see `planning/plans/gpu_queue.md` for sequential job schedule. **Software-track sessions run in parallel** while GPU bakes; never wait on GPU.

### Phase 4 — Tools and autonomy
- Browser workflow capability (scoped)
- File workflow capability (scoped)
- Safer automation patterns
- Action approval framework (policy engine maturity)
- Audit / replay surfaces
- Model escalation logic (router maturity)
- Red-team test suite v1

### Phase 5 — Memory and continuity
- Richer multimodal memory (images, files)
- Memory editing / governance UI
- Sync architecture (desktop ↔ mobile)
- Mobile companion (React Native shell, read-focused)
- Longer-session continuity improvements
- Behavior memory (persona drift, adaptation)

### Phase 6 — Highest-tier companion quality (REVISED 2026-05-18)
**Note:** "Full-body avatar" and "photoreal rendering" are no longer Phase 6 stretch — they are Phase 3 required, locked by doctrine §5 and ADR-0014.

- Deeper presence realism (richer motion, broader gesture vocabulary)
- Richer motion scheduling (rare emotional registers, context-specific gestures)
- Improved relationship continuity
- Advanced personal workflows (integrations, triggers)
- Tighter human-standard UX refinement loops
- Possible escalation to ADR-0013 hybrid mode (on-demand generation for clips outside library coverage)
- Quality-Eval V2+ for ongoing regression watch

---

## Success criteria

Companion is successful when:
1. It is clearly **not a wrapper product** — the moat layers are custom-controlled.
2. Core user-relationship layers (presence, memory, timing, trust, policy) are custom.
3. The assistant feels **premium and socially coherent** under real use.
4. Trust and permissions are **legible and auditable**.
5. **Hardware adaptation** allows the product to scale from mainstream to high-performance without losing core identity.
6. Red-team review finds mitigations documented and testable.
7. Users report it feels like a companion, not an AI tool.

---

## Failure modes to avoid

- **Close-enough quality** in must-own layers (violates doctrine §1).
- **Borrowed moat** — depending on vendor for presence / memory / router / policy.
- **Headshot-first character work** — explicitly forbidden by doctrine §5; reintroduces the transition problem the photoreal full-body pipeline exists to avoid.
- **Interim release of any subsystem** — voice-only, chat-only, headshot-only, OSS-preview-only — all forbidden by doctrine §6.
- **Surfacing un-self-tested work to Don** — violates doctrine §8.
- **Hidden permissions** — destroys trust.
- **Cloud-first defaults** — violates local-first doctrine.
- **Feature-matching competitors** — the product is a relationship, not a checklist.
- **Premature mobile parity** — desktop must be rock-solid first.
- **Parallel GPU jobs** — violates GPU-saturation discipline; queue is single sequential per `gpu_queue.md`.
- **Software sessions waiting on GPU** — violates parallel-software-tracks operating model; pick from `parallel_software_tracks.md` instead.

---

## Cross-references
- Doctrine: [../01_product_doctrine.md](../01_product_doctrine.md)
- Vision: [../03_vision_and_thesis.md](../03_vision_and_thesis.md)
- Architecture: [../08_system_architecture.md](../08_system_architecture.md)
- Realtime: [../09_realtime_interaction.md](../09_realtime_interaction.md)
- Memory: [../10_memory_architecture.md](../10_memory_architecture.md)
- Avatar / presence: [../11_avatar_presence.md](../11_avatar_presence.md)
- Permissions: [../12_permissions_autonomy.md](../12_permissions_autonomy.md)
- Trust / red-team: [../13_trust_security_redteam.md](../13_trust_security_redteam.md)
- Performance tiers: [../14_performance_tiers_vram.md](../14_performance_tiers_vram.md)
- Updates: [../15_updates_releases.md](../15_updates_releases.md)
- Tech stack: [../16_tech_stack.md](../16_tech_stack.md)
- Open questions: [../OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md)
