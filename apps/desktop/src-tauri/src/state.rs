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

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, RwLock};

use aether_l1_interaction::{TurnEngine, TurnRequest, TurnResult, TurnRouter};
#[cfg(feature = "sqlite-backend")]
use aether_l2_memory::{DurableSessionStore, SqliteSessionMemoryStore};
use aether_l2_memory::{InMemorySessionMemoryStore, SessionMemoryStore};
use aether_l3_presence::{InMemoryPresenceController, PresenceController};
use aether_l5_policy::{
    policy_engine::PolicyEngine, AuditStore, AutonomyPreset, DefaultPolicyEngine, EngineConfig,
    InMemoryAuditStore, InMemoryGrantLedger, InMemorySink, PersonaId,
};
use aether_l6_persona::{CompiledPersona, DefaultPersonaCompiler, PersonaProfile};
use serde::Serialize;

use crate::adapter::{ModelRouterAdapter, ReflexModelRouter};
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
        let catalog = default_catalog();
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
        })
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

/// Hard-coded persona catalog. Three voices to start: Aurora (warm /
/// balanced), Sable (neutral / bold), and Ember (formal / cautious).
/// Real persona packs will load from `personas/*.yaml` later (per
/// planning/17_persona_pack_schema.md).
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
        for (content, ts) in [("old-1", 1_000), ("old-2", 2_000), ("new-1", 9_000), ("new-2", 10_000)] {
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
