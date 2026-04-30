# Handoff — 2026-04-30 Autonomous Run

> **Live document.** Will be amended throughout the 12-hour autonomous run. Read this first; it supersedes earlier handoffs for any decision/state that disagrees.
>
> **Branch:** `dev` (pushed). Tip moves throughout the run; check `git log -1` for current.
> **Wallclock window:** Don gave a 12-hour autonomous mandate starting ~07:30 PT 2026-04-30.

---

## TL;DR — what changed in the last ~12 hours of session work

1. **5 of 5 Don-delegated decisions resolved** (1–5 from 2026-04-29 night → 2026-04-30 morning). All locked, audit-trail in place.
2. **T1.5 closed end-to-end.** Real Ed25519 release key generated, backed up, bundled-const swapped, install orchestrator parameterized on injected pk, all 306 desktop tests green.
3. **6 parallel-tracks tasks moved to DONE.** T4.4, T4.1, T2.1, T2.2, T2.3, T4.6 all shipped. T1.1 + T1.2 verified-already-shipped via stale-prompt audit (both flagged as blocked/available in the tracks doc, both actually done — patched the tracks doc).
4. **4 stale-prompt drift cases caught.** T1.1 retention sweep (already shipped at `memory_service.rs:737`), T1.2 quality-eval rot guard (already shipped at `4b0a5ce`), **Memory V2 step 6 — embeddings** (already shipped at `e135c2a`; full provider stack at `embeddings.rs` 912 lines + `hf_provider.rs` 407 lines + retention cascade at `memory_service.rs:587-589` + ADR-0002 + ADR-0007 + ADR-0003 default `bge-m3`), and **T2.5 memory tab/drawer consolidation** (already closed at Run 5, 2026-04-23 — the legacy `MemoryDrawer` was retired; header Memory button opens Trust drawer on the Memory tab; one canonical surface; per `App.tsx:427` comment). Repo beat prompt FOUR times; agents correctly refused to redo. The pattern is conclusive: **the older HANDOFF_2026-05-18 status section is significantly stale**; verify against `git log` + the live code before treating any "pending" item as actually pending. T1.1, T1.2, Memory V2 step 6, T2.5 — all four claimed pending in HANDOFF_2026-05-18; all four shipped weeks-to-months earlier.
5. **`tools/persona-reference-gen/` scaffolded per ADR-0015.** Avatar GPU pipeline Step 1 unblocked (Aurora kickoff is now `python tools/persona-reference-gen/__main__.py --persona aurora --batch <id>`).
6. **`packages/l5-browser/` skeleton landed** (T1.3 first slice). Re-landed cleanly after a multi-agent commit race required cleanup (b40b837 revert).
7. **Doctrine §5/§6/§7/§8 propagation complete** across `02_product_family.md`, `03_vision_and_thesis.md`, all roadmaps, all numbered specs (04, 05, 06, 07, 11, 12, 14, 16), all inbox docs. Plus `01_product_doctrine.md` "Aether Pro" heading flipped to "Companion."
8. **ADR-0016 mobile sync schema accepted (full).** Body + 10 OQs locked at recommended defaults.
9. **Cast-creator session (2026-04-28 night) artifacts preserved.** No regression.

## Lessons learned, applied immediately

### Multi-agent `git add -A` race

When two parallel agents both run `git add -A` (or `git add -u`) against a dirty working tree, one agent's commit can sweep up the other's files under the wrong commit message. This happened today between an l5-browser scaffold agent and a Companion-rename Tier 2 agent. The misattributed commit `b028a06` was reverted (`b40b837`), then both pieces re-landed cleanly as `4c6cb2b` (rename) and `1b8f3d4` (l5-browser).

**Rule for future parallel dispatches:** every agent prompt now includes `CRITICAL — never use git add -A or git add -u; stage with explicit paths only`. The lesson is baked into wave-4 dispatches and beyond.

### Stale-prompt drift recurs

