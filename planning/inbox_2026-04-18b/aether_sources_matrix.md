# Aether Source Matrix

This document lists the external sources that informed the Aether OSS Preview specification, Aether Pro specification, and Aether cross-system architecture documents. It groups sources by theme so they can be audited, replaced, or extended as the project evolves.[cite:170][cite:171][cite:172]

## Table legend

- **ID**: Internal short identifier used in this matrix.
- **Type**: Web article, blog, guide, benchmark, etc.
- **Topic**: Main subject of the source.
- **Why used**: How the source informed the Aether specifications.
- **Docs**: Which Aether specs the source supports (`OSS`, `PRO`, `XSYS`).

## UX, onboarding, and tutorial design

| ID | Type | Topic | Why used | Docs |
|----|------|-------|----------|------|
| UX-ONB-1 | Web | User onboarding best practices 2026[cite:127] | Used to justify progressive, non-technical onboarding with presets, inline explanations, and short flows. | OSS, PRO, XSYS |
| UX-ONB-2 | Web | Onboarding examples 2026[cite:128] | Informed the need for guided checklists, contextual walkthroughs, and modular tutorials. | OSS, PRO, XSYS |
| UX-ONB-3 | Web | Progressive disclosure explanation[cite:129] | Supported the requirement to hide advanced controls behind expandable sections for non-technical users. | OSS, PRO, XSYS |
| UX-ONB-4 | Web | macOS onboarding best practices[cite:130] | Helped calibrate expectations for desktop onboarding experience quality. | OSS, PRO |
| UX-ONB-5 | Web | SaaS onboarding flow best practices[cite:131] | Informed the structure for persona setup, permissions setup, and performance tier selection. | OSS, PRO, XSYS |
| UX-ONB-6 | Web | Onboarding content that scales 2026[cite:150] | Guided the modular tutorial/help system design. | OSS, PRO, XSYS |

## UX/UI trends and product design

| ID | Type | Topic | Why used | Docs |
|----|------|-------|----------|------|
| UX-DES-1 | Web | UX design guide 2026[cite:189] | Supported the emphasis on premium, human-centered UI and experience as a core product constraint. | OSS, PRO, XSYS |
| UX-DES-2 | Web | UX trends shaping 2026[cite:190] | Informed the direction toward conversational, emotionally aware product surfaces. | PRO, XSYS |
| UX-DES-3 | Web | UX best practices 2026[cite:191] | Reinforced requirements around clarity, feedback, and ease-of-use in the UI. | OSS, PRO |
| UX-DES-4 | Web | UI/UX trends 2026[cite:192] | Helped define the visual standard for "state-of-the-art" product presentation. | PRO |
| UX-DES-5 | Web | SaaS product design trends 2026[cite:148] | Backed the decision to avoid generic dashboards and emphasize AI-native UI patterns. | OSS, PRO |
| UX-DES-6 | Web | SaaS UI design shifts 2026[cite:151] | Informed the modular design and conversational surfaces across Aether. | PRO, XSYS |
| UX-DES-7 | Web | SaaS UI design trends 2026[cite:153] | Supported the move away from template aesthetics in favor of custom design systems. | OSS, PRO |
| UX-DES-8 | Web | Humanizing AI product experience[cite:196] | Grounded the assistant/companion relationship standard and human-standard expectations. | PRO, XSYS |

## Build vs buy, custom stack, and product doctrine

| ID | Type | Topic | Why used | Docs |
|----|------|-------|----------|------|
| BVB-1 | Web | Build vs buy for products 2026[cite:193] | Used to justify custom ownership of core differentiator layers instead of relying on generic SaaS wrappers. | PRO, XSYS |
| BVB-2 | Web | Custom SaaS development build vs buy[cite:195] | Supported the decision to treat orchestration, presence, memory, and policy as custom-built moats. | PRO, XSYS |
| BVB-3 | Web | Fintech tech stack build vs buy[cite:200] | Provided additional evidence for selective use of external primitives and owning core logic. | PRO, XSYS |
| BVB-4 | Web | Data stack build vs buy trends 2026[cite:198] | Helped frame which infrastructure components can be safely outsourced. | PRO, XSYS |

## Software specification and roadmap structure

