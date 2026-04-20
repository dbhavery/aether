# P1 — Media permission model + Settings surface (2026-04-25)

## Goal

Land the foundation for video-assistant work: a clear, local-only
permission model the rest of the multimodal stack consults before
touching the camera or screen.

## What shipped

### Rust — `apps/desktop/src-tauri/src/media_permissions.rs` (new)

- `enum PermissionState { Allow, Ask, Deny }` with lowercase serde
  rename. `Default = Ask`.
- `enum MediaKind { Camera, Screen }` with the same wire shape.
- `struct MediaPermissions { camera, screen }`. Default = both `Ask`.
- `enum CaptureGate { Proceed, PromptUser, Deny }` — what a capture
  site should do given the current posture. Future camera/screen
  code paths branch on this.
- `load_or_default(path)` / `save(path, perms)` — atomic
  write-to-temp-then-rename JSON persistence.
- `permissions_path_for(app_data_dir)` — canonical file location
  helper.

Nine unit tests: defaults, gate evaluation, set isolation, missing
file fallback, malformed JSON fallback, save→load round-trip, wire
parsing for both enums, lowercase JSON shape, path helper.

### Rust — `apps/desktop/src-tauri/src/state.rs`

- `AppState` gains `media_permissions: RwLock<MediaPermissions>` and
  `media_permissions_path: Option<PathBuf>`.
- `attach_media_permissions_file(path)` loads from disk and remembers
  the path for subsequent writes.
- `media_permissions()` snapshot accessor.
- `set_media_permission(kind, state)` — updates and persists,
  surfacing persistence failures so the UI can tell the user the
  change did not stick.
- `evaluate_media_permission(kind)` — the gate future capture sites
  call.
- Three new tests: defaults after boot, in-memory set updates the
  gate, file round-trips across two AppStates pointing at the same
  file.

### Rust — `apps/desktop/src-tauri/src/main.rs`

- Module registered.
- `build_app_state` now wires
  `<app_data>/media_permissions.json` into the AppState alongside
  `aether.db` and the personas dir.

### Rust — `apps/desktop/src-tauri/src/commands.rs`

- `get_media_permissions` — returns the snapshot.
- `set_media_permission(kind, state_value)` — wire-format parse +
  forward to AppState, returning the resulting snapshot. Unknown
  values are rejected with a structured error.

### Frontend — `apps/desktop/src/lib/types.ts`, `api.ts`

- `MediaPermissionState`, `MediaKind`, `MediaPermissions` mirrored.
- `getMediaPermissions()`, `setMediaPermission(kind, state)` typed
  IPC wrappers.

### Frontend — `apps/desktop/src/components/SettingsDrawer.tsx` (new)

- Right-side drawer mirroring the existing Trust drawer's visual
  language.
- "Media" section with two `PermissionRow` cards (camera, screen),
  each carrying a tri-state radio group (`Allow` / `Ask` / `Never`)
  and explanatory copy.
- Footer notes the on-disk location (`%APPDATA%/Aether/
  media_permissions.json`) so power users know where to look.
- Errors from the IPC layer are surfaced inline; busy state disables
  the radios for the in-flight device only.

### Header / App wiring

- `Header.tsx` gains a "Settings" button that opens the drawer.
- `App.tsx` widens the `drawer` discriminant to include `"settings"`
  and renders the new drawer.

### Docs

- `docs/MEDIA-PERMISSIONS.md` documents the wire shape, persistence
  location, enforcement contract, and command surface.

## Verification

- `cargo fmt --all -- --check` — clean.
- `cargo check --workspace` — clean (existing warnings only).
- `cargo test --workspace` — passes.
- `cargo test -p aether-l2-memory --features sqlite-backend` — clean.
- `cargo test -p aether-l6-persona` — clean.
- `cd apps/desktop/src-tauri && cargo test` — **37 passed** (was 24;
  added 12 new media-permission tests across the module + state).
- `python tools/lint-layer-boundaries/check.py` — 0 violations.
- `cd apps/desktop && pnpm typecheck && pnpm build` — clean.

## Notes for review

- `Deny` is the "Never" semantic from the product spec. The string
  shown to the user reads "Never" but the wire / persistence shape is
  `deny` so the JSON file matches what users would expect from the
  underlying capability model.
- The screen device is part of the model from day one even though no
  capture path consumes it yet. Adding the second device later would
  have meant a wire-format break for a tiny ergonomics gain.
- A persistence failure on `set_media_permission` returns an error to
  the UI (not silently logged) so the user can see the change did not
  stick. The opposite would let a Deny look like it stuck across
  restart when it actually did not.
- No capture path exists yet — this is the foundation slice. P2/P3
  consume it.
