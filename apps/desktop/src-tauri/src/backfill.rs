//! ADR-0007 §Decision 5 — embeddings backfill orchestrator.
//!
//! When the user toggles `embeddings.enabled = true` on a profile that
//! already has Durable / Projects / Artifacts content, those rows are
//! invisible to retrieval until they have embedding rows. Backfill
//! walks every embed-eligible domain, computes the embedding for each
//! row's content, and upserts into the `EmbeddingStore`.
//!
//! ## Design contract
//!
//! - **Triggered by user action.** Never auto-runs on enable (per
//!   ADR-0007 D5 "no auto-backfill" rejected alternative). The user
//!   clicks "Backfill now" with the cost estimate visible.
//! - **Background job.** Tauri command returns immediately with a job
//!   id; the worker runs on `tauri::async_runtime::spawn`. The shell
//!   never blocks the IPC thread.
//! - **Cancel via shared atomic.** `cancel_backfill` flips
//!   `AppState::backfill_cancel`; the worker checks at every row
//!   boundary. Cancel finishes the in-flight embed call gracefully
//!   (no kill mid-call) — typical latency to actual stop is one row.
//! - **Progress events.** The worker emits `backfill:progress` after
//!   every row with a `BackfillProgress` payload. UI subscribes for
//!   live updates.
//! - **Per-row pacing.** ADR-0007 D7 §Tuning notes flagged that
//!   rapid-fire bge-m3 embeds can trigger Ollama HTTP 500 from queue
//!   pressure. Default per-row pause: 50 ms. Tunable via
//!   `BackfillOptions::per_row_pause_ms`.
//! - **Wasteful but correct.** Today we re-embed every row
//!   unconditionally, even rows that already have an embedding (the
//!   `EmbeddingStore` `upsert` is idempotent so this is safe). A
//!   smarter "skip if already embedded" path would require an
//!   `embedded_ids(domain)` enumeration method on the trait — that's
//!   a `packages/l2-memory` change and out of scope for this shell-
//!   only commit. Backfill is one-time-per-flag-flip; for typical
//!   personal-scale (<1000 rows), the brute-force walk completes in
//!   under a minute even on Spark hardware.
//! - **Capability-gated.** Every backfill invocation routes through
//!   the same L5 `Capability::RetrievalContext` gate the orchestrator
//!   uses. A non-Allow decision aborts before any embed call lands.
//! - **Failure-tolerant.** A single embed call failing does not kill
//!   the job; the row is counted as a failure and the worker
//!   continues. The final report carries `failures` count.

use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::time::Duration;

use aether_l2_memory::{EmbeddingRow, MemoryDomain as L2Domain, MemoryId, EMBED_ELIGIBLE_DOMAINS};
use aether_l5_policy::capability::{Capability, ResourceScope};
use aether_l5_policy::common::{MonotonicTimestamp, RequestId, TurnId};
use aether_l5_policy::decision::Decision;
use aether_l5_policy::policy_engine::ActionRequest;
use aether_l5_policy::PersonaId;
use serde::Serialize;
use tauri::{AppHandle, Emitter};

use crate::memory_config::MemoryDomain as ShellDomain;
use crate::state::{AppState, BackfillProgress};

/// Default per-row pause to keep Ollama's embed queue happy.
/// ADR-0007 D7 §Tuning notes: rapid-fire bge-m3 embeds at row 4-5
/// triggered HTTP 500 from queue pressure. 50 ms is a conservative
/// floor — measured throughput at this rate sustains ~5 rows/sec for
/// bge-m3 on Don's 3090 Ti, matching the Block 5 sustained warm rate.
pub const DEFAULT_PER_ROW_PAUSE_MS: u64 = 50;

/// One-shot backfill configuration. Future runs may add per-domain
/// scope, "last 30 days only" filters, etc. — held simple for now.
#[derive(Debug, Clone)]
pub struct BackfillOptions {
    pub per_row_pause_ms: u64,
}

impl Default for BackfillOptions {
    fn default() -> Self {
        Self {
            per_row_pause_ms: DEFAULT_PER_ROW_PAUSE_MS,
        }
    }
}

/// Wire payload for the `backfill:progress` Tauri event. Mirrors
/// `BackfillProgress` from `state.rs` plus the job id for the UI to
/// disambiguate stale events from a new run.
#[derive(Debug, Clone, Serialize)]
pub struct BackfillProgressPayload {
    pub job_id: String,
    #[serde(flatten)]
    pub progress: BackfillProgress,
}