| ID | Type | Topic | Why used | Docs |
|----|------|-------|----------|------|
| SPEC-1 | Web | Software requirements spec template 2026[cite:170] | Informed the high-level structure and use of separate follow-on spec documents. | OSS, PRO, XSYS |
| SPEC-2 | Web | Writing SRS in 2026[cite:171] | Supported the numbered outline, traceability mindset, and separation of concerns. | OSS, PRO, XSYS |
| SPEC-3 | Web | Software requirements trends[cite:172] | Encouraged explicit doctrine and traceability between requirements and evidence. | OSS, PRO, XSYS |
| SPEC-4 | Web | Software development plan 2026[cite:155] | Guided the segmentation into preview vs flagship vs cross-system tracks. | OSS, PRO, XSYS |
| SPEC-5 | Web | Software architecture principles 2026[cite:156] | Supported explicit engine separation (interaction, cognition, memory, policy, presence). | PRO, XSYS |
| SPEC-6 | Web | Engineering roadmap guide 2026[cite:176] | Influenced phased milestones and platform-first architecture. | OSS, PRO |
| SPEC-7 | Web | AI product strategy 2026[cite:163] | Helped frame Aether as a platform with moat-oriented subsystems. | PRO |
| SPEC-8 | Web | Custom software SRS 2026[cite:174] | Reinforced separation of product-level and subsystem-level specs. | OSS, PRO, XSYS |

## Local-first, offline-first, and sync

| ID | Type | Topic | Why used | Docs |
|----|------|-------|----------|------|
| LCL-1 | Web | Offline-first tech stack 2026[cite:206] | Supported the recommendation for local DB + sync layer and local-first state. | OSS, PRO, XSYS |
| LCL-2 | Web | Local-first architecture advocacy 2026[cite:164] | Reinforced local-first principle and client-owned state. | PRO, XSYS |
| LCL-3 | Web | Local-first value article[cite:84] | Provided conceptual backing for local-primary data models and sync. | PRO, XSYS |

## Hardware, VRAM, and performance tiers

| ID | Type | Topic | Why used | Docs |
|----|------|-------|----------|------|
| HW-1 | Web | GPU requirements for LLMs/VRAM 2026[cite:133] | Informed the 50% VRAM default budget and headroom practices. | PRO, XSYS |
| HW-2 | Web | How much VRAM for AI in 2026[cite:136] | Supported performance tiering and VRAM planning. | OSS, PRO, XSYS |
| HW-3 | Web | Best GPU for LLM in 2026[cite:109] | Provided context on consumer GPU classes and tier needs. | OSS, PRO |
| HW-4 | Web | Local LLM VRAM guide 2025[cite:139] | Reinforced VRAM budgeting and practical local inference constraints. | PRO |
| HW-5 | Web | GPU selection for AI in 2026[cite:103] | Backed explicit tier definitions (Lite/Balanced/Full). | OSS, PRO |

## Speech (STT/TTS) and speech-to-speech

| ID | Type | Topic | Why used | Docs |
|----|------|-------|----------|------|
| SPEECH-1 | Web | Best open-source STT models 2026[cite:64] | Used to recommend STT candidates such as Parakeet and Whisper variants. | OSS, PRO |
| SPEECH-2 | Web | Open-source TTS models overview[cite:62] | Informed TTS research direction and expressive local voice experimentation. | OSS, PRO |
| SPEECH-3 | Web | Speech-to-speech local agent stack[cite:65] | Provided patterns for streaming STT/TTS integration. | PRO |
| SPEECH-4 | Web | Speech-to-speech API architecture 2026[cite:74] | Influenced low-latency voice loop and routing considerations. | PRO |

## Avatar, facial animation, and presence

| ID | Type | Topic | Why used | Docs |
|----|------|-------|----------|------|
| AVA-1 | Web | MuseTalk real-time lip sync[cite:98] | Used as reference for open-source preview avatar lip-sync options. | OSS, PRO |
| AVA-2 | Web | TalkingHead 3D head avatar[cite:99] | Informed preview talking-head implementation options. | OSS |
| AVA-3 | Web | Realtime Wav2Lip repo[cite:101] | Provided another baseline for lip-sync research and experimentation. | OSS |
| AVA-4 | Web | NVIDIA Audio2Face open-sourcing[cite:43] | Grounded recommendation for Audio2Face-class facial animation primitives. | PRO |
| AVA-5 | Web | Audio2Face open source coverage[cite:53] | Additional context on open licensing and Avatar stack options. | PRO |
| AVA-6 | Web | Real-time AI conversations with MetaHumans[cite:47] | Informed recommendation for Unreal-class rendering surfaces. | PRO |
| AVA-7 | Web | MetaHuman animator workflows[cite:86] | Helped specify possible avatar pipelines for flagship. | PRO |
| AVA-8 | Web | Audio-driven realistic facial animation research[cite:58] | Supported the presence engine and speech-to-face architecture decisions. | PRO |
| AVA-9 | Web | Hologram from AI avatar guide 2026[cite:29] | Provided insight into presence and social timing considerations. | PRO |

## Agent stack, orchestration, and infrastructure

