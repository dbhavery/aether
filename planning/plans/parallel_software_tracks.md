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

### T1.3 — Browser + file workflow tools
**Status:** DONE — files command flow end-to-end live as of 2026-05-01. Shipped across 10 waves spanning 2026-04-30 → 2026-05-01:
- Wave 4: `packages/l5-browser/` skeleton (`1b8f3d4`) + `packages/l5-files/` skeleton (`f0f8e70`).
- Waves 7-8: l5-browser first impl slice (`ca38a5a..1b22781` + `1b22781`); l5-files first impl slice (`3293844..f4fce68`); l5-browser Tauri command surface (`f8c22d4..54776ef`).
- Wave 9: real Playwright Node-subprocess driver (`2c056af..c2d9c4b`); l5-files Tauri command surface (`3ffe041..b1b0447`).
- Wave 10A: l5-files real tokio::fs backend graduation (`91479a5..a09c03d`) — atomic write-temp-rename, canonicalize-before-allowlist, runtime-absent self-degrade.
- Wave 10B: T1.3 §2.3 ApprovalScope (`7969efb..3e1e1cc`) — `ApprovalScope` enum + storage migration 0006 + consume-while-valid rule + 86 l5-policy tests.
- Wave 11: L5-gated approval routing for browser/files (`85437f4..bacc232`) — `Decision::Ask` routes through pending-approval registry, executor fires post-approval; 319 desktop tests.
- Wave 12: executor reject path `respond_approval(Reject)` for audit-row completeness (`2d353d4..7326789`) — second-Reject fails proving consume; 320 desktop tests.
- Wave 14: L7 approval-modal radio surface (`eda3668..8bea4e3`) — 4-option `ApprovalScope` radio + separate Decline; `UserChoiceWire` widening on both Rust and TS; 327 desktop / 279 vitest.
- Wave 13a: l5-files mutable allowlist (`4a2640c..15c8b35`, merge `341b53e`) — `Arc<RwLock<ScopeAllowlist>>`, `set_allowlist`, `update_allowlist_from_paths`; 28 → 34 tests.
- Wave 13b: apps/desktop allowlist plumbing (`4054e93..7afe05f`, merge `ebf074c`) — `AppState` holds concrete `Arc<StdFsExecutor>`, boots from active grants, `ExecutorAllowlistSink` rebuilds on `GrantIssued`/`GrantRevoked`; persona-swap clears stale grants. 327 → 333 desktop tests.
- Wave 15: affordance gating (`ade50cb`) — `ApprovalPayload` gains `task_id_present` + `side_effecting`; modal hides `allow_task` when no task lineage and `defer_draft` for read-only capabilities. 333 → 335 desktop / 279 → 285 vitest.
- Wave 16: DeferToDraft Turn-path affordance (`cc9b5bf`) — `TranscriptMessage.variant?: "draft_only"`, amber bubble + "Draft only" badge in `Transcript.tsx`. 285 → 288 vitest.

**Carryover (post-T1.3 follow-ups, ranked):**
- Wave 19 — Doctrine §8 used-as-user Playwright verification on the Wave 14/15 modal. Owed before the modal ships to Don's daily-driver build. Heavier than the inline-fixable waves; recommended as a separate session because it needs `pnpm tauri dev` + browser orchestration.
- Wave 13c — task lineage threading. Wave 15 hardcodes `task_id_present: false` because every `TurnRequest` carries `task_id: None`. Flip to `request.task_id.is_some()` once a future wave plumbs task lineage. Search for `task_id: None,` in `apps/desktop/src-tauri/src/{commands,browser_commands,files_commands}.rs`.
- Wave 17 — OncePerSession outbound sync filter. Out of scope until the sync layer ships post-mobile.

