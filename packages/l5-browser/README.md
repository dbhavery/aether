# aether-l5-browser — L5 browser-automation capability surface

> **Status:** Trait + types defined. `PlaywrightExecutor` is now a real Node-subprocess driver behind the `playwright` feature; default builds remain dependency-light.

This crate is the L5-gated browser-automation surface for Companion. It is not a *new* policy layer; it plugs additively into `aether_l5_policy::Capability` (variants `BrowserOpen`, `BrowserReadPage`, `BrowserExtractData`, `BrowserFillForm`, `BrowserUpload`, `BrowserDownload`, `BrowserSubmit`, `BrowserLoginReuse` already exist in L5).

## Surface

- `BrowserExecutor` (`src/executor.rs`) — the object-safe async trait every backend implements. Methods: `open`, `navigate`, `read_page`, `extract`, `fill_form`, `submit`, `close`.
- Value types (`src/types.rs`) — `SessionId`, `PageSnapshot`, `FormField`, `BrowserExecError`.
- `capability_for_method` (`src/capability_map.rs`) — maps method names to `aether_l5_policy::Capability` variants. The integration point where future Tauri commands check L5 policy **before** invoking the executor.
- `PlaywrightExecutor` (`src/playwright_stub.rs`, `playwright` feature) — default backend. Spawns a long-lived Node child running `scripts/driver.mjs` and frames JSON-lines requests/replies across stdin/stdout.

## Features

- `default = []` — ships the trait + types + capability map only. No tokio process / tracing / subprocess deps.
- `playwright` — additionally compiles the `PlaywrightExecutor` real Node-subprocess driver. Pulls `tokio` (`process` + `io-util`) and `tracing` for child-lifecycle logging.

## Runtime requirements (`playwright` feature)

The Rust side spawns `node packages/l5-browser/scripts/driver.mjs`. The host running the executor must have:

1. **`node` on PATH** — any reasonably recent Node (≥ 18). The driver script uses ES modules (`.mjs`), top-level `await`, and `node:crypto`.
2. **`playwright` installed** in a `node_modules` resolvable from the script path (typically: install in the consuming workspace's scripts root with `npm install playwright`, then run `npx playwright install chromium` once to fetch the browser binary).

If either prerequisite is missing the executor degrades gracefully — it does **not** panic:

- Missing `node` / driver-script-not-found at construction → `PlaywrightExecutor::new()` succeeds but enters a "disabled" state. Every gated method returns `BrowserExecError::BackendDisabled`. `close()` returns `Ok(())` (cleanup must always succeed).
- Playwright not installed → the Node side surfaces a structured `{err, kind: "Internal"}` on the first `open()`; the Rust side returns `BrowserExecError::Internal` with the message.

## Wire protocol (driver IPC)

JSON-lines, one object per line, both directions:

```
request:  {"req_id": <int>, "op": <string>, "args": {...}}
ok reply: {"req_id": <int>, "ok": <op-specific-value>}
err reply:{"req_id": <int>, "err": "<message>", "kind": "<variant>"}
```

`kind` strings map onto `BrowserExecError` variants verbatim: `Navigation`, `SelectorNotFound`, `SessionNotFound`, `Timeout`, `Internal`. Unknown kinds fall through to `Internal`.

Per-request wall-clock budget: 10 s. Exceeding it returns `BrowserExecError::Timeout` and unregisters the in-flight slot.

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
- **Auto-submit is blocked** on financial / auth / purchase pages (Critical risk class per `ARCHITECTURE.md` and the risk-class definitions in `docs/adr/`). Power User can grant on a per-action basis only.

## Backend

Playwright via subprocess. Cross-platform, headless-safe, mature automation surface. Locked over WebView2 (Windows-coupling) and CDP-direct (re-implements what Playwright already does well). One Node child per `PlaywrightExecutor`; one `BrowserContext` per `SessionId` (isolated cookies/storage). `Drop` triggers best-effort `start_kill` and the executor was spawned with `kill_on_drop` set, so abandoned executors don't leak browser processes.

## What this crate does NOT do

- Tauri commands. The wiring from Tauri command handlers through L5 policy and into `BrowserExecutor` lives in `apps/desktop/` (already shipped — see commits `f8c22d4`..`54776ef`).
- New approval modes. `ApprovalScope` ("Ask once per session / task") and "Draft only" land in `aether-l5-policy` directly per T1.3 §2.3.
- Credential persistence. OS-keychain integration is a separate later slice with its own threat-model review.

## References

- `ARCHITECTURE.md` — the L5 policy layer, browser capability, and the approved browser/file workflow.
- `ARCHITECTURE.md` + `docs/adr/` — ApprovalScope design and the autonomy preset framework + risk classes.
- `aether_l5_policy::Capability` — the additive surface this crate plugs into.
- `tools/redteam/scenarios/browser_misuse/` — capability-specific adversarial scenarios; the credential-fill scenario stubbed in T2.2 unblocks once the real Playwright driver lands.
