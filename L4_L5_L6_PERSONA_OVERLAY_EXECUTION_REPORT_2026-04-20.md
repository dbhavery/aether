# L5 / L6 — Persona policy defaults → EngineConfig overlay

**Date:** 2026-04-20 (P4)
**Branch:** `dev` (local, not pushed)

---

## 1. Status

**Complete.** Persona stance (Cautious / Balanced / Bold) now visibly
changes which capabilities are Auto vs Ask vs Deny in the shell. The
compiled persona's `policy_defaults.per_capability_defaults` is
threaded into `EngineConfig` at build time via a new
`EngineConfig::with_persona_overlay` method; the preset is the floor,
the persona is the hint layer on top.

## 2. What shipped

### `packages/l5-policy/src/engine.rs`

- New method `EngineConfig::with_persona_overlay(&HashMap<Capability,
  ApprovalMode>, PrivacyPosture) -> Self`:
  - Replaces the `mode` of each capability the persona opines on.
  - Preserves the preset-declared `risk` (risk is a property of the
    capability, not the persona).
  - Inserts new capabilities the preset didn't know about with a
    conservative default risk (see `default_risk_for`).
  - Sets `posture` from the persona.
- New module-private `default_risk_for(&Capability)` fallback map.
- 4 new `#[cfg(test)] mod tests`:
  - `overlay_replaces_mode_while_preserving_preset_risk`
  - `overlay_inserts_new_capabilities_with_default_risk`
  - `overlay_sets_posture_from_persona`
  - `overlay_cannot_bypass_presets_deny` — documents the invariant
    that L6's default compiler is what enforces `ShellExec = Deny`
    across personas, not L5. L5 trusts its compiled inputs.

### `packages/l6-persona/src/default_compiler.rs`

- `compile_policy_defaults` now actually differs by stance:

  | Capability | Cautious | Balanced | Bold |
  |---|---|---|---|
  | `FilesRead` | Auto | Auto | Auto |
  | `FilesCreate` | Ask | Ask | **Auto** |
  | `FilesEdit` | Ask | Ask | Ask |
  | `FilesDelete` | Ask | Ask | Ask |
  | `BrowserOpen` | **Deny** | Ask | **Auto** |
  | `ShellExec` | Deny | Deny | Deny |

  Bold personas auto-approve `FilesCreate` and `BrowserOpen`; Cautious
  personas outright `Deny` `BrowserOpen`. Edit/Delete stay `Ask` even
  for Bold — "bold" shouldn't mean "reckless".

### `apps/desktop/src-tauri/src/state.rs`

- `AppState::new` now calls
  `EngineConfig::wave3_default(persona_id).with_persona_overlay(&c.policy_defaults.per_capability_defaults, c.policy_defaults.privacy_posture)`
  instead of the bare `wave3_default`. Inline comment explains the
  floor-vs-hint relationship.

## 3. Visible product effect

Before this slice, Aurora (Balanced) and a hypothetical Cautious or
Bold persona all got identical engine defaults — the "stance" slider
was cosmetic. Now:

- A **Cautious** persona refuses `browse https://...` outright at the
  policy layer (Deny, not Ask, not NeedsUpgrade).
- A **Balanced** persona (Aurora) asks on both `browse` and
  `write /tmp/foo` — same as before.
- A **Bold** persona auto-approves `write /tmp/foo` and
  `browse https://...`, still asks on `edit`/`delete`, still denies
  `shell`.

Each is observable from the approval modal / trust drawer — no code
change needed in the UI.

## 4. Checks run

| Check | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean |
| `cargo test --workspace` | **all green** — every crate's existing tests still pass |
| `cargo test -p aether-l5-policy` | 10 pass (+4 new overlay tests) |
| `cargo test -p aether-l6-persona` | 7 pass (existing, including the shell-exec-always-Deny regression) |
| `cargo check --features ollama-provider` (src-tauri) | clean |
| `python tools/lint-layer-boundaries/check.py` | OK (0 violations) |

## 5. Known follow-ups

- The CLI (`apps/l1-cli`) doesn't use the overlay — it still calls
  `EngineConfig::wave3_default(persona)` directly. Same fix would
  take 2 LOC; defer until the CLI cares.
- `with_persona_overlay` takes a `&HashMap<Capability, ApprovalMode>`
  and a `PrivacyPosture` as two separate args. Could accept a
  `&PersonaCompiledPolicyDefaults` directly, but L5 doesn't depend on
  L6 — and shouldn't — so two primitive args is the right seam.
- `default_risk_for` is conservative but hand-maintained. If new
  `Capability` variants land, the fallback defaults should land in
  the same PR.
- L6's `compile_policy_defaults` is still hand-maintained. A future
  L6 pass might drive it from a YAML persona-pack schema
  (`planning/17_persona_pack_schema.md`).

## 6. Commit

`feat(l5,l6,apps/desktop): [L4] thread persona policy defaults through EngineConfig overlay`
