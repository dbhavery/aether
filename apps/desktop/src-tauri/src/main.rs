// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod adapter;
mod backfill;
mod commands;
mod hardware;
mod idle_probe;
mod media_permissions;
mod memory_config;
mod memory_router;
mod memory_service;
mod mic_permissions;
mod presence_config;
mod provider;
mod retrieval;
mod state;
mod tier;
mod vision_cache;
mod vision_registry;
mod voice_registry;

use state::AppState;
use std::sync::Arc;
use std::time::Duration;
use tauri::Manager;

/// Poll interval for the presence attention loop. 1 Hz is coarse
/// enough that the loop is effectively free and fine enough that an
/// `idle_after_s = 10` threshold is honored within a second. The
/// design doc §2 suggested 2 Hz; 1 Hz is the conservative default —
/// threshold resolution is in seconds, not milliseconds.
const PRESENCE_POLL_MS: u64 = 1_000;

/// Interval between Memory V2 retention sweep ticks once the shell
/// is running. One hour is deliberate: retention TTLs are measured
/// in days, so anything sub-hourly is noise; anything supra-hourly
/// leaves the "Durable = 30 days" policy visibly stale near a day
/// boundary. Not user-configurable in this phase (see design §10
/// item 5 and ADR-0001's follow-up notes).
const RETENTION_SWEEP_INTERVAL_MS: u64 = 60 * 60 * 1_000;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|_app, _argv, _cwd| {
            // Placeholder — second-instance focuses the main window via
            // tauri-plugin-single-instance's default behaviour when given
            // an empty handler. A richer handler can route CLI args into
            // the running instance later.
        }))
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .setup(|app| {
            // Resolve the app state *after* Tauri has initialised so we can
            // use its path resolver. The durable session memory file lives
            // beside the window-state plugin's data under the OS-native app
            // data dir (e.g. %APPDATA%/Aether on Windows).
            let app_state = build_app_state(app.handle())?;
            // ADR-0007 D5 (Phase 4D) — wrap in `Arc` so the async backfill
            // worker can hold its own clone independent of the IPC
            // thread's `State<...>` borrow. Tauri's `manage<T>` stores
            // the value in a `Pin<Box<T>>` whose reference cannot escape
            // the calling command's lifetime; an `Arc` lets background
            // tasks keep state alive past command return.
            app.manage(Arc::new(app_state));
            // Memory V2 step 5: run the retention sweep once at boot,
            // before the first command is served. Evicting expired
            // rows up front means the first `memory_recent` the UI
            // asks for will not surface anything the user's
            // `memory.json` policy said should already be gone.
            // Failures trace and are ignored — a sweep that can't run
            // must not take the shell offline.
            if let Some(state) = app.try_state::<Arc<AppState>>() {
                let now_ms = state.next_ts();
                match state.run_retention_sweep(now_ms) {
                    Ok(n) => tracing::info!("retention sweep (boot): evicted {n} row(s)"),
                    Err(e) => tracing::warn!("retention sweep (boot) failed: {e}"),
                }
            }
            // Presence V1 step 2: spawn the attention poll loop. Uses
            // `tauri::async_runtime::spawn` to run on Tauri's own tokio
            // runtime so we don't stand up a second one. The loop is
            // cheap — one `GetLastInputInfo` call per tick on Windows,
            // a no-op on unsupported platforms — and a transition only
            // produces an event when the state label actually changes.
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                run_presence_loop(handle).await;
            });
            // Memory V2 step 5: hourly retention sweep tick. Runs on
            // the same Tauri tokio runtime as the presence loop.
            let sweep_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                run_retention_sweep_loop(sweep_handle).await;
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::companion_banner,
            commands::submit_turn,
            commands::resolve_approval,
            commands::presence_current,
            commands::memory_recent,
            commands::clear_session,
            commands::audit_recent,
            commands::list_personas,
            commands::switch_persona,
            commands::set_autonomy_preset,
            commands::current_autonomy_preset,
            commands::forget_older_than_days,
            commands::telemetry_recent,
            commands::telemetry_clear,
            commands::get_media_permissions,
            commands::set_media_permission,
            commands::get_mic_permission,
            commands::set_mic_permission,
            commands::get_presence_config,
            commands::set_presence_config,
            commands::presence_status,
            commands::presence_recent_history,
            commands::get_memory_config,
            commands::set_memory_config,
            commands::get_tier,
            commands::set_tier,
            commands::redetect_hardware,
            commands::embeddings_readiness,
            commands::backfill_status,
            commands::backfill_count,
            commands::start_backfill,
            commands::cancel_backfill,
            commands::memory_list,
            commands::memory_forget,
            commands::memory_forget_item,
            commands::memory_forget_item_after_approval,
            commands::memory_edit,
            commands::memory_edit_after_approval,
            commands::analyze_frame,
            commands::transcribe_utterance,
            commands::voice_status,
            commands::list_speech_providers,
            commands::list_speech_models,
            commands::refresh_speech_models,
            commands::set_active_speech_provider,
            commands::set_active_speech_model,
            commands::vision_status,
            commands::list_vision_providers,
            commands::list_vision_models,
            commands::refresh_vision_models,
            commands::set_active_vision_provider,
            commands::set_active_vision_model,
        ])
        .run(tauri::generate_context!())
        .expect("error while running aether-desktop");
}

