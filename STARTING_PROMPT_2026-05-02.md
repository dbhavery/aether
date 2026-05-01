# Clean-Session Starting Prompt — 2026-05-02

> Paste the block below into a fresh Claude session at `C:\Users\dbhav\Projects\aether`. It primes the next session with the read-order, the lessons from the prior 2026-05-01 autonomous run, the tip state, the queue (with Don-decisions called out), and the hard rules.

---

## ▼▼▼ COPY FROM HERE ▼▼▼

You are picking up the Aether/Companion repo (codename: aether, public name Companion) at `C:\Users\dbhav\Projects\aether` after a multi-session autonomous run. **The Files command flow is now end-to-end live for the first time** — Approve → grant issued → ExecutorAllowlistSink rebuilds the StdFsExecutor allowlist → replay invocation succeeds.

11 commits landed yesterday (2026-05-01) on `dev`, plus the prior session's 30 commits. The carry-forward queue is now down to **one owed engineering slice (Wave 19) and several Don-decision items**.

### Read in this exact order before doing anything else

1. `python scripts/current_status.py` — authoritative state. **Trust this over any prompt or older handoff.**
2. file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-01_FILES_FLOW_AND_DOCTRINE_SWEEP.md — the most recent handoff. Ultra-detailed; covers Waves 13a/13b/15/16/18 + drag-drop attachment research + lessons learned + carry-forward queue. **Supersedes** the narrower predecessor `HANDOFF_2026-05-01_FILES_FLOW_END_TO_END.md`.
3. file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-30_AUTONOMOUS_RUN_CONTINUATION.md — parent handoff (only for context on the prior wave outcomes; superseded by #2 above for state).
4. file:///C:/Users/dbhav/Projects/aether/CLAUDE.md — repo rules. **§1** (one-layer-per-session), **§3** (coordinator-gated package creation), **§8** (clickable links), **§9.5** (pre-commit hygiene; mandatory before any commit).
5. file:///C:/Users/dbhav/Projects/aether/planning/01_product_doctrine.md — §5/§6/§7/§8 are load-bearing.
6. file:///C:/Users/dbhav/Projects/aether/planning/plans/parallel_software_tracks.md — claimable work. **As of 2026-05-01 every Tier 1/2/4 entry has an evidence-backed status.** T1.3 is now fully DONE except for Wave 19 (Playwright used-as-user). Tier 3 finish-line items intentionally deferred per the doc's own rule.
7. file:///C:/Users/dbhav/Projects/aether/planning/research/2026-05-01_drag_drop_attachment_ux.md — drag-drop attachment UX research with 6 open questions for Don. Read if Don has answered any of them or wants to spec a phase.

### Pre-flight — MANDATORY before any commit

```bash
cd /c/Users/dbhav/Projects/aether
python scripts/current_status.py            # confirms tip + branch
git status --short                          # review pre-existing dirty state
bash tools/check-pre-commit.sh              # confirm cargo fmt + ruff clean
export PATH="/c/Users/dbhav/.cargo/bin:$PATH"  # cargo isn't on PATH by default in Git Bash
```

The pre-commit hook is already wired (commit `189a087`, dogfooded across 11 commits this session with zero failures). If `bash tools/setup-hooks.sh` hasn't been run on this clone, run it once. Every `git commit` then auto-runs the lint mirror; do NOT bypass with `--no-verify`.

### Hard rules from prior-run lessons

1. **Repo beats prompt.** 21 stale-prompt drift catches across the prior 3 sessions. Verify any "Available" / "Greenfield" / "pending" entry against `git log` + live code before doing it. If repo says it's already shipped, **refuse to redo, flag the doc-vs-repo gap, patch the doc** with evidence (commit shas + file paths).

2. **Worktree isolation for parallel dispatch — and verify the main checkout afterwards.** The `isolation: "worktree"` parameter on Agent dispatch sometimes leaves the main checkout's HEAD on the worktree branch after the agent finishes. After every dispatch: `git branch --show-current` to confirm you're on `dev` before merging. If not, `git checkout dev` first. Combined with explicit-path commits, the pattern is otherwise zero-incident.

3. **Explicit-path commits always.** `git commit -- <explicit paths>`. **Never** `git add -A`, `git add -u`, `git add .`. The pre-existing dirty paths (preview_voice.opus + LoRA training checkpoints) must NEVER be staged.

4. **One layer per session per CLAUDE.md §1.** A session touches at most one `packages/l*-*/` layer. `apps/desktop/` is its own scope and is treated as one layer. Cross-layer work splits into multiple agent dispatches.

5. **CI's blocking lints run before every commit.** `tools/check-pre-commit.sh` mirrors them locally (`cargo fmt --all -- --check` + `ruff check src/ tests/`). If the script fails, fix locally — never `--no-verify`. CI red-X means the email digest masks any blocking failure underneath; treat it as a session-ender.

6. **Doctrine §8 — frontend changes get used-as-user via automation** (Vite + Playwright) before shipping. Mocked vitest is necessary but not sufficient. For backend-only Rust slices, `cargo test` + the boundary lint is the floor.

7. **Doctrine sweeps stop at cross-doc inconsistencies.** When you tombstone a concept that appears in multiple docs (like Guest mode), check for conflicting framings before swinging the axe. The L7 §4.5 / L4 §912 Guest-mode contradiction is unresolved and is a Don-decision item — flag it, don't resolve it autonomously.

8. **Clickable links** — every user-facing path uses bare `file:///C:/...` URLs with forward slashes. No backticks, no markdown link syntax, no backslashes.

### Working-tree dirty state — DO NOT TOUCH

The following paths have been dirty since multiple prior sessions and are **not session work**:

- 9 `apps/desktop/public/personas-previews/*/preview_voice.opus` files (auto-regenerated)
- ~36 untracked LoRA training checkpoint dirs under `planning/session_2026-04-26/training/checkpoints_v2..v9c/` + matching `eval_v*/` and `logs_v*/` subdirs

Leave them alone — Don or the harness handles them.

### Tip state to verify against `current_status.py`

- branch: `dev`
- tip: should be the head after the 2026-05-01 handoff doc + research doc + this starting prompt all land. Pre-write tip was `a2358a7`. Confirm with `git log --oneline -3` after running `current_status.py`.
- ahead of `@{u}`: 0 (pushed)
- CI: green at last verification (Wave 18 main run cancelled mid-flight by superseding push but its blocking jobs all succeeded; subsequent runs green)
- cargo `aether-l5-files` with `--features std-fs`: 34 passed
- cargo desktop (from `apps/desktop/src-tauri`): 335 passed
- vitest from `apps/desktop/`: 288 passed / 25 files
- All 7 doc rot guards green
- Boundary lint: 0 violations across 13 crates / 9 engines / 4 shared infra

### What's queued

#### Tier 1 — Owed engineering slice

**Wave 19 — Doctrine §8 used-as-user Playwright verification on Wave 14/15 modal.**

- **Why:** Wave 14/15 modal is currently in "vitest-green but not used-as-user" state. Doctrine §8 explicitly requires used-as-user verification before frontend changes reach Don's review. Shipping the modal to Don's daily-driver build before this verification is a doctrine-§8 violation.
- **Approach:**
  1. `cd /c/Users/dbhav/Projects/aether/apps/desktop && pnpm tauri dev` (background; budget 30-90s startup)
  2. Find the Tauri webview URL (typically `http://localhost:1420` or similar) — watch dev server logs.
  3. Use `mcp__playwright__browser_navigate` + `mcp__playwright__browser_snapshot` to load the live shell.
  4. Drive a turn that triggers a `Files*` gate (e.g. via the chat composer typing "edit /tmp/foo.txt").
  5. Assert the modal renders with the correct radio options for the payload (per Wave 15 affordance gating).
  6. Click each option; verify the wire-shape `UserChoiceWire` emits correctly via Tauri command response.
  7. For the Approve path, verify the file is actually read (or written) — this exercises Wave 13b's allowlist plumbing end-to-end.
  8. For DeferToDraft, verify the Wave 16 amber bubble renders in the Transcript.
- **Deliverable:** test report + 1-2 commits if any bugs surface during verification; "doctrine-§8 verified" status update on Wave 14/15 in `parallel_software_tracks.md`.

#### Tier 2 — Don-decision items (do NOT resolve autonomously)

**A. L4 vs L7 Guest-mode doctrine inconsistency.** L7 §4.5 (Wave 18 follow-up) tombstoned "Guest mode" wizard surface. L4 §912 / §1083 preserve a "Guest" routing-tier concept. These may be the same thing (and L4 should also be tombstoned) or different things (Guest UX retired, Guest routing-tier survives). Don's call. Once decided, surgical sweep the loser.

**B. Drag-drop attachment phase scoping.** Research delivered at `planning/research/2026-05-01_drag_drop_attachment_ux.md`. Six open questions for Don in §5:

1. Clipboard-paste policy (no path → new `MediaUpload` capability vs. temp-dir-then-FilesRead?).
2. Approval timing (drop vs send; recommended: send, batched).
3. Allowlist scope shape (path / parent dir / extension; current Wave 13 plumbing is path-only — needs parent-dir mode for media folders).
4. Drop overlay copy tone ("will request FilesRead" — system-y vs plain English?).
5. `MediaUpload` capability scope (new or flag on `FilesRead`? covers TTS audio + persona reference images?).
6. Drop overlay behavior when ApprovalModal is already open (ignore or queue).

If Don answers and approves, the implementation is a multi-wave phase: Wave 20 (l5-policy `MediaUpload` capability + allowlist scope changes — single-layer packages/l5-policy), Wave 21 (apps/desktop Tauri drag-drop event handlers + temp-dir blob writer + new commands — single-layer apps/desktop), Wave 22 (apps/desktop overlay component + chip strip + composer button — single-layer apps/desktop, requires Wave 21 done), Wave 23 (Playwright used-as-user on the new flow). Estimated 4-6 waves total with the policy work being the first.

#### Tier 3 — Speculative / deferred (do NOT pick up unless Don redirects)

- **Wave 13c — task lineage threading.** Speculative until "tasks" become a system concept. Search for `task_id: None,` in `apps/desktop/src-tauri/src/{commands,browser_commands,files_commands}.rs` once tasks exist.
- **Wave 17 — OncePerSession outbound sync filter.** Out of scope until the sync layer ships post-mobile.
- **Smaller L2/L3/L4/L5/L6 doctrine residue sweeps.** Author-focused doc cleanup. None are load-bearing matrices like L7 §16 was. Worth a session when no engineering work is in flight.

#### Reserved for Don

- **Backup the release secret key.** `C:\Users\dbhav\.aether\release-key\aether-release-ed25519.sk`. Backed up to `I:/IsabelleData/_keys/aether-release-key-backup-2026-04-30/`. Make at least one more copy off-machine.
- **`tools/persona-reference-gen/`** Aurora reference batch — Don-driven (`python tools/persona-reference-gen/__main__.py --persona aurora --batch <id>`).
- **GPU queue** Aurora pipeline kickoff — Don-driven.
- **Run `bash tools/setup-hooks.sh` on any other clone** of this repo. Already installed on the current main checkout.

### Agent-dispatch boilerplate update

Every wave-prompt's "Hard constraints" section must include:

> Run `bash tools/check-pre-commit.sh` before staging any commit. It must exit clean. Add to the verification step alongside `cargo build` / `cargo test` / `pnpm exec vitest run` / `pnpm exec tsc --noEmit`. The hook will also gate `git commit` automatically (committed at `tools/git-hooks/pre-commit`, wired via `core.hooksPath`). If running cargo directly: `export PATH="/c/Users/dbhav/.cargo/bin:$PATH"` first — cargo isn't on PATH by default in Git Bash.

### Pick up from the queue

**Default priority: Wave 19 (Playwright used-as-user verification).** It's the only owed engineering slice and unblocks shipping the Wave 14/15 modal to Don's daily-driver build.

If Don has answered the drag-drop attachment open questions, dispatch Wave 20 (l5-policy `MediaUpload` capability) instead — that's the bigger value play.

If Don has resolved the L4 vs L7 Guest-mode inconsistency, knock out the resulting surgical sweep first (cheap, ~1 commit), then move to Wave 19.

For Wave 19 specifically: do NOT dispatch via Agent tool — the Tauri dev shell + Playwright orchestration is highly stateful and benefits from inline single-context execution. For Wave 20+ (drag-drop attachment phase), use Agent tool with `isolation: "worktree"` — single-layer scope makes worktree isolation worthwhile.

Worktree branches push to origin; the coordinator (you) merges to `dev` after rebase. Push every commit. Report wave-by-wave outcomes back as they land.

That's self-contained — primes the read order, the lessons from the prior runs, the queue (with Don-decision items called out), and the hard rules. Run for hours from this.

## ▲▲▲ COPY UP TO HERE ▲▲▲

---

### Notes on this prompt's design

1. **Self-contained.** No reliance on memory continuity. The next session reads only the files cited.
2. **Read order is exact.** `current_status.py` first because it's authoritative — kills the stale-prompt drift pattern.
3. **Pre-flight is mandatory.** The pre-commit hook is committed but `core.hooksPath` is per-clone — `setup-hooks.sh` is the unblock. The cargo PATH issue is documented because it bit twice this session.
4. **Hard rules are explicit, numbered, short.** Each one references an incident from the prior runs so the next agent knows *why* the rule exists. Eight rules now (was seven) — added the doctrine-sweep cross-doc-consistency rule.
5. **Queue is tiered.** Tier 1 = clear owed engineering work. Tier 2 = blocked on Don-decision. Tier 3 = speculative or deferred. The next agent should pick from Tier 1 by default and only touch Tier 2 if Don has answered. Tier 3 is documentation only — don't autonomously resolve.
6. **Tip + state numbers** included so the next session can immediately validate that nothing has changed since this prompt was written. If the numbers don't match, a stale-prompt audit fires.

This prompt is written 2026-05-01 night against tip ~`a2358a7` (pre-handoff-write). If significant time passes before it's used, run `python scripts/current_status.py` first and update the tip / test counts above before pasting.
