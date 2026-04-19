# L7 — Trust UX & Onboarding

**Status:** draft
**Last updated:** 2026-04-18
**Layer type:** must-own (doctrine §1.8)
**Depends on:** L5 (policy engine — disclosures, approval UI), L2 (memory kernel — memory-review UI), L4 (model router — routing-decision audit UI), L6 (persona compiler — onboarding → persona pipeline), L1 (interaction timing — first-run handoff, ack pool reference).
**Blocked by:** custom design-system foundation; hardware auto-detect probe; policy engine stub for disclosure copy.

---

## Purpose

Own the user-visible surface that establishes and maintains trust. Onboarding wizard, disclosures, permission UI, memory-review UI, trust center, routing-decision audit UI, guest-mode entry, consent patterns, info-explainer component, first-run checklist, and inline walkthrough plumbing. This is the layer the user sees first, returns to when anxious, and uses to revoke consent. It is the single surface where the doctrine's "user experience outranks implementation convenience" clause is most visibly enforced.

## Why must-own

Trust UX cannot be outsourced to a generic component library, a SaaS admin panel, or a borrowed settings framework. The product's "premium, careful, legible" posture lives in this surface — the copy, the info-explainer on every option, the "Aether will / will always ask / will never" phrasing, the memory-review affordances, the action-history replay, the guest-mode entry. Any generic drop-in component ("we'll just use shadcn permissions") caps the ceiling here because it was designed for SaaS dashboards, not for a companion product. Doctrine rule §1.1 applies hardest here: no close-enough SaaS in the layer that defines the user relationship.

## Boundaries

