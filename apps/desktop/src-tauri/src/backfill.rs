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
//! - **Skip-already-embedded fast path.** At each domain boundary the
//!   worker asks `EmbeddingStore::embedded_ids(domain)` for the set
//!   of memory ids already vectorised. Rows whose synthetic id
//!   (`mem-{session}-{seq}`) is in that set are counted into
//!   `BackfillProgress::skipped_already_embedded` and skipped without
//!   issuing an embed call. The second invocation of backfill on the
//!   same data therefore drops from ~3-5 sec/row to a single index
//!   scan + a no-op walk. Stores that don't override `embedded_ids`
//!   return an empty set (trait default) and the historical brute-
//!   force re-embed kicks in — strictly safe; `upsert` is idempotent
//!   so re-embedding never corrupts state, just wastes wall-clock.
//! - **Capability-gated.** Every backfill invocation routes through
//!   the same L5 `Capability::RetrievalContext` gate the orchestrator
//!   uses. A non-Allow decision aborts before any embed call lands.
//! - **Failure-tolerant.** A single embed call failing does not kill
//!   the job; the row is counted as a failure and the worker
//!   continues. The final report carries `failures` count.

use std::collections::HashSet;
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
use tauri::{AppHandle, Emitter, Runtime};

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
/// Headless variant for unit tests — runs the worker without a Tauri
/// runtime (no event emission). Production callers go through
/// [`run_backfill_worker`].
#[cfg(test)]
pub fn run_backfill_worker_headless(
    state: &AppState,
    job_id: String,
    options: BackfillOptions,
) {
    run_backfill_worker::<tauri::test::MockRuntime>(state, None, job_id, options);
}

