# @aether/l5-policy-ts

**Status:** Wave 2 hand-written mirror. **Rust is source-of-truth.**

TypeScript facade over `packages/l5-policy`. Provides stable type shapes and the 16-command IPC surface so L7 / `apps/desktop` can compile against L5 contracts before the Rust-to-TS generator ships.

## Rules

- **Do not extend by hand once `tools/ts-bindings-gen/` lands.** The generator will produce this package wholesale from `#[derive(ts_rs::TS)]` annotations on the Rust structs; any hand edits after that will be overwritten.
- **Types only.** No runtime behavior, no `invoke` wrappers. The thin `invoke<K extends keyof PolicyCommands>(k, ...)` helper is an `apps/desktop` concern.
- **Match Rust structure module-by-module.** This keeps the generator replacement mechanical.

## Layout

```
packages/l5-policy-ts/
├── package.json      — pnpm workspace member, depends on @aether/types
├── tsconfig.json
├── README.md
└── src/
    ├── index.ts      — re-exports
    ├── decision.ts   — Decision + Capability + Approval + DenyReason (+ Decision 3/4 items)
    ├── support.ts    — ActionRequest + Grant + Audit + posture + BYOK
    └── commands.ts   — PolicyCommands interface (16 commands)
```

## Locked-decision footprint

- Decision 1: `Decision.tag === "NeedsUpgrade"` is a top-level variant (not nested inside `Deny`).
- Decision 2: `Decision.DraftOnly.source ∈ { "System" | "UserChoice" }`; `UserChoice.tag === "DeferToDraft"` is present.
- Decision 3: `Capability.kind ∈ { "AuditExport", "CostCapAdmin" }`; `policy.export_audit`, `policy.set_cost_cap`, `policy.reset_cost_counter` exposed in `PolicyCommands`.
- Decision 4: `RE_EVAL_TRIGGERS` array of length 8.
- Decision 5: `CostCap`, `CostWindow`, `policy.set_cost_cap` / `policy.reset_cost_counter` surfaced as re-auth-gated commands (re-auth enforcement lives in Rust).

## Next wave

Wave 3 introduces `tools/ts-bindings-gen` and regenerates this package. Hand edits stop there.