/// Wire the [`AppState`] against the OS-native app data directory so the
/// durable session memory store has a stable home across launches.
///
/// On builds compiled without `sqlite-backend` (or on path-resolution
/// failure) we fall back to [`AppState::new`] which uses the in-memory
/// store. The shell must still boot either way — a missing data dir is
/// not a valid reason to deny the user their companion.
fn build_app_state(app: &tauri::AppHandle) -> Result<AppState, Box<dyn std::error::Error>> {
    #[cfg(feature = "sqlite-backend")]
    {
        match app.path().app_data_dir() {
            Ok(dir) => {
                // Wire the persona-pack loader to look in
                // `<app_data>/personas/`. Only seed the env var if the
                // caller hasn't already set one — that way dev /
                // CI / power users can still override with their own
                // directory.
                if std::env::var_os("AETHER_PERSONAS_DIR").is_none() {
                    let personas = dir.join("personas");
                    if let Err(e) = seed_persona_pack_dir(app, &personas) {
                        tracing::warn!(
                            "persona pack seed failed: {e}; \
                             pack dir will scan whatever already exists"
                        );
                    }
                    std::env::set_var("AETHER_PERSONAS_DIR", &personas);
                    tracing::info!("persona pack dir set to {}", personas.display());
                }
                let db_path = dir.join("aether.db");
                tracing::info!(
                    "initialising AppState with durable session memory at {}",
                    db_path.display()
                );
                let mut state = AppState::new_with_db_path(db_path)?;
                let perms_path = media_permissions::permissions_path_for(&dir);
                tracing::info!("media permissions file at {}", perms_path.display());
                state.attach_media_permissions_file(perms_path);
                let mic_path = mic_permissions::permission_path_for(&dir);
                tracing::info!("mic permission file at {}", mic_path.display());
                state.attach_mic_permission_file(mic_path);
                let presence_path = presence_config::config_path_for(&dir);
                tracing::info!("presence config file at {}", presence_path.display());
                state.attach_presence_config_file(presence_path);
                let memory_cfg_path = memory_config::config_path_for(&dir);
                tracing::info!("memory config file at {}", memory_cfg_path.display());
                state.attach_memory_config_file(memory_cfg_path);
                let tier_cfg_path = tier::config_path_for(&dir);
                tracing::info!("tier config file at {}", tier_cfg_path.display());
                state.attach_tier_config_file(tier_cfg_path);
                // ADR-0006 D2 + D3 — run a hardware-detection pass on
                // first launch and on every subsequent launch where
                // the user hasn't manually overridden. Light-usage:
                // wgpu adapter enumeration + sysinfo + 750ms HTTP
                // probe; no model loads. Persisted snapshot informs
                // tier-aware subsystems (embeddings onboarding via
                // ADR-0007 D7 today; future TTS / vision / avatar).
                if let Err(e) = state.redetect_hardware() {
                    tracing::warn!("boot-time hardware detection failed: {e}");
                }
                // ADR-0007 D2 + D3 — boot probe wires the initial
                // retrieval readiness state. Light-usage: HTTP GET on
                // /api/tags with 750ms timeout, no model loads. State
                // self-heals on every subsequent real turn (D3
                // symmetric event-driven cadence) so a flaky probe
                // here is harmless.
                let initial = state.probe_readiness_now();
                tracing::info!("boot-time retrieval readiness: {initial:?}");
                wire_vision_registry(&state, Some(&dir));
                wire_voice_registry(&state, Some(&dir));
                return Ok(state);
            }
            Err(e) => {
                tracing::warn!(
                    "could not resolve app_data_dir: {e}; using in-memory session store"
                );
            }
        }
    }
    let state = AppState::new()?;
    wire_vision_registry(&state, None);
    wire_voice_registry(&state, None);
    Ok(state)
}

