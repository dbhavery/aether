# Community Demo Slice — L1 CLI using L4 ModelRouter (Execution Report)

**Date:** 2026-04-19
**Branch:** `dev` (continuing from `9ee8883`; this wave adds commits on top)
**Scope:** new `apps/l1-cli/` demo crate; no edits to engine crates.

---

## 1. Where the demo lives

| Item              | Path                                                     |
|-------------------|----------------------------------------------------------|
| Crate             | `apps/l1-cli/`                                           |
| Binary            | `aether-l1-cli`                                          |
| Workspace member  | added to `Cargo.toml` members list                       |
| Adapter module    | `apps/l1-cli/src/adapter.rs`                             |
| CLI loop          | `apps/l1-cli/src/main.rs`                                |
| Docs              | `apps/l1-cli/README.md` + new section in root `README.md`|

The crate is marked `publish = false` so it won't drift onto crates.io.

## 2. How the TurnRouter adapter calls L4

`apps/l1-cli/src/adapter.rs` contains two pieces:

1. **`ReflexModelRouter`** — a stub that implements `aether_l4_router::ModelRouter`. It does no inference; `route(tier, prompt)` returns a formatted string so the demo runs without any provider configuration, and `execute_tool` returns a typed `ToolError::Internal` so calls never silently succeed.

2. **`ModelRouterAdapter<R: ModelRouter>`** — the actual L4 → L1 bridge. It implements `aether_l1_interaction::TurnRouter::dispatch`:

   ```rust
   fn dispatch(&self, _turn_id, prompt, _decision) -> Result<RouteOutcome, L1Error> {
       let response = self.router.route(self.tier, prompt)
           .map_err(|e| L1Error::Router(format!("{e}")))?;
       Ok(RouteOutcome {
           tier: tier_label(self.tier).to_string(),
           provider: self.provider_label.clone(),
           response_text: response,
       })
   }
   ```

Tier selection lives in the adapter (fixed to `RouterTier::Reflex` in this demo). A richer adapter could pick tier from decision metadata or utterance length. Because the adapter crate is the only thing that imports both L1 and L4, the sibling-engine rule stays intact inside the libraries.

Boundary linter (`python tools/lint-layer-boundaries/check.py`): **0 violations**. The linter ignores `apps/*` crates by design (only engines and shared infra are policed), so adding this bridge doesn't require any rule relaxation.

## 3. How to run it

```bash
cargo run -p aether-l1-cli
```

Prerequisites: Rust toolchain (pinned via `rust-toolchain.toml`). No network, no model weights, no env vars.

At the `aether>` prompt, the command verb maps to a capability so every FSM branch is reachable from the keyboard:

| Command              | Capability      | Decision branch exercised |
|----------------------|-----------------|---------------------------|
| `read <path>`        | `FilesRead`     | Allow → Completed         |
| `write <path>`       | `FilesCreate`   | Ask → AwaitingPolicyApproval |
| `edit <path>`        | `FilesEdit`     | Ask → AwaitingPolicyApproval |
| `delete <path>`      | `FilesDelete`   | Ask → AwaitingPolicyApproval |
| `shell <cmd>`        | `ShellExec`     | Deny → PolicyDenied       |
| `browse <url>`       | `BrowserOpen`   | NeedsUpgrade → PolicyDenied |
| *anything else*      | `FilesRead`     | Allow → Completed         |

Exit with `quit`, `exit`, `:q`, or Ctrl+D.

The `sqlite-backend` cargo feature on the CLI crate is wired (forwards to `aether-l5-policy/sqlite-backend`) but the demo always instantiates in-memory backends right now; durable mode is an easy follow-up (env-var DB path + feature flag).

## 4. What the output looks like

Actual session transcript (tested this wave):

