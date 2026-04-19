# 05 — UX Principles

The governing UX principles for Aether. These apply to both OSS Preview and Pro; the bar is the same.

---

## UX goals

- **State-of-the-art UI and showcase quality** — not generic SaaS dashboard, not dev tool aesthetic.
- **Attractive and accessible to all technology skill levels** — non-technical users are never blocked; power users are never limited.
- **Emotionally warm but trustworthy** — the assistant feels present and cared-for without feeling manipulative.
- **Premium and cinematic where appropriate** — avatar mode, showcase surfaces, identity setup.
- **Calm and precise where appropriate** — settings, permissions, trust center.
- **AI-native companion product** — not a dashboard, not a dev console.

---

## Design language targets

| Attribute | Direction |
|-----------|-----------|
| Premium | Yes — quality implied in every detail |
| AI-native | Conversational layouts, modular surfaces, personalization |
| Socially alive | Avatar surfaces feel present even when idle |
| Cinematic | Avatar mode, showcase, identity — not chat or settings |
| Clear | Settings and permissions are legible to non-technical users |
| Trust-building | Permissions, logs, disclosures feel reassuring, not scary |
| Distinctive | Own design system, not template styling |
| Restrained | No noisy "AI aesthetic" (neon, cyberpunk, indigo-purple slop) |
| Warm | Type, motion, color feel human-scale |

**Don's established aesthetic preference:** deep 3D neumorphic monochrome.

---

## Mode-specific tone

- **Chat**: calm, precise, fast. Minimal ornamentation.
- **Settings / Sandbox**: calm, legible, controlled. Every control explained.
- **Avatar mode**: cinematic, emotionally rich, visually considered.
- **Permissions / trust center**: transparent, reassuring, concrete.
- **Onboarding**: warm, guided, forgiving of skill level.
- **Showcase / demo surfaces**: narrative, choreographed, confidence-building.

---

## Showcase layer

Aether ships with a **dedicated showcase layer** — not just a core app UI. This is distinct from onboarding: it is an in-product surface for activation, trust-building, and marketing storytelling.

### Purpose
- Market the vision
- Onboard users emotionally
- Demonstrate capabilities with strong first impressions
- Build trust through visible product discipline

### Structure
Modular, chapter-based, "choose your path" where appropriate. Not a single long auto-play tour.

### Candidate chapters
1. **Meet your assistant** — persona, voice, avatar first impression
2. **Choose your style** — persona / appearance customization preview
3. **See how permissions work** — trust and autonomy demonstration
4. **Watch a task happen** — end-to-end scripted demo
5. **Explore future modes** — teaser of upcoming capabilities (Pro roadmap features shown as future, not fake)

### Placement
- Available from onboarding's welcome screen (optional)
- Always re-accessible from settings or help menu
- Short, skippable, replayable

---

## First-run and activation principles

- **Progressive disclosure** — advanced options hidden by default, available on expansion.
- **Preset-first** — most users complete setup via recommended presets.
- **Learning by doing** — not passive tours. Interactive checklists and inline walkthroughs.
- **No dead ends** — every step has a "recommended default" and an "I'll decide later" path.
- **Skippable + replayable** — everything can be skipped and replayed later.

---

## Information architecture rules

- **Every meaningful option has an (i) info explainer** — plain language, recommended default, example, impact (privacy / performance / trust).
- **Permissions are always visible** — never buried three menus deep.
- **Action history is always reviewable** — what did the assistant just do?
- **Memory is always inspectable** — what does the assistant remember about me?
- **Trust center is one click away from every mode**.

---

## Motion and animation

- **Motion is used for trust and clarity, not decoration.**
- State transitions animate to reinforce what the system is doing (listening → thinking → speaking).
- Avatar motion obeys the presence controller (see `11_avatar_presence.md`).
- Reduced-motion accessibility respected.

---

## Component system

Aether uses a **custom design system**, not template UI. Tokenized components for:
- Onboarding steps
- Settings rows
- Permission prompts
- Trust center views
- Cards, modals, dialogs
- Avatar containers and state indicators
- Chat message bubbles and status lines
- Showcase narrative segments

The component library is built once and used across OSS Preview and Pro. Isabelle inherits it.

---

## What the UI is NOT

- **Not a ChatGPT clone** — chat is one surface, not the whole product.
- **Not a SaaS dashboard** — no endless sidebar, no "workspace" metaphor.
- **Not a dev console** — no raw logs, no JSON dumps, no unexplained toggles.
- **Not cyberpunk / neon AI aesthetic** — no glowing gradients, no indigo-purple slop.
- **Not enterprise-blank** — warmth and identity matter.
- **Not over-animated** — motion serves comprehension, not spectacle.

---

## Accessibility baseline

- Keyboard navigable throughout.
- Reduced-motion respected.
- High-contrast mode supported.
- Screen-reader-meaningful labels on all interactive surfaces.
- Voice-only operation is a valid full use path (see [04_user_modes.md](04_user_modes.md)).
- Works without avatar rendering for users on low-GPU systems or who prefer text.

---

## Cross-references
- Modes: [04_user_modes.md](04_user_modes.md)
- Onboarding: [06_onboarding_spec.md](06_onboarding_spec.md)
- Tutorials: [07_tutorial_help_system.md](07_tutorial_help_system.md)
- Avatar: [11_avatar_presence.md](11_avatar_presence.md)
- Trust center: [13_trust_security_redteam.md](13_trust_security_redteam.md)
