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
**Status:** DONE — verified shipped in `apps/desktop/src-tauri/src/memory_service.rs::run_retention_sweep` + `main.rs::RETENTION_SWEEP_INTERVAL_MS` (boot + hourly tick) + `packages/l2-memory/src/sqlite_session.rs::prune_before`. Seven sweep tests + 75 l2-memory tests + lint-memory-doc all green. ADR-0001 already locked the `MemoryDomain` reconciliation on 2026-04-23 (Option 3); HANDOFF_2026-05-18 Risk A was stale-prompt drift. Repo beats prompt per Decision #32.
**Layer:** L2.
**Self-test gate:** unit + integration tests on retention behavior across all six domains — all passing.
**Notes:** No new work needed. Optional follow-up: belt-and-suspenders explicit "kill mid-sweep + restart" test (current coverage is implicit via SQL-row atomicity + next-sweep idempotency).

### T1.2 — Quality-Eval Tier 2B (rot guard + doc flip)
**Status:** DONE — `tools/lint-quality-doc/check.py` shipped in commit `4b0a5ce` (60 anchors, 19 files); `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` flipped to "Current as of 2026-04-23". The earlier "BLOCKED" claim in handoffs was stale.
**Scope (historical):** `tools/lint-quality-doc/` mirroring `tools/lint-presence-doc/check.py`. Flip `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` from "Design-only" → "Current". Reconcile any drift surfaced by anchor seeding.
**Self-test gate:** rot guard runs green; doc anchors all resolve.
**Notes:** Mechanical work. Closes Risk G from HANDOFF_2026-05-18.

### T1.3 — Browser + file workflow tools (Pro Phase 4)
**Status:** Greenfield. Coordinator-gated (new module).
**Scope:** L5-gated browser automation + file CRUD primitives. Action approval framework + audit replay surfaces.
**Self-test gate (frontend portion):** any UI for approval flows must be exercised end-to-end as a user — click through approval modal, deny path, audit log review.
**Notes:** Pro doctrine requires this — without it, Companion is "chat with permissions," not the agent doctrine §3 promises.

