# tools/lint-private-asset-leak

**Status:** Wave 1 scaffold — strategy doc only.

Fails builds if any Isabelle-tagged asset appears in a public distributable manifest (OSS Preview, Aether Pro public build).

## Strategy

1. Private Isabelle overlay lives outside this repo (per doctrine §8).
2. Any asset copied into a distributable manifest is tagged with a `source_profile` field.
3. This tool inspects the final build manifest (Tauri bundle plan, pnpm pack output, installer input list) and fails if any row has `source_profile = "isabelle-private"` and the target build flag is `--product=oss` or `--product=pro-public`.

## Implementation sketch

- Rust binary that reads a manifest JSON emitted by the build pipeline.
- Exit 1 on leak; prints file paths and the manifest row that triggered the block.

## References

- file:///C:/Users/dbhav/Projects/aether/planning/01_product_doctrine.md
- file:///C:/Users/dbhav/Projects/aether/planning/planning/monorepo_plan_draft.md §3.2 (X2 Isabelle migration)

## Wave 4 TODO

Implement once the first public distributable is being built. Until then this tool exists only as a reminder hook.
