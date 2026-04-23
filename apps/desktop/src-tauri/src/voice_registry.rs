//! Speech provider registry — keeps zero, one, or several
//! [`SpeechProvider`] implementations alongside an active selection
//! the user can change at runtime. Voice V1 step 3.
//!
//! ## Why a registry instead of a single Option?
//!
//! Same reasoning as `vision_registry.rs`: the shell must tolerate
//! multiple adapters being configured at boot (whisper.cpp today, a
//! hypothetical second local adapter tomorrow) and let the user swap
//! between them without restarting. The registry holds the bag of
//! available adapters; the active selection lives in a small `RwLock`
//! next to it; persistence is a tiny JSON file beside
//! `vision_provider.json`.
//!
//! ## Persistence
//!
//! Active selection + per-provider model is stored as
//! `<app_data>/voice_provider.json`:
//!
//! ```json
//! {
//!   "active": "whispercpp-speech",
//!   "model_per_provider": { "whispercpp-speech": "ggml-base.en.bin" }
//! }
//! ```
//!
//! Contract (identical to `vision_provider.json`):
//!
//! - **Additive** — new fields may be added by future builds.
//! - **Default-safe on read** — `model_per_provider` has a `serde`
//!   default; `active` is `Option<String>`. Old files that lack a
//!   field load cleanly.
//! - **Unknown fields silently ignored on read.** No
//!   `#[serde(deny_unknown_fields)]`.
//! - **Unknown fields dropped on rewrite.** No `serde(flatten)`
//!   extras bag. Documented limitation; locked by test.
//! - **Malformed JSON falls back to default state with a WARN that
//!   names the file path** — the shell still boots cleanly.
//! - **Persistence is single-writer through `VoiceRegistry`.**
//!
//! When the file is missing, malformed, or names an id that is no
//! longer registered, the registry falls back to the first registered
//! provider (insertion order) — never crashes the shell.

use std::collections::BTreeMap;
use std::fs;
use std::io::{self, ErrorKind};
use std::path::{Path, PathBuf};
use std::sync::{Arc, RwLock};

use aether_l4_router::SpeechProvider;
use serde::{Deserialize, Serialize};

/// Wire shape persisted to `voice_provider.json`. Additive contract —
/// old files that only carry `active` keep loading because
/// `model_per_provider` has a serde default.
#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq, Eq)]
pub struct VoicePersistedState {
    /// Provider id (matches `SpeechProvider::id`). `None` when the
    /// user has explicitly cleared the selection (voice disabled).
    pub active: Option<String>,
    /// Per-provider last-selected model id. Survives a provider swap
    /// so switching whisper.cpp → (future adapter) → whisper.cpp
    /// restores the whisper.cpp model the user previously picked.
    /// Uses a BTreeMap so the JSON output is deterministic (stable
    /// key order) — tests assert on round-trips.
    #[serde(default)]
    pub model_per_provider: BTreeMap<String, String>,
}

/// Status entry shown to the UI for one registered speech provider.
#[derive(Debug, Clone, Serialize)]
pub struct SpeechProviderInfo {
    /// Stable id (`"whispercpp-speech"`, future others).
    pub id: String,
    /// Human-readable label.
    pub label: String,
    /// Whether this provider is the currently-active one. Exactly
    /// one `true` across the list when an active provider is
    /// configured; all `false` when the user has deliberately
    /// disabled voice or no providers were registered at boot.
    pub active: bool,
}

/// In-memory bag of registered speech providers + the active id.
pub struct VoiceRegistry {
    providers: Vec<RegisteredProvider>,
    active: RwLock<Option<String>>,
    /// Last-selected model id per provider id. Persisted to
    /// `voice_provider.json` and applied to each provider via
    /// `SpeechProvider::set_model` at attach time and on provider
    /// swap.
    model_per_provider: RwLock<BTreeMap<String, String>>,
    persistence_path: Option<PathBuf>,
}