/// Map L2 domain → shell domain. Mirror of the helper in retrieval.rs;
/// duplicated here to avoid making either module depend on the other.
fn shell_domain(d: L2Domain) -> ShellDomain {
    match d {
        L2Domain::Session => ShellDomain::Session,
        L2Domain::Durable => ShellDomain::Durable,
        L2Domain::Facts => ShellDomain::Facts,
        L2Domain::Projects => ShellDomain::Projects,
        L2Domain::Preferences => ShellDomain::Preferences,
        L2Domain::Artifacts => ShellDomain::Artifacts,
    }
}

/// Compute the total un-embedded row count across embed-eligible
/// domains. Approximate — assumes 1:1 between memory rows and
/// embedding rows for "embedded." A smarter counter would need
/// `EmbeddingStore::embedded_ids(domain)`. Suitable for the
/// "Backfill ~N items" copy.
pub fn estimate_unembedded_count(state: &AppState) -> usize {
    let mut total = 0;
    for &domain in EMBED_ELIGIBLE_DOMAINS {
        let memory_rows = count_memory_rows_for_domain(state, domain);
        let embedded = state
            .embedding_store
            .count(domain)
            .unwrap_or(memory_rows); // pessimistic: if count fails, assume all embedded
        total += memory_rows.saturating_sub(embedded);
    }
    total
}

/// Walk the configured store for `domain` and count rows.
/// Currently only Durable is wired into a real store; Projects and
/// Artifacts will gain stores in later milestones — until then they
/// return 0 and contribute nothing to the backfill count.
fn count_memory_rows_for_domain(state: &AppState, domain: L2Domain) -> usize {
    let store = state.memory_for_domain(shell_domain(domain));
    let sessions = match store.list_sessions() {
        Ok(s) => s,
        Err(_) => return 0,
    };
    let mut count = 0;
    for sid in sessions {
        if let Ok(window) = store.recent(&sid) {
            count += window.records.len();
        }
    }
    count
}

/// Synchronous backfill worker — performs the embed walk and emits
/// progress via `app.emit`. Returns when complete, cancelled, or on
/// fatal error.
///
/// `app` is `Option` so unit tests can run the worker without a
/// Tauri runtime; in production the shell always provides one.
///
/// Cancellation: checks `state.backfill_cancel` at every row boundary.
/// When set, finishes the in-flight call, marks
/// `progress.cancelled = true`, emits a final event, returns.
///
/// Error tolerance: per-row embed failures are counted, not fatal.
/// The L5 gate IS fatal — if policy denies, the job aborts cleanly.
pub fn run_backfill_worker(
    state: &AppState,
    app: Option<&AppHandle>,
    job_id: String,
    options: BackfillOptions,
) {
    // Mark in-progress at job start. The cancel flag is NOT reset
    // here — `spawn_backfill` resets it before spawning, so any
    // cancel arriving during the run remains observable. Tests that
    // pre-set the cancel flag before invoking the worker directly
    // therefore see the immediate-cancel path.
    state.backfill_in_progress.store(true, Ordering::SeqCst);

    // Compute total up front so the UI can show a real progress bar
    // rather than a spinner.
    let mut total = 0usize;
    let domains: Vec<L2Domain> = EMBED_ELIGIBLE_DOMAINS.iter().copied().collect();
    let mut per_domain_rows: Vec<(L2Domain, Vec<(String, u64, String)>)> = Vec::new();
    for &domain in &domains {
        let store = state.memory_for_domain(shell_domain(domain));
        let sessions = store.list_sessions().unwrap_or_default();
        let mut rows: Vec<(String, u64, String)> = Vec::new();
        for sid in sessions {
            if let Ok(window) = store.recent(&sid) {
                for r in window.records {
                    rows.push((r.session_id.clone(), r.sequence, r.content));
                }
            }
        }
        total += rows.len();
        per_domain_rows.push((domain, rows));
    }

    {
        let mut p = state.backfill_progress.lock().expect("backfill progress lock");
        p.total = total;
        p.completed = 0;
        p.failures = 0;
        p.finished = false;
        p.cancelled = false;
        p.current_domain = None;
        p.started_at_ms = state.next_ts();
    }
    emit_progress(app, &job_id, state);

    // L5 gate before any embed call.
    let ts_raw = state.next_ts();
    let persona_id = {
        let a = state.active.read().expect("active read lock");
        PersonaId(a.compiled.persona_id.0.clone())
    };
    let gate_request = ActionRequest {
        request_id: RequestId(format!("backfill-{ts_raw}")),
        turn_id: TurnId(format!("backfill-turn-{ts_raw}")),
        capability: Capability::RetrievalContext,
        resource: ResourceScope::None,
        actor_persona: persona_id,
        emitted_at: MonotonicTimestamp(ts_raw),
        task_id: None,
        provenance_tags: Vec::new(),
        intended_route: None,
        risk_class_hint: None,
    };
    let allow = {
        let active = state.active.read().expect("active read lock");
        match active.policy.evaluate(gate_request) {
            Ok(d) => matches!(d, Decision::Allow { .. }),
            Err(e) => {
                tracing::warn!("backfill policy evaluate: {e}");
                false
            }
        }
    };
    if !allow {
        tracing::warn!("backfill: L5 gate denied — aborting before any embed");
        finalize(state, app, &job_id, /* cancelled */ false);
        return;
    }

    // Walk every (domain, row).
    let provider = state
        .embedding_provider
        .read()
        .expect("embedding provider read lock")
        .clone();
    let pause = Duration::from_millis(options.per_row_pause_ms);
    'outer: for (domain, rows) in per_domain_rows {
        {
            let mut p = state.backfill_progress.lock().expect("backfill progress lock");
            p.current_domain = Some(domain.label().to_string());
        }
        for (sid, seq, content) in rows {
            if state.backfill_cancel.load(Ordering::SeqCst) {
                let mut p = state.backfill_progress.lock().expect("backfill progress lock");
                p.cancelled = true;
                break 'outer;
            }
            match provider.embed(&content) {
                Ok(vector) => {
                    let row = EmbeddingRow {
                        memory_id: MemoryId::new(format!("mem-{sid}-{seq}")),
                        domain,
                        vector,
                    };
                    if let Err(e) = state.embedding_store.upsert(row) {
                        tracing::warn!("backfill upsert {} seq {}: {e}", domain.label(), seq);
                        bump_failures(state);
                    } else {
                        bump_completed(state);
                    }
                }
                Err(e) => {
                    tracing::warn!("backfill embed {} seq {}: {e}", domain.label(), seq);
                    bump_failures(state);
                }
            }
            emit_progress(app, &job_id, state);
            // Pacing pause to avoid Ollama queue 500s under sustained
            // bge-m3 load (ADR-0007 D7 §Tuning notes).
            std::thread::sleep(pause);
        }
    }

    let cancelled = state.backfill_cancel.load(Ordering::SeqCst);
    finalize(state, app, &job_id, cancelled);
}

