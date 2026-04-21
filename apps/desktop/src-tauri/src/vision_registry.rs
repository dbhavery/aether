//! Vision provider registry — keeps zero, one, or several
//! [`VisionProvider`] implementations alongside an active selection
//! the user can change at runtime.
//!
//! ## Why a registry instead of a single Option?
//!
//! Adding a second [`VisionProvider`] (P1 of 2026-04-26) made the
//! single-`Option` model on `AppState` insufficient: the user might
//! have both Ollama vision AND llama.cpp vision configured at boot
//! and want to swap between them without restarting. The registry
//! holds the bag of available adapters; the active selection lives
//! in a small `RwLock` next to it; persistence is a tiny JSON file
//! beside `media_permissions.json`.
//!
//! ## Persistence
//!
//! Active selection is stored as `<app_data>/vision_provider.json`:
//!
//! ```json
//! { "active": "ollama-vision" }
//! ```
//!
//! When the file is missing, malformed, or names an id that is no
//! longer registered, the registry falls back to the first registered
//! provider (insertion order) — never crashes the shell.

use std::fs;
use std::io::{self, ErrorKind};
use std::path::{Path, PathBuf};
use std::sync::{Arc, RwLock};

use aether_l4_router::VisionProvider;
use serde::{Deserialize, Serialize};

/// Wire shape persisted to `vision_provider.json`. Tiny on purpose —
/// the active id is the only piece of state the user controls.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct VisionPersistedState {
    /// Provider id (matches `VisionProvider::id`). `None` when the
    /// user has explicitly cleared the selection (text-only mode).
    pub active: Option<String>,
}

/// Status entry shown to the UI for one registered provider.
#[derive(Debug, Clone, Serialize)]
pub struct VisionProviderInfo {
    /// Stable id (`"ollama-vision"`, `"llamacpp-vision"`, ...).
    pub id: String,
    /// Human-readable label.
    pub label: String,
    /// Whether this provider is the currently-active one. Exactly one
    /// `true` across the list when an active provider is configured;
    /// all `false` when the user has deliberately picked text-only or
    /// no providers were registered at boot.
    pub active: bool,
}

/// In-memory bag of registered providers + the active id.
pub struct VisionRegistry {
    providers: Vec<RegisteredProvider>,
    active: RwLock<Option<String>>,
    persistence_path: Option<PathBuf>,
}

struct RegisteredProvider {
    id: String,
    provider: Arc<dyn VisionProvider>,
}

impl VisionRegistry {
    /// Empty registry. Equivalent to "no vision providers configured".
    pub fn empty() -> Self {
        Self {
            providers: Vec::new(),
            active: RwLock::new(None),
            persistence_path: None,
        }
    }

    /// Register a provider. Insertion order matters because it
    /// determines the fallback when the persisted active id refers to
    /// an unknown provider — first-registered wins.
    pub fn register(&mut self, provider: Arc<dyn VisionProvider>) {
        let id = provider.id().to_string();
        // De-dup: if a provider with this id is already registered,
        // replace it. Lets a future hot-reload swap an adapter
        // without growing the list.
        if let Some(existing) = self.providers.iter_mut().find(|p| p.id == id) {
            existing.provider = provider;
            return;
        }
        self.providers.push(RegisteredProvider { id, provider });
    }

    /// Wire a disk-backed persistence file. Reads the persisted active
    /// id and applies it (with the fallback rules described in the
    /// module docs). Subsequent `set_active` calls write back through
    /// this path.
    pub fn attach_persistence(&mut self, path: PathBuf) {
        let persisted = load_persisted(&path);
        self.persistence_path = Some(path);
        self.apply_persisted_active(persisted);
    }

    fn apply_persisted_active(&self, persisted: VisionPersistedState) {
        let mut w = self.active.write().expect("vision active write lock");
        match persisted.active {
            Some(id) if self.providers.iter().any(|p| p.id == id) => {
                *w = Some(id);
            }
            Some(unknown) => {
                tracing::warn!(
                    "persisted vision provider id {:?} is not registered; using fallback",
                    unknown
                );
                *w = self.providers.first().map(|p| p.id.clone());
            }
            None => {
                // The user explicitly cleared the selection (text-only
                // mode). Honor it even if providers are registered.
                *w = None;
            }
        }
    }

