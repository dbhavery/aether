# AETHER / ISABELLE MASTER PLANNING TREE

Full hierarchical planning tree. This is the anchor document — every `NN_*.md` file and roadmap in this folder expands one branch of this tree.

> **Planning-layer model [DECIDED 2026-04-18]:** the must-own planning split is **7 layers** (L1–L7), with the reflex router embedded inside L1 Interaction Timing as a distinct concept rather than a sibling layer. Canonical definition in [`01_product_doctrine.md`](01_product_doctrine.md) §"Must-own layers"; orchestration in [`plans/00_ORCHESTRATION_MAP.md`](plans/00_ORCHESTRATION_MAP.md); live decision log in [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md). The architectural "engines" enumerated below (§6) are the runtime substrate and are orthogonal to the L1–L7 moat partition.

---

## 0. Vision and product thesis

### 0.1 Core vision
- Build a production-grade multimodal AI assistant platform
- Primary user experience goal:
  - feels like conversing with a real assistant
  - supports text/chat and avatar/video interaction
  - remains useful, responsive, and trustworthy across user skill levels
- Product is not a hobby project, demo, or toy
- UX/UI quality is a top-level strategic priority, not just a surface layer
- System should feel socially present, not merely functional

### 0.2 Experience thesis
- People prefer to converse with a human-like assistant to get work done
- Conversation quality depends on:
  - low-latency acknowledgement
  - believable timing
  - strong memory continuity
  - permission trust
  - polished presentation
- Text mode and avatar mode are both first-class, not side features
- Voice-only is treated as text/chat plus mic/audio, not a separate major product mode

### 0.3 Strategic thesis
- Local-first where possible
- Cloud-backed where necessary
- Strong separation between:
  - real-time local reflex behavior
  - remote high-quality reasoning
  - avatar rendering and behavior
  - user permission/policy enforcement
- Product moat comes from integration, orchestration, memory, timing, trust, and UX
- Roadmap separates MVP wedge from flagship platform
- **OSS Preview may use open-source components aggressively; Aether Pro onward is primarily custom-written software**

---

## 1. Product family structure

### 1.1 Aether OSS Preview
- Free
- Open-source
- Launch-fast showcase / teaser product
- Desktop-first
- Uses open-source / available-now components only
- Narrowed scope:
  - text/chat
  - mic input
  - headshot avatar
  - lip-sync
  - onboarding wizard
  - T&S and disclosures
  - permissions
  - teaser surfaces for future features
- Purpose:
  - demonstrate vision
  - build community
  - gather feedback
  - establish early trust
  - create distribution momentum
- Should not overextend into deep full-platform complexity

### 1.2 Aether Public Pro
- Full-performance public flagship product
- Commercial / premium-ready architecture
- Full multimodal roadmap target
- Desktop + mobile continuity
- Advanced avatar, memory, tools, and autonomy
- Performance tiers and downloadable packs
- Strong trust, governance, and permission system
- Built as the real long-term public platform
- **Primarily custom-written; off-the-shelf only for non-moat, non-ceiling layers**

### 1.3 Isabelle / Isabelle_Kunstig
- Personal private branch/profile
- Built on top of Aether Public Pro
- 100% custom for personal assistant/companion use
- Private features and private tuning not included in public release
- Should ideally remain a privileged profile layer, not a fully separate base code stack
- Can include:
  - custom persona
  - custom appearance
  - custom voice
  - private memory tuning
  - private permissions
  - private workflows

### 1.4 Brand hierarchy
- Umbrella candidate: **Aether**
- Open-source preview candidate: Aether OSS / Aether Preview
- Public flagship candidate: Aether Core / Aether One / Aether Pro
- Personal profile: Isabelle / Isabelle_Kunstig
- Branding should support both community distribution and premium trust positioning

---

## 2. User-facing modes

### 2.1 Chat / text mode
- Primary core interaction mode
- Can operate text-only
- Can optionally include mic input
- Can mute assistant voice and/or user voice path
- Best mode for precision, fast work, and low-friction use
- Should remain useful even when avatar is disabled