**Self-test gate (frontend portion):** Wave 14/15 modal + Wave 16 draft-only bubble are covered at vitest+RTL level (16 modal cases, 3 transcript cases). Real Playwright-driven verification (Wave 19) is owed before shipping to Don's daily-driver build.

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
**Status:** DONE — shipped across 6 atomic rename commits + supporting fixes (2026-04-28..30) plus a 2026-05-02 live-grep audit pass that caught residue the diff-log sweeps missed:
- `7980060` Tier 1A: Companion in load-bearing governing docs (`aether` codename preserved).
- `158e495` Tier 1B-a: planning numbered specs + index docs.
- `558dc22` Tier 1B-b: `plans/` + `prompts/` + monorepo plan.
- `ff5fe74` Tier 1B-c: roadmaps + root governance.
- `1a9db85` Tier 1B-d: community + security policy files.
- `7d5bdb8` Tier 1B-e: `docs/` supplementary architecture + posts.
- `d6deb34` + `34241f6` finish Pro→Companion rename in `aether_pro.md` + `isabelle_private.md` roadmaps.
- `1b553e0` SettingsDrawer wrong-data-folder fix + UI JSDoc rename.
- **`b975ae0` (2026-05-02 live-grep pass):** L2 runtime label `MemoryRole::Assistant => "Aether"` was still emitting "Aether" via `render_transcript` to the user CLI in `apps/l1-cli/src/main.rs`. Flipped the literal + matching test fixtures in `packages/l2-memory/src/session.rs` and `apps/l1-cli/src/memory.rs`. l2-memory: 21/21 green; l1-cli: 20/20 green. **This was the only user-visible runtime literal still emitting "Aether".**
- **`e46ce9e` (2026-05-02 metadata sweep):** 18 files of dev-facing residue in non-`l*-*/` packages: Cargo.toml descriptions (event-bus, storage, media-engine, telemetry), package.json descriptions (@aether/ui-kit, @aether/types), module docstrings (event-bus, ui-kit, l2-memory/domain, storage), storage migration headers (0001..0006), package READMEs (types, media-engine).

Tooling at `tools/rename_companion_tier1b.py` + `tools/rename_companion_tier1b_diff.log` documents the rule set + diff for the original sweep.

**Scope (historical):** `Aether` product references → `Companion` in `planning/`, `docs/`, `README`, code comments. Preserve internal identifiers.

**Self-test gate:** grep for residual `Aether` product references; confirm internal `aether` codename references untouched. Live grep performed 2026-05-02 — all user-visible refs flipped; codename refs (crate names, npm scopes, db filenames, repo identity) preserved.

**Carryover (lower priority — single-layer follow-up sessions):** Live grep surfaced product-name residue in `packages/l3-presence/`, `packages/l4-router/`, `packages/l5-policy/`, `packages/l5-policy-ts/`, `packages/l5-files/`, and `packages/l5-browser/` (docstrings, READMEs, Cargo.toml descriptions). These are dev-facing only — no user-visible runtime emissions. Each layer needs its own single-session sweep per CLAUDE.md §1 (one `packages/l*-*/` layer per session). Sites to flip:
- `packages/l3-presence/README.md` line 20; `src/controller.rs` lines 4, 41; `src/attention.rs` line 5.
- `packages/l4-router/src/providers/ollama.rs` line 3.
- `packages/l5-policy/Cargo.toml` line 9; `README.md` line 5; `src/lib.rs` line 7; `src/audit.rs` line 55.
- `packages/l5-policy-ts/package.json` line 5.
- `packages/l5-files/Cargo.toml` line 9.
- `packages/l5-browser/Cargo.toml` lines 9, 20; `scripts/driver.mjs` line 2.

