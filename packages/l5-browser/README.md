# aether-l5-browser — L5 browser-automation capability surface

> **Status (T1.3 first impl slice):** Trait + types defined; default backend is a stub that returns `BackendDisabled`. Real Playwright subprocess wiring is a later slice.

This crate is the L5-gated browser-automation surface for Companion. It is not a *new* policy layer; it plugs additively into `aether_l5_policy::Capability` (variants `BrowserOpen`, `BrowserReadPage`, `BrowserExtractData`, `BrowserFillForm`, `BrowserUpload`, `BrowserDownload`, `BrowserSubmit`, `BrowserLoginReuse` already exist in L5).

## Surface

- `BrowserExecutor` (`src/executor.rs`) — the object-safe async trait every backend implements. Methods: `open`, `navigate`, `read_page`, `extract`, `fill_form`, `submit`, `close`.
- Value types (`src/types.rs`) — `SessionId`, `PageSnapshot`, `FormField`, `BrowserExecError`.
- `capability_for_method` (`src/capability_map.rs`) — maps method names to `aether_l5_policy::Capability` variants. The integration point where future Tauri commands check L5 policy **before** invoking the executor.
- `PlaywrightExecutor` (`src/playwright_stub.rs`, `playwright` feature) — default backend stub. Every method returns `BrowserExecError::BackendDisabled`.

## Features

- `default = []` — ships the trait + types + capability map only.
- `playwright` — additionally compiles the `PlaywrightExecutor` stub. The real Node-subprocess driver lands in a later slice.

## Wiring contract

L5 is the single writer for side effects (CLAUDE.md §1.5). The executor itself does NOT perform any policy check. Call sites:

1. Resolve a `Capability` via `capability_for_method(method_name)`.
2. Ask `aether_l5_policy::PolicyEngine` for a `Decision::Allow`.
3. Only on `Allow`, invoke the matching method on a `Arc<dyn BrowserExecutor>`.

`close` is intentionally ungated — releasing session resources must always be permitted (a denied close would leak browser processes).

## Approval mode by autonomy preset

| Preset | Open / Navigate / Read | Click / Fill | Submit / Login |
|---|---|---|---|
| Observer | Deny | Deny | Deny |
| Assistant | Ask | Ask | Ask |
| Operator | Auto (within approved scope) | Ask | Ask |
| Power User | Auto + per-session grants | Auto + per-session grants | Ask |

## Hard rules

- **Outside-list navigation drops to Ask in Operator.** The agent never silently navigates somewhere it wasn't told to.
- **No credential persistence.** OS keychain integration is a separate later slice with its own threat-model review.
- **Auto-submit is blocked** on financial / auth / purchase pages (Critical risk class per `planning/12_permissions_autonomy.md`). Power User can grant on a per-action basis only.

## Backend

Playwright via subprocess. Cross-platform, headless-safe, mature automation surface. Locked over WebView2 (Windows-coupling) and CDP-direct (re-implements what Playwright already does well). The current `PlaywrightExecutor` is structurally complete but every method returns `BackendDisabled`; the real Node-subprocess driver, IPC framing, and session map land in a later slice.

## What this crate does NOT do

- Real browser automation. The Playwright Node subprocess, IPC framing, and session lifecycle land in a later slice.
- Tauri commands. The wiring from Tauri command handlers through L5 policy and into `BrowserExecutor` is the next single-layer follow-up session under `apps/desktop/`.
- New approval modes. `ApprovalScope` ("Ask once per session / task") and "Draft only" land in `aether-l5-policy` directly per T1.3 §2.3.

## References

- `planning/plans/T1.3_browser_file_workflow_proposal.md` §2.1 — Approved coordinator proposal.
- `planning/plans/T1.3_approval_scope_design.md` — ApprovalScope design (out-of-scope for this slice).
- `planning/12_permissions_autonomy.md` — autonomy preset framework + risk classes.
- `aether_l5_policy::Capability` — the additive surface this crate plugs into.
- `tools/redteam/scenarios/browser_misuse/` — capability-specific adversarial scenarios; the credential-fill scenario stubbed in T2.2 unblocks once the real Playwright driver lands.
