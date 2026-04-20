// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod adapter;
mod commands;
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
                let db_path = dir.join("aether.db");
                tracing::info!(
                    "initialising AppState with durable session memory at {}",
                    db_path.display()
                );
                return AppState::new_with_db_path(db_path).map_err(Into::into);
            }
            Err(e) => {
                tracing::warn!(
                    "could not resolve app_data_dir: {e}; using in-memory session store"
                );
            }
        }
    }
    AppState::new().map_err(Into::into)
}