### T1.4 — L3 Presence runtime renderer scaffold
**Status:** DONE — shipped 2026-04-29 in commit `2035822` ("feat(l3-presence): runtime renderer trait + opaque handle types (ADR-0013 scaffold)"). `packages/l3-presence/src/runtime.rs` ships the `Renderer` trait, `LogStubRenderer` (no-op log-only impl), `MotionClipLibraryHandle` + `MotionClipId` + `AudioStreamHandle` opaque input-contract types, `RendererEvent` + `RENDERER_EVENT_LOG_CAP`, `BoxedRendererController`, and `RenderingPresenceController`. All exported from `lib.rs`. Stale-prompt drift catch — repo beat prompt (Decision #32). Patched 2026-04-30 during the autonomous run continuation.
**Scope (historical):** Stub the runtime renderer's input contract (motion clip library + L3 events + TTS audio stream) per ADR-0013. Wire L3's existing state machine to a no-op rendering surface that logs state transitions. When motion library lands from GPU pipeline, swap log-stub for actual playback.
**Self-test gate:** L3 state transitions visibly logged in the surface; presence-bridge tests still green.
**Notes:** When the motion library lands from the GPU pipeline (per ADR-0014 Step 5), implement a real `Renderer` (replacing `LogStubRenderer`) and swap the controller's renderer field. The trait + handle types + event log are stable.

### T1.5 — Persona pack release infrastructure (Tier-2 closure)
**Status:** DONE — closed 2026-04-30 in commit `91f23a9`. Real Ed25519 key generated (`~/.aether/release-key/`, backed up to `I:/IsabelleData/_keys/`); bundled `RELEASE_PUBLIC_KEY_B64` swapped; install orchestrator parameterized on `pk`; tests use the L6 fixture pk explicitly. Desktop test suite: 306/306 green.
**Scope (historical):** Ed25519 fixture key → real key swap. Update bundled cross-language fixture verifier test.
**Self-test gate:** desktop crate test suite all green; bundled-key tests verify shape + that the const ≠ fixture pk.
**Notes:** Key-rotation runbook deferred — when needed, run `keygen.py --force` and repeat the const-swap commit shape.

---

## Tier 2 — Long-arc software (high value, no GPU)

### T2.1 — Mobile companion architecture + sync schema
**Status:** DONE — design draft committed 2026-04-29 (`39439b6` — `planning/plans/T2.1_mobile_sync_schema.md`). ADR-0016 (mobile sync schema) body Accepted 2026-04-29; all 10 OQs locked at recommended defaults 2026-04-30. Two-master + per-domain conflict rules; revoke-precedence with otherwise LWW by Lamport on `policy_grants`. Stale-prompt drift catch — patched 2026-04-30.
**Scope (historical):** Sync schema decisions, event-log shape, conflict resolution, offline behavior. Lock now to avoid retrofit pain later.
**Self-test gate:** schema validation tests; conflict-resolution unit tests on synthetic event streams. Implementation tests follow when mobile companion app builds against the locked schema.
**Notes:** Decisions are now load-bearing for the policy_grants sync filter that ApprovalScope::OncePerSession assumes (see ADR-0016 §"What does NOT sync" + the T1.3 ApprovalScope design §7).

### T2.2 — Red-team scenario harness
**Status:** DONE — shipped 2026-04-30 across `2706395` (harness scaffold + CLI), `f05cc8f` (scenarios + adversarial canaries + unit tests), `d798d89` (README + `tools/lint-redteam-coverage/` guard for ≥2 scenarios per category). Integrates with Quality-Eval V1 capture/replay. Stale-prompt drift catch — patched 2026-04-30.
**Scope (historical):** Prompt attacks, memory poisoning, browser misuse, permission bypass, exfiltration test scenarios. Replayable. Integrates with Quality-Eval V1 capture/replay.
**Self-test gate:** each scenario runs deterministically; failure modes log clearly. Coverage lint enforces ≥2 scenarios per category.

### T2.3 — Autonomy preset picker UI (Tier 2C)
**Status:** DONE — `apps/desktop/src/components/PresetPicker.tsx` lives in the desktop crate, wired into `App.tsx` + `SettingsDrawer.tsx`. Backend (`AppState::apply_preset`) covers Observer / Assistant / Operator / Power User / Custom. Stale-prompt drift catch — patched 2026-04-30.
**Scope (historical):** UI surface for autonomy presets (Observer / Assistant / Operator / Power User / Custom per `planning/12_permissions_autonomy.md`).
**Self-test gate (doctrine §8):** agent uses the picker as a user — selects each preset, confirms persisted state, confirms downstream behavior changes (e.g., approval modal appears for Ask actions in Observer, suppressed in Operator). Used-as-user verification owed; banner here flags it.

### T2.4 — Persona picker UI (Tier 2D)
**Status:** DONE — shipped 2026-04-30 as `apps/desktop/src/components/PersonaSection.tsx` with `PersonaSection.test.tsx` (7 vitest cases) mounted at the top of `SettingsDrawer.tsx` above Media. Three commits: `776f9e0` (component + installPersona/personaManifestUrl api wrappers), `614fdf5` (SettingsDrawer mount), `05cdf88` (vitest coverage). Coordinates with ADR-0012 install-on-demand flow. Stale-prompt drift catch — patched 2026-04-30.
**Scope (historical):** Settings surface for persona switch. Coordinates with ADR-0012 install/uninstall flow.
**Self-test gate (doctrine §8):** agent uses the picker as a user — switch personas, confirm voice + name + identity update across UI, confirm memory continuity per ADR-0001. Doctrine §8 used-as-user verification owed for cross-persona voice/name/identity propagation; banner here flags it.

### T2.5 — Memory tab / MemoryDrawer consolidation (HANDOFF_2026-05-18 Risk D/E)
**Status:** DONE — closed at Run 5 (2026-04-23). Per `apps/desktop/src/App.tsx:427`: "the legacy `MemoryDrawer` was retired now that Memory V2 is closed. The header Memory button opens the Trust drawer on the Memory tab — one canonical surface for 'what does Companion remember about me'." HANDOFF_2026-05-18 Risk D/E was stale-prompt drift.
**Scope (historical):** Decide one surface, remove the other, migrate users across.
**Self-test gate (doctrine §8) — historical:** memory surface used-as-user via Trust drawer's Memory tab.

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
**Status:** DONE — 7 doc rot guards live and green per `scripts/current_status.py`: `tools/lint-presence-doc/`, `tools/lint-vision-doc/`, `tools/lint-voice-doc/`, `tools/lint-quality-doc/` (4b0a5ce), `tools/lint-memory-doc/`, `tools/lint-policy-doc/`, `tools/lint-media-permissions-doc/`. Plus `tools/lint-redteam-coverage/` for T2.2 scenario coverage. Stale-prompt patched 2026-04-30.
**Scope (historical):** Mirror existing `tools/lint-vision-doc/`, `tools/lint-voice-doc/`, `tools/lint-presence-doc/` patterns for the remaining critical arch docs.

### T4.2 — Companion rename Tier 1 — text-only pass
Per Task #9 in the active plan. `Aether` product references → `Companion` in `planning/`, `docs/`, `README`, code comments. Preserve internal identifiers.
**Self-test gate:** grep for residual `Aether` product references; confirm internal `aether` codename references untouched.

### T4.3 — Companion rename Tier 2 — UI strings, persona YAMLs, glossary
Per Task #10. Audit + finish what the 2026-04-28 5-commit rename missed.
**Self-test gate (doctrine §8):** agent runs the built app as a user; confirms no `Aether` appears anywhere user-visible.

### T4.4 — Doctrine refresh propagation audit
**Status:** DONE — propagation completed per HANDOFF_2026-04-30 §7: doctrine §5/§6/§7/§8 reflected consistently across `02_product_family.md`, `03_vision_and_thesis.md`, all roadmaps, all numbered specs (04, 05, 06, 07, 11, 12, 14, 16), all inbox docs. Plus `01_product_doctrine.md` "Aether Pro" heading flipped to "Companion." A residual banner-only sweep for the 6 `L*_system_design.md` files landed 2026-04-30 as part of T4.7. Stale-prompt patched 2026-04-30.
**Scope (historical):** Confirm doctrine §5 / §6 / §7 / §8 (added 2026-05-18) are reflected consistently in `02_product_family.md`, `03_vision_and_thesis.md`, roadmaps, and inbox docs.

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