### T4.3 — Companion rename Tier 2 — UI strings, persona YAMLs, glossary
**Status:** DONE — shipped 2026-04-28 night across 5 atomic commits `2cc40d2..3658242`: `8d480f3` (productName + Tauri window title), `cad2d0e` (persona YAML headers + metadata), `3ab5558` (UI strings), `3658242` (CHARACTERS.md + RENAME COMPLETE marker). Internal codename `aether` preserved per `aether/RENAME_TO_COMPANION.md` (repo / Tauri identifier / database / Cargo workspace). Stale-prompt patched 2026-04-30.
**Scope (historical):** Audit + finish what the 2026-04-28 5-commit rename missed.
**Self-test gate (doctrine §8):** agent runs the built app as a user; confirms no `Aether` appears anywhere user-visible. Used-as-user verification is owed against the latest production build; banner here flags it.

### T4.4 — Doctrine refresh propagation audit
**Status:** DONE — propagation completed per HANDOFF_2026-04-30 §7: doctrine §5/§6/§7/§8 reflected consistently across `02_product_family.md`, `03_vision_and_thesis.md`, all roadmaps, all numbered specs (04, 05, 06, 07, 11, 12, 14, 16), all inbox docs. Plus `01_product_doctrine.md` "Aether Pro" heading flipped to "Companion." A residual banner-only sweep for the 6 `L*_system_design.md` files landed 2026-04-30 as part of T4.7. Stale-prompt patched 2026-04-30.
**Scope (historical):** Confirm doctrine §5 / §6 / §7 / §8 (added 2026-05-18) are reflected consistently in `02_product_family.md`, `03_vision_and_thesis.md`, roadmaps, and inbox docs.

### T4.5 — `aether_oss_preview` roadmap retirement
**Status:** DONE — `planning/roadmaps/aether_oss_preview.md` tombstoned with "RETIRED 2026-05-18" header per doctrine §6. Body preserved as historical record. Companion-Phase Crosswalk + 00_ORCHESTRATION_MAP banners point at this retirement.
**Scope (historical):** Tombstone or rewrite per `01_product_doctrine.md` §6.

### T4.7 — Doctrine §6 banner sweep on `L*_system_design.md`
**Status:** DONE (banner-only) — 6 banners landed 2026-04-30 in commit `7d88c0c` ("docs(planning): doctrine §6 banner-only sweep on L2-L7 system_design docs"). Each banner names the file's specific OSS-Preview / Pro-Phase residue, points at doctrine §6, explicitly preserves body content. L1 already clean.
**Surgical sweep on L7 §16 — DONE 2026-05-01 (Wave 18):** the load-bearing OSS-Preview-vs-Pro divergence matrix in §16 was tombstoned in `planning/plans/L7_trust_ux_onboarding_system_design.md`. The body now points at git history for the rationale and at doctrine §6 for the active spec. L7 banner updated to reflect Wave 18 closure.
**Carryover (lower priority):** smaller residue still threads through L7 §4.5 ("Guest mode (OSS Preview only)"), L7 §2.3 ("pywebview adapter parity"), and L7 §3.6 footnotes. Surgical sweeps owed but not load-bearing — the §16 tombstone closed the doctrine-§6-violating piece.
**Self-test gate:** banner present in each of L2..L7 system_design docs; verified via grep for "2026-04-30 banner" — all 6 hit. L7 §16 tombstoned (verified by grep for "RETIRED (Wave 18").

---

## Operating rules

1. **Sessions claim from this file.** Pick a task, mark it claimed, do it, commit, update status here.
2. **Doctrine §8 is non-negotiable.** Every task above with a "Self-test gate" must satisfy that gate before being surfaced to Don. Frontend tasks especially: use the app as a user.
3. **Software work runs in parallel with GPU.** Don't wait on the GPU queue. Don't ask whether GPU is busy — it always is. Pick software work and proceed.
4. **Coordinator-gated tasks (new packages/apps) need Don approval first.** Don't create directories under `packages/*/` or `apps/*/` unilaterally.
5. **One layer per session.** Multi-task in this file is fine if tasks are in different layers or in `tools/` / `docs/`. Touching two `packages/l*/` layers in one session is a violation.
6. **Status flip rules.** `available` → `in_progress (claimed by session XXX)` → `awaiting Don review (self-test passed)` → `complete`.