### 2.2 Sandbox / settings / customization mode
- Product control center
- Persona customization
- Model selection
- Memory controls
- Permission controls
- Hardware / performance settings
- Integrations
- Logs / trust center
- Advanced tools and builder-facing controls

### 2.3 Video / avatar mode
- Face-to-face conversational mode
- User sees avatar assistant
- Avatar speaks, listens, responds, and animates
- Should feel like video call / FaceTime-style interaction
- Includes:
  - lip-sync
  - facial animation
  - eye behavior
  - listening posture
  - speaking behavior
  - thinking/acknowledgement behavior
  - later: hand and body movement
- Should degrade gracefully to simpler avatar levels on weaker systems

### 2.4 Voice-only interpretation
- Not a separate core product mode
- Effectively chat mode + microphone/audio channel
- Can coexist with text output only
- Should share same orchestration and permissions as main conversation mode

---

## 3. UX principles

### 3.1 UX goals
- State-of-the-art UI and showcase quality
- Attractive and available to all technology skill levels
- Emotionally warm but trustworthy
- Premium and cinematic where appropriate
- Calm and precise in settings and permissions
- Feels like an AI-native companion product, not a generic SaaS dashboard

### 3.2 Onboarding philosophy
- As non-technical as possible
- Guided setup of assistant rather than configuration of a system
- Progressive disclosure
- Recommended presets
- Advanced settings hidden by default
- Every option has info icon / pop-up explanation
- Every risky choice includes simple consequences/tradeoffs
- Should support beginners without limiting power users

### 3.3 Help and explanation pattern
- Info pop-up links for every option
- Plain-language descriptions
- Example use cases
- Recommended value indicator
- Privacy/performance/trust impact summaries
- Searchable help/reference later

### 3.4 Tutorial strategy
- Yes, but not one long tutorial
- Setup wizard during onboarding
- First-run checklist
- Contextual walkthroughs for major features
- Skippable and replayable
- Modular feature tutorials
- Searchable docs / short media reference later

### 3.5 Showcase strategy
- Dedicated product showcase/demo layer
- Used for launch, teaser, onboarding excitement, and marketing
- Modular narrative segments such as:
  - meet your assistant
  - choose your style
  - permissions and trust
  - watch a task happen
  - future feature teasers
- Should communicate both capability and trust

### 3.6 Design language targets
- Premium
- AI-native
- Socially alive
- Cinematic in avatar mode
- Clear in settings
- Trust-building in permissions
- Distinctive rather than generic template styling

---

## 4. Performance and hardware strategy

### 4.1 Constraint recognition
- Many users will have limited VRAM
- Many users will have limited drive storage
- Hardware diversity must be treated as a first-class design constraint
- Product cannot assume flagship GPU systems

### 4.2 Performance tiers
- **Lite**
  - Low VRAM / low storage systems
  - Smaller local models
  - Headshot avatar only
  - Lower resolution assets
  - Reduced cache size
  - More cloud assistance
  - Aggressive fallback behavior
- **Balanced**
  - Moderate local hardware
  - Improved avatar quality
  - Stronger local reflex stack
  - More persistent assets
  - Better local memory capacity
- **Full / Pro**
  - Strong local hardware
  - Highest-fidelity local runtime
  - Richer local behavior and animation
  - Larger persistent model and asset packs
  - Designed for premium flagship experience

### 4.3 VRAM policy
- Fully installed final Pro product targets 50% of available VRAM by default
- Rationale:
  - leave headroom for rendering
  - leave headroom for framework overhead
  - leave headroom for fragmentation
  - leave headroom for concurrency and spikes
  - preserve user system stability
- Suggested default envelopes:
  - Lite: 15–25%
  - Balanced: 30–40%
  - Pro default: 50%
  - Expert override: higher than 50% with warnings
- Onboarding should auto-detect hardware and recommend a tier

### 4.4 Storage strategy
- Tiered model packs
- Tiered asset packs
- Optional downloads for heavier features
- Limited local cache options
- Allow user to control retention and installed components

### 4.5 Hardware detection
- Detect VRAM
- Detect storage capacity
- Detect microphone/camera
- Detect likely performance class
- Recommend setup automatically during onboarding
- Allow manual override in advanced settings

