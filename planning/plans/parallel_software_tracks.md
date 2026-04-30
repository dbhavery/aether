# Parallel Software Tracks — Claimable Work That Doesn't Wait on GPU

> **Operating model.** GPU runs `gpu_queue.md` jobs sequentially, near 100% utilization. This file lists software/integration work that runs in **parallel** on CPU, claimable by sessions while the GPU bakes. Sessions never wait on the GPU queue — they pick from this list.
>
> **Created:** 2026-05-18 — under doctrine §6 (single-product, ships when complete) and the GPU-saturation operating model.

---

## Doctrine reminders for every task in this file

- **Doctrine §8 — Self-test before Don review.**
  - Frontend tasks: agent uses the frontend **as a user** (browser/Tauri automation, click through, fill forms, observe state) before claiming ready-for-review. Diff-only or unit-test-only is **not** sufficient.
  - Visual artifacts: agent runs multimodal vision self-test against acceptance criteria before surfacing.
- **CLAUDE.md §3 — package creation is coordinator-gated.** New `packages/*/` or `apps/*/` requires Don approval first.
- **CLAUDE.md §1 — one layer per session.** A session touches at most one `packages/l*-*/` layer.
- **`HANDOFF_2026-05-18` constraints still apply** until superseded.

---

## Tier 1 — Closes moat layers (high leverage, no GPU)

### T1.1 — Memory V2 step 5 (retention sweep)
**Status:** BLOCKED on Don's `MemoryDomain` enum reconciliation decision (HANDOFF_2026-05-18 Risk A — three options documented).
**Layer:** L2.
**Self-test gate:** unit + integration tests on retention behavior across all six domains.
**Notes:** Cannot start until Don picks reconciliation option. Highest-priority unblock.

### T1.2 — Quality-Eval Tier 2B (rot guard + doc flip)
**Status:** Available now.
**Scope:** `tools/lint-quality-doc/` mirroring `tools/lint-presence-doc/check.py`. Flip `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` from "Design-only" → "Current as of 2026-05-18". Reconcile any drift surfaced by anchor seeding.
**Self-test gate:** rot guard runs green; doc anchors all resolve.
**Notes:** Mechanical work. Closes Risk G from HANDOFF_2026-05-18.

### T1.3 — Browser + file workflow tools (Pro Phase 4)
**Status:** Greenfield. Coordinator-gated (new module).
**Scope:** L5-gated browser automation + file CRUD primitives. Action approval framework + audit replay surfaces.
**Self-test gate (frontend portion):** any UI for approval flows must be exercised end-to-end as a user — click through approval modal, deny path, audit log review.
**Notes:** Pro doctrine requires this — without it, Companion is "chat with permissions," not the agent doctrine §3 promises.

### T1.4 — L3 Presence runtime renderer scaffold
**Status:** Available — Presence V1 is DONE rot-guarded; renderer is additive.
**Scope:** Stub the runtime renderer's input contract (motion clip library + L3 events + TTS audio stream) per ADR-0013. Wire L3's existing state machine to a no-op rendering surface that logs state transitions. When motion library lands from GPU pipeline, swap log-stub for actual playback.
**Self-test gate:** L3 state transitions visibly logged in the surface; presence-bridge tests still green.
**Notes:** Lets the runtime side advance in parallel with the GPU asset side.

### T1.5 — Persona pack release infrastructure (Tier-2 closure)
**Status:** Largely done per `48f3765` (Tier-2 install — HTTP fetch + install_persona Tauri command landed). Open: real-key swap of `RELEASE_PUBLIC_KEY_B64` once Don runs `keygen.py`.
**Scope:** Ed25519 fixture key → real key swap. Update bundled cross-language fixture verifier test. Document key-rotation runbook.
**Self-test gate:** install Tier-2 pack via Tauri command end-to-end on Don's actual install; verify signature passes against real key.
**Notes:** Don-reserved on key generation itself.

---

## Tier 2 — Long-arc software (high value, no GPU)

### T2.1 — Mobile companion architecture + sync schema
**Status:** Greenfield. Design-only — no app yet.
**Scope:** Sync schema decisions, event-log shape, conflict resolution, offline behavior. Lock now to avoid retrofit pain later.
**Self-test gate:** schema validation tests; conflict-resolution unit tests on synthetic event streams.
**Notes:** Decisions made now lock you in. Critical to do **before** Pro P4 tools work commits to a single-device shape.

### T2.2 — Red-team scenario harness
**Status:** Greenfield. Audit chain exists; scenarios don't.
**Scope:** Prompt attacks, memory poisoning, browser misuse, permission bypass, exfiltration test scenarios. Replayable. Integrates with Quality-Eval V1 capture/replay.
**Self-test gate:** each scenario runs deterministically; failure modes log clearly.

