# tools/lint-policy-bypass

**Status:** Wave 1 scaffold — rules doc only. Implementation in Wave 2+.

Rejects direct executor calls (file I/O, network, subprocess, shell, webview `invoke`) from anywhere outside `packages/l5-policy`'s approved execution paths.

## Forbidden patterns (draft)

### Rust — forbidden outside `packages/l5-policy` and its sanctioned helpers

- `std::fs::*` mutating calls (`write`, `create`, `remove_file`, `rename`, `copy`, `set_permissions`) in layer crates.
- `std::process::Command` / `tokio::process::Command`.
- `reqwest::*` / `hyper::Client` / any outbound HTTP client instantiation.
- `tauri::api::shell::open` / `tauri::api::process::Command`.

### TypeScript — forbidden outside sanctioned trust-center paths

- Raw `fetch(` calls in layer-facade or layer-internal modules.
- `window.open`, `document.createElement("a").click()` (file downloads) outside `packages/l7-trust-center`.

## Implementation sketch

- Rust: a small binary using `syn` + `walkdir` (or a `rust-analyzer`-backed check) that grep-parses crate sources for banned symbols. Runs in CI.
- TS: an ESLint rule `@aether/no-policy-bypass`.

Both emit `source_layer`-aware diagnostics and are blocking in CI once lit up.

## L5-scaffold alignment (Wave 2, 2026-04-19)

Now that `packages/l5-policy` exists, the concrete enforcement pattern is:

- Every caller of a forbidden symbol must hold an `Arc<dyn aether_l5_policy::PolicyEngine>`
  and be able to produce a matching `aether_l5_policy::Decision::Allow` or
  an in-scope `Grant` covering the call under the Decision 4 re-eval rule.
- Exceptions live only inside `packages/l5-policy` itself and its test harness.
- Tauri `#[tauri::command]` handlers that proxy to `PolicyCommands` (see
  `packages/l5-policy/src/ipc.rs`) are an allowed executor path once
  `apps/desktop/src-tauri` scaffolds the bridge — the handler itself still
  invokes `PolicyEngine::evaluate`.

The Rust grep-parser prototype (Wave 3) will flag every violator and produce
a `source_layer`-aware diagnostic keyed off the call site's crate.

## References

- `ARCHITECTURE.md` — the L5 policy layer and autonomy/risk-class framework this lint enforces.
- file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/policy_engine.rs
- file:///C:/Users/dbhav/Projects/aether/CLAUDE.md §1.5

## Wave 2 TODO

1. Create `rules.md` listing the full banned-symbol set with rationale.
2. Prototype the Rust grep-parser binary.
3. Scaffold the ESLint rule.
