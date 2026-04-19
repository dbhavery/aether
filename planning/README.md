# Aether Planning — Reference Folder

Source of truth for the Aether product family planning: **OSS Preview**, **Aether Pro** flagship, and **Isabelle / Isabelle_Kunstig** private branch.

This folder replaces/supersedes prior scattered planning:
- `file:///C:/Users/dbhav/Projects/aether_oss_preview_roadmap.md`
- `file:///C:/Users/dbhav/Projects/aether_pro_roadmap.md`
- `file:///C:/Users/dbhav/Projects/aether_cross_systems_spec.md`
- `file:///C:/Users/dbhav/Projects/aether_sources_matrix.md`
- `file:///C:/Users/dbhav/Projects/aether/docs/` (old repo planning)
- `file:///C:/Users/dbhav/Projects/Isabelle_Kunstig/docs/` (legacy)

Old files remain in place until the comparison pass migrates or discards them.

## Hard rule (applied throughout)

- **OSS Preview**: open-source / available-now components acceptable — it is a launch-fast wedge.
- **Aether Pro and Isabelle**: we write our own software from here on. Borrowed primitives are permitted **only** where they do not cap the product ceiling or become the moat. Every "must-own" layer in `01_product_doctrine.md` is custom-built.

## Index

### Meta / anchor
- [MASTER_OUTLINE_TREE.md](MASTER_OUTLINE_TREE.md) — Full hierarchical planning tree (14 sections)
- [NUMBERED_SPEC.md](NUMBERED_SPEC.md) — Formal 1.0–18.0 numbered specification
- [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) — Unresolved decisions

### Doctrine + family
- [01_product_doctrine.md](01_product_doctrine.md) — No-close-enough-SaaS rule, bare-metal boundary, companion-grade standard
- [02_product_family.md](02_product_family.md) — Three-product split
- [03_vision_and_thesis.md](03_vision_and_thesis.md) — Core vision, experience thesis, strategic thesis

### User-facing product
- [04_user_modes.md](04_user_modes.md) — Chat, sandbox/settings, avatar, voice-only
- [05_ux_principles.md](05_ux_principles.md) — UX goals, design language, showcase
- [06_onboarding_spec.md](06_onboarding_spec.md) — Non-technical onboarding, progressive disclosure, info-explainers
- [07_tutorial_help_system.md](07_tutorial_help_system.md) — Modular tutorials, inline walkthroughs

### System architecture
- [08_system_architecture.md](08_system_architecture.md) — Six engines, event bus, platform roles
- [09_realtime_interaction.md](09_realtime_interaction.md) — Two-speed cognition, latency, acknowledgment pool
- [10_memory_architecture.md](10_memory_architecture.md) — Memory layers, governance, quality
- [11_avatar_presence.md](11_avatar_presence.md) — Avatar layers, presence controller, rendering

### Policy + trust
- [12_permissions_autonomy.md](12_permissions_autonomy.md) — Capability model, risk classes, autonomy presets
- [13_trust_security_redteam.md](13_trust_security_redteam.md) — Red-team readiness, trust center

### Platform + ops
- [14_performance_tiers_vram.md](14_performance_tiers_vram.md) — Lite/Balanced/Full, 50% VRAM rule
- [15_updates_releases.md](15_updates_releases.md) — Update policy, release channels
- [16_tech_stack.md](16_tech_stack.md) — Languages, frameworks, libraries, moat layers

### Concrete specs (ported from v1.0)
- [17_persona_pack_schema.md](17_persona_pack_schema.md) — Persona pack folder structure, YAML schemas, archetype catalog, licensing
- [18_model_router_spec.md](18_model_router_spec.md) — Tier abstraction (fast/main/heavy), Gemma 4 routing, fallback chains, BYOK

### Roadmaps (per product)
- [roadmaps/aether_oss_preview.md](roadmaps/aether_oss_preview.md) — Free OSS preview spec + phases
- [roadmaps/aether_pro.md](roadmaps/aether_pro.md) — Public flagship spec + phases
- [roadmaps/isabelle_private.md](roadmaps/isabelle_private.md) — Isabelle / Isabelle_Kunstig private branch spec

### Sources
- [sources_matrix.md](sources_matrix.md) — External sources informing these specs

## Status

- **Written**: 2026-04-18
- **Phase**: Active planning; pre-execution
- **Next**: After batch writes complete → comparison pass against old project files → repo structure decisions
