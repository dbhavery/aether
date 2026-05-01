# Handoff — 2026-04-30 Autonomous Run Continuation

> **Purpose.** Successor to `HANDOFF_2026-04-30_AUTONOMOUS_RUN.md`. Records the second wave of the 12-hour autonomous mandate (mid-day → afternoon PT). Read **after** the parent handoff (`HANDOFF_2026-04-30_AUTONOMOUS_RUN.md`) for full context.
>
> **Branch:** `dev` (pushed). Tip at handoff write: `8bea4e3` (Wave 14 merge).
> **This session:** **26 commits** between parent handoff tip `be82563` and `8bea4e3`. **5 waves landed** (10A, 10B, 11, 12, 14) plus 1 doc sweep + 6 stale-prompt patch commits.

---

## TL;DR

End-to-end **ApprovalScope flow is now fully wired**, from the policy-crate enum to the L7 user-choice picker:

1. **Wave 10A** — `packages/l5-files/` `StdFsExecutor` graduated from `BackendDisabled` stub to real `tokio::fs` backend (atomic write-temp-rename, canonicalize-before-allowlist, runtime-absent self-degrade).
2. **Wave 10B** — `aether_l5_policy::ApprovalScope` enum + storage migration `0006_policy_grants_approval_scope.sql` + §4.2 consume-while-valid rule + 86 l5-policy tests + 10 struct-literal call-site sweep.
3. **Wave 11** — `Decision::Ask` from browser/files gates now routes through the same pending-approval registry that `submit_turn` uses. Pending registry widened to a sum (`PendingApproval::{Turn, Executor}`); `resolve_approval` now returns a tagged `ResolveApprovalReply { kind: "turn" | "executor", ... }`. Approve path issues a one-shot grant + replays the executor invocation.
4. **Wave 12** — Reject path on the executor flow now calls `policy.respond_approval(Reject)` for L5 audit-row completeness. `PendingApproval::Executor` now caches the live `ApprovalTicket`.
5. **Wave 14** — L7 approval modal surfaces the **4-option ApprovalScope radio** per T1.3 §2.3 design §5: `allow_once` / `allow_task` / `allow_session` / `defer_draft` + separate Deny button. `resolve_approval(ticket, UserChoiceWire)` widening on both Rust and TS sides. Engine receives the chosen `UserChoice` so `policy_grants` rows are written with the correct `ApprovalScope` (`PerAction` / `OncePerSession` / `OncePerTask`).

Plus **15 stale-prompt drift catches** in `parallel_software_tracks.md`. The doc is now an evidence-backed mirror of repo state for every Tier 1/2/4 entry. Tier 3 finish-line items left as-is per the doc's own "defer until close to launch" intent.

---

## Commits — chronological

### Wave 10A — `packages/l5-files/` real `tokio::fs` backend

- `91479a5` build(l5-files): add tokio dep + tempfile dev-dep behind std-fs feature
- `e28a293` feat(l5-files): graduate StdFsExecutor from stub to real tokio::fs backend
- `652d4aa` test(l5-files): integration tests for real tokio::fs backend
- `a09c03d` docs(l5-files): flip stub language to real backend in lib + README + executor

Tests: default 13 / `--features std-fs` 28. Boundary lint: 0 violations.

### Wave 10B — T1.3 `ApprovalScope`

- `7969efb` feat(l5-policy): add ApprovalScope enum + UserChoice mapping
- `b18115c` feat(l5-policy): thread ApprovalScope through PolicyDecisionEvent + GrantIssuedEvent
- `66ba14e` feat(l5-policy): add Grant.approval_scope field
- `c57dc0a` feat(l5-policy): add AuditRecordEvent.approval_scope + auto_approved_under_grant + AuditFilter.approval_scope
- `9aaa1df` build(storage): migration 0006 — policy_grants.approval_scope column
- `7f02280` feat(l5-policy): wire ApprovalScope through evaluate + respond_approval (§4.2 consume-while-valid)
- `3e1e1cc` test(l5-policy): ApprovalScope behavioral + round-trip + re-eval regression suite

Tests: 86 l5-policy / 409 workspace. Storage migration smoke-tested via `db.rs::run_pending_migrations`. 10 struct-literal call sites touched.

### Stale-prompt + docs commits (interleaved)

