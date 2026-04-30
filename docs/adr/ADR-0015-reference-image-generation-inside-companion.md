# ADR-0015: Reference image generation lives inside Companion (not in CIGE/Forge as upstream)

- **Status:** **Accepted** (Don's explicit directive 2026-05-18: "inside companion for public avail characters").
- **Date:** 2026-05-18
- **Deciders:** Don (final, explicit), drafted by coordinator.
- **Supersedes:** the implicit option of using CIGE/Forge (`Projects/Custom-Image-Generator-and-Editor/`, public name **Forge**) as the upstream image-generation tool whose outputs Companion would consume via file handoff.
- **Superseded by:** nothing yet.
- **Related:**
  - `planning/01_product_doctrine.md` §5 (photoreal full-body) and §6 (single-product, ships when complete).
  - `docs/adr/ADR-0014-per-persona-character-pipeline.md` Step 1 (consumes the pipeline this ADR locates).
  - `feedback_ai_source_models_only.md` (AI-generated source models constraint).
  - `feedback_captioning_requires_don.md` (Don-in-loop curation constraint).

## Context

ADR-0014 Step 1 specifies "reference image generation, Don-curated" as the first step of the per-persona character pipeline. Two locations were possible:

- **Option A — CIGE/Forge as upstream.** Companion's pipeline consumes image files produced by CIGE/Forge (`Projects/Custom-Image-Generator-and-Editor/`, a separate finished PySide6 desktop app already built around FLUX.1-dev + RealVisXL Lightning). Two repos, file handoff, no code coupling.
- **Option B — Reference-gen inside Companion.** Companion grows its own reference-image generation module. Single repo, no inter-project dependency, public-cast pipeline self-contained.

Don's directive 2026-05-18: "inside companion for public avail characters."

## Decision

**Adopt Option B.** Reference-image generation for the public-cast persona pipeline lives inside the Companion repo. CIGE/Forge remains a separate finished product and is not in Companion's dependency surface for public characters.

## Rationale

1. **Single-product doctrine (doctrine §6).** Companion ships as one product; its persona pipeline ships with it. An external tool dependency for the public-character pipeline would split the build.
2. **Reproducibility.** Public characters are produced and reproduced entirely from Companion's repo. Anyone with the Companion source can re-derive every persona's reference set without needing a separate Forge install.
3. **No inter-project file handoff.** File handoff between two repos creates path-coordination friction, version-skew risk, and extra steps Don has to remember. Removing it removes those.
4. **CIGE/Forge stays Forge.** Forge is its own product with its own audience (general image generation + editing). Conflating Forge's roadmap with Companion's persona pipeline would distort both.
5. **Private overlay is unaffected.** Isabelle's private persona pipeline is on the X2 cadence and its reference-gen tooling can live wherever Don prefers; this ADR governs the public cast only.

## Architecture

### Module location
`tools/persona-reference-gen/` (new, scaffolded under coordinator-gated package creation per `CLAUDE.md` §3 if it requires a new top-level directory; otherwise under existing `tools/`).

### Stack
- **Models:** FLUX.1-dev and RealVisXL Lightning baselines (matches Forge's stack — same primitives, different control surface and curation flow).
- **Language:** Python (matches existing `infra/persona-manifest/` and `tools/evals/` patterns; not Rust).
- **Inputs:** persona slug, prompt anchors from `personas/<slug>/persona.yaml`, seed sets, framing/lighting matrix.
- **Outputs:** curated image set written to `personas/<slug>/_pipeline/step1_references/` (or equivalent per Step 5 final placement).
- **Don-in-loop curation:** captioning and final-cull is interactive per `feedback_captioning_requires_don.md`. The module produces a candidate batch; Don approves/rejects/re-prompts.

### Boundary lints
This module is `tools/`-scoped (Python, build-time) and does not import from any `packages/l*/` Rust crate. It produces files consumed by ADR-0014's later steps. `tools/lint-layer-boundaries/` does not need a new bridge rule.

### Relationship to Forge
Zero. Forge continues to exist independently. If Don personally uses Forge for any private-character or one-off image work, that's outside this ADR's scope.

## Consequences

**Positive:**
- Companion is self-contained for public-character production.
- No two-repo coordination or version skew.
- The persona pipeline (Step 1) is reproducible from a Companion checkout alone.
- Forge stays focused on its own product.

**Negative:**
- Some duplication of image-gen plumbing between Companion's `tools/persona-reference-gen/` and Forge. Acceptable — Forge's UX layer (Graphite Pro UI, editor surface, 144 tests) is not duplicated; only the underlying FLUX/RealVisXL invocation primitives are. Those primitives are thin wrappers around the model runtimes.
- If FLUX.1-dev / RealVisXL plumbing improves in Forge, Companion does not automatically benefit. Acceptable — Companion's plumbing is built once and frozen alongside ADR-0014's Frozen Recipe.

## Out of scope

- **Isabelle's private reference-gen tooling.** Don's call where it lives.
- **Forge's roadmap.** Independent product, not governed by this ADR.
- **Image editing / inpainting workflows** post-generation. If needed for the persona pipeline, deferred to a separate decision; Step 1 is generation only.
