# Memory V2 step 2 — memory.json + policy surface — execution report (2026-05-16)

**Status:** Shipped locally on `dev`. Push not authorized.

## Goal

Land the policy/config surface for the L5 capabilities that landed
in step 1. Per `docs/MEMORY-V2-ARCHITECTURE.md` §3: `memory.json`
config file (retention + per-domain default risk + embeddings
opt-in), Tauri get/set commands, Settings section. **No L2
consumer in this slice** — step 3 wires the write/read plumbing
through the new policy surface.

## Surfaces touched

### `apps/desktop/src-tauri/src/memory_config.rs` (new)

- `MemoryDomain` enum — six variants per design §1 (Session,
  Durable, Facts, Projects, Preferences, Artifacts). Serde
  wire format is snake-case. `ALL` const + `label()` for UI.
- `MemoryRisk` enum — `Auto` / `Ask` / `Deny`. Lowercase serde.
- `MemoryConfig` struct:
  - `retention_days: BTreeMap<MemoryDomain, Option<u16>>` (days;
    `None` = keep until forgotten).
  - `default_risk: BTreeMap<MemoryDomain, MemoryRisk>`.
  - `embeddings: EmbeddingsConfig` (enabled, provider).
- Missing domains in the persisted maps fall back to design
  defaults via `risk_for` / `retention_for` accessors —
  additive-safe.
- Same contract as every other Aether config: additive,
  default-safe on read, unknown fields silently ignored, unknown
  fields dropped on rewrite, atomic writes.
- 10 tests: defaults lock, all-domains enumerated, labels,
  missing → defaults, save / load round trip, malformed fallback,
  unknown fields ignored / dropped, partial config, missing map
  entries fall back, canonical path.

### `apps/desktop/src-tauri/src/main.rs`

- New `mod memory_config;`.
- On boot, after `attach_presence_config_file`, also calls
  `state.attach_memory_config_file(memory_config::config_path_for(&dir))`.
- Registers `get_memory_config` + `set_memory_config` commands.

### `apps/desktop/src-tauri/src/state.rs`

- New fields on `AppState`: `memory_config: RwLock<MemoryConfig>`
  and `memory_config_path: Option<PathBuf>`.
- `attach_memory_config_file`, `memory_config()`,
  `set_memory_config()` helpers.
- `set_memory_config` rejects `embeddings.enabled = true` with an
  unset or empty provider — catches the "embeddings on but
  nothing wired" state at the policy boundary instead of letting
  the later embeddings slice fail silently.

### `apps/desktop/src-tauri/src/commands.rs`

- `get_memory_config` / `set_memory_config` Tauri commands. Full-
  snapshot wire semantics (no partial patch).

### `apps/desktop/src/lib/types.ts` + `api.ts`

- `MemoryDomain` / `MemoryRisk` type unions.
- `MemoryConfig` interface.
- `MEMORY_DOMAINS` array and `MEMORY_CONFIG_DEFAULTS` mirror so
  the UI can render sensible rows before the first round trip.
- `getMemoryConfig` / `setMemoryConfig` API wrappers.

### `apps/desktop/src/components/SettingsDrawer.tsx`

- New Memory section below Presence:
  - Six `MemoryRiskRow` rows (one per domain).
  - Tri-state radio (Auto / Ask / Deny) per row mirroring the
    Media permission affordance so the two surfaces feel like
    siblings.
  - Retention shown as a read-only hint ("retained 30 days" /
    "kept until forgotten") — retention-days editing lands with
    the sweep slice.
  - `MEMORY_DOMAIN_COPY` provides short human-readable titles +
    hints per domain; `MEMORY_RISK_COPY` provides the tri-state
    label + colour (reuses `aether-ok / -warn / -err`).

### Persistence

- File: `%APPDATA%/Aether/memory.json` (unix: `$XDG_DATA_HOME/…`).
- Also mentioned in the Settings drawer's "stored locally at …"
  footer alongside the other config files.

## Checks — all green

- `cargo test -p aether-desktop-shell --features …` — **175 / 175**
  (+11 over the pre-Memory-V2-step-2 baseline).
- `apps/desktop && pnpm typecheck && pnpm build && pnpm test` —
  unchanged / 145 / 145.

## Hard-constraint compliance

- **No L2 consumer yet.** ✅ Policy/config surface only.
- **No `AuditRecordEvent` shape change.** ✅ Additive wire format
  only.
- **No raw-media persistence.** ✅ Memory config stores policy,
  not items.
- **User-sensitive domains default Ask.** ✅ Facts + Artifacts
  ship `Ask`; others `Auto`. Verified by the
  `defaults_match_design_doc` test.
- **Embeddings opt-in and off by default.** ✅ Enabling without
  a provider is rejected at the boundary.
- **Additive config contract.** ✅ Round-trip + unknown-fields-
  ignored + unknown-fields-dropped-on-rewrite tests locked.

## Design decisions worth noting

1. **`BTreeMap` over `HashMap`.** Stable key order gives us
   deterministic JSON output — diffs against previously-saved
   configs are readable.
2. **Missing map entries fall back to design defaults on the
   lookup path** (`risk_for` / `retention_for`), not during
   deserialization. That means a future build can drop a domain
   silently and older personas keep working without special
   migration code.
3. **Boundary-layer validation for the embeddings pair.** The
   runtime will eventually validate the provider at adapter-
   construction time, but rejecting `enabled = true` without a
   provider here keeps the UI honest and saves a confusing
   round-trip.
4. **Retention shown read-only in v1.** The sweep doesn't exist
   yet; exposing editable day counts would imply a contract we
   don't honor. The config supports it; the UI just doesn't
   expose the editors until step 5 lands.
5. **Separate Settings section from Presence.** Memory is its own
   mental model (write posture, retention, provenance); coupling
   it to presence would confuse users. Presence is "is the user
   here?"; Memory is "what does Aether remember?".

## What is deliberately NOT in this slice

- L2 plumbing — step 3 wires `MemoryConfig::risk_for` into the
  memory-write path.
- Memory tab in Trust drawer — step 4.
- Retention sweep — step 5.
- Embedding provider — step 6.
- Rot guard (`tools/lint-memory-doc/`) — step 7.

## Next step

Memory V2 step 3 — per-domain write/read plumbing. Wire the new
Memory V2 capabilities into L2's write/read paths; route user-
sensitive domains through the Ask flow using the policy surface
that just landed.
