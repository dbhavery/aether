//! App-level shared state for the Tauri shell.
//!
//! Owns the currently-active compiled persona, memory store, policy
//! engine, turn engine, presence controller, and the pending-approval
//! registry that lets us split a turn across two IPC calls (submit →
//! resolve_approval) without holding an async wait inside a Tauri
//! command.
//!
//! The swappable engine pieces — compiled persona, turn engine, policy
//! engine, audit store, provider mode — live inside an `RwLock` so
//! `switch_persona` can rebuild them atomically without forcing every
//! command site to take a write lock.

use std::collections::{HashMap, VecDeque};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, RwLock};

use aether_l1_interaction::{TurnEngine, TurnRequest, TurnResult, TurnRouter};
use aether_l4_router::VisionProvider;

use crate::vision_cache::ModelListCache;
use crate::vision_registry::{VisionProviderInfo, VisionRegistry};
#[cfg(feature = "sqlite-backend")]
use aether_l2_memory::{DurableSessionStore, SqliteSessionMemoryStore};
use aether_l2_memory::{InMemorySessionMemoryStore, SessionMemoryStore};
use aether_l3_presence::{InMemoryPresenceController, PresenceController};
use aether_l5_policy::{
    policy_engine::PolicyEngine, AuditStore, AutonomyPreset, DefaultPolicyEngine, EngineConfig,
    InMemoryAuditStore, InMemoryGrantLedger, InMemorySink, PersonaId,
};
use aether_l6_persona::{load_pack_dir, CompiledPersona, DefaultPersonaCompiler, PersonaProfile};
use serde::Serialize;

use crate::adapter::{ModelRouterAdapter, ReflexModelRouter};
use crate::media_permissions::{self, CaptureGate, MediaKind, MediaPermissions, PermissionState};
use crate::memory_router::MemoryAwareRouter;
use crate::provider::ProviderMode;

/// The single active session id for v0. One conversation per app instance.
pub const SESSION_ID: &str = "desktop-session";

/// Default persona id used on boot when no explicit choice has been made.
pub const DEFAULT_PERSONA_ID: &str = "aurora";

/// Lightweight persona catalog entry — shown in the header picker. Not
/// the same as a compiled persona; this is just the "which persona
/// would you like?" menu surface.
#[derive(Debug, Clone, Serialize)]
pub struct PersonaCatalogEntry {
    pub id: String,
    pub name: String,
    pub tagline: String,
    pub stance: String,
    pub tone: String,
}

/// The active engine pieces that must rebuild when the persona changes.
/// Wrapped in `RwLock` on `AppState` so writers (persona switch) can
/// swap the whole tuple at once while readers (every command) take a
/// cheap shared lock.
pub struct ActiveEngine {
    pub compiled: CompiledPersona,
    pub persona_display_name: String,
    pub persona_tagline: String,
    pub policy: Arc<dyn PolicyEngine>,
    pub audit: Arc<dyn AuditStore>,
    pub engine: TurnEngine,
    pub provider_mode: ProviderMode,
    pub provider_label: String,
}

/// Application-wide shared state held in a Tauri `State<AppState>`.
pub struct AppState {
    /// Pre-defined personas available for runtime switching. Deliberately
    /// hard-coded rather than loaded from YAML — that's a later slice
    /// (persona-pack loader, per planning/17_persona_pack_schema.md).
    pub catalog: Vec<PersonaProfile>,
    pub presence: Arc<dyn PresenceController>,
    pub memory: Arc<dyn SessionMemoryStore>,
    pub active: RwLock<ActiveEngine>,
    ts: AtomicU64,
    pending: Mutex<HashMap<String, PendingTurn>>,
    #[allow(dead_code)] // Read via `memory_backend()` accessor and in tests.
    memory_backend: MemoryBackend,
    /// Current autonomy preset overlay. Applied after the persona
    /// overlay when `build_active` rebuilds the engine. `None` means the
    /// baseline Assistant behaviour is used — equivalent to the user
    /// having never picked, or explicitly deferring.
    preset: RwLock<Option<AutonomyPreset>>,
    /// Concrete typed handle to the SQLite-backed memory store, when
    /// the shell booted with the durable backend. Used for retention
    /// maintenance (explicit "Forget older than N days" surface)
    /// without downcasting the trait-object `memory`.
    #[cfg(feature = "sqlite-backend")]
    durable_store: Option<Arc<SqliteSessionMemoryStore>>,
    /// Ring buffer of recent-turn telemetry surfaced by the Trust
    /// drawer's History tab. Bounded to `TELEMETRY_BUFFER_CAPACITY`
    /// entries — this is a UX convenience, not a durable record.
    telemetry: Mutex<VecDeque<TelemetryEntry>>,
    /// Local-only media permission posture (camera + screen). Loaded
    /// from disk at boot when a `permissions_path` is configured;
    /// writes are persisted atomically via `persist_media_permissions`.
    media_permissions: RwLock<MediaPermissions>,
    /// Disk-backed location for `media_permissions`. `None` when the
    /// shell is running without a writable data dir (tests, sandboxes)
    /// — the in-memory copy still works, but changes do not survive
    /// restarts.
    media_permissions_path: Option<PathBuf>,
    /// Registry of zero or more vision-capable providers + the active
    /// selection. Replaces the v0 single-`Option` model so the user
    /// can swap providers at runtime (Ollama vision ↔ llama.cpp
    /// vision ↔ text-only fallback). The active selection is
    /// persisted via `vision_registry`'s attached file.
    vision: RwLock<VisionRegistry>,
    /// Short-TTL cache in front of each vision provider's
    /// `list_models`. Absorbs the burst of calls triggered by the
    /// camera/screen panels without re-hitting the daemon.
    vision_model_cache: ModelListCache,
}

/// Error surface for the cached vision model-list helpers. Lets the
/// Tauri command layer translate each case into a plain-language
/// message without leaking transport details.
#[derive(Debug, Clone)]
pub enum VisionModelListError {
    /// No vision provider is currently active (text-only mode).
    NoActive,
    /// The active provider's adapter returned an error when asked for
    /// its model list. Carries the provider id for UI annotation.
    Unavailable(String),
}

/// How many telemetry entries the shell retains for the History tab.
/// In-memory only; cleared on app restart. A durable telemetry log is
/// a separate concern and out of scope for this slice.
pub const TELEMETRY_BUFFER_CAPACITY: usize = 50;

