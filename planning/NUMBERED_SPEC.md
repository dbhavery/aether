# Aether Numbered Specification Outline (1.0–18.0)

Formal numbered form of the master planning tree. Parallel to [MASTER_OUTLINE_TREE.md](MASTER_OUTLINE_TREE.md) — use whichever form is more useful for the current task (tree for scanning, numbered for ticketing/docs).

---

## 1.0 Product family definition

### 1.1 Umbrella product
- **1.1.1 Working umbrella name:** Aether
- **1.1.2 Umbrella purpose:** Aether is the master platform family for a multimodal AI assistant product centered on conversational interaction, local-first responsiveness, customizable identity, and a high-trust user experience.

### 1.2 Public open-source product
- **1.2.1 Working name:** Aether OSS Preview
- **1.2.2 Product role:** Free, open-source, fast-launch preview and showcase product. Wedge for adoption, visibility, community, and teaser marketing.
- **1.2.3 Primary goal:** Deliver a complete but narrower assistant experience using currently available open-source components, with strong onboarding, permissions, disclosures, and headshot lip-sync avatar interaction.

### 1.3 Public flagship product
- **1.3.1 Working names:** Aether Pro, Aether Core, or Aether One
- **1.3.2 Product role:** Full-performance public flagship. Commercial-grade multimodal assistant platform with advanced memory, permissions, avatar systems, and multi-device continuity.
- **1.3.3 Primary goal:** Deliver the full public vision with premium UX, performance tiers, strong trust posture, and expandable architecture. **Primarily custom-written software.**

### 1.4 Private personal branch
- **1.4.1 Working names:** Isabelle / Isabelle_Kunstig
- **1.4.2 Product role:** Private customized profile or branch built on top of the flagship Aether platform. Personal assistant/companion instance with unique private capabilities not distributed in the public product.
- **1.4.3 Architecture recommendation:** Isabelle should be implemented as a privileged profile/branch/configuration super-layer on top of the Aether Pro platform rather than a completely separate foundational codebase.

---

## 2.0 Product vision

### 2.1 Core vision
- **2.1.1 Central concept:** Build a production-grade conversational AI assistant that users primarily interact with through text/chat mode and avatar/video mode.
- **2.1.2 Experience goal:** The assistant should feel socially present, persistent, responsive, and helpful rather than merely functional or tool-like.
- **2.1.3 Quality standard:** Premium, first-to-market in experience quality, strategically differentiated through deep integration rather than superficial feature matching.

### 2.2 Design thesis
- **2.2.1 User expectation:** Many users prefer conversational, human-centered interfaces for getting work done.
- **2.2.2 Interface priority:** UI/UX quality is a primary strategic asset, not a cosmetic wrapper.
- **2.2.3 Product differentiation:** Comes from orchestration, memory, autonomy controls, presence, performance adaptation, and trust design — more than from any single model or avatar primitive.

---

## 3.0 Product modes

### 3.1 Chat/text mode
- **3.1.1 Role:** Primary functional interaction mode.
- **3.1.2 Capabilities:** Text input/output; optional mic input; optional voice output; can operate fully text-only.
- **3.1.3 Importance:** Must remain useful even when avatar features are disabled or unavailable.

### 3.2 Sandbox/settings/customization mode
- **3.2.1 Role:** Configuration and control center.
- **3.2.2 Core responsibilities:** Persona setup, model selection, memory controls, permissions and autonomy, hardware/performance settings, tool integrations, trust and audit visibility.

### 3.3 Video/avatar mode
- **3.3.1 Role:** Face-to-face conversational assistant mode.
- **3.3.2 Core experience:** User interacts with a visible avatar assistant in a live conversational format similar to a video call.
- **3.3.3 Expected features:** Listening behavior, speaking behavior, lip-sync, facial animation, natural motion, turn-taking cues; later-stage body and hand movement.

### 3.4 Voice-only interpretation
- **3.4.1 Clarification:** Voice-only is not treated as a separate major product mode.
- **3.4.2 Definition:** Voice-only is text/chat mode with microphone and optional voice output enabled; either party may remain muted visually or aurally.

---

## 4.0 Product split and planning separation