---

## 5. Real-time interaction strategy

### 5.1 Latency goals
- Target sub-1000 ms response feel where possible
- If deeper reasoning takes too long, system must acknowledge immediately
- User should not feel silence or dead air
- Timing quality matters as much as raw answer quality

### 5.2 Two-speed cognition model
- **Reflex path**
  - Local
  - Low-latency
  - Handles acknowledgment
  - Handles quick simple answers
  - Handles local memory recall
  - Handles state transitions
  - Can decide when remote model escalation is needed
- **Deliberative path**
  - Slower
  - Deeper reasoning
  - Research
  - Tool use
  - Coding
  - High-quality paid remote LLM if needed
- User should see one seamless assistant, not two separate systems

### 5.3 Acknowledgement pattern
- Assistant chooses from a pool of prewritten phrases
- Phrases indicate:
  - looking that up
  - checking
  - needs a moment
  - verifying
- Should preserve social continuity while remote or long-running work proceeds
- Should map to avatar motion / presence behavior

### 5.4 Presence continuity
- Assistant should remain socially present while thinking
- Avatar should not freeze unnaturally
- Listening, thinking, and responding should each have distinct behavior states
- Interruptions and turn-taking should feel natural

---

## 6. Core system architecture

### 6.1 Major engines
- **Interaction engine**
  - turn-taking
  - state machine
  - acknowledgements
  - user intent framing
  - UI-visible status
- **Cognition engine**
  - local quick-answer logic
  - remote model routing
  - reasoning and planning
  - task/tool selection
  - critic/verification later
- **Memory engine**
  - user memory
  - session memory
  - artifact memory
  - semantic retrieval
  - memory editing
  - memory governance
- **Media engine**
  - VAD
  - STT
  - TTS
  - visemes
  - lip-sync
  - camera/audio handling
  - transport timing
- **Presence/rendering engine**
  - avatar rendering
  - facial animation
  - eye behavior
  - idle motion
  - gesture scheduling
  - full-body later
- **Policy/authorization engine**
  - permissions
  - capability checks
  - risk classes
  - approvals
  - logs
  - trust center data

### 6.2 Event-driven architecture
- Internal event bus
- Events include:
  - speech_start
  - partial_transcript
  - intent_hint
  - route_decision
  - memory_hit
  - ack_phrase
  - tts_chunk
  - viseme_chunk
  - gesture_state
  - answer_commit
  - memory_write
- Architecture preserves deterministic behavior under mixed local/remote timing

### 6.3 Platform split
- Desktop app as control/configuration center
- Mobile app as companion/use/capture layer
- Private network or Tailscale-like connectivity concept considered
- Local-first storage/sync
- Remote cloud used for high-quality intelligence and optional services

---

## 7. Memory architecture

### 7.1 Memory importance
- Essential to companion feel
- Should support semantic retention, processing, and recall
- Should be user-editable and governable
- Should improve continuity over time

### 7.2 Memory layers
- Ephemeral turn memory
- Session memory
- Durable user memory
- Artifact/document/file memory
- Behavior/persona memory
- Extracted preference memory

### 7.3 Memory controls
- Save
- Edit
- Revoke
- Delete
- Review
- Export
- Configure retention

### 7.4 Memory quality requirements
- Selective rather than indiscriminate ingestion
- Novelty filtering
- Confidence weighting
- Provenance tracking
- Recency and salience handling
- User-controlled forgetting

### 7.5 Product use of memory
- Quick personalization
- Relationship continuity
- Recurring task help
- Settings preferences
- Behavioral adaptation
- Future semantic companion depth

---

## 8. Avatar system

### 8.1 Long-term target
- Persistent photorealistic assistant
- Conversationally believable
- Listens, speaks, moves, responds naturally
- Can become full-body in final vision
- User knows it is AI; no deception objective

### 8.2 MVP target
- Headshot avatar
- Lip-sync
- Speech-driven animation
- Lower-level but complete preview product
- Open-source accessible baseline

