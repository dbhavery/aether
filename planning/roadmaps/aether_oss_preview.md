# Aether OSS Preview — Specification & Roadmap

## Purpose

Aether OSS Preview is the **free, open-source, fast-launch wedge** for the broader Aether platform family. Its purpose is to demonstrate the product vision in a complete but intentionally constrained form: text chat, mic-enabled interaction, headshot avatar presence, full onboarding, permissions, disclosures, and teaser-level visibility into future capabilities.

This product optimizes for **speed to launch, community accessibility, trust, and visual polish** — not for maximum realism or total feature breadth.

---

## Product doctrine (OSS Preview context)

OSS Preview is NOT a disposable demo or a thin wrapper around generic AI SaaS. It is a launch-fast but **complete** preview product that already demonstrates the family's core values:
- premium UX
- trust
- conversational clarity
- hardware-aware setup
- visible identity

**Open-source / available-now components are acceptable here — aggressively so** — for speed. But even in preview form, shallow quality is not acceptable in the user-facing experience. The preview exists to prove the flagship is being built to a serious quality bar.

See [../01_product_doctrine.md](../01_product_doctrine.md) for the full doctrine.

---

## Product boundaries

### Included scope
- Desktop application packaging
- Text chat (primary mode)
- Optional mic input
- Optional voice output
- Headshot / bust-level avatar with real-time or near-real-time lip-sync
- Onboarding wizard with info-explainers
- Terms & conditions / disclosures flow
- Simplified permissions (least-privilege presets)
- Performance tier recommendation (Lite / Balanced, optional Enhanced)
- First-run tutorial / checklist
- Short showcase / demo surface
- Teaser surfaces for future features (locked, clearly marked "coming to Pro")

### Excluded / deferred scope
- Full-body photoreal avatar motion
- Broad autonomous tooling (email send, terminal execution, etc.)
- Deep multimodal memory with rich governance
- Advanced research pipelines
- Mobile companion
- Rich sync architecture
- Maximum-fidelity rendering
- Full 5-preset permission ladder
- Per-feature advanced configuration matrix

These belong in the Pro roadmap and are shown only as **future-facing showcase elements** in this tier.

---

## Primary users

### Community and early adopters
- Open-source users
- Technical explorers
- Design-forward early adopters
- Curious mainstream users sampling the concept

### Strategic role users
- Future contributors / testers / evangelists
- A polished preview with clear permission boundaries and strong first-run trust signals is more valuable than a rough internal dump for building early community credibility.

---

## Experience goals

### Core UX goals
- **Feels premium, simple, inviting, trustworthy.**
- Demonstrates Aether is not a research toy — it is a thoughtfully designed AI-native assistant product with onboarding, identity, permissions, and social presence as first-class systems.

### Demo goals
The preview answers three questions for a first-time user:
1. **What Aether is**
2. **What it can already do today**
3. **Why the full platform will be meaningfully more powerful later**

This is why the preview needs a built-in showcase structure rather than a bare interface.

---

## Functional requirements

### Core interaction
- Text chat as default mode
- Microphone input available as optional layer, not separate mode
- Muted text-only responses supported
- Optional spoken responses supported
- Basic state feedback: listening / thinking / replying
- Responsiveness and clarity prioritized over answer depth

### Avatar
- Headshot or bust-level talking avatar
- Real-time or near-real-time lip-sync
- Basic listening presence
- Visible state transitions (listening / thinking / speaking)
- Muted visual presence mode supported
- Speech-driven facial animation sufficient at this tier
- Degrades to Lite visual mode on weak hardware

### Onboarding
- First-run wizard
- Non-technical
- Progressive disclosure
- Recommended defaults everywhere
- Inline info explainer on every option
- 3–7 core steps
- Covers: disclosures, identity setup, mode preferences, hardware tier, permissions preset, memory preferences, first-run checklist
- Advanced settings hidden behind explicit expansion