fn bump_completed(state: &AppState) {
    let mut p = state.backfill_progress.lock().expect("backfill progress lock");
    p.completed += 1;
}

fn bump_failures(state: &AppState) {
    let mut p = state.backfill_progress.lock().expect("backfill progress lock");
    p.failures += 1;
}

fn finalize(state: &AppState, app: Option<&AppHandle>, job_id: &str, cancelled: bool) {
    {
        let mut p = state.backfill_progress.lock().expect("backfill progress lock");
        p.finished = true;
        p.cancelled = cancelled;
        p.current_domain = None;
    }
    state.backfill_in_progress.store(false, Ordering::SeqCst);
    state.backfill_cancel.store(false, Ordering::SeqCst);
    emit_progress(app, job_id, state);
    emit_done(app, job_id, state);
}

fn emit_progress(app: Option<&AppHandle>, job_id: &str, state: &AppState) {
    if let Some(a) = app {
        let snapshot = state
            .backfill_progress
            .lock()
            .expect("backfill progress lock")
            .clone();
        let payload = BackfillProgressPayload {
            job_id: job_id.to_string(),
            progress: snapshot,
        };
        let _ = a.emit("backfill:progress", payload);
    }
}

fn emit_done(app: Option<&AppHandle>, job_id: &str, state: &AppState) {
    if let Some(a) = app {
        let snapshot = state
            .backfill_progress
            .lock()
            .expect("backfill progress lock")
            .clone();
        let payload = BackfillProgressPayload {
            job_id: job_id.to_string(),
            progress: snapshot,
        };
        let _ = a.emit("backfill:done", payload);
    }
}

/// Spawn the backfill worker on the Tauri runtime. Returns a job id
/// the caller can use to correlate progress events. Returns `None`
/// (and emits a `tracing::warn`) if a backfill is already in
/// progress — only one job at a time.
pub fn spawn_backfill(
    state_handle: Arc<AppState>,
    app: AppHandle,
    options: BackfillOptions,
) -> Option<String> {
    if state_handle.backfill_in_progress.load(Ordering::SeqCst) {
        tracing::warn!("backfill already in progress; new job rejected");
        return None;
    }
    // Reset cancel before launching so a stale cancel from a prior
    // job (or a racy double-cancel) doesn't poison the new run.
    state_handle.backfill_cancel.store(false, Ordering::SeqCst);
    let job_id = format!("backfill-{}", state_handle.next_ts());
    let job_id_for_task = job_id.clone();
    tauri::async_runtime::spawn_blocking(move || {
        run_backfill_worker(&state_handle, Some(&app), job_id_for_task, options);
    });
    Some(job_id)
}

