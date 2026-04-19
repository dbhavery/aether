# Aether Cross-System Architecture and Standards

## Product family doctrine

Across the Aether family, “close enough” commodity SaaS behavior is unacceptable in the layers that define the user relationship, trust model, autonomy model, and perceived assistant quality. External libraries, engines, and services may be used as accelerators, but core differentiators must remain custom-controlled enough to preserve the intended product ceiling and moat.[cite:193][cite:195][cite:200]

The family-wide rule is simple: borrow primitives where they do not lower the quality ceiling; own the layers that determine the assistant relationship. Current build-vs-buy guidance strongly supports building where differentiation lives and buying where the function is standardized infrastructure rather than product identity.[cite:193][cite:198]

## Shared architecture principles

### User experience priority

User experience is the top priority cross-system constraint. Onboarding, permissions, memory, presence, updates, and performance tuning should all be designed first around the user’s perceived trust, continuity, clarity, and responsiveness rather than technical convenience.[cite:189][cite:194][cite:196]

### Local-first principle

The family should remain local-first for identity, fast acknowledgments, major settings, permission state, and core user continuity wherever practical. Local-first design remains strongly recommended when responsiveness, offline resilience, and user control over data are important to product value.[cite:206][cite:82][cite:84]

### Tier-aware principle

All shared systems must support hardware-aware performance adaptation. This includes onboarding defaults, model packs, cache rules, avatar fidelity, and tool availability, because local AI experiences vary widely by consumer hardware class.[cite:103][cite:109][cite:136]

### Trust-by-design principle

Permissions, risk classes, audits, logs, disclosures, and recovery pathways should be embedded into the system architecture, not bolted on at the end. AI red-team guidance in 2026 continues to emphasize evidence-backed safety, scenario testing, and governance-aware operations.[cite:132][cite:135][cite:138]

## Shared recommended stack

### UI and product surfaces

**Recommended:** React + TypeScript for desktop-facing product surfaces and early shared UI logic. This remains a practical choice for large, stateful interface systems, especially where onboarding, settings, trust surfaces, and complex modal flows are important.[cite:202][cite:206]

### Desktop shell

**Recommended:** Tauri as the default desktop shell across early Aether products where package size, performance, and Rust alignment matter. Tauri continues to compare favorably with Electron for lighter-weight desktop distribution.[cite:102][cite:105][cite:111]

### Core runtime

**Recommended:** Rust for policy evaluation, local runtime coordination, event routing, and other performance-sensitive services. Rust’s fit for safe concurrent systems makes it especially suitable for AI runtime coordination and desktop-native helpers.[cite:207][cite:212]

### ML and experimentation

**Recommended:** Python for offline processing, experimentation, memory pipelines, model evaluations, and early integrations that will later be hardened or ported into more controlled runtime layers.[cite:54][cite:58]

### Mobile strategy

**Recommended public-first path:** React Native for faster early mobile reach.[cite:203]

**Recommended performance-first path:** SwiftUI and Jetpack Compose/Kotlin for later deeper native performance, media, and device integration.[cite:203][cite:205][cite:213]

### Local data and sync

**Recommended direction:** structured local database plus explicit sync layer, rather than cloud-only state. Current offline-first guidance points to local DB plus sync engine and conflict handling as the coherent pattern for resilient apps.[cite:206][cite:82]

### Observability and governance

**Recommended:** production observability stack for traces, latency, cost, routing, tool calls, approvals, denials, and policy violations. Agentic AI stack guidance now treats observability and governance as mandatory operational layers rather than optional extras.[cite:207][cite:210][cite:212]

## Onboarding system standard

### Core requirements

Onboarding must be non-technical, preset-based, progressive, and accessible to users across all skill levels. It must frame setup as configuring an assistant relationship rather than a technical stack.[cite:127][cite:129][cite:131]

### Mandatory info pattern

Every major setting and choice must include an inline info explainer that covers meaning, recommendation, example usage, and impact on privacy, trust, or performance where relevant.[cite:127][cite:131]

### Hardware recommendation

Onboarding must perform hardware assessment and recommend a performance profile automatically, because mainstream users should not be expected to reason about VRAM budgets or local inference limits directly.[cite:127][cite:136]

## Permission and autonomy standard

### Shared model

Permissions must be capability-based, least-privilege, resource-scoped, approval-aware, and time-bounded where appropriate. A single broad “agent access” model is not acceptable for a high-trust product family.[cite:119][cite:123][cite:126]

### Shared capability domains

The shared domains should include files, browser, email, memory/data, system tools, and integrations. Each domain should expose both simple presets and advanced controls.[cite:124][cite:126]

### Shared risk model

All products should classify actions into low, medium, high, and critical risk tiers, with increasingly strict approval and logging requirements as risk rises. This aligns with current governance guidance for agentic systems and irreversible actions.[cite:121][cite:126]

## Trust and red-team standard

### Trust center

All family products should include some form of trust center or equivalent surface showing permissions, recent actions, safety boundaries, and relevant control state. Visibility is central to user trust, especially in systems with partial autonomy.[cite:135][cite:141]

### Red-team readiness

Cross-system testing should cover prompt injection, memory poisoning, tool misuse, data leakage, policy bypass, and audit completeness. Scenario-driven testing and replayable action evidence are now standard expectations for serious AI products.[cite:132][cite:135][cite:138]

## Performance tier standard

### Shared tiers

The product family should use at least Lite, Balanced, and Full profiles with common semantic meaning across products. These profiles should influence local model size, cache footprint, avatar quality, and cloud escalation strategy.[cite:103][cite:136]

### VRAM standard

For the full installed flagship product, approximately 50% of available VRAM should be treated as the default local budget target. Public VRAM planning guidance continues to recommend leaving significant headroom rather than planning to max out the device.[cite:133][cite:136][cite:139]

## Update and release standard

### Update philosophy

Updates should be optional or recommended by default, with forced updates reserved for genuinely critical cases involving safety, trust, compatibility, or product integrity. Current update guidance supports this two-mode approach across desktop and mobile ecosystems.[cite:142][cite:149]

### Release channels

The family should support stable, beta, and experimental release tracks so that innovation and safety can coexist without collapsing into one unstable public surface.[cite:149]

## Isabelle inheritance rule

Isabelle should inherit the same cross-system architecture for trust, permissions, performance, onboarding, and observability rather than reinventing those foundations independently. Private customization should occur in persona, workflows, memory tuning, and privileged capabilities, not by discarding the shared platform safety model.[cite:156][cite:176]

## Success profile

The cross-system architecture is successful when every Aether-family product feels coherent, premium, and understandable; when users can trust what the assistant is doing; when performance is automatically adapted to the device; when onboarding lowers the complexity barrier; and when the platform’s custom-controlled core layers preserve a path toward the highest-tier assistant/companion experience rather than collapsing into commodity wrapper behavior.[cite:188][cite:194][cite:196]