- `7d88c0c` docs(planning): doctrine §6 banner-only sweep on L2-L7 system_design docs (T4.7) — 6 banners, 1 atomic commit
- `0e16f0c` docs(planning): mark T1.4 L3 renderer scaffold DONE — stale-prompt drift catch
- `241503f` docs(planning): patch T2.1+T2.2+T2.3 stale statuses — flip to DONE with evidence
- `38bd21e` docs(planning): patch T4.1 + T4.4 stale statuses — flip to DONE with evidence
- `846baa9` docs(planning): mark T2.4 persona picker UI DONE — stale-prompt drift catch
- `725db75` docs(planning): patch T1.3 + T4.3 + T4.5 + add T4.7 — close session stale-prompt sweep
- `281000b` docs(planning): mark T4.2 Companion rename Tier 1 DONE — final stale-prompt sweep

### Wave 11 — Decision::Ask routing for browser/files

- `85437f4` fix(desktop): adapt StdFsExecutor::new() → ::default() after L5-files real-backend graduation **[Wave 10A regression caught + fixed]**
- `0b3d80c` feat(desktop): widen pending registry to PendingApproval sum + dispatch resolve_approval
- `7e015d1` feat(desktop): route Decision::Ask through pending registry for browser_*/files_* gates
- `0c57ec0` test(desktop): Wave 11 routing tests — Decision::Ask → executor replay end-to-end
- `bacc232` feat(desktop-ui): mirror ResolveApprovalReply tagged-enum on the TS wire

Tests: 315 → 319 desktop, vitest 268 / 24 files preserved.

### Wave 12 — executor reject `respond_approval` audit completeness

- `2d353d4` feat(desktop): cache live ApprovalTicket on PendingApproval::Executor (Wave 12 prep)
- `37aaef7` feat(desktop): wire respond_approval(Reject) on executor reject path (Wave 12)
- `7326789` Merge Wave 12 — executor reject audit completeness

Tests: 319 → 320 desktop. Load-bearing assertion: a *second* `respond_approval(Reject)` against the same cached ticket fails, proving the first Reject actually consumed the ticket from the engine's pending-tickets table.

### Wave 14 — L7 ApprovalScope modal radio

- `eda3668` feat(desktop): widen resolve_approval to UserChoiceWire (Wave 14 §5.3)
- `1531221` test(desktop): cover Wave 14 UserChoiceWire wire mapping + scope plumbing
- `1b08125` feat(desktop-ui): approval modal surfaces 4-option ApprovalScope radio (Wave 14)
- `b1a9603` test(desktop-ui): cover ApprovalModal Wave 14 radio surface
- `8bea4e3` Merge Wave 14 — L7 ApprovalScope modal radio

Tests: 320 → 327 desktop (+7 wire-mapping tests). vitest 268 → 279, 24 → 25 files (+11 modal tests). tsc clean.

---

## Lessons learned, applied this session

### Wave 10A regression: cross-layer ABI breakage on signature change

When `StdFsExecutor::new()` was rewritten to take a `ScopeAllowlist` argument, the desktop crate's call site (which passes no args) became an immediate build break. The Wave 11 agent caught it on its `cargo build` floor verification and fixed it preemptively in commit `85437f4` by switching the call to `::default()`.

**Rule for future cross-layer constructor changes:** when graduating a stub into a real backend with new constructor args, audit every call site in `apps/desktop/src-tauri/src/state.rs` (which holds the `Arc<dyn FilesExecutor>` etc.) in the SAME PR. If the slice is one-layer-bound and the call site lives in another layer, bake a `Default` impl into the new shape so the call site can stay on `::default()` until plumbed properly.

### Stale-prompt drift recurs at scale

`parallel_software_tracks.md` had **15 stale entries** at session start — every Tier 1, every Tier 2, two Tier 4 entries plus T4.2 (which had 6 commits proving completion). The pattern is now exhaustively validated: **the tracks doc lags the repo by weeks**. `python scripts/current_status.py` + `git log` are authoritative.

This session patched all 15 in 6 atomic commits with evidence pointers (commit shas + file paths). The doc is now honest. Future sessions should still run the `repo beats prompt` audit before treating any "Available" / "Greenfield" entry as actually pending.

### Worktree-isolation works; explicit-path commits still required

5 background agents dispatched across the session. None hit a multi-agent commit race (the failure mode that bit Wave 4 yesterday). Combined with `git commit -- <explicit paths>` discipline, the worktree-isolation pattern is durable. Adopt as default for every parallel dispatch.

### `git checkout -b X origin/Y` from a different CWD can target the wrong worktree

When merging worktree-branch commits back to `dev`, `git checkout -b temp-rebase-X origin/worktree-agent-Y` from the main checkout's CWD silently retargets the agent's worktree if that worktree is currently checked out at `worktree-agent-Y`. Result: the rebase happens "in" the agent's worktree, not the main checkout. Mitigation: always `cd /c/Users/dbhav/Projects/aether && git ...` before merge-up. This bit me twice this session; recovered both times via `git stash` + `git merge --no-ff` from the main checkout.