```
aether> read /tmp/x
  turn-id      : turn-1
  final-state  : Completed
  state-trace  : Idle -> AwaitingPolicyApproval -> RouterDispatched -> Completed
  policy       : Allow  (grant=g-1, audit=a-1)
  route        : tier=reflex provider=reflex-stub
  response     : [reflex] heard you: read /tmp/x

aether> delete /tmp/y
  turn-id      : turn-2
  final-state  : AwaitingPolicyApproval
  state-trace  : Idle -> AwaitingPolicyApproval
  policy       : Ask    (ticket=t-1, audit=a-2)
  blocked      : awaiting user approval (Ask ticket open)

aether> shell ls
  turn-id      : turn-3
  final-state  : PolicyDenied
  state-trace  : Idle -> AwaitingPolicyApproval -> PolicyDenied
  policy       : Deny   (ModeDeny, audit=a-3)
  blocked      : policy denied

aether> browse https://example.com
  turn-id      : turn-4
  final-state  : PolicyDenied
  state-trace  : Idle -> AwaitingPolicyApproval -> PolicyDenied
  policy       : NeedsUpgrade  (cap=unknown.path, preset=wave3.operator, audit=a-4)
  blocked      : capability not in active preset (upgrade required)
```

Every field is produced by real engine code: the audit IDs come from `DefaultPolicyEngine::write_audit`, the grant IDs come from `issue_and_emit_grant`, the state trace is the actual `TurnState` path the FSM walked.

## 5. Tests & checks

| Check                                          | Result                         |
|------------------------------------------------|--------------------------------|
| `cargo fmt --all -- --check`                   | clean                          |
| `cargo check --workspace`                      | clean                          |
| `cargo test --workspace`                       | all green (35 test groups, 0 failures) |
| `cargo test -p aether-l1-cli`                  | 3 tests passed                 |
| `python tools/lint-layer-boundaries/check.py`  | OK, 0 violations               |

Tests added in `apps/l1-cli/src/main.rs` (unit tests module):

- `demo_engine_runs_allow_path_end_to_end` — constructs the real engine (policy + adapter), runs one `FilesRead` turn, asserts `RouteOutcome.provider == "reflex-stub"` and response contains the prompt.
- `demo_engine_blocks_shell_exec` — same engine, `ShellExec` request, asserts `BlockReason::Denied` and no route.
- `parse_command_routes_verbs_to_capabilities` — command → capability mapping.

## 6. Limitations & future improvements

- **No real inference.** `ReflexModelRouter` echoes the prompt under a reflex-tier label. Plugging a genuine `ModelRouter` impl (llama.cpp, Ollama, Anthropic) is a drop-in — swap the type parameter on `ModelRouterAdapter`.
- **Ask is terminal.** The CLI prints the pending ticket and stops. Resuming through `respond_approval` would require either an inline prompt or a separate command (e.g. `approve t-1` / `deny t-1`).
- **No presence / persona integration.** `PresenceClient` exists in L1 but isn't wired. A later slice could push `on_turn_state` calls and show a persona-driven banner.
- **Formatting is plain stdout.** Colours, JSON output mode (`--json`), and a `--trace` flag that prints the full L5 event sink are obvious next moves.
- **Durable mode wired but not switched on.** The `sqlite-backend` feature forwards through but the CLI always builds in-memory. A `--db <path>` flag plus a cfg'd builder is ~20 lines.
- **Command vocabulary is ad-hoc.** `read / write / edit / delete / shell / browse` was chosen to surface each decision branch; a real CLI would negotiate capabilities differently (e.g. via a tool-call DSL).

## 7. Recommended next session

Two strong candidates, roughly equal weight:

1. **Audit hash-chain + HMAC sealing.** Now that there is a real end-to-end caller (L1 CLI) producing audit rows, the audit chain is easy to pressure-test. Wire `prev_hash` + `record_hmac` through `write_audit`, add a `verify_chain` implementation, and surface chain-break detection through `DegradedMode::AuditBroken`.

2. **First presence/persona slice (L3 + L6).** Add a minimal `PersonaEngine` that the CLI can consult for utterance framing, and a `PresenceClient` that prints a banner on each `TurnStateChange`. Small, visible, and exercises two more engines on the same demo path.

Choosing (1) pays down a known Wave-3 deferral; choosing (2) widens the demo surface. My recommendation is **(1)** — the audit chain is doctrine-critical and now has a real caller to validate against. Presence/persona can follow once audit sealing is green.

---

**Status:** community demo slice complete. Working tree ready for commit.
