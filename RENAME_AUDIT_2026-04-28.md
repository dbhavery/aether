# Rename Audit — Aether → Companion (2026-04-28)

> Post-rename grep audit of `apps/desktop/` for any remaining "Aether"
> strings, classified by category. Run after commit `3658242` (rename
> COMPLETE). Findings split into auto-fixed, flagged-for-Don, and
> intentionally-preserved.

## ✓ Auto-fixed this audit pass

### `apps/desktop/src-tauri/Cargo.toml` (commit 09ce7e8)
- Line 4: `description` flipped to "Companion desktop shell v0…".
  Feeds `CARGO_PKG_DESCRIPTION` → `resource.rc` → Windows EXE
  FileDescription. Was the cause of every stale `.d` file in
  `target/debug/deps/` reading "Aether desktop shell v0".
- Line 9: `authors` flipped to "Companion contributors".

## ⚠ Flagged for Don

### 1. `apps/desktop/src/components/SettingsDrawer.tsx:354–366` (USER-FACING UI)

Renders this text in the Memory & Privacy panel footer:

```
Stored locally at %APPDATA%/Aether/media_permissions.json,
%APPDATA%/Aether/mic_permissions.json,
%APPDATA%/Aether/presence.json,
and %APPDATA%/Aether/memory.json
```

**Question:** what is the actual on-disk path?

Tauri 2 with `identifier: "dev.aether.desktop"` typically resolves
`BaseDirectory::AppData` to `%APPDATA%/dev.aether.desktop/`, not
`%APPDATA%/Aether/`. If the displayed text doesn't match what's on
disk, users will hunt in the wrong folder.

**Three possible fixes** — Don picks:
- (a) Match reality: `%APPDATA%/dev.aether.desktop/...`
- (b) Match the rename plan ("db files stay aether"): keep
  "%APPDATA%/Aether/" but verify a custom resolver elsewhere
  actually writes there
- (c) Rename to "%APPDATA%/Companion/" if a public-facing on-disk
  rename is desired (would touch the Rust-side appdata resolver too)

This is not a pure rename question — it's a path-correctness question
that the rename surfaced. Recommend verifying the actual on-disk path
first via the running app, then picking.

### 2. JSDoc / code comments referring to the product as "Aether" (5 sites)

| File | Line | Comment text |
|---|---|---|
| `src/App.tsx` | 367 | "what does Aether remember about me" |
| `src/components/VisionBadge.tsx` | 33 | "restarting Aether" |
| `src/components/TrustDrawer.tsx` | 81 | "what did Aether just decide, and why do I…" |
| `src/components/TrustDrawer.tsx` | 419 | "what Aether also saw" |
| `src/components/TrustDrawer.tsx` | 816 | "Aether routed a turn to a model that took 3.2 s" |
| `src/components/ScreenPanel.tsx` | 29 | "the OS picker drives source selection — Aether…" |

These describe product-as-user-perceives-it from a developer-comment
perspective. Two interpretations:
- **Strict-public-rename:** flip all to Companion since they describe
  the shipping product's behavior.
- **Internal-codename-applies:** leave as Aether since code comments
  are a dev-internal artifact (and "all internal docs/planning/"
  stays Aether per the rename plan).

Recommend: flip them next pass for narrative consistency, but no rush
— users never see these.

### 3. `apps/desktop/src-tauri/capabilities/default.json:4`

Description string: "…Only the Aether-authored commands plus the
minimum core event/window controls are exposed…". This is internal
permission-system documentation. Same call as #2.

## ✓ Intentionally preserved (per rename plan)

- `apps/desktop/src-tauri/Cargo.toml` line 2: `name = "aether-desktop-shell"`
- `apps/desktop/src-tauri/Cargo.toml` line 8: `repository = "https://github.com/dbhavery/aether"`
- `apps/desktop/src-tauri/tauri.conf.json` line 5: `identifier: "dev.aether.desktop"`
- All `bg-aether-*` / `text-aether-*` Tailwind token classes across UI
- All `AETHER_*` env vars
- `db` filenames

## Skipped — stale build artifacts

These will be regenerated on next build and don't need touching:
- `apps/desktop/dist/index.html` (Vite output, says `<title>Aether</title>`)
- `apps/desktop/dist/assets/index-*.js` (built bundle)
- `apps/desktop/src-tauri/target/debug/deps/*.d` (cargo dep files)
- `apps/desktop/src-tauri/target/debug/build/*/out/resource.rc` (now
  regenerates with "Companion" thanks to Cargo.toml fix above)
- `apps/desktop/src-tauri/target/debug/build/*/out/capabilities.json`

## Skipped — internal test fixtures

- `apps/desktop/src/lib/wavEncoder.test.ts:72` — uses "Hello, Aether!"
  as a fixed input string for WAV encoding test. Internal data. No
  change needed.

## Build state at audit time

- `npx vitest run`: 232/232 pass (commit f00ca95)
- `npx tsc -b --noEmit`: clean (commit f00ca95)
- `cargo check --manifest-path apps/desktop/src-tauri/Cargo.toml`:
  warnings only, no errors (commit 09ce7e8)
- Workspace `cargo check --workspace`: warnings only

Rename is mechanically sound. Ambiguous items are pure judgment calls.