/// One observable turn on the telemetry surface. `kind` distinguishes
/// normal completed turns from policy-blocked / denied turns so the UI
/// can colour them without re-parsing the content.
#[derive(Debug, Clone, Serialize)]
pub struct TelemetryEntry {
    /// Stable per-turn id (mirrors the transcript id).
    pub turn_id: String,
    /// Monotonic timestamp stamped by AppState::next_ts at record time.
    pub timestamp_ms: u64,
    /// High-level outcome — "completed" | "denied" | "needs_upgrade" |
    /// "draft_only" | "provider_error".
    pub kind: String,
    /// Persona id that served the turn.
    pub persona_id: String,
    /// Provider mode (e.g. "ollama", "reflex-stub") or None for blocks.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub provider: Option<String>,
    /// Tier the router chose.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tier: Option<String>,
    /// End-to-end latency in ms, if observed.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub latency_ms: Option<u64>,
    /// Prompt-side token count, if reported.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prompt_tokens: Option<u32>,
    /// Completion-side token count, if reported.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub completion_tokens: Option<u32>,
}

/// Which backend is behind `AppState::memory`. Used for diagnostics and
/// the optional dev-only debug surface — the engine never branches on it.
#[derive(Debug, Clone)]
#[allow(dead_code)] // Variants consumed via pattern-match in tests / logging.
pub enum MemoryBackend {
    /// Transient in-memory store; history is lost on restart.
    InMemory,
    /// SQLite-backed durable store at the given path.
    Durable {
        /// Absolute path to the SQLite file on disk.
        path: PathBuf,
    },
}

/// An Ask turn that is waiting on a UI approval. Holds enough state to
/// replay the turn after the user resolves the ticket.
pub struct PendingTurn {
    pub request: TurnRequest,
    pub ask_result: TurnResult,
}

impl AppState {
    /// In-memory constructor used by unit tests and any environment
    /// without a writable data directory. Mirrors the historical
    /// pre-durable-memory behaviour.
    pub fn new() -> Result<Self, String> {
        Self::build(
            Arc::new(InMemorySessionMemoryStore::new_default()) as Arc<dyn SessionMemoryStore>,
            MemoryBackend::InMemory,
        )
    }

    /// Construct the app state with an explicit persistence path for the
    /// durable session memory store. Falls back to the in-memory store
    /// (with a tracing::warn) if the path cannot be opened or migrations
    /// fail — the shell must still boot so the user sees a usable UI.
    #[cfg(feature = "sqlite-backend")]
    pub fn new_with_db_path(path: impl AsRef<Path>) -> Result<Self, String> {
        let path_ref = path.as_ref();
        if let Some(parent) = path_ref.parent() {
            if let Err(e) = std::fs::create_dir_all(parent) {
                tracing::warn!(
                    "could not create app data dir {}: {e}; using in-memory session store",
                    parent.display()
                );
                return Self::new();
            }
        }
        match DurableSessionStore::open(path_ref) {
            Ok(durable) => {
                tracing::info!("durable session memory opened at {}", path_ref.display());
                let concrete = durable.concrete();
                let mut state = Self::build(
                    durable.store.clone(),
                    MemoryBackend::Durable {
                        path: path_ref.to_path_buf(),
                    },
                )?;
                state.durable_store = concrete;
                Ok(state)
            }
            Err(e) => {
                tracing::warn!(
                    "durable session memory open failed at {}: {e}; using in-memory fallback",
                    path_ref.display()
                );
                Self::new()
            }
        }
    }

    /// Concrete durable-store handle for retention maintenance. `None`
    /// when the shell booted against the in-memory backend (tests or
    /// sandboxes that lack a writable data dir).
    #[cfg(feature = "sqlite-backend")]
    pub fn durable_store(&self) -> Option<Arc<SqliteSessionMemoryStore>> {
        self.durable_store.clone()
    }

    fn build(memory: Arc<dyn SessionMemoryStore>, backend: MemoryBackend) -> Result<Self, String> {
        let catalog = merge_yaml_personas(default_catalog());
        let presence: Arc<dyn PresenceController> = Arc::new(InMemoryPresenceController::new());
        let active = build_active(&pick_default(&catalog), memory.clone(), None)?;

        Ok(Self {
            catalog,
            presence,
            memory,
            active: RwLock::new(active),
            ts: AtomicU64::new(1_000),
            pending: Mutex::new(HashMap::new()),
            memory_backend: backend,
            preset: RwLock::new(None),
            #[cfg(feature = "sqlite-backend")]
            durable_store: None,
            telemetry: Mutex::new(VecDeque::with_capacity(TELEMETRY_BUFFER_CAPACITY)),
            media_permissions: RwLock::new(MediaPermissions::defaults()),
            media_permissions_path: None,
            vision: RwLock::new(VisionRegistry::empty()),
            vision_model_cache: ModelListCache::new(),
        })
    }

    /// Register a vision-capable provider into the registry. Called
    /// from `build_app_state` in main.rs for each provider whose
    /// boot-time healthcheck passed. Order matters — first registered
    /// is the fallback when persisted state names an unknown id.
    #[allow(dead_code)] // Wired only behind provider features in main.rs.
    pub fn register_vision_provider(&self, provider: Arc<dyn VisionProvider>) {
        let mut w = self.vision.write().expect("vision registry write lock");
        w.register(provider);
    }

    /// Wire the on-disk persistence file for the active vision-provider
    /// selection. Loads the persisted state (with safe fallbacks).
    #[allow(dead_code)] // Wired only behind provider features in main.rs.
    pub fn attach_vision_persistence(&self, path: PathBuf) {
        let mut w = self.vision.write().expect("vision registry write lock");
        w.attach_persistence(path);
    }

    /// Auto-select the first registered provider if no active id was
    /// loaded from persistence. No-op when an active id is already set.
    #[allow(dead_code)] // Wired only behind provider features in main.rs.
    pub fn vision_auto_select_if_unset(&self) {
        let r = self.vision.read().expect("vision registry read lock");
        r.auto_select_first_if_unset();
    }

