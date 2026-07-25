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
use aether_l4_router::{SpeechProvider, VisionProvider};

use crate::vision_cache::ModelListCache;
use crate::vision_registry::{VisionProviderInfo, VisionRegistry};
use crate::voice_registry::{SpeechProviderInfo, VoiceRegistry};
#[cfg(feature = "sqlite-backend")]
use aether_l2_memory::{DurableSessionStore, SessionAndDurableStores, SqliteSessionMemoryStore};
use aether_l2_memory::{
    EmbeddingProvider, EmbeddingStore, FlatFileEmbeddingStore, HfEmbeddingProvider,
    InMemorySessionMemoryStore, OllamaEmbeddingProvider, SessionMemoryStore,
};
use aether_l3_presence::{
    AttentionEvent, AttentionSnapshot, AttentionThresholds, InMemoryPresenceController,
    PresenceController, UserAttentionController,
};
use aether_l5_policy::{
    policy_engine::PolicyEngine, AuditStore, AutonomyPreset, DefaultPolicyEngine, EngineConfig,
    InMemoryAuditStore, InMemoryGrantLedger, InMemorySink, PersonaId,
};
use aether_l6_persona::{load_pack_dir, CompiledPersona, DefaultPersonaCompiler, PersonaProfile};
use serde::Serialize;

use crate::adapter::{ModelRouterAdapter, ReflexModelRouter};
use crate::media_permissions::{self, CaptureGate, MediaKind, MediaPermissions, PermissionState};
use crate::memory_config::{self, MemoryConfig, MemoryDomain};
use crate::memory_router::MemoryAwareRouter;
use crate::mic_permissions::{self, MicPermission};
use crate::presence_config::{self, PresenceConfig};
use crate::provider::ProviderMode;
use crate::retrieval::ReadinessState;
use crate::tier::{self, Tier, TierConfig};

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
    /// Personas available for runtime switching. Initialised from the
    /// hard-coded built-ins merged with YAML packs found in
    /// `AETHER_PERSONAS_DIR`. Wrapped in `RwLock` so that ADR-0012
    /// Tier-2 installs can hot-add a freshly extracted pack without a
    /// shell restart — see `refresh_catalog`.
    pub catalog: RwLock<Vec<PersonaProfile>>,
    pub presence: Arc<dyn PresenceController>,
    pub memory: Arc<dyn SessionMemoryStore>,
    /// Memory V2 / ADR-0004 — Durable-domain session-memory store.
    /// Routed to from [`AppState::memory_for_domain`] whenever the
    /// request carries `MemoryDomain::Durable`. When the shell booted
    /// against the in-memory backend (tests, sandboxes), this is a
    /// second `InMemorySessionMemoryStore` instance — separate from
    /// `memory` so Session rows and Durable rows do not cross-pollute
    /// even without a real SQLite file.
    pub durable_memory: Arc<dyn SessionMemoryStore>,
    /// Memory V2 step 6 (ADR-0002) — embeddings store. Owned by the
    /// shell so the Memory tab can query, count, and forget without
    /// downcasting. Trait object so tests can inject an in-memory
    /// store. Always constructed today (the shell's `aether-l2-memory`
    /// feature set includes `embeddings`); consumption is gated by
    /// `memory_config.embeddings.enabled`, not by compile-time.
    pub embedding_store: Arc<dyn EmbeddingStore>,
    /// Memory V2 step 6 — embedding provider. Wrapped in an `RwLock`
    /// so Settings changes to the provider id can swap the live
    /// provider without rebuilding the whole `AppState`.
    pub embedding_provider: RwLock<Arc<dyn EmbeddingProvider>>,
    pub active: RwLock<ActiveEngine>,
    ts: AtomicU64,
    pending: Mutex<HashMap<String, PendingApproval>>,
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
    /// Local-only microphone permission posture. Loaded from disk at
    /// boot when a `mic_permission_path` is configured; writes are
    /// persisted atomically through `set_mic_permission`. Separate
    /// file from `media_permissions` so the camera/screen consent and
    /// the mic consent stay independently auditable.
    mic_permission: RwLock<MicPermission>,
    /// Disk-backed location for `mic_permission`. `None` when the
    /// shell is running without a writable data dir (tests,
    /// sandboxes) — the in-memory copy still works, but changes do
    /// not survive restarts.
    mic_permission_path: Option<PathBuf>,
    /// Presence V1 configuration snapshot — enabled, idle/away
    /// thresholds, Trust drawer history toggle. Observational only
    /// (no L5 capability gate, no audit rows), per
    /// docs/PRESENCE-V1-ARCHITECTURE.md §4.
    presence_config: RwLock<PresenceConfig>,
    /// Disk-backed location for `presence_config`. `None` in
    /// sandboxes; in-memory copy still works.
    presence_config_path: Option<PathBuf>,
    /// Presence V1 step 2 — user-attention axis controller
    /// (Active / Idle / Away). Sibling to [`PresenceController`],
    /// which owns the assistant-posture axis. The shell's poll task
    /// (wired in `main.rs`) calls `tick` with an OS-idle reading each
    /// interval; transitions are emitted as `presence:attention`
    /// events and pushed into `presence_history` for the Trust drawer.
    pub attention: Arc<UserAttentionController>,
    /// T1.3 — L5-gated browser automation executor. The trait object
    /// is kept on `AppState` so every browser_* Tauri command can
    /// share one Playwright session map (when the real backend lands).
    /// Today this is the [`PlaywrightExecutor`] stub from
    /// `aether-l5-browser`; every method returns
    /// `BrowserExecError::BackendDisabled`. The stub-to-real swap is
    /// a single-line change in `build()`.
    pub browser_executor: Arc<dyn aether_l5_browser::BrowserExecutor>,
    /// T1.3 file-workflow — L5-gated files executor. The trait object
    /// is kept on `AppState` so every `files_*` Tauri command can share
    /// one backend (and, when the real backend lands, one
    /// [`ScopeAllowlist`](aether_l5_files::ScopeAllowlist) /
    /// blocking-pool handle). Today this is the
    /// [`StdFsExecutor`](aether_l5_files::std_fs_stub::StdFsExecutor)
    /// stub from `aether-l5-files`; every method returns
    /// `FilesExecError::BackendDisabled`. The wiring contract this
    /// field implements is verified in `files_commands::tests` against
    /// those same `BackendDisabled` returns; the stub-to-real swap is
    /// a single-line change in `build()` once the `std::fs` /
    /// `tokio::fs` driver lands in a later slice.
    pub files_executor: Arc<dyn aether_l5_files::FilesExecutor>,
    /// Wave 13b — concrete handle on the same `StdFsExecutor` that
    /// `files_executor` wraps as a trait object. Cloning the inner
    /// `Arc<StdFsExecutor>` yields a second outer `Arc` whose internal
    /// `Arc<RwLock<ScopeAllowlist>>` is *shared* with `files_executor`
    /// (Wave 13a contract). The handle exists so the boot path and the
    /// L5 event sink can call `set_allowlist` /
    /// `update_allowlist_from_paths` on the concrete type without
    /// extending the public `FilesExecutor` trait surface that
    /// `files_commands.rs` consumes.
    pub files_executor_handle: Arc<aether_l5_files::std_fs_stub::StdFsExecutor>,
    /// Bounded, UX-only history of attention transitions for the
    /// Trust drawer's History tab. Does NOT go through the L5 audit
    /// store — presence is observational per design §4. Cleared on
    /// app restart.
    presence_history: Mutex<VecDeque<PresenceHistoryEntry>>,
    /// Memory V2 step 2 — user-owned memory-system policy
    /// (retention + per-domain risk + embeddings opt-in). See
    /// `docs/MEMORY-V2-ARCHITECTURE.md` §3. Step 2 lands the
    /// config/commands/Settings surface only; L2 consumers wire into
    /// `risk_for` in a later slice.
    memory_config: RwLock<MemoryConfig>,
    /// Disk-backed location for `memory_config`. `None` in sandboxes;
    /// the in-memory copy still works but changes do not survive
    /// restarts.
    memory_config_path: Option<PathBuf>,
    /// Per-domain read counters for the Memory V2 sampled-read audit
    /// (design §4 — 1 sample per ~100 reads per domain per session).
    /// Populated with all six domains at `build()` time and never
    /// mutated in shape again; the AtomicU64 values are bumped
    /// lock-free. See `memory_service::memory_read_audit_tick`.
    memory_read_counters: HashMap<MemoryDomain, AtomicU64>,
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
    /// Registry of zero or more speech-capable providers + the active
    /// selection. Parallel to `vision` but separate — the mic and
    /// camera/screen consent boundaries stay auditable independently.
    /// The active selection is persisted via `voice_registry`'s
    /// attached file.
    voice: RwLock<VoiceRegistry>,
    /// ADR-0007 §Decision 3 retrieval readiness state. Updated by every
    /// invocation of `run_retrieval_context` (event-driven symmetric
    /// cadence) plus boot probes and settings-change probes. Read by
    /// the `embeddings_readiness` Tauri command for the Trust drawer
    /// indicator + drawer-icon attention badge.
    retrieval_readiness: RwLock<ReadinessState>,
    /// ADR-0006 hardware tier model — selected tier, detected tier,
    /// hardware snapshot. Read by every tier-aware subsystem (today
    /// embeddings onboarding via ADR-0007 D7; future TTS/vision/avatar
    /// ADRs). Disk-backed when `tier_config_path` is wired.
    tier_config: RwLock<TierConfig>,
    /// Disk-backed location for `tier_config`. `None` in sandboxes;
    /// the in-memory copy still works but changes do not survive
    /// restarts.
    tier_config_path: Option<PathBuf>,
    /// ADR-0007 §Decision 5 backfill — true while a backfill job is
    /// running; checked by `start_backfill` to reject concurrent
    /// requests. The backfill task itself sets it false on completion
    /// or cancellation. Atomic so the read in the start path is
    /// lock-free.
    pub backfill_in_progress: std::sync::atomic::AtomicBool,
    /// ADR-0007 §Decision 5 backfill — set true by `cancel_backfill`
    /// to ask the running task to stop at the next row boundary. The
    /// task resets to false on observation. Atomic so the write from
    /// the cancel command and the read from the worker task don't
    /// need a mutex.
    pub backfill_cancel: std::sync::atomic::AtomicBool,
    /// ADR-0007 §Decision 5 backfill — last-known progress snapshot.
    /// Updated by the worker task as it advances; read by
    /// `backfill_status` for UI polling. Mutex (not RwLock) because
    /// the writer is the sole hot path.
    pub backfill_progress: Mutex<BackfillProgress>,
}

