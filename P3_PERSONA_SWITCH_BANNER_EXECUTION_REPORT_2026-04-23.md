# P3 Execution Report — Persona-switch system-message banner

**Date:** 2026-04-23
**Scope:** `apps/desktop/` — make the existing session reset on persona
change explicit in the UI by emitting a system-role transcript line so
the user sees *why* the transcript just cleared.

## Summary

- `commands::switch_persona` now:
  1. snapshots the outgoing persona display name,
  2. swaps the active engine / clears session state (pre-existing
     behaviour),
  3. appends a system-role `TurnMemoryRecord` to session memory
     carrying the banner text,
  4. returns the usual banner payload.
- Banner copy is produced by a pure `persona_switch_banner_text(old,
  new)` helper so tests can lock the exact wording and future i18n can
  swap it. Current format:
  `"Session reset because you switched to <new>. Previous context with <old> cleared."`
- A failed memory append is logged at WARN level but does not fail the
  command — the persona swap itself has already committed and must not
  be rolled back over a UI-only concern.
- Frontend: `App.tsx::handleSwitchPersona` replaces its unconditional
  `setMessages([])` with a `memoryRecent()` fetch so the new persona's
  transcript opens on the banner instead of an empty scroll.

## Tests

Two new `commands.rs::tests`:

1. `persona_switch_banner_references_both_names` — locks the copy so
   future changes surface explicitly (outgoing + incoming persona
   names, "reset", "cleared").
2. `switch_persona_records_system_banner_in_memory` — seeds one user
   turn, simulates the command body (switch_persona + append banner),
   and asserts the resulting `recent(session)` window contains exactly
   one record whose role is `System` and whose content matches the
   banner helper output.

## Behaviour change

The UX contract shifts from *"persona swap silently empties the
transcript"* to *"persona swap clears history and tells the user it
did."* The session reset itself is unchanged — we are not preserving
turns across persona boundaries; that's a deliberate trust-surface
decision from earlier waves. The banner simply removes the surprise.

## Checks run

| Command | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo test --workspace` | all green |
| `cargo test -p aether-l2-memory --features sqlite-backend` | 5/5 ok |
| `apps/desktop/src-tauri && cargo test` | 19/19 ok (up from 17) |
| `python tools/lint-layer-boundaries/check.py` | OK (0 violations) |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm build` | clean |

## Risks / notes

- The banner is stored in the session memory store, so the durable
  SQLite backend now carries it across restarts. That is consistent
  with every other transcript line and means reopening the app surfaces
  the last persona switch even if the user forgot they made it.
- If the memory store is ever replaced with a store that rejects the
  `System` role, this path would warn-and-continue rather than fail
  the persona switch. Any future store must preserve the existing
  `MemoryRole::System` contract.
- Frontend does *not* dedupe if memory already contained the banner
  (e.g. re-rendering after a reopen). That's acceptable — the banner
  is append-only along with the rest of the transcript.

## Next (per handoff)

P4 (optional) — Retention policy for durable memory. Either rolling
N-day retention at boot, or an explicit "Forget everything older than
X" UX action. Scope a design note if the implementation feels too
large for one slice.