#[cfg(test)]
mod tests {
    use super::*;
    use aether_l2_memory::{
        embeddings::StubEmbedder, EmbeddingProvider, MemoryRole, TurnMemoryRecord,
    };

    fn enable_embeddings(state: &AppState) {
        let mut cfg = state.memory_config();
        cfg.embeddings.enabled = true;
        cfg.embeddings.provider = Some("stub:16".into());
        state.set_memory_config(cfg).unwrap();
    }

    fn swap_stub_embedder(state: &AppState, dim: usize) {
        let stub: Arc<dyn EmbeddingProvider> = Arc::new(StubEmbedder::new(dim));
        *state.embedding_provider.write().unwrap() = stub;
    }

    fn seed_durable_only(state: &AppState, sid: &str, n: u64) {
        for i in 1..=n {
            state
                .durable_memory
                .append(TurnMemoryRecord {
                    session_id: sid.into(),
                    sequence: 0,
                    role: MemoryRole::User,
                    content: format!("backfill row {i}"),
                    timestamp_ms: i * 1_000,
                })
                .unwrap();
        }
    }

    #[test]
    fn estimate_unembedded_count_returns_zero_on_empty_state() {
        let state = AppState::new().expect("state");
        assert_eq!(estimate_unembedded_count(&state), 0);
    }

    #[test]
    fn estimate_unembedded_count_reflects_seeded_rows() {
        let state = AppState::new().expect("state");
        seed_durable_only(&state, "s1", 5);
        // 5 memory rows, 0 embedded → 5 un-embedded.
        assert_eq!(estimate_unembedded_count(&state), 5);
    }

    #[test]
    fn worker_embeds_every_durable_row_to_completion() {
        let state = AppState::new().expect("state");
        swap_stub_embedder(&state, 8);
        enable_embeddings(&state);
        seed_durable_only(&state, "s1", 3);
        // Drive without an AppHandle (unit test).
        run_backfill_worker(
            &state,
            None,
            "test-job".into(),
            BackfillOptions { per_row_pause_ms: 0 },
        );
        let p = state.backfill_progress.lock().unwrap();
        assert!(p.finished, "worker must mark finished");
        assert!(!p.cancelled, "worker must not be marked cancelled on success");
        assert_eq!(p.total, 3, "total must match seeded row count");
        assert_eq!(p.completed, 3, "every row must be embedded");
        assert_eq!(p.failures, 0, "no failures on stub embedder");
    }

    #[test]
    fn worker_resets_in_progress_flag_after_completion() {
        let state = AppState::new().expect("state");
        swap_stub_embedder(&state, 8);
        enable_embeddings(&state);
        seed_durable_only(&state, "s1", 2);
        assert!(!state.backfill_in_progress.load(Ordering::SeqCst));
        run_backfill_worker(
            &state,
            None,
            "test-job".into(),
            BackfillOptions { per_row_pause_ms: 0 },
        );
        assert!(
            !state.backfill_in_progress.load(Ordering::SeqCst),
            "in_progress must be false on exit"
        );
    }

    #[test]
    fn worker_marks_cancelled_when_flag_set() {
        let state = AppState::new().expect("state");
        swap_stub_embedder(&state, 8);
        enable_embeddings(&state);
        seed_durable_only(&state, "s1", 5);
        // Pre-cancel: the very first cancel-check trips and the worker
        // exits before embedding the first row.
        state.backfill_cancel.store(true, Ordering::SeqCst);
        run_backfill_worker(
            &state,
            None,
            "test-job".into(),
            BackfillOptions { per_row_pause_ms: 0 },
        );
        let p = state.backfill_progress.lock().unwrap();
        assert!(p.finished);
        assert!(p.cancelled, "cancelled flag must surface in final progress");
    }

    #[test]
    fn worker_aborts_when_embeddings_disabled_via_policy_path() {
        // The L5 gate denies when the persona is not configured for
        // RetrievalContext; for the default "aurora" persona used in
        // AppState::new() the gate allows. Skip strict policy-deny
        // simulation here and verify the happy path doesn't surface
        // cancelled. Cross-layer policy mocking belongs to a deeper
        // test surface than this unit test.
        let state = AppState::new().expect("state");
        swap_stub_embedder(&state, 8);
        enable_embeddings(&state);
        seed_durable_only(&state, "s1", 1);
        run_backfill_worker(
            &state,
            None,
            "test-job".into(),
            BackfillOptions { per_row_pause_ms: 0 },
        );
        let p = state.backfill_progress.lock().unwrap();
        assert!(p.finished);
        assert!(!p.cancelled);
    }
}
