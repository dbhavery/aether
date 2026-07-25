# Companion glossary

> **Status:** Skeleton. Structure and stubs only.
> **Created:** 2026-05-16 (closing audit gap #1 against the 22-section
> numbered specification outline).
> **Keystone.** This is the canonical vocabulary file for Companion. When
> two docs disagree on what a term means, this file is where the tie
> is broken.

---

## 0. How to use this glossary

- **Authoring new specs.** Reference terms here rather than
  redefining them inline. If a term doesn't exist yet, add a stub
  here first, then link to it.
- **Term disagreements.** If two docs use the same word for different
  things, the resolution lives here — either as one definition with
  notes on context, or as two explicitly-namespaced terms.
- **Stub convention.** Entries marked `TODO — derive from <source>`
  are known placeholders. Fill them when the referenced source is
  stable enough to copy from.
- **Back-links.** Every entry should reference its canonical source
  doc once the stub is filled. The glossary is the vocabulary index,
  not the source of truth for behavior — the architecture docs are.

### 0.1 When to add a term

- The term appears in ≥2 docs or ≥2 subsystems.
- Its meaning is load-bearing (removing the term would confuse a
  reviewer).
- A user-facing or spec-facing decision depends on the meaning being
  unambiguous.

### 0.2 When NOT to add a term

- Single-use technical identifiers (function names, commit SHAs,
  file paths).
- Terms whose meaning is entirely captured by a single
  architecture doc's own internal definition and isn't referenced
  elsewhere.

---

## 1. Core product concepts

- **Companion**
  Definition: TODO — derive from `ARCHITECTURE.md`
  + `docs/PRODUCT-PLAN.md`.
  Short: the master platform family for a multimodal AI assistant
  product centred on conversational interaction, local-first
  responsiveness, customisable identity, and high-trust UX.

- **local-first**
  Definition: TODO — derive from `docs/PRODUCT-PLAN.md` +
  `docs/LLM-PROVIDERS.md`.
  Short: execution and data default to the user's machine; network /
  cloud is opt-in, not assumed.

- **personal companion**
  Definition: TODO — derive from `ARCHITECTURE.md`.

- **multimodal**
  Definition: TODO — derive from `docs/ARCHITECTURE-V2.md` +
  `docs/VISION-V1-ARCHITECTURE.md` + `docs/VOICE-V1-ARCHITECTURE.md`.
  Short: text + voice (push-to-talk) + vision (single-frame) + presence
  as first-class interaction modalities in the same session.

- **trust surface**
  Definition: TODO — derive from `docs/PRESENCE-V1-ARCHITECTURE.md` §4
  + `ARCHITECTURE.md` §Trust & security.
  Short: any UI or audit affordance where the user can see, inspect,
  or reverse what Companion did on their behalf.

- **Companion**
  Definition: TODO — derive from `docs/PRODUCT-PLAN.md`.

- **Companion (OSS Preview wedge thesis retired 2026-05-18 per doctrine §6)**
  Definition: TODO — derive from `docs/PRODUCT-PLAN.md`.

---

## 2. User and mode terminology

- **persona**
  Definition: TODO — derive from `docs/PERSONA-SCHEMA.md`.

- **user mode**
  Definition: TODO — derive from `ARCHITECTURE.md`.

- **session**
  Definition: TODO — derive from `ARCHITECTURE.md`
  + `plans/L1_interaction_timing.md`.
  Short: one continuous conversation bounded by window lifecycle +
  explicit "new session" actions.

- **conversation**
  Definition: TODO. Note: often used interchangeably with "session";
  resolve namespace vs session if they diverge.

- **assistant posture**
  Definition: TODO — derive from
  `packages/l3-presence/src/controller.rs` doc comments +
  `docs/PRESENCE-V1-ARCHITECTURE.md` §2.
  Short: the assistant's own state axis at turn granularity (Quiet /
  Listening / Thinking / AwaitingApproval / Responding).

- **user attention**
  Definition: TODO — derive from
  `packages/l3-presence/src/attention.rs` doc comments +
  `docs/PRESENCE-V1-ARCHITECTURE.md` §2.
  Short: the user's own state axis, coarse (Active / Idle / Away),
  driven by OS idle timer. Sibling to assistant posture.

