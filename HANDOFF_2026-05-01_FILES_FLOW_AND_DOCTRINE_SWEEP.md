# Handoff — 2026-05-01 Files-flow end-to-end + L7 doctrine sweep + drag-drop research

> **Purpose.** Ultra-detailed record of the autonomous run that closed the medium-value carry-forwards from `HANDOFF_2026-04-30_AUTONOMOUS_RUN_CONTINUATION.md` and produced one piece of forward-looking research (drag-drop attachment UX). Successor to `HANDOFF_2026-05-01_FILES_FLOW_END_TO_END.md` (which only covered Waves 13a/13b/15/16 — this doc supersedes it).
>
> **Branch:** `dev` (pushed). **Tip at handoff write:** TBD (final commit will be this handoff doc itself + the research doc + the starting prompt). Pre-write tip: `a2358a7` (Wave 18 follow-up).
>
> **Session shape:** 11 commits across 5 functional waves (13a, 13b, 15, 16, 18) + 4 docs commits + 1 research deliverable. The Files command flow is now end-to-end live for the first time. Wave 19 (Playwright used-as-user verification) is the only outstanding owed slice on T1.3.

---

## TL;DR (for fast recovery)

Three deliverable streams landed this session:

### Stream A — Files command flow end-to-end live

Before this session: even after Approve, `files_*` invocations fell through to `FilesExecError::NotInScope` because `StdFsExecutor::default()` (empty allowlist) was the Wave 11 build-unblocker. The wire was in place but the executor was deaf to grant events.

After this session: Approve a `Files*` request → grant issued → `ExecutorAllowlistSink` (new in Wave 13b) updates the executor's allowlist → replay invocation succeeds. Modal also intelligently hides options that don't apply to the request (Wave 15) and renders DeferToDraft outcomes with a distinct affordance (Wave 16).

### Stream B — L7 doctrine sweep

Doctrine §6 (single product, ships when complete) retired the OSS-Preview-as-wedge thesis on 2026-05-18. The L7 system_design doc carried the heaviest residue of any L*_system_design.md — a full §16 "OSS Preview vs Pro divergence" matrix, plus inline references throughout. Wave 18 closed the load-bearing residue (§16 tombstone) and the smaller language touches (§1 scope, §2.2/§2.4/§2.5 inline doc-comments, §2.3 two-implementations table, §4.1 wizard row 6, §4.5 Guest mode, §9/§13 transport-failure language). The §20 open-questions list and §22 sections-accomplished checklist are intentionally left as historical change-log style sections.

### Stream C — Drag-drop attachment research

Don asked "do you have drag-drop file/image windows? Research UIs and UXs for similar creator dashboards." Companion has zero today (confirmed by grep). Research deliverable at `planning/research/2026-05-01_drag_drop_attachment_ux.md` covers 13 surfaces (ChatGPT, Claude, Gemini, Perplexity, Cursor, Krea, Magnific, Midjourney, ComfyUI, Firefly, Linear, Notion, Slack/Discord), the Tauri-specific architecture call (must use `onDragDropEvent` not HTML5 `drop` for L5 path-allowlist compatibility), and a recommended Perplexity-class pattern with 6 open questions for Don to resolve before any implementation.

---

## Commits — chronological with full context

### Wave 13a — l5-files mutable allowlist

