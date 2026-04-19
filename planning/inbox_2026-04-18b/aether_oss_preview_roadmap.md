# Aether OSS Preview Specification and Roadmap

## Product doctrine

Aether OSS Preview is not intended to be a disposable demo or a thin wrapper around generic AI SaaS. It is a launch-fast but complete preview product that should already demonstrate the product family’s core values: premium UX, trust, conversational clarity, hardware-aware setup, and visible identity. Product requirements guidance in the AI era increasingly emphasizes that differentiating AI products need explicit experience standards rather than vague “feature parity” goals.[cite:188][cite:175]

The preview may use open-source and available-now components aggressively for speed, but it should still avoid a “close enough” mentality in the user-facing experience. The preview exists to prove that the final platform is being built toward a high bar, not to normalize shallow quality expectations.[cite:194][cite:195]

## Product purpose

Aether OSS Preview is the free, open-source wedge into the broader Aether platform family. Its job is to launch quickly, spread through the open-source community, and give users a complete early experience of the assistant concept with onboarding, permissions, avatar presence, and polished UI already treated as first-class product systems.[cite:98][cite:102][cite:111]

This product should optimize for fast distribution, trust, design polish, and architectural clarity rather than attempting the entire flagship experience at once. Current roadmap guidance for complex software strongly favors clear scope control and explicit subsystem boundaries over oversized first releases.[cite:155][cite:176]

## Product boundaries

### Included scope

The OSS Preview should include desktop app packaging, text chat, optional mic input, optional voice output, headshot avatar presence, lip-sync, onboarding wizard, terms/disclosures, simplified permissions, performance tier recommendation, and short tutorial/checklist flows.[cite:98][cite:99][cite:127]

The avatar should be a real conversational surface rather than a decorative overlay. A headshot or bust-level avatar with visible listening and speaking states is sufficient at this tier if timing, clarity, and polish are strong.[cite:98][cite:99][cite:101]

### Excluded or deferred scope

The preview should not attempt the full flagship stack: full-body photoreal motion, broad autonomous tooling, deep multimodal memory, advanced research pipelines, rich sync architecture, or maximum-fidelity rendering. Those belong in the Pro roadmap and should be shown only as future-facing showcase elements in this tier.[cite:155][cite:176]

## UX and design standard

### UX priority

The user experience is the top priority for the preview. Even in open-source form, the app should feel inviting, understandable, premium, and coherent to users across technical skill levels.[cite:189][cite:191][cite:197]

### Showcase quality

The preview should be visually strong enough to function as a showcase product, not just a utility shell. Current design guidance for AI-native products favors modular conversational layouts, emotionally aware interfaces, and polished identity surfaces rather than generic template dashboards.[cite:148][cite:151][cite:153]

### Onboarding standard

Onboarding must be non-technical, preset-driven, and progressive. Every meaningful option should expose an inline info explainer with plain-language meaning, recommended default, example use, and performance/privacy impact where relevant.[cite:127][cite:129][cite:131]

## Recommended tech stack

### Desktop application shell

**Recommended:** Tauri + TypeScript UI + Rust-backed native bridge. Tauri remains one of the strongest choices for a lightweight cross-platform desktop app when smaller package size, lower overhead, and Rust integration matter.[cite:102][cite:105][cite:111]

**Why this stack:**
- Smaller distribution size than Electron.[cite:102][cite:111]
- Better alignment with future Rust-based low-latency runtime work.[cite:102]
- Good fit for open-source packaging and faster desktop iteration.[cite:111]

### Front-end UI layer

**Recommended:** TypeScript with React for the desktop UI shell and onboarding/settings flows. React remains a practical default for complex interface composition, and strong ecosystem maturity still matters for a product with many settings, dialogs, and stateful panels.[cite:202][cite:206]

**Recommended UI approach:**
- Custom design system, not generic template UI.
- Motion used selectively for trust and clarity, not decoration.
- Tokenized component system for onboarding, settings, cards, modals, permission prompts, and trust center views.[cite:148][cite:151][cite:153]

### Local runtime and services

**Recommended:** Rust for local runtime orchestration where possible, with a Python sidecar for initial model and avatar service integration. This preserves launch speed while aligning with the longer-term plan to move latency-critical orchestration into lower-level code.[cite:102][cite:207][cite:212]