- **turn**
  Definition: TODO — derive from `plans/L1_interaction_timing.md`.

---

## 3. Architecture and layering

- **L1 — interaction timing**
  Definition: TODO — derive from `plans/L1_interaction_timing.md`.

- **L2 — memory kernel**
  Definition: TODO — derive from `plans/L2_memory_kernel.md`.

- **L3 — presence engine**
  Definition: TODO — derive from `plans/L3_presence_engine.md` +
  `docs/PRESENCE-V1-ARCHITECTURE.md`.
  Note: currently hosts two orthogonal axes (assistant posture +
  user attention). Watch for a sub-layer split if more axes land.

- **L4 — model router**
  Definition: TODO — derive from `plans/L4_model_router.md`.

- **L5 — policy engine**
  Definition: TODO — derive from `plans/L5_policy_engine.md`.

- **L6 — persona compiler**
  Definition: TODO — derive from `plans/L6_persona_compiler.md`.

- **L7 — trust + UX + onboarding**
  Definition: TODO — derive from `plans/L7_trust_ux_onboarding.md`.

- **layer (L1–L7)**
  Definition: a dependency / moat axis. Layers are ordered by
  dependency direction; siblings do not import each other directly
  (per `CLAUDE.md` §1.4). **Not** a time axis — layers do not
  correspond to phases of work.

- **subsystem**
  Definition: a named user-facing capability cluster (Vision, Voice,
  Presence, Memory, Quality-Eval, Onboarding). A subsystem may cut
  across layers; e.g., Memory V2 spans L2 (kernel), L5 (capabilities),
  and L7 (trust surfaces).

- **interface pack**
  Definition: TODO — derive from `ARCHITECTURE.md`.
  Short: the contract surface (types, events, public traits) a layer
  exposes to its consumers.

- **event contracts**
  Definition: TODO — derive from `ARCHITECTURE.md`.
  Short: canonical event names + payload shapes crossing the
  event bus; Rust enums are canonical, TS is generated.

- **change_id / seq / source_layer**
  Definition: event-envelope fields (see `event_contracts_master.md`)
  that identify the originating layer and ordering. Required on every
  event.

---

## 4. Waves and steps

- **Wave 1–4**
  Definition: TODO — derive from `CLAUDE.md` §1 +
  `ARCHITECTURE.md`.
  Short: coarse architectural phasing for the monorepo build-out.
  Wave 1 scaffolds; later waves flesh out. Waves are the only
  architectural-time axis in the repo.

- **subsystem V&lt;N&gt; step &lt;N&gt;**
  Definition: the canonical execution-tracking format. Used in
  handoffs, execution reports, and commit messages. Examples:
  `Vision V1 step 5`, `Voice V1 step 6`, `Presence V1 step 2`,
  `Memory V2 step 2`. The `V<N>` is the subsystem milestone; the
  `step <N>` is a bounded slice of work under that milestone.

- **step**
  Definition: a bounded, shippable slice of work under a subsystem
  `V<N>` milestone. Each step lands with commits, tests, and an
  execution report. Steps do not span sessions.

- **design-only → current**
  Definition: the lifecycle every subsystem architecture doc follows.
  A doc starts as "design-only" (nothing enforced by code); flips to
  "current" when its rot guard (`tools/lint-<subsystem>-doc/`) ships
  and verifies anchors against the code.

- **decision-lock pass**
  Definition: a planning session that converts open questions into
  locked decisions. The locked decisions are recorded in
  `ARCHITECTURE.md` and the relevant `docs/adr/` entries.

---

## 5. Capabilities and policy

- **capability**
  Definition: TODO — derive from
  `packages/l5-policy/src/capability.rs` +
  `ARCHITECTURE.md` §Permissions & autonomy.
  Short: a named action the assistant might take that is subject to
  policy evaluation (e.g., `MediaCamera`, `MemoryWrite`, `FilesEdit`).

