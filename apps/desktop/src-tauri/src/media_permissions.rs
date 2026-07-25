//! Media permission model for camera and screen capture.
//!
//! This module owns a small, **local-only** representation of how much
//! Companion is allowed to look at the user's camera and screen. It is the
//! single point of truth that future capture/inference paths must
//! consult before touching either device.
//!
//! ## Design notes
//!
//! - Tri-state per device: `Allow` / `Ask` / `Deny`. `Deny` is the
//!   "Never" semantic from the product spec — once written it stays
//!   stable across launches and capture sites short-circuit before
//!   touching the device. The OS-level prompt is still authoritative
//!   regardless of what we record here.
//! - Default = `Ask` for both. Boot must never silently grant a
//!   capture capability the user has not seen a prompt for.
//! - Persistence is a single JSON file beside the durable session
//!   memory (`<app_data>/media_permissions.json`). We deliberately do
//!   **not** put this in the SQLite session store — it is shell
//!   policy state, not conversation memory, and the JSON file is
//!   trivial to inspect or hand-edit during incident response.
//! - There is **no** remote/analytics surface. The model is read and
//!   written by the local shell only.

use std::fs;
use std::io::{self, ErrorKind};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

/// Tri-state per-device permission.
///
/// Wire format is intentionally lowercase strings (`"allow" | "ask" |
/// "deny"`) so the JSON file and the Tauri command surface read the
/// same way the user thinks about them. The display name shown in the
/// Settings UI is computed in the frontend; this enum carries no
/// presentation concern.
#[derive(Debug, Copy, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PermissionState {
    /// Capture may proceed without an in-app approval prompt. The OS
    /// permission prompt is still authoritative.
    Allow,
    /// Capture must trigger an in-app approval prompt for each session
    /// (ticket flow, mirrors the L7 approval pattern). This is the
    /// default for both devices on first boot.
    Ask,
    /// Capture is hard-disabled in this build. Capture sites must
    /// short-circuit and surface a friendly "permission disabled"
    /// message instead of even attempting to acquire the device.
    Deny,
}

impl PermissionState {
    /// Wire-format label — matches the lowercase serde rename.
    #[allow(dead_code)] // Public API; consumed by future capture sites and tests.
    pub fn wire(self) -> &'static str {
        match self {
            PermissionState::Allow => "allow",
            PermissionState::Ask => "ask",
            PermissionState::Deny => "deny",
        }
    }

    /// Parse the wire-format label. Returns `None` for unknown input
    /// so the caller can surface "unknown state" instead of silently
    /// defaulting to one direction or the other.
    pub fn from_wire(s: &str) -> Option<Self> {
        match s {
            "allow" => Some(PermissionState::Allow),
            "ask" => Some(PermissionState::Ask),
            "deny" => Some(PermissionState::Deny),
            _ => None,
        }
    }
}

impl Default for PermissionState {
    fn default() -> Self {
        PermissionState::Ask
    }
}

/// Which media device a permission targets.
///
/// Camera and screen are the two surfaces the foundation slice cares
/// about. Microphone capture lives behind the L1/voice track and has
/// its own consent path; we deliberately do not bundle it here so the
/// two consents stay auditable separately.
#[derive(Debug, Copy, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MediaKind {
    Camera,
    Screen,
}

impl MediaKind {
    pub fn from_wire(s: &str) -> Option<Self> {
        match s {
            "camera" => Some(MediaKind::Camera),
            "screen" => Some(MediaKind::Screen),
            _ => None,
        }
    }

    /// Lower-case wire label, matching the serde rename. Used by
    /// command handlers building user-facing copy.
    pub fn wire_label(self) -> &'static str {
        match self {
            MediaKind::Camera => "camera",
            MediaKind::Screen => "screen",
        }
    }
}

/// Snapshot of the local media-permission posture. Cheap to clone;
/// callers should treat it as a value, not a handle.
#[derive(Debug, Copy, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MediaPermissions {
    pub camera: PermissionState,
    pub screen: PermissionState,
}

impl MediaPermissions {
    /// Both devices default to `Ask`. The shell must never auto-grant
    /// capture the user hasn't seen a prompt for.
    pub fn defaults() -> Self {
        Self {
            camera: PermissionState::Ask,
            screen: PermissionState::Ask,
        }
    }

    /// Read the permission for a single device.
    pub fn get(&self, kind: MediaKind) -> PermissionState {
        match kind {
            MediaKind::Camera => self.camera,
            MediaKind::Screen => self.screen,
        }
    }

    /// Replace the permission for a single device. Returns `self` so
    /// the call site can chain or assign in one expression.
    pub fn set(&mut self, kind: MediaKind, state: PermissionState) -> &mut Self {
        match kind {
            MediaKind::Camera => self.camera = state,
            MediaKind::Screen => self.screen = state,
        }
        self
    }

    /// Pre-capture permission gate. Capture sites call this before
    /// touching the device — it never starts capture itself.
    ///
    /// `Allow` -> proceed without an in-app prompt.
    /// `Ask`   -> start the in-app approval flow.
    /// `Deny`  -> short-circuit with a friendly explanation; do not
    ///            even attempt to acquire the device.
    pub fn evaluate(&self, kind: MediaKind) -> CaptureGate {
        match self.get(kind) {
            PermissionState::Allow => CaptureGate::Proceed,
            PermissionState::Ask => CaptureGate::PromptUser,
            PermissionState::Deny => CaptureGate::Deny,
        }
    }
}

impl Default for MediaPermissions {
    fn default() -> Self {
        Self::defaults()
    }
}