### 8.3 Avatar layers
- Speech-to-viseme / speech-to-face
- Facial expression layer
- Gaze and blink logic
- Listening/thinking posture layer
- Idle behavior layer
- Gesture/body scheduler
- Cinematic stabilizer / anti-uncanny control

### 8.4 Presence controller concept
- Distinct from pure lip-sync
- Maps system state to social behavior
- Controls:
  - eye contact
  - blink timing
  - idle motion
  - speaking emphasis
  - listening cues
  - thinking behavior
- **Key moat area**

### 8.5 Rendering strategy
- Open-source or available-now primitives for MVP
- Deeper custom engine path for flagship
- Potential reliance on strong rendering engine for full realism
- Final system likely combines borrowed primitives with custom control/orchestration code

---

## 9. Permissions and autonomy

### 9.1 Requirement
- Multiple levels of automated control / permissions
- Easily configured in onboarding and settings
- Understandable to non-technical users
- Central to high-trust product design

### 9.2 Permission philosophy
- Default deny
- Least privilege
- Capability-based access
- Resource scoping
- Approval thresholds
- Time-limited grants
- Full logging and review

### 9.3 Permission layers
- Feature access
- Action scope
- Resource scope
- Approval mode
- Grant duration

### 9.4 Capability groups
- **Files** — read, create, edit, move/rename, delete, bulk operations
- **Browser** — open sites, read pages, extract data, fill forms, upload/download, submit actions, login/session reuse
- **Email** — read metadata, read bodies, draft, edit drafts, send, attachments
- **System/tools** — clipboard, scripts, terminal, package install, integrations
- **Memory/data** — save memories, use memories, export, delete / retention rules

### 9.5 User-facing permission modes
- Observer
- Assistant
- Operator
- Power User / Builder
- Custom

### 9.6 Risk classes
- Low risk
- Medium risk
- High risk
- Critical risk

### 9.7 Approval patterns
- Always allow within scope
- Ask every time
- Ask once per session/task
- Draft only
- Deny always
- Admin/advanced approval thresholds later

### 9.8 Onboarding integration
- Autonomy & permissions step
- Recommended preset
- Simple explanations
- Resource pickers
- "Aether will be able to..."
- "Aether will always ask before..."

### 9.9 Settings integration
- Preset selector
- Granular capability matrix
- Resource scope editor
- Temporary grants
- Logs / review history
- Emergency revoke all
- Trust center

### 9.10 Non-negotiable blocks
- No unrestricted disk access by default
- No sending email by default
- No silent uploads
- No risky domains by default
- No destructive system actions in safe presets
- All autonomous actions logged

---

## 10. Trust, security, and red-team readiness

### 10.1 Trust target
- High product trust level
- Built to pass red-team audits
- Visible safety and permission transparency
- Premium confidence rather than scary autonomy

### 10.2 Trust-by-design requirements
- Disclosures
- Informed onboarding
- Permission clarity
- Action logs
- Approval workflows
- Undo/recovery where possible
- Clearly bounded assistant capabilities

### 10.3 Red-team readiness areas
- Prompt attacks
- Memory poisoning
- Browser misuse
- File/data exfiltration
- Permission bypass
- Harmful autonomous actions
- Logging/audit completeness
- Failure/recovery behavior

### 10.4 Trust center concept
- Permissions summary
- Recent actions
- Logs
- Model/source disclosure
- Memory controls
- What the assistant can/cannot do
- Safety / privacy explanations

### 10.5 Release and audit support
- Stable / beta / experimental channels
- Staged release safety
- Telemetry for risky flows
- Replayable action history
- Retest loops for identified failures

---

## 11. Updates and release management

### 11.1 Update policy
- Not universally forced
- Mostly optional / recommended
- Mandatory only for critical security, compatibility, or trust fixes
- Different strategy for OSS Preview vs Pro

### 11.2 OSS Preview update stance
- Optional / opt-in favored
- Community-friendly
- Low-friction installation and experimentation
- Avoids alienating open-source users

### 11.3 Pro update stance
- Recommended-on by default
- Optional where possible
- Security and compatibility exceptions
- Trust-oriented versioning

