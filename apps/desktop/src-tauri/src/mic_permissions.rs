//! Microphone permission model for push-to-talk voice capture.
//!
//! This module owns a small, **local-only** representation of how much
//! Companion is allowed to listen. It is the single point of truth that
//! future voice-capture paths must consult before touching the mic.
//!
//! ## Design notes (mirrors [`crate::media_permissions`])
//!
//! - Single tri-state: `Allow` / `Ask` / `Deny`. `Deny` is the
//!   "Never" semantic — once written it stays stable across launches
//!   and capture sites short-circuit before touching the device. The
//!   OS-level mic prompt is still authoritative regardless of what we
//!   record here.
//! - Default = `Ask`. Boot must never silently grant mic capture the
//!   user has not seen a prompt for.
//! - Persistence is a single JSON file beside the media-permissions
//!   file (`<app_data>/mic_permissions.json`). Deliberately not in
//!   SQLite — it is shell policy state, not conversation memory, and
//!   the JSON file is trivial to inspect or hand-edit during incident
//!   response.
//! - There is **no** remote/analytics surface. Read and written by the
//!   local shell only.
//! - The file shape is **additive and default-safe**: unknown fields
//!   silently ignored on read; malformed JSON falls back to `defaults`
//!   with a WARN that names the path; freshly-rewritten files drop
//!   unknown fields (documented limitation — symmetrical with
//!   `vision_provider.json`).
//! - The `PermissionState` / `CaptureGate` enums are imported from
//!   [`crate::media_permissions`] because the three-state semantics
//!   are shared across every consent surface. The mic does not invent
//!   new states.
//!
//! ## Why not reuse `MediaPermissions`
//!
//! Camera and screen share a physical boundary (visual capture);
//! bundling them in a single record matches how a user thinks about
//! them. The microphone has its own distinct consent boundary — the
//! user who says "yes, look at my screen" has not said "yes, listen to
//! me." Keeping mic state in its own file preserves that separation
//! when the user reviews `<app_data>/` during an incident.

use std::fs;
use std::io::{self, ErrorKind};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::media_permissions::{CaptureGate, PermissionState};

/// Snapshot of the local mic-permission posture. Cheap to clone;
/// callers should treat it as a value, not a handle.
///
/// Serde layout is an object with a single `state` field so the JSON
/// file has room to grow additively (e.g. future `allow_devices`
/// allowlist) without breaking old builds:
///
/// ```json
/// { "state": "ask" }
/// ```
///
/// Unknown top-level fields are silently ignored on read — the struct
/// intentionally omits `#[serde(deny_unknown_fields)]`.
#[derive(Debug, Copy, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MicPermission {
    /// Current user-chosen permission level for the microphone.
    /// Default is `Ask` so boot never silently grants capture.
    #[serde(default)]
    pub state: PermissionState,
}

impl MicPermission {
    /// Default = `Ask`. Boot must never silently grant mic capture the
    /// user has not seen a prompt for.
    pub fn defaults() -> Self {
        Self {
            state: PermissionState::Ask,
        }
    }

    /// Pre-capture permission gate. Voice-capture sites call this
    /// before touching the microphone — it never starts capture
    /// itself.
    ///
    /// `Allow` -> proceed without an in-app prompt.
    /// `Ask`   -> start the in-app approval flow.
    /// `Deny`  -> short-circuit with a friendly explanation; do not
    ///            even attempt to acquire the device.
    pub fn evaluate(&self) -> CaptureGate {
        match self.state {
            PermissionState::Allow => CaptureGate::Proceed,
            PermissionState::Ask => CaptureGate::PromptUser,
            PermissionState::Deny => CaptureGate::Deny,
        }
    }
}

impl Default for MicPermission {
    fn default() -> Self {
        Self::defaults()
    }
}

/// Load the persisted mic permission from `path`, falling back to
/// [`MicPermission::defaults`] if the file is missing or malformed.
///
/// Intentionally lenient about read failures: a corrupt or unreadable
/// file MUST NOT take down the shell. Returning the default (`Ask`)
/// keeps the user in the safe state where the next capture attempt
/// re-prompts.
pub fn load_or_default(path: &Path) -> MicPermission {
    match fs::read_to_string(path) {
        Ok(s) => match serde_json::from_str::<MicPermission>(&s) {
            Ok(p) => p,
            Err(e) => {
                tracing::warn!(
                    "mic permission file {} is malformed ({e}); using defaults",
                    path.display()
                );
                MicPermission::defaults()
            }
        },
        Err(e) if e.kind() == ErrorKind::NotFound => MicPermission::defaults(),
        Err(e) => {
            tracing::warn!(
                "could not read mic permission file {}: {e}; using defaults",
                path.display()
            );
            MicPermission::defaults()
        }
    }
}