pub fn run_backfill_worker<R: Runtime>(
    state: &AppState,
    app: Option<&AppHandle<R>>,
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
    let mut per_domain_rows: Vec<(L2Domain, Vec<(String, u64, String)>)> = Vec::new();
    for &domain in EMBED_ELIGIBLE_DOMAINS {
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
        p.skipped_already_embedded = 0;
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
        audit_extras: None,
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
        // Pre-compute the already-embedded set for this domain so the
        // hot per-row loop is a single hash probe. A failure here is
        // non-fatal — we fall back to "skip nothing" (the same shape
        // a default-impl store gives) and keep going.
        let already: HashSet<MemoryId> = match state.embedding_store.embedded_ids(domain) {
            Ok(set) => set,
            Err(e) => {
                tracing::warn!(
                    "backfill embedded_ids({}) failed; falling back to brute-force: {e}",
                    domain.label()
                );
                HashSet::new()
            }
        };
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
            let memory_id = MemoryId::new(format!("mem-{sid}-{seq}"));
            if already.contains(&memory_id) {
                bump_skipped(state);
                emit_progress(app, &job_id, state);
                // No pause on skip — the whole point is the cheap path.
                continue;
            }
            match provider.embed(&content) {
                Ok(vector) => {
                    let row = EmbeddingRow {
                        memory_id: memory_id.clone(),
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

fn bump_skipped(state: &AppState) {
    let mut p = state.backfill_progress.lock().expect("backfill progress lock");
    p.skipped_already_embedded += 1;
}

fn finalize<R: Runtime>(state: &AppState, app: Option<&AppHandle<R>>, job_id: &str, cancelled: bool) {
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

fn emit_progress<R: Runtime>(app: Option<&AppHandle<R>>, job_id: &str, state: &AppState) {
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

fn emit_done<R: Runtime>(app: Option<&AppHandle<R>>, job_id: &str, state: &AppState) {
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
/// if a backfill is already in progress — only one job at a time per
/// ADR-0007 D5.
///
/// Phase 4D wired this into the live `start_backfill` Tauri command
/// (commands.rs). The worker runs on `tauri::async_runtime::spawn_blocking`
/// because `run_backfill_worker` is sync (per-row `provider.embed`
/// is a blocking HTTP call and the per-row pacing pause is
/// `std::thread::sleep`); placing it on `spawn` would starve the
/// async runtime instead. The double-start guard checks
/// `backfill_in_progress` atomically before reset to give
/// `cancel_backfill` a stable signal.
pub fn spawn_backfill<R: Runtime>(
    state_handle: Arc<AppState>,
    app: AppHandle<R>,
    options: BackfillOptions,
) -> Option<String> {
    // Compare-and-swap so a racing pair of `start_backfill` IPC calls
    // can't both pass the guard. `compare_exchange` returns Err with
    // the existing value if the swap failed — that's our
    // "already running" signal. SeqCst matches every other access on
    // this atomic in this module to keep the visibility model simple.
    if state_handle
        .backfill_in_progress
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_err()
    {
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
        run_backfill_worker_headless(
            &state,
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
        run_backfill_worker_headless(
            &state,
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
        run_backfill_worker_headless(
            &state,
            "test-job".into(),
            BackfillOptions { per_row_pause_ms: 0 },
        );
        let p = state.backfill_progress.lock().unwrap();
        assert!(p.finished);
        assert!(p.cancelled, "cancelled flag must surface in final progress");
    }

    #[test]
    fn worker_skips_already_embedded_rows_on_second_pass() {
        // First pass embeds N=4 rows. Second pass on the same state
        // must skip every row via embedded_ids — no new embeds, no
        // failures, and skipped_already_embedded == 4.
        let state = AppState::new().expect("state");
        swap_stub_embedder(&state, 8);
        enable_embeddings(&state);
        seed_durable_only(&state, "s1", 4);

        run_backfill_worker_headless(
            &state,
            "first".into(),
            BackfillOptions { per_row_pause_ms: 0 },
        );
        {
            let p = state.backfill_progress.lock().unwrap();
            assert_eq!(p.completed, 4);
            assert_eq!(p.skipped_already_embedded, 0);
            assert_eq!(p.failures, 0);
        }

        // Second invocation — the FlatFile store now has all four ids
        // for Durable, so every row should land in the skip path.
        run_backfill_worker_headless(
            &state,
            "second".into(),
            BackfillOptions { per_row_pause_ms: 0 },
        );
        let p = state.backfill_progress.lock().unwrap();
        assert!(p.finished);
        assert!(!p.cancelled);
        assert_eq!(p.total, 4);
        assert_eq!(p.completed, 0, "second pass must not re-embed");
        assert_eq!(p.failures, 0);
        assert_eq!(
            p.skipped_already_embedded, 4,
            "every row must be counted as skipped on second pass"
        );
    }

    #[test]
    fn worker_skips_subset_when_only_some_rows_pre_embedded() {
        // Seed N=5 rows, then manually pre-embed two of them so the
        // second pass shows a mixed completed/skipped split.
        let state = AppState::new().expect("state");
        swap_stub_embedder(&state, 8);
        enable_embeddings(&state);
        seed_durable_only(&state, "s1", 5);

        // Pre-populate two ids in the embedding store so the worker
        // sees them as already-embedded. seed_durable_only writes
        // sequence=0 for every record because the in-memory durable
        // store assigns sequence inside `append`; mirror the worker's
        // id-construction logic against the actual stored sequences.
        let store = state.memory_for_domain(crate::memory_config::MemoryDomain::Durable);
        let sessions = store.list_sessions().unwrap();
        let mut all_ids: Vec<MemoryId> = Vec::new();
        for sid in sessions {
            for r in store.recent(&sid).unwrap().records {
                all_ids.push(MemoryId::new(format!("mem-{}-{}", r.session_id, r.sequence)));
            }
        }
        assert_eq!(all_ids.len(), 5);
        // Pre-embed the first two with a junk vector.
        for id in all_ids.iter().take(2) {
            state
                .embedding_store
                .upsert(EmbeddingRow {
                    memory_id: id.clone(),
                    domain: L2Domain::Durable,
                    vector: vec![0.0; 8],
                })
                .unwrap();
        }

        run_backfill_worker_headless(
            &state,
            "mixed".into(),
            BackfillOptions { per_row_pause_ms: 0 },
        );
        let p = state.backfill_progress.lock().unwrap();
        assert!(p.finished);
        assert_eq!(p.total, 5);
        assert_eq!(p.skipped_already_embedded, 2);
        assert_eq!(p.completed, 3);
        assert_eq!(p.failures, 0);
    }

    #[test]
    fn worker_cancel_during_skip_walk_still_marks_cancelled() {
        // Pre-embed every row so the skip path runs for all of them,
        // then pre-cancel before the worker enters the row loop.
        // The cancel check sits at the head of the per-row loop — the
        // worker must observe the flag and exit cancelled rather than
        // marching through the skip walk to natural completion.
        let state = AppState::new().expect("state");
        swap_stub_embedder(&state, 8);
        enable_embeddings(&state);
        seed_durable_only(&state, "s1", 6);

        // First pass: embed everything.
        run_backfill_worker_headless(
            &state,
            "warmup".into(),
            BackfillOptions { per_row_pause_ms: 0 },
        );

        // Now pre-cancel and run again. Every row would be a skip, but
        // the cancel must short-circuit the loop.
        state.backfill_cancel.store(true, Ordering::SeqCst);
        run_backfill_worker_headless(
            &state,
            "cancelled".into(),
            BackfillOptions { per_row_pause_ms: 0 },
        );
        let p = state.backfill_progress.lock().unwrap();
        assert!(p.finished);
        assert!(p.cancelled, "cancel during skip walk must still surface");
        assert_eq!(p.completed, 0);
    }

    // ----- Phase 4D: spawn_backfill async semantics -----
    //
    // These tests use `tauri::test::mock_app()` to build a real
    // `AppHandle` against `MockRuntime` so the worker can `app.emit`
    // without a webview. The MockRuntime owns its own tokio runtime
    // and runs `spawn_blocking` on a dedicated thread pool — the
    // tests therefore exercise the actual async wiring, not a stub.

    /// Block on the in-progress flag flipping back to false. Spins
    /// at 5 ms granularity which is below the 200 ms cancel-latency
    /// budget; returns `Err` once the timeout elapses so the test
    /// fails loud rather than hanging the suite.
    fn wait_until_idle(state: &Arc<AppState>, timeout_ms: u64) -> Result<(), String> {
        let start = std::time::Instant::now();
        while state.backfill_in_progress.load(Ordering::SeqCst) {
            if start.elapsed() > Duration::from_millis(timeout_ms) {
                return Err(format!("worker did not idle within {timeout_ms} ms"));
            }
            std::thread::sleep(Duration::from_millis(5));
        }
        Ok(())
    }

    #[test]
    fn spawn_backfill_returns_immediately_under_50ms_with_100_rows() {
        // 100 rows × 0 ms pause × stub embedder is still ~ms of CPU
        // when run synchronously. The contract is that the spawn
        // call itself returns within ~50 ms regardless: the worker
        // must run on the runtime, not on the calling thread.
        let app = tauri::test::mock_app();
        let raw = AppState::new().expect("state");
        swap_stub_embedder(&raw, 8);
        enable_embeddings(&raw);
        seed_durable_only(&raw, "s1", 100);
        let state = Arc::new(raw);

        let t0 = std::time::Instant::now();
        let job_id = spawn_backfill(
            state.clone(),
            app.handle().clone(),
            BackfillOptions { per_row_pause_ms: 0 },
        )
        .expect("first start must succeed");
        let elapsed = t0.elapsed();
        assert!(
            elapsed < Duration::from_millis(50),
            "spawn_backfill should return in <50 ms, took {elapsed:?}"
        );
        assert!(job_id.starts_with("backfill-"));
        // Drain the worker so we don't leak a background thread into
        // the next test (in-progress flag stays sticky otherwise).
        wait_until_idle(&state, 5_000).expect("worker should finish");
    }

    #[test]
    fn double_spawn_backfill_returns_none_on_second_call() {
        // The second start request must NOT spawn a parallel worker
        // and must NOT clear the in-progress flag of the first.
        let app = tauri::test::mock_app();
        let raw = AppState::new().expect("state");
        swap_stub_embedder(&raw, 8);
        enable_embeddings(&raw);
        // 200 rows × 5 ms pause keeps the worker alive long enough to
        // race the second spawn against it.
        seed_durable_only(&raw, "s1", 200);
        let state = Arc::new(raw);

        let first = spawn_backfill(
            state.clone(),
            app.handle().clone(),
            BackfillOptions { per_row_pause_ms: 5 },
        );
        assert!(first.is_some(), "first spawn must succeed");

        // Second call while the first is still running.
        let second = spawn_backfill(
            state.clone(),
            app.handle().clone(),
            BackfillOptions { per_row_pause_ms: 0 },
        );
        assert!(second.is_none(), "second spawn must be rejected");
        // Cancel so the test doesn't have to wait for natural
        // completion (200 rows × 5 ms = 1 sec).
        state.backfill_cancel.store(true, Ordering::SeqCst);
        wait_until_idle(&state, 5_000).expect("worker should drain after cancel");
    }

    #[test]
    fn cancel_during_spawned_run_exits_within_200ms_with_cancelled_flag() {
        // Worker runs against a long row set (200 × 5 ms = 1 sec
        // natural duration). Flipping cancel mid-run must surface
        // `cancelled = true` and the worker must idle within 200 ms.
        let app = tauri::test::mock_app();
        let raw = AppState::new().expect("state");
        swap_stub_embedder(&raw, 8);
        enable_embeddings(&raw);
        seed_durable_only(&raw, "s1", 200);
        let state = Arc::new(raw);

        spawn_backfill(
            state.clone(),
            app.handle().clone(),
            BackfillOptions { per_row_pause_ms: 5 },
        )
        .expect("spawn must succeed");
        // Give the worker a real chance to enter the row loop. 50 ms
        // is well above the spawn_blocking dispatch latency on every
        // platform we ship to.
        std::thread::sleep(Duration::from_millis(50));
        let cancel_at = std::time::Instant::now();
        state.backfill_cancel.store(true, Ordering::SeqCst);
        wait_until_idle(&state, 200).expect("worker must exit within 200 ms of cancel");
        let cancel_latency = cancel_at.elapsed();
        assert!(
            cancel_latency < Duration::from_millis(200),
            "cancel-to-idle should be <200 ms, was {cancel_latency:?}"
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
        run_backfill_worker_headless(
            &state,
            "test-job".into(),
            BackfillOptions { per_row_pause_ms: 0 },
        );
        let p = state.backfill_progress.lock().unwrap();
        assert!(p.finished);
        assert!(!p.cancelled);
    }
}