/// ADR-0007 §Decision 5 backfill progress snapshot. Returned by
/// `backfill_status` and embedded in `backfill:progress` events.
/// Stable wire shape — UI consumes it for the progress strip.
#[derive(Debug, Clone, Default, Serialize)]
pub struct BackfillProgress {
    /// `true` once the worker task has finished (success or cancel).
    /// Matched by the UI to flip the button back from "Cancel" to
    /// "Backfill now".
    pub finished: bool,
    /// `true` only when the worker exited via cancel.
    pub cancelled: bool,
    /// Total rows the worker plans to embed (sum across embed-eligible
    /// domains at job-start time). Stable for the duration of the job.
    pub total: usize,
    /// Rows successfully (re-)embedded so far.
    pub completed: usize,
    /// Rows that errored mid-embed and were skipped. Worker continues
    /// past failures so a single bad row doesn't kill the job.
    /// Counts only rows that exhausted every retry attempt — a row
    /// that succeeded on a retry is counted in `completed`, with the
    /// retry surfaced separately in `recovered_failures` (Phase 3B F1).
    pub failures: usize,
    /// Rows that hit at least one transient embed failure (HTTP
    /// 5xx / timeout / connection-refused) but succeeded on a
    /// subsequent retry. Increments once per recovered row regardless
    /// of how many retries were consumed; the row itself is also
    /// counted in `completed`. Surfaced separately so the UI and
    /// post-run summary can highlight Ollama queue-pressure recovery
    /// without conflating it with un-retried success. Phase 3B F1
    /// landed this against ADR-0007 D7's documented ~1.3% sustained
    /// HTTP 500 rate at 50 ms pacing.
    pub recovered_failures: usize,
    /// Rows skipped because an embedding already exists for the
    /// (domain, memory_id) pair. Surfaced separately from `completed`
    /// so the UI can show "skipped X already-embedded rows" rather
    /// than double-counting them as completed work. Populated when the
    /// `EmbeddingStore` impl honours `embedded_ids(domain)`; impls that
    /// fall back to the trait default (empty set) will see this stay
    /// at 0 and the worker will fall back to the historical brute-
    /// force re-embed.
    pub skipped_already_embedded: usize,
    /// Domain currently being walked, if any. `None` between domains
    /// or when finished.
    pub current_domain: Option<String>,
    /// Wall-clock millis when the job started; 0 if no job has run.
    pub started_at_ms: u64,
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

/// How many presence-attention transitions the shell retains for the
/// Trust drawer's History tab. Bounded by design — presence is
/// observational and transient per `docs/PRESENCE-V1-ARCHITECTURE.md`
/// §8. Separate buffer from `telemetry` so the presence-event shape
/// doesn't leak into the turn-telemetry schema.
pub const PRESENCE_HISTORY_CAPACITY: usize = 64;

/// One row on the shell's presence-history ring. Mirrors an
/// `AttentionEvent` from L3 plus a stable label for telemetry-kind
/// matching (design §5 — `presence_state_changed`). Serde is on so
/// the Tauri command can return it directly.
#[derive(Debug, Clone, Serialize)]
pub struct PresenceHistoryEntry {
    /// Always `"presence_state_changed"` for the step-2 surface. Held
    /// as a field rather than a constant so step-3+ history shapes
    /// (e.g. `session_opened`) can share the same ring.
    pub kind: String,
    /// Previous state label (`"active"` / `"idle"` / `"away"`).
    pub from: String,
    /// New state label.
    pub to: String,
    /// Seconds of OS idle at the transition — useful for debugging
    /// and for the Trust drawer's future hover tooltip.
    pub idle_seconds: u64,
    /// `AppState::next_ts`-stamped transition time (monotonic ms).
    pub at_ms: u64,
}

impl PresenceHistoryEntry {
    /// Lift a raw L3 attention event onto the shell history shape.
    fn from_event(ev: AttentionEvent) -> Self {
        Self {
            kind: "presence_state_changed".to_string(),
            from: ev.from.label().to_string(),
            to: ev.to.label().to_string(),
            idle_seconds: ev.idle_seconds,
            at_ms: ev.at_ms,
        }
    }
}

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
    /// Model id, when the route used a vision provider that exposes
    /// one. `None` for text-only turns and for adapters that don't
    /// report a model (passive adapters / discovery failures). Used
    /// by the Trust drawer's History tab to annotate media rows with
    /// the exact model that served them.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
    /// End-to-end latency in ms, if observed.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub latency_ms: Option<u64>,
    /// Prompt-side token count, if reported.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prompt_tokens: Option<u32>,
    /// Completion-side token count, if reported.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub completion_tokens: Option<u32>,
    /// Memory V2 domain label (wire form — `"facts"`, `"durable"`,
    /// etc.). Populated only by memory-scoped telemetry kinds
    /// (`memory_written`, `memory_forgotten`, `memory_edited`,
    /// `memory_write_asked`, `memory_write_denied`,
    /// `memory_retrieval`); `None` everywhere else. Additive field;
    /// pre-V2 telemetry consumers ignore it.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub memory_domain: Option<String>,
    /// Memory V2 per-item id (stable across this shell process).
    /// `None` for domain-scoped events (forget-all, sampled
    /// retrieval) that don't target a single item.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub memory_id: Option<String>,
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
    /// Raw user utterance *without* the ADR-0005 retrieval block.
    /// Now redundant with `request.original_utterance` after ADR-0009
    /// landed (the L1 `TurnRequest` carries both channels itself), but
    /// kept as a separately-owned `String` so the post-approval
    /// `finalize_turn` path doesn't need a borrow into `pending.request`.
    /// Memory records and the user-visible transcript use this string.
    pub original_utterance: String,
}

/// An executor invocation (`browser_*` / `files_*`) that is waiting on a
/// UI approval after the L5 gate returned `Decision::Ask`. The variant
/// payload carries everything needed to replay the call from
/// `resolve_approval` once the user clicks Approve. Wave 11 introduced
/// this enum so the gate's `Ask` decision can route through the same
/// approval modal the chat surface (`submit_turn` → `resolve_approval`)
/// already wires, instead of short-circuiting with a string error.
#[derive(Debug, Clone)]
pub enum PendingExecutorCall {
    BrowserOpen {
        url: String,
    },
    BrowserNavigate {
        session: aether_l5_browser::SessionId,
        url: String,
    },
    BrowserReadPage {
        session: aether_l5_browser::SessionId,
    },
    BrowserExtract {
        session: aether_l5_browser::SessionId,
        selector: String,
    },
    BrowserFillForm {
        session: aether_l5_browser::SessionId,
        fields: Vec<aether_l5_browser::FormField>,
    },
    BrowserSubmit {
        session: aether_l5_browser::SessionId,
        selector: String,
    },
    FilesRead {
        path: String,
    },
    FilesCreate {
        path: String,
        contents: Vec<u8>,
    },
    FilesEdit {
        path: String,
        contents: Vec<u8>,
    },
    FilesRename {
        src: String,
        dst: String,
    },
    FilesDelete {
        path: String,
    },
    FilesGrep {
        root: String,
        pattern: String,
    },
}

/// Approval pending in the shared registry. A single `HashMap<TicketId,
/// PendingApproval>` holds both flavours so `resolve_approval` can
/// dispatch on the variant without scanning multiple maps.
pub enum PendingApproval {
    /// Original chat-surface flavour — replay `handle_turn` post-approval.
    Turn(PendingTurn),
    /// Wave 11 — replay an L5-gated executor invocation post-approval.
    /// `payload` carries the `ApprovalPayload` shape the UI's modal
    /// already consumes so `resolve_approval` can mirror the chat-surface
    /// experience without inventing a second wire shape.
    ///
    /// Wave 12 added `ticket`: the live `ApprovalTicket` captured from
    /// the gate's `Decision::Ask { ticket, .. }`. Cached so the reject
    /// path in `resolve_executor_approval` can call
    /// `respond_approval(Reject)` for L5 audit-row completeness — the
    /// chat-surface Turn path already does this, the executor path now
    /// matches.
    Executor {
        call: PendingExecutorCall,
        approval: crate::commands::ApprovalPayload,
        ticket: aether_l5_policy::ApprovalTicket,
    },
}

