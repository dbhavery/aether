# tools/lint-layer-boundaries

**Status:** Wave 1 scaffold — config skeleton only. No enforcement yet.

Enforces the core boundary rule: sibling `packages/l*-*` crates/packages never import each other. Coordination must go through `packages/event-bus` or through `packages/l5-policy` / `packages/l6-persona` typed outputs.

## Strategy

### Rust side

Use `cargo-deny` with a `bans` block that marks layer crates as mutually exclusive in dependency graphs. Draft config: see `deny.toml` in this folder.

### TypeScript side

Custom ESLint rule `@aether/no-cross-layer-import` that rejects imports matching the pattern `@aether/l[0-9]-*` from any `packages/l*-*` package. Draft stubs land in Wave 2 alongside the first TS layer facade.

## References

- file:///C:/Users/dbhav/Projects/aether/planning/planning/monorepo_plan_draft.md §4.1
- file:///C:/Users/dbhav/Projects/aether/CLAUDE.md §1.4

## Wave 2 TODO

1. Flesh out `deny.toml` with real `[bans]` pairs (once layer crates exist).
2. Scaffold the ESLint rule package.
3. Wire both into a root `pnpm lint` / `cargo deny check` task.
