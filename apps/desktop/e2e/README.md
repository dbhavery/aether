# Desktop e2e — used-as-user verification harness

Playwright suite that satisfies the **Doctrine §8 "used-as-user"** gate
for the desktop shell: it drives the real Vite-served React frontend in
Chromium and exercises each UI surface the way a user would, asserting
both visible behaviour and the IPC the app emits.

This is the layer the `vitest` + React-Testing-Library suite (jsdom)
cannot reach: real DOM, real CSS visibility/layout, real focus and
keyboard wiring, and the full `App.tsx` state-machine path.

## Run it

```bash
cd apps/desktop
pnpm exec playwright test                 # all specs
pnpm exec playwright test approval-modal  # one spec
```

`playwright.config.ts` boots `pnpm dev` (Vite on :1420) as the
`webServer`. CI runs the same thing as a **blocking** job
(`.github/workflows/ci.yml` → `e2e`).

## How the Tauri IPC is mocked

A browser has no Tauri runtime, so `tauri-mock.ts` installs a
`window.__TAURI_INTERNALS__` shim via Playwright `addInitScript`
(**before** the bundle loads — the app calls `companion_banner` /
`presence_current` / `list_personas` on mount). The shim matches the
`@tauri-apps/api@2.10.1` `core.js` contract: `invoke(cmd, args, options)`
delegates to `__TAURI_INTERNALS__.invoke`, events ride `transformCallback`
+ `plugin:event|*`, and `_unlisten` needs
`__TAURI_EVENT_PLUGIN_INTERNALS__.unregisterListener`.

Every `invoke` is recorded to `window.__MOCK_CALLS__` so tests assert
the exact command + args the UI sent (`readCalls` / `readResolveChoice`).

Unhandled commands log a `[tauri-mock] unhandled invoke: …` warning and
return `null` — grep your test output for these when adding a spec that
touches a new command, then add a handler.

## `installTauriMock(page, config)`

Call **before** `page.goto("/")`. Config (all optional):

| field | purpose |
|-------|---------|
| `approval` | payload `submit_turn` raises → exercises the approval modal |
| `personas` | catalog (`≥2` surfaces the header persona `<select>`); first is active. `switch_persona` is **stateful** so a post-switch `companion_banner` re-fetch reports the new persona |
| `initialAutonomy` | value `current_autonomy_preset` returns |
| `memory` | per-domain Memory-tab store; **stateful** (forget removes, edit rewrites). Auto domains mutate directly; `risk: "ask"` domains return `requires_approval` then mutate on `*_after_approval` |
| `freshUser` | skip the three first-run gate-seed keys so the onboarding flow (wizard → disclosure → preset) renders. Default `false` (gates pre-acked → land on chat) |

By default the mock seeds the three onboarding gates
(`aether.persona.last`, `aether.disclosure.acknowledged`,
`aether.onboarding.autonomy-preset(.version)`) so a spec lands directly
on the chat surface.

## Specs

| file | surface |
|------|---------|
| `approval-modal.spec.ts` | Wave 14/15 approval modal (Wave 19) |
| `persona-picker.spec.ts` | header persona switcher (T2.4) |
| `autonomy-preset.spec.ts` | Settings autonomy radiogroup (T2.3) |
| `memory-tab.spec.ts` | Trust-drawer Memory tab (T2.5) |
| `onboarding-flow.spec.ts` | first-run wizard → disclosure → preset |
| `turn-outcome.spec.ts` | chat reply + "no silent fallback" error surface |
| `media-permission.spec.ts` | Settings camera/screen/mic permission gates |
| `capture-panels.spec.ts` | Camera/Screen/Voice panel permission gating (fake media) |

## Adding a spec

1. `installTauriMock(page, { … })` with the config your surface needs,
   then `page.goto("/")`.
2. Drive the UI with role-based locators (`getByRole`), not CSS classes.
3. Assert visible behaviour **and** `readCalls(page)` for the IPC.
4. If you see an `unhandled invoke` warning, add a handler in
   `tauri-mock.ts` returning a shape that mirrors `src/lib/types.ts`.

Outputs (`e2e/.report/`, `e2e/.artifacts/`) are git-ignored.