---

## State as of latest commit

Run `python scripts/current_status.py` for live state. Highlights:

- Branch: `dev` at `8bea4e3` (pushed).
- Tests:
  - cargo `aether-desktop`: **327 passed** (up from 315 at session start).
  - cargo `aether-l5-policy`: **86 passed** (up from 71).
  - cargo `aether-l5-files`: 13 default / 28 with `--features std-fs`.
  - workspace `cargo test --workspace --all-features`: **409+ passed**.
  - vitest from `apps/desktop/`: **279 passed / 25 files** (up from 268 / 24).
  - tsc clean.
- All 7 doc rot guards green.
- Boundary lint: 13 crates / 9 engines / 4 shared infra, 0 violations.
- Storage migrations: 0001 → 0006 (new `0006_policy_grants_approval_scope.sql` smoke-tested green).
- ADRs: 0001-0010, 0012-0016 (no 0011) all in place.

---

## Decisions locked this session

| # | Decision | Source | Status |
|---|---|---|---|
| ApprovalScope enum shape | `PerAction` / `OncePerSession` / `OncePerTask` / `DraftOnly` | T1.3 §2.3 design `3a858a8` | Implemented in Wave 10B |
| storage migration 0006 | additive `policy_grants.approval_scope TEXT NULL` | Wave 10B | Shipped |
| §4.2 consume-while-valid (not consume-once-per-N) | matches user mental model of "remember for this session" | T1.3 §2.3 design §4.2 | Implemented |
| Audit HMAC: ApprovalScope NOT folded into v2 canonical seal | freeze v2 chain integrity; future v3 bump can fold | T1.3 §2.3 design §3.3 | Honored |
| OncePerSession outbound sync = device-local | ADR-0016 §"What does NOT sync" | T1.3 §2.3 design §7 | Honored (sync filter hook deferred — see Wave 13 below) |
| Approval modal: radio with 4 fixed-order options + separate Deny button | "remember unchecked + AllowSession" contradiction prevented | T1.3 §2.3 design §5.1 | Implemented in Wave 14 |
| `apps/desktop/build_approval_response_for_choice` owns choice→response mapping | `aether_l7_trust::build_approval_response` is `ApprovalResolution`-shaped only; widening it would cross layers | Wave 14 implementation choice | Locked; documented in commit body |
| `auto_approved_under_grant` = first-class column, NOT folded into stage_trace | faster filter, clearer schema | T1.3 §2.3 design §10.OQ-3 | Implemented |
| Legacy NULL-scope grants treated as PerAction at read time, no backfill | zero behavior change, zero migration cost | T1.3 §2.3 design §10.OQ-4 | Implemented |

---

## Carry-forward open items

