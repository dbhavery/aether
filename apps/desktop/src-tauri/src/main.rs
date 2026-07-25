// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod adapter;
mod backfill;
mod browser_commands;
mod commands;
mod files_commands;
mod hardware;
mod idle_probe;
mod media_permissions;
mod memory_config;
mod memory_router;
mod memory_service;
mod mic_permissions;
mod policy_sink;
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

/// Ed25519 public key for verifying signed persona manifests
/// (ADR-0012 §6). Base64-encoded to keep the binary diff small and
/// the value human-inspectable.
///
/// **Provenance.** The fixture value below is the deterministic
/// keypair used by the cross-language verifier test
/// (`packages/l6-persona/tests/cross_language_verify.rs`, seed
/// `[7u8; 32]`). It is **NOT a real release key** — anyone with the
/// repo can derive the matching secret. Don runs
/// `python infra/persona-manifest/keygen.py` once when ready to ship
/// real Tier-2 packs, then replaces this constant with the contents
/// of `~/.aether/release-key/aether-release-ed25519.pk.b64`.
///
/// Until then, the constant is wired so callers can be tested
/// end-to-end against the fixture, and the swap-to-real-key
/// motion is a single-line edit.
const RELEASE_PUBLIC_KEY_B64: &str = "d5MxCr5Z7VRiJkqBqP7Hm3eg/2k7oDYQshiCsa5jMzQ=";

/// Verify a signed persona manifest with the bundled public key.
///
/// Decodes [`RELEASE_PUBLIC_KEY_B64`] into 32 raw bytes and forwards
/// to [`aether_l6_persona::verify_signed_manifest`]. Returns
/// `Ok(())` on a verified signature, or maps decode/verify errors
/// into the L6 error type the rest of the install flow uses.
///
/// Most callers will receive the manifest bytes from a network
/// fetch; the bytes themselves stay opaque to this function so it
/// can be unit-tested without an HTTP roundtrip.
fn verify_persona_manifest_with_bundled_key(
    manifest_bytes: &[u8],
) -> Result<(), aether_l6_persona::ManifestVerifyError> {
    let pk = decode_bundled_release_public_key()?;
    aether_l6_persona::verify_signed_manifest(manifest_bytes, &pk)
}

/// Decode the bundled [`RELEASE_PUBLIC_KEY_B64`] const into 32 raw
/// bytes. Returns the L6 verifier's `PublicKeyInvalid` variant on
/// malformed input — only reachable if the const is hand-edited to
/// non-base64 or the build-time include corrupts.
///
/// Exposed so production callers (the install orchestrator) can
/// decode once and pass `&pk` to the parameterized install/resolve
/// helpers below; tests bypass this entirely and pass a fixture pk.
pub(crate) fn decode_bundled_release_public_key(
) -> Result<Vec<u8>, aether_l6_persona::ManifestVerifyError> {
    use base64::engine::general_purpose::STANDARD as B64;
    use base64::Engine as _;
    B64.decode(RELEASE_PUBLIC_KEY_B64)
        .map_err(|_| aether_l6_persona::ManifestVerifyError::PublicKeyInvalid)
}

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
            // data dir (e.g. %APPDATA%/dev.aether.desktop/ on Windows — the
            // bundle identifier from tauri.conf.json, codename preserved).
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
            commands::install_persona,
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
            // T1.3 — L5-gated browser automation surface. Backed by
            // the `aether-l5-browser` PlaywrightExecutor stub today;
            // every method propagates BackendDisabled until the real
            // Node-subprocess driver lands.
            browser_commands::browser_open,
            browser_commands::browser_navigate,
            browser_commands::browser_read_page,
            browser_commands::browser_extract,
            browser_commands::browser_fill_form,
            browser_commands::browser_submit,
            browser_commands::browser_close,
            // T1.3 — L5-gated file-workflow surface. Backed by the
            // `aether-l5-files` StdFsExecutor stub today; every method
            // propagates BackendDisabled until the real `std::fs` /
            // `tokio::fs` driver lands.
            files_commands::files_read,
            files_commands::files_create,
            files_commands::files_edit,
            files_commands::files_rename,
            files_commands::files_delete,
            files_commands::files_grep,
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
/// `resources/personas/*.yaml` (see `tauri.conf.json` `bundle.resources`).
/// Without
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
    let report = seed_persona_pack_dir_from(&resource_dir, dest)?;
    if matches!(report, PersonaSeedOutcome::NoSource) {
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
    if let PersonaSeedOutcome::Copied { copied, skipped } = report {
        tracing::info!(
            "persona pack seed: copied {copied} new file(s), skipped {skipped} existing in {}",
            dest.display()
        );
    }
    Ok(())
}

