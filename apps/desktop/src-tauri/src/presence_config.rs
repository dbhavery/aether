//! Presence V1 configuration surface (step 1).
//!
//! Owns `<app_data>/presence.json` — the small, additive, default-
//! safe config the Settings UI writes and the future presence
//! controller reads. Same shape contract every other Companion config
//! file follows (see `mic_permissions.rs`, `vision_registry.rs`).
//!
//! ## Design notes (per `docs/PRESENCE-V1-ARCHITECTURE.md` §3)
//!
//! - Fields:
//!   - `enabled`                  — master toggle; default `true`.
//!   - `idle_after_s`             — OS-idle threshold Active → Idle.
//!                                  Default 120.
//!   - `away_after_s`             — OS-idle threshold Idle → Away.
//!                                  Default 600.
//!   - `history_in_trust_drawer`  — whether the Trust drawer history
//!                                  tab surfaces presence events.
//!                                  Default `true`.
//! - **Additive** — new fields may be added by future builds.
//! - **Default-safe on read** — every field has `#[serde(default)]`.
//! - **Unknown fields silently ignored on read** — no
//!   `#[serde(deny_unknown_fields)]`.
//! - **Unknown fields dropped on rewrite** — documented limitation;
//!   locked by test. Symmetrical with `vision_provider.json`.
//! - **Malformed JSON → default + WARN naming the path.**
//! - **Atomic writes** — write-to-temp + rename.
//!
//! No L5 capability gate, no L5 audit rows — presence is
//! observational per design §4. The two Settings toggles
//! (`enabled`, `history_in_trust_drawer`) are the user-facing
//! consent surface.

use std::fs;
use std::io::{self, ErrorKind};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

/// Default idle threshold for `Active → Idle` (seconds). Mirrors
/// the design doc §2.
pub const DEFAULT_IDLE_AFTER_S: u32 = 120;
/// Default away threshold for `Idle → Away` (seconds). Mirrors the
/// design doc §2.
pub const DEFAULT_AWAY_AFTER_S: u32 = 600;

fn default_enabled() -> bool {
    true
}

fn default_idle_after_s() -> u32 {
    DEFAULT_IDLE_AFTER_S
}

fn default_away_after_s() -> u32 {
    DEFAULT_AWAY_AFTER_S
}

fn default_history_in_trust_drawer() -> bool {
    true
}

/// Snapshot of the local presence-config state. Cheap to clone;
/// callers should treat it as a value, not a handle.
///
/// Serde layout is an object matching the doc §3 shape:
///
/// ```json
/// {
///   "enabled": true,
///   "idle_after_s": 120,
///   "away_after_s": 600,
///   "history_in_trust_drawer": true
/// }
/// ```
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct PresenceConfig {
    #[serde(default = "default_enabled")]
    pub enabled: bool,
    #[serde(default = "default_idle_after_s")]
    pub idle_after_s: u32,
    #[serde(default = "default_away_after_s")]
    pub away_after_s: u32,
    #[serde(default = "default_history_in_trust_drawer")]
    pub history_in_trust_drawer: bool,
}

impl PresenceConfig {
    /// Canonical defaults — enabled, 120/600-second thresholds,
    /// Trust drawer history visible.
    pub fn defaults() -> Self {
        Self {
            enabled: default_enabled(),
            idle_after_s: default_idle_after_s(),
            away_after_s: default_away_after_s(),
            history_in_trust_drawer: default_history_in_trust_drawer(),
        }
    }
}

impl Default for PresenceConfig {
    fn default() -> Self {
        Self::defaults()
    }
}

/// Load the persisted presence config from `path`, falling back to
/// [`PresenceConfig::defaults`] if the file is missing or malformed.
/// Intentionally lenient — a corrupt or unreadable file MUST NOT
/// take down the shell.
pub fn load_or_default(path: &Path) -> PresenceConfig {
    match fs::read_to_string(path) {
        Ok(s) => match serde_json::from_str::<PresenceConfig>(&s) {
            Ok(cfg) => cfg,
            Err(e) => {
                tracing::warn!(
                    "presence config file {} is malformed ({e}); using defaults",
                    path.display()
                );
                PresenceConfig::defaults()
            }
        },
        Err(e) if e.kind() == ErrorKind::NotFound => PresenceConfig::defaults(),
        Err(e) => {
            tracing::warn!(
                "could not read presence config file {}: {e}; using defaults",
                path.display()
            );
            PresenceConfig::defaults()
        }
    }
}