impl AppState {
    /// In-memory constructor used by unit tests and any environment
    /// without a writable data directory. Mirrors the historical
    /// pre-durable-memory behaviour.
    pub fn new() -> Result<Self, String> {
        let session: Arc<dyn SessionMemoryStore> =
            Arc::new(InMemorySessionMemoryStore::new_default());
        // Separate in-memory store for the Durable lane so fallback-mode
        // callers still see per-domain isolation — matches the ADR-0004
        // contract that Durable writes do not mix with Session writes.
        let durable: Arc<dyn SessionMemoryStore> =
            Arc::new(InMemorySessionMemoryStore::new_default());
        Self::build(session, durable, MemoryBackend::InMemory)
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
        match DurableSessionStore::open_session_and_durable(
            path_ref,
            aether_l2_memory::RecentMemoryConfig::default_narrow(),
            aether_l2_memory::RetentionPolicy::default_bounded(),
            aether_l2_memory::RetentionPolicy::unbounded(),
        ) {
            Ok(SessionAndDurableStores {
                session,
                durable,
                conn: _,
            }) => {
                tracing::info!(
                    "durable session+durable memory opened at {}",
                    path_ref.display()
                );
                // Clone the concrete typed handle so `durable_store()`
                // keeps surfacing the Session-lane store for retention
                // maintenance (the existing accessor). ADR-0004's
                // per-domain stores are reached via `memory_for_domain`.
                let concrete = session.clone();
                let session_trait: Arc<dyn SessionMemoryStore> = session;
                let durable_trait: Arc<dyn SessionMemoryStore> = durable;
                let mut state = Self::build(
                    session_trait,
                    durable_trait,
                    MemoryBackend::Durable {
                        path: path_ref.to_path_buf(),
                    },
                )?;
                state.durable_store = Some(concrete);
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

    /// ADR-0004: pick the backing store for `domain`. Session and
    /// Durable each own a dedicated store; every other domain falls
    /// back to the Session store with a `warn!` citing the
    /// known-limitation gap ADR-0005 will close.
    ///
    /// Callers that know they only ever route a real-store domain
    /// (Session/Durable) can still call this; the fallback is
    /// defensive, not a normal path.
    pub fn memory_for_domain(&self, domain: MemoryDomain) -> Arc<dyn SessionMemoryStore> {
        match domain {
            MemoryDomain::Session => self.memory.clone(),
            MemoryDomain::Durable => self.durable_memory.clone(),
            other => {
                tracing::warn!(
                    "memory_for_domain({}) has no dedicated store yet (ADR-0005); falling back to Session lane",
                    other.label()
                );
                self.memory.clone()
            }
        }
    }

    /// ADR-0004: domains with a dedicated backing store today. Used by
    /// the retention sweep to decide which lanes to prune; domains not
    /// in this list are trace-skipped regardless of their retention
    /// policy value. Order matches `MemoryDomain::ALL` for deterministic
    /// sweep-walk ordering.
    pub const DOMAINS_WITH_STORE: &'static [MemoryDomain] =
        &[MemoryDomain::Session, MemoryDomain::Durable];

    /// True iff `domain` has a dedicated backing store (vs. the Session
    /// fallback). Wrapper over the `DOMAINS_WITH_STORE` constant so
    /// callers can write `state.has_domain_store(d)` without importing
    /// the slice directly.
    pub fn has_domain_store(&self, domain: MemoryDomain) -> bool {
        Self::DOMAINS_WITH_STORE.contains(&domain)
    }

    fn build(
        memory: Arc<dyn SessionMemoryStore>,
        durable_memory: Arc<dyn SessionMemoryStore>,
        backend: MemoryBackend,
    ) -> Result<Self, String> {
        let catalog = merge_yaml_personas(default_catalog());
        let presence: Arc<dyn PresenceController> = Arc::new(InMemoryPresenceController::new());
        let cfg = PresenceConfig::defaults();
        let attention = Arc::new(UserAttentionController::new(
            cfg.enabled,
            AttentionThresholds {
                idle_after_s: cfg.idle_after_s,
                away_after_s: cfg.away_after_s,
            },
        ));
        // Wave 13b — concrete StdFsExecutor handle. Both `files_executor`
        // and `files_executor_handle` wrap clones of the SAME inner Arc,
        // so the internal Arc<RwLock<ScopeAllowlist>> is shared. The
        // handle exists so the boot-time seed step and the L5 event sink
        // can call `set_allowlist`/`update_allowlist_from_paths` on the
        // concrete type without extending the FilesExecutor trait.
        let files_executor_handle: Arc<aether_l5_files::std_fs_stub::StdFsExecutor> =
            Arc::new(aether_l5_files::std_fs_stub::StdFsExecutor::default());
        let active = build_active(
            &pick_default(&catalog),
            memory.clone(),
            None,
            files_executor_handle.clone(),
        )?;

        let embedding_store: Arc<dyn EmbeddingStore> =
            Arc::new(FlatFileEmbeddingStore::in_memory());
        let embedding_provider: Arc<dyn EmbeddingProvider> =
            Arc::new(OllamaEmbeddingProvider::from_env());

        Ok(Self {
            catalog: RwLock::new(catalog),
            presence,
            memory,
            durable_memory,
            embedding_store,
            embedding_provider: RwLock::new(embedding_provider),
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
            mic_permission: RwLock::new(MicPermission::defaults()),
            mic_permission_path: None,
            presence_config: RwLock::new(cfg),
            presence_config_path: None,
            attention,
            browser_executor: Arc::new(
                aether_l5_browser::playwright_stub::PlaywrightExecutor::new(),
            ),
            // Wave 13b — both fields wrap clones of the SAME
            // Arc<StdFsExecutor>. Wave 13a's hand-rolled `Clone` shares
            // the internal `Arc<RwLock<ScopeAllowlist>>`, so a mutation
            // via the handle is observed through the trait surface
            // immediately. The trait-object form preserves the existing
            // `files_commands.rs` consumption contract; the concrete
            // form lets the boot seed and the L5 event sink call
            // `set_allowlist` / `update_allowlist_from_paths` without
            // extending the `FilesExecutor` trait.
            files_executor: files_executor_handle.clone(),
            files_executor_handle,
            presence_history: Mutex::new(VecDeque::with_capacity(PRESENCE_HISTORY_CAPACITY)),
            memory_config: RwLock::new(MemoryConfig::defaults()),
            memory_config_path: None,
            memory_read_counters: MemoryDomain::ALL
                .iter()
                .map(|d| (*d, AtomicU64::new(0)))
                .collect(),
            vision: RwLock::new(VisionRegistry::empty()),
            vision_model_cache: ModelListCache::from_env(),
            voice: RwLock::new(VoiceRegistry::empty()),
            retrieval_readiness: RwLock::new(ReadinessState::Unknown),
            tier_config: RwLock::new(TierConfig::defaults()),
            tier_config_path: None,
            backfill_in_progress: std::sync::atomic::AtomicBool::new(false),
            backfill_cancel: std::sync::atomic::AtomicBool::new(false),
            backfill_progress: Mutex::new(BackfillProgress::default()),
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

    /// First-launch hook: seed `model_per_provider` from each
    /// registered adapter's `current_model()` for entries not already
    /// present. Idempotent on subsequent launches.
    #[allow(dead_code)] // Wired only behind provider features in main.rs.
    pub fn vision_seed_missing_models(&self) -> Result<(), String> {
        let r = self.vision.read().expect("vision registry read lock");
        r.seed_missing_models_from_adapters()
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
    pub fn vision_model_list_cached(&self) -> Result<(String, Vec<String>), VisionModelListError> {
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

    // --- Voice (speech) provider registry ----------------------------------

    /// Register a speech-capable provider into the registry. Called
    /// from `build_app_state` in main.rs for each provider whose
    /// boot-time healthcheck passed. Order matters — first registered
    /// is the fallback when persisted state names an unknown id.
    #[allow(dead_code)] // Wired only behind provider features in main.rs.
    pub fn register_speech_provider(&self, provider: Arc<dyn SpeechProvider>) {
        let mut w = self.voice.write().expect("voice registry write lock");
        w.register(provider);
    }

    /// Wire the on-disk persistence file for the active speech-provider
    /// selection. Loads the persisted state (with safe fallbacks).
    #[allow(dead_code)] // Wired only behind provider features in main.rs.
    pub fn attach_voice_persistence(&self, path: PathBuf) {
        let mut w = self.voice.write().expect("voice registry write lock");
        w.attach_persistence(path);
    }

    /// Auto-select the first registered speech provider if no active
    /// id was loaded from persistence. No-op when an active id is
    /// already set.
    #[allow(dead_code)] // Wired only behind provider features in main.rs.
    pub fn voice_auto_select_if_unset(&self) {
        let r = self.voice.read().expect("voice registry read lock");
        r.auto_select_first_if_unset();
    }

    /// First-launch hook: seed `model_per_provider` from each
    /// registered speech adapter's `current_model()` for entries not
    /// already present. Idempotent on subsequent launches.
    #[allow(dead_code)] // Wired only behind provider features in main.rs.
    pub fn voice_seed_missing_models(&self) -> Result<(), String> {
        let r = self.voice.read().expect("voice registry read lock");
        r.seed_missing_models_from_adapters()
    }

    /// Cheap clone of the active speech provider handle. `None` when
    /// no provider is selected (voice disabled) or the registry is
    /// empty. Voice V1 step 4's `transcribe_utterance` treats the
    /// absence as a hard error — unlike vision, there is no silent
    /// text fallback for voice.
    pub fn speech_provider(&self) -> Option<Arc<dyn SpeechProvider>> {
        let r = self.voice.read().expect("voice registry read lock");
        r.active()
    }

    /// Active speech provider id, if any.
    #[allow(dead_code)] // Surfaced in step 4 Tauri commands.
    pub fn speech_active_id(&self) -> Option<String> {
        let r = self.voice.read().expect("voice registry read lock");
        r.active_id()
    }

    /// Human-readable label for the active speech provider, if any.
    #[allow(dead_code)] // Surfaced in step 4 Tauri commands.
    pub fn speech_provider_label(&self) -> Option<String> {
        let r = self.voice.read().expect("voice registry read lock");
        r.active_label()
    }

    /// Snapshot of every registered speech provider plus an `active`
    /// flag. Surfaced via the future step 4 `list_speech_providers`
    /// Tauri command.
    #[allow(dead_code)] // Surfaced in step 4 Tauri commands.
    pub fn speech_provider_list(&self) -> Vec<SpeechProviderInfo> {
        let r = self.voice.read().expect("voice registry read lock");
        r.list()
    }

    /// Set the active speech provider by id. `None` disables voice
    /// input. Persists when a file is wired.
    #[allow(dead_code)] // Surfaced in step 4 Tauri commands.
    pub fn set_active_speech_provider(&self, id: Option<String>) -> Result<(), String> {
        let r = self.voice.read().expect("voice registry read lock");
        r.set_active(id)
    }

    /// Current model id of the active speech provider, if any.
    #[allow(dead_code)] // Surfaced in step 4 Tauri commands.
    pub fn speech_active_model(&self) -> Option<String> {
        let r = self.voice.read().expect("voice registry read lock");
        r.active_model()
    }

    /// Switch the model used by the active speech provider. Persists
    /// under the active provider id so a future provider swap
    /// restores the same pick.
    #[allow(dead_code)] // Surfaced in step 4 Tauri commands.
    pub fn set_active_speech_model(&self, model: &str) -> Result<(), String> {
        let r = self.voice.read().expect("voice registry read lock");
        r.set_active_model(model)
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

    /// Wire a disk-backed mic-permission file into this state. Loads
    /// the current contents (or falls back to defaults if the file is
    /// missing/malformed) and remembers the path so subsequent writes
    /// persist atomically. Mirrors `attach_media_permissions_file`.
    pub fn attach_mic_permission_file(&mut self, path: PathBuf) {
        let loaded = mic_permissions::load_or_default(&path);
        *self.mic_permission.write().expect("mic perm write lock") = loaded;
        self.mic_permission_path = Some(path);
    }

    /// Snapshot the current mic permission. Cheap clone; safe to hand
    /// to a Tauri command response.
    pub fn mic_permission(&self) -> MicPermission {
        *self.mic_permission.read().expect("mic perm read lock")
    }

    /// Update the mic permission and persist the new state to disk if
    /// a path is wired. Returns the resulting snapshot so the caller
    /// can echo it back to the UI in one round trip.
    ///
    /// Persistence failures are surfaced as `Err` so the UI can show
    /// the user the change did not stick. A tracing INFO line records
    /// the transition for local observability; no L5 `AuditRecordEvent`
    /// is emitted here — the audit surface for mic activity lives at
    /// the capture site (see `transcribe_utterance`, step 4), the same
    /// way `analyze_frame` owns the audit for media capture.
    pub fn set_mic_permission(&self, state: PermissionState) -> Result<MicPermission, String> {
        let (previous, snapshot) = {
            let mut w = self.mic_permission.write().expect("mic perm write lock");
            let previous = w.state;
            w.state = state;
            (previous, *w)
        };
        if let Some(path) = &self.mic_permission_path {
            mic_permissions::save(path, &snapshot)
                .map_err(|e| format!("persist mic permission: {e}"))?;
        }
        if previous != state {
            tracing::info!("mic permission: {} -> {}", previous.wire(), state.wire());
        }
        Ok(snapshot)
    }

    /// Pre-capture gate for mic. Future voice-capture sites must call
    /// this before touching the microphone — it never starts capture
    /// itself. See [`media_permissions::CaptureGate`] for the action
    /// the caller should take.
    #[allow(dead_code)] // Consumed by `transcribe_utterance` in Voice V1 step 4.
    pub fn evaluate_mic_permission(&self) -> CaptureGate {
        self.mic_permission().evaluate()
    }

    /// Wire a disk-backed presence config into this state. Loads
    /// current contents (falling back to defaults for
    /// missing/malformed files) and remembers the path so
    /// subsequent writes persist atomically. Also seeds the
    /// attention controller with the loaded thresholds + enabled
    /// flag so the first poll tick respects the persisted policy
    /// rather than the code defaults.
    pub fn attach_presence_config_file(&mut self, path: PathBuf) {
        let loaded = presence_config::load_or_default(&path);
        *self
            .presence_config
            .write()
            .expect("presence cfg write lock") = loaded;
        self.presence_config_path = Some(path);
        // Propagate into the attention controller. Swallow lock
        // errors — tracing handles observability, and a poisoned
        // lock on boot is a far bigger problem than presence rot.
        let _ = self.attention.set_enabled(loaded.enabled);
        let _ = self.attention.set_thresholds(AttentionThresholds {
            idle_after_s: loaded.idle_after_s,
            away_after_s: loaded.away_after_s,
        });
    }

    /// Snapshot the current presence config. Cheap clone; safe to
    /// hand to a Tauri command response.
    pub fn presence_config(&self) -> PresenceConfig {
        *self.presence_config.read().expect("presence cfg read lock")
    }

    /// Replace the presence config and persist atomically when a
    /// path is wired. Returns the resulting snapshot so the caller
    /// can echo it back to the UI in one round trip. Persistence
    /// failures are surfaced as `Err` so the UI can show the change
    /// did not stick.
    ///
    /// Also hot-swaps the threshold + enabled flag onto the live
    /// attention controller so the next poll tick uses the updated
    /// config without requiring an app restart.
    pub fn set_presence_config(&self, cfg: PresenceConfig) -> Result<PresenceConfig, String> {
        // Reject obviously-invalid thresholds at the boundary. The
        // controller sanitises further, but rejecting here keeps the
        // Settings UI honest (we don't persist a 5-second Away
        // threshold when the UI's number input has loose validation).
        if cfg.idle_after_s < 10 || cfg.idle_after_s > 86_400 {
            return Err(format!(
                "idle_after_s must be between 10 and 86400 seconds (got {})",
                cfg.idle_after_s
            ));
        }
        if cfg.away_after_s < 10 || cfg.away_after_s > 86_400 {
            return Err(format!(
                "away_after_s must be between 10 and 86400 seconds (got {})",
                cfg.away_after_s
            ));
        }
        if cfg.away_after_s <= cfg.idle_after_s {
            return Err(format!(
                "away_after_s ({}) must be greater than idle_after_s ({})",
                cfg.away_after_s, cfg.idle_after_s
            ));
        }
        let snapshot = {
            let mut w = self
                .presence_config
                .write()
                .expect("presence cfg write lock");
            *w = cfg;
            *w
        };
        if let Some(path) = &self.presence_config_path {
            presence_config::save(path, &snapshot)
                .map_err(|e| format!("persist presence config: {e}"))?;
        }
        // Live-propagate into the attention controller so the next
        // tick picks up the new policy without requiring a restart.
        // Lock-poison errors are logged but not fatal — the config
        // is persisted and will be re-applied on next boot.
        if let Err(e) = self.attention.set_enabled(snapshot.enabled) {
            tracing::warn!("attention set_enabled failed: {e}");
        }
        if let Err(e) = self.attention.set_thresholds(AttentionThresholds {
            idle_after_s: snapshot.idle_after_s,
            away_after_s: snapshot.away_after_s,
        }) {
            tracing::warn!("attention set_thresholds failed: {e}");
        }
        Ok(snapshot)
    }

    /// Apply one presence-poll tick. Feeds the controller the current
    /// monotonic timestamp and an idle reading (or `None` when the
    /// platform probe is unsupported — macOS / Linux today). Returns
    /// `Some(event)` when the state label changed; the caller (the
    /// poll task) is then responsible for `app.emit` and for pushing
    /// a `PresenceHistoryEntry` via [`push_presence_history`].
    pub fn attention_tick(&self, now_ms: u64, idle_seconds: Option<u64>) -> Option<AttentionEvent> {
        self.attention.tick(now_ms, idle_seconds)
    }

    /// Cheap snapshot for the `presence_status` command.
    pub fn attention_snapshot(&self) -> AttentionSnapshot {
        self.attention.snapshot()
    }

    /// Push a transition onto the UX-only presence-history ring
    /// buffer. Bounded by [`PRESENCE_HISTORY_CAPACITY`]; oldest
    /// entries are evicted first. Never errors — UX buffer only.
    pub fn push_presence_history(&self, entry: PresenceHistoryEntry) {
        match self.presence_history.lock() {
            Ok(mut g) => {
                if g.len() == PRESENCE_HISTORY_CAPACITY {
                    g.pop_front();
                }
                g.push_back(entry);
            }
            Err(e) => {
                tracing::warn!("presence history lock poisoned: {e}; entry dropped");
            }
        }
    }

    /// Snapshot of recent attention transitions (newest-first).
    /// Capped at `limit` entries. Used by the Trust drawer's History
    /// tab (Presence V1 step 3).
    pub fn presence_history_recent(&self, limit: usize) -> Vec<PresenceHistoryEntry> {
        let Ok(g) = self.presence_history.lock() else {
            return Vec::new();
        };
        g.iter().rev().take(limit).cloned().collect()
    }

    // --- Memory V2 step 2 — memory.json read/write surface ---------------

    /// Wire a disk-backed memory config into this state. Mirrors
    /// `attach_presence_config_file`: load contents (falling back to
    /// defaults for missing/malformed files) and remember the path
    /// for atomic writes.
    pub fn attach_memory_config_file(&mut self, path: PathBuf) {
        let loaded = memory_config::load_or_default(&path);
        // Honor the persisted embeddings.provider on boot — without
        // this, the in-memory embedding_provider Arc stays at its
        // boot-time env-loaded default until the user touches Settings,
        // even if memory.json on disk says something different. Mirror
        // of the swap applied by set_memory_config so the runtime
        // provider always matches what the persisted config promises.
        if let Some(provider_str) = loaded.embeddings.provider.as_deref() {
            self.swap_embedding_provider_for_config(provider_str);
        }
        *self.memory_config.write().expect("memory cfg write lock") = loaded;
        self.memory_config_path = Some(path);
    }

    /// Wire the on-disk persistence file for the tier config (ADR-0006).
    /// Loads the persisted state with safe fallbacks. If `path` does
    /// not yet exist, the in-memory `TierConfig::defaults()` (Spark,
    /// pre-detection) stands until the first detect/set_tier call.
    pub fn attach_tier_config_file(&mut self, path: PathBuf) {
        let loaded = tier::load_or_default(&path);
        *self.tier_config.write().expect("tier cfg write lock") = loaded;
        self.tier_config_path = Some(path);
    }

    /// Snapshot the current tier config. Cheap clone; safe for Tauri.
    pub fn tier_config(&self) -> TierConfig {
        self.tier_config.read().expect("tier cfg read lock").clone()
    }

    /// User-initiated tier change (Settings UI). Updates `selected_tier`,
    /// flips `manual_override` if the new selection diverges from
    /// `detected_tier`, and persists atomically when a path is wired.
    /// Returns the resulting snapshot for the UI to echo back.
    pub fn set_tier(&self, new_tier: Tier) -> Result<TierConfig, String> {
        let next = {
            let mut w = self.tier_config.write().expect("tier cfg write lock");
            w.selected_tier = new_tier;
            w.manual_override = new_tier != w.detected_tier;
            w.clone()
        };
        if let Some(path) = &self.tier_config_path {
            tier::save(path, &next).map_err(|e| format!("persist tier config: {e}"))?;
        }
        Ok(next)
    }

    /// Run a fresh hardware-detection pass and update the tier config
    /// in place. The recommended tier is recomputed; if the user has
    /// not manually overridden, `selected_tier` follows the detection.
    /// If they have, only `detected_tier` and `hardware_snapshot`
    /// update — their manual selection stays.
    ///
    /// Light-usage: calls `hardware::detect`, which is a pure read
    /// (no model loads, no rendering). Returns the resulting config
    /// snapshot for the UI to echo.
    pub fn redetect_hardware(&self) -> Result<TierConfig, String> {
        let app_data = self
            .tier_config_path
            .as_ref()
            .and_then(|p| p.parent())
            .map(|p| p.to_path_buf());
        // Only probe Ollama when the embeddings flag is on; redetection
        // shouldn't poke at a daemon the user has explicitly turned
        // off.
        let cfg = self.memory_config();
        let ollama_url = if cfg.embeddings.enabled {
            Some("http://127.0.0.1:11434")
        } else {
            None
        };
        let snapshot = crate::hardware::detect(app_data.as_deref(), ollama_url);
        let recommended = tier::recommend_tier(&snapshot);

        let next = {
            let mut w = self.tier_config.write().expect("tier cfg write lock");
            w.detected_tier = recommended;
            w.hardware_snapshot = snapshot;
            w.detected_at_ms = w.hardware_snapshot.detected_at_ms.max(w.detected_at_ms);
            // If selected matches the new detected, drop any manual-
            // override flag — user's choice now coincides with detection.
            if w.selected_tier == recommended {
                w.manual_override = false;
            } else if !w.manual_override {
                // No prior manual override: follow the new detection.
                w.selected_tier = recommended;
            }
            w.clone()
        };
        if let Some(path) = &self.tier_config_path {
            tier::save(path, &next).map_err(|e| format!("persist tier config: {e}"))?;
        }
        Ok(next)
    }

    /// Snapshot the current memory policy. Cheap clone; safe to hand
    /// to a Tauri command response.
    pub fn memory_config(&self) -> MemoryConfig {
        self.memory_config
            .read()
            .expect("memory cfg read lock")
            .clone()
    }

    /// Snapshot of the current ADR-0007 retrieval readiness state.
    /// Read by the `embeddings_readiness` Tauri command and by tests.
    pub fn retrieval_readiness(&self) -> ReadinessState {
        self.retrieval_readiness
            .read()
            .expect("retrieval readiness read lock")
            .clone()
    }

    /// Run the ADR-0007 §Decisions 2 + 8 readiness probe and update
    /// the stored readiness state. Light-usage: pure HTTP GET +
    /// JSON parse + disk check, no model loads. Returns the new
    /// state for callers that want to react synchronously (e.g.
    /// the boot path or a settings-change handler that wants to
    /// emit a transition toast).
    ///
    /// Inputs are read from the live `AppState`:
    /// - `memory_config.embeddings.{enabled, provider}`
    /// - `tier_config.hardware_snapshot.disk_available_gb`
    /// - Ollama base URL: `AETHER_EMBED_OLLAMA_BASE_URL` env var
    ///   or the standard default `http://127.0.0.1:11434`.
    pub fn probe_readiness_now(&self) -> ReadinessState {
        let cfg = self.memory_config();
        let disk = self.tier_config().hardware_snapshot.disk_available_gb;
        let base_url = std::env::var("AETHER_EMBED_OLLAMA_BASE_URL")
            .unwrap_or_else(|_| "http://127.0.0.1:11434".to_string());
        let next = crate::retrieval::probe_readiness(
            cfg.embeddings.enabled,
            cfg.embeddings.provider.as_deref(),
            &base_url,
            disk,
        );
        self.set_retrieval_readiness(next.clone());
        next
    }

    /// Replace the retrieval readiness state. Called by
    /// `run_retrieval_context` on every invocation outcome
    /// (event-driven symmetric cadence per ADR-0007 §Decision 3) and
    /// by the boot / settings-change probes (wired by future commit).
    /// Returns the previous state so callers can detect transitions
    /// and decide whether to emit a Trust-drawer toast.
    pub fn set_retrieval_readiness(&self, next: ReadinessState) -> ReadinessState {
        let mut w = self
            .retrieval_readiness
            .write()
            .expect("retrieval readiness write lock");
        std::mem::replace(&mut *w, next)
    }

    /// Replace the memory policy and persist atomically when a path
    /// is wired. Returns the resulting snapshot so the caller can
    /// echo it back to the UI. Persistence failures surface as `Err`
    /// so the UI can show the change did not stick.
    ///
    /// No L2 consumer yet — step 2 scope. Step 3 wires the write
    /// path through `MemoryConfig::risk_for`.
    pub fn set_memory_config(&self, cfg: MemoryConfig) -> Result<MemoryConfig, String> {
        // Reject embeddings.enabled without a provider — the later
        // embeddings slice can reject at the plumbing layer, but
        // catching this at the policy boundary keeps the Settings UI
        // honest and spares the user a confusing "embeddings on but
        // nothing's happening" state.
        if cfg.embeddings.enabled
            && cfg
                .embeddings
                .provider
                .as_deref()
                .map_or(true, |p| p.trim().is_empty())
        {
            return Err("embeddings.provider must be set before embeddings.enabled = true".into());
        }
        let snapshot = {
            let mut w = self.memory_config.write().expect("memory cfg write lock");
            *w = cfg;
            w.clone()
        };
        if let Some(path) = &self.memory_config_path {
            memory_config::save(path, &snapshot)
                .map_err(|e| format!("persist memory config: {e}"))?;
        }
        // ADR-0007: hot-swap the actual embedding_provider Arc when
        // the user changes embeddings.provider via Settings. Without
        // this, the readiness probe correctly reports "ready for
        // bge-m3" but real embed calls still use whatever model the
        // boot-time env-loaded provider was configured with — silent
        // drift between what UI says and what backend does.
        //
        // Today this handles the `ollama:` prefix (and bare names,
        // treated as ollama). `hf:` and `stub:` prefixes are recognised
        // but only swapped when feature support exists; unknown
        // prefixes warn and leave the existing provider in place so a
        // typo can't brick retrieval.
        if let Some(provider_str) = snapshot.embeddings.provider.as_deref() {
            self.swap_embedding_provider_for_config(provider_str);
        }
        // ADR-0007 D3 — settings-change probe. Re-evaluate readiness
        // whenever the user touches the memory policy; flag flips,
        // provider swaps, and disk reservations all surface here.
        // Light-usage: same HTTP probe as boot, no model loads.
        let _ = self.probe_readiness_now();
        Ok(snapshot)
    }

    /// Hot-swap the embedding_provider Arc to honor a new
    /// `memory.embeddings.provider` value. Called from set_memory_config.
    ///
    /// Provider-string parsing matches the readiness probe's
    /// `parse_model_name` rules:
    /// - `ollama:<model>` -> `OllamaEmbeddingProvider::new(base, model)`
    /// - bare `<model>` (no prefix) -> assume ollama, same as above
    /// - `hf:org/repo` (canonical) or `hf:org:repo:tag` (legacy) ->
    ///   `HfEmbeddingProvider`. Legacy three-segment form is normalised
    ///   to canonical via `HfEmbeddingProvider::normalise_model_id`.
    ///   Helper subprocess spawns lazily on first embed; helper +
    ///   sentence-transformers must be installed for embeds to succeed.
    /// - `stub:<dim>` -> NOT swapped from runtime (test-only seam)
    /// - unknown prefix -> logs warn, no swap
    ///
    /// Empty strings are no-ops (the writer rejects empty providers
    /// when embeddings.enabled = true via set_memory_config's earlier
    /// check, but bare `embeddings.enabled = false` may carry an
    /// empty provider legitimately — silent here).
    fn swap_embedding_provider_for_config(&self, provider_str: &str) {
        let trimmed = provider_str.trim();
        if trimmed.is_empty() {
            return;
        }
        let (prefix, rest) = match trimmed.split_once(':') {
            Some((p, r)) => (p, r),
            None => ("ollama", trimmed),
        };
        match prefix {
            "ollama" => {
                let base = std::env::var("AETHER_EMBED_OLLAMA_BASE_URL")
                    .unwrap_or_else(|_| aether_l2_memory::DEFAULT_OLLAMA_BASE_URL.to_string());
                let new_provider: Arc<dyn EmbeddingProvider> =
                    Arc::new(OllamaEmbeddingProvider::new(base, rest));
                if let Ok(mut w) = self.embedding_provider.write() {
                    *w = new_provider;
                    tracing::info!("embedding provider swapped to ollama:{rest}");
                } else {
                    tracing::warn!("embedding provider lock poisoned; swap skipped");
                }
            }
            "hf" => {
                let model = HfEmbeddingProvider::normalise_model_id(rest);
                let new_provider: Arc<dyn EmbeddingProvider> =
                    Arc::new(HfEmbeddingProvider::new(&model));
                if let Ok(mut w) = self.embedding_provider.write() {
                    *w = new_provider;
                    tracing::info!(
                        "embedding provider swapped to hf:{model} \
                         (helper subprocess will spawn on first embed; \
                         requires sentence-transformers Python install)"
                    );
                } else {
                    tracing::warn!("embedding provider lock poisoned; swap skipped");
                }
            }
            "stub" => {
                // Stub providers are test-only; the runtime path doesn't
                // swap to them. Production set_memory_config calls with
                // stub: prefix only happen in tests that explicitly want
                // to leave the test-injected stub in place.
                tracing::debug!("stub: prefix provider — no swap (test seam)");
            }
            other => {
                tracing::warn!(
                    "unknown embedding provider prefix '{other}' \
                     (configured: {provider_str}); existing provider unchanged"
                );
            }
        }
    }

    /// Access the per-domain read counter for the Memory V2 sampled
    /// audit path. Every domain is populated at `build()` time so the
    /// `get` is infallible; an unknown domain would indicate a
    /// contract drift (`MemoryDomain::ALL` out of sync with the
    /// field init) and panics loudly rather than silently skipping
    /// the audit sample.
    pub fn memory_read_counter(&self, domain: MemoryDomain) -> &AtomicU64 {
        self.memory_read_counters
            .get(&domain)
            .expect("memory_read_counters must contain every MemoryDomain — see build()")
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
            let catalog = self.catalog.read().expect("catalog read lock");
            catalog
                .iter()
                .find(|p| p.persona_id.0 == active.compiled.persona_id.0)
                .cloned()
                .ok_or_else(|| "active persona missing from catalog".to_string())?
        };
        let new_active = build_active(
            &profile,
            self.memory.clone(),
            preset,
            self.files_executor_handle.clone(),
        )?;
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

    /// Register a pending approval keyed on `ticket_id`. Wave 11 widened
    /// the value type from `PendingTurn` to `PendingApproval` so the same
    /// registry holds both chat-surface (`PendingTurn`) and executor
    /// (`PendingExecutorCall`) flavours; existing call sites that record
    /// a `PendingTurn` should wrap it in
    /// `PendingApproval::Turn(...)` at the call site.
    pub fn record_pending(&self, ticket_id: String, pending: PendingApproval) {
        let mut g = self.pending.lock().expect("pending lock");
        g.insert(ticket_id, pending);
    }

    /// Remove and return the pending approval for `ticket_id`. The caller
    /// dispatches on the variant — `Turn` replays `handle_turn`, `Executor`
    /// replays the originally-attempted command.
    pub fn take_pending(&self, ticket_id: &str) -> Option<PendingApproval> {
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
        let catalog = self.catalog.read().expect("catalog read lock");
        catalog.iter().map(profile_to_entry).collect()
    }

    /// Re-scan `AETHER_PERSONAS_DIR` and merge any newly-installed
    /// flat-schema YAML packs into the live catalog. Called after a
    /// Tier-2 install lands a pack on disk so the wizard / picker can
    /// see the new persona without a shell restart (ADR-0012). Existing
    /// entries with the same id are not replaced — same merge rule as
    /// boot-time `merge_yaml_personas`.
    ///
    /// Returns the number of newly-added personas.
    pub fn refresh_catalog(&self) -> usize {
        let mut catalog = self.catalog.write().expect("catalog write lock");
        let before = catalog.len();
        let merged = merge_yaml_personas(catalog.clone());
        *catalog = merged;
        catalog.len().saturating_sub(before)
    }

    /// Swap the active persona. Clears session state (memory, presence,
    /// pending approvals) and rebuilds the engine / policy / audit
    /// against the new persona's defaults. Audit chain is reset because
    /// a different persona is a different trust surface.
    pub fn switch_persona(&self, id: &str) -> Result<(), String> {
        let profile = {
            let catalog = self.catalog.read().expect("catalog read lock");
            catalog
                .iter()
                .find(|p| p.persona_id.0 == id)
                .ok_or_else(|| format!("unknown persona: {id}"))?
                .clone()
        };
        let preset = self.current_preset();
        let new_active = build_active(
            &profile,
            self.memory.clone(),
            preset,
            self.files_executor_handle.clone(),
        )?;
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

/// Wave 13b — best-effort seed of the executor's allowlist from the
/// active File-capability grants in `ledger`. Called once per
/// `build_active` invocation (boot + every engine rebuild). Each path
/// is canonicalized individually; a failure (volume unmounted, dir
/// deleted) drops that one path from the new allowlist instead of
/// aborting. An empty resulting allowlist is correct — every
/// `files_*` invocation falls through to `FilesExecError::NotInScope`,
/// which matches the pre-Wave-13b behaviour the call sites already
/// tolerate.
fn seed_executor_allowlist_from_ledger(
    ledger: &dyn aether_l5_policy::GrantLedger,
    executor: &aether_l5_files::std_fs_stub::StdFsExecutor,
) {
    use aether_l5_files::ScopeAllowlist;
    use aether_l5_policy::{Capability, GrantFilter, ResourceScope};

    let active = ledger.snapshot(&GrantFilter {
        active_only: true,
        ..Default::default()
    });
    let mut canonical: Vec<PathBuf> = Vec::new();
    for grant in active.iter() {
        let is_files_cap = matches!(
            grant.capability,
            Capability::FilesRead
                | Capability::FilesCreate
                | Capability::FilesEdit
                | Capability::FilesRenameMove
                | Capability::FilesDelete
                | Capability::FilesBulkOp
        );
        if !is_files_cap {
            continue;
        }
        let raw = match &grant.resource_pattern {
            ResourceScope::Path(s) => PathBuf::from(s),
            _ => continue,
        };
        match std::fs::canonicalize(&raw) {
            Ok(c) => canonical.push(c),
            Err(e) => {
                tracing::warn!(
                    "build_active: dropping un-canonicalizable grant path {}: {}",
                    raw.display(),
                    e
                );
            }
        }
    }
    executor.set_allowlist(ScopeAllowlist::new(canonical));
}

/// Build every swappable engine piece for the given profile.
///
/// Wave 13b — `files_executor_handle` is the live `StdFsExecutor` whose
/// allowlist will be kept in sync with the engine's grant ledger via
/// [`ExecutorAllowlistSink`]. Each engine rebuild (boot, persona swap,
/// preset change) gets a fresh ledger + audit; the executor handle is
/// re-used, and the new sink seeds it from the (empty) fresh ledger so
/// stale grants from the prior persona do not leak across.
fn build_active(
    profile: &PersonaProfile,
    memory: Arc<dyn SessionMemoryStore>,
    preset: Option<AutonomyPreset>,
    files_executor_handle: Arc<aether_l5_files::std_fs_stub::StdFsExecutor>,
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
    // Wave 13b — concrete ledger handle is shared between the engine
    // and the `ExecutorAllowlistSink` so the sink can re-snapshot active
    // grants on every issue/revoke event.
    let ledger: Arc<dyn aether_l5_policy::GrantLedger> = Arc::new(InMemoryGrantLedger::new());
    // Inner sink stays the existing `InMemorySink::new()` — preserved
    // for any future test/diag consumer that reads from it.
    let inner_sink: Arc<dyn aether_l5_policy::L5EventSink> = Arc::new(InMemorySink::new());
    let allowlist_sink: Arc<dyn aether_l5_policy::L5EventSink> =
        Arc::new(crate::policy_sink::ExecutorAllowlistSink::new(
            inner_sink,
            ledger.clone(),
            files_executor_handle.clone(),
        ));
    // Boot-time / rebuild-time seed: snapshot the (empty on first build,
    // possibly populated after a future persistence load) ledger and
    // mirror its active File-capability grants into the executor's
    // allowlist BEFORE the engine begins handing out `Allow`s.
    seed_executor_allowlist_from_ledger(&*ledger, &files_executor_handle);
    let policy: Arc<dyn PolicyEngine> = Arc::new(DefaultPolicyEngine::new(
        cfg,
        ledger,
        audit.clone(),
        allowlist_sink,
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
/// per `docs/PERSONA-SCHEMA.md`.
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

    /// Process-wide lock shared by every test in this module that
    /// mutates `AETHER_PERSONAS_DIR` — or any other env var read by
    /// `AppState::new`. Previously each env-touching test declared
    /// its own function-scoped `static` mutex, which looked like
    /// serialisation but wasn't: function-scope `static` items are
    /// unique per function, so two tests declaring
    /// `static ENV_LOCK: Mutex<()>` hold distinct locks. Under
    /// parallel execution that left
    /// `yaml_persona_pack_merges_into_catalog` and
    /// `yaml_persona_id_collision_with_builtin_is_skipped` racing
    /// each other through `AETHER_PERSONAS_DIR`. Hoisting the lock
    /// to module scope fixes this at the source; see
    /// `HANDOFF_2026-05-17_SESSION_END_ULTRA_LONG_SETUP.md` Risk E.
    ///
    /// Handles lock poisoning internally so a panic inside a guarded
    /// test only poisons the lock, which the next test recovers
    /// from.
    static STATE_TESTS_ENV_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    /// Acquire the env lock, returning a guard that releases the
    /// mutex when dropped. Paired with a `TempDir` + scoped env
    /// pattern in each env-touching test.
    fn state_tests_env_lock() -> std::sync::MutexGuard<'static, ()> {
        STATE_TESTS_ENV_LOCK
            .lock()
            .unwrap_or_else(|e| e.into_inner())
    }

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
            original_utterance: "edit /tmp/x".into(),
            model_input_utterance: "edit /tmp/x".into(),
            capability: Capability::FilesEdit,
            resource: ResourceScope::Path("/tmp/x".into()),
            emitted_at: MonotonicTimestamp(state.next_ts()),
            retrieval_provenance: None,
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
            PendingApproval::Turn(PendingTurn {
                request: req.clone(),
                ask_result: ask_result.clone(),
                original_utterance: req.original_utterance.clone(),
            }),
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
        let pending = match state
            .take_pending(&ticket.ticket_id.0)
            .expect("pending ticket")
        {
            PendingApproval::Turn(t) => t,
            PendingApproval::Executor { .. } => panic!("expected Turn, got Executor"),
        };
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
            original_utterance: "edit /tmp/y".into(),
            model_input_utterance: "edit /tmp/y".into(),
            capability: Capability::FilesEdit,
            resource: ResourceScope::Path("/tmp/y".into()),
            emitted_at: MonotonicTimestamp(state.next_ts()),
            retrieval_provenance: None,
        };
        let ask = {
            let a = state.active.read().unwrap();
            a.engine.handle_turn(req.clone()).unwrap()
        };
        let ticket = match &ask.policy_decision {
            Decision::Ask { ticket, .. } => ticket.clone(),
            other => panic!("expected Ask, got {other:?}"),
        };
        let utter = req.original_utterance.clone();
        state.record_pending(
            ticket.ticket_id.0.clone(),
            PendingApproval::Turn(PendingTurn {
                request: req,
                ask_result: ask,
                original_utterance: utter,
            }),
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
            original_utterance: "read /tmp/z".into(),
            model_input_utterance: "read /tmp/z".into(),
            capability: Capability::FilesRead,
            resource: ResourceScope::Path("/tmp/z".into()),
            emitted_at: MonotonicTimestamp(state.next_ts()),
            retrieval_provenance: None,
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
                model: None,
                latency_ms: Some(100 + i as u64),
                prompt_tokens: None,
                completion_tokens: None,
                memory_domain: None,
                memory_id: None,
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
    /// RAII wrapper that holds the shared env lock and restores the
    /// previous `AETHER_PERSONAS_DIR` value on drop — including the
    /// panic path. Required because a panic inside a test after
    /// `set_var` would leave the process-wide env var pointing at a
    /// `TempDir` that's about to be cleaned up, poisoning any
    /// subsequent `AppState::new` that reads the directory.
    struct PersonasDirGuard {
        _lock: std::sync::MutexGuard<'static, ()>,
        previous: Option<std::ffi::OsString>,
    }

    impl PersonasDirGuard {
        fn with(dir: &std::path::Path) -> Self {
            let _lock = state_tests_env_lock();
            let previous = std::env::var_os("AETHER_PERSONAS_DIR");
            std::env::set_var("AETHER_PERSONAS_DIR", dir);
            Self { _lock, previous }
        }
    }

    impl Drop for PersonasDirGuard {
        fn drop(&mut self) {
            match self.previous.take() {
                Some(v) => std::env::set_var("AETHER_PERSONAS_DIR", v),
                None => std::env::remove_var("AETHER_PERSONAS_DIR"),
            }
        }
    }

    #[test]
    fn yaml_persona_pack_merges_into_catalog() {
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

        let _env = PersonasDirGuard::with(tmp.path());
        let state = AppState::new().expect("AppState::new");

        let ids: Vec<String> = state.catalog_entries().into_iter().map(|e| e.id).collect();
        assert!(ids.contains(&"aurora".to_string()));
        assert!(
            ids.contains(&"solstice".to_string()),
            "YAML persona should appear in catalog; saw {ids:?}"
        );
    }

    #[test]
    fn refresh_catalog_picks_up_yaml_pack_dropped_after_boot() {
        // ADR-0012 Tier-2 install flow: a freshly installed pack lands
        // on disk after AppState boot, and `refresh_catalog` must let
        // the live catalog see it without a shell restart.
        let tmp = tempfile::TempDir::new().unwrap();
        let _env = PersonasDirGuard::with(tmp.path());

        // Boot with an empty persona dir → catalog is the built-ins only.
        let state = AppState::new().expect("AppState::new");
        let before: Vec<String> = state.catalog_entries().into_iter().map(|e| e.id).collect();
        assert!(
            !before.contains(&"freshpick".to_string()),
            "precondition: freshpick must not be in the built-in catalog"
        );

        // Drop a new flat-schema pack into the dir AFTER boot.
        let yaml = r#"
id: "freshpick"
version: 1
name: "FreshPick"
description: "Installed live."
tone: "warm"
verbosity: "balanced"
stance: "balanced"
humor: "dry"
"#;
        std::fs::write(tmp.path().join("freshpick.yaml"), yaml).unwrap();

        // Catalog should still NOT see it before refresh.
        let mid: Vec<String> = state.catalog_entries().into_iter().map(|e| e.id).collect();
        assert!(
            !mid.contains(&"freshpick".to_string()),
            "catalog must not auto-rescan; saw {mid:?}"
        );

        // Refresh — exactly one new persona should appear, and the
        // live catalog must include `freshpick`.
        let added = state.refresh_catalog();
        assert_eq!(added, 1, "refresh_catalog should report 1 new entry");
        let after: Vec<String> = state.catalog_entries().into_iter().map(|e| e.id).collect();
        assert!(
            after.contains(&"freshpick".to_string()),
            "freshpick should be in catalog after refresh; saw {after:?}"
        );
    }

    #[test]
    fn refresh_catalog_is_idempotent() {
        // Calling refresh twice with no on-disk change must report
        // zero additions on the second call. Guards against duplicate
        // entries growing the catalog on every install attempt.
        let tmp = tempfile::TempDir::new().unwrap();
        let yaml = r#"
id: "twice"
version: 1
name: "Twice"
description: "Second refresh must not duplicate."
tone: "warm"
verbosity: "balanced"
stance: "balanced"
humor: "dry"
"#;
        std::fs::write(tmp.path().join("twice.yaml"), yaml).unwrap();
        let _env = PersonasDirGuard::with(tmp.path());

        let state = AppState::new().expect("AppState::new");
        // Pack was present at boot, so it's already merged.
        assert_eq!(state.refresh_catalog(), 0);
        assert_eq!(state.refresh_catalog(), 0);
        let ids: Vec<String> = state.catalog_entries().into_iter().map(|e| e.id).collect();
        let count = ids.iter().filter(|id| id.as_str() == "twice").count();
        assert_eq!(count, 1, "expected exactly one `twice` entry, saw {ids:?}");
    }

    #[test]
    fn yaml_persona_id_collision_with_builtin_is_skipped() {
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

        let _env = PersonasDirGuard::with(tmp.path());
        let state = AppState::new().expect("AppState::new");

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
            model: None,
            latency_ms: None,
            prompt_tokens: None,
            completion_tokens: None,
            memory_domain: None,
            memory_id: None,
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
            original_utterance: "edit /tmp/observer".into(),
            model_input_utterance: "edit /tmp/observer".into(),
            capability: Capability::FilesEdit,
            resource: ResourceScope::Path("/tmp/observer".into()),
            emitted_at: MonotonicTimestamp(state.next_ts()),
            retrieval_provenance: None,
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

    /// Mic permission defaults to `Ask` at boot and the gate maps to
    /// `PromptUser` accordingly — same "never auto-grant" rule as
    /// camera/screen.
    #[test]
    fn mic_permission_defaults_to_ask_after_boot() {
        let state = AppState::new().unwrap();
        assert_eq!(state.mic_permission().state, PermissionState::Ask);
        assert_eq!(state.evaluate_mic_permission(), CaptureGate::PromptUser);
    }

    /// `set_mic_permission` updates the in-memory snapshot and shifts
    /// the capture gate accordingly. Without an attached file it is a
    /// pure in-process change — exercised here so the no-file path
    /// keeps working in tests / sandboxes.
    #[test]
    fn set_mic_permission_updates_snapshot_and_gate() {
        let state = AppState::new().unwrap();
        let snap = state
            .set_mic_permission(PermissionState::Allow)
            .expect("set");
        assert_eq!(snap.state, PermissionState::Allow);
        assert_eq!(state.evaluate_mic_permission(), CaptureGate::Proceed);

        let snap = state
            .set_mic_permission(PermissionState::Deny)
            .expect("set");
        assert_eq!(snap.state, PermissionState::Deny);
        assert_eq!(state.evaluate_mic_permission(), CaptureGate::Deny);
    }

    /// With a mic-permission file attached, writes round-trip through
    /// disk — a fresh AppState pointing at the same file recovers the
    /// previously-saved posture instead of resetting to defaults.
    #[test]
    fn mic_permission_file_round_trips_across_appstates() {
        let tmp = tempfile::TempDir::new().unwrap();
        let mic_path = tmp.path().join("mic_permissions.json");

        {
            let mut state = AppState::new().unwrap();
            state.attach_mic_permission_file(mic_path.clone());
            state.set_mic_permission(PermissionState::Allow).unwrap();
        }

        let mut state2 = AppState::new().unwrap();
        state2.attach_mic_permission_file(mic_path);
        assert_eq!(state2.mic_permission().state, PermissionState::Allow);
    }

    /// Mic and camera/screen permission files are independent: a write
    /// to one must not bleed into the other. This locks the "distinct
    /// consent boundaries" promise called out in mic_permissions.rs.
    #[test]
    fn mic_permission_is_independent_from_media_permissions() {
        let tmp = tempfile::TempDir::new().unwrap();
        let media_path = tmp.path().join("media_permissions.json");
        let mic_path = tmp.path().join("mic_permissions.json");

        let mut state = AppState::new().unwrap();
        state.attach_media_permissions_file(media_path);
        state.attach_mic_permission_file(mic_path);

        state
            .set_mic_permission(PermissionState::Allow)
            .expect("mic set");
        let media = state.media_permissions();
        assert_eq!(media.camera, PermissionState::Ask);
        assert_eq!(media.screen, PermissionState::Ask);

        state
            .set_media_permission(MediaKind::Camera, PermissionState::Deny)
            .expect("media set");
        let mic = state.mic_permission();
        assert_eq!(mic.state, PermissionState::Allow);
    }

    // --- Presence V1 step 2 — attention state wiring --------------------

    #[test]
    fn set_presence_config_rejects_out_of_range_thresholds() {
        let state = AppState::new().unwrap();
        let mut cfg = state.presence_config();
        cfg.idle_after_s = 5;
        assert!(
            state.set_presence_config(cfg).is_err(),
            "too small rejected"
        );
        let mut cfg = state.presence_config();
        cfg.idle_after_s = 100_000;
        assert!(state.set_presence_config(cfg).is_err(), "too big rejected");
    }

    #[test]
    fn set_presence_config_rejects_away_le_idle() {
        let state = AppState::new().unwrap();
        let mut cfg = state.presence_config();
        cfg.idle_after_s = 300;
        cfg.away_after_s = 300;
        assert!(
            state.set_presence_config(cfg).is_err(),
            "away must be > idle"
        );
    }

    #[test]
    fn set_presence_config_hot_swaps_attention_thresholds_and_enabled() {
        // Locks the controller contract from the user's perspective: a
        // Settings-UI write must take effect without restart.
        let state = AppState::new().unwrap();
        let mut cfg = state.presence_config();
        cfg.enabled = false;
        cfg.idle_after_s = 20;
        cfg.away_after_s = 40;
        state.set_presence_config(cfg).expect("persisted");
        let thresholds = state.attention.thresholds();
        assert_eq!(thresholds.idle_after_s, 20);
        assert_eq!(thresholds.away_after_s, 40);
        let snap = state.attention_snapshot();
        assert!(!snap.enabled, "enabled flag propagated");
    }

    #[test]
    fn attention_tick_and_history_record_transition() {
        let state = AppState::new().unwrap();
        let mut cfg = state.presence_config();
        cfg.idle_after_s = 10;
        cfg.away_after_s = 30;
        state.set_presence_config(cfg).unwrap();

        // Tick with idle reading under threshold: silent.
        assert!(state.attention_tick(1_000, Some(0)).is_none());
        assert!(state.presence_history_recent(10).is_empty());

        // Tick past idle_after_s: transition fires and the shell
        // pushes a `presence_state_changed` row on the ring.
        let ev = state.attention_tick(11_000, Some(15)).expect("→ idle");
        let entry = PresenceHistoryEntry {
            kind: "presence_state_changed".into(),
            from: ev.from.label().into(),
            to: ev.to.label().into(),
            idle_seconds: ev.idle_seconds,
            at_ms: ev.at_ms,
        };
        state.push_presence_history(entry);
        let recent = state.presence_history_recent(10);
        assert_eq!(recent.len(), 1);
        assert_eq!(recent[0].kind, "presence_state_changed");
        assert_eq!(recent[0].from, "active");
        assert_eq!(recent[0].to, "idle");
    }

    #[test]
    fn disabled_presence_controller_never_emits() {
        let state = AppState::new().unwrap();
        let mut cfg = state.presence_config();
        cfg.enabled = false;
        cfg.idle_after_s = 10;
        cfg.away_after_s = 30;
        state.set_presence_config(cfg).unwrap();
        // Even with idle seconds well past the threshold, a disabled
        // controller is silent.
        assert!(state.attention_tick(10_000, Some(500)).is_none());
    }

    #[test]
    fn presence_history_ring_is_bounded() {
        let state = AppState::new().unwrap();
        for i in 0..(PRESENCE_HISTORY_CAPACITY + 10) {
            state.push_presence_history(PresenceHistoryEntry {
                kind: "presence_state_changed".into(),
                from: "active".into(),
                to: "idle".into(),
                idle_seconds: 0,
                at_ms: i as u64,
            });
        }
        assert_eq!(
            state.presence_history_recent(usize::MAX).len(),
            PRESENCE_HISTORY_CAPACITY
        );
    }

    #[test]
    fn set_memory_config_swaps_embedding_provider_for_ollama_prefix() {
        // ADR-0007 hot-swap: configuring a new ollama: provider via
        // memory_config must replace the in-memory embedding_provider
        // Arc, not just persist the string. Verifies the label of the
        // active provider changes after the swap.
        let state = AppState::new().expect("state");
        let initial_label = state
            .embedding_provider
            .read()
            .expect("provider read lock")
            .label();
        let mut cfg = state.memory_config();
        cfg.embeddings.enabled = true;
        cfg.embeddings.provider = Some("ollama:bge-m3-test-marker".into());
        state.set_memory_config(cfg).expect("set_memory_config");
        let new_label = state
            .embedding_provider
            .read()
            .expect("provider read lock")
            .label();
        assert_ne!(
            initial_label, new_label,
            "provider label must change after ollama: swap"
        );
        assert!(
            new_label.contains("bge-m3-test-marker"),
            "new label should reflect the configured model name; got {new_label}"
        );
    }

    #[test]
    fn set_memory_config_swap_handles_bare_model_name_as_ollama() {
        // No prefix → assumed ollama. The provider should still swap.
        let state = AppState::new().expect("state");
        let mut cfg = state.memory_config();
        cfg.embeddings.enabled = true;
        cfg.embeddings.provider = Some("snowflake-arctic-test".into());
        state.set_memory_config(cfg).expect("set_memory_config");
        let label = state
            .embedding_provider
            .read()
            .expect("provider read lock")
            .label();
        assert!(
            label.contains("snowflake-arctic-test"),
            "bare name should swap to ollama:<name>; got {label}"
        );
    }

    #[test]
    fn set_memory_config_swaps_for_hf_canonical_prefix() {
        // hf:org/repo (canonical HF Hub form) MUST swap to a real
        // HfEmbeddingProvider. The provider label proves the swap took
        // effect; we don't actually call embed() here (which would
        // spawn the Python helper). Helper-spawn behaviour is tested
        // in packages/l2-memory/src/hf_provider.rs.
        let state = AppState::new().expect("state");
        let initial_label = state
            .embedding_provider
            .read()
            .expect("provider read lock")
            .label();
        let mut cfg = state.memory_config();
        cfg.embeddings.enabled = true;
        cfg.embeddings.provider = Some("hf:BAAI/bge-small-en-v1.5".into());
        state.set_memory_config(cfg).expect("set_memory_config");
        let after_label = state
            .embedding_provider
            .read()
            .expect("provider read lock")
            .label();
        assert_ne!(
            initial_label, after_label,
            "hf:org/repo must swap (was previously a warn-only no-op)"
        );
        assert_eq!(after_label, "hf:BAAI/bge-small-en-v1.5");
    }

    #[test]
    fn set_memory_config_swap_normalises_legacy_hf_three_segment_form() {
        // Legacy memory.json may carry `hf:BAAI:bge-small-en-v1.5`
        // (three colons, not org/repo). The swap must normalise to
        // canonical org/repo so HF Hub recognises it.
        let state = AppState::new().expect("state");
        let mut cfg = state.memory_config();
        cfg.embeddings.enabled = true;
        cfg.embeddings.provider = Some("hf:BAAI:bge-small-en-v1.5".into());
        state.set_memory_config(cfg).expect("set_memory_config");
        let label = state
            .embedding_provider
            .read()
            .expect("provider read lock")
            .label();
        assert_eq!(
            label, "hf:BAAI/bge-small-en-v1.5",
            "legacy three-segment hf id must normalise to org/repo"
        );
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

    // -----------------------------------------------------------------
    // Wave 13b — boot seed + grant-event allowlist plumbing.
    // -----------------------------------------------------------------

    /// Boot wires `files_executor` and `files_executor_handle` to the
    /// SAME backing executor (Arc-shared scope state per Wave 13a).
    /// Mutating the allowlist via the handle must be observable through
    /// the trait-object surface.
    #[tokio::test]
    async fn files_executor_and_handle_share_scope_state() {
        use aether_l5_files::{FilesExecutor, ScopeAllowlist};

        let state = AppState::new().expect("AppState::new");
        let dir = tempfile::TempDir::new().unwrap();
        let path = dir.path().join("hi.txt");
        std::fs::write(&path, b"hi").unwrap();

        // Boot allowlist is empty (the ledger is empty on first build)
        // — the trait-object read rejects.
        let err = state.files_executor.read(&path).await.unwrap_err();
        assert!(
            matches!(err, aether_l5_files::FilesExecError::NotInScope(_)),
            "got {err:?}"
        );

        // Mutate the allowlist via the concrete handle.
        let canonical = std::fs::canonicalize(dir.path()).unwrap();
        state
            .files_executor_handle
            .set_allowlist(ScopeAllowlist::new([canonical]));

        // The trait-object surface sees the new scope immediately.
        let bytes = state.files_executor.read(&path).await.unwrap();
        assert_eq!(bytes, b"hi");
    }

    /// `seed_executor_allowlist_from_ledger` must mirror an active
    /// `FilesRead` grant's path into the executor's allowlist and
    /// ignore non-File grants. Tests the boot helper directly without
    /// rebuilding `AppState`.
    #[tokio::test]
    async fn seed_helper_mirrors_active_files_grants() {
        use aether_l5_files::{FilesExecutor, ScopeAllowlist};
        use aether_l5_policy::{
            ApprovalMode, ApprovalScope, Grant, GrantDuration, GrantId, GrantLedger,
            InMemoryGrantLedger, MonotonicTimestamp, PersonaId, ResourceScope,
        };

        let dir = tempfile::TempDir::new().unwrap();
        let canonical = std::fs::canonicalize(dir.path()).unwrap();
        let file = dir.path().join("h.txt");
        std::fs::write(&file, b"x").unwrap();

        let executor = aether_l5_files::std_fs_stub::StdFsExecutor::default();
        // Pre-condition: empty ledger seeds an empty allowlist (no-op).
        let empty_ledger = InMemoryGrantLedger::new();
        seed_executor_allowlist_from_ledger(&empty_ledger, &executor);
        let err = executor.read(&file).await.unwrap_err();
        assert!(
            matches!(err, aether_l5_files::FilesExecError::NotInScope(_)),
            "got {err:?}"
        );

        // Populate the ledger with one File grant + one non-File grant.
        let ledger = InMemoryGrantLedger::new();
        ledger
            .issue(Grant {
                grant_id: GrantId("file-g".to_string()),
                capability: aether_l5_policy::Capability::FilesRead,
                resource_pattern: ResourceScope::Path(canonical.display().to_string()),
                persona_id: PersonaId("test".to_string()),
                approval_mode: ApprovalMode::Ask,
                duration: GrantDuration::Session,
                issued_at: MonotonicTimestamp(0),
                expires_at: None,
                preset_version_issued_under: 0,
                approval_scope: Some(ApprovalScope::PerAction),
            })
            .expect("issue file grant");
        ledger
            .issue(Grant {
                grant_id: GrantId("url-g".to_string()),
                capability: aether_l5_policy::Capability::BrowserOpen,
                resource_pattern: ResourceScope::Url("https://example.com".to_string()),
                persona_id: PersonaId("test".to_string()),
                approval_mode: ApprovalMode::Ask,
                duration: GrantDuration::Session,
                issued_at: MonotonicTimestamp(0),
                expires_at: None,
                preset_version_issued_under: 0,
                approval_scope: Some(ApprovalScope::PerAction),
            })
            .expect("issue url grant");

        // Reset to empty (sanity), then seed.
        executor.set_allowlist(ScopeAllowlist::default());
        seed_executor_allowlist_from_ledger(&ledger, &executor);

        // The File grant widened the scope; the URL grant did not.
        let bytes = executor.read(&file).await.unwrap();
        assert_eq!(bytes, b"x");
    }
}
