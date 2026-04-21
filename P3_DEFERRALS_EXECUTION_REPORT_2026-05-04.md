# P3 — Documented deferrals (continuation): ts-rs id codegen + remote vision privacy (2026-05-04)

**Status:** Docs only. No code change.

## Why these are still deferred

Both deferrals from the 2026-05-03 report still hold. This update
does not re-litigate them; it confirms nothing has changed and
restates the trigger conditions for picking them up.

See [P3_DEFERRALS_EXECUTION_REPORT_2026-05-03.md](file:///C:/Users/dbhav/Projects/aether/P3_DEFERRALS_EXECUTION_REPORT_2026-05-03.md)
for the full rationale and likely approach for each.

---

## Deferral 1 — `ts-rs`-style codegen for vision provider ids

### Status update

- TS dedup remains complete via `apps/desktop/src/lib/visionProviders.ts`.
- Rust adapters still declare their ids independently.
- Still only **two** vision adapters in the workspace.

### Trigger condition

Pick this up when a third vision adapter is being scoped. Any
attempt to wire a third adapter without codegen first is the wrong
order — the cost curve has flipped at three sources.

---

## Deferral 2 — Remote-vision privacy posture

### Status update

- Still no remote vision adapter in the workspace.
- Image bytes remain transient in memory; durable-memory privacy
  posture for images unchanged.
- The seven open questions captured in the 2026-05-03 report are
  unanswered (intentionally — answers belong with the adapter that
  forces them).

### Trigger condition

Pick this up when a remote vision adapter is the next piece of
vision-track work. The privacy spec lands alongside (or just
before) that adapter, not as a series of small drive-bys.

---

## Hard-constraint compliance

- No push.
- No code change in this report.