### Speech stack

**Recommended open-source STT candidates:**
- Parakeet TDT for ultra-low-latency streaming use cases.[cite:64]
- Whisper Large V3 Turbo or Distil-Whisper for faster throughput and broader flexibility.[cite:64]
- Moonshine for more edge/mobile-oriented paths later.[cite:64]

**Recommended open-source TTS starting direction:**
- XTTS-v2-class experimentation for expressive local speech reference work, with licensing reviewed carefully before commercial carry-forward.[cite:62]

### Avatar stack

**Recommended preview baselines:**
- MuseTalk for real-time lip-sync/talking-head quality benchmarking.[cite:98]
- TalkingHead for lightweight real-time avatar reference and rapid experimentation.[cite:99]
- Real-time Wav2Lip-style implementations for comparison/prototyping.[cite:101]

### Local state and settings storage

**Recommended:** SQLite-backed local settings/state layer with a simple typed access layer. For the preview, a full sync engine is unnecessary, but strong local persistence for onboarding choices, permissions, profile setup, and app state is important.[cite:206]

## Infrastructure and packaging

### Distribution

The preview should be packaged for low-friction install and open-source sharing, with simple releases, contributor-friendly structure, and clear optional update paths. Open community products benefit from easy install, visible roadmap direction, and a low-overhead desktop runtime.[cite:102][cite:111]

### Update strategy

Updates should be optional or recommended rather than broadly forced, except for critical security or compatibility breakage. Current app update guidance supports flexible default flows with stronger enforcement only in higher-severity cases.[cite:142][cite:149]

### Release channels

The preview should support at least stable and experimental channels, with beta added if release volume justifies it. This lets community testers move faster without destabilizing the core public experience.[cite:149]

## Permissions and trust

### Permission architecture

The preview should use a simplified but real least-privilege model, with capabilities scoped by action and resource where possible. Agentic AI safety guidance in 2026 consistently recommends minimal-footprint access, task-bounded permissions, and visible approval behavior for desktop and browser-capable agents.[cite:119][cite:123][cite:126]

### Initial capability groups

The preview should cover a constrained version of:
- local file read/draft access,
- limited browser access,
- local memory permissions,
- clipboard and export behaviors,
- user-approved drafting actions.[cite:119][cite:124]

### Trust center light

Even the preview should include a light trust center showing current permissions, recent assistant actions, disclosures, and simple memory controls. Trust becomes more believable when it is inspectable.[cite:135][cite:141]

## Performance model

### Required tiers

The preview should support Lite and Balanced modes by default, with an optional Enhanced mode where hardware allows. Consumer local AI guidance continues to show that low-, mid-, and high-resource systems need different model and asset strategies.[cite:103][cite:109][cite:136]

### Auto-detection

The preview should assess hardware and recommend a mode automatically during onboarding. This is especially important because the product is meant for all technical skill levels, not only users who understand VRAM and inference tradeoffs.[cite:127][cite:136]

## Roadmap phases

### Phase 0: definition and design

- Finalize preview scope.
- Finalize name and brand treatment.
- Create UI system and onboarding map.
- Define preview permission presets.
- Define hardware-tier rules.[cite:155][cite:176]

### Phase 1: shippable preview core

- Tauri app shell.
- React/TypeScript UI.
- Chat interface.
- Onboarding wizard.
- Settings surface.
- Disclosure and T&S flows.
- Local state persistence.[cite:102][cite:127]

### Phase 2: speech and avatar integration

- Mic input.
- STT integration.
- TTS integration.
- Headshot avatar rendering.
- Lip-sync integration.
- Listening/thinking/speaking state cues.[cite:64][cite:98][cite:99]

### Phase 3: trust and polish

- Permission prompts.
- Action history.
- Trust center light.
- First-run tutorial/checklist.
- Showcase/demo scenes.
- Performance auto-detection and recommendation.[cite:123][cite:127][cite:147]

## Success criteria

Aether OSS Preview is successful when users can install it easily, understand it without technical fluency, complete onboarding confidently, interact with a believable assistant presence, understand what is and is not permitted, and leave with a strong sense that the flagship platform is being built to a serious quality bar.[cite:127][cite:147][cite:188]