/// Atomically persist `cfg` to `path`, creating parent directories
/// as needed. Write-to-temp + rename so a crash in the middle of a
/// write cannot leave a half-written file the next boot will
/// reject.
pub fn save(path: &Path, cfg: &PresenceConfig) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("json.tmp");
    let body =
        serde_json::to_string_pretty(cfg).map_err(|e| io::Error::new(ErrorKind::InvalidData, e))?;
    fs::write(&tmp, body)?;
    fs::rename(&tmp, path)?;
    Ok(())
}

/// Resolve the canonical presence-config path beside the other
/// shell-state files. Used by the shell when constructing the
/// `AppState`; tests pass any directory.
pub fn config_path_for(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join("presence.json")
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn defaults_match_design_doc() {
        let c = PresenceConfig::defaults();
        assert!(c.enabled);
        assert_eq!(c.idle_after_s, 120);
        assert_eq!(c.away_after_s, 600);
        assert!(c.history_in_trust_drawer);
    }

    #[test]
    fn load_or_default_when_missing_returns_defaults() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("missing.json");
        assert_eq!(load_or_default(&path), PresenceConfig::defaults());
    }

    #[test]
    fn save_then_load_roundtrips() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("nested").join("presence.json");
        let original = PresenceConfig {
            enabled: false,
            idle_after_s: 90,
            away_after_s: 420,
            history_in_trust_drawer: false,
        };
        save(&path, &original).expect("save");
        let loaded = load_or_default(&path);
        assert_eq!(loaded, original);
    }

    #[test]
    fn load_or_default_falls_back_on_malformed_json() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("presence.json");
        fs::write(&path, "not json at all").unwrap();
        assert_eq!(load_or_default(&path), PresenceConfig::defaults());
    }

    #[test]
    fn unknown_fields_are_silently_ignored_on_read() {
        // Additive-safe — future builds may add fields; older shells
        // must tolerate them without bailing. Locks the additive
        // contract at the boundary.
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("presence.json");
        fs::write(
            &path,
            r#"{
                "enabled": false,
                "idle_after_s": 60,
                "away_after_s": 500,
                "history_in_trust_drawer": true,
                "future_knob": "some-value"
            }"#,
        )
        .unwrap();
        let c = load_or_default(&path);
        assert!(!c.enabled);
        assert_eq!(c.idle_after_s, 60);
    }

    #[test]
    fn unknown_fields_are_dropped_on_rewrite() {
        // Documented limitation: the struct has no `serde(flatten)`
        // extras bag, so unknown fields from a newer build do NOT
        // survive a rewrite by the current build. Symmetrical with
        // VisionPersistedState / MicPermission.
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("presence.json");
        fs::write(&path, r#"{ "enabled": true, "future_knob": ["x"] }"#).unwrap();

        let loaded = load_or_default(&path);
        save(&path, &loaded).expect("rewrite");
        let rewritten = fs::read_to_string(&path).unwrap();
        assert!(rewritten.contains("\"enabled\""));
        assert!(
            !rewritten.contains("future_knob"),
            "unknown field survived a rewrite: {rewritten}"
        );
    }

    #[test]
    fn missing_fields_fall_back_to_defaults() {
        // `#[serde(default)]` on every field lets an otherwise-empty
        // config load cleanly. The "default-safe on read" half of
        // the additive contract.
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("presence.json");
        fs::write(&path, "{}").unwrap();
        assert_eq!(load_or_default(&path), PresenceConfig::defaults());
    }

    #[test]
    fn partial_config_preserves_provided_fields_only() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("presence.json");
        fs::write(&path, r#"{ "enabled": false }"#).unwrap();
        let c = load_or_default(&path);
        assert!(!c.enabled);
        assert_eq!(c.idle_after_s, 120);
        assert_eq!(c.away_after_s, 600);
        assert!(c.history_in_trust_drawer);
    }

    #[test]
    fn config_path_for_lives_beside_app_data() {
        let dir = Path::new("/tmp/aether-test");
        let p = config_path_for(dir);
        assert_eq!(p, Path::new("/tmp/aether-test/presence.json"));
    }
}