struct RegisteredProvider {
    id: String,
    provider: Arc<dyn SpeechProvider>,
}

impl VoiceRegistry {
    /// Empty registry. Equivalent to "no speech providers configured".
    pub fn empty() -> Self {
        Self {
            providers: Vec::new(),
            active: RwLock::new(None),
            model_per_provider: RwLock::new(BTreeMap::new()),
            persistence_path: None,
        }
    }

    /// Register a speech provider. Insertion order matters because
    /// it determines the fallback when the persisted active id
    /// refers to an unknown provider — first-registered wins.
    pub fn register(&mut self, provider: Arc<dyn SpeechProvider>) {
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

    /// Wire a disk-backed persistence file. Reads the persisted
    /// active id and the per-provider model map, applies each
    /// persisted model to its matching adapter via
    /// `SpeechProvider::set_model`, and applies the active id (with
    /// fallback rules). Subsequent `set_active` / `set_active_model`
    /// calls write back through this path.
    pub fn attach_persistence(&mut self, path: PathBuf) {
        let persisted = load_persisted(&path);
        self.persistence_path = Some(path);
        self.apply_persisted(persisted);
    }

    fn apply_persisted(&self, persisted: VoicePersistedState) {
        // Hydrate the model map first so that once the active
        // provider is set below, it's already pointed at the right
        // model.
        {
            let mut map = self
                .model_per_provider
                .write()
                .expect("voice model map write lock");
            *map = persisted.model_per_provider.clone();
        }
        // Push each persisted model into its matching adapter.
        // Unknown provider ids are tolerated — they may belong to a
        // feature that's not compiled in this build; we keep the
        // entry in the map so a future boot that does have the
        // feature inherits it.
        for (id, model) in persisted.model_per_provider.iter() {
            if let Some(p) = self.providers.iter().find(|p| p.id == *id) {
                if let Err(e) = p.provider.set_model(model) {
                    tracing::warn!(
                        "voice: persisted model {:?} for provider {:?} rejected: {e}",
                        model,
                        id
                    );
                }
            }
        }

        let mut w = self.active.write().expect("voice active write lock");
        match persisted.active {
            Some(id) if self.providers.iter().any(|p| p.id == id) => {
                *w = Some(id);
            }
            Some(unknown) => {
                tracing::warn!(
                    "persisted voice provider id {:?} is not registered; using fallback",
                    unknown
                );
                *w = self.providers.first().map(|p| p.id.clone());
            }
            None => {
                // The user explicitly cleared the selection (voice
                // disabled). Honor it even if providers are
                // registered.
                *w = None;
            }
        }
    }

    /// Auto-select a default active provider when none was
    /// persisted. First-registered wins; idempotent so it's safe to
    /// call from boot regardless of whether persistence is wired.
    pub fn auto_select_first_if_unset(&self) {
        let mut w = self.active.write().expect("voice active write lock");
        if w.is_none() {
            *w = self.providers.first().map(|p| p.id.clone());
        }
    }

    /// Active speech provider handle. `None` when no provider is
    /// selected (voice disabled) or no provider is registered.
    pub fn active(&self) -> Option<Arc<dyn SpeechProvider>> {
        let id = self.active.read().expect("voice active read lock").clone();
        let id = id?;
        self.providers
            .iter()
            .find(|p| p.id == id)
            .map(|p| p.provider.clone())
    }

    /// Active provider id, if any.
    pub fn active_id(&self) -> Option<String> {
        self.active.read().expect("voice active read lock").clone()
    }

    /// Active provider label, if any.
    pub fn active_label(&self) -> Option<String> {
        self.active().map(|p| p.label())
    }

    /// Snapshot of every registered provider's `(id, label, active)`
    /// in registration order.
    pub fn list(&self) -> Vec<SpeechProviderInfo> {
        let active_id = self.active_id();
        self.providers
            .iter()
            .map(|p| SpeechProviderInfo {
                id: p.id.clone(),
                label: p.provider.label(),
                active: active_id.as_deref() == Some(p.id.as_str()),
            })
            .collect()
    }

    /// Set the active provider by id. Pass `None` to deliberately
    /// disable voice input (future `transcribe_utterance` calls will
    /// surface a clear "no active speech provider" error rather than
    /// fall back silently). Persists the new selection through the
    /// attached file when one is wired, and reapplies the
    /// newly-active provider's persisted model (if any) so the swap
    /// restores the user's last pick.
    pub fn set_active(&self, id: Option<String>) -> Result<(), String> {
        if let Some(want) = id.as_deref() {
            if !self.providers.iter().any(|p| p.id == want) {
                return Err(format!("unknown speech provider id: {want}"));
            }
        }
        {
            let mut w = self.active.write().expect("voice active write lock");
            *w = id.clone();
        }

        // Reapply any persisted model for the newly-active provider
        // so the adapter's model state matches what the user last
        // picked on that provider.
        if let Some(active_id) = id.as_deref() {
            let persisted_model = self
                .model_per_provider
                .read()
                .expect("voice model map read lock")
                .get(active_id)
                .cloned();
            if let Some(model) = persisted_model {
                if let Some(p) = self.providers.iter().find(|p| p.id == active_id) {
                    if let Err(e) = p.provider.set_model(&model) {
                        tracing::warn!(
                            "voice: replaying persisted model {:?} for {:?} failed: {e}",
                            model,
                            active_id
                        );
                    }
                }
            }
        }

        self.save_current_state()
    }

    /// Switch the model used by the currently-active speech provider.
    /// Errors when no provider is active, when the target provider
    /// has been removed from the registry, or when the adapter
    /// rejects the id. On success the new model is persisted under
    /// the active provider id so a future provider swap restores the
    /// same pick.
    pub fn set_active_model(&self, model: &str) -> Result<(), String> {
        let active_id = self
            .active_id()
            .ok_or_else(|| "no active speech provider".to_string())?;
        let provider = self
            .providers
            .iter()
            .find(|p| p.id == active_id)
            .ok_or_else(|| format!("active provider {active_id} no longer registered"))?;
        provider
            .provider
            .set_model(model)
            .map_err(|e| format!("set_model: {e}"))?;
        {
            let mut map = self
                .model_per_provider
                .write()
                .expect("voice model map write lock");
            map.insert(active_id, model.to_string());
        }
        self.save_current_state()
    }

    /// Currently-active provider's model id, if any. Reads the live
    /// adapter (not the persisted map) so callers always see what
    /// the next `transcribe` call will actually use.
    pub fn active_model(&self) -> Option<String> {
        self.active().and_then(|p| p.current_model())
    }

    /// Snapshot of the per-provider persisted model map entry for
    /// the given id. Exposed for tests and future model-cache
    /// wiring.
    #[allow(dead_code)]
    pub fn model_for(&self, provider_id: &str) -> Option<String> {
        self.model_per_provider
            .read()
            .expect("voice model map read lock")
            .get(provider_id)
            .cloned()
    }

    /// Boot-time first-launch hook. For every registered provider
    /// that is NOT already in `model_per_provider`, ask the adapter
    /// for its `current_model()` and seed the map with that value.
    /// If anything changed, persist the result so the on-disk file
    /// reflects the model the user is actually running, even before
    /// they've touched the badge.
    ///
    /// Idempotent: re-running after first launch is a no-op because
    /// every provider is already in the map. Adapters that don't
    /// expose `current_model()` (passive future adapters) are
    /// skipped — the map gets nothing rather than a misleading
    /// empty string.
    ///
    /// Persistence failures are returned as `Err` but the in-memory
    /// seed is still applied; the caller logs and continues so a
    /// read-only data dir doesn't block first launch.
    pub fn seed_missing_models_from_adapters(&self) -> Result<(), String> {
        let mut changed = false;
        {
            let mut map = self
                .model_per_provider
                .write()
                .expect("voice model map write lock");
            for p in &self.providers {
                if map.contains_key(&p.id) {
                    continue;
                }
                let Some(model) = p.provider.current_model() else {
                    continue;
                };
                if model.trim().is_empty() {
                    continue;
                }
                map.insert(p.id.clone(), model);
                changed = true;
            }
        }
        if changed {
            self.save_current_state()?;
        }
        Ok(())
    }

    fn save_current_state(&self) -> Result<(), String> {
        let Some(path) = &self.persistence_path else {
            return Ok(());
        };
        let state = VoicePersistedState {
            active: self.active.read().expect("voice active read lock").clone(),
            model_per_provider: self
                .model_per_provider
                .read()
                .expect("voice model map read lock")
                .clone(),
        };
        save_persisted(path, &state).map_err(|e| format!("persist voice provider: {e}"))
    }

    /// Number of registered providers. Useful for boot-time
    /// logging.
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
/// `vision_provider.json` file. Tests may pass any directory.
pub fn voice_persistence_path_for(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join("voice_provider.json")
}

fn load_persisted(path: &Path) -> VoicePersistedState {
    match fs::read_to_string(path) {
        Ok(s) => serde_json::from_str(&s).unwrap_or_else(|e| {
            tracing::warn!(
                "voice_provider.json at {} is malformed ({e}); ignoring persisted selection",
                path.display(),
            );
            VoicePersistedState::default()
        }),
        Err(e) if e.kind() == ErrorKind::NotFound => VoicePersistedState::default(),
        Err(e) => {
            tracing::warn!(
                "could not read voice_provider.json at {}: {e}",
                path.display(),
            );
            VoicePersistedState::default()
        }
    }
}

fn save_persisted(path: &Path, state: &VoicePersistedState) -> io::Result<()> {
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
    use aether_l4_router::{L4Error, SpeechRequest, SpeechResponse};
    use tempfile::TempDir;

    struct StubSpeech {
        id: &'static str,
        label_text: String,
        model: RwLock<String>,
    }

    impl StubSpeech {
        fn new(id: &'static str) -> Arc<Self> {
            Self::new_with_model(id, "default-model")
        }

        fn new_with_model(id: &'static str, model: &str) -> Arc<Self> {
            Arc::new(Self {
                id,
                label_text: format!("stub-speech · {id}"),
                model: RwLock::new(model.to_string()),
            })
        }
    }

    impl SpeechProvider for StubSpeech {
        fn id(&self) -> &str {
            self.id
        }
        fn label(&self) -> String {
            format!(
                "{} ({})",
                self.label_text,
                self.model.read().unwrap().clone()
            )
        }
        fn healthcheck(&self) -> Result<(), L4Error> {
            Ok(())
        }
        fn set_model(&self, id: &str) -> Result<(), L4Error> {
            *self.model.write().unwrap() = id.to_string();
            Ok(())
        }
        fn current_model(&self) -> Option<String> {
            Some(self.model.read().unwrap().clone())
        }
        fn transcribe(&self, _req: SpeechRequest) -> Result<SpeechResponse, L4Error> {
            Ok(SpeechResponse {
                text: format!("stub:{}", self.id),
                confidence: None,
                prompt_tokens: None,
                completion_tokens: None,
            })
        }
    }

    #[test]
    fn empty_registry_has_no_active_provider() {
        let r = VoiceRegistry::empty();
        assert!(r.is_empty());
        assert!(r.active().is_none());
        assert!(r.active_id().is_none());
        assert!(r.list().is_empty());
    }

    #[test]
    fn auto_select_first_picks_insertion_order() {
        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        r.register(StubSpeech::new("beta"));
        r.auto_select_first_if_unset();
        assert_eq!(r.active_id().as_deref(), Some("alpha"));
    }

    #[test]
    fn list_marks_exactly_the_active_provider() {
        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        r.register(StubSpeech::new("beta"));
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
        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        let err = r.set_active(Some("nope".into())).unwrap_err();
        assert!(err.contains("nope"));
        assert_eq!(r.active_id(), None);
    }

    #[test]
    fn set_active_none_disables_voice() {
        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        r.auto_select_first_if_unset();
        assert_eq!(r.active_id().as_deref(), Some("alpha"));
        r.set_active(None).unwrap();
        assert!(r.active_id().is_none());
        assert!(r.active().is_none());
    }

    #[test]
    fn register_dedups_by_id() {
        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        r.register(StubSpeech::new("alpha"));
        assert_eq!(r.len(), 1);
    }

    #[test]
    fn persistence_round_trips_active_selection() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("voice_provider.json");
        {
            let mut r = VoiceRegistry::empty();
            r.register(StubSpeech::new("alpha"));
            r.register(StubSpeech::new("beta"));
            r.attach_persistence(path.clone());
            r.set_active(Some("beta".into())).unwrap();
        }
        let mut r2 = VoiceRegistry::empty();
        r2.register(StubSpeech::new("alpha"));
        r2.register(StubSpeech::new("beta"));
        r2.attach_persistence(path);
        assert_eq!(r2.active_id().as_deref(), Some("beta"));
    }

    #[test]
    fn persisted_unknown_id_falls_back_to_first_registered() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("voice_provider.json");
        save_persisted(
            &path,
            &VoicePersistedState {
                active: Some("ghost".into()),
                ..Default::default()
            },
        )
        .unwrap();

        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        r.register(StubSpeech::new("beta"));
        r.attach_persistence(path);
        assert_eq!(r.active_id().as_deref(), Some("alpha"));
    }