/// Outcome of [`seed_persona_pack_dir_from`]. Surfaced as a typed
/// return so tests can pattern-match without parsing log output.
#[cfg(feature = "sqlite-backend")]
#[derive(Debug, Clone, PartialEq, Eq)]
enum PersonaSeedOutcome {
    /// Resource dir is missing or not a directory; nothing to do.
    NoSource,
    /// Walked the source dir; copied N new files, skipped M existing.
    Copied { copied: u32, skipped: u32 },
}

/// Pure, side-effect-only-on-the-filesystem core of the persona-pack
/// seed. Extracted from [`seed_persona_pack_dir`] so tests can drive
/// it with tempdirs instead of a real `tauri::AppHandle`.
///
/// Contract:
/// - If `source` is not a directory → `Ok(NoSource)`. No `dest`
///   touch.
/// - Otherwise: `dest` is created (and parents) if missing. Each
///   `*.yaml` / `*.yml` file in `source` is copied into `dest` only
///   if the destination filename is missing — existing files are
///   never overwritten.
/// - Non-yaml entries (sub-directories, other extensions, dotfiles
///   without yaml extension) are silently skipped.
/// - Returns the (copied, skipped) counts so the caller can log /
///   tests can assert.
#[cfg(feature = "sqlite-backend")]
fn seed_persona_pack_dir_from(
    source: &std::path::Path,
    dest: &std::path::Path,
) -> Result<PersonaSeedOutcome, Box<dyn std::error::Error>> {
    if !source.is_dir() {
        return Ok(PersonaSeedOutcome::NoSource);
    }
    std::fs::create_dir_all(dest)?;
    let mut copied = 0u32;
    let mut skipped = 0u32;
    for entry in std::fs::read_dir(source)? {
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
    Ok(PersonaSeedOutcome::Copied { copied, skipped })
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
    //! One v0-compatible YAML per cast member is emitted into
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

/// Errors surfaced by [`install_persona_from_local_files`].
///
/// Each variant maps cleanly to a user-facing reason string the
/// wizard surfaces in the install-failed state. The orchestrator
/// treats every error as terminal — no partial install survives a
/// failed run thanks to L6's `.partial → final` rename.
#[derive(Debug, thiserror::Error)]
pub(crate) enum PersonaInstallError {
    #[error("personas dir is not configured (no app_data_dir and no AETHER_PERSONAS_DIR env)")]
    NoPersonasDir,
    #[error("network fetch from {url:?} failed: {message}")]
    Fetch { url: String, message: String },
    #[error("read failed at {path:?}: {source}")]
    Io {
        path: std::path::PathBuf,
        #[source]
        source: std::io::Error,
    },
    #[error("manifest is not valid JSON: {source}")]
    ManifestJson {
        #[source]
        source: serde_json::Error,
    },
    #[error("manifest signature did not verify: {source}")]
    ManifestSignature {
        #[source]
        source: aether_l6_persona::ManifestVerifyError,
    },
    #[error("manifest does not declare a persona named {slug:?}")]
    SlugNotInManifest { slug: String },
    #[error("manifest entry for {slug:?} is missing required field {field:?}")]
    SlugEntryMalformed { slug: String, field: String },
    #[error("pack download did not match the manifest's declared SHA-256: {source}")]
    Sha256 {
        #[source]
        source: aether_l6_persona::InstallError,
    },
    #[error("extraction failed: {source}")]
    Extract {
        #[source]
        source: aether_l6_persona::InstallError,
    },
}

/// Orchestrate a Tier-2 persona install from on-disk inputs.
///
/// The HTTP fetching layer wraps this function with ureq (or
/// equivalent). Decoupling the orchestration from the network keeps
/// the security loop unit-testable: tests drive every branch with
/// fixture files. The HTTP wrapper only adds two thin layers
/// (download manifest, download zip) on top.
///
/// Steps, in order — any failure aborts:
///   1. Read manifest bytes from `manifest_path`.
///   2. Verify Ed25519 signature against the bundled public key.
///   3. Locate the persona entry for `slug`; pull `sha256`.
///   4. Verify `zip_path` SHA-256 matches the manifest claim.
///   5. Extract zip into `dest_dir/<slug>/` via the L6 atomic
///      `.partial → rename` install primitive.
///
/// On success returns the final extracted directory path. The
/// caller is responsible for catalog refresh — the live catalog in
/// `AppState` is hard-coded today; ADR-0012 §Switch flow expects an
/// "engine pause / install / resume" wrapper which lands when the
/// catalog gains interior mutability.
pub(crate) fn install_persona_from_local_files(
    manifest_path: &std::path::Path,
    zip_path: &std::path::Path,
    slug: &str,
    dest_dir: &std::path::Path,
    pk: &[u8],
) -> Result<std::path::PathBuf, PersonaInstallError> {
    let manifest_bytes = std::fs::read(manifest_path).map_err(|e| PersonaInstallError::Io {
        path: manifest_path.to_path_buf(),
        source: e,
    })?;
    aether_l6_persona::verify_signed_manifest(&manifest_bytes, pk)
        .map_err(|source| PersonaInstallError::ManifestSignature { source })?;
    let manifest: serde_json::Value = serde_json::from_slice(&manifest_bytes)
        .map_err(|source| PersonaInstallError::ManifestJson { source })?;
    let entry = manifest
        .get("personas")
        .and_then(|v| v.as_array())
        .and_then(|arr| {
            arr.iter()
                .find(|e| e.get("slug").and_then(|v| v.as_str()) == Some(slug))
        })
        .ok_or_else(|| PersonaInstallError::SlugNotInManifest {
            slug: slug.to_string(),
        })?;
    let expected_sha = entry
        .get("sha256")
        .and_then(|v| v.as_str())
        .ok_or_else(|| PersonaInstallError::SlugEntryMalformed {
            slug: slug.to_string(),
            field: "sha256".to_string(),
        })?;
    aether_l6_persona::verify_zip_sha256(zip_path, expected_sha)
        .map_err(|source| PersonaInstallError::Sha256 { source })?;
    aether_l6_persona::extract_pack_zip(zip_path, dest_dir, slug)
        .map_err(|source| PersonaInstallError::Extract { source })
}

/// Maximum bytes we'll accept for either a manifest or a pack zip.
/// Manifests are JSON describing a handful of personas, packs are
/// modest yaml + voice clips + a thumbnail. 32 MiB is a generous
/// ceiling that still rejects "the network handed us a tarball of
/// the entire site" denial-of-service input.
const PERSONA_FETCH_BYTE_LIMIT: u64 = 32 * 1024 * 1024;

/// Stream `url` into `dest`. Refuses inputs larger than
/// [`PERSONA_FETCH_BYTE_LIMIT`] so a hostile server cannot exhaust
/// disk by streaming forever. Truncates+overwrites `dest` on success.
///
/// Kept blocking — Tauri commands schedule this on a blocking task
/// pool so the IPC thread stays responsive. ureq is already a
/// dependency for the Ollama readiness probe (see Cargo.toml), so
/// pulling it in here adds no new transitive deps.
pub(crate) fn fetch_url_to_file(
    url: &str,
    dest: &std::path::Path,
) -> Result<(), PersonaInstallError> {
    let response = ureq::get(url)
        .call()
        .map_err(|e| PersonaInstallError::Fetch {
            url: url.to_string(),
            message: e.to_string(),
        })?;
    let mut reader = response.into_reader();
    let mut limited = std::io::Read::take(&mut reader, PERSONA_FETCH_BYTE_LIMIT + 1);
    let mut file = std::fs::File::create(dest).map_err(|e| PersonaInstallError::Io {
        path: dest.to_path_buf(),
        source: e,
    })?;
    let copied = std::io::copy(&mut limited, &mut file).map_err(|e| PersonaInstallError::Io {
        path: dest.to_path_buf(),
        source: e,
    })?;
    if copied > PERSONA_FETCH_BYTE_LIMIT {
        // Drop the over-sized partial; never leave the caller with a
        // file the orchestrator might trust.
        let _ = std::fs::remove_file(dest);
        return Err(PersonaInstallError::Fetch {
            url: url.to_string(),
            message: format!("response exceeded {} byte limit", PERSONA_FETCH_BYTE_LIMIT),
        });
    }
    Ok(())
}

/// Look up the asset URL for `slug` inside a signed manifest.
///
/// Verifies the Ed25519 signature against the bundled release public
/// key BEFORE trusting the manifest's contents — so the URL we
/// download from has been authenticated by Don's signing key. The
/// orchestrator that follows re-verifies signature and SHA-256 on the
/// downloaded zip; this helper exists only to know *where* to
/// download.
pub(crate) fn resolve_pack_asset_for_slug(
    manifest_bytes: &[u8],
    slug: &str,
    pk: &[u8],
) -> Result<String, PersonaInstallError> {
    aether_l6_persona::verify_signed_manifest(manifest_bytes, pk)
        .map_err(|source| PersonaInstallError::ManifestSignature { source })?;
    let manifest: serde_json::Value = serde_json::from_slice(manifest_bytes)
        .map_err(|source| PersonaInstallError::ManifestJson { source })?;
    let entry = manifest
        .get("personas")
        .and_then(|v| v.as_array())
        .and_then(|arr| {
            arr.iter()
                .find(|e| e.get("slug").and_then(|v| v.as_str()) == Some(slug))
        })
        .ok_or_else(|| PersonaInstallError::SlugNotInManifest {
            slug: slug.to_string(),
        })?;
    let asset_url = entry
        .get("asset_url")
        .and_then(|v| v.as_str())
        .ok_or_else(|| PersonaInstallError::SlugEntryMalformed {
            slug: slug.to_string(),
            field: "asset_url".to_string(),
        })?
        .to_string();
    Ok(asset_url)
}

/// Full Tier-2 install: download manifest, download zip, verify+extract.
///
/// Wraps [`install_persona_from_local_files`] with the two HTTP
/// fetches it needs. Lands the final pack at
/// `dest_dir/<slug>/`. Returns the final extracted dir on success.
///
/// Caller is expected to invoke
/// [`crate::state::AppState::refresh_catalog`] after a successful
/// install so the live shell sees the new persona.
pub(crate) fn install_persona_via_http(
    manifest_url: &str,
    slug: &str,
    dest_dir: &std::path::Path,
    pk: &[u8],
) -> Result<std::path::PathBuf, PersonaInstallError> {
    // Stage manifest + zip in a tempdir so a partial download doesn't
    // pollute the personas dir; tempdir self-deletes on drop.
    let staging = tempfile::tempdir().map_err(|e| PersonaInstallError::Io {
        path: dest_dir.to_path_buf(),
        source: e,
    })?;
    let manifest_path = staging.path().join("manifest.json");
    fetch_url_to_file(manifest_url, &manifest_path)?;
    let manifest_bytes =
        std::fs::read(&manifest_path).map_err(|source| PersonaInstallError::Io {
            path: manifest_path.clone(),
            source,
        })?;
    let asset_url = resolve_pack_asset_for_slug(&manifest_bytes, slug, pk)?;
    let zip_path = staging.path().join("pack.zip");
    fetch_url_to_file(&asset_url, &zip_path)?;
    install_persona_from_local_files(&manifest_path, &zip_path, slug, dest_dir, pk)
}

#[cfg(test)]
mod http_install_tests {
    //! Integration tests for the Tier-2 HTTP install path. Drives a
    //! real local HTTP server (a tiny `std::net::TcpListener` thread)
    //! so the full download → verify → extract loop is exercised
    //! without mocking ureq.
    use super::*;
    use std::io::{Read as _, Write as _};
    use std::net::TcpListener;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::Arc;

    /// Read the L6 cross-language fixture public key (32 raw bytes).
    /// Tests pass this to the parameterized install/resolve helpers
    /// instead of the bundled production key — the production key's
    /// secret lives offline, so tests cannot sign against it.
    fn fixture_public_key() -> Vec<u8> {
        use std::path::PathBuf;
        let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../packages/l6-persona/tests/fixtures/release_public_key.bin");
        std::fs::read(&path).unwrap_or_else(|e| panic!("read fixture pk {}: {e}", path.display()))
    }

    /// Build a deterministic in-memory zip with a single
    /// `alice/persona.yaml` entry — same shape `extract_pack_zip`
    /// expects (top-level slug-named directory).
    fn build_alice_zip_bytes() -> Vec<u8> {
        use std::io::{Cursor, Write as _};
        use zip::write::SimpleFileOptions;
        let mut cursor = Cursor::new(Vec::<u8>::new());
        {
            let mut w = zip::ZipWriter::new(&mut cursor);
            let opts =
                SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
            w.start_file("alice/persona.yaml", opts).unwrap();
            w.write_all(b"id: alice\nversion: 1\nname: Alice\ndescription: x\n")
                .unwrap();
            w.finish().unwrap();
        }
        cursor.into_inner()
    }

    /// Build a manifest-and-zip pair for slug `alice`, signed by the
    /// fixture key (seed `[7u8; 32]`). After T1.5's real-key swap the
    /// bundled `RELEASE_PUBLIC_KEY_B64` is no longer this fixture pk;
    /// tests pass [`fixture_public_key`] explicitly to the
    /// parameterized install/resolve helpers so the fixture-signed
    /// manifests still verify in test mode. Embeds `asset_url` so the
    /// runtime install path can fetch the zip back from a test server.
    fn fixture_signed_manifest_with_url(asset_url: &str) -> (Vec<u8>, Vec<u8>, String) {
        use ed25519_dalek::Signer as _;
        use ed25519_dalek::SigningKey;
        use sha2::{Digest as _, Sha256};

        let zip = build_alice_zip_bytes();
        let sha = format!("{:x}", Sha256::digest(&zip));

        // Same seed used in cross_language_verify.rs — pairs with
        // `fixture_public_key()` above so test-time
        // verification round-trips through the L6 verifier.
        let signing = SigningKey::from_bytes(&[7u8; 32]);

        let manifest_personas = serde_json::json!([{
            "slug": "alice",
            "version": "1.0.0",
            "asset_url": asset_url,
            "sha256": sha,
        }]);
        // The verifier hashes the personas array's compact-canonical
        // serialization (BTreeMap keys, no whitespace) — same shape
        // sign_manifest.py produces.
        let canonical = serde_json::to_vec(&manifest_personas).unwrap();
        let signature = signing.sign(&canonical);
        use base64::Engine as _;
        let sig_b64 = base64::engine::general_purpose::STANDARD.encode(signature.to_bytes());

        let wrapped = serde_json::json!({
            "schema_version": 1,
            "personas": manifest_personas,
            "signature": format!("ed25519:{sig_b64}"),
        });
        let manifest_bytes = serde_json::to_vec(&wrapped).unwrap();
        (manifest_bytes, zip, sha)
    }

    /// Bind a random localhost port without yet serving anything.
    /// Lets the caller learn the URL before signing a manifest that
    /// points at it.
    fn bind_random_port() -> (TcpListener, String) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let addr = listener.local_addr().unwrap();
        let url = format!("http://{}", addr);
        (listener, url)
    }

    /// Drive a previously-bound listener as a one-shot HTTP server
    /// that serves `manifest_bytes` at `/manifest.json` and
    /// `zip_bytes` at `/pack.zip`. Returns a stop flag — set to true
    /// to terminate the server thread.
    fn serve_listener(
        listener: TcpListener,
        manifest_bytes: Vec<u8>,
        zip_bytes: Vec<u8>,
    ) -> Arc<AtomicBool> {
        let stop = Arc::new(AtomicBool::new(false));
        let stop_clone = stop.clone();
        listener.set_nonblocking(true).unwrap();
        std::thread::spawn(move || {
            while !stop_clone.load(Ordering::Relaxed) {
                match listener.accept() {
                    Ok((mut stream, _)) => {
                        let mut buf = [0u8; 1024];
                        let _ = stream.read(&mut buf);
                        let req = String::from_utf8_lossy(&buf);
                        let body: &[u8] = if req.contains("/manifest.json") {
                            &manifest_bytes
                        } else if req.contains("/pack.zip") {
                            &zip_bytes
                        } else {
                            b""
                        };
                        let header = format!(
                            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                            body.len()
                        );
                        let _ = stream.write_all(header.as_bytes());
                        let _ = stream.write_all(body);
                    }
                    Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                        std::thread::sleep(std::time::Duration::from_millis(10));
                    }
                    Err(_) => break,
                }
            }
        });
        stop
    }

    #[test]
    fn install_persona_via_http_end_to_end() {
        let dest = tempfile::tempdir().unwrap();
        // Bind first to learn the port, then sign the manifest with
        // an asset_url that points at this same listener.
        let (listener, base) = bind_random_port();
        let asset_url = format!("{}/pack.zip", base);
        let (manifest_bytes, zip_bytes, _) = fixture_signed_manifest_with_url(&asset_url);
        let stop = serve_listener(listener, manifest_bytes, zip_bytes);

        let manifest_url = format!("{}/manifest.json", base);
        let pk = fixture_public_key();
        let result = install_persona_via_http(&manifest_url, "alice", dest.path(), &pk);
        stop.store(true, Ordering::Relaxed);
        let final_dir = result.expect("install_persona_via_http should succeed");
        assert!(final_dir.is_dir(), "final dir not created: {final_dir:?}");
        assert!(
            final_dir.ends_with("alice"),
            "wrong slug dir: {final_dir:?}"
        );
    }

    #[test]
    fn fetch_url_to_file_rejects_missing_host() {
        // A bind-then-immediately-close port. ureq returns Transport.
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        drop(listener); // close — no one is listening now.
        let dst = tempfile::NamedTempFile::new().unwrap();
        let url = format!("http://127.0.0.1:{}/whatever", port);
        let err = fetch_url_to_file(&url, dst.path()).expect_err("should fail to fetch");
        match err {
            PersonaInstallError::Fetch { .. } => {}
            other => panic!("expected Fetch err, got {other:?}"),
        }
    }
}