See [../06_onboarding_spec.md](../06_onboarding_spec.md).

### Tutorial
- Short interactive first-run checklist (3 items)
- Inline walkthroughs on first use of major features
- Reference help center with searchable articles
- NO giant passive tour

See [../07_tutorial_help_system.md](../07_tutorial_help_system.md).

### Permissions
- Simplified preset ladder (Observer / Assistant default)
- Scoped capabilities for files, browser, memory, clipboard
- High-risk actions disabled or heavily limited by default
- Approval prompts for medium-risk actions
- Action history viewable in light trust center

See [../12_permissions_autonomy.md](../12_permissions_autonomy.md).

### Trust
- AI disclosure on first launch and in trust center
- Data locality disclosure (what stays local, what goes to cloud — minimal in OSS)
- Action history
- Memory controls (session / durable toggle)
- Clear boundaries stated

See [../13_trust_security_redteam.md](../13_trust_security_redteam.md).

---

## Technical direction

### Desktop shell
- **Tauri** + Rust backend + TypeScript/React frontend
- Smaller distribution size than Electron
- Rust alignment for long-term runtime work
- Good fit for open-source packaging

### Local runtime
- Rust for core runtime orchestration where possible
- Python sidecar for initial model and avatar service integration (transitional — moves to Rust in Pro)

### Local LLM
- **Gemma 4** (default, smallest variant for OSS Preview)
- Reflex path: always Gemma 4
- Deeper tasks: deferred to remote (if user provides API key) or gracefully degraded

### STT
- Parakeet TDT (ultra-low-latency streaming)
- Whisper Large V3 Turbo / Distil-Whisper (flexible)
- Moonshine (edge/mobile, later)

### TTS
- XTTS-v2-class for expressive local speech (licensing reviewed for commercial carry-forward)
- Open TTS fallbacks: Piper, Coqui, Kokoro

### Avatar
- **MuseTalk** — real-time lip-sync benchmark
- **TalkingHead** — lightweight real-time 3D/browser avatar
- **Wav2Lip variants** — prototype / comparison

### UI
- React + TypeScript
- Custom design system (not template UI)
- Motion for trust and clarity, not decoration
- Dark-first; deep 3D neumorphic monochrome direction

### Storage
- SQLite-backed local state
- Settings, onboarding choices, permissions, memory — persisted locally
- No cloud sync in OSS Preview

See [../16_tech_stack.md](../16_tech_stack.md) for full stack detail.

---

## Performance strategy

### Required tiers
- **Lite** — default for most systems
- **Balanced** — where hardware allows
- **Optional Enhanced** — for stronger systems (subset of Full capabilities)

### Hardware auto-detection
- Onboarding assesses VRAM, storage, mic, camera, network
- Recommends tier automatically
- User can override

### VRAM budget (OSS Preview)
- Lite: 15–25% of detected VRAM
- Balanced: 30–40%
- Enhanced: up to 50%

See [../14_performance_tiers_vram.md](../14_performance_tiers_vram.md).

---

## Trust and safety (OSS Preview scope)

### Disclosures
- AI-generated assistant and avatar — clearly disclosed
- What the assistant can and cannot do — clearly stated
- Data stays local unless user explicitly enables remote model

### Logging and action review
- Visible action history for permissioned tasks
- User-approved actions logged with intent / target / outcome

### Red-team posture
- Built with simplified but real trust controls
- Aligned with future red-team expectations
- Threat modeling and permission bypass testing early, not late

See [../13_trust_security_redteam.md](../13_trust_security_redteam.md).

---

## UI and design direction

### Visual positioning
- **Premium teaser of a bigger product**, not a raw dev utility.
- AI-native, emotionally warm, trustworthy.
- Not a SaaS dashboard. Not a ChatGPT clone.
- Distinctive design system, not template styling.