### 11.4 Release channels
- Stable
- Beta
- Experimental

---

## 12. Proposed technical stack directions

### 12.1 Language split
- Rust or C++ for real-time / latency-critical layers
- TypeScript for app shell and UI
- Python for experimentation / ML / orchestration support
- Mobile-native or cross-platform layer later
- Rendering engine tech for avatar surface

### 12.2 Desktop app direction
- **Tauri is the long-term family desktop default** [DECIDED 2026-04-18]. See [`01_product_doctrine.md`](01_product_doctrine.md) §"Desktop framework doctrine" and [`plans/00_ORCHESTRATION_MAP.md`](plans/00_ORCHESTRATION_MAP.md) §2.
- UI stack across the family: HTML / CSS / JS (no Tkinter, no Qt for visual UI).
- Chosen because:
  - lighter footprint
  - smaller distribution
  - Rust integration
  - signed-updater and native-integration path for Pro and Isabelle
- **pywebview** is a tactical OSS-Preview-only exception if speed-to-demo absolutely requires it; explicitly non-doctrinal.
- Electron remains viable but heavier; not the family default.

### 12.3 Open-source MVP building blocks (OSS Preview only)
- **MuseTalk** as lip-sync/talking-head benchmark
- **TalkingHead** as lightweight real-time 3D/browser reference
- Real-time **Wav2Lip** variants as prototype references
- Available-now open-source tools to accelerate OSS Preview

### 12.4 Full-product deeper stack directions
- **Custom** orchestration layer
- **Custom** memory kernel
- **Custom** presence scheduler
- **Custom** model router
- Stronger rendering/animation engine
- Local-first sync/runtime architecture
- Audio2Face-class primitives only as baselines to study/beat
- MetaHuman-class rigs referenced for rendering ceiling, not locked as dependency

### 12.5 Network/sync concept
- Local-first desktop state
- Mobile companion
- Possible private networking / Tailscale-style connectivity
- Cloud used for high-end model escalation and sync support

---

## 13. Roadmap structuring principles

### 13.1 Planning approach
- Separate projects for planning and building
- Break complexity into multiple tracks
- Document dependencies before coding
- Use phased milestones
- Treat design, trust, and architecture as early deliverables

### 13.2 Planned tracks
- Aether OSS Preview track
- Aether Public Pro track
- Isabelle private profile track
- Onboarding/UX track
- Permissions/trust track
- Memory track
- Speech track
- Avatar track
- Orchestration track
- Platform/sync track
- Performance/hardware track

### 13.3 Immediate next deliverable direction
- Organize everything from session (this folder)
- Then build segmented detailed roadmap
- Likely sequence:
  - master outline (this doc)
  - two-track roadmap
  - subsystem blueprints
  - permission matrix
  - onboarding architecture
  - MVP 72-hour launch plan

### 13.4 Roadmap output expectations
- Highly segmented
- Detailed
- Layered several levels deep
- Planning-oriented
- Grounded in current research and feasibility
- Suitable to evolve into implementation plans later

---

## 14. Open questions / to define later

See [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) for the live list.

### 14.1 Naming finalization
- Confirm Aether family naming
- Choose public flagship exact name
- Decide whether Isabelle_Kunstig remains formal private brand

### 14.2 Exact app stack decisions
- Final desktop framework
- Final mobile framework
- Avatar engine choice(s)
- Exact local model stack
- Sync architecture details

### 14.3 MVP cut line
- Define exact feature set that can ship within hours/days
- Define what is teaser only
- Define what is postponed to Pro

### 14.4 Flagship cut line
- Define initial public Pro milestone
- Define when full-body becomes realistic target
- Define desktop-first vs mobile parity timing

### 14.5 Trust / legal / disclosure specifics
- Disclosure copy
- T&S scope
- Consent language
- Memory retention defaults
- Account / data policy details

### 14.6 Evaluation metrics
- Time to first acknowledgment
- Time to useful answer
- Avatar smoothness
- Permission trust comprehension
- Onboarding completion rate
- Tutorial completion / skip rate
- Crash/performance stability by tier
- User trust and retention signals
