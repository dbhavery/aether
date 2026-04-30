# aether-l5-browser — L5 browser-automation capability surface

> **Status:** Skeleton only. Implementation lands in follow-up PRs per the T1.3 sub-decisions.

This crate is the L5-gated browser-automation surface for Companion. It does not exist as a *new* policy layer; it is the additive set of capabilities that extends `aether_l5_policy::Capability` with browser primitives.

## Scope (frozen 2026-04-30)

Capabilities (added to the L5 enum in a follow-up PR):

- `BrowserOpen` — start a browser session.
- `BrowserNavigate` — navigate to a URL within an approved scope.
- `BrowserClick` — click a DOM element by selector or accessible role.
- `BrowserFillForm` — fill input fields. Submit goes through Ask in Operator.
- `BrowserExtract` — extract text/structured data from the live DOM.
- `BrowserScreenshot` — capture page state for the audit log.

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

Playwright via subprocess. Cross-platform, headless-safe, mature automation surface. Locked over WebView2 (Windows-coupling) and CDP-direct (re-implements what Playwright already does well).

## What this crate does NOT do

- Implementation. The capability primitives, the Playwright wrapper, the audit-row emission — all land in follow-up PRs. This crate only holds the type space + the doc surface so the workspace check passes.
- New approval modes. `ApprovalScope` ("Ask once per session / task") and "Draft only" land in `aether-l5-policy` directly per T1.3 §2.3.

## References

- `planning/plans/T1.3_browser_file_workflow_proposal.md` §2.1 — Approved coordinator proposal (status flipped 2026-04-30 under Don's "1–5 are your decisions now" delegation).
- `planning/12_permissions_autonomy.md` — autonomy preset framework + risk classes.
- `aether_l5_policy::Capability` — the additive surface where new variants land.
- `tools/redteam/scenarios/browser_misuse/` — capability-specific adversarial scenarios; the credential-fill scenario stubbed in T2.2 unblocks once the first impl PR lands.