### 4.1 Need for separation
- **4.1.1 Planning principle:** Open-source preview, flagship platform, and private Isabelle instance are planned separately to avoid scope contamination and conflicting priorities.

### 4.2 Aether OSS Preview planning boundary
- **4.2.1 Scope:** Narrow, launch-fast, community-oriented, visually compelling, complete enough to feel real.
- **4.2.2 Exclusions:** Does not absorb the entire complexity of the flagship roadmap.

### 4.3 Aether Pro planning boundary
- **4.3.1 Scope:** Full public platform architecture, advanced systems, long-term premium product. Custom-written from here on.

### 4.4 Isabelle planning boundary
- **4.4.1 Scope:** Private customization layer on top of the flagship platform.

---

## 5.0 User experience principles

### 5.1 General UX goals
- **5.1.1 Accessibility target:** Attractive and usable across all technological skill levels.
- **5.1.2 Experience target:** Premium, modern, warm, confidence-building.
- **5.1.3 Mode-specific tone:** Chat/settings — calm, clear, controlled. Avatar — cinematic, emotionally rich.

### 5.2 State-of-the-art design requirement
- **5.2.1 Standard:** Target state-of-the-art UI and showcase design rather than generic dashboard patterns.
- **5.2.2 Design intent:** AI-native, companion-oriented, socially alive.

### 5.3 Showcase layer
- **5.3.1 Purpose:** Market the vision, onboard users emotionally, demonstrate capabilities with strong first impressions.
- **5.3.2 Showcase content candidates:** Meet your assistant; choose your assistant's style; understand trust and permissions; watch a task happen; preview future features.

---

## 6.0 Onboarding specification

### 6.1 Onboarding philosophy
- **6.1.1 Primary rule:** Onboarding must be as non-technical as possible.
- **6.1.2 Interaction model:** Users feel like they are setting up their assistant, not configuring an engineering system.
- **6.1.3 Usability approach:** Progressive disclosure, presets, simple language; no full configuration matrix upfront.

### 6.2 Onboarding flow requirements
- **6.2.1 Required characteristics:** Guided; friendly; skippable where appropriate; replayable later; clear in consequences and recommendations.
- **6.2.2 Suggested major steps:** Welcome and disclosure; assistant identity setup; interaction mode preferences; hardware/performance setup; permissions/autonomy setup; memory preferences; tutorial/checklist start.

### 6.3 Info-explainer requirement
- **6.3.1 Mandatory rule:** Every meaningful option must include an (i) info explanation link or pop-up.
- **6.3.2 Content requirements per explainer:** Plain-language definition; why this setting matters; recommended default; example use case; trust/privacy/performance impact if relevant.

### 6.4 Preset-first UX
- **6.4.1 Requirement:** Most users should complete onboarding via recommended presets.
- **6.4.2 Advanced options:** Available but collapsed/hidden until explicitly expanded.

---

## 7.0 Tutorial and help system

### 7.1 Tutorial philosophy
- **7.1.1 Requirement:** Tutorials exist but are not one long passive walkthrough.
- **7.1.2 Preferred structure:** Interactive, modular, context-aware, skippable.

### 7.2 Tutorial layers
- **7.2.1 Setup wizard:** Introduces core identity, permissions, and system mode choices.
- **7.2.2 First-run checklist:** 3–5 important first actions.
- **7.2.3 Inline walkthroughs:** Activated when the user first uses major features.
- **7.2.4 Reference layer:** Searchable help, explanations, replayable tutorials later.

---

## 8.0 Performance and hardware strategy

### 8.1 Constraint model
- **8.1.1 Hardware diversity:** User systems vary in VRAM, storage, CPU, capability.
- **8.1.2 Planning consequence:** Hardware adaptation built into product design and onboarding from the start.

### 8.2 Performance tiers
- **8.2.1 Lite tier:** Low VRAM/storage; smaller local models; lower-res assets; reduced cache; simpler avatar; more cloud assist.
- **8.2.2 Balanced tier:** Moderate systems; better reflex capability; better avatar quality; more persistent local assets and memory.
- **8.2.3 Full / Pro tier:** Strong systems; highest-quality local runtime; richest local behavior, assets, and avatar experience.

