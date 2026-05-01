# Clean-Session Starting Prompt — 2026-05-01

> Paste the block below into a fresh Claude session at `C:\Users\dbhav\Projects\aether`. It primes the next session with the read-order, the lessons from the prior 2026-04-30 autonomous run, the tip state, the queue, and the hard rules.

---

## ▼▼▼ COPY FROM HERE ▼▼▼

You are picking up the Aether/Companion repo (codename: aether, public name Companion) at `C:\Users\dbhav\Projects\aether` after a 2-day autonomous-run series. **30 commits** landed yesterday (2026-04-30) on `dev` between `be82563` and `189a087`. **CI is green at `189a087`** (run 25199422814 — all 5 jobs success).

### Read in this exact order before doing anything else

1. `python scripts/current_status.py` — authoritative state. **Trust this over any prompt or older handoff.**
2. file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-30_AUTONOMOUS_RUN_CONTINUATION.md — the most recent handoff. Reflects the second wave of yesterday's 12-hour mandate (5 feature waves: 10A/10B/11/12/14, plus the CI red-X root-cause + permanent fix). **Supersedes** the parent `HANDOFF_2026-04-30_AUTONOMOUS_RUN.md` wherever they disagree.
3. file:///C:/Users/dbhav/Projects/aether/CLAUDE.md — repo rules. **§1** (one-layer-per-session), **§3** (coordinator-gated package creation), **§8** (clickable links), **§9.5** (NEW — pre-commit hygiene; mandatory before any commit).
4. file:///C:/Users/dbhav/Projects/aether/planning/01_product_doctrine.md — §5/§6/§7/§8 are load-bearing.
5. file:///C:/Users/dbhav/Projects/aether/planning/plans/parallel_software_tracks.md — claimable work. **As of 2026-04-30 every Tier 1/2/4 entry has an evidence-backed status** (15 stale-prompt drift catches reconciled yesterday). Tier 3 finish-line items intentionally deferred per the doc's own rule.
6. file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-30_AUTONOMOUS_RUN.md — parent handoff (only for context on the morning waves; superseded by #2 above for state).

### Pre-flight — MANDATORY before any commit

Run these at session start:

```bash
cd /c/Users/dbhav/Projects/aether
python scripts/current_status.py            # confirms tip + branch
git status --short                          # review pre-existing dirty state
bash tools/check-pre-commit.sh              # confirm cargo fmt + ruff clean
```

The pre-commit hook is already wired (commit `189a087`). If `bash tools/setup-hooks.sh` hasn't been run on this clone, run it once. Every `git commit` then auto-runs the lint mirror; do NOT bypass with `--no-verify`.

### Hard rules from prior-run lessons

1. **Repo beats prompt.** 15 stale-prompt drift catches yesterday alone. Verify any "Available" / "Greenfield" / "pending" entry against `git log` + live code before doing it. If repo says it's already shipped, **refuse to redo, flag the doc-vs-repo gap, patch the doc** with evidence (commit shas + file paths).

2. **Worktree isolation for parallel dispatch.** Every parallel agent dispatch uses `isolation: "worktree"` on the Agent tool. 5 agents ran in parallel yesterday with zero commit-race incidents.

3. **Explicit-path commits always.** `git commit -- <explicit paths>`. **Never** `git add -A`, `git add -u`, `git add .`. The Wave 4 multi-agent commit-race fix (yesterday morning) was worktree isolation; the discipline still applies.

4. **One layer per session per CLAUDE.md §1.** A session touches at most one `packages/l*-*/` layer. `apps/desktop/` is its own scope and is treated as one layer. Cross-layer work splits into multiple agent dispatches.

5. **CI's blocking lints run before every commit.** `tools/check-pre-commit.sh` mirrors them locally (`cargo fmt --all -- --check` + `ruff check src/ tests/`). If the script fails, fix locally — never `--no-verify`. CI red-X means the email digest masks any blocking failure underneath; treat it as a session-ender.

6. **Doctrine §8 — frontend changes get used-as-user via automation** (Vite + Playwright) before shipping. Mocked vitest is necessary but not sufficient. For backend-only Rust slices, `cargo test` + the boundary lint is the floor.

7. **Clickable links** — every user-facing path uses bare `file:///C:/...` URLs with forward slashes. No backticks, no markdown link syntax, no backslashes.

### Working-tree dirty state — DO NOT TOUCH

The following paths have been dirty since the prior session and are **not session work**:

- `Cargo.lock` (modified — pre-existing churn from Wave 10A's `tokio` dep being added behind a feature)
- 9 `apps/desktop/public/personas-previews/*/preview_voice.opus` files (auto-regenerated)
- ~36 untracked LoRA training checkpoint dirs under `planning/session_2026-04-26/training/checkpoints_v2..v9c/` + matching `eval_v*/` and `logs_v*/` subdirs

Leave them alone — Don or the harness handles them.

### What's queued (post-Wave-14 carry-forward, ranked by value)

Per the continuation handoff §"Carry-forward open items":

- **Wave 13a** — `packages/l5-files/` extend `StdFsExecutor` with `set_allowlist(...)` + `update_allowlist_from_paths(...)` + tests. **HIGHEST VALUE** — today every `files_*` invocation falls through to `FilesExecError::NotInScope` because Wave 11 wired the approval flow but Wave 14 left the executor with `default()` (empty allowlist). Single-layer.
- **Wave 13b** — `apps/desktop/` `AppState` constructs `StdFsExecutor` with an initial allowlist from active grants; subscribes to `GrantIssuedEvent` / `GrantRevokedEvent` and updates the executor's allowlist. Single-layer. Depends on 13a.
- **Wave 15** — Affordance gating on the Wave 14 radio (`allow_task` requires task lineage, `defer_draft` requires side-effecting capability). Needs `task_id_present: bool` + capability metadata on `ApprovalPayload`. Single-layer (apps/desktop). Medium value.
- **Wave 16** — DeferToDraft Turn-path UI. Add a dedicated `draft_only` `TurnOutcomeKind`; today the chat surface surfaces denied-shape on draft. Single-layer (apps/desktop). Medium value.
- **Wave 17** — OncePerSession outbound sync filter. Out of scope until the sync layer ships post-mobile.
- **Wave 18** — `L7_trust_ux_onboarding_system_design.md` §16 surgical sweep. Today's banner-only T4.7 pass acknowledges §16 is doctrine-§6-violating; surgical sweep is owed. Low priority — author-focused, not load-bearing.
- **Wave 19** — Doctrine §8 used-as-user verification on the Wave 14 modal via Playwright (`pnpm tauri dev` + `mcp__playwright__browser_*`). Owed before the modal ships to Don's daily-driver build.

GPU work is unblocked but **Don-driven**: `python tools/persona-reference-gen/__main__.py --persona aurora --batch <id>`.

### Reserved-for-Don items (do NOT resolve autonomously)

- Anything modifying `planning/01_product_doctrine.md` (coordinator-gated).
- New `packages/*/` or `apps/*/` directories (coordinator-gated).
- Spec gap #3 (forward-looking requirement IDs).
- Avatar / viseme / L3 social-behavior rendering decisions.
- Force-push or destructive git ops without explicit ask.
- Backup of release secret key (`C:\Users\dbhav\.aether\release-key\aether-release-ed25519.sk`) — needs an off-machine copy beyond the existing `I:/IsabelleData/_keys/` backup.

### Tip state to verify against `current_status.py`

- branch: `dev`
- tip: `189a087` (build(tools): add pre-commit hook mirroring CI's blocking lints)
- ahead of `@{u}`: 0 (pushed)
- CI: green (run `25199422814`, all 5 jobs)
- cargo `aether-desktop`: 327 passed
- cargo `aether-l5-policy`: 86 passed
- cargo `aether-l5-files`: 13 default / 28 with `--features std-fs`
- vitest: 279 passed / 25 files
- All 7 doc rot guards green
- Boundary lint: 0 violations across 13 crates / 9 engines / 4 shared infra

### Agent-dispatch boilerplate update

Every wave-prompt's "Hard constraints" section must now include:

> Run `bash tools/check-pre-commit.sh` before staging any commit. It must exit clean. Add to the verification step alongside `cargo build` / `cargo test` / `pnpm exec vitest run` / `pnpm exec tsc --noEmit`. The hook will also gate `git commit` automatically (committed at `tools/git-hooks/pre-commit`, wired via `core.hooksPath`).

### Pick up from the queue

Pick the highest-value next slice (Wave 13a or 13b, depending on whether the user has scoped Wave 13a as a separate sub-session). Dispatch via the Agent tool with `isolation: "worktree"`. Worktree branches push to origin; the coordinator (you) merges to `dev` after rebase. Push every commit. Report wave-by-wave outcomes back as they land.

That's self-contained — primes the read order, the lessons from the prior runs, the queue, and the hard rules. Run for hours from this.

## ▲▲▲ COPY UP TO HERE ▲▲▲

---

### Notes on this prompt's design

1. **Self-contained.** No reliance on memory continuity. The next session reads only the files cited.
2. **Read order is exact.** `current_status.py` first because it's authoritative — kills the stale-prompt drift pattern that bit yesterday 4 times.
3. **Pre-flight is mandatory.** The pre-commit hook is committed but `core.hooksPath` is per-clone — running `setup-hooks.sh` once is the unblock. The CI red-X recurrence pattern justified the redundancy.
4. **Hard rules are explicit, numbered, short.** Each one references an incident from the prior run so the next agent knows *why* the rule exists.
5. **Queue is ranked by value.** Wave 13a is highest-value because Wave 11/14 shipped the approval flow but files commands fall through to NotInScope without Wave 13. The carry-forward is real, not theoretical.
6. **Tip + state numbers** included so the next session can immediately validate that nothing has changed since this prompt was written. If the numbers don't match, a stale-prompt audit fires.

This prompt is written 2026-05-01 against tip `189a087`. If significant time passes before it's used, run `python scripts/current_status.py` first and update the tip / test counts above before pasting.