### Showcase surfaces
The OSS Preview includes a short showcase layer:
- Meet your assistant
- Choose your style
- See permissions work
- Watch a simple task happen
- Preview future features (clearly marked "in Pro")

Modular, chapter-based, short, skippable, replayable.

See [../05_ux_principles.md](../05_ux_principles.md#showcase-layer).

---

## Distribution and community strategy

### Open-source positioning
- Designed for open-source community distribution
- Simple install, easy trial, visible roadmap
- Contributor-friendly structure
- GitHub-first releases
- Clear README, contribution guide, issue templates

### Update policy
- Optional / opt-in favored
- Critical security updates the only mandatory class
- Non-nagging, respectful notification style
- Stable + Experimental channels (+ Beta if volume justifies)

See [../15_updates_releases.md](../15_updates_releases.md).

### Naming
- Working: **Aether OSS Preview** (may shorten to Aether OSS or Aether Preview)
- Final naming in [../OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md#naming)

---

## Roadmap phases

### Phase 0 — Definition and design
- Finalize preview scope
- Finalize name and brand treatment
- Create UI system and onboarding map
- Define preview permission presets
- Define hardware-tier rules
- Build showcase narrative script

### Phase 1 — Shippable preview core
- Tauri app shell
- React/TypeScript UI framework
- Custom design system foundation (tokens, components)
- Chat interface
- Onboarding wizard (all 7 steps)
- Settings surface
- Disclosure and T&S flows
- Local state persistence (SQLite)
- Gemma 4 integration (smallest variant, reflex path)

### Phase 2 — Speech and avatar integration
- Mic input + VAD
- STT integration (Parakeet or Whisper Turbo)
- TTS integration (open TTS)
- Headshot avatar rendering
- Lip-sync integration (MuseTalk or Wav2Lip-class)
- Listening / thinking / speaking state cues
- Basic presence behavior

### Phase 3 — Trust and polish
- Permission prompts and presets
- Action history
- Light trust center (permissions + recent actions + AI disclosure + memory controls)
- First-run tutorial / checklist
- Inline walkthroughs for major features
- Showcase / demo scenes
- Performance auto-detection and recommendation
- Final design polish pass
- Launch packaging (installers, GitHub release, README, contrib guide)

---

## Success criteria

Aether OSS Preview is successful when:
1. Users install it easily.
2. Non-technical users complete onboarding confidently.
3. Users interact with a believable assistant presence.
4. Users understand what is and is not permitted.
5. Users leave with a strong sense that **the flagship platform is being built to a serious quality bar**.
6. The open-source community can contribute without barriers.
7. The preview looks and feels like a premium product — not a research demo.

---

## Failure modes to avoid

- **Overbuilding the avatar** and delaying launch
- **Underbuilding onboarding** and looking like a dev toy
- **Missing trust UX** and feeling reckless
- **Template UI** and looking generic
- **Technical jargon in the main flow** and alienating non-technical users
- **Forced updates** and alienating open-source audience
- **Incomplete permissions model** and failing early trust test

---

## Cross-references
- Doctrine: [../01_product_doctrine.md](../01_product_doctrine.md)
- Product family: [../02_product_family.md](../02_product_family.md)
- Vision: [../03_vision_and_thesis.md](../03_vision_and_thesis.md)
- Modes: [../04_user_modes.md](../04_user_modes.md)
- UX principles: [../05_ux_principles.md](../05_ux_principles.md)
- Onboarding: [../06_onboarding_spec.md](../06_onboarding_spec.md)
- Permissions: [../12_permissions_autonomy.md](../12_permissions_autonomy.md)
- Trust: [../13_trust_security_redteam.md](../13_trust_security_redteam.md)
- Performance tiers: [../14_performance_tiers_vram.md](../14_performance_tiers_vram.md)
- Updates: [../15_updates_releases.md](../15_updates_releases.md)
- Tech stack: [../16_tech_stack.md](../16_tech_stack.md)
- Open questions: [../OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md)