/// Seed the user-facing persona pack directory from Tauri-bundled
/// resources on first launch.
///
/// The desktop installer ships flat-schema yaml packs at
/// `resources/personas/*.yaml` (see `tauri.conf.json` `bundle.resources`
/// and `scripts/persona_generator/generate_flat_packs.py`). Without
/// this seeding step the user's `<app_data>/personas/` dir is empty
/// at first launch and the persona-pack loader falls through to the
/// 3 hard-coded built-ins, which means the wizard renders only one
/// pickable cast member (aurora). Seeding promotes the bundled cast
/// to live catalog entries the moment the shell boots.
///
/// **Idempotent.** Files that already exist in the destination are
/// not overwritten — power users who hand-edit a pack keep their
/// edits across launches. Only the first-launch (empty dir) case
/// fully populates the cast. A new file added in a future release
/// will land on every user's machine because the per-file copy
/// check is "destination missing", not "directory missing".
///
/// Failures are non-fatal: the caller logs and continues with
/// whatever YAMLs the user already has on disk.
#[cfg(feature = "sqlite-backend")]
fn seed_persona_pack_dir(
    app: &tauri::AppHandle,
    dest: &std::path::Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let resource_dir = app
        .path()
        .resolve("resources/personas", tauri::path::BaseDirectory::Resource)?;
    if !resource_dir.is_dir() {
        // Bundled resources weren't packaged (e.g. dev runs without
        // `tauri build`, or a custom build that strips resources).
        // Treat as a no-op rather than an error — the loader still
        // works against whatever is on disk.
        tracing::info!(
            "no bundled persona resources at {}; skipping seed",
            resource_dir.display()
        );
        return Ok(());
    }
    std::fs::create_dir_all(dest)?;
    let mut copied = 0u32;
    let mut skipped = 0u32;
    for entry in std::fs::read_dir(&resource_dir)? {
        let entry = entry?;
        let src = entry.path();
        let ext = src.extension().and_then(|e| e.to_str()).unwrap_or("");
        if !matches!(ext, "yaml" | "yml") {
            continue;
        }
        let Some(file_name) = src.file_name() else {
            continue;
        };
        let target = dest.join(file_name);
        if target.exists() {
            skipped += 1;
            continue;
        }
        std::fs::copy(&src, &target)?;
        copied += 1;
    }
    tracing::info!(
        "persona pack seed: copied {copied} new file(s), skipped {skipped} existing in {}",
        dest.display()
    );
    Ok(())
}

/// Build the vision provider registry — register every provider whose
/// boot-time healthcheck passes, attach the persistence file (when an
/// app data dir is available), then auto-select the first registered
/// provider if no persisted active id was loaded.
///
/// Each provider is feature-gated independently; the registry stays
/// empty when no provider features are compiled in (or when none of
/// the configured providers healthcheck) — the `analyze_frame`
/// command falls back to its text-only path in that case.
fn wire_vision_registry(state: &AppState, app_data_dir: Option<&std::path::Path>) {
    register_ollama_vision_if_configured(state);
    register_llamacpp_vision_if_configured(state);
    if let Some(dir) = app_data_dir {
        let path = vision_registry::vision_persistence_path_for(dir);
        tracing::info!("vision provider persistence at {}", path.display());
        state.attach_vision_persistence(path);
    }
    state.vision_auto_select_if_unset();
    // First-launch seeding: if `model_per_provider` is missing entries
    // for any registered adapter, fill them from each adapter's
    // current model id (the env-supplied default at boot). Idempotent
    // on later boots — adapters whose models were already persisted
    // are left alone.
    if let Err(e) = state.vision_seed_missing_models() {
        tracing::warn!("vision: first-launch model seeding failed: {e}; continuing");
    }
    if let Some(label) = state.vision_provider_label() {
        tracing::info!("vision provider active: {}", label);
    } else {
        tracing::info!("no vision provider active; analyze_frame on text-only fallback");
    }
}

#[cfg(feature = "ollama-provider")]
fn register_ollama_vision_if_configured(state: &AppState) {
    use std::sync::Arc;

    use aether_l4_router::{OllamaVisionConfig, OllamaVisionProvider, VisionProvider};
    let Some(parsed) = OllamaVisionConfig::from_env() else {
        return;
    };
    match parsed {
        Ok(cfg) => {
            tracing::info!(
                "vision provider candidate: ollama model={} base={}",
                cfg.model,
                cfg.base_url
            );
            let base = cfg.base_url.clone();
            let provider = OllamaVisionProvider::new(cfg);
            if let Err(e) = provider.healthcheck() {
                tracing::warn!("ollama vision healthcheck failed at {base}: {e}; not registering",);
                return;
            }
            let arc: Arc<dyn VisionProvider> = Arc::new(provider);
            tracing::info!("registering vision provider: {}", arc.label());
            state.register_vision_provider(arc);
        }
        Err(e) => {
            tracing::warn!("AETHER_OLLAMA_VISION_* config invalid: {e}");
        }
    }
}