**Owns:**
- Onboarding wizard (7 steps, info-explainer on every option, progressive disclosure, preset-first).
- Disclosure flow (AI nature, data locality, model use, memory semantics) with plain-English summary + full-text expand.
- Permission UI — approval prompts, capability matrix view, resource scope pickers, "Aether will / will always ask / will never" surface.
- Memory-review UI — inspect / edit / delete / export, memory-write notifications, confidence/provenance display.
- Trust center — permissions summary, recent actions, full action history (searchable, replayable), model/source disclosures, safety docs.
- Routing-decision audit UI — per-turn "which model answered, why" surface for the deliberative path (Pro+).
- Guest-mode entry — Aether Guest landing surface, rate-limit copy, "upgrade to local" path.
- First-run checklist + inline walkthrough plumbing (triggers, dismissal, re-show).
- Info-explainer component (the (i) icon) — the single reusable primitive.
- Consent-revocation flow — uniform across memory, permissions, integrations.
- Showcase hand-off from onboarding (does not own showcase content — that's UX/design work).

**Does not own:**
- The underlying capability model or policy evaluation (L5).
- Memory storage, confidence, or decay (L2).
- Persona compilation logic (L6 — L7 only surfaces the choices and hands them off).
- Avatar rendering (Presence engine).
- Model routing logic (L4 — L7 surfaces the decision, does not make it).
- Help-center article content authoring (UX/design, though L7 owns the container).
- Design-system tokens (cross-cutting; L7 consumes, does not author).

## Dependencies

- **L5 policy engine** — L7 renders approval prompts, so needs a stable event contract (`approval_required`, `approval_granted`, `approval_denied`, risk class, scope, duration).
- **L2 memory kernel** — L7 needs `memory_write`, `memory_updated`, `memory_confidence_changed` events; needs edit/delete/export RPCs.
- **L4 model router** — L7 needs `route_decision` events with `model`, `reason`, `latency`, `cost` fields for the audit UI.
- **L6 persona compiler** — onboarding step 2 feeds persona-compiler input; L7 must respect the compiler's schema.
- **Hardware probe** — L7's onboarding step 4 needs tier-recommendation output before step 4 renders.
- **Design-system foundation** — L7 cannot ship until the tokenized component set exists (neumorphic monochrome, dark-first).

## Borrowable vs custom

| Piece | Decision |
|---|---|
| Onboarding wizard shell | **Custom.** The copy, step structure, info-explainer, and preset model are doctrine surfaces. Generic wizard libraries cap the ceiling. |
| Info-explainer popup component | **Custom.** Reused 100+ times across product; has to match design-system exactly. |
| Disclosure copy | **Custom.** Plain-English summaries are authored, not templated. |
| Permission approval prompt | **Custom.** "Aether will / will always ask / will never" phrasing is doctrinal. |
| Trust center shell | **Custom.** Action-history replay + memory-review + model disclosure is not a commodity pattern. |
| Form primitives (input, select, toggle) | **Borrow** — Radix or Headless UI behind design-system wrapper. |
| Markdown renderer (help center) | **Borrow** — isolated behind a component; content is custom. |
| Search index (help center) | **Borrow** — lunr/FlexSearch; swap-able. |
| Guest-mode Worker | **Borrow+wrap** — Cloudflare Worker + Groq free tier is tactical; copy and rate-limit UX are custom. |

## Key risks

1. **Info-explainer fatigue.** If every control has a verbose popup, users tune them out. Mitigation: 5-line cap, consistent structure, plain language, "Learn more" link for depth.
2. **Approval-prompt overload.** Too many interruptions and users auto-click "Allow." Mitigation: risk-class-driven — only medium+ asks; low-risk logged silently; session grants with visible revocation.
3. **Dark-pattern drift.** Pressure to pre-check consent boxes or bundle permissions. Mitigation: anti-pattern list in 06/13 is enforced in design review; every release includes a consent-pattern audit.
4. **Memory-review surface cost.** If the memory UI is slow or clumsy, users stop using it and trust decays silently. Mitigation: memory-review is a first-class surface, not a settings sub-page; perf budget <100 ms to list.
5. **Guest-mode trust gap.** Users may think Guest persists data. Mitigation: explicit "Guest does not remember you; install to keep this conversation" copy on every Guest turn.
6. **Trust center becoming a log dump.** If action history reads as raw JSON, it fails the doctrine. Mitigation: action entries are rendered as plain-English sentences with expandable detail; replay is a user feature, not a developer feature.
7. **Locked feedback conflict.** Don's `feedback_css_default_for_ui.md` says pywebview; session locks Tauri. Tauri is a webview shell so the spirit ("HTML/CSS/JS for UI, never Tkinter/Qt") is preserved. Flag in Open decisions.

## Sequencing

1. **P0 (OSS Preview Phase 1–3)** — 7-step onboarding wizard (may use v1.0 8-screen concrete spec as reference, condensed to 7), info-explainer component, disclosures, simplified permission presets (Observer/Assistant), light trust center (permissions + recent actions + memory toggle + AI disclosure), first-run checklist (3 items), inline walkthroughs for chat/avatar/permissions.
2. **P1 (Pro Phase 0)** — design-system foundation, component library tokenization, onboarding shell ported to Tauri + React, accessibility baseline (keyboard, reduced-motion, screen-reader).
3. **P2 (Pro Phase 1)** — full 5-preset permission ladder UI, resource-scope pickers, approval prompt component wired to policy engine events, info-explainer populated across settings.
4. **P3 (Pro Phase 2)** — full trust center (searchable action history, replay, memory-review UI with edit/delete/export, model-disclosure panel), routing-decision audit UI stub, info-explainer rendered everywhere.
5. **P4 (Pro Phase 3–4)** — routing-decision audit UI full, consent-revocation flow uniform across surfaces, red-team-driven copy review, trust center 1-click-from-every-mode.
6. **P5 (Pro Phase 5–6)** — Isabelle-private trust surfaces (wider autonomy visualization, cross-project memory review), showcase chapter hand-off maturation, accessibility re-audit against shipped flows.

**Guest-mode & 8-screen wizard**: the v1.0 docs (Aether Guest endpoint concept; 8-screen concrete wizard) are a content source for P0. Agent D owns v1.0 content port into the component copy; L7 owns the shell and hands copy slots to Agent D.

## Acceptance criteria

- 7-step onboarding completable by a non-technical user in <5 minutes with default presets, zero required text entry beyond an optional assistant name.
- Every interactive control in the product has an info-explainer; automated lint/test fails the build if a new control lacks one.
- Permissions UI renders "Aether will / will always ask / will never" lists generated from the capability model (no hand-maintained copy drift).
- Trust center reachable in ≤1 click from every mode.
- Every autonomous action shows up in action history within 500 ms of completion, rendered as plain English with expandable raw detail.
- Memory-review UI list renders <100 ms for 10 000 memories.
- Consent revocation is immediate and visible; revoking a memory permission wipes matching memories within 1 s and surfaces confirmation.
- Guest-mode entry shows rate-limit + non-persistence copy on every turn; "install to keep this" CTA always visible.
- Onboarding replayable from Settings with no state loss.
- Reduced-motion, keyboard-only, and screen-reader passes on all onboarding + trust-center surfaces.

## Open decisions for executing agent

- Whether to ship the v1.0 8-screen wizard verbatim as P0 content, or condense to the 06_onboarding_spec.md 7-step shape. (Agent D coordination.)
- Guest-mode infrastructure: Cloudflare Worker + Groq free tier (v1.0 concept) vs. a different provider vs. defer until post-OSS-Preview.
- Whether routing-decision audit UI ships at Pro Phase 2 (alongside trust center v1) or slips to Phase 4 (alongside tool autonomy audits).
- pywebview (OSS Preview tactical) vs. Tauri (Pro) — L7 shell must be identical from the user's perspective; confirm shared React component tree works in both. Flag: conflicts with locked `feedback_css_default_for_ui.md` if OSS Preview moves to Tauri too early.
- Help-center search engine choice (lunr vs FlexSearch vs custom) — low-stakes but pick early.

## Reference specs

- `file:///C:/Users/dbhav/Projects/aether-planning/05_ux_principles.md`
- `file:///C:/Users/dbhav/Projects/aether-planning/06_onboarding_spec.md`
- `file:///C:/Users/dbhav/Projects/aether-planning/07_tutorial_help_system.md`
- `file:///C:/Users/dbhav/Projects/aether-planning/13_trust_security_redteam.md`
- `file:///C:/Users/dbhav/Projects/aether-planning/12_permissions_autonomy.md`
- `file:///C:/Users/dbhav/Projects/aether-planning/01_product_doctrine.md`
- v1.0 reference (to be ported by Agent D): 8-screen onboarding wizard, Aether Guest endpoint concept.
