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
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, RwLock};

use aether_l1_interaction::{TurnEngine, TurnRequest, TurnResult, TurnRouter};
use aether_l2_memory::{InMemorySessionMemoryStore, SessionMemoryStore};
use aether_l3_presence::{InMemoryPresenceController, PresenceController};
use aether_l5_policy::{
    policy_engine::PolicyEngine, AuditStore, DefaultPolicyEngine, EngineConfig, InMemoryAuditStore,
    InMemoryGrantLedger, InMemorySink, PersonaId,
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
}

/// An Ask turn that is waiting on a UI approval. Holds enough state to
/// replay the turn after the user resolves the ticket.
pub struct PendingTurn {
    pub request: TurnRequest,
    pub ask_result: TurnResult,
}

impl AppState {
    pub fn new() -> Result<Self, String> {
        let catalog = default_catalog();
        let memory: Arc<dyn SessionMemoryStore> =
            Arc::new(InMemorySessionMemoryStore::new_default());
        let presence: Arc<dyn PresenceController> = Arc::new(InMemoryPresenceController::new());
        let active = build_active(&pick_default(&catalog), memory.clone())?;

        Ok(Self {
            catalog,
            presence,
            memory,
            active: RwLock::new(active),
            ts: AtomicU64::new(1_000),
            pending: Mutex::new(HashMap::new()),
        })
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
        let new_active = build_active(&profile, self.memory.clone())?;
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
) -> Result<ActiveEngine, String> {
    let persona_display_name = profile.name.clone();
    let persona_tagline = profile.description.clone();
    let compiled = DefaultPersonaCompiler::new()
        .compile(profile)
        .map_err(|e| format!("persona compile: {e}"))?;

    let persona_id = PersonaId(compiled.persona_id.0.clone());
    let cfg = EngineConfig::wave3_default(persona_id).with_persona_overlay(
        &compiled.policy_defaults.per_capability_defaults,
        compiled.policy_defaults.privacy_posture,
    );
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
    use aether_l6_persona::Stance;

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
}