    /// Cheap clone of the active vision provider handle. `None` when
    /// no provider is selected (text-only mode) or the registry is
    /// empty — `analyze_frame` uses the absence as a signal to fall
    /// back to its text-only path.
    pub fn vision_provider(&self) -> Option<Arc<dyn VisionProvider>> {
        let r = self.vision.read().expect("vision registry read lock");
        r.active()
    }

    /// Active provider id (`"ollama-vision"` / `"llamacpp-vision"`),
    /// if any. Surfaced via the `vision_status` Tauri command.
    pub fn vision_active_id(&self) -> Option<String> {
        let r = self.vision.read().expect("vision registry read lock");
        r.active_id()
    }

    /// Human-readable label for the active vision provider, if any.
    pub fn vision_provider_label(&self) -> Option<String> {
        let r = self.vision.read().expect("vision registry read lock");
        r.active_label()
    }

    /// Snapshot of every registered vision provider plus an `active`
    /// flag. Surfaced via the `list_vision_providers` Tauri command.
    pub fn vision_provider_list(&self) -> Vec<VisionProviderInfo> {
        let r = self.vision.read().expect("vision registry read lock");
        r.list()
    }

    /// Set the active vision provider by id. `None` switches to
    /// text-only mode. Persists when a file is wired.
    pub fn set_active_vision_provider(&self, id: Option<String>) -> Result<(), String> {
        let r = self.vision.read().expect("vision registry read lock");
        let outcome = r.set_active(id.clone());
        // Provider swap can change what the model list *means* for the
        // active slot; drop the incoming provider's entry so the next
        // lookup is fresh. We intentionally don't clear the whole
        // cache — other providers' entries stay valid.
        if let Some(id) = id.as_deref() {
            self.vision_model_cache.invalidate(id);
        }
        outcome
    }

    /// Cached model list for the active vision provider. First call
    /// (or call after invalidate / TTL expiry) hits the daemon; later
    /// calls within the TTL return the cached snapshot.
    ///
    /// Returns `(provider_id, models)` so the caller can construct the
    /// VisionModelList envelope without a second registry lookup.
    pub fn vision_model_list_cached(
        &self,
    ) -> Result<(String, Vec<String>), VisionModelListError> {
        let Some(provider) = self.vision_provider() else {
            return Err(VisionModelListError::NoActive);
        };
        let id = provider.id().to_string();
        if let Some(cached) = self.vision_model_cache.get(&id) {
            return Ok((id, cached));
        }
        match provider.list_models() {
            Ok(models) => {
                self.vision_model_cache.put(&id, models.clone());
                Ok((id, models))
            }
            Err(_) => Err(VisionModelListError::Unavailable(id)),
        }
    }

    /// Force a fresh fetch of the active provider's model list,
    /// bypassing the cache. Wired to the manual `refresh_vision_models`
    /// command so the UI can show the user's newly-pulled model
    /// without waiting for TTL expiry.
    pub fn vision_model_list_refresh(&self) -> Result<(String, Vec<String>), VisionModelListError> {
        let Some(provider) = self.vision_provider() else {
            return Err(VisionModelListError::NoActive);
        };
        let id = provider.id().to_string();
        self.vision_model_cache.invalidate(&id);
        match provider.list_models() {
            Ok(models) => {
                self.vision_model_cache.put(&id, models.clone());
                Ok((id, models))
            }
            Err(_) => Err(VisionModelListError::Unavailable(id)),
        }
    }

    /// Current model id of the active vision provider, if any.
    pub fn vision_active_model(&self) -> Option<String> {
        let r = self.vision.read().expect("vision registry read lock");
        r.active_model()
    }

    /// Switch the model used by the active vision provider. Persists
    /// alongside the active-provider selection so a future provider
    /// swap restores the same pick. Errors when no provider is active
    /// or the adapter rejects the id. Invalidates the model-list
    /// cache for the active provider so the next `list_vision_models`
    /// sees the new pick without waiting for TTL expiry.
    pub fn set_active_vision_model(&self, model: &str) -> Result<(), String> {
        let active = self.vision_active_id();
        let outcome = {
            let r = self.vision.read().expect("vision registry read lock");
            r.set_active_model(model)
        };
        if let Some(id) = active {
            self.vision_model_cache.invalidate(&id);
        }
        outcome
    }

    /// Wire a disk-backed media-permissions file into this state. Loads
    /// the current contents (or falls back to defaults if the file is
    /// missing/malformed) and remembers the path so subsequent writes
    /// persist atomically.
    pub fn attach_media_permissions_file(&mut self, path: PathBuf) {
        let loaded = media_permissions::load_or_default(&path);
        *self.media_permissions.write().expect("perm write lock") = loaded;
        self.media_permissions_path = Some(path);
    }

    /// Snapshot the current media permissions. Cheap clone; safe to
    /// hand to a Tauri command response.
    pub fn media_permissions(&self) -> MediaPermissions {
        *self.media_permissions.read().expect("perm read lock")
    }

    /// Update one device's permission and persist the new state to
    /// disk if a path is wired. Returns the resulting full snapshot
    /// so the caller can echo it back to the UI in one round trip.
    ///
    /// Persistence failures are surfaced as `Err` so the UI can show
    /// the user the change did not stick — silent partial success
    /// would let a denied permission look like it stuck across a
    /// restart when it actually did not.
    pub fn set_media_permission(
        &self,
        kind: MediaKind,
        state: PermissionState,
    ) -> Result<MediaPermissions, String> {
        let snapshot = {
            let mut w = self.media_permissions.write().expect("perm write lock");
            w.set(kind, state);
            *w
        };
        if let Some(path) = &self.media_permissions_path {
            media_permissions::save(path, &snapshot)
                .map_err(|e| format!("persist media permissions: {e}"))?;
        }
        Ok(snapshot)
    }

    /// Pre-capture gate. Future camera/screen capture sites must call
    /// this before touching the device — it never starts capture
    /// itself. See [`media_permissions::CaptureGate`] for the action
    /// the caller should take.
    pub fn evaluate_media_permission(&self, kind: MediaKind) -> CaptureGate {
        self.media_permissions().evaluate(kind)
    }

    /// Record a telemetry entry. Evicts the oldest entry if the buffer
    /// is at capacity. Never errors; poisoned locks fall back to a
    /// no-op with a tracing warning because telemetry is UX-only.
    pub fn record_telemetry(&self, entry: TelemetryEntry) {
        match self.telemetry.lock() {
            Ok(mut g) => {
                if g.len() == TELEMETRY_BUFFER_CAPACITY {
                    g.pop_front();
                }
                g.push_back(entry);
            }
            Err(e) => {
                tracing::warn!("telemetry lock poisoned: {e}; entry dropped");
            }
        }
    }