#[cfg(test)]
mod bundled_release_key_tests {
    //! Locks the contract between `RELEASE_PUBLIC_KEY_B64` (the bundled
    //! constant) and the L6 verifier.
    //!
    //! As of T1.5's real-key swap (2026-04-30) the bundled const is the
    //! production Ed25519 public key whose secret lives offline at
    //! `~/.aether/release-key/aether-release-ed25519.sk`. The
    //! cross-language fixture under
    //! `packages/l6-persona/tests/fixtures/` remains the seed-derived
    //! interop pair (Python signer ↔ Rust verifier). Bundled const and
    //! fixture pk are intentionally different — tests sign against the
    //! fixture pk via the parameterized install/resolve helpers; the
    //! bundled const is exercised here only for shape (length, base64
    //! decode, ≠ fixture).

    use super::{decode_bundled_release_public_key, RELEASE_PUBLIC_KEY_B64};
    use std::path::PathBuf;

    fn fixture_dir() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../packages/l6-persona/tests/fixtures")
    }

    fn fixture_signed_manifest() -> Vec<u8> {
        let path = fixture_dir().join("signed_manifest.json");
        std::fs::read(&path).unwrap_or_else(|e| panic!("read fixture {}: {e}", path.display()))
    }

    fn fixture_public_key() -> Vec<u8> {
        let path = fixture_dir().join("release_public_key.bin");
        std::fs::read(&path).unwrap_or_else(|e| panic!("read fixture pk {}: {e}", path.display()))
    }

    #[test]
    fn fixture_pk_verifies_cross_language_fixture() {
        let pk = fixture_public_key();
        aether_l6_persona::verify_signed_manifest(&fixture_signed_manifest(), &pk)
            .expect("fixture pk must verify the cross-language fixture");
    }

    #[test]
    fn bundled_key_const_decodes_to_32_bytes() {
        let raw = decode_bundled_release_public_key()
            .expect("bundled const must decode at runtime");
        assert_eq!(
            raw.len(),
            32,
            "Ed25519 public keys are 32 bytes; bundled const decoded to {}",
            raw.len()
        );
    }

    #[test]
    fn bundled_key_const_differs_from_fixture_pk() {
        // After the T1.5 real-key swap, the bundled const is Don's
        // production pk. The fixture pk is the seed-derived test pair.
        // These MUST differ — equality means a regression rolled the
        // const back to the fixture key.
        let fixture_b64_path = fixture_dir().join("release_public_key.b64");
        let fixture_b64 = std::fs::read_to_string(&fixture_b64_path)
            .unwrap_or_else(|e| panic!("read {}: {e}", fixture_b64_path.display()))
            .trim()
            .to_string();
        assert_ne!(
            RELEASE_PUBLIC_KEY_B64, fixture_b64,
            "bundled const equals fixture pk — real-key swap regressed",
        );
    }

    #[test]
    fn fixture_pk_rejects_tampered_personas_array() {
        // The cross-language fixture has alice's sha256 set to
        // "a"*64. Flip a byte and the verify should fail.
        let bytes = fixture_signed_manifest();
        let s = String::from_utf8(bytes).unwrap();
        let tampered = s.replace(&"a".repeat(64), &"f".repeat(64));
        let pk = fixture_public_key();
        let err = aether_l6_persona::verify_signed_manifest(&tampered.into_bytes(), &pk)
            .unwrap_err();
        assert!(
            matches!(err, aether_l6_persona::ManifestVerifyError::BadSignature),
            "expected BadSignature, got {err:?}"
        );
    }
}