/// What a capture site should do, given the current permission posture
/// and the device it wants to touch. This is the only return shape
/// future camera/screen code paths should branch on — keeps the
/// "have we asked the user?" decision out of every device adapter.
#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub enum CaptureGate {
    /// User has pre-authorised this device. Proceed with the OS prompt
    /// (which is still the source of truth at the OS layer).
    Proceed,
    /// Per-session approval prompt required before the device may be
    /// acquired. Wire to the existing approval/trust modal.
    PromptUser,
    /// Capture is hard-disabled. Surface the disabled state in the UI
    /// and do not attempt acquisition.
    Deny,
}

/// Load the persisted permissions from `path`, falling back to
/// [`MediaPermissions::defaults`] if the file is missing or malformed.
///
/// This is intentionally lenient about read failures: a corrupt or
/// unreadable file MUST NOT take down the shell. Returning the default
/// (both `Ask`) keeps the user in the safe state where the next
/// capture attempt re-prompts.
pub fn load_or_default(path: &Path) -> MediaPermissions {
    match fs::read_to_string(path) {
        Ok(s) => match serde_json::from_str::<MediaPermissions>(&s) {
            Ok(p) => p,
            Err(e) => {
                tracing::warn!(
                    "media permissions file {} is malformed ({e}); using defaults",
                    path.display()
                );
                MediaPermissions::defaults()
            }
        },
        Err(e) if e.kind() == ErrorKind::NotFound => MediaPermissions::defaults(),
        Err(e) => {
            tracing::warn!(
                "could not read media permissions file {}: {e}; using defaults",
                path.display()
            );
            MediaPermissions::defaults()
        }
    }
}

/// Atomically persist `perms` to `path`, creating parent directories
/// as needed.
///
/// "Atomic" here means write-to-temp-then-rename, so a crash in the
/// middle of a write cannot leave a half-written JSON file the next
/// boot will reject.
pub fn save(path: &Path, perms: &MediaPermissions) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("json.tmp");
    let body = serde_json::to_string_pretty(perms)
        .map_err(|e| io::Error::new(ErrorKind::InvalidData, e))?;
    fs::write(&tmp, body)?;
    fs::rename(&tmp, path)?;
    Ok(())
}

/// Resolve the canonical permissions file path beside a durable
/// session-memory database. Used by the shell when constructing the
/// `AppState`; tests may pass any directory.
pub fn permissions_path_for(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join("media_permissions.json")
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn defaults_are_ask_for_both_devices() {
        let p = MediaPermissions::defaults();
        assert_eq!(p.camera, PermissionState::Ask);
        assert_eq!(p.screen, PermissionState::Ask);
    }

    #[test]
    fn evaluate_returns_correct_gate_for_each_state() {
        let mut p = MediaPermissions::defaults();
        assert_eq!(p.evaluate(MediaKind::Camera), CaptureGate::PromptUser);
        p.set(MediaKind::Camera, PermissionState::Allow);
        assert_eq!(p.evaluate(MediaKind::Camera), CaptureGate::Proceed);
        p.set(MediaKind::Camera, PermissionState::Deny);
        assert_eq!(p.evaluate(MediaKind::Camera), CaptureGate::Deny);
        // Screen should be unaffected by camera changes.
        assert_eq!(p.evaluate(MediaKind::Screen), CaptureGate::PromptUser);
    }

    #[test]
    fn set_only_touches_the_targeted_device() {
        let mut p = MediaPermissions::defaults();
        p.set(MediaKind::Screen, PermissionState::Allow);
        assert_eq!(p.camera, PermissionState::Ask);
        assert_eq!(p.screen, PermissionState::Allow);
    }

    #[test]
    fn load_or_default_when_missing_returns_defaults() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("missing.json");
        let p = load_or_default(&path);
        assert_eq!(p, MediaPermissions::defaults());
    }

    #[test]
    fn save_then_load_roundtrips() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("nested").join("media_permissions.json");
        let mut original = MediaPermissions::defaults();
        original.set(MediaKind::Camera, PermissionState::Allow);
        original.set(MediaKind::Screen, PermissionState::Deny);
        save(&path, &original).expect("save");

        let loaded = load_or_default(&path);
        assert_eq!(loaded, original);
    }

    #[test]
    fn load_or_default_falls_back_on_malformed_json() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("media_permissions.json");
        fs::write(&path, "not json").unwrap();
        let p = load_or_default(&path);
        assert_eq!(p, MediaPermissions::defaults());
    }

    #[test]
    fn wire_format_roundtrips_for_every_state() {
        for s in [
            PermissionState::Allow,
            PermissionState::Ask,
            PermissionState::Deny,
        ] {
            assert_eq!(PermissionState::from_wire(s.wire()), Some(s));
        }
        assert!(PermissionState::from_wire("unknown").is_none());
    }

    #[test]
    fn wire_format_for_media_kind() {
        assert_eq!(MediaKind::from_wire("camera"), Some(MediaKind::Camera));
        assert_eq!(MediaKind::from_wire("screen"), Some(MediaKind::Screen));
        assert_eq!(MediaKind::from_wire("nope"), None);
    }

    #[test]
    fn json_uses_lowercase_state_strings() {
        let mut p = MediaPermissions::defaults();
        p.set(MediaKind::Camera, PermissionState::Allow);
        let s = serde_json::to_string(&p).unwrap();
        assert!(
            s.contains("\"allow\""),
            "expected lowercase state in JSON, got: {s}"
        );
        assert!(s.contains("\"ask\""));
    }

    #[test]
    fn permissions_path_for_lives_beside_app_data() {
        let dir = Path::new("/tmp/aether-test");
        let p = permissions_path_for(dir);
        assert_eq!(p, Path::new("/tmp/aether-test/media_permissions.json"));
    }
}