    /// Snapshot of the newest-first telemetry entries, capped at
    /// `limit`. Returns a clone so the webview sees a frozen view.
    pub fn telemetry_recent(&self, limit: usize) -> Vec<TelemetryEntry> {
        let Ok(g) = self.telemetry.lock() else {
            return Vec::new();
        };
        g.iter().rev().take(limit).cloned().collect()
    }

    /// Wipe the telemetry buffer. Used by the UI's "Clear history" on
    /// the trust drawer History tab; does NOT touch the audit log.
    pub fn clear_telemetry(&self) {
        if let Ok(mut g) = self.telemetry.lock() {
            g.clear();
        }
    }

    /// Current autonomy preset, or `None` if the user has not chosen or
    /// deferred. Exposed for commands and diagnostics.
    pub fn current_preset(&self) -> Option<AutonomyPreset> {
        *self.preset.read().expect("preset read lock")
    }

    /// Apply a new autonomy preset (or clear it with `None`) and rebuild
    /// the active engine so the change takes effect immediately. Keeps
    /// the current persona; does NOT clear session memory — preset
    /// changes are non-destructive.
    pub fn apply_preset(&self, preset: Option<AutonomyPreset>) -> Result<(), String> {
        {
            let mut w = self.preset.write().expect("preset write lock");
            *w = preset;
        }
        let profile = {
            let active = self.active.read().expect("active read lock");
            self.catalog
                .iter()
                .find(|p| p.persona_id.0 == active.compiled.persona_id.0)
                .cloned()
                .ok_or_else(|| "active persona missing from catalog".to_string())?
        };
        let new_active = build_active(&profile, self.memory.clone(), preset)?;
        let mut w = self.active.write().expect("active write lock");
        *w = new_active;
        Ok(())
    }

    /// Identify which backend is providing session memory. Exposed for
    /// diagnostics and logging, not for routing decisions.
    pub fn memory_backend(&self) -> &MemoryBackend {
        &self.memory_backend
    }

    /// Monotonic millisecond counter for stamp fields. Not a wall clock;
    /// stable within one process run.
    pub fn next_ts(&self) -> u64 {
        self.ts.fetch_add(1, Ordering::Relaxed)
    }

    pub fn record_pending(&self, ticket_id: String, pending: PendingTurn) {
        let mut g = self.pending.lock().expect("pending lock");
        g.insert(ticket_id, pending);
    }

    pub fn take_pending(&self, ticket_id: &str) -> Option<PendingTurn> {
        let mut g = self.pending.lock().expect("pending lock");
        g.remove(ticket_id)
    }

    /// Drop session state (memory, presence, pending). Engine + policy
    /// retain grants / audit for now — a "new session" feels clean to the
    /// user without wiping the trust ledger.
    pub fn clear_session(&self) -> Result<(), String> {
        self.memory
            .clear_session(SESSION_ID)
            .map_err(|e| format!("memory clear: {e}"))?;
        self.presence
            .clear_session(SESSION_ID)
            .map_err(|e| format!("presence clear: {e}"))?;
        let mut g = self.pending.lock().expect("pending lock");
        g.clear();
        Ok(())
    }

    /// List the available personas in catalog order.
    pub fn catalog_entries(&self) -> Vec<PersonaCatalogEntry> {
        self.catalog.iter().map(profile_to_entry).collect()
    }

    /// Swap the active persona. Clears session state (memory, presence,
    /// pending approvals) and rebuilds the engine / policy / audit
    /// against the new persona's defaults. Audit chain is reset because
    /// a different persona is a different trust surface.
    pub fn switch_persona(&self, id: &str) -> Result<(), String> {
        let profile = self
            .catalog
            .iter()
            .find(|p| p.persona_id.0 == id)
            .ok_or_else(|| format!("unknown persona: {id}"))?
            .clone();
        let preset = self.current_preset();
        let new_active = build_active(&profile, self.memory.clone(), preset)?;
        self.clear_session()?;
        let mut w = self.active.write().expect("active write lock");
        *w = new_active;
        Ok(())
    }
}

fn pick_default(catalog: &[PersonaProfile]) -> PersonaProfile {
    let want = std::env::var("AETHER_PERSONA").unwrap_or_else(|_| DEFAULT_PERSONA_ID.to_string());
    catalog
        .iter()
        .find(|p| p.persona_id.0 == want)
        .cloned()
        .unwrap_or_else(|| catalog[0].clone())
}

fn profile_to_entry(p: &PersonaProfile) -> PersonaCatalogEntry {
    PersonaCatalogEntry {
        id: p.persona_id.0.clone(),
        name: p.name.clone(),
        tagline: p.description.clone(),
        stance: stance_label(p.stance),
        tone: tone_label(p.tone),
    }
}

fn stance_label(s: aether_l6_persona::Stance) -> String {
    use aether_l6_persona::Stance::*;
    match s {
        Cautious => "cautious",
        Balanced => "balanced",
        Bold => "bold",
    }
    .to_string()
}

fn tone_label(t: aether_l6_persona::Tone) -> String {
    use aether_l6_persona::Tone::*;
    match t {
        Warm => "warm",
        Neutral => "neutral",
        Formal => "formal",
    }
    .to_string()
}

/// Build every swappable engine piece for the given profile.
fn build_active(
    profile: &PersonaProfile,
    memory: Arc<dyn SessionMemoryStore>,
    preset: Option<AutonomyPreset>,
) -> Result<ActiveEngine, String> {
    let persona_display_name = profile.name.clone();
    let persona_tagline = profile.description.clone();
    let compiled = DefaultPersonaCompiler::new()
        .compile(profile)
        .map_err(|e| format!("persona compile: {e}"))?;

    let persona_id = PersonaId(compiled.persona_id.0.clone());
    let mut cfg = EngineConfig::wave3_default(persona_id).with_persona_overlay(
        &compiled.policy_defaults.per_capability_defaults,
        compiled.policy_defaults.privacy_posture,
    );
    if let Some(p) = preset {
        cfg = cfg.with_preset_overlay(p);
    }
    let audit: Arc<dyn AuditStore> = Arc::new(InMemoryAuditStore::new());
    let policy: Arc<dyn PolicyEngine> = Arc::new(DefaultPolicyEngine::new(
        cfg,
        Arc::new(InMemoryGrantLedger::new()),
        audit.clone(),
        Arc::new(InMemorySink::new()),
    ));

    let (router, provider_mode, provider_label) = build_router_stack(&compiled, memory);
    let engine = TurnEngine::new(policy.clone(), router);

    Ok(ActiveEngine {
        compiled,
        persona_display_name,
        persona_tagline,
        policy,
        audit,
        engine,
        provider_mode,
        provider_label,
    })
}

