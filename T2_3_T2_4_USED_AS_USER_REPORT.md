# Doctrine §8 used-as-user verification — T2.3 + T2.4

> Closes the gap that the existing `apps/desktop/src/components/SettingsDrawer.test.tsx` mocked-vitest coverage leaves open. Doctrine §8 mandates *frontend changes get used-as-user via automation* — diff-only or unit-tests-only is not sufficient. This report records that verification for **T2.3 (Autonomy preset picker)** and **T2.4 (Persona switcher)**.

- **Date:** 2026-04-30
- **Branch / tip:** `worktree-agent-aab31793adb46bd32` @ `70786a2`
- **Scope:** Read-only verification. No production code modified.
- **Components under test:** file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/SettingsDrawer.tsx and file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/PersonaSection.tsx
- **Existing mocked coverage:** file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/SettingsDrawer.test.tsx and file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/PersonaSection.test.tsx

---

## 1. Approach

**Vite dev server + Tauri-IPC mock + Playwright.** Full Tauri build is heavy and not needed for UI logic verification, so we drove the production React tree through a thin harness.

Files added (test fixtures only — never bundled into a release build):

- file:///C:/Users/dbhav/Projects/aether/apps/desktop/used_as_user.html — minimal HTML entry consumed by Vite dev. Production `index.html` does not reference it.
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/test/harness_entry.tsx — installs `@tauri-apps/api/mocks`'s `mockIPC()` *before* the React tree mounts so every `invoke()` from `lib/api.ts` resolves against the harness handler. Mounts the production `SettingsDrawer` (which embeds `PersonaSection`). Exposes `window.__HARNESS_RESET__` + `window.__HARNESS_CALLS__` so Playwright can flip scenarios and assert IPC traffic without re-mounting Vite.
- file:///C:/Users/dbhav/Projects/aether/tools/used-as-user/screenshots/ — 9 PNGs captured by the Playwright MCP browser.

Vite dev server was started with `npx vite --port 5180 --strictPort --host 127.0.0.1` from `apps/desktop/`. `node_modules` was junction-linked from the main worktree (`C:/Users/dbhav/Projects/aether/{,apps/desktop/}node_modules/`) so this worktree could share dependencies without a heavy `pnpm install`.

The Playwright MCP browser then drove the harness page directly. Each interaction was followed by an `evaluate()` introspection of `window.__HARNESS_CALLS__` (the list of every `invoke()` the React tree fired) and the live DOM (`aria-checked`, `disabled`, error-banner text).

Aborted alternatives considered:

- **Browser-vitest provider** — would have required installing `@vitest/browser` + a browser binding; not present in the lockfile, and the Vite-dev path is faster.
- **Full `pnpm tauri:dev` build** — explicitly excluded by the prompt; 5–15 min cargo build for no incremental signal over Vite + IPC mock.

---

## 2. Pass / fail per assertion

### T2.3 — Autonomy preset picker (file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/SettingsDrawer.tsx — `AutonomyRow`)

| # | Assertion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Drawer renders Autonomy section with all four choices (Observer / Assistant / Operator / No override) | PASS | snapshot 08; radiogroup `aria-label="Autonomy preset"` present, four `[role=radio]` children |
| 2 | Backend value `"assistant"` → Assistant radio `aria-checked="true"` on mount | PASS | snapshot 08, `Active preset: Assistant` |
| 3 | Click Operator → `set_autonomy_preset` invoked with `preset: "operator"`, Operator `aria-checked` flips to `true` | PASS | screenshot 02; `__HARNESS_CALLS__` contains `{cmd:"set_autonomy_preset", payload:{preset:"operator"}}` |
| 4 | Click Observer → `set_autonomy_preset` invoked with `preset: "observer"` | PASS | screenshot 03; calls log entry confirms |
| 5 | Click "No override" → `set_autonomy_preset` invoked with `preset: null` (overlay cleared, *not* the wire string `"later"`) | PASS | calls log entry `{cmd:"set_autonomy_preset", payload:{preset:null}}` |
| 6 | Backend value `null` → "No override" radio `aria-checked="true"` on mount (the `autonomyChoiceFromBackend` mapping) | PASS | screenshot 04; only the No-override radio is checked |
| 7 | Backend `set_autonomy_preset` rejection surfaces a visible error banner | PASS | screenshot 05b; banner text `Error: backend rejected: unknown autonomy preset (harness)` |
| 8 | Radios stay disabled until `current_autonomy_preset` resolves | PASS (existing unit test) — not separately replayed in browser since the busy-load gate is the same code path that vitest already exercises. The harness reset path proves the row re-mounts cleanly when the resolved promise lands. |