### Reserved for Don
- **Backup the release secret key** (still owed from yesterday's handoff). `C:\Users\dbhav\.aether\release-key\aether-release-ed25519.sk`. Backed up to `I:/IsabelleData/_keys/aether-release-key-backup-2026-04-30/`. Make at least one more copy off-machine.
- **`tools/persona-reference-gen/`** Aurora reference batch — Don-driven (`python tools/persona-reference-gen/__main__.py --persona aurora --batch <id>`).
- **GPU queue** Aurora pipeline kickoff — Don-driven.

### Software follow-ups (next session candidates)

#### Wave 13 — `StdFsExecutor` allowlist plumbing (cross-layer)
**Why this matters now:** `StdFsExecutor::default()` (empty allowlist) is the Wave 11 build-unblocker. Today every `files_*` invocation falls through to `FilesExecError::NotInScope`. Files commands have a fully-wired approval flow but no operative backend.

**Scope:** plumb a real allowlist sourced from approved-scope ledger (the `policy_grants` SQL table). Allowlist updates on grant changes. Cross-layer (l5-files setter + apps/desktop wire-up + grant-change listener). Per CLAUDE.md §1, this should split into:
- **Wave 13a** (l5-files only) — extend `StdFsExecutor` with `set_allowlist(...)` + `update_allowlist_from_paths(...)`. Add tests.
- **Wave 13b** (apps/desktop only) — `AppState` constructs `StdFsExecutor` with an initial allowlist from the active grants; subscribes to `GrantIssuedEvent` / `GrantRevokedEvent` and updates the executor's allowlist on the fly.

Estimated 4-6 commits each.

#### Wave 15 — affordance gating on the Wave 14 radio
Today's modal renders all 4 options unconditionally. Per design §5.1, `allow_task` should require task lineage and `defer_draft` should require side-effecting capability. Both gates need additional fields on `ApprovalPayload` (`task_id_present: bool` + capability metadata). Single-layer (apps/desktop). 2-4 commits.

#### Wave 16 — DeferToDraft Turn-path UI
Currently surfaces denied-shape on the chat wire because the chat surface doesn't yet render a "draft ready" affordance. Engine writes the `Decision::DraftOnly` audit row regardless. Add a dedicated `draft_only` `TurnOutcomeKind`. Single-layer (apps/desktop). 2-4 commits.

#### Wave 17 — OncePerSession outbound sync filter
Per ADR-0016 §"What does NOT sync" / OQ-2. When the sync layer lands (post-mobile), drop outbound `policy_grants` rows where `approval_scope == Some(OncePerSession)` and log inbound drops. Out of any current PR's scope; tracked here so it doesn't get lost.

#### Wave 18 — L7_trust_ux_onboarding_system_design.md §16 surgical sweep
Today's T4.7 banner-only pass acknowledges the §16 "OSS Preview vs Pro divergence" section is doctrine-§6-violating. A surgical sweep is owed (rewrite to "single product divergence-free model" or tombstone the section). Lower priority — author-focused, not load-bearing.

#### Wave 19 — Doctrine §8 used-as-user verification on the Wave 14 modal
vitest+RTL tests pass; cargo wire-string regression tests pass. Real Playwright-driven verification (`pnpm tauri dev` + `mcp__playwright__browser_*`) was out of scope per Wave 14 prompt. The user-as-user pass is owed before the modal ships to Don's daily-driver build.

### Cross-reference debt
- **`std_fs_stub.rs` filename misleading** — the file is no longer a stub. Cosmetic rename to `std_fs.rs` would touch `lib.rs::mod` path. Coordinator-only, not urgent.
- **TS bindings stub at `packages/l5-policy-ts/src/support.ts` is stale** — was already stale before Wave 10B, now staler (missing `approval_scope`, `auto_approved_under_grant`, `original_utterance`, `retrieval_provenance`, `schema_version`, `actor`, `stage_trace`). The `tools/ts-bindings-gen/` generator landing will fix it wholesale; do not hand-author TS in the meantime per CLAUDE.md §5.

---

## State of `parallel_software_tracks.md` after this session

Every Tier 1, Tier 2, and Tier 4 entry now carries an evidence-backed status — DONE with commit shas, or substantially-DONE with explicit carryover. T4.7 added to the doc as a new entry (the doctrine §6 banner sweep). Tier 3 finish-line items intentionally left as-is per the doc's own "defer until close to launch" rule.

Next-session reading order:
1. `python scripts/current_status.py`
2. `HANDOFF_2026-04-30_AUTONOMOUS_RUN.md` (parent)
3. **THIS document** (continuation)
4. `aether/CLAUDE.md` (rules)
5. `planning/01_product_doctrine.md` (§5/§6/§7/§8)
6. `planning/plans/parallel_software_tracks.md` (now honest)
7. `planning/plans/T1.3_approval_scope_design.md` (still load-bearing for follow-ups)

---

## Useful reference paths

- file:///C:/Users/dbhav/Projects/aether/scripts/current_status.py
- file:///C:/Users/dbhav/Projects/aether/aether/CLAUDE.md
- file:///C:/Users/dbhav/Projects/aether/planning/01_product_doctrine.md
- file:///C:/Users/dbhav/Projects/aether/planning/plans/parallel_software_tracks.md
- file:///C:/Users/dbhav/Projects/aether/planning/plans/T1.3_approval_scope_design.md
- file:///C:/Users/dbhav/Projects/aether/planning/plans/T1.3_browser_file_workflow_proposal.md
- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-30_AUTONOMOUS_RUN.md
- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-30_AUTONOMOUS_RUN_CONTINUATION.md (this file)
- file:///C:/Users/dbhav/Projects/aether/packages/l5-files/src/std_fs_stub.rs
- file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/approval.rs
- file:///C:/Users/dbhav/Projects/aether/packages/storage/migrations/0006_policy_grants_approval_scope.sql
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/commands.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/browser_commands.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/files_commands.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/state.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/ApprovalModal.tsx
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/ApprovalModal.test.tsx

---

*Run total this session: 26 commits, 5 waves, 15 stale-prompt drift catches, 1 cross-layer regression caught + fixed (Wave 10A → Wave 11 prep), 1 doctrine §6 banner sweep. End-to-end ApprovalScope flow now wired from L5 enum to L7 user picker.*
