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
4. **3 stale-prompt drift cases caught.** T1.1 (retention sweep already shipped at `memory_service.rs:737`), T1.2 (quality-eval rot guard already shipped at `4b0a5ce`), and **Memory V2 step 6 — embeddings** (already shipped at `e135c2a`; full provider stack at `embeddings.rs` 912 lines + `hf_provider.rs` 407 lines + retention cascade at `memory_service.rs:587-589` + ADR-0002 + ADR-0007 + ADR-0003 default `bge-m3`). Repo beat prompt three times; agents correctly refused to redo. The pattern is conclusive: **the older HANDOFF_2026-05-18 status section is significantly stale**; verify against `git log` + the live code before treating any "pending" item as actually pending.
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
- Boundary lint green: 12 crates / 8 engines / 4 shared infra (will move to 13/9/4 once l5-files lands).
- All workspace `cargo test`s green.
- Desktop crate `cargo test --bin aether-desktop`: 306+ green (new sweep idempotency test added this session).
- Frontend `pnpm exec tsc --noEmit` clean; `pnpm exec vitest run` 261+ pass (new SettingsDrawer Autonomy tests added; persona-switcher tests pending wave-4 finish).

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

## What's actively in flight as of session-mid (Wave 4)

- Agent: **T1.3 l5-files skeleton** — second skeleton PR per §5.5 lock. Mirrors l5-browser exactly.
- Agent: **T2.4 persona switcher UI** — post-onboarding switch surface in SettingsDrawer or Trust drawer.

Both dispatched with explicit-paths `git add` rule. Disjoint paths.

## Wave 5+ queued (will dispatch when Wave 4 lands cleanly)

- **T2.5 Memory tab/drawer consolidation.** HANDOFF_2026-05-18 Risk D/E. Decide one surface, retire the other, migrate users. Frontend, doctrine §8 used-as-user gate.
- **First T1.3 implementation slice — `BrowserOpen` + `BrowserNavigate` capabilities** in `packages/l5-browser/`. Adds Playwright dep, `BrowserCapability` variants, and the additive entries on `aether_l5_policy::Capability`. Multi-layer; needs a cross-layer coordinator pass per CLAUDE.md §1.
- **First T1.3 implementation slice — `FilesEdit` + `FilesGrep`** in `packages/l5-files/`. Same shape, smaller blast radius (no subprocess).
- **`infra/persona-manifest/sign_manifest.py` end-to-end exercise.** Now that the real key exists, run the full sign → publish → verify roundtrip on a real manifest to lock the production path.
- **Doctrine §8 used-as-user verification on T2.3 + T2.4.** Live Tauri build → click through → confirm state persists → confirm chat behavior shifts when preset/persona changes.
- **GPU queue:** Aurora reference batch (Don-driven; not agent work).

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
