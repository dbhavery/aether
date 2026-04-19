# tools/ts-bindings-gen

**Status:** Wave 1 placeholder.

Generates `packages/types/` from Rust structs annotated with `ts-rs` (or `specta`) derives. Replaces the hand-written stubs in `packages/types/src/index.ts`.

## Strategy

- Every Rust type that crosses the Tauri IPC bridge derives `#[derive(ts_rs::TS)]`.
- A root `cargo run -p ts-bindings-gen` (added in Wave 2) invokes `ts-rs` exports and writes to `packages/types/src/generated/`.
- CI fails if generated TS is out-of-date vs Rust sources.

## Wave 2 TODO

1. Choose `ts-rs` vs `specta`. (Default: `ts-rs` — wider community, simpler.)
2. Scaffold the generator crate as a workspace member.
3. Add derives to `aether-event-bus` types first, prove the end-to-end path, then propagate.