/// Atomically persist `perm` to `path`, creating parent directories
/// as needed.
///
/// "Atomic" here means write-to-temp-then-rename, so a crash in the
/// middle of a write cannot leave a half-written JSON file the next
/// boot will reject.
pub fn save(path: &Path, perm: &MicPermission) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("json.tmp");
    let body = serde_json::to_string_pretty(perm)
        .map_err(|e| io::Error::new(ErrorKind::InvalidData, e))?;
    fs::write(&tmp, body)?;
    fs::rename(&tmp, path)?;
    Ok(())
}

/// Resolve the canonical mic-permission file path beside the media
/// permissions file. Used by the shell when constructing the
/// `AppState`; tests may pass any directory.
pub fn permission_path_for(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join("mic_permissions.json")
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn defaults_are_ask() {
        let p = MicPermission::defaults();
        assert_eq!(p.state, PermissionState::Ask);
    }

    #[test]
    fn evaluate_returns_correct_gate_for_each_state() {
        let mut p = MicPermission::defaults();
        assert_eq!(p.evaluate(), CaptureGate::PromptUser);
        p.state = PermissionState::Allow;
        assert_eq!(p.evaluate(), CaptureGate::Proceed);
        p.state = PermissionState::Deny;
        assert_eq!(p.evaluate(), CaptureGate::Deny);
    }

    #[test]
    fn load_or_default_when_missing_returns_defaults() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("missing.json");
        let p = load_or_default(&path);
        assert_eq!(p, MicPermission::defaults());
    }

    #[test]
    fn save_then_load_roundtrips() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("nested").join("mic_permissions.json");
        let original = MicPermission {
            state: PermissionState::Allow,
        };
        save(&path, &original).expect("save");
        let loaded = load_or_default(&path);
        assert_eq!(loaded, original);
    }

    #[test]
    fn load_or_default_falls_back_on_malformed_json() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("mic_permissions.json");
        fs::write(&path, "not json at all").unwrap();
        let p = load_or_default(&path);
        assert_eq!(p, MicPermission::defaults());
    }

    #[test]
    fn unknown_fields_are_silently_ignored_on_read() {
        // Future builds may add fields; older shells must tolerate
        // them without bailing. This locks the additive-default-safe
        // contract at the boundary — same promise as
        // `vision_provider.json`.
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("mic_permissions.json");
        fs::write(
            &path,
            r#"{ "state": "allow", "future_allowlist": ["hw-id-123"] }"#,
        )
        .unwrap();
        let p = load_or_default(&path);
        assert_eq!(p.state, PermissionState::Allow);
    }

    #[test]
    fn unknown_fields_are_dropped_on_rewrite() {
        // Documented limitation: the struct has no `serde(flatten)`
        // extras bag, so unknown fields from a newer build do NOT
        // survive a rewrite by the current build. Symmetrical with
        // `VisionPersistedState`; locked here so future behavior
        // changes are conscious.
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("mic_permissions.json");
        fs::write(
            &path,
            r#"{ "state": "allow", "future_allowlist": ["hw-id-123"] }"#,
        )
        .unwrap();

        let loaded = load_or_default(&path);
        save(&path, &loaded).expect("rewrite");

        let rewritten = fs::read_to_string(&path).unwrap();
        assert!(rewritten.contains("\"state\""));
        assert!(
            !rewritten.contains("future_allowlist"),
            "unknown field survived a rewrite; contract broken: {rewritten}"
        );
    }

    #[test]
    fn missing_state_field_falls_back_to_default() {
        // `#[serde(default)]` on `state` lets an otherwise-empty
        // config load cleanly. This is the "default-safe on read"
        // half of the additive contract.
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("mic_permissions.json");
        fs::write(&path, "{}").unwrap();
        let p = load_or_default(&path);
        assert_eq!(p.state, PermissionState::Ask);
    }

    #[test]
    fn json_uses_lowercase_state_strings() {
        let p = MicPermission {
            state: PermissionState::Deny,
        };
        let s = serde_json::to_string(&p).unwrap();
        assert!(
            s.contains("\"deny\""),
            "expected lowercase state in JSON, got: {s}"
        );
    }

    #[test]
    fn permission_path_for_lives_beside_app_data() {
        let dir = Path::new("/tmp/aether-test");
        let p = permission_path_for(dir);
        assert_eq!(p, Path::new("/tmp/aether-test/mic_permissions.json"));
    }
}
