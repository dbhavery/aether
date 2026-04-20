# aether-l1-cli

**Status:** community demo slice. Not a product. Not a shell. A runnable
example that walks a single stdin line through Aether's L1 / L5 / L4 engines
and prints exactly what each layer decided.

## Why this crate exists

L1 (interaction) and L4 (router) are siblings. Per the layer-boundary rule
([CLAUDE.md §1.4](../../CLAUDE.md), enforced by
[tools/lint-layer-boundaries](../../tools/lint-layer-boundaries/)),
`aether-l1-interaction` **must not** depend on `aether-l4-router`. So L1
defines its own `TurnRouter` trait; any binary that wants to drive L1 with a
real L4 router has to supply the adapter itself.

`apps/l1-cli/` is that adapter crate. It depends on both engines and stitches
them together in `src/adapter.rs`.

## Prerequisites

- Rust toolchain (see `rust-toolchain.toml` at the repo root; install via
  [rustup](https://rustup.rs/)).

No network, no model weights, no configuration — the demo uses a stub
`ReflexModelRouter` that echoes the prompt.

## Run it

```bash
cargo run -p aether-l1-cli
```

Type a command at the `aether>` prompt. Each command maps to a capability so
you can see every branch of the FSM light up:

| Command                  | Capability         | Expected result                              |
|--------------------------|--------------------|----------------------------------------------|
| `read /tmp/x`            | `FilesRead`        | Allow → router dispatch → Completed          |
| `write /tmp/x`           | `FilesCreate`      | Ask → AwaitingPolicyApproval (terminal here) |
| `edit /tmp/x`            | `FilesEdit`        | Ask → AwaitingPolicyApproval                 |
| `delete /tmp/x`          | `FilesDelete`      | Ask → AwaitingPolicyApproval                 |
| `shell ls`               | `ShellExec`        | Deny → PolicyDenied                          |
| `browse https://…`       | `BrowserOpen`      | NeedsUpgrade → PolicyDenied                  |
| anything else            | `FilesRead` (None) | Allow → router dispatch → Completed          |

`quit`, `exit`, `:q`, or Ctrl+D ends the session.

## What a turn looks like

```
aether> read /tmp/x
  turn-id      : turn-1
  final-state  : Completed
  state-trace  : Idle -> AwaitingPolicyApproval -> RouterDispatched -> Completed
  policy       : Allow  (grant=g-1, audit=a-1)
  route        : tier=reflex provider=reflex-stub
  response     : [reflex] heard you: read /tmp/x

aether> shell ls
  turn-id      : turn-2
  final-state  : PolicyDenied
  state-trace  : Idle -> AwaitingPolicyApproval -> PolicyDenied
  policy       : Deny   (ModeDeny, audit=a-2)
  blocked      : policy denied
```

Every line is a real output of a real engine — the policy engine wrote an
audit row before the Allow returned, the L1 FSM actually transitioned
through those states, and the router call really passed through the
`TurnRouter → ModelRouter` adapter.

## Opt in to SQLite-backed L5

The default engine uses in-memory grants and audit. To switch to the
durable SQLite-backed backends (from Wave 4.5), rebuild with the feature
enabled and pass a DB path via an env var (coming in a later wave — for
now, the feature is wired but the CLI always uses in-memory). Engine-level
SQLite integration is covered by
`packages/l1-interaction/tests/turn_slice_sqlite.rs`.

## What this demo is not

- Not a product. There is no persona, no presence, no audio path, no
  approval UI, no real model.
- Not a routing benchmark. `ReflexModelRouter` does no inference.
- Not a complete turn loop. `Ask` is terminal here; approval plumbing comes
  in a later wave.

## Next steps

- Plug a real `ModelRouter` implementation (llama.cpp / Ollama / Anthropic)
  behind `ModelRouterAdapter` so the `Allow` path produces genuine
  completions.
- Wire an approval handler so `Ask` turns become resumable.
- Integrate L3 presence so each `TurnStateChange` nudges a visual state.
