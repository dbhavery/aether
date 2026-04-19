# 07 — Tutorial and Help System

Aether's in-product learning and help system. Distinct from onboarding (first-run setup) and from the showcase (marketing/narrative surface).

---

## Philosophy

### Core rule
**Tutorials exist — but not as one long passive tour.**

- **No giant intro tour.** Users are not walked through every feature on first launch.
- **Learning by doing.** Tutorials appear when the user first touches a feature, in context.
- **Modular, short, replayable.** Each tutorial is focused on one thing and takes under 2 minutes.
- **Always skippable.** Every tutorial has a clear "skip" and "don't show me this again."

### Distinct from onboarding
- Onboarding = first-run setup (3–7 steps, assistant identity + permissions + tier).
- Tutorials = in-product feature learning (modular, triggered by use).

### Distinct from the showcase
- Showcase = narrative / marketing surface (cinematic demo chapters).
- Tutorials = practical how-to, triggered by interaction.

---

## The four tutorial layers

### Layer 1 — Setup wizard (onboarding)
See [06_onboarding_spec.md](06_onboarding_spec.md). The setup wizard handles core identity, permissions, and performance-tier choices. Not repeated here.

### Layer 2 — First-run checklist
Appears after onboarding completes. A short guided checklist with **3–5 actions** the user can try to activate the product.

Candidate checklist items:
- **Talk to your assistant** — opens chat, suggested first message
- **Try voice mode** — mic test, say hello
- **Meet your avatar** — open avatar mode briefly
- **Customize your assistant** — link to persona settings
- **Explore permissions** — one-click tour of the trust center

Completion is optional; skippable. Progress persisted.

### Layer 3 — Inline walkthroughs
**Triggered when the user first uses a major feature.** Short, contextual, in-place.

Examples:
- First time the user opens memory settings → inline walkthrough of memory editing
- First time the user grants a browser permission → walkthrough of approval flow
- First time the user switches to avatar mode → brief avatar behavior explainer
- First time the user opens the trust center → tour of logs, permissions, disclosures

Each walkthrough:
- 2–6 steps max
- Lives inline (tooltips + highlights), not in a modal over everything
- "Got it" dismisses; "Show me again" available from help menu

### Layer 4 — Reference / help center
The always-available searchable help surface.

Contents:
- Feature explainers (mirroring onboarding info-popups, expanded)
- FAQ / common questions
- Permission reference
- Memory reference
- Trust / privacy docs
- Troubleshooting
- Short media (images / short videos for complex flows)

Accessible from:
- Settings → Help
- Global help icon (if surface permits)
- Search field

---

## Info-explainer pattern (the (i) icon)

Every meaningful control across the product has an **(i) info icon**. Clicking / hovering shows a small popup with:

1. **Plain-language definition**
2. **Why this matters**
3. **Recommended default**
4. **Example use case**
5. **Impact summary** — privacy / performance / trust / cost where relevant
6. **"Learn more"** link to reference / help center

This is mandatory, not optional. Defined in [06_onboarding_spec.md](06_onboarding_spec.md#info-explainer-on-every-option) and enforced by design review.

---

## Tutorial content principles

- **Plain language.** No unexplained jargon.
- **Concrete examples.** Show, don't just describe.
- **Skippable always.** No forced tutorials.
- **Progressive.** Basic tutorial first; advanced linked separately.
- **Replayable.** Anything a user dismissed can be re-shown from Settings → Help.
- **Respectful.** No "are you sure you want to skip?" nags.

---

## When NOT to show a tutorial

- When the user has skipped similar ones repeatedly (respect the signal).
- When the user is clearly a power user (heuristic: has used advanced settings).
- When the user has explicitly enabled "don't show me tutorials" in settings.
- When the user is re-opening a feature they've already used.

---

## Search and discoverability

- Help center has full-text search.
- Every info-explainer entry is searchable.
- Common queries route to the right section ("how do I delete memory?" → memory reference).
- Help system does not require network connection for core content.

---

## Content types

| Type | Use case | Format |
|------|----------|--------|
| Info-explainer popup | Per-control, always available | 5-line plain text |
| Inline walkthrough | First use of a major feature | 2–6 tooltips with highlights |
| Reference article | Help center deep-dive | Markdown + optional short media |
| Short video | Complex multi-step flows | 15–45 seconds, captioned, skippable |
| FAQ entry | Common question | Q + short A + "Learn more" link |

---

## Anti-patterns (explicitly forbidden)

- **No giant intro tour** that walks through the whole app on first launch.
- **No modal tutorials** that block the UI until dismissed.
- **No auto-play videos** for help content.
- **No pop-under tutorials** that steal focus.
- **No "are you sure you want to skip" nags.**
- **No gated features** behind tutorial completion.
- **No technical jargon** in default tutorial copy (advanced tutorials may use it).

---

## OSS Preview vs Pro differences

| Element | OSS Preview | Pro |
|---------|-------------|-----|
| First-run checklist | 3 items | 5 items |
| Inline walkthroughs | Core features only (chat, avatar, permissions) | All major features |
| Reference center | Basic | Full + troubleshooting + sync |
| Short videos | Optional / community-contributed | Polished, produced |
| Search | Basic full-text | Full-text + suggestions |

---

## Success criteria

- Users activate the product without reading docs.
- Users never feel "lost" when first touching a major feature.
- Users can find answers in the help center in under 30 seconds.
- Skip rates are high (good — means inline UX is self-explanatory) but help center usage is also non-zero (good — means it's findable when needed).
- No feature is discoverable **only** through the tutorial system — everything is reachable through the UI itself.

---

## Cross-references
- Onboarding: [06_onboarding_spec.md](06_onboarding_spec.md)
- UX principles: [05_ux_principles.md](05_ux_principles.md)
- Showcase: [05_ux_principles.md](05_ux_principles.md#showcase-layer)
- Trust center: [13_trust_security_redteam.md](13_trust_security_redteam.md)
