# 02 — Product Structure

> **REWRITTEN 2026-05-18.** Doctrine §6 collapsed the prior three-product structure (OSS Preview / Pro / Isabelle) into **one product (Companion) + one private overlay (Isabelle)**. The OSS Preview was retired; Pro was renamed to Companion; the umbrella name "Aether" is preserved as internal codename only. Prior version of this file is in git history.

---

## One product: **Companion**

**Public name:** Companion. **Internal codename / repo / database / Tauri identifier / Cargo workspace:** `aether` (preserved — see doctrine naming-convention block).

Companion is the multimodal AI assistant product centered on:
- conversational interaction (text, voice, avatar — interoperable, not separate "modes")
- local-first responsiveness
- photoreal full-body characters (doctrine §5)
- long-lived companion relationship, not single-session Q&A
- non-bypassable policy + visible trust UX
- hardware-aware tier model (Lite / Balanced / Full)

**Companion ships once — when complete** (doctrine §6). No interim wedge product. No headshot-only release. No voice-only release. No chat-only release. The OSS-friendly engineering posture (clean Tauri shell, layer scaffolds, open-weights tooling) remains correct as engineering practice — it just does not ship as a separate product.

### Companion scope (target end-state)

- Photoreal full-body 9-persona public cast (Aurora + 8 others) per ADR-0014.
- Pre-generated motion clip library + runtime blend + lip-sync overlay per ADR-0013.
- Text chat / mic input / voice output / avatar mode — interoperable; voice and avatar are sub-features, not separate products.
- Multi-tier performance (Lite / Balanced / Full); 50% VRAM default for Full.
- Capability-based permissions, 5-preset autonomy ladder, full trust center.
- Desktop primary (Tauri + React/TS + Rust core); mobile companion later (per Phase 5).
- Local-first state; cloud opt-in, scoped.

### Cast ownership

The 9-persona public cast is shipped under cast-creator authority (per Don's 2026-04-28 directive). Don retains override. Persona pipeline (ADR-0014) and runtime architecture (ADR-0013) govern technical assembly; persona content (look, voice, persona YAML) is delegated.

---

## Private overlay: **Isabelle / Isabelle_Kunstig**

### Role
Don's private avatar / persona overlay on top of Companion. Same codebase, separate persona pack and voice training. Overlay-only at runtime for Don's profile. **Never enters public distributables** — build-time lint enforces (`tools/lint-private-asset-leak/`).

### Architecture
**Isabelle is a privileged profile / persona pack on top of the Companion platform — not a separate codebase.** Rationale unchanged from prior version: separate codebase = maintenance drag; one shared platform with a private overlay = sustainable.

### Scope (private extensions on top of Companion)
- Custom persona (identity, tone, relationship style)
- Custom appearance (private avatar pack — separate photoreal pipeline run on X2 cadence per ADR-0014's out-of-scope clause)
- Custom voice
- Private memory tuning (salience, retention, provenance rules)
- Private permissions (wider autonomy, private domain/folder allowlists)
- Private workflows (Don-specific automations, integrations, triggers)
- Tight integration with Don's existing systems (Isabelle_Kunstig data, Tailscale network, existing project tooling)

### Policy
- Not distributed publicly.
- Built on Companion; does not diverge at the platform layer.
- All Companion doctrine applies; Isabelle is strictly additive on top.

### Working name
Isabelle / Isabelle_Kunstig (decision deferred — see [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)).

---

## Brand hierarchy summary

| Tier | Public name | Internal codename / role |
|------|-------------|---------------------------|
| Product | **Companion** | Internal codename `aether`. Repo `Projects/aether/`. The product. |
| Private overlay | **Isabelle** / **Isabelle_Kunstig** | Don's personal companion instance. Overlay-only at runtime. |

Public-facing names for related Don projects (memory-index reference):
- Vault (Library), Forge (CIGE), Herald (Morning Intel), VoxType (VoiceType), FuelFleet (StaFull), Snap (screenshot-clipboard).

---

## Retired structures

These were collapsed by doctrine §6 (2026-05-18):

- **"Aether OSS Preview" as standalone wedge product** — RETIRED. Tombstoned at `roadmaps/aether_oss_preview.md`. The OSS-friendly engineering posture remains correct; standalone OSS distribution does not.
- **"Aether Pro" as separate flagship distinct from OSS Preview** — RENAMED. Aether Pro is now simply Companion (one product, ships when complete).
- **"Aether umbrella name"** — preserved as internal codename `aether` only. Public branding is Companion.

---

## Separation rules

- **Public Companion vs private Isabelle** — same codebase, separated by build-time lint. Isabelle assets must never appear in public distributable manifests.
- **Cast vs overlay** — public 9-persona cast (Aurora et al.) is part of Companion. Isabelle is its own private persona, never bundled.
- **Shared concerns** (onboarding patterns, permission architecture, trust UX, design language) are defined once in the cross-cutting spec files (`04`–`16`).

---

## Cross-references
- Doctrine: [01_product_doctrine.md](01_product_doctrine.md) (§5+§6+§7+§8 are the most recent — added 2026-05-18).
- Vision & guardrails: [00_VISION_AND_GUARDRAILS.md](00_VISION_AND_GUARDRAILS.md).
- Companion roadmap: [roadmaps/aether_pro.md](roadmaps/aether_pro.md) (renamed-in-place; file path retained).
- OSS Preview tombstone: [roadmaps/aether_oss_preview.md](roadmaps/aether_oss_preview.md).
- Isabelle roadmap: [roadmaps/isabelle_private.md](roadmaps/isabelle_private.md).
- Avatar runtime: [docs/adr/ADR-0013-avatar-runtime-architecture.md](../docs/adr/ADR-0013-avatar-runtime-architecture.md).
- Per-persona pipeline: [docs/adr/ADR-0014-per-persona-character-pipeline.md](../docs/adr/ADR-0014-per-persona-character-pipeline.md).
- Reference-gen ownership: [docs/adr/ADR-0015-reference-image-generation-inside-companion.md](../docs/adr/ADR-0015-reference-image-generation-inside-companion.md).
- GPU queue: [plans/gpu_queue.md](plans/gpu_queue.md).
- Parallel software tracks: [plans/parallel_software_tracks.md](plans/parallel_software_tracks.md).
- Naming decisions: [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md#naming).