### 8.3 VRAM policy
- **8.3.1 Default policy:** Final Pro product targets ~50% of available VRAM as default local budget ceiling.
- **8.3.2 Rationale:** Preserve headroom for rendering, framework overhead, fragmentation, spikes, concurrent tasks, stability.
- **8.3.3 Suggested default budget envelope:** Lite 15–25%; Balanced 30–40%; Pro default 50%; Expert override optional higher cap with warnings.

### 8.4 Storage strategy
- **8.4.1 Requirement:** Heavy components installable as modular packs.
- **8.4.2 Components to modularize:** Model packs, voice packs, avatar asset packs, large caches, advanced local tools.

### 8.5 Hardware detection
- **8.5.1 Requirement:** Onboarding assesses likely hardware class.
- **8.5.2 Inputs:** VRAM, storage, microphone/camera, performance indicators.
- **8.5.3 Output:** Recommended preset and performance tier.

---

## 9.0 Core interaction and latency model

### 9.1 Latency requirement
- **9.1.1 Experience goal:** Fast and socially responsive.
- **9.1.2 Behavioral rule:** If full answer will take longer, assistant must acknowledge quickly — no silence.

### 9.2 Two-path cognition model
- **9.2.1 Reflex path:** Local, low-latency; quick acknowledgements, simple answers, state transitions, memory retrieval.
- **9.2.2 Deliberative path:** Slower; deep reasoning, research, tools, coding, higher-quality remote model use.
- **9.2.3 UX requirement:** Both paths feel like one coherent assistant.

### 9.3 Acknowledgement phrase pool
- **9.3.1 Requirement:** Select from a pool of short prewritten acknowledgement phrases when deeper work is needed.
- **9.3.2 Example purposes:** "Checking that." "Give me a moment." "I'm looking that up." "Let me verify that."

### 9.4 Presence continuity
- **9.4.1 Requirement:** Assistant remains socially present while thinking or waiting.
- **9.4.2 Avatar impact:** Visual behavior reflects listening, thinking, and responding states distinctly.

---

## 10.0 System architecture

### 10.1 Major engines
- **10.1.1 Interaction engine:** Turn-taking; visible state transitions; acknowledgement timing; user-facing flow.
- **10.1.2 Cognition engine:** Reasoning, planning, routing, tool selection, local vs remote decisions.
- **10.1.3 Memory engine:** Session memory, durable user memory, semantic retrieval, editing and governance.
- **10.1.4 Media engine:** Audio capture, VAD, STT, TTS, lip-sync timing, viseme output.
- **10.1.5 Presence/rendering engine:** Avatar rendering, gaze, blink, idle behavior, gesture scheduling, later body motion.
- **10.1.6 Policy/authorization engine:** Permission evaluation, resource scope checks, approval workflow, logging, trust-center data.

### 10.2 Event-driven structure
- **10.2.1 Requirement:** Event-driven internal architecture handling asynchronous mixed local/remote timing cleanly.
- **10.2.2 Example event classes:** speech_start; transcript_partial; memory_hit; route_decision; ack_emission; tts_chunk; viseme_chunk; action_request; action_approval; memory_write.

### 10.3 Platform roles
- **10.3.1 Desktop role:** Main control center and primary configuration surface.
- **10.3.2 Mobile role:** Companion use, access, later continuity layer.
- **10.3.3 Connectivity:** Local-first with optional private-network or similar connectivity patterns.

---

## 11.0 Memory architecture

### 11.1 Memory importance
- **11.1.1 Strategic role:** Central to personalization, continuity, companion feel.

### 11.2 Memory layers
- **11.2.1 Ephemeral turn memory:** Active immediate conversational context.
- **11.2.2 Session memory:** Context spanning a conversation session.
- **11.2.3 Durable user memory:** Long-lived preferences, biographical facts, recurring patterns.
- **11.2.4 Artifact memory:** Files, screenshots, documents, extracted facts, external content.
- **11.2.5 Behavior/persona memory:** Preferred assistant style, interaction habits, tone.