/// Resolve the persona-pack directory the shell should scan for YAML
/// persona files. Order:
///
/// 1. `AETHER_PERSONAS_DIR` environment variable (absolute path).
/// 2. The OS-native app data dir + `/personas/` (see
///    `build_app_state` in main.rs; when the AppState is constructed
///    outside Tauri, e.g. tests, this falls back to `None`).
///
/// Returning `None` means "no pack dir configured" — the loader
/// treats that as "empty pack set" so boot never fails on absence.
fn persona_pack_dir() -> Option<std::path::PathBuf> {
    if let Ok(custom) = std::env::var("AETHER_PERSONAS_DIR") {
        if !custom.trim().is_empty() {
            return Some(std::path::PathBuf::from(custom));
        }
    }
    None
}

/// Enrich the built-in catalog with persona profiles loaded from YAML
/// pack files. YAML personas are **additive-only** — a file declaring
/// an id already present in the built-in catalog is skipped with a
/// tracing WARN. This keeps the first-launch shell predictable even
/// when an experimental YAML file is dropped in.
fn merge_yaml_personas(mut catalog: Vec<PersonaProfile>) -> Vec<PersonaProfile> {
    let Some(dir) = persona_pack_dir() else {
        return catalog;
    };
    match load_pack_dir(&dir) {
        Ok(extras) => {
            for profile in extras {
                if catalog.iter().any(|p| p.persona_id == profile.persona_id) {
                    tracing::warn!(
                        "persona pack id {:?} collides with a built-in persona; YAML entry skipped",
                        profile.persona_id.0
                    );
                    continue;
                }
                tracing::info!(
                    "loaded persona pack {:?} from {}",
                    profile.persona_id.0,
                    dir.display()
                );
                catalog.push(profile);
            }
        }
        Err(e) => {
            tracing::warn!(
                "persona pack dir {} failed to load: {e}; continuing with built-ins only",
                dir.display()
            );
        }
    }
    catalog
}

/// Hard-coded persona catalog. Three voices to start: Aurora (warm /
/// balanced), Sable (neutral / bold), and Ember (formal / cautious).
/// YAML-defined personas are merged on top by `merge_yaml_personas`
/// per `planning/17_persona_pack_schema.md`.
fn default_catalog() -> Vec<PersonaProfile> {
    use aether_l6_persona::{Humor, Stance, Tone, Verbosity};

    let mut aurora = PersonaProfile::simple("aurora", "Aurora");
    aurora.description = String::from(
        "Warm and grounded. A calm presence for focused work. Local-first by default.",
    );
    aurora.tone = Tone::Warm;
    aurora.verbosity = Verbosity::Balanced;
    aurora.stance = Stance::Balanced;
    aurora.humor = Humor::Occasional;

    let mut sable = PersonaProfile::simple("sable", "Sable");
    sable.description = String::from(
        "Direct and decisive. Moves fast, auto-approves low-risk moves, still asks before touching anything sharp.",
    );
    sable.tone = Tone::Neutral;
    sable.verbosity = Verbosity::Terse;
    sable.stance = Stance::Bold;
    sable.humor = Humor::Dry;

    let mut ember = PersonaProfile::simple("ember", "Ember");
    ember.description = String::from(
        "Careful and deliberate. Asks before acting, prefers the safer path, declines risky tools.",
    );
    ember.tone = Tone::Formal;
    ember.verbosity = Verbosity::Balanced;
    ember.stance = Stance::Cautious;
    ember.humor = Humor::Dry;

    vec![aurora, sable, ember]
}

