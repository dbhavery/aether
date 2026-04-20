# P3 Execution Report — Persona-pack YAML loader

**Date:** 2026-04-24
**Scope:** `packages/l6-persona/` + `apps/desktop/` — replace the
hard-coded persona catalog path with a YAML-backed pack loader so
personas can be added without a Rust rebuild.

## Summary

### L6 — `pack_loader` module

New module `packages/l6-persona/src/pack_loader.rs` with:

- `PersonaPackFile` — on-disk schema (`#[serde(deny_unknown_fields)]`)
  mirroring `PersonaProfile` 1:1 with lower-case string enum variants
  and optional-with-defaults dials (`tone`, `verbosity`, `stance`,
  `humor` all fall back to the `Balanced` / `Neutral` / `Occasional`
  equivalents).
- `load_pack_file(path)` — parse a single YAML file.
- `load_pack_dir(dir)` — scan a directory for `*.yaml` / `*.yml`
  files, parse each, error on duplicate ids within the load. Non-YAML
  files are ignored; a missing directory returns `Ok(Vec::new())`
  so callers can invoke unconditionally.
- `PackLoadError { Io, Parse, DuplicateId }` — explicit failure modes.

Supporting change: `Tone`, `Verbosity`, `Stance`, `Humor` enums now
carry `#[serde(rename_all = "lowercase")]` so YAML round-trips with
the "warm" / "balanced" / "occasional" lexicon humans expect. No
external consumer relied on PascalCase serialisation (verified by
grep: only internal `serde_json::to_string` equality checks in the
default_compiler tests).

Dep added: `serde_yaml = "0.9"` (L6 only). `tempfile` in dev-deps for
tests.

### L6 — tests (7 new)

All in-module:

1. `valid_yaml_parses_to_persona_profile` — full schema round-trip.
2. `load_pack_dir_returns_every_valid_file` — two files parsed,
   non-YAML file ignored.
3. `missing_directory_is_empty_pack_set` — absence tolerated.
4. `duplicate_id_across_files_is_an_error` — id-uniqueness contract.
5. `yaml_missing_fields_errors_cleanly` — required-field guard.
6. `unknown_fields_are_rejected` — `deny_unknown_fields` regression
   (catches typos like `tonality` → `tone`).
7. `optional_dials_fall_back_to_defaults` — minimal profile valid.

### Shell — integration

- `state.rs::build` now calls `merge_yaml_personas(default_catalog())`.
- `merge_yaml_personas` looks up the pack directory via
  `persona_pack_dir()`, which reads the `AETHER_PERSONAS_DIR`
  environment variable. (The in-app-data-dir default is plumbed by
  `main.rs` when Tauri boots; unit tests exercise the env var path.)
- YAML personas are **additive only** — a YAML file whose `id` matches
  a built-in persona is skipped with a tracing WARN. This makes
  first-launch behaviour predictable even if a user drops in an
  experimental file that happens to clash.
- Loader failures (IO, Parse, DuplicateId) log at WARN and boot
  continues with the built-in catalog. A broken persona pack never
  denies the user their companion.

### Shell — tests (2 new)

In `state.rs`:

1. `yaml_persona_pack_merges_into_catalog` — writes a YAML file into
   a tempdir, points `AETHER_PERSONAS_DIR` at it, constructs
   `AppState::new()`, asserts both the built-in `aurora` and the YAML
   `solstice` appear in `catalog_entries()`.
2. `yaml_persona_id_collision_with_builtin_is_skipped` — a YAML
   declaring `id: aurora` must *not* replace the built-in; the catalog
   entry keeps the original name `"Aurora"`.

Both tests share a file-scoped mutex because they mutate process-wide
env vars.

## Behaviour change

Dropping a `*.yaml` file into `%APPDATA%/Aether/personas/` (or the
path pointed at by `AETHER_PERSONAS_DIR`) now makes that persona
available in the header picker on next launch. Built-in personas
remain canonical; YAML cannot override them in this slice. No UI
surface for authoring or editing YAML — that's a later wave, gated
by signature-verified packs.

Enum serialisation for `Tone` / `Verbosity` / `Stance` / `Humor` now
uses lower-case wire strings. No external consumer was affected
(verified by grep over `apps/`, `packages/`).

## Checks run

| Command | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo test --workspace` | all green |
| `cargo test -p aether-l6-persona` | 16/16 (+7) |
| `cargo test -p aether-l2-memory --features sqlite-backend` | 11/11 |
| `apps/desktop/src-tauri && cargo test` | 24/24 (+2) |
| `python tools/lint-layer-boundaries/check.py` | OK |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm build` | clean |

## Risks / notes

- **Enum wire format changed.** Serialised forms of `Tone`,
  `Verbosity`, `Stance`, `Humor` are now lowercase. Any pre-existing
  persisted JSON/YAML using PascalCase would no longer deserialise.
  Grep confirmed no such persisted data exists; if release builds
  already shipped snapshots with PascalCase, we'd need a migration
  shim. Flagging for review.
- **No app-data-dir wiring yet.** `main.rs` does not compose
  `app_data_dir() + "/personas"` into `AETHER_PERSONAS_DIR` or
  equivalent. Adding this is a 5-line change once the product path
  is confirmed — I deliberately left it out so the loader can be
  exercised via env var for tests / power users first.
- **Additive-only semantics** means a user cannot override a built-in
  persona via YAML. That's intentional for v0; a later wave can lift
  the restriction under a signature-verified pack surface.
- **`personas/` directory is not a storage API.** The loader re-reads
  the directory on every AppState construction (i.e. boot or persona
  switch, since build_active rebuilds active but catalog stays
  immutable after construction). No hot-reload.

## Next

- Wire `main.rs` to seed `AETHER_PERSONAS_DIR` from the app data dir
  so users can drop YAML files into `%APPDATA%/Aether/personas/`
  without env-var setup.
- Preset settings entry calling `forget_older_than_days` (P1 backend).
- Optional: hot-reload persona packs from a watch loop.