#[cfg(not(feature = "ollama-provider"))]
fn register_ollama_vision_if_configured(_state: &AppState) {}

#[cfg(feature = "vision-llamacpp")]
fn register_llamacpp_vision_if_configured(state: &AppState) {
    use std::sync::Arc;

    use aether_l4_router::{LlamaCppVisionConfig, LlamaCppVisionProvider, VisionProvider};
    let Some(parsed) = LlamaCppVisionConfig::from_env() else {
        return;
    };
    match parsed {
        Ok(cfg) => {
            tracing::info!(
                "vision provider candidate: llamacpp model={} base={}",
                cfg.model,
                cfg.base_url
            );
            let base = cfg.base_url.clone();
            let provider = LlamaCppVisionProvider::new(cfg);
            if let Err(e) = provider.healthcheck() {
                tracing::warn!(
                    "llamacpp vision healthcheck failed at {base}: {e}; not registering",
                );
                return;
            }
            let arc: Arc<dyn VisionProvider> = Arc::new(provider);
            tracing::info!("registering vision provider: {}", arc.label());
            state.register_vision_provider(arc);
        }
        Err(e) => {
            tracing::warn!("AETHER_LLAMACPP_VISION_* config invalid: {e}");
        }
    }
}

#[cfg(not(feature = "vision-llamacpp"))]
fn register_llamacpp_vision_if_configured(_state: &AppState) {}

/// Build the speech provider registry — register every provider whose
/// boot-time healthcheck passes, attach the persistence file (when an
/// app data dir is available), then auto-select the first registered
/// provider if no persisted active id was loaded.
///
/// Each provider is feature-gated independently; the registry stays
/// empty when no provider features are compiled in (or when none of
/// the configured providers healthcheck). Voice V1 step 4's
/// `transcribe_utterance` surfaces a clear "no active speech
/// provider" error in that case — unlike vision, there is no silent
/// text fallback for voice.
fn wire_voice_registry(state: &AppState, app_data_dir: Option<&std::path::Path>) {
    register_whispercpp_speech_if_configured(state);
    if let Some(dir) = app_data_dir {
        let path = voice_registry::voice_persistence_path_for(dir);
        tracing::info!("voice provider persistence at {}", path.display());
        state.attach_voice_persistence(path);
    }
    state.voice_auto_select_if_unset();
    if let Err(e) = state.voice_seed_missing_models() {
        tracing::warn!("voice: first-launch model seeding failed: {e}; continuing");
    }
    if let Some(label) = state.speech_provider_label() {
        tracing::info!("voice provider active: {}", label);
    } else {
        tracing::info!("no voice provider active; transcribe_utterance will error loudly");
    }
}

#[cfg(feature = "speech-whispercpp")]
fn register_whispercpp_speech_if_configured(state: &AppState) {
    use std::sync::Arc;

    use aether_l4_router::{SpeechProvider, WhisperCppSpeechConfig, WhisperCppSpeechProvider};
    let Some(parsed) = WhisperCppSpeechConfig::from_env() else {
        return;
    };
    match parsed {
        Ok(cfg) => {
            tracing::info!(
                "voice provider candidate: whispercpp model={} base={}",
                cfg.model,
                cfg.base_url
            );
            let base = cfg.base_url.clone();
            let provider = WhisperCppSpeechProvider::new(cfg);
            if let Err(e) = provider.healthcheck() {
                tracing::warn!(
                    "whispercpp speech healthcheck failed at {base}: {e}; not registering",
                );
                return;
            }
            let arc: Arc<dyn SpeechProvider> = Arc::new(provider);
            tracing::info!("registering voice provider: {}", arc.label());
            state.register_speech_provider(arc);
        }
        Err(e) => {
            tracing::warn!("AETHER_WHISPERCPP_SPEECH_* config invalid: {e}");
        }
    }
}

#[cfg(not(feature = "speech-whispercpp"))]
fn register_whispercpp_speech_if_configured(_state: &AppState) {}

