// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod adapter;
mod commands;
mod media_permissions;
mod memory_router;
mod provider;
mod state;

use state::AppState;
use tauri::Manager;

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
            app.manage(app_state);
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
            commands::analyze_frame,
            commands::vision_status,
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
                attach_vision_provider_if_configured(&mut state);
                return Ok(state);
            }
            Err(e) => {
                tracing::warn!(
                    "could not resolve app_data_dir: {e}; using in-memory session store"
                );
            }
        }
    }
    let mut state = AppState::new()?;
    attach_vision_provider_if_configured(&mut state);
    Ok(state)
}

/// Attach the Ollama vision adapter when the user has opted in via
/// `AETHER_OLLAMA_VISION_MODEL`. No-op when the env var is unset, the
/// config parses badly, or the daemon does not respond — the
/// `analyze_frame` command falls back cleanly in any of those cases.
///
/// Compiled out entirely when the `ollama-provider` feature is off so
/// the OSS default build pulls no network dependencies.
#[cfg(feature = "ollama-provider")]
fn attach_vision_provider_if_configured(state: &mut AppState) {
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
            let provider = OllamaVisionProvider::new(cfg);
            if let Err(e) = provider.healthcheck() {
                tracing::warn!(
                    "vision provider healthcheck failed: {e}; falling back to text-only frame analysis"
                );
                return;
            }
            let arc: Arc<dyn VisionProvider> = Arc::new(provider);
            tracing::info!("vision provider attached: {}", arc.label());
            state.attach_vision_provider(arc);
        }
        Err(e) => {
            tracing::warn!(
                "AETHER_OLLAMA_VISION_* config invalid: {e}; falling back to text-only frame analysis"
            );
        }
    }
}

#[cfg(not(feature = "ollama-provider"))]
fn attach_vision_provider_if_configured(_state: &mut AppState) {}