| ID | Type | Topic | Why used | Docs |
|----|------|-------|----------|------|
| AGENT-1 | Web | 7 layers of agentic AI stack 2026[cite:207] | Supported explicit multi-layer architecture (runtime, policy, tools, observability). | PRO, XSYS |
| AGENT-2 | Web | AI agent infrastructure guide[cite:212] | Informed separation of orchestration, policy, storage, and observability planes. | PRO, XSYS |
| AGENT-3 | Web | LLM orchestration/tool frameworks overview[cite:73] | Guided the decision to build a custom router and interaction core. | PRO |
| AGENT-4 | Web | Observability updates for AI agents 2026[cite:210] | Supported the requirement for traces, metrics, and action logs. | PRO, XSYS |

## Security, permissions, and red-teaming

| ID | Type | Topic | Why used | Docs |
|----|------|-------|----------|------|
| SEC-1 | Web | Desktop AI agent safety and permissions[cite:119] | Motivated least-privilege permission design and scoped capabilities. | OSS, PRO, XSYS |
| SEC-2 | Web | AI browser agents and risks[cite:113] | Highlighted browser tool risk considerations. | PRO, XSYS |
| SEC-3 | Web | AI browser security and agent risk[cite:115] | Informed browser permission design and domain scoping. | PRO, XSYS |
| SEC-4 | Web | Minimal-footprint principle for autonomous agents[cite:123] | Backed the requirement for task-bounded and time-bounded access. | PRO, XSYS |
| SEC-5 | Web | Agentic AI risks and governance gap[cite:121] | Motivated red-team readiness and governance design. | PRO, XSYS |
| SEC-6 | Web | AI and data governance guide 2026[cite:118] | Supported logging, auditability, and memory governance decisions. | PRO, XSYS |
| SEC-7 | Web | AI red-teaming landscape 2026[cite:132] | Guided red-team scope and trust-by-design expectations. | PRO, XSYS |
| SEC-8 | Web | AI red-teaming practices 2026[cite:135] | Reinforced need for scenario-based testing and evidence-backed safety. | PRO, XSYS |
| SEC-9 | Web | Agentic AI risks overview[cite:126] | Informed risk classes and high/critical-risk approval patterns. | PRO, XSYS |

## Updates and release management

| ID | Type | Topic | Why used | Docs |
|----|------|-------|----------|------|
| UPD-1 | Web | In-app update flows (Android)[cite:142] | Informed flexible vs immediate update strategies. | OSS, PRO, XSYS |
| UPD-2 | Web | Best practices for app maintenance & updates[cite:144] | Helped calibrate update expectations and maintenance posture. | PRO |
| UPD-3 | Web | Mandatory app update strategies[cite:149] | Backed the choice of optional-by-default, mandatory-for-critical model. | OSS, PRO, XSYS |

## Tech stack and app development

| ID | Type | Topic | Why used | Docs |
|----|------|-------|----------|------|
| STACK-1 | Web | Tauri in 2026 cross-platform guide[cite:102] | Supported recommendation of Tauri for desktop shell. | OSS, PRO, XSYS |
| STACK-2 | Web | Tauri vs Electron guidance 2026[cite:105] | Reinforced Tauri’s smaller footprint and Rust alignment. | OSS, PRO |
| STACK-3 | Web | Desktop frameworks comparison 2026[cite:111] | Provided context on Tauri vs Electron vs others. | OSS, PRO |
| STACK-4 | Web | Mobile app frameworks with AI 2026[cite:203] | Guided React Native vs native mobile framework decisions. | PRO, XSYS |
| STACK-5 | Web | App dev tech stack selection 2026[cite:204] | Helped reason about language/framework choices. | PRO |
| STACK-6 | Web | Mobile tech stacks 2026[cite:205] | Provided mobile-specific stack tradeoffs. | PRO |
| STACK-7 | Web | Mobile tech stack selection 2026[cite:213] | Supported later-stage native mobile choices. | PRO |

## Memory and multimodal agents

| ID | Type | Topic | Why used | Docs |
|----|------|-------|----------|------|
| MEM-1 | Web | Lifelong multimodal agent memory research[cite:54] | Informed structured, selective memory design and multimodal memory plans. | PRO, XSYS |
| MEM-2 | Web | AI agent memory frameworks 2026[cite:70] | Guided memory governance and user-editability goals. | PRO |

## Miscellaneous supporting sources

| ID | Type | Topic | Why used | Docs |
|----|------|-------|----------|------|
| MISC-1 | Web | AI developer roadmap 2026[cite:166] | Provided context on skill sets involved in the project. | PRO |
| MISC-2 | Web | System design guide 2026[cite:158] | Supported general systems thinking and separation of concerns. | PRO, XSYS |
