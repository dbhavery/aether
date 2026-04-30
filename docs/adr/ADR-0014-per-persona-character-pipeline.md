# ADR-0014: Per-persona character pipeline — 7-step recipe, vertical-first then horizontal

- **Status:** **Proposed** (drafted 2026-05-18, awaits Don ratification before persona #1 begins).
- **Date:** 2026-05-18
- **Deciders:** Don (final), drafted by coordinator under doctrine §5+§6 authorization.
- **Supersedes:** the implicit headshot-first persona work that was paused per Don's 2026-04-29+ direction. Headshot-only persona development is closed.
- **Superseded by:** nothing yet.
- **Related:**
  - `planning/01_product_doctrine.md` §5 (photoreal full-body, no headshot intermediate).
  - `docs/adr/ADR-0013-avatar-runtime-architecture.md` (consumes Step 5 output).
  - `docs/adr/ADR-0015-reference-image-generation-inside-companion.md` (Step 1 ownership).
  - `docs/adr/ADR-0012-persona-delivery-download-on-demand.md` (delivery contract for the assets this pipeline produces).
  - `personas/CHARACTERS.md` (cast roster).
  - `planning/plans/gpu_queue.md` (queue execution order).

## Context

The cast is shipped (9 personas: Aurora, Marcus, Sara, James, Nadia, Priya, Ray, Hannah, Tomás) with anchor + portrait + profile images and voice references — the "headshot-class" asset pack documented in ADR-0012. Doctrine §5 retires headshot-only as a path: characters must be created photoreal full-body from the start. The existing asset packs are insufficient for full-body video character training because the framing and identity-conditioning are headshot-biased.

A new pipeline is required. The pipeline is GPU-heavy, multi-step, and per-persona. With 9 personas, two execution patterns are possible:

- **Horizontal:** all 9 through Step 1, then all 9 through Step 2, etc. Batch efficiency, consistent recipe across cast.
- **Vertical:** Persona #1 end-to-end through all steps first, then remaining 8 batched horizontally once recipe is locked.

The recipe itself (which specific models, ranks, training counts, motion targets) is non-trivial and will surface bugs that invalidate prior steps. Choosing the wrong execution pattern costs months of GPU time.

## Decision

**Adopt the 7-step pipeline below.** **Persona #1 (Aurora) runs end-to-end vertically first** as the recipe-proving case. Once Aurora ships clean and the recipe is locked in this ADR's "Frozen recipe" section, the remaining 8 personas batch horizontally (all 8 through Step 1, then Step 2, etc.).

Aurora is chosen as #1 because she is the foundational character (the Creator) and her output gets the most scrutiny — the recipe needs to survive that scrutiny before being applied at scale.

## The 7-step recipe

### Step 1 — Reference image generation (Don-curated)
Generate a curated set of full-body photoreal reference images per persona at varied poses, framings, lighting conditions. Tooling lives **inside Companion** per ADR-0015 (not in CIGE/Forge as upstream). Models: FLUX.1-dev or RealVisXL Lightning baseline; persona-specific seeds and prompt anchors. Output: ~30–100 curated images per persona after Don's cull. Captioning requires Don in the loop (per `feedback_captioning_requires_don.md`).

### Step 2 — Identity LoRA training (face + body locked)
Train a persona-identity LoRA on the curated reference set. Face and body are **locked together in one training run** — no separate face-LoRA / body-LoRA split (would reintroduce the headshot-transition problem doctrine §5 forbids). Recipe parameters (rank, alpha, learning rate, step count) frozen after Aurora's run. Output: persona-identity LoRA (image-domain).

### Step 3 — Voice cloning
Per-persona voice clone using Zonos-class infrastructure (already proven in QuickGrid TTS work; see `reference_zonos_30s_cap.md` for the chunking constraint). Voice identity locked per persona. Existing `voice.yaml` + voice reference WAVs in the persona pack are inputs. Output: persona-voice TTS-ready model.

### Step 4 — Video character LoRA
Train a video-domain LoRA on the persona's identity for a chosen video model (Wan 2.1 / HunyuanVideo / LTX-Video — model choice deferred to first run). Conditioning on identity LoRA from Step 2. This is the single largest GPU spend per persona. Output: video-character LoRA suitable for clip generation.

### Step 5 — Motion clip library generation
Generate the motion library per ADR-0013's asset-side specification: idle, listening, speaking-base poses, transitions, common gestures. Each clip generated against the video character LoRA, Don-curated for identity consistency and motion quality. Output: motion clip library per persona, on disk, ready for L3's runtime renderer.

### Step 6 — Lip-sync fine-tune (optional, late-stage)
If the chosen lip-sync model (Sonic / Hallo / EMO — bake-off per ADR-0013) underperforms on a persona's identity, fine-tune the lip-sync model on persona-specific speaking samples. Skipped if baseline is acceptable. Output: per-persona lip-sync overlay (only when needed).

### Step 7 — Quality eval generation
Generate end-to-end test runs against Quality-Eval V1 scenarios. Audio + video + transcript produced for review. Pass criteria: identity stable across clips, lip-sync tracks without drift, presence feels socially coherent, no uncanny defects.

**Visual self-test gate (doctrine §8).** Before any Step 7 output reaches Don, the agent runs multimodal vision evaluation against the pass criteria above. Self-test report is attached when the persona is surfaced for Don's pass-gate. Failed self-tests do **not** reach Don — they re-loop the failing producing step (typically Step 5 motion library or Step 6 lip-sync fine-tune). Same gate applies to Step 1 reference images and Step 5 motion library outputs before Don's curation passes.

Output: pass/fail verdict per persona; persona ships only on pass.

## Frozen recipe (filled after Aurora completes — DO NOT EDIT MANUALLY before that)

| Parameter | Aurora value | Locked across cast |
| --- | --- | --- |
| Step 1 base model | _TBD after Aurora_ | _TBD_ |
| Step 1 image count (post-cull) | _TBD_ | _TBD_ |
| Step 2 LoRA rank | _TBD_ | _TBD_ |
| Step 2 LoRA alpha | _TBD_ | _TBD_ |
| Step 2 step count | _TBD_ | _TBD_ |
| Step 4 video model | _TBD_ | _TBD_ |
| Step 4 LoRA rank | _TBD_ | _TBD_ |
| Step 5 clip count per state | _TBD_ | _TBD_ |
| Step 6 lip-sync model | _TBD per ADR-0013 bake-off_ | _TBD_ |

## Execution sequencing

```
Phase 1 (vertical, Aurora):
  Step 1 → Step 2 → Step 3 → Step 4 → Step 5 → (Step 6 if needed) → Step 7
  Pass-gate: Don approves Aurora end-to-end.
  Then: lock the Frozen Recipe section above.

Phase 2 (horizontal, remaining 8):
  Step 1 batch (8 personas) → Step 2 batch → ... → Step 7 batch
  Pass-gate per persona at Step 7. Failed personas re-loop the failing step.
```

GPU queue runs sequentially throughout — see `planning/plans/gpu_queue.md` for current job, on-deck, and completed.

## Consequences

**Positive:**
- Recipe bugs surface on one persona, not nine.
- Each persona ships as a complete photoreal identity (no headshot-then-body discontinuity per doctrine §5).
- GPU saturation maintained — sequential queue with finite per-persona work units.
- Outputs are consumable directly by L3 Presence V1's runtime renderer (per ADR-0013 contract).
- Each persona's final delivery can flow through ADR-0012's existing pack-signing crypto loop.

**Negative:**
- Aurora end-to-end is the long pole before any other persona can start. If Aurora's recipe takes weeks to lock, the other 8 personas wait.
- Per-persona disk footprint will balloon vs the current ~15 MB pack (full motion library is video data). ADR-0012's bundled-vs-download tier model needs revisiting after Step 5 measures actual size.
- Step 4 (video LoRA) is research-grade in early 2026 — the open-weight video model ecosystem is moving fast. Recipe may need refresh between Phase 1 and Phase 2 if a materially better base model lands. Acceptable risk; documented here.

## Out of scope

- **Isabelle private overlay.** Isabelle's photoreal pipeline runs separately on the X2 cadence. This ADR governs the public cast only.
- **Persona authorship / look / voice / persona content.** Cast creator (per Don's 2026-04-28 directive) retains those choices; this ADR governs the technical pipeline only.
- **Lip-sync model selection.** Deferred to a follow-up ADR after Aurora's bake-off.
- **Storage / delivery footprint update for ADR-0012.** Deferred until Step 5 has produced the first measured library.
