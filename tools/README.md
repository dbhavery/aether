# tools/

Developer and agent tooling. Each subdirectory is a single-purpose tool with its own README, config, and (eventually) entry point.

## Wave 1 scaffolds

| Tool | Purpose | Status |
|---|---|---|
| `lint-layer-boundaries/` | Enforce the no-sibling-layer-import rule (Rust `cargo-deny` + TS ESLint rule) | Config skeleton + README |
| `lint-policy-bypass/` | Reject direct executor calls outside `packages/l5-policy` | Rules-doc skeleton |
| `ts-bindings-gen/` | `ts-rs`/`specta` codegen from Rust → `packages/types/` | Placeholder |

Real implementations land in Wave 2+ (boundary + codegen).

## Package-creation protocol reference

Adding a new tool follows the same protocol as adding a package — see `CLAUDE.md` §3. Propose in planning first, scaffold after approval.
