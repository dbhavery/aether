# P2 — Runtime vision provider swap (2026-04-26)

## Goal

Let the user inspect and switch the active vision provider at runtime
without editing env vars or restarting the shell.

## What shipped

### Shell — `apps/desktop/src-tauri/src/vision_registry.rs` (new)

- `VisionRegistry` owns:
  - a `Vec<RegisteredProvider>` (insertion order is the fallback
    order),
  - a `RwLock<Option<String>>` for the active provider id,
  - an optional `PathBuf` for the on-disk persistence file.
- `VisionPersistedState { active: Option<String> }` — tiny JSON shape
  written to `<app_data>/vision_provider.json`.
- Fallback contract:
  - persisted unknown id → first-registered wins,
  - persisted `None` → text-only mode honoured even when providers
    are registered (the user explicitly chose it),
  - missing file → no auto-selection until
    `auto_select_first_if_unset` is called,
  - corrupt JSON → safe default (no crash).
- 11 unit tests cover every branch above.

### Shell — `state.rs`

- `AppState` field `vision_provider: Option<Arc<dyn VisionProvider>>`
  → `vision: RwLock<VisionRegistry>`.
- New accessors: `register_vision_provider`,
  `attach_vision_persistence`, `vision_auto_select_if_unset`,
  `vision_active_id`, `vision_provider_list`,
  `set_active_vision_provider`. Existing `vision_provider()` still
  works (now reads through the registry); `vision_provider_label()`
  preserved.

### Shell — `main.rs`

- New `wire_vision_registry` pass:
  1. registers each configured provider whose healthcheck passes,
  2. attaches persistence (when an app data dir is available),
  3. auto-selects the first registered provider when nothing was
     persisted,
  4. logs the active provider label (or "text-only fallback").
- Each adapter is registered through its own
  `register_*_if_configured` helper, gated by its own cargo feature.

### Shell — `commands.rs`

- `vision_status` now returns `{ enabled, active_id, label,
  providers: [{id, label, active}] }` — a single round trip is enough
  to render the dropdown + status badge.
- New `list_vision_providers` for callers that only need the
  inventory.
- New `set_active_vision_provider(id)` — accepts a provider id, or
  the wire sentinels `null` / `""` / `"none"` for text-only mode.
  Unknown ids are rejected with a structured error.

### Shell — `Cargo.toml`

- New `vision-llamacpp` feature wires through to L4's same-named
  feature.

### Frontend — `lib/types.ts`, `lib/api.ts`

- New `VisionProviderInfo` type and extended `VisionStatus`.
- New `setActiveVisionProvider(id)` typed wrapper.

### Frontend — `components/VisionBadge.tsx`

- Status + dropdown control. Shows the active route as a coloured
  pill (green when a vision provider is active, neutral when
  text-only) plus the active label inline.
- `<select>` lists every registered provider plus a sentinel
  "Text-only fallback" option. Picking an entry POSTs to
  `set_active_vision_provider`; the new status snapshot is echoed
  back and rendered in one cycle.
- When zero providers are registered the dropdown is hidden and
  the explanatory copy lists both env vars
  (`AETHER_OLLAMA_VISION_MODEL`, `AETHER_LLAMACPP_VISION_MODEL`).

## Verification

- `cargo fmt --all -- --check` — clean.
- `cargo check --workspace` — clean.
- Shell tests: 48 default, **54 with both provider features** (was
  37 / 43; +11 registry tests).
- `pnpm typecheck && pnpm build` — clean.
- `python tools/lint-layer-boundaries/check.py` — 0 violations.

## Decisions for review

- **Hot swap is real.** Selection takes effect on the next
  `analyze_frame` call — no restart needed. Verified by
  test `persistence_round_trips_active_selection` and by the
  end-to-end accessor flow.
- **Persistence is a single-key JSON file**
  (`<app_data>/vision_provider.json`). Deliberately tiny — only the
  active id is persisted. New fields can be added later without
  migration because deserialization defaults `active` to `None`.
- **Text-only mode is a first-class persisted state.** A user who
  picks "Text-only fallback" stays on text-only across restarts even
  if Ollama vision is configured at boot.
- **No model-list discovery.** The dropdown shows registered
  providers, not all models the daemon has. Model discovery would
  require provider-specific list calls; out of scope this run.
- **`#[allow(dead_code)]` markers** on `VisionRegistry::len` and
  `is_empty` because they're only exercised in tests today.