The `feedback_stale_prompt_drift.md` rule fired twice today. Handoff documents claimed work was blocked or pending that the repo had already shipped (T1.1 retention sweep, T1.2 quality-eval rot guard, MemoryDomain reconciliation via ADR-0001). The verification pattern that worked: agent reads the live code first, refuses to redo when repo beats prompt, flags the doc-vs-repo gap. **`scripts/current_status.py` is authoritative; handoffs are advisory.**

---

## State as of latest commit

Run `python scripts/current_status.py` for the live state. Highlights as of session-mid:

- All 7 doc rot guards green (presence, vision, voice, quality, memory, policy, media-permissions).
- Boundary lint green: **13 crates / 9 engines / 4 shared infra** (l5-browser + l5-files skeletons + first impl slices landed).
- All workspace `cargo test`s green.
- Desktop crate `cargo test --bin aether-desktop`: **311 passed / 0 failed** (kill-mid-sweep idempotency test, reshaped bundled-key tests, 4 new browser_commands tests).
- Frontend `pnpm exec tsc --noEmit` clean; `pnpm exec vitest run` **268 passed / 24 files** (PersonaSection 7 cases + 3 doctrine-§8-bug-fix updates).
- l5-browser: 15 tests green with `--features playwright`. l5-files: 13 default + 19 with `--features std-fs`.

## Decisions locked this run

| # | Decision | ADR / doc | Status |
|---|---|---|---|
| MemoryDomain reconciliation | Option 3 — kernel stub retired, shell taxonomy canonical | ADR-0001 (Accepted 2026-04-23) | Stale-prompt audit flipped Risk A from "open" to "closed since 2026-04-23" |
| ADR-0016 mobile sync — body | Two-master + per-domain conflict rules | ADR-0016 §§1-9 | Accepted 2026-04-29 |
| ADR-0016 mobile sync — 10 OQs | All locked at recommended defaults | ADR-0016 §10 | Accepted 2026-04-30 |
| T1.3 sub-decisions (6) | Playwright / explicit allowlist / Power User in T1.3 / no creds / two skeleton PRs | T1.3 proposal §7 | Approved 2026-04-30 |
| Doctrine §"Must-own layers" heading | "Aether Pro onward" → unqualified; 1 body line and 1 cross-page reference flipped | `01_product_doctrine.md` | Edit landed cb15c2b |
| `%APPDATA%/Aether/` paths | STAY `Aether` (Tauri identifier-derived; internal) | T4.3 task | Locked 2026-04-29 |
| Real release Ed25519 key | Generated, backed up to `I:/IsabelleData/_keys/...`, bundled in main.rs | T1.5 commit `91f23a9` | Closed |
| `aether-l5-browser` crate exists | Engine sibling, no deps in skeleton | T1.3 §2.1 | Skeleton landed at `1b8f3d4` |

## Carry-forward open items

### Reserved for Don
- **Backup the release secret key.** The keygen output lives at `C:\Users\dbhav\.aether\release-key\aether-release-ed25519.sk` (32 bytes, raw). Backed up to `I:/IsabelleData/_keys/aether-release-key-backup-2026-04-30/`. **You should make at least one more copy (USB or off-machine).** If lost, every signed manifest from now on becomes unverifiable AND the deployed binaries can never accept new manifests without a const-swap follow-up.
- **`01_product_doctrine.md`** — read the §"Must-own layers" + §"Desktop framework doctrine" edits I made under your delegation. If you want different wording, push a follow-up.
- **`tools/persona-reference-gen/`** — Aurora reference batch is unblocked. When you have the budget for the curation cycle, run:
  - `python tools/persona-reference-gen/__main__.py --persona aurora --batch 2026-04-30a --notes "Aurora kickoff"`
  - Then `python tools/persona-reference-gen/curate.py --persona aurora --batch 2026-04-30a` for the keep/reject pass.