- **Capability::MediaCamera / MediaScreenCapture / Microphone**
  Definition: TODO — derive from capability.rs.

- **Capability::MemoryRead / MemoryWrite / MemoryForget / MemoryEdit**
  Definition: TODO — derive from capability.rs +
  `docs/MEMORY-V2-ARCHITECTURE.md` §10 step 1.
  Note: Memory V2 coarse surface. Step 1 (additive landing) complete;
  step 2 (policy surface) complete; step 3 (L2 plumbing) pending.

- **policy mode: Auto / Ask / Deny**
  Definition: TODO — derive from `docs/MEMORY-V2-ARCHITECTURE.md` §4
  + `ARCHITECTURE.md` §Permissions & autonomy.
  Short: tri-state write posture per domain. `Auto` = proceed + audit;
  `Ask` = user approval modal + audit; `Deny` = reject + audit.

- **decision (Allow / Ask / Deny / NeedsUpgrade / DraftOnly)**
  Definition: TODO — derive from
  `packages/l5-policy/src/engine.rs`.
  Short: the L5 engine's evaluation result for a requested capability
  under current policy + autonomy preset.

- **autonomy preset (Observer / Assistant / Operator)**
  Definition: TODO — derive from L5 engine + `04_user_modes.md`.

- **grant ledger**
  Definition: TODO — derive from L5 policy engine.

---

## 6. Trust, permissions, and audit

- **Trust drawer**
  Definition: TODO — derive from
  `apps/desktop/src/components/TrustDrawer.tsx` +
  `ARCHITECTURE.md` §Trust & security.
  Short: the user-facing review surface that renders audit rows,
  turn telemetry, and presence history side by side.

- **audit store**
  Definition: TODO — derive from
  `packages/l5-policy/src/audit.rs`.
  Short: append-only hash-chained log of every L5 decision.

- **audit event (AuditRecordEvent)**
  Definition: TODO — derive from L5 events. One row per policy-gated
  action. Shape is stable — changes go through additive capability
  enum variants.

- **telemetry ring / telemetry entry**
  Definition: TODO — derive from
  `apps/desktop/src-tauri/src/state.rs` (`TelemetryEntry`).
  Short: in-memory bounded ring of per-turn observability rows; UX
  only, cleared on restart. Separate from audit.

- **presence history ring**
  Definition: TODO — derive from
  `apps/desktop/src-tauri/src/state.rs` (`PresenceHistoryEntry`).
  Short: UX-only bounded ring of presence transitions, rendered in
  the Trust drawer History tab. Separate from telemetry and audit
  because presence is observational, not policy-gated.

- **rot guard**
  Definition: a doc/code drift enforcement tool under `tools/lint-
  <name>-doc/`. Checks that named anchor strings from an
  architecture doc are present across a fixed set of code files.
  **Enforces doc↔code anchor presence, not behavioral correctness.**
  See [`docs/AC-STYLE.md`](AC-STYLE.md) for the split between rot
  guards and acceptance criteria.

- **hard constraints**
  Definition: a section in every subsystem architecture doc listing
  invariants that must hold for every PR in that subsystem. Rot-
  guarded. **Not** acceptance criteria — hard constraints describe
  *what must stay true*; acceptance criteria describe *how we
  verify it under inputs*.

- **anchor (in rot-guard context)**
  Definition: a short quoted string from a subsystem architecture doc
  that must appear, unchanged, in one or more designated source files.
  The rot guard fails CI if the anchor is moved or removed without
  updating the manifest.

