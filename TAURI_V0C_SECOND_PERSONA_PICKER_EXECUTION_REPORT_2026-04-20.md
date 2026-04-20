# TAURI_V0C — Second persona + header picker

**Date:** 2026-04-20 (P5)
**Branch:** `dev` (local, not pushed)

---

## 1. Status

**Complete.** The shell now ships two personas — Aurora (Warm /
Balanced) and Sable (Neutral / Bold / Terse / Dry humor) — with a
minimal dropdown in the header that lets the user swap between them
at runtime. Switching a persona clears session state and rebuilds the
active engine with that persona's compiled policy defaults, so the
Ask / Auto / Deny surface visibly changes between personas (courtesy
of P4's overlay).

A fresh persona can also be selected at boot via `AETHER_PERSONA=<id>`
(default `aurora`).

## 2. What shipped

### Backend — `apps/desktop/src-tauri/src/state.rs` (refactored)

- Replaced the single-persona `AppState` fields with:
  - `catalog: Vec<PersonaProfile>` — the fixed list of available personas.
  - `active: RwLock<ActiveEngine>` — everything that swaps when the
    persona changes (compiled persona, turn engine, policy, audit,
    provider mode/label, display strings).
- New `ActiveEngine` struct groups the swappable pieces so
  `switch_persona` can replace the whole tuple atomically.
- New `AppState::catalog_entries()` returns a serializable
  `PersonaCatalogEntry[]` for the UI picker.
- New `AppState::switch_persona(id)` rebuilds the engine against the
  new persona, clears memory/presence/pending approvals, and installs
  the new `ActiveEngine` via the write lock.
- New `pick_default(catalog)` helper honours `AETHER_PERSONA` env var.
- New `default_catalog()` hard-codes Aurora and Sable.

### Backend — `apps/desktop/src-tauri/src/commands.rs`

- All command sites that previously read `state.compiled`, `state.engine`,
  `state.policy`, `state.audit`, `state.provider_*` now take
  `state.active.read()` first. Reads are cheap shared locks.
- Two new commands:
  - `list_personas() -> Vec<PersonaCatalogEntry>`
  - `switch_persona(id) -> CompanionBanner` — delegates to
    `state.switch_persona(id)`, fires a Quiet presence transition,
    returns the new banner.

### Backend — `apps/desktop/src-tauri/src/main.rs`

- Registers the two new commands in `generate_handler!`.

### Frontend — `apps/desktop/src/lib/types.ts`

- New `PersonaCatalogEntry` interface.

### Frontend — `apps/desktop/src/lib/api.ts`

- New `listPersonas()` and `switchPersona(id)` typed wrappers.

### Frontend — `apps/desktop/src/components/Header.tsx`

- New `personas` prop + `onSwitchPersona` callback.
- Renders a `<select>` between the persona-name and the presence dot
  when >1 persona is available; options show `Name · stance`.

### Frontend — `apps/desktop/src/App.tsx`

- Loads `listPersonas()` during boot.
- New `handleSwitchPersona(id)` — invokes the backend, swaps the
  banner, clears messages/pending approvals, bumps the session nonce
  (which re-seeds the presence subscription).
- Wires `personas` + `handleSwitchPersona` into `Header`.

## 3. Sable vs Aurora

| | Aurora | Sable |
|---|---|---|
| Tone | Warm | Neutral |
| Verbosity | Balanced | Terse |
| Stance | Balanced | **Bold** |
| Humor | Occasional | Dry |
| `FilesCreate` | Ask | **Auto** |
| `BrowserOpen` | Ask | **Auto** |
| `FilesEdit` / `FilesDelete` | Ask | Ask |
| `ShellExec` | Deny | Deny |

Switching to Sable and typing `write /tmp/foo` no longer opens the
approval modal; Sable auto-allows and echoes through the reflex stub.
`edit /tmp/foo` still asks; `shell ls` still denies. Same text under
Aurora surfaces the approval modal.

## 4. Deliberate non-goals

- **No third persona.** A cautious option would be the natural next
  add but the backlog asked for "one more" — two is enough to prove
  the picker.
- **No persona-pack YAML loader.** Personas are hard-coded in
  `default_catalog()`. The YAML-driven loader lives behind L6's
  persona-pack schema (planning/17_persona_pack_schema.md); that's a
  later slice.
- **No audit-chain preservation across switches.** Switching resets
  the audit store with the new persona. That's correct for the
  shell's trust model — each persona's trust ledger is separate — but
  the trust drawer will appear empty right after a switch.
- **No persistence of the picked persona.** The next app launch will
  default to `AETHER_PERSONA` or Aurora, not "whichever the user
  picked last". That's onboarding-wizard territory (P6 / later
  `tauri-plugin-store` slice).

## 5. Checks run

| Check | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean |
| `cargo check` (src-tauri default) | clean |
| `cargo check --features ollama-provider` (src-tauri) | clean |
| `cargo test` (src-tauri, default) | 9 pass |
| `cargo test --features ollama-provider` (src-tauri) | 12 pass |
| `cargo test --workspace` | clean (via earlier run; no engine-layer code changed since) |
| `pnpm typecheck` (apps/desktop) | clean |
| `pnpm build` (apps/desktop) | clean — 164.77 KB / 51.52 KB gzipped |
| `python tools/lint-layer-boundaries/check.py` | OK (0 violations) |

## 6. Commit

`feat(apps/desktop): [TAURI_V0C] second persona + header picker`