### T2.3 — Autonomy preset picker UI (Tier 2C)
**Status:** Backend ready (`AppState::apply_preset`). UI missing.
**Scope:** UI surface for autonomy presets (Observer / Assistant / Operator / Power User / Custom per `planning/12_permissions_autonomy.md`).
**Self-test gate (doctrine §8):** agent uses the picker as a user — selects each preset, confirms persisted state, confirms downstream behavior changes (e.g., approval modal appears for Ask actions in Observer, suppressed in Operator). Manual click-through, not just unit tests.

### T2.4 — Persona picker UI (Tier 2D)
**Status:** Wizard exists; switcher UI for post-onboarding persona swap pending.
**Scope:** Settings surface for persona switch. Coordinates with ADR-0012 install/uninstall flow.
**Self-test gate (doctrine §8):** agent uses the picker as a user — switch personas, confirm voice + name + identity update across UI, confirm memory continuity per ADR-0001.

### T2.5 — Memory tab / MemoryDrawer consolidation (HANDOFF_2026-05-18 Risk D/E)
**Status:** Both surfaces live; consolidation deferred.
**Scope:** Decide one surface, remove the other, migrate users across.
**Self-test gate (doctrine §8):** agent uses memory surface as a user — list, forget, edit, lane-level forget-all, approval flow on Facts/Artifacts. All paths exercised.

---

## Tier 3 — Finish-line work (defer until close to launch)

### T3.1 — First-run tutorial / interactive checklist
Per `planning/07_tutorial_help_system.md`. Modular, skippable, replayable.
**Self-test gate (doctrine §8):** agent runs the tutorial as a fresh user.

### T3.2 — Showcase / demo scenes
Per `planning/05_ux_principles.md` §3.5. Meet your assistant / choose your style / permissions tour / watch a task.
**Self-test gate (doctrine §8):** agent walks each scene as a user; confirms cinematic quality + clarity.

### T3.3 — Onboarding refinement
Polish pass on the wizard once persona picker (T2.4) is integrated.
**Self-test gate (doctrine §8):** full onboarding flow as a fresh user.

### T3.4 — Settings polish
Audit + cleanup pass on settings surface once autonomy picker (T2.3) and persona picker (T2.4) are in.
**Self-test gate (doctrine §8):** agent uses settings as a user — every panel, every toggle, every persistence path.

### T3.5 — Distribution packaging
Tauri bundle, signing, installer flows. Defer until everything else is locked.
**Self-test gate:** install on a clean Windows VM (or equivalent), run through onboarding to first conversation.

---

## Tier 4 — Hygiene / governance (cheap wins, do anytime)

### T4.1 — CI guard for arch-doc rot
Already-flagged risk. Cheap to build. Mirror existing `tools/lint-vision-doc/`, `tools/lint-voice-doc/`, `tools/lint-presence-doc/` patterns.

### T4.2 — Companion rename Tier 1 — text-only pass
Per Task #9 in the active plan. `Aether` product references → `Companion` in `planning/`, `docs/`, `README`, code comments. Preserve internal identifiers.
**Self-test gate:** grep for residual `Aether` product references; confirm internal `aether` codename references untouched.

### T4.3 — Companion rename Tier 2 — UI strings, persona YAMLs, glossary
Per Task #10. Audit + finish what the 2026-04-28 5-commit rename missed.
**Self-test gate (doctrine §8):** agent runs the built app as a user; confirms no `Aether` appears anywhere user-visible.

### T4.4 — Doctrine refresh propagation audit
Confirm doctrine §5 / §6 / §7 / §8 (added 2026-05-18) are reflected consistently in `02_product_family.md`, `03_vision_and_thesis.md`, roadmaps, and inbox docs.

### T4.5 — `aether_oss_preview` roadmap retirement
Per Task #8. Tombstone or rewrite per `01_product_doctrine.md` §6.

---

## Operating rules

1. **Sessions claim from this file.** Pick a task, mark it claimed, do it, commit, update status here.
2. **Doctrine §8 is non-negotiable.** Every task above with a "Self-test gate" must satisfy that gate before being surfaced to Don. Frontend tasks especially: use the app as a user.
3. **Software work runs in parallel with GPU.** Don't wait on the GPU queue. Don't ask whether GPU is busy — it always is. Pick software work and proceed.
4. **Coordinator-gated tasks (new packages/apps) need Don approval first.** Don't create directories under `packages/*/` or `apps/*/` unilaterally.
5. **One layer per session.** Multi-task in this file is fine if tasks are in different layers or in `tools/` / `docs/`. Touching two `packages/l*/` layers in one session is a violation.
6. **Status flip rules.** `available` → `in_progress (claimed by session XXX)` → `awaiting Don review (self-test passed)` → `complete`.