    /// Auto-select a default active provider when none was persisted.
    /// First-registered wins; idempotent so it's safe to call from
    /// boot regardless of whether persistence is wired.
    pub fn auto_select_first_if_unset(&self) {
        let mut w = self.active.write().expect("vision active write lock");
        if w.is_none() {
            *w = self.providers.first().map(|p| p.id.clone());
        }
    }

    /// Active provider handle. `None` when no provider is selected
    /// (text-only mode) or no provider is registered.
    pub fn active(&self) -> Option<Arc<dyn VisionProvider>> {
        let id = self.active.read().expect("vision active read lock").clone();
        let id = id?;
        self.providers
            .iter()
            .find(|p| p.id == id)
            .map(|p| p.provider.clone())
    }

    /// Active provider id, if any.
    pub fn active_id(&self) -> Option<String> {
        self.active.read().expect("vision active read lock").clone()
    }

    /// Active provider label, if any.
    pub fn active_label(&self) -> Option<String> {
        self.active().map(|p| p.label())
    }

    /// Snapshot of every registered provider's `(id, label, active)`
    /// in registration order.
    pub fn list(&self) -> Vec<VisionProviderInfo> {
        let active_id = self.active_id();
        self.providers
            .iter()
            .map(|p| VisionProviderInfo {
                id: p.id.clone(),
                label: p.provider.label(),
                active: active_id.as_deref() == Some(p.id.as_str()),
            })
            .collect()
    }

    /// Set the active provider by id. Pass `None` to deliberately
    /// switch to text-only mode (the assistant will run the existing
    /// text-fallback path on subsequent `analyze_frame` calls).
    /// Persists the new selection through the attached file when one
    /// is wired.
    pub fn set_active(&self, id: Option<String>) -> Result<(), String> {
        if let Some(want) = id.as_deref() {
            if !self.providers.iter().any(|p| p.id == want) {
                return Err(format!("unknown vision provider id: {want}"));
            }
        }
        {
            let mut w = self.active.write().expect("vision active write lock");
            *w = id.clone();
        }
        if let Some(path) = &self.persistence_path {
            if let Err(e) = save_persisted(path, &VisionPersistedState { active: id }) {
                return Err(format!("persist vision provider: {e}"));
            }
        }
        Ok(())
    }

    /// Number of registered providers. Useful for boot-time logging.
    #[allow(dead_code)] // Surfaced via tests + future logging.
    pub fn len(&self) -> usize {
        self.providers.len()
    }

    /// `true` when no providers have been registered.
    #[allow(dead_code)] // Surfaced via tests + future logging.
    pub fn is_empty(&self) -> bool {
        self.providers.is_empty()
    }
}

/// Resolve the canonical persistence file path beside the
/// media-permissions file. Tests may pass any directory.
pub fn vision_persistence_path_for(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join("vision_provider.json")
}

fn load_persisted(path: &Path) -> VisionPersistedState {
    match fs::read_to_string(path) {
        Ok(s) => serde_json::from_str(&s).unwrap_or_else(|e| {
            tracing::warn!("vision_provider.json is malformed ({e}); ignoring persisted selection");
            VisionPersistedState::default()
        }),
        Err(e) if e.kind() == ErrorKind::NotFound => VisionPersistedState::default(),
        Err(e) => {
            tracing::warn!("could not read vision_provider.json: {e}");
            VisionPersistedState::default()
        }
    }
}