#[cfg(test)]
mod persona_install_orchestration_tests {
    //! Drives `install_persona_from_local_files` through every
    //! branch using the cross-language fixture + a freshly-built
    //! zip whose SHA-256 we inject into a copy of the fixture. This
    //! locks the manifest-signature → sha-verify → atomic-extract
    //! pipeline at unit-test time so the HTTP wrapper that lands
    //! later only has to test fetching.

    use super::install_persona_from_local_files;
    use std::fs;
    use std::io::Write;
    use std::path::{Path, PathBuf};
    use tempfile::TempDir;

    fn fixture_dir() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../packages/l6-persona/tests/fixtures")
    }

    fn fixture_signed_manifest_path() -> PathBuf {
        fixture_dir().join("signed_manifest.json")
    }

    /// Read the L6 cross-language fixture pk. Tests pass this to
    /// `install_persona_from_local_files` directly — the bundled
    /// production const is unrelated to the seed-derived fixture pair
    /// after T1.5's real-key swap.
    fn fixture_public_key() -> Vec<u8> {
        let path = fixture_dir().join("release_public_key.bin");
        fs::read(&path).unwrap_or_else(|e| panic!("read fixture pk {}: {e}", path.display()))
    }

    /// Build a deterministic zip with a couple of files, return
    /// (zip_path, hex_sha256).
    fn build_zip_with_known_sha(dir: &Path, name: &str) -> (PathBuf, String) {
        use sha2::{Digest, Sha256};
        use zip::write::SimpleFileOptions;

        let zip_path = dir.join(name);
        let f = fs::File::create(&zip_path).unwrap();
        let mut w = zip::ZipWriter::new(f);
        let opts =
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        w.start_file("alice/persona.yaml", opts).unwrap();
        w.write_all(b"id: alice\nversion: 1\nname: Alice\ndescription: x\n")
            .unwrap();
        w.start_file("alice/avatar/anchor.png", opts).unwrap();
        w.write_all(b"\x89PNG\r\n\x1a\nfake").unwrap();
        w.finish().unwrap();

        let mut h = Sha256::new();
        h.update(fs::read(&zip_path).unwrap());
        let sha = format!("{:x}", h.finalize());
        (zip_path, sha)
    }

    /// Re-sign a copy of the fixture manifest with alice's sha
    /// updated to match a freshly-built zip. We can do this in the
    /// test because the fixture's deterministic seed is also baked
    /// into the L6 verifier's cross-language test, so we know the
    /// secret key.
    fn signed_manifest_with_sha(tmp: &TempDir, alice_sha: &str) -> PathBuf {
        use base64::engine::general_purpose::STANDARD as B64;
        use base64::Engine as _;
        use ed25519_dalek::{Signer, SigningKey};

        let raw = fs::read(fixture_signed_manifest_path()).unwrap();
        let mut manifest: serde_json::Value = serde_json::from_slice(&raw).unwrap();
        manifest["personas"][0]["sha256"] = serde_json::Value::String(alice_sha.to_string());

        // Re-sign with the same deterministic key the fixture used
        // (seed [7;32], also the cross-language Rust test seed).
        let sk = SigningKey::from_bytes(&[7u8; 32]);
        let body = serde_json::to_vec(manifest.get("personas").unwrap()).unwrap();
        let sig = sk.sign(&body);
        manifest["signature"] =
            serde_json::Value::String(format!("ed25519:{}", B64.encode(sig.to_bytes())));

        let path = tmp.path().join("manifest.json");
        fs::write(&path, serde_json::to_vec(&manifest).unwrap()).unwrap();
        path
    }

    #[test]
    fn happy_path_installs_alice() {
        let tmp = TempDir::new().unwrap();
        let (zip, sha) = build_zip_with_known_sha(tmp.path(), "alice.zip");
        let manifest = signed_manifest_with_sha(&tmp, &sha);
        let dest = tmp.path().join("install");

        let pk = fixture_public_key();
        let result = install_persona_from_local_files(&manifest, &zip, "alice", &dest, &pk)
            .expect("install");
        assert_eq!(result, dest.join("alice"));
        assert!(dest.join("alice/alice/persona.yaml").exists());
    }

    #[test]
    fn slug_not_in_manifest_errors_cleanly() {
        let tmp = TempDir::new().unwrap();
        let (zip, sha) = build_zip_with_known_sha(tmp.path(), "alice.zip");
        let manifest = signed_manifest_with_sha(&tmp, &sha);
        let dest = tmp.path().join("install");

        let pk = fixture_public_key();
        let err = install_persona_from_local_files(&manifest, &zip, "ghost", &dest, &pk)
            .unwrap_err();
        assert!(matches!(
            err,
            super::PersonaInstallError::SlugNotInManifest { .. }
        ));
    }

    #[test]
    fn manifest_with_bad_signature_aborts_before_extract() {
        let tmp = TempDir::new().unwrap();
        let (zip, sha) = build_zip_with_known_sha(tmp.path(), "alice.zip");
        let manifest = signed_manifest_with_sha(&tmp, &sha);

        // Corrupt the manifest signature post-sign.
        let mut m: serde_json::Value =
            serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();
        m["personas"][0]["display_name"] = serde_json::Value::String("Corrupted".to_string());
        fs::write(&manifest, serde_json::to_vec(&m).unwrap()).unwrap();

        let dest = tmp.path().join("install");
        let pk = fixture_public_key();
        let err = install_persona_from_local_files(&manifest, &zip, "alice", &dest, &pk)
            .unwrap_err();
        assert!(matches!(
            err,
            super::PersonaInstallError::ManifestSignature { .. }
        ));
        // No extract happened.
        assert!(!dest.join("alice").exists());
    }

    #[test]
    fn zip_with_wrong_sha_aborts_before_extract() {
        let tmp = TempDir::new().unwrap();
        let (zip, _real_sha) = build_zip_with_known_sha(tmp.path(), "alice.zip");
        // Tell the manifest to expect a different sha.
        let manifest = signed_manifest_with_sha(&tmp, &"f".repeat(64));
        let dest = tmp.path().join("install");

        let pk = fixture_public_key();
        let err = install_persona_from_local_files(&manifest, &zip, "alice", &dest, &pk)
            .unwrap_err();
        assert!(matches!(err, super::PersonaInstallError::Sha256 { .. }));
        assert!(!dest.join("alice").exists());
    }
}