### 11.3 Memory governance
- **11.3.1 Requirement:** Users can review, edit, revoke, export, delete memory.
- **11.3.2 Quality controls:** Selective ingestion; novelty filtering; confidence weighting; provenance; retention rules.

---

## 12.0 Avatar and presence system

### 12.1 Long-term target
- **12.1.1 Goal:** Persistent, photorealistic, conversationally believable assistant avatar.
- **12.1.2 Clarification:** User knows it is AI; goal is realism and social presence, not deception.

### 12.2 MVP target
- **12.2.1 Scope:** Headshot avatar; real-time or near-real-time lip-sync; speech-driven facial animation; open-source-compatible implementation.

### 12.3 Avatar subsystem layers
- **12.3.1 Speech-to-face layer:** Visemes and mouth motion.
- **12.3.2 Facial expression layer:** Speech-linked and state-linked expressions.
- **12.3.3 Gaze and blink layer:** Eye behavior and realism cues.
- **12.3.4 Listening/thinking posture layer:** Non-speaking state presence.
- **12.3.5 Idle motion layer:** Subtle alive-state motion.
- **12.3.6 Gesture/body scheduler:** Later-stage hand and body movement.

### 12.4 Presence controller
- **12.4.1 Definition:** Dedicated control layer mapping internal assistant state to visible social behavior.
- **12.4.2 Importance:** Likely moat area — believable presence requires more than lip-sync alone.

---

## 13.0 Permissions and autonomy system

### 13.1 Core requirement
- **13.1.1 Requirement:** Assistant supports multiple levels of automated control and permissions.
- **13.1.2 UX requirement:** Permission setup is understandable and simple for non-technical users.

### 13.2 Permission philosophy
- **13.2.1 Principles:** Default deny; least privilege; capability-based access; scoped resources; time-limited grants; logging and review.

### 13.3 Permission layers
- **13.3.1 Feature access:** Whether a capability family exists at all.
- **13.3.2 Action scope:** What the assistant may do within that family.
- **13.3.3 Resource scope:** Which folders, domains, inboxes, or assets are in bounds.
- **13.3.4 Approval mode:** Auto-allowed, requires confirmation, or blocked.
- **13.3.5 Grant duration:** Per action, per task, per session, or persistent.

### 13.4 Capability groups
- **13.4.1 Files:** Read; create; edit; move/rename; delete; bulk actions.
- **13.4.2 Browser:** Read pages; navigate; extract; fill forms; upload/download; submit actions; session reuse/login.
- **13.4.3 Email:** Read metadata; read bodies; draft; edit drafts; send; attachments.
- **13.4.4 System/tools:** Clipboard; scripts; terminal; package installs; integrations.
- **13.4.5 Memory/data:** Save memory; use memory; export memory; delete or expire memory.

### 13.5 User-facing autonomy presets
- **13.5.1 Observer:** Minimal autonomy.
- **13.5.2 Assistant:** Read and draft oriented.
- **13.5.3 Operator:** Some scoped automated actions.
- **13.5.4 Power User / Builder:** Wider tool capability with warnings and logs.
- **13.5.5 Custom:** Full granular control.

### 13.6 Risk classes
- **13.6.1 Low:** Read/summarize style actions.
- **13.6.2 Medium:** Drafting, editing, non-final form filling.
- **13.6.3 High:** Sending, deletion, uploads, terminal execution.
- **13.6.4 Critical:** Financial, security, or irreversible high-impact actions.

### 13.7 Onboarding integration
- **13.7.1 Requirement:** Onboarding includes a permissions/autonomy step.
- **13.7.2 Plain-language output:** "Aether can do this." "Aether will always ask before this."

### 13.8 Settings integration
- **13.8.1 Required views:** Preset mode selector; granular capability matrix; scope editor; temporary grants; log viewer; emergency revoke all.

---

## 14.0 Trust, security, and red-team readiness

### 14.1 Trust goal
- **14.1.1 Requirement:** Designed to pass strong red-team review and support high user trust.

### 14.2 Trust-by-design requirements
- **14.2.1 User-visible trust elements:** Clear disclosures; understandable permissions; action history; reviewability; boundaries of what the assistant can and cannot do.