/// Presence V1 step 2 — the attention poll loop.
///
/// Spawned once from the Tauri setup hook; runs for the life of the
/// app. Each tick:
///
/// 1. Sleeps for `PRESENCE_POLL_MS`.
/// 2. Reads the platform idle probe (Windows: `GetLastInputInfo`;
///    macOS / Linux: `None` until their probes ship).
/// 3. Feeds `(now_ms, idle_seconds)` into
///    [`AppState::attention_tick`] via
///    [`commands::drive_attention_tick`].
/// 4. On transition, emits `presence:attention` to the webview and
///    pushes a `PresenceHistoryEntry` onto the shell's bounded ring.
///
/// The loop never unwraps — a missing `AppState` (shouldn't happen in
/// practice) short-circuits to another sleep; a poisoned lock is
/// reported via tracing and skipped.
async fn run_presence_loop(app: tauri::AppHandle) {
    let probe = idle_probe::platform_probe();
    tracing::info!("presence loop: idle probe = {}", probe.label());
    let mut interval = tokio::time::interval(Duration::from_millis(PRESENCE_POLL_MS));
    interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    loop {
        interval.tick().await;
        let Some(state) = app.try_state::<Arc<AppState>>() else {
            // Still booting; sleep for a tick and retry.
            continue;
        };
        let now_ms = state.next_ts();
        let idle = probe.idle_seconds();
        commands::drive_attention_tick(&app, &state, now_ms, idle);
    }
}

/// Memory V2 step 5 — hourly retention-sweep tick.
///
/// Boot-time eviction happens in `setup` before this loop spawns.
/// `tokio::time::interval` fires immediately on the first `.tick()`,
/// so we consume-and-skip that tick to avoid a second sweep right
/// after boot; subsequent ticks are spaced by
/// `RETENTION_SWEEP_INTERVAL_MS`.
async fn run_retention_sweep_loop(app: tauri::AppHandle) {
    let mut interval = tokio::time::interval(Duration::from_millis(RETENTION_SWEEP_INTERVAL_MS));
    interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    // Swallow the immediate first tick — boot sweep already ran.
    interval.tick().await;
    loop {
        interval.tick().await;
        let Some(state) = app.try_state::<Arc<AppState>>() else {
            continue;
        };
        let now_ms = state.next_ts();
        match state.run_retention_sweep(now_ms) {
            Ok(0) => tracing::trace!("retention sweep (tick): no evictions"),
            Ok(n) => tracing::info!("retention sweep (tick): evicted {n} row(s)"),
            Err(e) => tracing::warn!("retention sweep (tick) failed: {e}"),
        }
    }
}

#[cfg(test)]
mod bundled_persona_pack_tests {
    //! Contract tests for the bundled flat-schema persona packs.
    //!
    //! `scripts/persona_generator/generate_flat_packs.py` emits one
    //! v0-compatible YAML per cast member into
    //! `resources/personas/`. These files are bundled by the desktop
    //! installer (see `tauri.conf.json` `bundle.resources`) and
    //! seeded into the user's `<app_data>/personas/` on first boot
    //! by `seed_persona_pack_dir`. If the schemas drift apart these
    //! tests fail at `cargo test` time rather than at user boot
    //! time.

    use std::path::PathBuf;

    fn bundled_resource_dir() -> PathBuf {
        // Tests run with cwd = `apps/desktop/src-tauri/`. The bundled
        // resources live one level up under `resources/personas/`.
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources/personas")
    }

    #[test]
    fn every_bundled_persona_pack_loads_via_l6_loader() {
        let dir = bundled_resource_dir();
        assert!(
            dir.is_dir(),
            "bundled persona resource dir missing at {} — \
             did `generate_flat_packs.py` get committed?",
            dir.display()
        );
        let profiles = aether_l6_persona::load_pack_dir(&dir).unwrap_or_else(|e| {
            panic!(
                "bundled persona pack failed to load through l6 pack_loader: {e}; \
                 schemas have drifted between generator and loader"
            )
        });
        assert!(
            profiles.len() >= 8,
            "expected >=8 bundled persona packs (the v0 cast minus aurora collision), \
             got {} in {}",
            profiles.len(),
            dir.display()
        );
    }

    #[test]
    fn bundled_persona_ids_are_unique_and_non_empty() {
        let dir = bundled_resource_dir();
        let profiles = aether_l6_persona::load_pack_dir(&dir).expect("load_pack_dir");
        let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
        for p in &profiles {
            assert!(!p.persona_id.0.trim().is_empty(), "empty persona_id");
            assert!(
                seen.insert(p.persona_id.0.clone()),
                "duplicate persona_id {:?} in bundled packs",
                p.persona_id.0
            );
        }
    }
}
