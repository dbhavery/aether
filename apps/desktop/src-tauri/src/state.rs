//! App-level shared state for the Tauri shell.
//!
//! Owns the compiled persona, memory store, policy engine, turn engine,
//! presence controller, and the pending-approval registry that lets us
//! split a turn across two IPC calls (submit → resolve_approval) without
//! holding an async wait inside a Tauri command.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use aether_l1_interaction::{TurnEngine, TurnRequest, TurnResult, TurnRouter};
use aether_l2_memory::{InMemorySessionMemoryStore, SessionMemoryStore};
use aether_l3_presence::{InMemoryPresenceController, PresenceController};
use aether_l5_policy::{
    policy_engine::PolicyEngine, AuditStore, DefaultPolicyEngine, EngineConfig, InMemoryAuditStore,
    InMemoryGrantLedger, InMemorySink, PersonaId,
};
use aether_l6_persona::{CompiledPersona, DefaultPersonaCompiler, PersonaProfile};

use crate::adapter::{ModelRouterAdapter, ReflexModelRouter};
use crate::memory_router::MemoryAwareRouter;
use crate::provider::ProviderMode;

/// The single active session id for v0. One conversation per app instance.
pub const SESSION_ID: &str = "desktop-session";

/// Application-wide shared state held in a Tauri `State<AppState>`. Every
/// field is cheap to clone (`Arc` or primitive) — commands that mutate
/// state take a single `Mutex` lock for the pending-approval registry.
pub struct AppState {
    pub compiled: CompiledPersona,
    /// Display name sourced from the profile (CompiledPersona drops it).
    pub persona_display_name: String,
    /// Short tagline sourced from the profile description.
    pub persona_tagline: String,
    pub presence: Arc<dyn PresenceController>,
    pub memory: Arc<dyn SessionMemoryStore>,
    pub policy: Arc<dyn PolicyEngine>,
    /// Direct handle for read-side audit queries (the PolicyEngine trait
    /// does not expose a list API; we keep our own Arc and pass a clone
    /// to the engine at construction).
    pub audit: Arc<dyn AuditStore>,
    pub engine: TurnEngine,
    pub provider_mode: ProviderMode,
    pub provider_label: String,
    ts: AtomicU64,
    pending: Mutex<HashMap<String, PendingTurn>>,
}

/// An Ask turn that is waiting on a UI approval. Holds enough state to
/// replay the turn after the user resolves the ticket.
pub struct PendingTurn {
    pub request: TurnRequest,
    pub ask_result: TurnResult,
}

impl AppState {
    pub fn new() -> Result<Self, String> {
        let profile = default_profile();
        let persona_display_name = profile.name.clone();
        let persona_tagline = profile.description.clone();
        let compiled = DefaultPersonaCompiler::new()
            .compile(&profile)
            .map_err(|e| format!("persona compile: {e}"))?;

        let memory: Arc<dyn SessionMemoryStore> =
            Arc::new(InMemorySessionMemoryStore::new_default());
        let presence: Arc<dyn PresenceController> = Arc::new(InMemoryPresenceController::new());

        let persona_id = PersonaId(compiled.persona_id.0.clone());
        let cfg = EngineConfig::wave3_default(persona_id);
        let audit: Arc<dyn AuditStore> = Arc::new(InMemoryAuditStore::new());
        let policy: Arc<dyn PolicyEngine> = Arc::new(DefaultPolicyEngine::new(
            cfg,
            Arc::new(InMemoryGrantLedger::new()),
            audit.clone(),
            Arc::new(InMemorySink::new()),
        ));

        let (router, provider_mode, provider_label) = build_router_stack(&compiled, memory.clone());
        let engine = TurnEngine::new(policy.clone(), router);

        Ok(Self {
            compiled,
            persona_display_name,
            persona_tagline,
            presence,
            memory,
            policy,
            audit,
            engine,
            provider_mode,
            provider_label,
            ts: AtomicU64::new(1_000),
            pending: Mutex::new(HashMap::new()),
        })
    }

    /// Monotonic millisecond counter for stamp fields. Not a wall clock;
    /// stable within one process run. Wall-clock ms would require pulling
    /// `chrono` or `time` — not worth it for v0.
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
}

fn default_profile() -> PersonaProfile {
    use aether_l6_persona::{Humor, Stance, Tone, Verbosity};
    let mut p = PersonaProfile::simple("aurora", "Aurora");
    p.description = String::from(
        "Warm and grounded. A calm presence for focused work. Local-first by default.",
    );
    p.tone = Tone::Warm;
    p.verbosity = Verbosity::Balanced;
    p.stance = Stance::Balanced;
    p.humor = Humor::Occasional;
    p
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
                        let adapter = ModelRouterAdapter::new(provider, "ollama", tier);
                        let router: Arc<dyn TurnRouter> =
                            Arc::new(MemoryAwareRouter::new(adapter, memory, SESSION_ID));
                        let label = format!("Ollama · {} · {}", cfg.model, cfg.base_url);
                        return (router, ProviderMode::Ollama, label);
                    }
                }
                Err(e) => {
                    tracing::warn!("Ollama config error: {e}; falling back to reflex stub");
                }
            }
        }
    }
    let _ = compiled; // silence "unused variable" on default build path
    let tier = crate::provider::tier_from_rules(&compiled.routing.preferred_tier);
    let adapter = ModelRouterAdapter::new(ReflexModelRouter::new(), "reflex-stub", tier);
    let router: Arc<dyn TurnRouter> = Arc::new(MemoryAwareRouter::new(adapter, memory, SESSION_ID));
    (
        router,
        ProviderMode::ReflexStub,
        "Reflex stub (no model)".to_string(),
    )
}