    #[test]
    fn persisted_explicit_none_keeps_voice_disabled() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("voice_provider.json");
        save_persisted(&path, &VoicePersistedState::default()).unwrap();

        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        r.attach_persistence(path);
        assert!(r.active_id().is_none());
    }

    #[test]
    fn missing_persistence_file_uses_fallback_select() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("nope.json");

        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        r.attach_persistence(path);
        assert!(r.active_id().is_none());
        r.auto_select_first_if_unset();
        assert_eq!(r.active_id().as_deref(), Some("alpha"));
    }

    #[test]
    fn set_active_model_writes_through_provider_and_map() {
        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        r.register(StubSpeech::new("beta"));
        r.set_active(Some("alpha".into())).unwrap();

        assert_eq!(r.active_model().as_deref(), Some("default-model"));
        r.set_active_model("ggml-base.en")
            .expect("set_active_model");
        assert_eq!(r.active_model().as_deref(), Some("ggml-base.en"));
        assert_eq!(r.model_for("alpha").as_deref(), Some("ggml-base.en"));
        assert!(r.model_for("beta").is_none());
    }

    #[test]
    fn set_active_model_errors_when_no_active_provider() {
        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        let err = r.set_active_model("x").unwrap_err();
        assert!(err.contains("no active"));
    }

    #[test]
    fn provider_swap_preserves_each_providers_last_model() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("voice_provider.json");

        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        r.register(StubSpeech::new("beta"));
        r.attach_persistence(path.clone());

        r.set_active(Some("alpha".into())).unwrap();
        r.set_active_model("ggml-base.en").unwrap();

        r.set_active(Some("beta".into())).unwrap();
        r.set_active_model("ggml-small").unwrap();

        r.set_active(Some("alpha".into())).unwrap();
        assert_eq!(r.active_model().as_deref(), Some("ggml-base.en"));

        r.set_active(Some("beta".into())).unwrap();
        assert_eq!(r.active_model().as_deref(), Some("ggml-small"));
    }

    #[test]
    fn persisted_model_map_round_trips_and_reapplies_on_reopen() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("voice_provider.json");

        {
            let mut r = VoiceRegistry::empty();
            r.register(StubSpeech::new("alpha"));
            r.register(StubSpeech::new("beta"));
            r.attach_persistence(path.clone());
            r.set_active(Some("alpha".into())).unwrap();
            r.set_active_model("ggml-base.en").unwrap();
            r.set_active(Some("beta".into())).unwrap();
            r.set_active_model("ggml-small").unwrap();
        }

        let mut r2 = VoiceRegistry::empty();
        r2.register(StubSpeech::new("alpha"));
        r2.register(StubSpeech::new("beta"));
        r2.attach_persistence(path);

        assert_eq!(r2.active_id().as_deref(), Some("beta"));
        assert_eq!(r2.active_model().as_deref(), Some("ggml-small"));
        assert_eq!(r2.model_for("alpha").as_deref(), Some("ggml-base.en"));
        assert_eq!(r2.model_for("beta").as_deref(), Some("ggml-small"));
    }

    #[test]
    fn persisted_model_for_unknown_provider_is_retained_but_not_applied() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("voice_provider.json");
        let mut seed = VoicePersistedState::default();
        seed.active = Some("alpha".into());
        seed.model_per_provider
            .insert("ghost".into(), "phantom-model".into());
        seed.model_per_provider
            .insert("alpha".into(), "ggml-base.en".into());
        save_persisted(&path, &seed).unwrap();

        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        r.attach_persistence(path);

        assert_eq!(r.active_model().as_deref(), Some("ggml-base.en"));
        assert_eq!(r.model_for("ghost").as_deref(), Some("phantom-model"));
    }

    #[test]
    fn unknown_top_level_field_is_ignored_on_load() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("voice_provider.json");
        std::fs::write(
            &path,
            r#"{
                "active": "alpha",
                "model_per_provider": { "alpha": "ggml-base.en" },
                "future_unknown_field": "hello",
                "future_object": { "nested": 42 },
                "future_array": [1, 2, 3]
            }"#,
        )
        .unwrap();

        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        r.attach_persistence(path);
        assert_eq!(r.active_id().as_deref(), Some("alpha"));
        assert_eq!(r.model_for("alpha").as_deref(), Some("ggml-base.en"));
    }

    #[test]
    fn load_persisted_directly_tolerates_unknown_fields() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("voice_provider.json");
        std::fs::write(
            &path,
            r#"{
                "active": "beta",
                "model_per_provider": {
                    "alpha": "ggml-base.en",
                    "beta": "ggml-small"
                },
                "schema_version": 7,
                "telemetry_opt_in": false
            }"#,
        )
        .unwrap();

        let loaded = load_persisted(&path);
        assert_eq!(loaded.active.as_deref(), Some("beta"));
        assert_eq!(
            loaded.model_per_provider.get("alpha").map(String::as_str),
            Some("ggml-base.en"),
        );
        assert_eq!(
            loaded.model_per_provider.get("beta").map(String::as_str),
            Some("ggml-small"),
        );
    }

    #[test]
    fn unknown_fields_are_dropped_on_rewrite() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("voice_provider.json");
        std::fs::write(
            &path,
            r#"{
                "active": "alpha",
                "model_per_provider": { "alpha": "ggml-base.en" },
                "future_field": "preserved-elsewhere"
            }"#,
        )
        .unwrap();

        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        r.attach_persistence(path.clone());
        r.set_active_model("ggml-small").unwrap();

        let on_disk = std::fs::read_to_string(&path).unwrap();
        assert!(
            !on_disk.contains("future_field"),
            "rewrite should drop unknown fields; file was: {on_disk}",
        );
        assert!(on_disk.contains("\"active\""));
        assert!(on_disk.contains("\"model_per_provider\""));
        assert!(on_disk.contains("ggml-small"));
    }

    #[test]
    fn malformed_json_falls_back_to_default_state() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("voice_provider.json");
        std::fs::write(&path, r#"{ "active": ["not", "a", "string"] }"#).unwrap();

        let loaded = load_persisted(&path);
        assert_eq!(loaded, VoicePersistedState::default());
    }

    #[test]
    fn old_persistence_without_model_map_still_loads() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("voice_provider.json");
        std::fs::write(&path, r#"{ "active": "alpha" }"#).unwrap();

        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new("alpha"));
        r.attach_persistence(path);
        assert_eq!(r.active_id().as_deref(), Some("alpha"));
        assert!(r.model_for("alpha").is_none());
    }

    #[test]
    fn seed_missing_models_writes_through_for_first_launch() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("voice_provider.json");

        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new_with_model("alpha", "alpha-env-model"));
        r.register(StubSpeech::new_with_model("beta", "beta-env-model"));
        r.attach_persistence(path.clone());
        r.auto_select_first_if_unset();

        assert!(r.model_for("alpha").is_none());
        assert!(r.model_for("beta").is_none());

        r.seed_missing_models_from_adapters().unwrap();
        assert_eq!(r.model_for("alpha").as_deref(), Some("alpha-env-model"));
        assert_eq!(r.model_for("beta").as_deref(), Some("beta-env-model"));

        let mut r2 = VoiceRegistry::empty();
        r2.register(StubSpeech::new_with_model("alpha", "irrelevant-default"));
        r2.register(StubSpeech::new_with_model("beta", "irrelevant-default"));
        r2.attach_persistence(path);
        assert_eq!(r2.active_id().as_deref(), Some("alpha"));
        assert_eq!(r2.active_model().as_deref(), Some("alpha-env-model"));
        assert_eq!(r2.model_for("beta").as_deref(), Some("beta-env-model"));
    }

    #[test]
    fn seed_missing_models_is_idempotent_after_user_pick() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("voice_provider.json");

        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new_with_model("alpha", "alpha-env"));
        r.attach_persistence(path);
        r.auto_select_first_if_unset();

        r.set_active_model("user-picked").unwrap();
        assert_eq!(r.model_for("alpha").as_deref(), Some("user-picked"));

        r.seed_missing_models_from_adapters().unwrap();
        assert_eq!(r.model_for("alpha").as_deref(), Some("user-picked"));
    }

    #[test]
    fn seed_missing_models_skips_providers_with_no_current_model() {
        struct PassiveSpeech;
        impl SpeechProvider for PassiveSpeech {
            fn id(&self) -> &str {
                "passive-speech"
            }
            fn label(&self) -> String {
                "passive".into()
            }
            fn healthcheck(&self) -> Result<(), L4Error> {
                Ok(())
            }
            fn transcribe(&self, _r: SpeechRequest) -> Result<SpeechResponse, L4Error> {
                Ok(SpeechResponse {
                    text: String::new(),
                    confidence: None,
                    prompt_tokens: None,
                    completion_tokens: None,
                })
            }
        }

        let mut r = VoiceRegistry::empty();
        r.register(Arc::new(PassiveSpeech) as Arc<dyn SpeechProvider>);
        r.seed_missing_models_from_adapters().unwrap();
        assert!(r.model_for("passive-speech").is_none());
    }

    #[test]
    fn seed_missing_models_skips_whitespace_only_models() {
        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new_with_model("blank", "   "));
        r.seed_missing_models_from_adapters().unwrap();
        assert!(r.model_for("blank").is_none());
    }

    #[test]
    fn seed_missing_models_no_op_when_persistence_unwired() {
        let mut r = VoiceRegistry::empty();
        r.register(StubSpeech::new_with_model("alpha", "alpha-env"));
        r.seed_missing_models_from_adapters().unwrap();
        assert_eq!(r.model_for("alpha").as_deref(), Some("alpha-env"));
    }

    #[test]
    fn voice_persistence_path_helper_lives_beside_app_data() {
        let dir = Path::new("/tmp/aether-test");
        let p = voice_persistence_path_for(dir);
        assert_eq!(p, Path::new("/tmp/aether-test/voice_provider.json"));
    }
}
