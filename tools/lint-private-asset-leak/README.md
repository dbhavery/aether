# tools/lint-private-asset-leak

**Status:** Wave 1 scaffold — strategy doc only.

Fails builds if any Isabelle-tagged asset appears in a public Companion distributable manifest. (Pre-doctrine §6 framing referenced "OSS Preview" and "Aether Pro public build" as separate surfaces; under doctrine §6 there is one Companion product, and this lint guards its public build.)

## Strategy

1. Private Isabelle overlay lives outside this repo (per doctrine §8).
2. Any asset copied into a distributable manifest is tagged with a `source_profile` field.
3. This tool inspects the final build manifest (Tauri bundle plan, pnpm pack output, installer input list) and fails if any row has `source_profile = "isabelle-private"` and the target is the public Companion build (post-doctrine §6 the only public surface; pre-doctrine §6 build flags `--product=oss` / `--product=pro-public` collapsed into the single Companion product).

## Implementation sketch

- Rust binary that reads a manifest JSON emitted by the build pipeline.
- Exit 1 on leak; prints file paths and the manifest row that triggered the block.

## References

- file:///C:/Users/dbhav/Projects/aether/planning/01_product_doctrine.md
- file:///C:/Users/dbhav/Projects/aether/planning/planning/monorepo_plan_draft.md §3.2 (X2 Isabelle migration)

## Wave 4 TODO

Implement once the first public distributable is being built. Until then this tool exists only as a reminder hook.