fn save_persisted(path: &Path, state: &VisionPersistedState) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("json.tmp");
    let body = serde_json::to_string_pretty(state)
        .map_err(|e| io::Error::new(ErrorKind::InvalidData, e))?;
    fs::write(&tmp, body)?;
    fs::rename(&tmp, path)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use aether_l4_router::{L4Error, VisionRequest, VisionResponse};
    use tempfile::TempDir;

    struct StubProvider {
        id: &'static str,
        label_text: String,
    }

    impl StubProvider {
        fn new(id: &'static str) -> Arc<Self> {
            Arc::new(Self {
                id,
                label_text: format!("stub · {id}"),
            })
        }
    }

    impl VisionProvider for StubProvider {
        fn id(&self) -> &str {
            self.id
        }
        fn label(&self) -> String {
            self.label_text.clone()
        }
        fn healthcheck(&self) -> Result<(), L4Error> {
            Ok(())
        }
        fn analyze(&self, _req: VisionRequest) -> Result<VisionResponse, L4Error> {
            Ok(VisionResponse {
                text: format!("stub:{}", self.id),
                prompt_tokens: None,
                completion_tokens: None,
            })
        }
    }

    #[test]
    fn empty_registry_has_no_active_provider() {
        let r = VisionRegistry::empty();
        assert!(r.is_empty());
        assert!(r.active().is_none());
        assert!(r.active_id().is_none());
        assert!(r.list().is_empty());
    }

    #[test]
    fn auto_select_first_picks_insertion_order() {
        let mut r = VisionRegistry::empty();
        r.register(StubProvider::new("alpha"));
        r.register(StubProvider::new("beta"));
        r.auto_select_first_if_unset();
        assert_eq!(r.active_id().as_deref(), Some("alpha"));
    }

    #[test]
    fn list_marks_exactly_the_active_provider() {
        let mut r = VisionRegistry::empty();
        r.register(StubProvider::new("alpha"));
        r.register(StubProvider::new("beta"));
        r.set_active(Some("beta".into())).unwrap();
        let infos = r.list();
        assert_eq!(infos.len(), 2);
        assert_eq!(infos[0].id, "alpha");
        assert!(!infos[0].active);
        assert_eq!(infos[1].id, "beta");
        assert!(infos[1].active);
    }

    #[test]
    fn set_active_rejects_unknown_id() {
        let mut r = VisionRegistry::empty();
        r.register(StubProvider::new("alpha"));
        let err = r.set_active(Some("nope".into())).unwrap_err();
        assert!(err.contains("nope"));
        assert_eq!(r.active_id(), None);
    }

    #[test]
    fn set_active_none_clears_selection() {
        let mut r = VisionRegistry::empty();
        r.register(StubProvider::new("alpha"));
        r.auto_select_first_if_unset();
        assert_eq!(r.active_id().as_deref(), Some("alpha"));
        r.set_active(None).unwrap();
        assert!(r.active_id().is_none());
        assert!(r.active().is_none());
    }

    #[test]
    fn register_dedups_by_id() {
        let mut r = VisionRegistry::empty();
        r.register(StubProvider::new("alpha"));
        r.register(StubProvider::new("alpha"));
        assert_eq!(r.len(), 1);
    }

    #[test]
    fn persistence_round_trips_active_selection() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("vision_provider.json");
        {
            let mut r = VisionRegistry::empty();
            r.register(StubProvider::new("alpha"));
            r.register(StubProvider::new("beta"));
            r.attach_persistence(path.clone());
            r.set_active(Some("beta".into())).unwrap();
        }
        // Reopen — same providers, same path. Should restore "beta".
        let mut r2 = VisionRegistry::empty();
        r2.register(StubProvider::new("alpha"));
        r2.register(StubProvider::new("beta"));
        r2.attach_persistence(path);
        assert_eq!(r2.active_id().as_deref(), Some("beta"));
    }

    #[test]
    fn persisted_unknown_id_falls_back_to_first_registered() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("vision_provider.json");
        save_persisted(
            &path,
            &VisionPersistedState {
                active: Some("ghost".into()),
            },
        )
        .unwrap();

        let mut r = VisionRegistry::empty();
        r.register(StubProvider::new("alpha"));
        r.register(StubProvider::new("beta"));
        r.attach_persistence(path);
        // "ghost" isn't registered → fall back to first ("alpha").
        assert_eq!(r.active_id().as_deref(), Some("alpha"));
    }

    #[test]
    fn persisted_explicit_none_keeps_text_only_mode() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("vision_provider.json");
        save_persisted(&path, &VisionPersistedState { active: None }).unwrap();

        let mut r = VisionRegistry::empty();
        r.register(StubProvider::new("alpha"));
        r.attach_persistence(path);
        assert!(r.active_id().is_none());
    }

    #[test]
    fn missing_persistence_file_uses_fallback_select() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("nope.json");

        let mut r = VisionRegistry::empty();
        r.register(StubProvider::new("alpha"));
        r.attach_persistence(path);
        // No persisted state → active stays None until auto_select.
        assert!(r.active_id().is_none());
        r.auto_select_first_if_unset();
        assert_eq!(r.active_id().as_deref(), Some("alpha"));
    }

    #[test]
    fn vision_persistence_path_helper_lives_beside_app_data() {
        let dir = Path::new("/tmp/aether-test");
        let p = vision_persistence_path_for(dir);
        assert_eq!(p, Path::new("/tmp/aether-test/vision_provider.json"));
    }
}
