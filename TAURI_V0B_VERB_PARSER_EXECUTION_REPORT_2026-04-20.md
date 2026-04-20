# TAURI_V0B — Verb-prefix parser in desktop shell

**Date:** 2026-04-20 (morning unattended run, P1)
**Branch:** `dev` (local, not pushed)

---

## 1. Status

**Complete.** The desktop shell now parses the leading verb of each
user utterance and routes it to the matching `Capability` +
`ResourceScope`, mirroring `apps/l1-cli/src/main.rs::parse_command`.
This makes the shell capable of exercising every L5 decision path —
Allow, Ask, Deny, NeedsUpgrade — from the UI, which was the first real
quirk flagged in the 2026-04-19 handoff.

Before this slice, `submit_turn` hard-coded `Capability::FilesRead` +
`ResourceScope::None`, so typing `write /tmp/foo` in the shell was
indistinguishable from typing `hello` — neither ever reached the Ask
path. Users could see the approval modal design, but could not trigger
an approval.

## 2. Smoke-launch result (prerequisite)

Before touching code, I ran `pnpm install && pnpm tauri dev` with
`cargo` on PATH. The backend compiled (413 crates; ~1m 05s cold), the
dev profile binary started as `target\debug\aether-desktop.exe` (PID
42564), and WebView2 child processes appeared. **Window launched
successfully.** Confirmed the repo-as-shipped-by-the-night-of-2026-04-19
runs on this machine.

## 3. What shipped

### `apps/desktop/src-tauri/src/commands.rs`

- New private helper `parse_command(&str) -> (Capability, ResourceScope)`
  — identical verb set and semantics to the CLI's `parse_command`. The
  docstring explicitly calls the CLI the canonical demo surface so
  future maintainers know to keep the two in sync.
- New private helper `path_scope_or_none(&str) -> ResourceScope`.
- `submit_turn` now calls `parse_command(&text)` instead of
  hard-coding `FilesRead`/`None`.
- New `#[cfg(test)] mod tests` with 9 unit tests covering every verb,
  the plain-chat fallback, case-insensitivity, and the missing-arg
  case. All pass.

### `apps/desktop/src/components/InputBar.tsx`

- Replaced the single right-aligned keyboard-shortcut hint with a
  two-column row: a left-aligned example hint
  (`read /tmp/x`, `write /tmp/x`, `shell ls`) and the keyboard
  shortcuts on the right. Gives new users something to try to reach
  the approval / deny paths.

## 4. Checks run

| Check | Result |
|---|---|
| `cargo fmt --all -- --check` (root) | clean |
| `cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml -- --check` | clean |
| `cargo check --workspace` (root) | clean |
| `cargo check` (src-tauri, default) | clean |
| `cargo check --features ollama-provider` (src-tauri) | clean |
| `cargo test --workspace` | all green |
| `cargo test` (src-tauri) | **9 new tests pass**, 0 failed |
| `pnpm typecheck` (apps/desktop) | clean |
| `pnpm build` (apps/desktop) | clean — 163 KB / 51 KB gzipped |
| `python tools/lint-layer-boundaries/check.py` | OK (0 violations) |

## 5. What this unlocks

- Typing `write /tmp/x` in the shell now surfaces the L7 approval
  modal with the sealed ticket id. Approving or declining walks the
  engine through `resolve_approval`, and a new audit row drops into
  the trust drawer.
- Typing `shell ls` now reaches the Deny path and surfaces the
  "Declined" system message.
- Typing `browse https://example.com` surfaces NeedsUpgrade.
- Plain chat is unchanged — `FilesRead` + `None`, Allow path, echoes
  through the reflex stub.

## 6. Known follow-ups

- The parser is duplicated between CLI and shell. Acceptable for now;
  both crates deliberately stand alone. If a third caller appears, the
  parser should move to a shared crate (candidate:
  `packages/l7-trust` or a new `apps/common`).
- The input hint is static. A future pass could gate it behind a
  first-run tip or show it only when the transcript is empty.
- No end-to-end Tauri test yet — the parser is exercised by unit
  tests; the full command flow is only typechecked.

## 7. Next up

P2a: mock-HTTP integration test for `OllamaProvider::chat`. See
`HANDOFF_2026-04-20_CONTINUE_COMPANION_BUILD.md` §3 P2 and the
"copy-paste starting prompt" at §6 for the full backlog.