- **`tools/persona-reference-gen/` doctrine §8 visual self-test** — currently stubbed (no multimodal-vision pass). Worth wiring before Don sees candidates for any future cast member.
- **GPU queue Aurora pipeline** — `planning/plans/gpu_queue.md` still says "initial state — awaits Aurora pipeline kickoff." Run the reference batch to flip it to active.

### Cross-reference debt (small, fixable later)
- T1.3 proposal cites "ADR-0009 (policy decisions)" but ADR-0009 is `retrieval-augmented-utterance-audit-reach`. There is no policy-doctrine ADR by that number. Either add one or correct the cite in the proposal. Flagged 2026-04-30.

## Waves through 8 — completed across the autonomous run

**Wave 4**: T1.3 l5-files skeleton (`f0f8e70`), T2.4 persona switcher UI (`776f9e0` / `614fdf5` / `05cdf88`). Multi-agent commit race caught + cleaned up (revert `b40b837`, re-land `4c6cb2b` + `1b8f3d4`). Lesson: **explicit-paths `git add` insufficient under agent concurrency; worktree isolation is the durable fix**.

**Wave 5**: Memory V2 step 6 audit (stale-confirm — already shipped at `e135c2a`, no commits), sign_manifest end-to-end exercise (runbook at `999f40b`, real-key roundtrip PASS, T1.5 fully closed).

**Wave 6** (worktree-isolated): docs/AC-STYLE.md Gap #6 (`70786a2`), planning/plans/T1.3_approval_scope_design.md (`3a858a8`), docs/RTM.md Gap #5 (`bbe0d5c`), GLOSSARY follow-ups (`27a7307`), OPEN_QUESTIONS doctrine §6 cleanup (`3bd02a5`, `5e66344`), RTM PD2/PD3 stale correction (`ee54b04`), tombstones on 02_oss_preview_alignment_map + banner refresh on 01_pro_phase_crosswalk + 00_ORCHESTRATION_MAP (`6ce0fed`, `2061882`), GLOSSARY/lint-private-asset-leak doctrine §6 cleanup (`0dcb9b3`).

**Wave 7** (worktree-isolated): T1.3 first impl slice — `aether-l5-browser` with `BrowserExecutor` async trait + types + capability map + `PlaywrightExecutor` stub (`ca38a5a`..`6dadb2a`+`1b22781`, 7 atomic commits). NFR.md doctrine §6 cleanup (`84035b6`). Doctrine §8 used-as-user verify on T2.3 + T2.4 in isolated worktree — **3 real bugs surfaced and fixed in foreground (`7ccc978`)**: persona-switch a11y label, Loading-stuck-after-error, drawer-wide error visibility.

**Wave 8** (worktree-isolated): T1.3 first impl slice — `aether-l5-files` with `FilesExecutor` trait + types + `ScopeAllowlist` + capability map + `StdFsExecutor` stub (`3293844`..`f4fce68`, 6 atomic commits). T1.3 Tauri command surface wiring `BrowserExecutor` end-to-end through L5 PolicyEngine (`f8c22d4`..`54776ef`, 4 atomic commits, +4 desktop tests).

**Wave 9** (worktree-isolated): real Playwright Node-subprocess driver replacing the stub — `PlaywrightExecutor` now spawns `node packages/l5-browser/scripts/driver.mjs` with length-prefixed JSON-lines IPC (`2c056af`..`c2d9c4b`, 4 atomic commits, 13 driver tests under `--features playwright`). l5-files Tauri command surface wiring `FilesExecutor` end-to-end (`3ffe041`..`b1b0447`, 4 atomic commits cherry-picked from worktree branch, +4 desktop tests = **315 total**). Real regression caught + fixed in foreground (`e2690d5`): Playwright driver's `spawn()` now checks `Handle::try_current()` so synchronous test harnesses self-degrade to `BackendDisabled` instead of panicking.

## Final tallies (run total)