- **acceptance criteria (AC)**
  Definition: behavioural, testable checks that verify a feature does
  the right thing under specific inputs. Each criterion expresses one
  observable outcome a tester can pass/fail by inspection — written
  user-perspective ("the user sees", "the agent emits", "the audit
  log shows"), not implementation-perspective. Live as numbered lists
  under `## Acceptance criteria` headings in spec docs; verified by
  tests, evals, or other measurable artifacts. **Do not collapse AC
  into rot guards or hard constraints** — those are different shapes.
  See [`docs/AC-STYLE.md`](AC-STYLE.md) for the canonical writing
  rules + good/bad examples.

---

## 7. Modality-specific terms

### 7.1 Vision

- **vision provider**
  Definition: TODO — derive from `docs/VISION-V1-ARCHITECTURE.md` +
  `apps/desktop/src-tauri/src/vision_registry.rs`.

- **analyze_frame**
  Definition: TODO — Tauri command; single-frame inference.

- **vision model id**
  Definition: TODO.

- **VisionBadge / ActiveVisionRoute**
  Definition: TODO — UI components surfacing the active vision route.

### 7.2 Voice

- **push-to-talk (PTT)**
  Definition: TODO — derive from `docs/VOICE-V1-ARCHITECTURE.md`.
  Short: user must hold a control to capture audio. No continuous
  listening, no VAD, no wake word.

- **speech provider**
  Definition: TODO — derive from voice architecture doc +
  `apps/desktop/src-tauri/src/voice_registry.rs`.

- **utterance**
  Definition: TODO — derive from `transcribe_utterance` command.

- **no silent fallback**
  Definition: a Voice V1 contract. Transport, HTTP, parse errors
  surface as visible errors — they never degrade silently to empty
  transcripts.

- **whisper.cpp / whisper-server**
  Definition: TODO — reference implementation for local speech.

### 7.3 Presence

- **presence state**
  Definition: ambiguous — disambiguate by axis. See "assistant
  posture" (§2) and "user attention" (§2).

- **PresenceController**
  Definition: TODO — derive from `packages/l3-presence/src/
  controller.rs`. Owns the assistant-posture axis.

- **UserAttentionController**
  Definition: TODO — derive from `packages/l3-presence/src/
  attention.rs`. Owns the user-attention axis. Sibling to
  PresenceController — they do not import each other.

- **IdleProbe**
  Definition: TODO — derive from
  `apps/desktop/src-tauri/src/idle_probe.rs`.

- **OS idle probe**
  Definition: platform implementation of `IdleProbe`. Windows uses
  `GetLastInputInfo`; macOS / Linux are stubbed (honest `None`) until
  their real probes ship.

- **idle_after_s / away_after_s**
  Definition: TODO — presence thresholds (seconds). Active→Idle at
  `idle_after_s`; Idle→Away at `away_after_s`. Bounded 10..=86400.

- **probe_supported**
  Definition: a snapshot flag that's `false` on platforms without a
  real idle probe. UI must surface this truthfully rather than
  pretending the user is always attentive.

### 7.4 Memory

- **memory domain**
  Definition: TODO — derive from `docs/MEMORY-V2-ARCHITECTURE.md` §1.
  Six values: Session, Durable, Facts, Projects, Preferences,
  Artifacts.

- **retention (days / forever)**
  Definition: TODO — derive from Memory V2 arch §3.

- **forget (per-item) vs delete (bulk)**
  Definition: TODO — derive from Memory V2 arch §8 item 2.
  `MemoryForget` is per-item; `MemoryDelete` is bulk (pre-V2,
  retained).

- **MemoryPolicyRegistry**
  Definition: TODO — the single-writer surface for `memory.json`.
  Lives in `apps/desktop/src-tauri/src/memory_config.rs`.

- **embeddings (opt-in)**
  Definition: TODO — derive from Memory V2 arch §3. Ship default off.

### 7.5 Quality-Eval

- **scenario (eval)**
  Definition: TODO — derive from `docs/QUALITY-EVAL-V1-ARCHITECTURE.md`
  §2.1. One-line JSONL record of setup + turns + actual + expectations.

- **adversarial probe**
  Definition: TODO — derive from quality-eval arch §2.3. A deliberately-
  bad response used to verify the detector still fires.

- **expectation kind (forbids / requires / length / tone)**
  Definition: TODO — derive from `tools/evals/expectations.py`.

- **baseline (eval)**
  Definition: a dated snapshot of the harness output, committed
  alongside the session handoff. `tools/evals/baseline/<date>.md`.

- **dry-run vs live backend**
  Definition: TODO — derive from `tools/evals/README.md`.

- **six quality domains**
  Definition: chat realism, tool-use judgment, vision response
  quality, voice transcription, memory appropriateness, presence-
  aware behaviour. The "indistinguishable from a real person" bar is
  defined per domain.

- **calibrated confidence**
  Definition: quality-eval arch §0 meta-criterion. The assistant's
  certainty must match the information it has.

---

## 8. Product-tier terms

- **Companion**
  Cross-reference: §1. The public, minimal, extensible baseline.

- **Companion**
  Cross-reference: §1. The commercial-grade flagship.

- **Cross-system spec**
  Definition: the rulebook covering onboarding, permissions, trust,
  performance tiers, and updates for the single Companion product.
  (Pre-doctrine §6 phrasing called this "shared across OSS Preview
  and Pro" — that split was retired 2026-05-18; the rulebook is now
  the Companion rulebook.) In the current repo, this material lives
  in numbered planning docs (`06_onboarding_spec.md`,
  `12_permissions_autonomy.md`,
  `13_trust_security_redteam.md`, `14_performance_tiers_vram.md`,
  `15_updates_releases.md`) rather than in one assembled document.

- **OSS/Pro alignment map**
  Definition: historical cross-walks that mapped layer work onto
  product tiers, before the single-product doctrine (§6) retired the
  OSS/Pro split. Superseded by `docs/PRODUCT-PLAN.md`.

---

## 9. Non-functional and operational terms

- **NFR (non-functional requirement)**
  Definition: TODO — populate when `docs/NFR.md` lands (audit gap
  #2). Short: requirements about *how* the system behaves (latency,
  availability, resource usage, portability) rather than *what* it
  does.

- **latency budget**
  Definition: TODO.

- **availability**
  Definition: TODO.

- **sync convergence**
  Definition: TODO — populate when the cross-device sync track has a design doc.

- **resource budget (VRAM / RAM / CPU tier)**
  Definition: TODO — derive from `docs/adr/ADR-0006-hardware-tier-model.md`.

- **tier (performance)**
  Definition: TODO — `docs/adr/ADR-0006-hardware-tier-model.md`.

- **model router tier (Reflex / Balanced / Critical)**
  Definition: TODO — derive from `plans/L4_model_router.md` +
  `docs/LLM-PROVIDERS.md`. Note: this is the *routing*
  tier, not the *performance* tier — they are different axes and
  should not be collapsed.

---

## 10. References and update rules

- **Back-link convention.** Every populated entry should cite its
  canonical source doc once, in the form "derive from
  `path/to/doc.md` §N".
- **Add a term when.** See §0.1.
- **Do not add a term when.** See §0.2.
- **Duplicate-term handling.** When two subsystems use the same word
  for different things (e.g., "presence state" at posture-axis
  granularity vs attention-axis granularity), disambiguate by
  namespace (e.g., "assistant-posture state" / "user-attention
  state") rather than letting context do the work.
- **This doc is not the source of truth for behaviour.** The
  architecture docs are. If a glossary entry and an architecture doc
  disagree, the architecture doc wins — and the glossary entry
  gets updated in the same PR.

---

## 11. Open glossary decisions

Tracked here temporarily; promote to a tracked ADR under `docs/adr/`
if any survives more than one drafting pass.

- ~~**AC house style** — bullets-with-thresholds vs Given/When/Then.~~
  **Resolved 2026-04-30** by [`docs/AC-STYLE.md`](AC-STYLE.md): bullets-with-thresholds + optional `(P0/P1/P2)` priority + optional `(verified by: <test or anchor>)` provenance. Don may override via a follow-up edit; default is locked.
- **Requirement ID scheme** — proposed `<layer>-<subsystem>-<NNN>`
  (e.g. `L2-MEM-014`). Not locked. Blocks populating any term that
  references "requirement ID".
- **Presence axis namespace.** Whether to keep the two L3 controllers
  as siblings in one crate or split into a sub-layer. Watch-only per
  the 2026-05-16 handoff; if a third axis lands, this decision comes
  off the back burner.
- **"Cross-system spec" doc shape.** Pointer doc vs generated view.
  Blocks populating the `Cross-system spec` entry above beyond the
  stub. See audit recommendation #6.