#[cfg(all(test, feature = "sqlite-backend"))]
mod persona_seed_tests {
    //! Tests for the pure file-copy core of the persona-pack seed.
    //!
    //! `seed_persona_pack_dir_from` is the testable extract of the
    //! Tauri-bound `seed_persona_pack_dir`. We drive it with
    //! `tempfile::TempDir`s so the test never touches the user's real
    //! `<app_data>/personas/` and the assertions stay reproducible
    //! across machines.

    use super::{seed_persona_pack_dir_from, PersonaSeedOutcome};
    use std::fs;
    use tempfile::TempDir;

    fn write(dir: &std::path::Path, name: &str, body: &str) {
        fs::write(dir.join(name), body).expect("write fixture");
    }

    #[test]
    fn missing_source_returns_no_source_and_does_not_touch_dest() {
        let dest = TempDir::new().expect("dest tempdir");
        let nonexistent = dest.path().join("does_not_exist");
        let outcome = seed_persona_pack_dir_from(&nonexistent, dest.path())
            .expect("seed should not error on missing source");
        assert_eq!(outcome, PersonaSeedOutcome::NoSource);
        // Dest contents unchanged (still empty).
        let entries: Vec<_> = fs::read_dir(dest.path())
            .unwrap()
            .filter_map(|e| e.ok())
            .collect();
        assert!(
            entries.is_empty(),
            "no-source case should not create files in dest"
        );
    }