### T2.4 — Persona switcher (file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/PersonaSection.tsx)

| # | Assertion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | PersonaSection renders at the top of the drawer (before Media) — T2.4 placement | PASS | snapshot shows `region "Persona"` precedes `region "Media"` |
| 2 | Catalog of 2 installed personas + 7 preview-only personas renders correctly tagged (Active marker on Aurora; "Preview only" tag on bundled-but-not-installed entries) | PASS | screenshot 01 + snapshot; bundled previews loaded from `apps/desktop/public/personas-previews/index.json` (no synthetic fixture — real preview catalog is what the user sees) |
| 3 | "Memory continuity" caption visible (ADR-0001: memory is user-keyed, not persona-keyed) | PASS | two captions rendered: section intro `"Pick which companion you talk to. Your memory stays with you across personas — only the voice, name, and stance change."` and section outro `"Your memory stays with you across personas."` |
| 4 | Click "Switch" on Marcus Chen → `switch_persona` invoked with `id: "marcus_chen"`, active marker moves from Aurora to Marcus | PASS | screenshot 06; `__HARNESS_CALLS__` contains `{cmd:"switch_persona", payload:{id:"marcus_chen"}}`; live DOM shows Aurora row → "Switch", Marcus row → "Active" badge + checked radio |
| 5 | Click "Install full pack" on a preview-only entry with `VITE_PERSONA_MANIFEST_BASE` unset → graceful error explaining the registry isn't configured (rather than firing a doomed network request) | PASS | error banner text `"Persona registry isn't configured for this build. Set VITE_PERSONA_MANIFEST_BASE at build time to enable Tier-2 downloads."` |
| 6 | `list_personas` rejection surfaces `role="alert"` error banner | PASS | screenshot 07; alert text `"Error: backend rejected: list_personas failed (harness)"` |
| 7 | Install-then-switch end-to-end (Tier-2 path) | NOT EXERCISED in this run — `personaManifestUrl()` returns null without `VITE_PERSONA_MANIFEST_BASE`, so the install path is gated behind a build-time env. This is the same gap T1.5 / the autonomous-build handoffs already track (real key swap + ureq fetch + Tauri command — see file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-29_FULL_AUTONOMOUS_BUILD.md). Mocked-vitest in `PersonaSection.test.tsx` covers the install-success contract; live used-as-user verification of that path needs a build with the env set. **Flagged for Don.** |

---

## 3. Real findings (highest-value output of doctrine §8)

These are the bugs / friction the unit tests do not catch because mocked-vitest is decoupled from the live DOM accessibility tree.

### Finding A — Persona switch radios have a non-descriptive accessible name

**Severity:** medium (a11y / SR UX). Not a functional bug.

**Where:** file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/PersonaSection.tsx around lines 290-303.

The "Switch" / "Active" button is rendered as `role="radio"` inside the `radiogroup aria-label="Active persona"`, but the only text content of the button is `"Switch"` or `"Active"` (or `"Switching…"`). There is no `aria-label` on the radio itself, so screen readers announce *"Switch radio button, not checked"* for Marcus instead of *"Marcus Chen radio button, not checked"*.

The persona's display name is rendered in a sibling `<div>` outside the button, which a screen reader reads as separate static text — it is not part of the radio's accessible name.

**Fix sketch:** add `aria-label={r.display_name}` to the radio button (and probably move the `aria-label` off the radiogroup so each radio carries its own name; the radiogroup already has a heading via `aria-labelledby="settings-persona-heading"` — wait, no, it has its own `aria-label="Active persona"` on the `<ul>`). Either way: each radio needs an accessible name = persona display name.

This will also surface in the `getByRole('radio', { name: 'Marcus Chen' })` style of test, which currently fails — the existing test uses a different selector to work around it.

### Finding B — `PersonaSection` shows "Loading personas…" indefinitely after `list_personas` rejects

**Severity:** medium. User-facing confusion.

**Where:** file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/PersonaSection.tsx lines 225-227 vs. lines 116-148.

When `list_personas()` rejects, `setErr(...)` runs but `catalog` stays `null`. The render path checks `!rows && <p>Loading personas…</p>`, so the user sees both:

1. The red error banner at the top (`role="alert"`).
2. The persistent `"Loading personas…"` message.

A user reading the section sees an error *and* "Loading…" simultaneously, which suggests the section might still recover. It will not — there is no retry trigger.

**Fix sketch:** swap the rows-null guard to also check `err === null`, or render a "Couldn't load personas" empty state with a retry button. Same applies to the preview catalog rejection branch (which is already softer because previews fall back to `[]`).