fn build_router_stack(
    compiled: &CompiledPersona,
    memory: Arc<dyn SessionMemoryStore>,
) -> (Arc<dyn TurnRouter>, ProviderMode, String) {
    #[cfg(feature = "ollama-provider")]
    {
        use aether_l4_router::{OllamaConfig, OllamaProvider};
        if OllamaConfig::env_opts_in() {
            match OllamaConfig::from_env() {
                Ok(cfg) => {
                    let provider = OllamaProvider::new(cfg.clone());
                    if provider.healthcheck().is_ok() {
                        let tier =
                            crate::provider::tier_from_rules(&compiled.routing.preferred_tier);
                        let tier_label = crate::provider::tier_label(tier).to_string();
                        let label = format!("Ollama · {} · {}", cfg.model, cfg.base_url);
                        let router: Arc<dyn TurnRouter> =
                            Arc::new(crate::memory_router::RoleTaggedOllamaRouter::new(
                                provider,
                                memory,
                                SESSION_ID,
                                compiled.prompts.system.clone(),
                                tier_label,
                                "ollama".to_string(),
                            ));
                        return (router, ProviderMode::Ollama, label);
                    }
                }
                Err(e) => {
                    tracing::warn!("Ollama config error: {e}; falling back to reflex stub");
                }
            }
        }
    }
    let tier = crate::provider::tier_from_rules(&compiled.routing.preferred_tier);
    let adapter = ModelRouterAdapter::new(ReflexModelRouter::new(), "reflex-stub", tier);
    let router: Arc<dyn TurnRouter> = Arc::new(MemoryAwareRouter::new(adapter, memory, SESSION_ID));
    (
        router,
        ProviderMode::ReflexStub,
        "Reflex stub (no model)".to_string(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use aether_l1_interaction::TurnState;
    use aether_l5_policy::{
        Capability, Decision, MonotonicTimestamp, PersonaId, ResourceScope, SessionId,
    };
    use aether_l6_persona::Stance;
    use aether_l7_trust::{build_approval_response, ApprovalResolution};

    #[test]
    fn default_catalog_contains_expected_persona_ids() {
        let cat = default_catalog();
        let ids: Vec<&str> = cat.iter().map(|p| p.persona_id.0.as_str()).collect();
        assert_eq!(ids, vec!["aurora", "sable", "ember"]);
    }

    #[test]
    fn ember_is_the_cautious_persona() {
        let cat = default_catalog();
        let ember = cat.iter().find(|p| p.persona_id.0 == "ember").unwrap();
        assert_eq!(ember.stance, Stance::Cautious);
        assert_eq!(ember.name, "Ember");
    }

    /// End-to-end cycle covering the same path `submit_turn` →
    /// `resolve_approval` drives in commands.rs:
    ///
    ///   1. build a TurnRequest for an Ask-tier capability (FilesEdit),
    ///   2. handle_turn → Ask decision → record PendingTurn,
    ///   3. respond_approval(Approve) on L5,
    ///   4. replay the stored request → Allow → route populated.
    ///
    /// The Tauri command wrappers around this logic are thin; the
    /// substance is this engine cycle.
    #[test]
    fn ask_approve_cycle_reaches_router_on_replay() {
        let state = AppState::new().expect("AppState::new");
        let req = TurnRequest {
            session_id: SessionId(SESSION_ID.into()),
            persona: PersonaId("aurora".into()),
            task_id: None,
            utterance: "edit /tmp/x".into(),
            capability: Capability::FilesEdit,
            resource: ResourceScope::Path("/tmp/x".into()),
            emitted_at: MonotonicTimestamp(state.next_ts()),
        };

        // Step 1 — first handle_turn: should Ask.
        let ask_result = {
            let a = state.active.read().unwrap();
            a.engine.handle_turn(req.clone()).unwrap()
        };
        assert_eq!(ask_result.final_state, TurnState::AwaitingPolicyApproval);
        let ticket = match &ask_result.policy_decision {
            Decision::Ask { ticket, .. } => ticket.clone(),
            other => panic!("expected Ask, got {other:?}"),
        };
        state.record_pending(
            ticket.ticket_id.0.clone(),
            PendingTurn {
                request: req.clone(),
                ask_result: ask_result.clone(),
            },
        );

        // Step 2 — user approves. Respond via L7 helper so we build the
        // same ApprovalResponse shape commands.rs builds.
        let response = build_approval_response(
            &ticket,
            ApprovalResolution::Approve,
            MonotonicTimestamp(state.next_ts()),
        );
        {
            let a = state.active.read().unwrap();
            a.policy.respond_approval(response).unwrap();
        }

        // Step 3 — pending retrieval should consume the entry.
        let pending = state
            .take_pending(&ticket.ticket_id.0)
            .expect("pending ticket");
        assert!(state.take_pending(&ticket.ticket_id.0).is_none());

        // Step 4 — replay. Should now Allow and carry a RouteOutcome.
        let final_result = {
            let a = state.active.read().unwrap();
            a.engine.handle_turn(pending.request).unwrap()
        };
        assert_eq!(final_result.final_state, TurnState::Completed);
        assert!(matches!(
            final_result.policy_decision,
            Decision::Allow { .. }
        ));
        let route = final_result.route.expect("route after approval");
        assert!(!route.response_text.is_empty());
        assert!(
            route.latency_ms.is_some(),
            "TurnEngine::handle_turn should stamp latency on replay too",
        );
    }

    /// Complementary path: a rejection should leave the engine able to
    /// safely continue accepting new turns (no lingering pending state).
    #[test]
    fn ask_reject_clears_pending_and_engine_remains_usable() {
        let state = AppState::new().expect("AppState::new");
        let req = TurnRequest {
            session_id: SessionId(SESSION_ID.into()),
            persona: PersonaId("aurora".into()),
            task_id: None,
            utterance: "edit /tmp/y".into(),
            capability: Capability::FilesEdit,
            resource: ResourceScope::Path("/tmp/y".into()),
            emitted_at: MonotonicTimestamp(state.next_ts()),
        };
        let ask = {
            let a = state.active.read().unwrap();
            a.engine.handle_turn(req.clone()).unwrap()
        };
        let ticket = match &ask.policy_decision {
            Decision::Ask { ticket, .. } => ticket.clone(),
            other => panic!("expected Ask, got {other:?}"),
        };
        state.record_pending(
            ticket.ticket_id.0.clone(),
            PendingTurn {
                request: req,
                ask_result: ask,
            },
        );

        // Reject via the same helper flow commands.rs uses.
        let response = build_approval_response(
            &ticket,
            ApprovalResolution::Reject,
            MonotonicTimestamp(state.next_ts()),
        );
        {
            let a = state.active.read().unwrap();
            a.policy.respond_approval(response).unwrap();
        }
        assert!(state.take_pending(&ticket.ticket_id.0).is_some());
        assert!(state.take_pending(&ticket.ticket_id.0).is_none());

        // Engine should still service a fresh Allow-tier turn afterwards.
        let follow_up = TurnRequest {
            session_id: SessionId(SESSION_ID.into()),
            persona: PersonaId("aurora".into()),
            task_id: None,
            utterance: "read /tmp/z".into(),
            capability: Capability::FilesRead,
            resource: ResourceScope::Path("/tmp/z".into()),
            emitted_at: MonotonicTimestamp(state.next_ts()),
        };
        let follow = {
            let a = state.active.read().unwrap();
            a.engine.handle_turn(follow_up).unwrap()
        };
        assert_eq!(follow.final_state, TurnState::Completed);
    }

    /// End-to-end durable round-trip: build an AppState over a temp
    /// SQLite file, drive turns into memory, drop the AppState, reopen
    /// a new AppState over the same file, and verify the prior turns
    /// come back. This is the integration guarantee P1 exists to give.
    #[cfg(feature = "sqlite-backend")]
    #[test]
    fn durable_memory_survives_appstate_reopen() {
        use aether_l2_memory::{MemoryRole, TurnMemoryRecord};
        use tempfile::TempDir;

        let tmp = TempDir::new().expect("tempdir");
        let db_path = tmp.path().join("subdir").join("aether.db");

        {
            let state = AppState::new_with_db_path(&db_path).expect("first AppState");
            assert!(matches!(
                state.memory_backend(),
                MemoryBackend::Durable { .. }
            ));
            state
                .memory
                .append(TurnMemoryRecord {
                    session_id: SESSION_ID.to_string(),
                    sequence: 0,
                    role: MemoryRole::User,
                    content: "hello across restarts".to_string(),
                    timestamp_ms: 100,
                })
                .unwrap();
            state
                .memory
                .append(TurnMemoryRecord {
                    session_id: SESSION_ID.to_string(),
                    sequence: 0,
                    role: MemoryRole::Assistant,
                    content: "remembered".to_string(),
                    timestamp_ms: 200,
                })
                .unwrap();
        }

        let state2 = AppState::new_with_db_path(&db_path).expect("second AppState");
        let w = state2.memory.recent(SESSION_ID).unwrap();
        assert_eq!(w.records.len(), 2);
        assert_eq!(w.records[0].content, "hello across restarts");
        assert_eq!(w.records[1].content, "remembered");
        assert!(matches!(
            state2.memory_backend(),
            MemoryBackend::Durable { .. }
        ));
    }

    #[test]
    fn telemetry_ring_buffer_evicts_oldest_and_returns_newest_first() {
        let state = AppState::new().unwrap();
        // Push more than capacity so eviction triggers.
        for i in 0..(TELEMETRY_BUFFER_CAPACITY + 5) {
            state.record_telemetry(TelemetryEntry {
                turn_id: format!("t-{i}"),
                timestamp_ms: (i as u64) * 10,
                kind: "completed".into(),
                persona_id: "aurora".into(),
                provider: Some("reflex-stub".into()),
                tier: Some("local".into()),
                latency_ms: Some(100 + i as u64),
                prompt_tokens: None,
                completion_tokens: None,
            });
        }
        let all = state.telemetry_recent(TELEMETRY_BUFFER_CAPACITY);
        assert_eq!(all.len(), TELEMETRY_BUFFER_CAPACITY);
        // Newest-first: first element is the last we pushed.
        assert_eq!(
            all[0].turn_id,
            format!("t-{}", TELEMETRY_BUFFER_CAPACITY + 4)
        );
        // Oldest entries (t-0..t-4) must have been evicted.
        assert!(all.iter().all(|e| !e.turn_id.ends_with("-0")
            || e.turn_id == format!("t-{}", TELEMETRY_BUFFER_CAPACITY + 0)));

        // Limit clamps correctly.
        let five = state.telemetry_recent(5);
        assert_eq!(five.len(), 5);
        assert_eq!(
            five[0].turn_id,
            format!("t-{}", TELEMETRY_BUFFER_CAPACITY + 4)
        );
    }

    /// When `AETHER_PERSONAS_DIR` points at a directory containing a
    /// YAML persona pack, `AppState::new()` should surface that persona
    /// alongside the built-ins.
    ///
    /// This test sets a process-wide env var, so it's intentionally
    /// serialised via a file-scoped mutex to avoid clobbering other
    /// tests that might read the same var in parallel. (Rust's test
    /// runner runs tests in-process but threaded.)
    #[test]
    fn yaml_persona_pack_merges_into_catalog() {
        use std::sync::Mutex;
        static ENV_LOCK: Mutex<()> = Mutex::new(());
        let _g = ENV_LOCK.lock().unwrap();

        let tmp = tempfile::TempDir::new().unwrap();
        let yaml = r#"
id: "solstice"
version: 1
name: "Solstice"
description: "A steady hand loaded from YAML."
tone: "warm"
verbosity: "balanced"
stance: "balanced"
humor: "dry"
"#;
        std::fs::write(tmp.path().join("solstice.yaml"), yaml).unwrap();

        std::env::set_var("AETHER_PERSONAS_DIR", tmp.path());
        let state = AppState::new().expect("AppState::new");
        std::env::remove_var("AETHER_PERSONAS_DIR");

        let ids: Vec<String> = state.catalog_entries().into_iter().map(|e| e.id).collect();
        assert!(ids.contains(&"aurora".to_string()));
        assert!(
            ids.contains(&"solstice".to_string()),
            "YAML persona should appear in catalog; saw {ids:?}"
        );
    }

    #[test]
    fn yaml_persona_id_collision_with_builtin_is_skipped() {
        use std::sync::Mutex;
        static ENV_LOCK: Mutex<()> = Mutex::new(());
        let _g = ENV_LOCK.lock().unwrap();

        let tmp = tempfile::TempDir::new().unwrap();
        // Try to override `aurora` from YAML — must be rejected.
        let yaml = r#"
id: "aurora"
version: 99
name: "Rogue Aurora"
description: "Should not replace the built-in."
tone: "formal"
verbosity: "terse"
stance: "bold"
humor: "playful"
"#;
        std::fs::write(tmp.path().join("rogue.yaml"), yaml).unwrap();

        std::env::set_var("AETHER_PERSONAS_DIR", tmp.path());
        let state = AppState::new().expect("AppState::new");
        std::env::remove_var("AETHER_PERSONAS_DIR");

        let entries = state.catalog_entries();
        let aurora = entries.iter().find(|e| e.id == "aurora").unwrap();
        assert_eq!(
            aurora.name, "Aurora",
            "built-in persona must not be replaced by a colliding YAML id",
        );
    }

    #[test]
    fn telemetry_clear_empties_buffer() {
        let state = AppState::new().unwrap();
        state.record_telemetry(TelemetryEntry {
            turn_id: "x".into(),
            timestamp_ms: 1,
            kind: "completed".into(),
            persona_id: "aurora".into(),
            provider: None,
            tier: None,
            latency_ms: None,
            prompt_tokens: None,
            completion_tokens: None,
        });
        assert_eq!(state.telemetry_recent(10).len(), 1);
        state.clear_telemetry();
        assert_eq!(state.telemetry_recent(10).len(), 0);
    }

    /// Booting against a real DB file populates the `durable_store`
    /// handle, and `prune_older_than` on that handle removes exactly
    /// the rows whose timestamps fall below the cutoff.
    #[cfg(feature = "sqlite-backend")]
    #[test]
    fn durable_store_prune_older_than_removes_only_old_rows() {
        use aether_l2_memory::{MemoryRole, TurnMemoryRecord};
        use tempfile::TempDir;

        let tmp = TempDir::new().unwrap();
        let state = AppState::new_with_db_path(tmp.path().join("aether.db")).unwrap();
        let store = state.durable_store().expect("durable_store available");

        // Seed four rows with controlled timestamps.
        for (content, ts) in [
            ("old-1", 1_000),
            ("old-2", 2_000),
            ("new-1", 9_000),
            ("new-2", 10_000),
        ] {
            state
                .memory
                .append(TurnMemoryRecord {
                    session_id: SESSION_ID.to_string(),
                    sequence: 0,
                    role: MemoryRole::User,
                    content: content.into(),
                    timestamp_ms: ts,
                })
                .unwrap();
        }

        // Cutoff = 5_000 → removes the two `old-*` rows.
        let removed = store.prune_older_than(SESSION_ID, 5_000).unwrap();
        assert_eq!(removed, 2);

        let w = state.memory.recent(SESSION_ID).unwrap();
        let texts: Vec<&str> = w.records.iter().map(|r| r.content.as_str()).collect();
        assert_eq!(texts, vec!["new-1", "new-2"]);
    }

    /// Applying the Observer preset must force write capabilities to
    /// Deny even on a Bold persona (Sable) that would normally leave
    /// them Ask/Auto. The overlay is the last word.
    #[test]
    fn apply_preset_observer_denies_write_capabilities() {
        let state = AppState::new().expect("AppState::new");
        state.switch_persona("sable").unwrap();

        state
            .apply_preset(Some(AutonomyPreset::Observer))
            .expect("apply observer preset");
        assert_eq!(state.current_preset(), Some(AutonomyPreset::Observer));

        // Drive a FilesEdit turn: under Observer the engine should Deny
        // rather than Ask.
        let req = TurnRequest {
            session_id: SessionId(SESSION_ID.into()),
            persona: PersonaId("sable".into()),
            task_id: None,
            utterance: "edit /tmp/observer".into(),
            capability: Capability::FilesEdit,
            resource: ResourceScope::Path("/tmp/observer".into()),
            emitted_at: MonotonicTimestamp(state.next_ts()),
        };
        let res = {
            let a = state.active.read().unwrap();
            a.engine.handle_turn(req).unwrap()
        };
        assert!(
            matches!(res.policy_decision, Decision::Deny { .. }),
            "observer preset should deny FilesEdit, got {:?}",
            res.policy_decision
        );

        // Clearing the overlay restores baseline (Sable hints Auto here;
        // at minimum we should stop Denying).
        state.apply_preset(None).unwrap();
        assert_eq!(state.current_preset(), None);
    }

    /// Observer preset must survive a persona switch — switching persona
    /// should re-apply the current preset overlay, not silently drop it.
    #[test]
    fn preset_persists_across_persona_switch() {
        let state = AppState::new().expect("AppState::new");
        state.apply_preset(Some(AutonomyPreset::Observer)).unwrap();
        state.switch_persona("ember").unwrap();
        assert_eq!(state.current_preset(), Some(AutonomyPreset::Observer));
    }

    /// AppState boots with both media permissions in `Ask` and reports
    /// `PromptUser` from the capture gate — the safe default.
    #[test]
    fn media_permissions_default_to_ask_after_boot() {
        let state = AppState::new().unwrap();
        let perms = state.media_permissions();
        assert_eq!(perms.camera, PermissionState::Ask);
        assert_eq!(perms.screen, PermissionState::Ask);
        assert_eq!(
            state.evaluate_media_permission(MediaKind::Camera),
            CaptureGate::PromptUser
        );
        assert_eq!(
            state.evaluate_media_permission(MediaKind::Screen),
            CaptureGate::PromptUser
        );
    }

    /// `set_media_permission` updates the in-memory snapshot and shifts
    /// the capture gate accordingly. Without an attached file it is a
    /// pure in-process change — exercised here so the no-file path
    /// keeps working in tests / sandboxes.
    #[test]
    fn set_media_permission_updates_snapshot_and_gate() {
        let state = AppState::new().unwrap();
        let snap = state
            .set_media_permission(MediaKind::Camera, PermissionState::Allow)
            .expect("set");
        assert_eq!(snap.camera, PermissionState::Allow);
        assert_eq!(
            state.evaluate_media_permission(MediaKind::Camera),
            CaptureGate::Proceed
        );
        // Screen untouched.
        assert_eq!(
            state.evaluate_media_permission(MediaKind::Screen),
            CaptureGate::PromptUser
        );

        let snap = state
            .set_media_permission(MediaKind::Screen, PermissionState::Deny)
            .expect("set");
        assert_eq!(snap.screen, PermissionState::Deny);
        assert_eq!(
            state.evaluate_media_permission(MediaKind::Screen),
            CaptureGate::Deny
        );
    }

    /// With a permissions file attached, writes round-trip through disk
    /// — a fresh AppState pointing at the same file recovers the
    /// previously-saved posture instead of resetting to defaults.
    #[test]
    fn media_permissions_file_round_trips_across_appstates() {
        let tmp = tempfile::TempDir::new().unwrap();
        let perms_path = tmp.path().join("media_permissions.json");

        {
            let mut state = AppState::new().unwrap();
            state.attach_media_permissions_file(perms_path.clone());
            state
                .set_media_permission(MediaKind::Camera, PermissionState::Allow)
                .unwrap();
            state
                .set_media_permission(MediaKind::Screen, PermissionState::Deny)
                .unwrap();
        }

        let mut state2 = AppState::new().unwrap();
        state2.attach_media_permissions_file(perms_path);
        let perms = state2.media_permissions();
        assert_eq!(perms.camera, PermissionState::Allow);
        assert_eq!(perms.screen, PermissionState::Deny);
    }

    /// If we point the durable constructor at an un-writable path, it
    /// must fall back to the in-memory store instead of panicking the
    /// shell during boot.
    #[cfg(feature = "sqlite-backend")]
    #[test]
    fn durable_open_failure_falls_back_to_in_memory() {
        // Path whose parent is a *file*, not a directory — create_dir_all
        // will fail, so we exercise the fallback branch.
        let tmp = tempfile::NamedTempFile::new().expect("tempfile");
        let not_a_dir = tmp.path().to_path_buf();
        let bogus = not_a_dir.join("nested").join("aether.db");

        let state = AppState::new_with_db_path(&bogus).expect("fallback AppState");
        assert!(matches!(state.memory_backend(), MemoryBackend::InMemory));
    }
}
