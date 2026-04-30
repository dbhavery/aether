# @aether/l5-browser

**Status:** Skeleton-only (T1.3 first slice, 2026-04-30). **Zero logic.** Implementation lands in follow-up PRs.

## What this crate is for

The L5-gated surface for browser-automation primitives Aether can perform on behalf of the user under the Operator / Power User autonomy presets. Each primitive will be a `Capability` declared additively under `aether-l5-policy`'s existing `Capability` enum, so the policy gate stays the single non-bypassable authorization point.

Planned primitives (per T1.3 §2.1):

- `BrowserOpen`
- `BrowserNavigate`
- `BrowserClick`
- `BrowserFillForm`
- `BrowserExtract`
- `BrowserScreenshot`

## Scope ceiling (locked)

From the T1.3 proposal §2.1:

- read + click + fill + extract
- **no** credential persistence
- **no** off-list navigation in Operator mode (must drop to Ask)
- **no** auto-submit on financial / auth / purchase pages (hard-blocked unless Power User + per-action confirm — Critical risk class per `planning/12_permissions_autonomy.md` §"Risk classes")

## Backend

**Playwright via subprocess** (locked, T1.3 §7). Cross-platform, mature, headless-safe. The Playwright dependency itself is not yet wired — it lands with the first implementation PR.

## Implementation not yet here

Per `CLAUDE.md` §3 (package-creation protocol), this commit is the skeleton step only:

- workspace `Cargo.toml` member entry
- empty `src/lib.rs` with module docs + placeholder `BrowserCapability` enum
- this README
- CODEOWNERS line

No functions, no Playwright dep, no IPC wiring, no Tauri commands. Those land in subsequent slices.

## Cross-links

- [`planning/plans/T1.3_browser_file_workflow_proposal.md`](../../planning/plans/T1.3_browser_file_workflow_proposal.md) — the approved coordinator proposal (Approved 2026-04-30)
- [`planning/12_permissions_autonomy.md`](../../planning/12_permissions_autonomy.md) — autonomy presets and risk classes
- [`packages/l5-policy/`](../l5-policy/) — sibling layer; capability declarations slot under its existing `Capability` enum

## Next slice

`packages/l5-files/` skeleton in a separate session per T1.3 §5.5 (two-skeleton-PR lock).