    #[test]
    fn empty_dest_gets_every_yaml_file_copied() {
        let src = TempDir::new().unwrap();
        let dest = TempDir::new().unwrap();
        write(src.path(), "alice.yaml", "id: alice\n");
        write(src.path(), "bob.yml", "id: bob\n");
        // Non-yaml — must be ignored.
        write(src.path(), "readme.md", "not a pack");

        let outcome = seed_persona_pack_dir_from(src.path(), dest.path()).expect("seed");
        assert_eq!(
            outcome,
            PersonaSeedOutcome::Copied {
                copied: 2,
                skipped: 0
            }
        );
        assert!(dest.path().join("alice.yaml").exists());
        assert!(dest.path().join("bob.yml").exists());
        assert!(!dest.path().join("readme.md").exists());
    }

    #[test]
    fn existing_dest_files_are_never_overwritten() {
        let src = TempDir::new().unwrap();
        let dest = TempDir::new().unwrap();
        write(src.path(), "alice.yaml", "id: alice_NEW\n");
        // Pre-existing user-edited copy at dest.
        write(dest.path(), "alice.yaml", "id: alice_USER\n");

        let outcome = seed_persona_pack_dir_from(src.path(), dest.path()).expect("seed");
        assert_eq!(
            outcome,
            PersonaSeedOutcome::Copied {
                copied: 0,
                skipped: 1
            }
        );
        // User edit survives — overwrite would have replaced this.
        let body = fs::read_to_string(dest.path().join("alice.yaml")).unwrap();
        assert!(
            body.contains("alice_USER"),
            "user edit was overwritten: {body:?}"
        );
    }