### Finding C — Drawer error banner is shared across sections

**Severity:** low. Cosmetic / discoverability.

**Where:** file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/SettingsDrawer.tsx — single `err` state at line 84 is consumed by every section's catch block.

When a user clicks Operator and the backend rejects, the error banner appears at the **top** of the drawer (above PersonaSection), not next to the Autonomy section. If the user has scrolled to Autonomy, the failure is visually invisible to them — they see the radio bounce back without explanation. PersonaSection has its own scoped `<div role="alert">`; the rest of the drawer should follow that pattern.

**Fix sketch:** local `err` state per section, mirroring how `PersonaSection` already does it. Or scroll the error banner into view on append.

### Finding D — Unmodified `aria-label` on Active persona radiogroup

**Severity:** info. Note for the next pass.

The `<ul role="radiogroup" aria-label="Active persona">` is correct, but combined with Finding A it means the radios under it inherit no announceable identity. Once Finding A is fixed, consider whether the aria-label on the radiogroup should change to "Choose persona" since "Active persona" reads like a status header to a screen reader.

---

## 4. Screenshots

All under file:///C:/Users/dbhav/Projects/aether/tools/used-as-user/screenshots/

- file:///C:/Users/dbhav/Projects/aether/tools/used-as-user/screenshots/01_initial_assistant_aurora.png — drawer on first open: PersonaSection at top with Aurora active, Marcus shown as a switch target, 7 preview-only personas. Active autonomy seed: Assistant.
- file:///C:/Users/dbhav/Projects/aether/tools/used-as-user/screenshots/02_autonomy_operator_selected.png — Autonomy section after clicking Operator. Active-preset chip flipped to "Operator" / amber.
- file:///C:/Users/dbhav/Projects/aether/tools/used-as-user/screenshots/03_autonomy_observer_selected.png — same after clicking Observer. Active-preset chip "Observer" / green; copy line "Read-only — watches and answers, never acts."
- file:///C:/Users/dbhav/Projects/aether/tools/used-as-user/screenshots/04_autonomy_no_override_selected.png — backend value `null` boots the row to "No override" — proves the `null → "later"` UX mapping in `autonomyChoiceFromBackend`.
- file:///C:/Users/dbhav/Projects/aether/tools/used-as-user/screenshots/05_autonomy_error_state.png — view scrolled to Autonomy after a `set_autonomy_preset` rejection. **The error banner is NOT visible here** — proves Finding C: the error rendered far away from the failed click.
- file:///C:/Users/dbhav/Projects/aether/tools/used-as-user/screenshots/05b_autonomy_error_top.png — same scenario, scrolled to drawer top. Error banner visible above PersonaSection.
- file:///C:/Users/dbhav/Projects/aether/tools/used-as-user/screenshots/06_persona_switched_to_marcus.png — after clicking Switch on Marcus Chen. Aurora row now shows "Switch" (no longer Active), Marcus shows the Active badge.
- file:///C:/Users/dbhav/Projects/aether/tools/used-as-user/screenshots/07_persona_section_load_error.png — `list_personas` rejected. Shows Finding B: "Loading personas…" persists alongside the error alert.
- file:///C:/Users/dbhav/Projects/aether/tools/used-as-user/screenshots/08_autonomy_section_in_drawer_context.png — Autonomy section rendered in its drawer context, showing T2.3 placement between Microphone and Presence.

---

## 5. Anything ambiguous left for Don

- **Tier-2 install path (assertion 7 in §2)** is gated behind `VITE_PERSONA_MANIFEST_BASE`. Used-as-user verification of the full download → install → auto-switch flow needs a build with that env set + a real registry, which is the same dependency T1.5 / the autonomous-build handoff already tracks. Recommend rolling the live install verification into the same session that swaps the fixture pubkey for the real release pubkey.
- **Finding A (a11y)** crosses the line between "test fixture catches it" and "live used-as-user catches it." The mocked vitest passes today because it queries by `getByRole('radio', { name: 'Switch' })`, which is exactly the wrong accessible name for a real user with assistive tech. Worth a small follow-up commit — single `aria-label={display_name}` on the button. I did **not** fix it here per the read-only constraint.
- **Findings B + C** are honest UX bugs the unit tests cannot see. Both are fixable in <20 LOC. Recommend they ride into the same wave that polishes T2.3 / T2.4.
- **`Switching…` / `Installing…` busy-state visuals** were not exercised because the harness `install_persona` / `switch_persona` mocks resolve too fast for the human eye. Slow them with a `setTimeout(250)` (already done for `install_persona` — but the `Install full pack` button never reaches the loading state in this run because the personaManifestUrl gate trips first).