- **97 commits** on `origin/dev` between 2026-04-29 ~21:00 PT and 2026-04-30 ~mid-day PT.
- **5/5 Don-delegated decisions** resolved (1–5).
- **4 stale-prompt drift catches** (T1.1, T1.2, MemV2 step 6, T2.5) — all four claimed pending in HANDOFF_2026-05-18, all four shipped weeks-to-months earlier.
- **3 real bugs caught by doctrine §8 used-as-user verification** (a11y label, loading-stuck-after-error, drawer-wide error visibility). All three fixed in foreground.
- **1 real regression caught + fixed during the run** (Playwright `tokio::spawn` outside-of-runtime panic).
- **9 waves of parallel work**, with **worktree isolation** adopted at Wave 6 after a multi-agent commit race in Wave 4.
- Workspace: 13 crates / 9 engines / 4 shared infra. l5-browser + l5-files now live with first impl slices, real-key bundled, Tauri commands wired, Playwright driver real (gracefully degrades when Node/playwright absent).
- Tests: cargo desktop **315 passed**, vitest **268 passed / 24 files**, l5-browser **13 with `--features playwright`**, l5-files **13 default + 19 with `--features std-fs`**, all 7 rot guards green.

## Wave 9+ queued (next session work)

- **Real Playwright Node-subprocess driver inside `playwright_stub.rs`.** Graduates the stub to a real backend — spawn long-lived Node child running the Playwright driver script, length-prefixed JSON over stdio, `HashMap<SessionId, BrowserContext>` session tracking, typed `BrowserExecError` mapping. Tauri wiring landed today is fully ready; only the `state.rs::build` constructor flips. Single-layer (`packages/l5-browser/`).
- **First T1.3 Tauri wiring for `aether-l5-files`** — mirror the `browser_commands.rs` shape for `files_*` Tauri commands. Same one-layer-per-session pattern; reuse the L5 gate helper from `browser_commands::gate()`.
- **L5-gated approval routing for browser/files commands.** Today `Decision::Ask` returns a string error; the next slice routes through the existing pending-approval registry that `submit_turn` uses (reference: `apps/desktop/src-tauri/src/commands.rs::submit_turn`).
- **T1.3 §2.3 ApprovalScope implementation** — apply the ApprovalScope design doc (`3a858a8`) to the live `aether-l5-policy` engine. Single-layer in l5-policy.
- **GPU queue:** Aurora reference batch (Don-driven; not agent work). `python tools/persona-reference-gen/__main__.py --persona aurora --batch 2026-04-30a` then `tools/persona-reference-gen/curate.py`.
- **L*_*_system_design.md doctrine §6 sweep** (T4.7 follow-up). Layer plan docs still reference OSS Preview / Pro split. Lower priority — these are author-focused, not load-bearing.
- **Spec gap #3** (forward-looking requirement IDs) — Don-reserved per HANDOFF_2026-05-18.

## Useful reference paths

- file:///C:/Users/dbhav/Projects/aether/scripts/current_status.py
- file:///C:/Users/dbhav/Projects/aether/aether/CLAUDE.md
- file:///C:/Users/dbhav/Projects/aether/planning/01_product_doctrine.md
- file:///C:/Users/dbhav/Projects/aether/planning/plans/parallel_software_tracks.md
- file:///C:/Users/dbhav/Projects/aether/planning/plans/gpu_queue.md
- file:///C:/Users/dbhav/Projects/aether/planning/plans/T1.3_browser_file_workflow_proposal.md
- file:///C:/Users/dbhav/Projects/aether/planning/plans/T2.1_mobile_sync_schema.md
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0001-memory-domain-reconciliation.md
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0012-persona-delivery-download-on-demand.md
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0013-avatar-runtime-architecture.md
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0014-per-persona-character-pipeline.md
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0015-reference-image-generation-inside-companion.md
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0016-mobile-sync-schema.md
- file:///C:/Users/dbhav/Projects/aether/T1.5_KEYGEN_DONE_REAL_KEY_SWAP_DEFERRED.md (now CLOSED, status note)
- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-29_FULL_SESSION_REPORT.md

---

*This document amends as the autonomous run continues. Latest tip: see `git log -1`.*