### 14.3 Red-team focus areas
- **14.3.1 Areas to test:** Prompt attacks; memory poisoning; browser misuse; data exfiltration; permission bypass; unsafe autonomy; incomplete logs; failure recovery.

### 14.4 Trust center
- **14.4.1 Requirement:** Product includes a trust center or equivalent surface.
- **14.4.2 Suggested contents:** Permission summary; recent actions; logs; memory controls; model/source disclosures; safety/privacy explanations.

---

## 15.0 Updates and release channels

### 15.1 Update policy
- **15.1.1 General rule:** Updates mostly optional or recommended, not universally forced.
- **15.1.2 Mandatory update exception:** Force only for critical security, compatibility, or trust-related fixes.

### 15.2 OSS Preview update stance
- **15.2.1 Policy:** Favor optional or opt-in updates for community friendliness.

### 15.3 Pro update stance
- **15.3.1 Policy:** Recommended-on by default; mandatory for critical issues.

### 15.4 Release channels
- **15.4.1 Required channels:** Stable; beta; experimental.

---

## 16.0 Technical stack directions

### 16.1 Language strategy
- **16.1.1 Realtime systems:** Rust or C++ for latency-critical runtime and media control.
- **16.1.2 App/UI:** TypeScript for shell, onboarding, settings, high-velocity UI work.
- **16.1.3 Experimentation:** Python for model experimentation, offline workflows, analysis.

### 16.2 Desktop framework direction
- **16.2.1 OSS Preview preference:** Tauri — lighter footprint, smaller package size, Rust alignment.
- **16.2.2 Alternative:** Electron remains viable but heavier.

### 16.3 MVP component direction (OSS Preview only)
- **16.3.1 Open-source avatar/lip-sync references:** MuseTalk; TalkingHead; real-time Wav2Lip-style references.

### 16.4 Flagship component direction (Aether Pro — custom-built)
- **16.4.1 Custom moat layers:** Reflex router; memory kernel; presence scheduler; model router; persona compiler; policy engine.

---

## 17.0 Roadmap structure

### 17.1 Planning method
- **17.1.1 Principle:** Separate fast-launch, flagship, and private-profile workstreams.
- **17.1.2 Additional principle:** Onboarding, permissions, trust, avatar, memory, performance, sync as first-class tracks.

### 17.2 Major roadmap tracks
- 17.2.1 Aether OSS Preview
- 17.2.2 Aether Public Pro
- 17.2.3 Isabelle private profile
- 17.2.4 Cross-cutting systems: onboarding, permissions, trust, performance, updates, memory, orchestration, sync

### 17.3 Immediate next documentation steps
- **17.3.1 Step 1:** Master numbered specification outline (this doc).
- **17.3.2 Step 2:** Segmented roadmap by product track.
- **17.3.3 Step 3:** Detailed subsystem blueprints.
- **17.3.4 Step 4:** Feature matrices, dependencies, milestone plans.

---

## 18.0 Open questions

See [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

### 18.1 Naming decisions
- 18.1.1 Final public flagship name
- 18.1.2 Final OSS preview naming
- 18.1.3 Final Isabelle formal naming

### 18.2 Scope boundary decisions
- 18.2.1 Exact MVP cut line
- 18.2.2 Exact first Pro milestone cut line
- 18.2.3 When full-body avatar becomes an actual target milestone

### 18.3 Technical decisions
- 18.3.1 Final desktop framework
- 18.3.2 Final mobile stack
- 18.3.3 Final local model stack
- 18.3.4 Final rendering stack
- 18.3.5 Final sync architecture

### 18.4 Trust/legal decisions
- 18.4.1 Final disclosure copy
- 18.4.2 Terms and conditions scope
- 18.4.3 Data retention defaults
- 18.4.4 Consent patterns

### 18.5 Evaluation metrics
- 18.5.1 Time to first acknowledgement
- 18.5.2 Time to useful answer
- 18.5.3 Avatar smoothness
- 18.5.4 Onboarding completion
- 18.5.5 Permission comprehension
- 18.5.6 Stability by performance tier
- 18.5.7 User trust and retention