    #[test]
    fn missing_dest_dir_is_created() {
        let src = TempDir::new().unwrap();
        write(src.path(), "alice.yaml", "id: alice\n");
        let parent = TempDir::new().unwrap();
        let dest = parent.path().join("nested/personas");
        assert!(!dest.exists(), "precondition: dest must not yet exist");

        let outcome = seed_persona_pack_dir_from(src.path(), &dest).expect("seed");
        assert_eq!(
            outcome,
            PersonaSeedOutcome::Copied {
                copied: 1,
                skipped: 0
            }
        );
        assert!(dest.join("alice.yaml").exists());
    }

    #[test]
    fn second_run_skips_everything_already_present() {
        let src = TempDir::new().unwrap();
        let dest = TempDir::new().unwrap();
        write(src.path(), "alice.yaml", "id: alice\n");
        write(src.path(), "bob.yaml", "id: bob\n");

        let first = seed_persona_pack_dir_from(src.path(), dest.path()).expect("seed1");
        assert_eq!(
            first,
            PersonaSeedOutcome::Copied {
                copied: 2,
                skipped: 0
            }
        );

        let second = seed_persona_pack_dir_from(src.path(), dest.path()).expect("seed2");
        assert_eq!(
            second,
            PersonaSeedOutcome::Copied {
                copied: 0,
                skipped: 2
            }
        );
    }

    #[test]
    fn newly_added_resource_lands_on_existing_install() {
        // Simulates a future release adding a new pack: user's dest
        // already has alice from the prior install; release adds bob.
        let src = TempDir::new().unwrap();
        let dest = TempDir::new().unwrap();
        write(src.path(), "alice.yaml", "id: alice\n");
        write(src.path(), "bob.yaml", "id: bob\n");
        // Pre-existing install: only alice is on disk.
        write(dest.path(), "alice.yaml", "id: alice\n");

        let outcome = seed_persona_pack_dir_from(src.path(), dest.path()).expect("seed");
        assert_eq!(
            outcome,
            PersonaSeedOutcome::Copied {
                copied: 1,
                skipped: 1
            }
        );
        assert!(dest.path().join("bob.yaml").exists());
    }
}