Single-layer scope: `packages/l5-files/`. Branched off `dev` tip `3beaaee` (the prior session's clean-session starting prompt commit). Dispatched to a worktree-isolated agent.

| Commit | Subject |
|---|---|
| `4a2640c` | `feat(l5-files): mutable allowlist on StdFsExecutor via Arc<RwLock>` |
| `dc69808` | `test(l5-files): cover Wave 13a runtime allowlist mutation` |
| `15c8b35` | `docs(l5-files): refresh module docstring for mutable allowlist` |
| `341b53e` | Merge Wave 13a — l5-files mutable allowlist (`--no-ff`) |

**What changed:** `StdFsExecutor` scope field went from `ScopeAllowlist` (immutable) to `Arc<RwLock<ScopeAllowlist>>` (interior mutability). Two new public methods on the concrete type (NOT on the `FilesExecutor` trait — keeping the trait surface narrow):

- `pub fn set_allowlist(&self, scope: ScopeAllowlist)` — sync, takes `&self` not `&mut self`, atomic wholesale swap.
- `pub fn update_allowlist_from_paths<I: IntoIterator<Item = PathBuf>>(&self, roots: I) -> Result<(), FilesExecError>` — sync, canonicalizes via `std::fs::canonicalize`, all-or-nothing (one bad path leaves the existing scope untouched and returns `FilesExecError::Io`).

Hand-rolled `Clone` on `StdFsExecutor` shares allowlist state via `Arc` (clones see each other's mutations). The helpers `canonicalize_and_authorize` and `canonicalize_parent_and_authorize` read the lock, clone the small `ScopeAllowlist`, and drop the guard before any `.await` — `std::sync::RwLock` guards aren't `Send`-safe across await on some platforms.

**Tests:** 28 → 34 with `--features std-fs` (+6 new). 13 default. Workspace build still clean.

**Known gotcha caught preemptively:** `Cargo.lock` moved on first build (tokio/std-fs feature graph adding `bytes`/`mio`/`signal-hook-registry`). Committed in commit 1 per the brief's allowance for build-driven moves.

### Wave 13b — apps/desktop allowlist plumbing

Single-layer: `apps/desktop/`. Branched off `dev` tip `341b53e` (Wave 13a merge). Worktree-isolated agent.

| Commit | Subject |
|---|---|
| `4054e93` | `feat(desktop): add concrete StdFsExecutor handle on AppState` |
| `aa3801d` | `feat(desktop): seed StdFsExecutor allowlist + wire ExecutorAllowlistSink` |
| `7afe05f` | `test(desktop): cover Wave 13b boot seed + handle/trait scope sharing` |
| `ebf074c` | Merge Wave 13b — apps/desktop allowlist plumbing (`--no-ff`) |

**What changed:**

1. `AppState` now holds two fields against the same underlying executor:
   - `pub files_executor: Arc<dyn FilesExecutor>` — unchanged trait-object surface for downstream `files_commands.rs` / `commands.rs`.
   - `pub files_executor_handle: Arc<StdFsExecutor>` — concrete handle for mutation.
   - Both wrap the same `StdFsExecutor`; allowlist state shared via the inner `Arc<RwLock<...>>` from Wave 13a.

2. New module `apps/desktop/src-tauri/src/policy_sink.rs` (334 lines, brand-new):
   - `ExecutorAllowlistSink` wraps the engine's existing `L5EventSink` and additionally holds `Arc<dyn GrantLedger>` + `Arc<StdFsExecutor>`.
   - On every `L5Event::GrantIssued` or `L5Event::GrantRevoked`, the sink calls a private `rebuild_allowlist_from_ledger()`: snapshots active grants → filters File* capabilities → extracts `ResourceScope::Path` paths → calls `executor.set_allowlist(...)` after individually canonicalizing each path (drops failures rather than failing the whole rebuild).
   - All other event variants forward to the inner sink.

3. `build_active_engine` (state.rs ~L1700) now:
   - Constructs `Arc<StdFsExecutor>` first.
   - Snapshots active grants on boot, seeds the executor allowlist (best-effort: per-path canonicalize, drop failures individually, never fail boot).
   - Constructs `DefaultPolicyEngine::new` with the `ExecutorAllowlistSink` wrapping `InMemorySink::new()`.
   - Three call sites (`build`, `apply_preset`, `switch_persona`) all thread the handle. Persona-swap / preset-change rebuilds with a fresh ledger → empty allowlist (no stale-grant leakage across personas — important security property).

**Tests:** desktop cargo 327 → 333 (+6: 4 in `policy_sink::tests`, 2 in `state::tests`). Pre-existing 327 untouched.

### Wave 15 — affordance gating on ApprovalModal

Single-layer: `apps/desktop/`. Done **inline** (not via agent dispatch) because the prior agent attempt hit the API rate limit at 10pm Pacific. Resumed inline after rate reset.

| Commit | Subject |
|---|---|
| `ade50cb` | `feat(desktop): Wave 15 — affordance gating on ApprovalModal radio` |

**What changed:**

1. `ApprovalPayload` (Rust at `commands.rs` L108-126; mirrored on TS at `types.ts` L48+) gained two fields:
   - `task_id_present: bool` — drives whether `allow_task` radio option renders.
   - `side_effecting: bool` — drives whether `defer_draft` renders.

2. New private helper `commands::capability_is_side_effecting(&Capability) -> bool` exhaustively classifies every Capability variant (read-only family: `FilesRead`, `BrowserReadPage`, `BrowserExtractData`, `EmailReadMetadata`, `EmailReadBody`, `ClipboardRead`, `NotificationRead`, `MemoryRead`, `RetrievalContext` → false; mutating/external family: everything else explicitly listed → true; `_` arm for defence-in-depth).

3. All three `ApprovalPayload` construction sites updated:
   - `commands.rs` L497 (turn-engine submit_turn path)
   - `browser_commands.rs` L148 (browser executor gate)
   - `files_commands.rs` L146 (files executor gate)
   - All three set `task_id_present: false` (every existing `TurnRequest` in the codebase carries `task_id: None` — flag reflects current truth; flip when task lineage threads through).
   - All three set `side_effecting: capability_is_side_effecting(&prompt.capability)`.

4. `ApprovalModal.tsx` filters `APPROVAL_RADIO_OPTIONS` at render time — `allow_task` hidden when `!payload.task_id_present`, `defer_draft` hidden when `!payload.side_effecting`. `useState` initializer falls back to `allow_once` (always visible) when the default would be gated out. Module doc-comment flipped from "V1 affordance state: every radio option is rendered unconditionally" to "V2 affordance state (Wave 15) — gating now lives behind the payload's flags per design §5.1".

5. Existing test fixture `PAYLOAD` updated to set both flags `true` so the prior 11 Wave 14 tests still observe all four radio options. New `renderModal` helper accepts an override payload.

**Tests:** desktop cargo 333 → 335 (+2: helper classifier across read-only and mutating Capability families). vitest 279 → 285 (+6: gating-off cases for each flag, both-flags-off, both-flags-on regression, default-selection survival, Approve emit on fully-gated payload).

### Wave 16 — DeferToDraft Turn-path affordance

Single-layer: `apps/desktop/`. Done inline. Closes the carry-forward where the chat surface treated `DraftOnly` outcomes the same as any system message (the wire-shape `TurnOutcomeKind = "draft_only"` was already in place from prior work; the affordance was missing).

| Commit | Subject |
|---|---|
| `cc9b5bf` | `feat(desktop-ui): Wave 16 — DeferToDraft Turn-path affordance` |

**What changed:**

1. `TranscriptMessage` (TS only) gained an optional `variant?: "draft_only"` field. Renderer-only — Rust does not populate it.

2. `App.tsx` `appendOutcome` tags the message at append time:
   ```ts
   const message =
     outcome.kind === "draft_only"
       ? { ...outcome.message, variant: "draft_only" as const }
       : outcome.message;
   ```

3. `Transcript.tsx` `MessageBubble` renders `system + variant === "draft_only"` with amber border (`border-aether-warn/60`), amber-tinted background (`bg-aether-warn/10`), and an inline "Draft only" badge above the message content. Generic system messages keep their muted styling.

4. New tests in `Transcript.test.tsx` use `@testing-library/react`. JSDOM doesn't implement `scrollIntoView`, so the file stubs `Element.prototype.scrollIntoView = function () {}` once via `beforeAll`.

**Tests:** vitest 285 → 288 (+3: variant-unset path, variant-set path, user/assistant rendering still untouched).

### Doc commits — session shape

| Commit | Subject |
|---|---|
| `087b23f` | `docs(handoff): 2026-05-01 — files flow end-to-end + modal affordances` (initial handoff covering 13a/13b/15/16) |
| `f7b929d` | `docs(planning): patch T1.3 — Waves 12/13a/13b/14/15/16 DONE with evidence` (stale-prompt drift catch on parallel_software_tracks.md) |
| `e552456` | `docs(handoff): mark Wave 18 DONE in 2026-05-01 carry-forward queue` |

### Wave 18 — L7 §16 OSS-Preview-vs-Pro divergence tombstone

Doc-only. Closes the load-bearing residue T4.7 (banner-only sweep) explicitly flagged.

| Commit | Subject |
|---|---|
| `a2fcddd` | `docs(planning): Wave 18 — tombstone L7 §16 OSS-Preview-vs-Pro divergence` |

**What changed:** L7 §16's full divergence matrix (8-screen wizard variants, preset-ladder splits, 4-vs-7-tab trust center, BYOK gating, Guest mode, audit-export gating, build-flag mechanism via `useEdition()` hook) replaced with a tombstone notice. Rationale preserved in git history at `f7b929d^`. T4.7 in `parallel_software_tracks.md` flipped to mark §16 surgical sweep DONE.

### Wave 18 follow-up — smaller L7 doctrine residue sweep

| Commit | Subject |
|---|---|
| `a2358a7` | `docs(planning): Wave 18 follow-up — sweep smaller L7 doctrine residue` |

**What changed:** Inline language touches across §1 scope (drop "or Python (pywebview)" from adapter sentence), §2.2 adapter pseudotype (drop "or pywebview JSON file" from `persistState` comment), §2.3 (collapse two-implementations table to single Tauri row + Wave 18 sweep note; preserve adapter pattern as a seam for future shells), §2.4 secret-handling rule 2 (drop "or pywebview overlay"), §2.5 IPC surface (drop "mirrored Python docstrings on pywebview side"), §4.1 wizard table row 6 (drop "(Pro) or Guest fallback (OSS Preview)" — single LLM-setup screen), §4.5 (tombstone Guest mode entirely as OSS-Preview-scoped), §9.1/§9.2 (drop "pywebview bridge drop" from transport-failure detection list), §13 secret-capture (drop pywebview branch from devtools-capture block list), §16 tombstone cross-reference paragraph (update to reflect §4.5 + §2.3 also closed).

**File-head banner** updated to enumerate Wave 18's full footprint and explicitly call out that §20 / §22 are intentionally left as historical change-log sections (reading them as current spec is a category error).

### Stream C — drag-drop attachment research

Untracked at handoff start; will be committed alongside this doc.

`planning/research/2026-05-01_drag_drop_attachment_ux.md` (~340 lines)

Coverage: 13 surfaces across 3 groups (AI chat / AI image-creator / general creator dashboards). Cross-cutting findings on the dominant 2026 pattern, AI-chat convergence, useful divergence (creator-tool role-distinguished slots), best compact pattern for single-composer chat (Perplexity), worst patterns to avoid (Slack-style affordance soup, Notion's block paradigm, Cursor's focus-routing bug). Tauri implementation notes (verdict: Architecture A — `onDragDropEvent` for real file paths that L5 needs). Recommended Perplexity-class compact pattern with full UX sketch and concrete behaviors. **Six open questions** for Don to resolve before implementation.

Visual preview also produced at file:///C:/tmp/aether-wave-15-16-preview.html showing Wave 15 modal states (3 variants) + Wave 16 transcript bubble. Not committed (not project-relevant; lives in temp).

---

## Lessons learned this session

### Engineering / process

1. **`isolation: "worktree"` does not always mean a separate worktree.** The Wave 13a + 13b agents both ran with `isolation: "worktree"` set, but my main checkout's HEAD ended up on the worktree branch after the agent finished. Worked around it by `git checkout dev` then `git merge --no-ff`. Don't assume the worktree stays isolated; always verify the main checkout's branch before merging.

2. **Worktree-isolation prevented commit races, even when shared workspace.** Despite the worktree isolation not being perfectly clean, the explicit-path commit discipline (`git add <specific files>`, never `git add -A`) prevented any race conditions. Five agents ran across the prior session + this session with zero commit-race incidents. Pattern is durable — adopt as default.

3. **The pre-commit hook is finally working.** `bash tools/check-pre-commit.sh` (committed at `tools/git-hooks/pre-commit`, wired via `core.hooksPath`) caught zero failures this session — Wave 13a/13b/15/16/18 authors all wrote code/docs that passed `cargo fmt --all -- --check` + `ruff check src/ tests/` on first commit. The CI red-X recurrence pattern from late April is now closed end-to-end. Hook fires automatically on every commit.

4. **Cargo isn't on PATH by default in Git Bash.** Multiple commands silently fail with `cargo: command not found` until you `export PATH="/c/Users/dbhav/.cargo/bin:$PATH"`. Add to wave-prompt boilerplate when an agent is going to run cargo directly.

5. **Test-build-time is the right tier for cargo verification, not test-runtime.** `cargo test --no-run` catches 100% of test-side compilation errors that struct field additions can introduce, in ~15s vs. ~30s for full `cargo test`. Use it as the first-pass smoke check after a struct-shape change.

6. **JSDOM lacks `scrollIntoView`.** The Transcript component scrolls a bottom sentinel into view on mount. Adding RTL render tests requires `beforeAll(() => { Element.prototype.scrollIntoView = function () {}; })` or the tests throw `TypeError`. Pattern needed for any component that calls `scrollIntoView` in `useEffect`. Document in the shared test setup if the pattern recurs.

7. **Existing test fixtures need updating when struct fields are added.** The `ApprovalModal.test.tsx`'s `PAYLOAD` const had to set both Wave 15 flags `true` so existing 4-option tests still observe all four radio options. Otherwise the gating would silently hide options and break unrelated assertions about "fixed-order four-option display". Pattern: when adding optional/required fields to a fixture, default the new fields so existing tests remain semantically correct.

8. **Inline work is viable when an agent rate-limits.** The Wave 15 agent hit the 10pm Pacific rate limit. Resumed inline. Worked because Wave 15 was bounded (3 files, ~50 lines). Pattern: dispatch agents for exploratory + multi-file scope; pick up inline when a wave is well-scoped + small.

9. **Read-before-edit hooks fire even for files read earlier in the session.** Multiple `PreToolUse:Edit` hooks suggested re-reading even when I had already read the file. Edits succeeded anyway — the hook is advisory, not blocking. Don't waste tool calls re-reading; just proceed.

10. **`git add` followed by a regex-pattern `git status --short | grep` beats reading the diff for staged files.** Faster confidence check that you staged what you meant to stage and not the dirty preview_voice.opus files.

### Doctrine / planning

11. **Stale-prompt drift recurred even after the prior session's exhaustive sweep.** `parallel_software_tracks.md` had Wave 12 listed as "in flight 2026-04-30" and Wave 14 modal radio + Wave 13 allowlist plumbing as Carryover, when all three had shipped. The prior session caught 15 instances; this session caught 6 more. Conclusion: the tracks doc lags the repo by days even with active maintenance. **Always run the script before treating any "Carryover" / "owed" / "still pending" entry as actually pending. Run `git log --oneline --all | grep <feature>` against any doc-claim of pending work.**

12. **Doctrine sweeps can introduce inconsistencies if pushed too aggressively.** Tombstoning L7 §4.5 ("Guest mode") introduced an L4 vs L7 contradiction — L4 §912 / §1083 preserve a "Guest" routing-tier concept while L7 §4.5 said "no anonymous try-it-without-installing surface". The two might be the same thing or different things; flagging this for Don rather than resolving autonomously was the right call. **Pattern: when a doctrine sweep touches a concept that appears in multiple docs, scan for cross-references before tombstoning. If the concept appears with different framings in two docs, that's an upstream design question.**

13. **The §20 / §22 "historical change-log" sections should be left untouched in surgical sweeps.** L7's §20 (open questions) and §22 (sections-accomplished checklist) read like log entries that document the doc's evolution. Sweeping them would erase historical context for readers trying to understand why decisions were made. Banner explicitly carved them out as historical; commit body documented the carve-out.

### Research / forward-looking

14. **Drag-drop in Tauri is the architectural decision, not the UX.** The default `dragDropEnabled: true` means Tauri intercepts file drops at the OS level — webview's HTML5 `drop` event never fires; you get paths, not blobs. For Companion's L5 path-allowlist, this is correct (HTML5 drop would break the policy gate). But it means element-scoped drop zones require a mouse-tracking workaround on some platforms, and devtools breaks drop position. Architecture-A (Tauri-native) over Architecture-B (HTML5) is non-negotiable for L5 compatibility.

15. **Cursor's clipboard-paste focus-routing bug is the cautionary tale for paste UX.** When focus state is ambiguous, Cmd/Ctrl+V on a screenshot lands in the wrong surface (the open editor instead of the chat input). The user types Cmd+V, sees nothing happen in the chat, and silently loses trust in the surface. Companion's paste UX needs an unambiguous focus indicator on the composer at all times.

---

## State at handoff write

Run `python scripts/current_status.py` for live state.

**Branch:** `dev` at `a2358a7` pre-write; final tip after this commit will be the head of dev with the handoff doc + research doc + starting prompt all committed in one or two commits.

**CI:** Wave 13a ✅ (`25200684979`), 13b ✅ (`25201062264`), 15 ✅ (`25203310037`), 16 ✅, T1.3-doc ✅ (`25205912281`), Wave 18 main cancelled mid-run by superseding push but its blocking jobs (Rust/Governance/Boundary/TS) all succeeded before cancellation, handoff-update run completed. All blocking jobs green at `a2358a7`.

**Tests:**
- cargo `aether-l5-files`: **34 passed** with `--features std-fs` (was 28; +6 Wave 13a)
- cargo desktop (from `apps/desktop/src-tauri`): **335 passed** (was 327; +6 Wave 13b + 2 Wave 15)
- vitest from `apps/desktop/`: **288 passed / 25 files** (was 279; +6 Wave 15 + 3 Wave 16)
- tsc clean; cargo fmt clean; ruff clean; pre-commit hook clean.
- Boundary lint: 13 crates / 9 engines / 4 shared infra, 0 violations (untouched — no `packages/*` changes after Wave 13a).

**Storage migrations:** 0001 → 0006 (unchanged this session).

**ADRs:** 0001-0010, 0012-0016 (unchanged).

**Working-tree dirty state (pre-existing, do NOT touch):**
- 9 `apps/desktop/public/personas-previews/*/preview_voice.opus` files (auto-regenerated)
- ~36 untracked LoRA training checkpoint dirs under `planning/session_2026-04-26/training/checkpoints_v2..v9c/`

---

## Decisions locked this session

| # | Decision | Source | Status |
|---|---|---|---|
| `StdFsExecutor` interior mutability via `Arc<RwLock<ScopeAllowlist>>` (std lib, not tokio) | reads are sync + cheap; never hold guard across await | Wave 13a implementation choice | Locked in 13a |
| `set_allowlist` and `update_allowlist_from_paths` live on the concrete type, NOT on `FilesExecutor` trait | trait surface stays narrow; mutator access requires concrete handle | Wave 13a brief constraint | Locked in 13a |
| `AppState` two-fields shape: `Arc<dyn FilesExecutor>` + `Arc<StdFsExecutor>` sharing inner state | clones share state via inner `Arc<RwLock<...>>`; downstream call sites unchanged | Wave 13b implementation choice | Locked in 13b |
| Boot-time allowlist seed is best-effort (per-path canonicalize, drop failures, never fail boot) | matches user expectation that an unmounted volume from a prior session shouldn't brick startup | Wave 13b brief | Locked in 13b |
| Persona-swap / preset-change rebuilds with a fresh ledger → empty allowlist | prevents stale-grant cross-persona leakage (security property) | Wave 13b implementation discovery | Locked in 13b |
| `task_id_present` hardcoded `false` at all `ApprovalPayload` construction sites | every existing `TurnRequest` already carries `task_id: None`; the field reflects current truth | Wave 15 implementation choice | Locked; flip when task lineage threads through |
| `capability_is_side_effecting` lives in `apps/desktop/src-tauri/src/commands.rs`, NOT in `packages/l5-policy` | single-layer constraint; classification is render-shaping, not policy | Wave 15 brief constraint | Locked in 15 |
| `TranscriptMessage.variant` is renderer-only (TS-only) | Rust doesn't need to mirror; App.tsx sets it at append time | Wave 16 implementation choice | Locked in 16 |
| `draft_only` UI affordance is amber border + inline "Draft only" badge | matches `aether-warn` token use elsewhere (audit history); not a denial | Wave 16 implementation choice | Locked in 16 |
| L7 §16 OSS-Preview-vs-Pro divergence matrix removed from active spec | doctrine §6 retired the OSS-Preview-as-wedge thesis; rationale lives in git history | Wave 18 doctrine sweep | Locked in 18 |
| L7 §4.5 Guest-mode wizard surface tombstoned | OSS-Preview-only feature; "no anonymous try-before-install surface" | Wave 18 follow-up | **POTENTIAL CONFLICT** with L4 §912 / §1083 which preserve a "Guest" routing-tier concept; flagged for Don |
| L7 §20 / §22 historical change-log sections preserved in doctrine sweep | reading them as current spec is a category error; banner carves them out | Wave 18 follow-up implementation choice | Locked in 18 |
| Drag-drop attachment Architecture A (Tauri-native `onDragDropEvent`) over Architecture B (HTML5 `drop`) | Architecture B gives blobs without paths; breaks L5's path allowlist | Stream C research finding | Recommended; awaiting Don's decision on the 6 open questions |

---

## Carry-forward queue (next session)

### Wave 19 — Doctrine §8 used-as-user Playwright verification (HIGHEST VALUE OWED)

**Status:** owed. Vitest+RTL covers the Wave 14/15 modal at the React level; the Wave 13b allowlist plumbing covers the integration at the Rust level; Wave 11/12/14 covered the wire. **What's missing:** a real `pnpm tauri dev` + `mcp__playwright__browser_*` pass that drives a turn through the gate, picks an option from the live modal, and verifies the executor replay actually returns the file bytes (not stubbed).

**Why this is the most valuable next slice:** Doctrine §8 explicitly requires "frontend changes get used-as-user via automation before reaching Don's review." The Wave 14/15 modal is currently in "vitest-green but not used-as-user" state. Shipping it to Don's daily-driver build before this verification is a doctrine-§8 violation.

**Why it's a separate session:** It needs the Tauri dev shell to start cleanly (could be a 30-90s startup), Playwright orchestration against the Tauri webview (which has its own quirks vs. a normal browser), and a fixture path that triggers a `Decision::Ask` to actually exercise the modal. None of these are blockers but together they consume context.

**Approach for the next session:**
1. `cd /c/Users/dbhav/Projects/aether/apps/desktop && pnpm tauri dev` (background)
2. Wait for the dev server to start (watch logs for "Press Ctrl+C to stop").
3. Use `mcp__playwright__browser_navigate` + `mcp__playwright__browser_snapshot` to find the Tauri webview URL (typically `http://localhost:1420` or similar).
4. Drive a turn that triggers a Files* gate (e.g. via the chat composer typing "edit /tmp/foo.txt").
5. Assert the modal renders with the correct radio options (per Wave 15 gating).
6. Click each option; verify the wire-shape `UserChoiceWire` emits correctly via Tauri command response.
7. For the Approve path, verify the file is actually read (or written) — this exercises Wave 13b's allowlist plumbing end-to-end.

### Wave 13c — Task lineage threading

**Status:** speculative. Wave 15 hardcodes `task_id_present: false` because every `TurnRequest` carries `task_id: None`. Flip to `request.task_id.is_some()` once a future wave plumbs task lineage through `submit_turn` and the gate paths.

**Why speculative:** Tasks aren't yet a concept in the system. The chat surface is single-turn — no multi-turn chains, no parent-child task relationships. Plumbing `task_id` requires upstream design for what a "task" is, when it's created, when it ends, and how the chat surface lets the user start one.

**Search for `task_id: None,` in `apps/desktop/src-tauri/src/{commands,browser_commands,files_commands}.rs`** — every site is a candidate flip once task lineage exists.

### Wave 17 — OncePerSession outbound sync filter

**Status:** still deferred until sync layer ships post-mobile. Per ADR-0016 §"What does NOT sync".

### L4 vs L7 Guest-mode doctrine inconsistency (DON DECISION)

L7 §4.5 (this session's tombstone) said "no anonymous try-before-install surface". L4 §912 / §1083 preserve a "Guest" routing-tier concept (no-BYOK fallback within the single product). These may be the same thing (and L4 should also be tombstoned) or different things (Guest UX retired, Guest routing-tier survives). Don's call. Once decided, sweep the loser.

### Drag-drop attachment phase (DON DECISION)

Research delivered. Six open questions for Don in `planning/research/2026-05-01_drag_drop_attachment_ux.md` §5:

1. Clipboard-paste policy (no path → new `MediaUpload` capability vs. temp-dir-then-FilesRead?).
2. Approval timing (drop vs send; recommended: send, batched).
3. Allowlist scope shape (path / parent dir / extension; current Wave 13 plumbing is path-only — needs parent-dir mode for media folders).
4. Drop overlay copy tone ("will request FilesRead" — system-y vs plain English?).
5. `MediaUpload` capability scope (new or flag on `FilesRead`? covers TTS audio + persona reference images?).
6. Drop overlay behavior when ApprovalModal is already open (ignore or queue).

If Don says go after answering, the implementation is a multi-wave phase touching `packages/l5-policy/` (new `MediaUpload` capability + allowlist scope changes), `apps/desktop/src-tauri/src/` (Tauri drag-drop event handlers + temp-dir blob writer + new commands), and `apps/desktop/src/` (overlay component + chip strip + composer button). Estimated 4-6 waves.

### Lower-priority L7 doctrine residue follow-ups

Smaller residue across L2/L3/L5/L6 system_design docs (counted earlier this session: L2=2 mentions, L3=5, L4=4, L5=4, L6=3). The prior session's banner-only sweep was deemed sufficient for these. Surgical sweeps owed but lower priority — none are load-bearing matrices like L7 §16 was. Worth doing in a doc-cleanup session when no engineering work is in flight.

### Reserved for Don (carried forward from prior handoffs)

- **Backup the release secret key.** `C:\Users\dbhav\.aether\release-key\aether-release-ed25519.sk`. Backed up to `I:/IsabelleData/_keys/aether-release-key-backup-2026-04-30/`. Make at least one more copy off-machine.
- **`tools/persona-reference-gen/`** Aurora reference batch — Don-driven.
- **GPU queue** Aurora pipeline kickoff — Don-driven.
- **Run `bash tools/setup-hooks.sh`** on any other clone of this repo. Already installed on the main checkout.

---

## Pre-flight for the next session — MANDATORY before any commit

```bash
cd /c/Users/dbhav/Projects/aether
python scripts/current_status.py            # confirms tip + branch
git status --short                          # review pre-existing dirty state
bash tools/check-pre-commit.sh              # confirm cargo fmt + ruff clean
export PATH="/c/Users/dbhav/.cargo/bin:$PATH"  # cargo isn't on PATH by default in Git Bash
```

Pre-commit hook is wired (`core.hooksPath = tools/git-hooks`) and dogfooded across this session (zero failures). Do NOT bypass with `--no-verify`.

If working in a fresh clone, also run `bash tools/setup-hooks.sh` once.

**Agent-dispatch boilerplate (unchanged from prior handoff):** every wave-prompt's "Hard constraints" section must require `bash tools/check-pre-commit.sh` to exit clean before staging any commit. Add `export PATH="/c/Users/dbhav/.cargo/bin:$PATH"` if the agent will run cargo directly.

---

## Useful reference paths

- file:///C:/Users/dbhav/Projects/aether/scripts/current_status.py
- file:///C:/Users/dbhav/Projects/aether/CLAUDE.md
- file:///C:/Users/dbhav/Projects/aether/planning/01_product_doctrine.md
- file:///C:/Users/dbhav/Projects/aether/planning/plans/parallel_software_tracks.md
- file:///C:/Users/dbhav/Projects/aether/planning/plans/T1.3_approval_scope_design.md
- file:///C:/Users/dbhav/Projects/aether/planning/plans/L7_trust_ux_onboarding_system_design.md
- file:///C:/Users/dbhav/Projects/aether/planning/research/2026-05-01_drag_drop_attachment_ux.md
- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-30_AUTONOMOUS_RUN.md (parent of parent)
- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-30_AUTONOMOUS_RUN_CONTINUATION.md (parent)
- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-01_FILES_FLOW_END_TO_END.md (predecessor — narrower scope)
- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-01_FILES_FLOW_AND_DOCTRINE_SWEEP.md (this file)
- file:///C:/Users/dbhav/Projects/aether/STARTING_PROMPT_2026-05-02.md (clean-session priming prompt for next session)
- file:///C:/Users/dbhav/Projects/aether/STARTING_PROMPT_2026-05-01.md (this session's predecessor prompt)
- file:///C:/Users/dbhav/Projects/aether/packages/l5-files/src/std_fs_stub.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/policy_sink.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/state.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/commands.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/browser_commands.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/files_commands.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/ApprovalModal.tsx
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/ApprovalModal.test.tsx
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/Transcript.tsx
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/Transcript.test.tsx
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/App.tsx
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/lib/types.ts
- file:///C:/tmp/aether-wave-15-16-preview.html (visual preview — local only, not committed)

---

*Run total this session: 11 commits across 5 functional waves (13a, 13b, 15, 16, 18) + 4 docs commits + 1 forward-looking research deliverable. Files command flow end-to-end live for the first time. L7 doctrine sweep closes the load-bearing OSS-Preview residue. Drag-drop attachment research delivered with 6 open questions awaiting Don. Wave 19 (Playwright used-as-user) is the only outstanding owed slice on T1.3.*
