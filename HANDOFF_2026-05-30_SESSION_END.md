# Handoff — 2026-05-30 session end

> To get current status, run `./scripts/current_status.sh` (or
> `python scripts/current_status.py`) — do not restate from memory.
> Repo beats prompt (Decision #32).

## Summary

Cold-resume session after ~28 days idle. Verified the baseline was
still green, then closed all three owed **Doctrine §8 used-as-user
gates** by standing up the repo's first Playwright e2e harness and
wiring it into CI as a blocking job. No product/doctrine changes; this
is verification + test-infra work on already-shipped UI.

The earlier `NEXT_SESSION_PROMPT_2026-05-17.md` is **superseded** — its
target tip `fa1c287` is an ancestor of the real tip; its Tier 1A/1B/1C
all shipped in the 05-02-dated tree. Commit author dates are scrambled
by a past rebase; trust ancestry, not dates.

## Commits (this session, all on `dev`, all pushed)

| SHA | Message |
|-----|---------|
| `c25ac93` | test(desktop): Wave 19 — Playwright used-as-user verification of Wave 14/15 approval modal |
| `c3338cd` | test(desktop): T2.4 + T2.3 — used-as-user verification of persona + autonomy pickers |
| `35e22d2` | ci: run desktop e2e (Playwright used-as-user) suite — advisory |
| `d8a5ca5` | ci: make desktop e2e job blocking — proven green on the runner |
| `471513a` | docs(handoff): 2026-05-30 session end |
| `db210cb` | docs(l3-presence): T4.2 — flip product-sense Aether → Companion in doc comments |
| `244b087` | test(desktop): T2.5 — used-as-user e2e for Trust drawer Memory tab |

Tip: `244b087`. `dev == origin/dev`. CI green (run 26702576249).

## Subsystem status

- Vision V1 — unchanged, closed, rot-guarded.
- Voice V1 — unchanged, closed, rot-guarded.
- Presence V1 — unchanged, closed, rot-guarded.
- Memory V2 — unchanged (step 5 landed earlier per T1.1). Trust-drawer
  Memory tab (T2.5) consolidated.
- Quality-Eval V1 — unchanged.
- **Desktop e2e harness — NEW.** `apps/desktop/e2e/` + `playwright.config.ts`.
  20 used-as-user scenarios, all green, enforced by a blocking CI job:
  - approval modal (Wave 19) — 9 scenarios
  - persona picker (T2.4) — 3 scenarios
  - autonomy preset picker (T2.3) — 4 scenarios
  - memory tab (T2.5) — 4 scenarios
- All three owed Doctrine §8 used-as-user gates are **retired** (approval
  modal, persona picker, autonomy picker), plus the memory tab hardened.
  All four UI surfaces verified for Don's daily-driver build.
- T4.2 (Aether→Companion docstring residue): l3-presence slice done;
  l4-router + l5-policy residue remains for a follow-up session.

## Check matrix (verified this session)

- `tools/check-pre-commit.sh` (cargo fmt + ruff) — PASS
- `cargo check --workspace` — PASS (2 harmless missing-doc warnings in
  `packages/l1-interaction/src/events.rs`)
- `cargo test --workspace -- --test-threads=1` — PASS (0 failures)
- `pnpm typecheck` (4 projects) — PASS
- `cd apps/desktop && pnpm exec playwright test` — 20 passed
- CI run `26702576249` (e2e blocking, 20 tests) — all 6 jobs success

Toolchain note: `cargo` is not on the bash PATH; it lives at
`/c/Users/dbhav/.cargo/bin/` (cargo 1.95.0). `export
PATH="/c/Users/dbhav/.cargo/bin:$PATH"` before any cargo command.

## Risks / alerts for next session

- **A. GPU / Aurora training is parked, not solved.** Decided path =
  clean-slate overnight (Option A, $0): close Isabelle + watchdog +
  heavy apps, run `Projects/ai-toolkit/TRAIN_AURORA_OVERNIGHT.bat`. It
  only needs an idle overnight window + a manual launch (clearing the
  box can't happen mid-interactive-session). Recipe/corpus/tooling all
  shipped; see `HANDOFF_2026-05-02_DAY_LORA_PIPELINE.md` §5.
- **B. e2e harness fidelity is mock-based.** The Tauri IPC is shimmed
  (`e2e/tauri-mock.ts`) — it verifies the frontend + App.tsx state
  machine, NOT the Rust command layer. Keep the mock in sync with the
  real command surface as commands change (it warns on unhandled
  invokes; `embeddings_readiness` currently falls through to the null
  default — fine, out of scope).
- **C. CI actions on Node 20** are deprecation-warned (forced to Node
  24 by 2026-06-16). Pre-existing across all jobs; bump
  `actions/checkout@v4` etc. when convenient. Non-blocking.
- **D. Two flaky Rust env-seam tests** (l6-persona dir, l4-router
  ollama) — pre-existing, pass under `--test-threads=1`. Not addressed.

## Next recommended work

1. **T4.2 docstring residue** in L3–L5 `packages/` (the only remaining
   parallel-software carryover; cosmetic, single-layer-per-session per
   CLAUDE.md §1.3).
2. GPU: launch the overnight Aurora train in the next idle window.
3. Optional: extend the e2e harness to the MemoryTab (T2.5) for a
   fourth §8 surface, and/or add a CI cache for the Playwright browser.

## Decisions log (new this session)

- #46. Desktop e2e verification uses a Playwright + Tauri-IPC-mock
  harness driving the Vite frontend in Chromium, not tauri-driver/
  WebDriver against the native shell. Rationale: addInitScript can
  install the IPC shim before bundle load; deterministic; CI-friendly
  on ubuntu-latest.
- #47. The e2e CI job is blocking (after one advisory proving run),
  matching the project's "tighten once green" convention.
- #48. GPU unblock path = clean-slate overnight (A), not cloud rental
  (cost) or FLUX-Schnell (quality risk). Claude's call under full
  technical authority; Don owns only the product bar.
