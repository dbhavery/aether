# `@aether/desktop` — Desktop shell (v0)

First real desktop surface for Companion. Thin Tauri 2 shell over the Rust
engine path: L1 turn FSM + L2 session memory + L3 presence + L5 policy +
L6 persona + L7 approval + L4 router (reflex stub by default, Ollama
behind a feature).

> **Status:** v0. Builds in dev mode with the `@tauri-apps/cli` local
> dev-dep. Bundled distribution is deliberately disabled in
> `tauri.conf.json` (`bundle.active = false`) — signing / notarization /
> release flows are a later wave.

---

## Run it

Prerequisites on Windows:

- Rust stable + the `rust-toolchain.toml` pins.
- Node ≥20 and `pnpm` (the repo already pins these).
- Microsoft WebView2 runtime (present on Windows 10 1803+ / all Windows 11).
- Visual Studio Build Tools (for the Tauri Rust build).

```bash
# From the repo root
cd apps/desktop
pnpm install          # first run only; installs @tauri-apps/cli locally
pnpm tauri dev        # boots the Rust backend + Vite dev server
```

On launch you'll see:

1. A one-time local-first disclosure modal (dismissible; re-accessible
   from the **About** button in the header).
2. A persona card introducing "Aurora" with current tier / output mode.
3. A chat input. Type something; the reflex stub echoes with a tier
   label.

### Enable the local Ollama provider

```bash
# In a separate shell — install Ollama (https://ollama.com) first
ollama serve
ollama pull gemma4        # or llama3, phi3, anything your VRAM supports

export AETHER_OLLAMA_MODEL=gemma4
cd apps/desktop
pnpm tauri dev -- --features ollama-provider
```

The provider badge in the header turns from a muted dot to green, the
label reads `Ollama · gemma4 · http://127.0.0.1:11434`, and each
assistant reply carries its tier/provider footer.

If the daemon is unreachable, the shell falls back silently to the
reflex stub and notes the failure in stderr.

---

## What's in the box

| Surface | What it does | Spec ref |
|---|---|---|
| Header presence dot | Live `quiet / listening / thinking / awaiting-approval / responding` | `ARCHITECTURE.md` §Presence |
| Persona card | Companion identity + tier + output mode | `docs/PERSONA-SCHEMA.md` |
| Transcript | User / assistant / system messages; meta-footer shows tier+provider | `ARCHITECTURE.md` §UX |
| Input bar | Text input, Enter to send, Shift+Enter newline, Ctrl+K focus | — |
| Approval modal | Clear capability / scope / reason / ticket. "Approve once" or "Decline" | `ARCHITECTURE.md` §Permissions & autonomy |
| Memory drawer | Inspect the current session's transcript window | `docs/MEMORY-V2-ARCHITECTURE.md` §Memory governance |
| Disclosure banner | Plain-language local-first statement on first run | `docs/ONBOARDING-SPEC.md` §Step 1 |
| New session | Clears memory + presence + pending approvals | — |

## What's deliberately out of scope for v0

- **No avatar, no viseme, no voice.** L3 macro presence only. Avatar work
  is later, per `ARCHITECTURE.md` §Presence.
- **No durable memory.** L2.1 is session-only. Edit/export/forget UX
  requires durable storage first.
- **No 7-step onboarding wizard.** The one-time disclosure is the
  minimum-viable first-run experience; the full wizard specified in
  `docs/ONBOARDING-SPEC.md` is a later session.
- **No autonomy preset picker.** The engine is locked to the wave3
  default ("Assistant"-equivalent). `ARCHITECTURE.md`
  §Permissions & autonomy.
- **No trust centre / audit view.** The audit chain exists in L5 but has
  no UI yet.
- **No persona picker.** v0 ships Aurora only.
- **No streaming responses.** The Ollama provider is blocking.
- **No tool-call dispatch.** L4 adapter returns `ToolError::Internal` on
  any tool request.
- **No signed bundle.** `bundle.active = false`. Release/signing is a
  coordinator-gated wave (`docs/DISTRIBUTION.md`).

## Architecture

```
apps/desktop/
├── src/                        # React + TypeScript UI
│   ├── App.tsx                 # root composition
│   ├── components/             # Header, Transcript, InputBar, …
│   ├── lib/api.ts              # typed invoke() wrapper
│   └── lib/types.ts            # command/event payloads
├── src-tauri/                  # Rust backend (standalone Cargo workspace)
│   ├── src/main.rs             # Tauri builder + plugins
│   ├── src/state.rs            # AppState — engine + policy + presence + memory
│   ├── src/commands.rs         # 6 typed commands + 1 event channel
│   ├── src/adapter.rs          # L4→L1 adapter (mirrors apps/l1-cli)
│   ├── src/memory_router.rs    # L2-aware TurnRouter wrapper
│   ├── src/provider.rs         # ProviderMode + tier translation
│   ├── capabilities/default.json   # default-deny allowlist
│   └── tauri.conf.json         # window, CSP, bundle off
├── tailwind.config.ts          # tokens bound to packages/ui-kit palette
└── vite.config.ts              # fixed port 1420, Tauri dev URL
```

### Layer hygiene

- `apps/desktop/src-tauri` is a **standalone Cargo workspace** — it does
  not join the root workspace, so `cargo check --workspace` at the repo
  root stays fast and unaffected by the Tauri dep graph.
- Only `apps/l1-cli` and `apps/desktop/src-tauri` depend on multiple L
  crates. The layer-boundary linter regulates `packages/l*-*` only.
- The webview never holds engine state; it is a view on top of the Rust
  core (`ARCHITECTURE.md` §Tauri shell).

### Command surface (frozen shape for v0)

| Command | Return | Notes |
|---|---|---|
| `companion_banner()` | `CompanionBanner` | Called once on boot |
| `submit_turn(text)` | `TurnOutcome` | `kind: "completed" \| "awaiting_approval" \| ...` |
| `resolve_approval(ticket_id, approve)` | `TurnOutcome` | Replays the turn on approve |
| `presence_current()` | `PresencePayload` | Initial seed only; updates arrive via events |
| `memory_recent()` | `TranscriptMessage[]` | Memory drawer |
| `clear_session()` | `()` | Drops memory + presence + pending |

Events: `presence:update`.

### Known gaps / TODO

- No E2E tests yet. The turn path is exercised by the existing
  `apps/l1-cli` tests; the Tauri command surface is not.
- `tauri.conf.json` icon is an SVG — fine for dev, not for bundle.
- Memory drawer polls on refresh key; real reactive updates would need
  a `memory:update` event channel.
- No keyboard-accessible routing to the approval modal focus ring.
- Windows-only runbook. macOS and Linux setup are not documented.
