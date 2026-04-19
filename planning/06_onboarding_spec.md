# 06 — Onboarding Specification

Onboarding is a top-priority product surface — it is where trust is formed and the premium bar is first established.

---

## Onboarding philosophy

### Primary rule
**Onboarding must be as non-technical as possible.** Users should feel like they are setting up their assistant, not configuring an engineering system.

### Interaction model
- Guided, friendly, warm
- Progressive disclosure — advanced hidden by default
- Recommended presets cover 80%+ of users
- Advanced controls available but not thrust forward
- Available and attractive to **all technological skill levels**

### Length target
- **3–7 core steps**, not 15+
- Each step feels like a question the assistant asks, not a form
- Skippable where appropriate; replayable later

---

## Mandatory rules

### Info-explainer on every option
**Every meaningful option MUST include an (i) info explanation** — link or pop-up.

Each explainer contains:
1. **Plain-language definition** — what this setting is
2. **Why this matters** — what it affects
3. **Recommended default** — which option most users pick
4. **Example use case** — concrete scenario
5. **Impact summary** — privacy / performance / trust / cost implications where relevant

### Preset-first design
- Every configuration surface ships with a "Recommended" preset selected.
- Users can complete onboarding without touching a single advanced control.
- Advanced controls are behind explicit expansion ("Customize", "Advanced").

### No dead ends
- Every step has a "recommended default" path.
- Every step has an "I'll decide later" or "skip" path.
- No step blocks the user with a required decision they don't have context to make.

---

## Core onboarding flow (target structure)

### Step 1 — Welcome & disclosure
- What Aether is (one sentence)
- What it does and doesn't do (plain-language)
- Terms & conditions acceptance (with short "plain English" summary + full text)
- AI disclosure (clearly stated — "You are interacting with AI-generated responses and an AI-generated avatar")
- Privacy disclosure (what data stays local, what goes to cloud, per the doctrine)

### Step 2 — Assistant identity
- Choose a name (default offered)
- Choose a style/persona preset (Warm / Professional / Playful / Custom)
- Optionally: choose voice
- Optionally: choose avatar appearance preset
- Preview appears inline

### Step 3 — Interaction mode preferences
- Default mode (Text / Text+Voice / Full Avatar)
- Microphone on/off
- Voice output on/off
- Avatar visibility on/off
- "You can change any of these later" reassurance

### Step 4 — Hardware & performance
- **Auto-detected tier shown** (Lite / Balanced / Full)
- One-sentence explanation of what the tier means
- "Recommended for your system" badge
- Advanced override available but collapsed
- Storage impact preview (how much this will install)

### Step 5 — Permissions & autonomy
- **Autonomy preset selection** (Observer / Assistant / Operator / Power User / Custom)
- Plain-language summary:
  - "Aether will be able to: [list]"
  - "Aether will always ask before: [list]"
  - "Aether will never: [list]"
- Resource pickers (approved folders, approved domains) — optional, defaults safe
- Advanced capability matrix available but collapsed

### Step 6 — Memory preferences
- Memory retention default (Session only / This device / Durable)
- "What would you like your assistant to remember?" — simple categories
- Memory controls surfaced (edit, export, delete — preview)
- Advanced controls hidden

### Step 7 — Ready / first-run checklist
- "You're ready." — summary of choices
- Show first-run checklist (3–5 actions the user can try)
- Optionally: start the showcase / demo tour
- All advanced settings available from this point in Settings

---

## Auto-detection during onboarding

### Hardware assessment (Step 4)
Runs automatically, silently, in the background during earlier steps so Step 4 already shows the recommended tier.

Detects:
- VRAM (detected + class: low / mid / high)
- Total storage capacity + free space
- CPU class
- Microphone availability
- Camera availability
- Network quality

Outputs:
- Recommended performance tier
- Recommended default model pack size
- Recommended asset pack size
- Any warnings (insufficient VRAM for Full tier, etc.)

### User override
All auto-detected values can be manually overridden in Step 4 advanced controls. A recommendation is never silently applied if the user selects otherwise.

---

## Trust-building elements embedded in onboarding

- **AI disclosure up front** — not buried
- **Permissions explained in plain language** — "Aether will be able to..."
- **Data locality disclosed** — what stays local, what goes to cloud
- **Every default is conservative** — least autonomy, least data, least risk
- **Review screen before finishing** — user sees all choices before committing
- **Everything is reversible** — emphasized repeatedly

---

## Showcase integration

- Onboarding's final step **offers** the showcase tour — does not force it.
- If user starts the showcase, onboarding marks itself complete.
- If user skips, they can start the showcase anytime from Settings → Help.
- Showcase lives in [05_ux_principles.md](05_ux_principles.md#showcase-layer).

---

## Replayability and correction

- Onboarding is **replayable** from Settings → "Re-run setup".
- Individual steps can be revisited (e.g., "re-choose persona", "re-run hardware detection").
- Every setting modified during onboarding is surfaced in Settings under the same name.

---

## Anti-patterns (explicitly forbidden)

- **No wall-of-text disclosures** — always plain-language summary + "Read full" expansion.
- **No unexplained toggles** — every switch has an explainer.
- **No technical jargon in default copy** — "VRAM," "LLM," "token," "embedding" do not appear in main flow (but are in advanced section).
- **No gated blocking steps** — user can always skip to "I'll decide later."
- **No dark patterns** — no pre-checked aggressive permissions, no buried "agree to everything" bundling.
- **No forced account creation** for the free OSS Preview.

---

## OSS Preview vs Pro onboarding differences

| Element | OSS Preview | Pro |
|---------|-------------|-----|
| Account creation | Not required | May require account for sync / licensing |
| Permissions presets | Simplified — Observer / Assistant default | Full 5-preset ladder |
| Performance tiers | Lite / Balanced + optional Enhanced | Full Lite / Balanced / Full ladder |
| Showcase depth | Teaser of future features shown as "coming to Pro" | Full showcase of flagship capabilities |
| Memory controls | Basic (session / durable) | Full granularity |
| Sync setup | N/A | Optional sync step for mobile companion |

---

## Success criteria

A user completing onboarding should:
1. Understand what Aether is.
2. Have their assistant configured (named, styled, tier-matched).
3. Understand what Aether will and won't do.
4. Trust that they can change anything later.
5. Feel the product is premium, thoughtful, trustworthy.
6. Be ready to start using it — or to watch the showcase.

Failure modes to avoid:
- Abandonment mid-flow because of jargon
- Completion with default permissions the user doesn't understand
- User unsure what just happened
- User feels the product is "AI-y" or "gimmicky"

---

## Cross-references
- UX principles: [05_ux_principles.md](05_ux_principles.md)
- Tutorial / help: [07_tutorial_help_system.md](07_tutorial_help_system.md)
- Performance tiers: [14_performance_tiers_vram.md](14_performance_tiers_vram.md)
- Permissions: [12_permissions_autonomy.md](12_permissions_autonomy.md)
- Trust / red-team: [13_trust_security_redteam.md](13_trust_security_redteam.md)
