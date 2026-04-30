# ADR-0013: Avatar runtime architecture — pre-generated motion library + runtime blend + lip-sync overlay

- **Status:** **Proposed** (drafted 2026-05-18, awaits Don ratification before deep training spend commits the project to one path).
- **Date:** 2026-05-18
- **Deciders:** Don (final), drafted by coordinator under doctrine §5+§6 authorization.
- **Supersedes:** nothing — first runtime-architecture ADR for the photoreal avatar.
- **Superseded by:** nothing yet.
- **Related:**
  - `planning/01_product_doctrine.md` §5 (photoreal full-body, no headshot intermediate) and §6 (no interim release).
  - `docs/adr/ADR-0014-per-persona-character-pipeline.md` (the GPU recipe whose output this ADR consumes).
  - `docs/adr/ADR-0015-reference-image-generation-inside-companion.md` (where the visual identity work lives).
  - `planning/11_avatar_presence.md` (avatar presence requirements).
  - `docs/PRESENCE-V1-ARCHITECTURE.md` (Presence V1 — DONE 2026-05-17, shipped without visual rendering).

## Context

Doctrine §5 locks photoreal full-body characters as the avatar target from the first identity training run. The avatar runtime — what actually plays back on screen during a conversation — is not yet decided. Three architectures are realistic in the early-2026 open-weights ecosystem:

1. **On-demand full-body video generation per response.** Every assistant turn triggers a fresh video generation conditioned on transcript + persona + state. Maximum flexibility, expressivity tracks the response exactly.
2. **Pre-generated motion clip library + runtime blend + lip-sync overlay.** Each persona ships with a library of pre-rendered motion clips covering states (idle, listening, thinking, speaking variations, transitions, common gestures). Runtime selects clips per L3 presence state, blends transitions, overlays lip-sync onto speaking clips.
3. **Hybrid.** Pre-generated library covers common states; on-demand generation triggers for rare/expressive states or as a quality-eval comparison.

This decision must be made **before** ADR-0014 commits training spend, because the pipeline's Step 5 (motion clip library generation) is sized entirely differently depending on whether on-demand is the primary path or a fallback.

## Decision

**Adopt option 2: pre-generated motion clip library + runtime blend + lip-sync overlay**, with hybrid (option 3) reserved as a possible later extension once the library approach is shipping.

## Rationale

1. **Latency.** On-demand full-body video generation in early 2026 is measured in seconds-to-minutes per clip on consumer hardware. Pre-generated library lookup + lip-sync overlay is sub-second. Doctrine §3 (north star) makes acknowledgment timing a first-class measurable; on-demand cannot meet it.
2. **Determinism.** Pre-generated clips are reviewable, curatable, and Don can cull at the asset stage. On-demand generation drifts per-turn — quality is non-stationary.
3. **GPU saturation discipline.** Pre-generated library lets the GPU queue (see `planning/plans/gpu_queue.md`) run sequentially overnight, producing a finite asset library that becomes runtime-static. On-demand generation makes the GPU a runtime resource competing with inference, which violates the GPU-saturation discipline.
4. **Failure mode.** A pre-generated clip that's wrong is a curatable defect (re-shoot the clip). An on-demand failure is a live-conversation defect.
5. **Open-weight maturity.** Motion-transfer / lip-sync overlay models (Sonic, Hallo, EMO-class, MimicMotion) are more production-ready in open weights than full-conditional video generation models (Wan 2.1, HunyuanVideo, LTX-Video, CogVideoX) for conversational use. Library-first plays to the strengths of the more mature open-weight stack.

## Architecture

### Asset side (per persona, output of ADR-0014's Step 5)

A motion clip library covering at minimum:
- **Idle states** — neutral standing, subtle weight shifts, breathing, micro-expressions.
- **Listening states** — attentive, engaged, thinking.
- **Speaking states** — multiple base poses with mouth-neutral framing, suitable for lip-sync overlay.
- **Transitions** — listening→speaking, speaking→idle, etc.
- **Common gestures** — affirmation, hesitation, emphasis (subset; persona-flavored).

Each clip is loop-safe at the boundaries (or has explicit transition pairs) so the runtime blend doesn't pop.

### Runtime side (lives in L3 Presence)

L3's existing presence state machine (Listening / Thinking / Acknowledging / Speaking / Idle / Waiting) drives clip selection. A blend layer cross-fades between clips at state transitions. When the state is Speaking, a lip-sync model (Sonic / Hallo / EMO-class) overlays the current TTS audio onto the chosen speaking-base clip.

L3 today (Presence V1, DONE 2026-05-17) ships the state machine and bridge events but no visual renderer. This ADR locks the renderer's input contract — clip library + L3 events + TTS audio stream — so L3 can be extended with the renderer in a later wave without contract churn.

### Open question deferred to follow-up

**Lip-sync model choice** (Sonic vs Hallo vs EMO vs custom fine-tune) is deferred to a separate ADR after a bake-off on the first persona's motion library. Comparison criteria: identity preservation across mouth shapes, latency, hallucination rate on long phrases, GPU footprint at runtime.

## Consequences

**Positive:**
- Sub-second avatar response time at runtime.
- GPU is fully consumed during pipeline build (saturation discipline) and free for inference at runtime.
- Quality is curatable per-clip rather than per-turn.
- L3 Presence V1 architecture stays valid; only its renderer is extended.
- Failure mode = pre-shipping defect (catchable) rather than live defect (visible to user).

**Negative:**
- Library size per persona will be non-trivial (each clip is real video). Persona pack delivery (ADR-0012) needs storage/footprint review when motion libraries land. Defer the per-pack footprint constraint update to a follow-up after the first pipeline cycle measures actual library size.
- Expressivity ceiling is the library's coverage. Rare emotional registers or context-specific gestures may require library expansion or hybrid-mode fallback. Acceptable for v1; revisit if quality eval flags it.
- Lip-sync overlay quality is the gating factor for "indistinguishable from human" — speaking clips dominate user attention. Lip-sync model choice (deferred above) is the next critical decision.

## Empirical validation plan

1. Persona #1 (Aurora) motion library generates as part of the ADR-0014 Step 5 run.
2. Lip-sync bake-off runs against Aurora's speaking clips.
3. End-to-end blind test: Don evaluates a 60-second sample conversation against Aurora's runtime renderer. Pass criteria: presence feels socially coherent, no uncanny defects, lip-sync tracks audio without obvious drift.
4. If pass: lock library-first as the doctrine and proceed to remaining 8 personas.
5. If fail: open a follow-up ADR for hybrid-mode escalation or alternative architecture.
