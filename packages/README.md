# packages/

Reusable libraries — shared infra + the 7 must-own layer packages. Wave 1 has scaffolded the shared infra only.

## Wave 1 scaffolds (present)

| Package | Kind | Status |
|---|---|---|
| `event-bus/` | Rust crate | Shapes only |
| `storage/` | Rust crate | Layout type only |
| `media-engine/` | Rust crate | Placeholder data types |
| `telemetry/` | Rust crate | Sink mode enum |
| `types/` | TS package | Hand-written mirror stubs |
| `ui-kit/` | TS package | Design tokens placeholder |

## Wave 2 targets

| Package | Kind | Owner |
|---|---|---|
| `l5-policy/` | Rust crate (+ `l5-policy-ts/`) | L5 agent |
| `l6-persona/` | Rust crate (+ `l6-persona-ts/`) | L6 agent |

See `planning/planning/monorepo_plan_draft.md` §2 for the full layer-to-package mapping.

## Adding a new package

Follow the protocol in `CLAUDE.md` §3 — planning PR first, coordinator approval, then scaffold PR.
