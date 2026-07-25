//! ADR-0005 retrieval orchestrator.
//!
//! Given an utterance + the `AppState`, runs the embed → query_nearest
//! → fetch_one → rank pipeline described in
//! `docs/adr/ADR-0005-retrieval-wiring.md` and returns a bounded
//! `Vec<RetrievalHit>` the prompt builder can consume.
//!
//! Separate module (not inline in `memory_router.rs`) so the
//! orchestrator is testable without standing up the full turn
//! pipeline. Wiring into `MemoryAwareRouter::dispatch` /
//! `RoleTaggedOllamaRouter::dispatch` lives in that file.
//!
//! ## Contract at a glance
//!
//! - Timing: sequential, post-memory, pre-prompt. Caller invokes
//!   `run_retrieval_context` **after** `SessionMemoryStore::recent`
//!   and **before** composing the final prompt.
//! - Bailout: wall-clock deadline applied across embed + query +
//!   fetch. On exceed, emits exactly one `warn!` and returns an empty
//!   vec. No silent fallback.
//! - Rank: score desc, recency tiebreak (newer first), truncate to
//!   the caller-provided `max_items`.
//! - Capability: every invocation routes through the L5 policy gate
//!   with `Capability::RetrievalContext`. Non-Allow returns empty
//!   plus a `warn!`.

use std::cmp::Ordering;
use std::time::{Duration, Instant};

use aether_l2_memory::{
    EmbeddingStore, MemoryDomain, MemoryId, SessionMemoryStore, SimilarityHit,
    EMBED_ELIGIBLE_DOMAINS,
};
use aether_l5_policy::capability::{Capability, ResourceScope};
use aether_l5_policy::common::{MonotonicTimestamp, RequestId, TurnId};
use aether_l5_policy::decision::Decision;
use aether_l5_policy::policy_engine::ActionRequest;
use aether_l5_policy::PersonaId;
use serde::{Deserialize, Serialize};

use crate::memory_config::MemoryDomain as ShellDomain;
use crate::state::AppState;

/// Default hard deadline for the full embed + query + fetch pipeline.
/// Per ADR-0005 §Decision 1.
pub const DEFAULT_RETRIEVAL_DEADLINE: Duration = Duration::from_secs(5);

/// ADR-0010 Option A — recency-weighted combine.
///
/// Phase 4 ranks by `cosine + RECENCY_WEIGHT_ALPHA * recency_decay`
/// where `recency_decay = exp(-Δt / τ)` is normalised to `[0, 1]`
/// (1.0 = "now", → 0 as Δt → ∞).
///
/// Default `α = 0.1` is intentionally small: cosine remains dominant,
/// recency breaks near-ties and offers a modest nudge for fresh content
/// rather than overpowering the semantic signal. The Phase 3A miss-
/// pattern analysis (retrieval calibration, 2026-04-25; see
/// `docs/adr/ADR-0010-rank-function-recency-weighted-combine.md`)
/// showed the dominant failure mode is within-thread top-1
/// confusion — not recency bias — so a heavy α would underperform.
pub const RECENCY_WEIGHT_ALPHA: f32 = 0.1;

/// Half-life for `recency_decay` in ADR-0010 Option A. 7 days mirrors
/// the timescale at which "fresh" / "still relevant" content gives
/// way to "older context" in typical Companion usage. Tunable per tier
/// in a follow-up if calibration shows a different curve helps.
pub const RECENCY_HALF_LIFE: Duration = Duration::from_secs(7 * 24 * 60 * 60);

/// Compute the recency-decayed weight for a row at `row_ts_ms`,
/// observed from `now_ms`. Returns a value in `[0.0, 1.0]`:
///
/// - 1.0 when the row is at or after `now_ms` (clock skew / future
///   timestamp — treat as fully fresh rather than letting the decay
///   blow up).
/// - `exp(-Δt / τ)` otherwise.
///
/// Pure function so the bench harness can mirror it byte-for-byte.
pub fn recency_decay(row_ts_ms: u64, now_ms: u64, half_life: Duration) -> f32 {
    if row_ts_ms >= now_ms {
        return 1.0;
    }
    let delta_ms = (now_ms - row_ts_ms) as f64;
    let half_life_ms = half_life.as_millis() as f64;
    if half_life_ms <= 0.0 {
        return 0.0;
    }
    // exp(-Δt / τ) normalised to [0, 1].
    (-delta_ms / half_life_ms).exp() as f32
}

/// Combine cosine + recency per ADR-0010 Option A. Pure function so
/// both the production rank (Phase 4) and the bench harness use the
/// same arithmetic.
pub fn combined_rank_score(
    cosine: f32,
    row_ts_ms: u64,
    now_ms: u64,
    alpha: f32,
    half_life: Duration,
) -> f32 {
    cosine + alpha * recency_decay(row_ts_ms, now_ms, half_life)
}

/// ADR-0007 §Decision 3 readiness state machine. Updated by every
/// invocation of `run_retrieval_context` (event-driven symmetric
/// cadence — failure paths flip to `NotReady`, success path flips
/// back to `Ready`), plus by boot probes and settings-change probes.
///
/// The shell exposes the current state via the `embeddings_readiness`
/// Tauri command; the UI renders a Trust-drawer indicator + drawer-
/// icon attention badge + transition toast per ADR-0007 §Decision 6.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ReadinessState {
    /// Pre-probe; the shell has not yet attempted to determine
    /// retrieval readiness. Distinct from `Disabled` (intentionally
    /// off) and `Ready` (proven working). Boot wires the first probe
    /// before any user-visible turn, so this state is normally only
    /// observed during the first ~250ms of process lifetime.
    Unknown,

    /// `embeddings.enabled = false`. Retrieval is intentionally off;
    /// no probes run, no warnings are surfaced. This is the ship
    /// default per ADR-0002 §Decision 5 / ADR-0007 §Decision 1.
    Disabled,

    /// Last probe or `run_retrieval_context` invocation succeeded.
    /// Retrieval is firing on real turns.
    Ready,

    /// Last probe or `run_retrieval_context` invocation failed.
    /// `reason` carries the structured detail the UI uses to compose
    /// the surfaced-warning copy.
    NotReady { reason: NotReadyReason },
}

impl Default for ReadinessState {
    fn default() -> Self {
        Self::Unknown
    }
}

/// Structured reason for `NotReady`. Stable wire form so the UI can
/// branch on `kind` without parsing free text. Each variant carries
/// the minimum context the UI needs to build the message ("model
/// `bge-m3` not installed — run `ollama pull bge-m3` (~1.2 GB)").
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum NotReadyReason {
    /// Provider HTTP probe failed (daemon not running, wrong port,
    /// etc.). `detail` is a short diagnostic string — not stable wire
    /// vocabulary.
    ProviderUnreachable { detail: String },
    /// Provider reachable but the configured embedding model is not
    /// in the list returned by `/api/tags`. Most common first-time
    /// failure.
    ModelNotInstalled { model: String },
    /// L5 policy gate returned non-Allow for `Capability::RetrievalContext`.
    PolicyDenied,
    /// Embedder produced an error mid-call (rare — usually catches
    /// adversarial text or transient model state).
    EmbedFailed { detail: String },
    /// Wall-clock deadline exceeded (5s default per ADR-0005 D1).
    /// Distinct from `EmbedFailed` so the UI can show the right
    /// remediation copy ("provider is reachable but slow").
    Bailout,
    /// Disk space below the threshold required to safely pull the
    /// configured model + working space (ADR-0007 §Decision 8).
    /// Surfaced before any pull instruction or backfill affordance.
    LowDisk { needed_gb: u32, available_gb: u32 },
}

/// One resolved retrieval row — content + score + provenance. What
/// the prompt builder consumes. Scores are raw cosine similarity in
/// `[-1.0, 1.0]`; higher = closer.
#[derive(Debug, Clone, PartialEq)]
pub struct RetrievalHit {
    /// Memory id as produced by `mk_memory_id("mem-{session}-{seq}")`.
    pub memory_id: String,
    /// Domain the hit came from.
    pub domain: MemoryDomain,
    /// Cosine similarity.
    pub score: f32,
    /// Row content, resolved via `fetch_one`.
    pub content: String,
    /// Row timestamp; used by rank for recency tiebreak and by the
    /// prompt builder to render provenance.
    pub timestamp_ms: u64,
}

/// Run retrieval against every embed-eligible domain and return a
/// ranked, capped result set. See module docs for the contract.
///
/// `utterance` is the raw user input; caller is responsible for
/// passing the memory-augmented query string if desired (ADR-0005
/// §Decision 1 recommends memory-augmented for quality).
///
/// `max_items` is the final cap applied post-rank. Callers read it
/// from `memory_config.retrieval.max_items` (ADR-0005 §Decision 3).
///
/// Returns `Ok(vec![])` on bailout, policy deny, or embeddings off.
/// Err is reserved for unrecoverable internal errors (lock poisoning);
/// normal failure modes warn + return empty.
pub fn run_retrieval_context(
    state: &AppState,
    session_id: &str,
    utterance: &str,
    max_items: usize,
    deadline: Duration,
) -> Vec<RetrievalHit> {
    if max_items == 0 {
        // Treat as Disabled — caller chose to suppress retrieval
        // without flipping the master flag. Same observable state.
        state.set_retrieval_readiness(ReadinessState::Disabled);
        return Vec::new();
    }
    let cfg = state.memory_config();
    if !cfg.embeddings.enabled {
        state.set_retrieval_readiness(ReadinessState::Disabled);
        return Vec::new();
    }

    // L5 gate — one audit row per retrieval invocation. Mirrors the
    // memory_service::build_action_request shape; inline here to
    // avoid cross-module coupling (retrieval is a standalone slice).
    let ts_raw = state.next_ts();
    let persona_id = {
        let a = state.active.read().expect("active read lock");
        PersonaId(a.compiled.persona_id.0.clone())
    };
    let gate_request = ActionRequest {
        request_id: RequestId(format!("retrieval-{ts_raw}")),
        turn_id: TurnId(format!("retrieval-turn-{ts_raw}")),
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
    let decision = {
        let active = state.active.read().expect("active read lock");
        match active.policy.evaluate(gate_request) {
            Ok(d) => d,
            Err(e) => {
                tracing::warn!("retrieval policy evaluate: {e}");
                state.set_retrieval_readiness(ReadinessState::NotReady {
                    reason: NotReadyReason::PolicyDenied,
                });
                return Vec::new();
            }
        }
    };
    if !matches!(decision, Decision::Allow { .. }) {
        tracing::warn!("retrieval gate non-Allow; skipping");
        state.set_retrieval_readiness(ReadinessState::NotReady {
            reason: NotReadyReason::PolicyDenied,
        });
        return Vec::new();
    }

    let deadline_at = Instant::now() + deadline;

    // Phase 1 — embed the utterance.
    let query_vec = {
        let provider = state
            .embedding_provider
            .read()
            .expect("embedding provider read lock")
            .clone();
        match timed(deadline_at, || provider.embed(utterance)) {
            TimedResult::Ok(Ok(v)) => v,
            TimedResult::Ok(Err(e)) => {
                tracing::warn!("retrieval embed failed: {e}");
                // Distinguish "provider unreachable" (HTTP transport
                // failure) from "embed call returned an error" (model
                // present but produced an error). The error string is
                // diagnostic only; the variant decides UI copy.
                let detail = e.to_string();
                let reason = if detail.contains("transport") || detail.contains("Connection") {
                    NotReadyReason::ProviderUnreachable { detail }
                } else {
                    NotReadyReason::EmbedFailed { detail }
                };
                state.set_retrieval_readiness(ReadinessState::NotReady { reason });
                return Vec::new();
            }
            TimedResult::Timeout => {
                tracing::warn!(
                    "retrieval embed phase exceeded {}s deadline",
                    deadline.as_secs()
                );
                state.set_retrieval_readiness(ReadinessState::NotReady {
                    reason: NotReadyReason::Bailout,
                });
                return Vec::new();
            }
        }
    };

    // Phase 2 — query every embed-eligible domain.
    let mut all_hits: Vec<(MemoryDomain, SimilarityHit)> = Vec::new();
    for &domain in EMBED_ELIGIBLE_DOMAINS {
        if Instant::now() >= deadline_at {
            tracing::warn!(
                "retrieval deadline exceeded before querying {}",
                domain.label()
            );
            state.set_retrieval_readiness(ReadinessState::NotReady {
                reason: NotReadyReason::Bailout,
            });
            return Vec::new();
        }
        match state
            .embedding_store
            .query_nearest(domain, &query_vec, max_items.max(1))
        {
            Ok(hits) => all_hits.extend(hits.into_iter().map(|h| (domain, h))),
            Err(e) => {
                tracing::warn!(
                    "retrieval query_nearest({}) failed: {e}; continuing",
                    domain.label()
                );
            }
        }
    }

    // Phase 3 — fetch content for each hit.
    let mut resolved: Vec<RetrievalHit> = Vec::with_capacity(all_hits.len());
    for (domain, hit) in all_hits {
        if Instant::now() >= deadline_at {
            tracing::warn!("retrieval deadline exceeded during fetch phase");
            state.set_retrieval_readiness(ReadinessState::NotReady {
                reason: NotReadyReason::Bailout,
            });
            return Vec::new();
        }
        let Some((sid, seq)) = parse_memory_id(&hit.memory_id) else {
            tracing::warn!("retrieval fetch: unparseable memory_id {}", hit.memory_id.0);
            continue;
        };
        let store = state.memory_for_domain(shell_domain(domain));
        // Session-aware: fetch_one guarantees the row belongs to the
        // session_id we parsed. If the hit was written under a
        // different session (shouldn't happen in single-lane durable
        // today, but possible once multi-profile lands), fetch_one
        // returns None and we drop the hit.
        let Ok(Some(row)) = store.fetch_one(&sid, seq) else {
            tracing::trace!(
                "retrieval fetch: stale hit {} (row evicted or missing)",
                hit.memory_id.0
            );
            continue;
        };
        resolved.push(RetrievalHit {
            memory_id: hit.memory_id.0.clone(),
            domain,
            score: hit.score,
            content: row.content,
            timestamp_ms: row.timestamp_ms,
        });
    }

    // Phase 4 — rank: score desc, recency desc, truncate to max_items.
    //
    // ADR-0010 §Empirical Validation: Option A (recency-weighted combine
    // using the `combined_rank_score` / `recency_decay` helpers below)
    // was measured against the 842-passage Phase 3A corpus and found to
    // *harm* recall (recall@1 −16.7 pp, MRR −13.4 pp). Option A is
    // Rejected; production retains the baseline cosine + strict-tiebreak
    // shape. The helpers stay public because Option B (cross-encoder
    // re-rank, +2.8 pp recall@1) is the ratified direction and may
    // re-use the recency primitive as a tertiary signal in a future
    // follow-up. See `docs/adr/ADR-0010-rank-function-recency-weighted-combine.md`
    // for the empirical evidence.
    resolved.sort_by(|a, b| match b.score.partial_cmp(&a.score) {
        Some(Ordering::Equal) | None => b.timestamp_ms.cmp(&a.timestamp_ms),
        Some(ord) => ord,
    });
    resolved.truncate(max_items);
    // Reaching the end of the function means every phase succeeded
    // (embed, query, fetch, rank). State flips to Ready whether or
    // not we found any hits — empty results are not a failure mode;
    // they just mean nothing matched semantically.
    state.set_retrieval_readiness(ReadinessState::Ready);
    resolved
}

/// Map the L2 `MemoryDomain` onto the shell's `MemoryDomain`. Today
/// the two enums share the same six variants (ADR-0001 reconciled
/// them) but live under different module paths; the shell wrapper
/// `state.memory_for_domain` consumes the shell-side type.
fn shell_domain(d: MemoryDomain) -> ShellDomain {
    match d {
        MemoryDomain::Session => ShellDomain::Session,
        MemoryDomain::Durable => ShellDomain::Durable,
        MemoryDomain::Facts => ShellDomain::Facts,
        MemoryDomain::Projects => ShellDomain::Projects,
        MemoryDomain::Preferences => ShellDomain::Preferences,
        MemoryDomain::Artifacts => ShellDomain::Artifacts,
    }
}

/// Reverse the `mk_memory_id` encoding `"mem-{session_id}-{sequence}"`.
/// Returns `Some((session_id, sequence))` on parse, `None` otherwise.
///
/// `session_id` itself may contain `-` (e.g. `"desktop-session"`), so
/// the split is: strip the `"mem-"` prefix, then split on the LAST
/// `-` to isolate the sequence.
pub fn parse_memory_id(raw: &MemoryId) -> Option<(String, u64)> {
    let body = raw.0.strip_prefix("mem-")?;
    let idx = body.rfind('-')?;
    let (sid, seq_str) = body.split_at(idx);
    let seq: u64 = seq_str.trim_start_matches('-').parse().ok()?;
    Some((sid.to_string(), seq))
}

/// Run `op` but surface a timeout if it hasn't produced a value by
/// `deadline`. This is a coarse wall-clock gate — cooperative, not
/// preemptive. The embed / query / fetch calls cannot be cancelled
/// mid-flight; the deadline prevents accumulating stalls across
/// phases, not a stall within a single phase. That matches the
/// ADR-0005 §Decision 1 intent: "broken Ollama never stalls a
/// turn indefinitely", not "every phase has a per-call timeout".
enum TimedResult<T> {
    Ok(T),
    Timeout,
}

fn timed<T, F: FnOnce() -> T>(deadline: Instant, op: F) -> TimedResult<T> {
    if Instant::now() >= deadline {
        return TimedResult::Timeout;
    }
    TimedResult::Ok(op())
}

/// Approximate disk-space requirement (in GB, rounded up with safety
/// margin) for a configured embedding provider string. ADR-0007
/// §Decision 8 requires `model_size * 1.5` free before any pull /
/// backfill affordance is offered. We bake the safety multiplier in
/// here so callers can compare directly against `available_space`.
///
/// Provider strings follow the Ollama convention `"ollama:<model>"`
/// (e.g. `"ollama:bge-m3"`). Unknown providers / models return a
/// conservative default sized for `bge-m3` so a low-disk machine is
/// never told it has more headroom than it really does.
pub fn required_disk_gb_for_provider(provider: Option<&str>) -> u32 {
    let model = match provider {
        Some(p) => p.rsplit(':').next().unwrap_or(p),
        None => return 2,
    };
    if model.contains("bge-m3") {
        2
    } else if model.contains("bge-small") || model.contains("bge-mini") {
        1
    } else if model.contains("nomic-embed") {
        1
    } else {
        // Unknown model name — assume bge-m3 sized to err on the
        // side of "not enough disk" rather than silently progressing
        // into a half-pulled state.
        2
    }
}

/// Extract the bare model name from a configured provider string
/// (`"ollama:bge-m3"` → `"bge-m3"`). Used by both readiness probe and
/// the indicator's pull-instruction copy.
pub fn parse_model_name(provider: &str) -> &str {
    provider.rsplit(':').next().unwrap_or(provider)
}

/// Run the readiness probe per ADR-0007 §Decisions 2 + 8 + Run 3
/// Session A. Pure decision function — caller assembles the inputs
/// from `AppState`, this just maps inputs → state.
///
/// Order of checks matters:
/// 1. Embeddings disabled → `Disabled` (intentional off; no probe).
/// 2. Provider unset / empty → `NotReady{ModelNotInstalled}` with
///    an empty model name. UI surfaces "configure provider in
///    Settings".
/// 3. Disk below threshold → `NotReady{LowDisk}`. ADR-0007 D8
///    requires `model_size * 1.5` free.
/// 4. HTTP probe of `/api/tags` fails → `NotReady{ProviderUnreachable}`.
/// 5. Model not in `/api/tags` list → `NotReady{ModelNotInstalled}`.
/// 6. All checks pass → `Ready`.
///
/// Light-usage: pure HTTP GET + JSON parse, no model loads. Bounded
/// by a 750ms timeout so unreachable daemons never hang the boot
/// path.
pub fn probe_readiness(
    embeddings_enabled: bool,
    provider: Option<&str>,
    ollama_base_url: &str,
    disk_available_gb: Option<u32>,
) -> ReadinessState {
    if !embeddings_enabled {
        return ReadinessState::Disabled;
    }

    let model_name = match provider.and_then(|p| {
        let m = parse_model_name(p);
        if m.is_empty() {
            None
        } else {
            Some(m.to_string())
        }
    }) {
        Some(m) => m,
        None => {
            return ReadinessState::NotReady {
                reason: NotReadyReason::ModelNotInstalled {
                    model: String::new(),
                },
            };
        }
    };

    let needed = required_disk_gb_for_provider(provider);
    if let Some(avail) = disk_available_gb {
        if avail < needed {
            return ReadinessState::NotReady {
                reason: NotReadyReason::LowDisk {
                    needed_gb: needed,
                    available_gb: avail,
                },
            };
        }
    }

    let url = format!("{}/api/tags", ollama_base_url.trim_end_matches('/'));
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_millis(750))
        .build();
    let resp = match agent.get(&url).call() {
        Ok(r) => r,
        Err(e) => {
            return ReadinessState::NotReady {
                reason: NotReadyReason::ProviderUnreachable {
                    detail: e.to_string(),
                },
            };
        }
    };
    let json: serde_json::Value = match resp.into_json() {
        Ok(j) => j,
        Err(e) => {
            return ReadinessState::NotReady {
                reason: NotReadyReason::ProviderUnreachable {
                    detail: format!("parse: {e}"),
                },
            };
        }
    };
    // Inline equivalent of `aether_l4_router::providers::ollama_vision::
    // parse_tags_response`. We duplicate the ~10-line parse so the
    // readiness probe stays feature-flag-independent (the router's
    // copy is gated on `ollama-provider`). Any drift between the two
    // is caught by the integration test that pins the wire shape.
    let installed: Vec<String> = json
        .get("models")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|m| m.get("name").and_then(|n| n.as_str()))
                .map(|s| s.to_string())
                .collect()
        })
        .unwrap_or_default();
    let installed_match = installed.iter().any(|m| {
        let bare = m.rsplit(':').next().unwrap_or(m);
        bare == model_name || m == &model_name || m.starts_with(&format!("{model_name}:"))
    });
    if !installed_match {
        return ReadinessState::NotReady {
            reason: NotReadyReason::ModelNotInstalled { model: model_name },
        };
    }

    ReadinessState::Ready
}

/// Render a ranked `[RetrievalHit]` into the deterministic prompt
/// prefix the router injects ahead of the user utterance. Returns
/// `None` for an empty slice so callers can skip prompt mutation
/// byte-for-byte.
///
/// Format (stable — do not reshape without bumping an ADR):
///
/// ```text
/// Relevant context (retrieval):
/// [1] <domain> <memory_id>: <content>
/// [2] ...
/// ```
///
/// The numbering reflects rank order as produced by
/// `run_retrieval_context`. Domain + memory_id render as plain
/// provenance so the model can cite them back. Content is included
/// verbatim; callers are responsible for content-length budgets via
/// `RetrievalConfig::max_items`.
pub fn format_retrieval_block(hits: &[RetrievalHit]) -> Option<String> {
    if hits.is_empty() {
        return None;
    }
    let mut out = String::from("Relevant context (retrieval):\n");
    for (i, h) in hits.iter().enumerate() {
        use std::fmt::Write as _;
        let _ = writeln!(
            out,
            "[{}] {} {}: {}",
            i + 1,
            h.domain.label(),
            h.memory_id,
            h.content
        );
    }
    Some(out)
}

/// Join a retrieval block + original utterance into the single string
/// the router forwards to the provider. Keeps the empty-hits case
/// byte-identical to pre-wire behaviour (returns `utterance.to_string()`).
pub fn augment_utterance(block: Option<&str>, utterance: &str) -> String {
    match block {
        Some(b) if !b.is_empty() => {
            let mut out = String::with_capacity(b.len() + utterance.len() + 1);
            out.push_str(b);
            out.push('\n');
            out.push_str(utterance);
            out
        }
        _ => utterance.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use aether_l2_memory::embeddings::StubEmbedder;
    use aether_l2_memory::{
        EmbeddingProvider, EmbeddingRow, FlatFileEmbeddingStore, MemoryRole, TurnMemoryRecord,
    };
    use std::sync::Arc;

    fn setup_state() -> AppState {
        AppState::new().expect("state")
    }

    fn swap_stub_embedder(state: &AppState, dim: usize) {
        let stub: Arc<dyn EmbeddingProvider> = Arc::new(StubEmbedder::new(dim));
        *state.embedding_provider.write().unwrap() = stub;
    }

    fn enable_embeddings(state: &AppState) {
        let mut cfg = state.memory_config();
        cfg.embeddings.enabled = true;
        cfg.embeddings.provider = Some("stub:16".into());
        state.set_memory_config(cfg).unwrap();
    }

    fn seed_durable(state: &AppState, session_id: &str, seq: u64, content: &str, ts: u64) {
        state
            .durable_memory
            .append(TurnMemoryRecord {
                session_id: session_id.into(),
                sequence: 0, // ignored by append; recomputed
                role: MemoryRole::User,
                content: content.into(),
                timestamp_ms: ts,
            })
            .unwrap();
        // Seed a paired embedding row. Use the same stub embedder so
        // the query path can actually score the content.
        let provider = state.embedding_provider.read().unwrap().clone();
        let v = provider.embed(content).unwrap();
        state
            .embedding_store
            .upsert(EmbeddingRow {
                memory_id: MemoryId::new(format!("mem-{session_id}-{seq}")),
                domain: MemoryDomain::Durable,
                vector: v,
            })
            .unwrap();
    }

    #[test]
    fn parse_memory_id_round_trip() {
        let id = MemoryId::new("mem-s1-42");
        assert_eq!(parse_memory_id(&id), Some(("s1".into(), 42)));
    }

    #[test]
    fn parse_memory_id_handles_session_ids_with_dashes() {
        // The existing `desktop-session` id contains a hyphen;
        // split-on-last-dash correctly isolates the sequence.
        let id = MemoryId::new("mem-desktop-session-9");
        assert_eq!(parse_memory_id(&id), Some(("desktop-session".into(), 9)));
    }

    #[test]
    fn parse_memory_id_rejects_malformed() {
        assert_eq!(parse_memory_id(&MemoryId::new("mem-s1")), None);
        assert_eq!(parse_memory_id(&MemoryId::new("s1-42")), None);
        assert_eq!(parse_memory_id(&MemoryId::new("mem-s1-abc")), None);
    }

    #[test]
    fn probe_returns_disabled_when_embeddings_off() {
        let s = probe_readiness(
            false,
            Some("ollama:bge-m3"),
            "http://127.0.0.1:1",
            Some(100),
        );
        assert_eq!(s, ReadinessState::Disabled);
    }

    #[test]
    fn probe_returns_low_disk_when_below_threshold() {
        let s = probe_readiness(true, Some("ollama:bge-m3"), "http://127.0.0.1:1", Some(0));
        assert!(matches!(
            s,
            ReadinessState::NotReady {
                reason: NotReadyReason::LowDisk {
                    needed_gb: 2,
                    available_gb: 0
                }
            }
        ));
    }

    #[test]
    fn probe_returns_provider_unreachable_on_dead_url() {
        // Port 1 is reserved/blocked on every platform; the connect
        // attempt fails fast. No daemon involved.
        let s = probe_readiness(true, Some("ollama:bge-m3"), "http://127.0.0.1:1", Some(100));
        assert!(matches!(
            s,
            ReadinessState::NotReady {
                reason: NotReadyReason::ProviderUnreachable { .. }
            }
        ));
    }

    #[test]
    fn probe_returns_model_not_installed_when_provider_empty() {
        let s = probe_readiness(true, None, "http://127.0.0.1:1", Some(100));
        assert!(matches!(
            s,
            ReadinessState::NotReady {
                reason: NotReadyReason::ModelNotInstalled { .. }
            }
        ));
    }

    #[test]
    fn required_disk_gb_for_provider_handles_known_models() {
        assert_eq!(required_disk_gb_for_provider(Some("ollama:bge-m3")), 2);
        assert_eq!(
            required_disk_gb_for_provider(Some("ollama:bge-small-en-v1.5")),
            1
        );
        assert_eq!(required_disk_gb_for_provider(Some("nomic-embed-text")), 1);
        // Unknown / future model → conservative default sized for bge-m3.
        assert_eq!(required_disk_gb_for_provider(Some("future-embed-2030")), 2);
        assert_eq!(required_disk_gb_for_provider(None), 2);
    }

    #[test]
    fn parse_model_name_strips_provider_prefix() {
        assert_eq!(parse_model_name("ollama:bge-m3"), "bge-m3");
        assert_eq!(parse_model_name("bge-m3"), "bge-m3");
        assert_eq!(parse_model_name("hf:org:repo:tag"), "tag");
    }

    #[test]
    fn readiness_starts_unknown_and_flips_to_disabled_when_off() {
        // ADR-0007 D3 invariant: pre-probe is Unknown; an invocation
        // with embeddings off transitions to Disabled (not NotReady —
        // off is intentional, not a failure).
        let state = setup_state();
        assert_eq!(state.retrieval_readiness(), ReadinessState::Unknown);
        let _ = run_retrieval_context(&state, "s1", "x", 5, DEFAULT_RETRIEVAL_DEADLINE);
        assert_eq!(state.retrieval_readiness(), ReadinessState::Disabled);
    }

    #[test]
    fn readiness_max_items_zero_treated_as_disabled() {
        let state = setup_state();
        let _ = run_retrieval_context(&state, "s1", "x", 0, DEFAULT_RETRIEVAL_DEADLINE);
        assert_eq!(state.retrieval_readiness(), ReadinessState::Disabled);
    }

    #[test]
    fn readiness_flips_to_ready_after_successful_invocation() {
        let state = setup_state();
        swap_stub_embedder(&state, 16);
        enable_embeddings(&state);
        seed_durable(&state, "s1", 1, "the quick brown fox", 1_000);
        let _ = run_retrieval_context(
            &state,
            "s1",
            "the quick brown fox",
            5,
            DEFAULT_RETRIEVAL_DEADLINE,
        );
        assert_eq!(state.retrieval_readiness(), ReadinessState::Ready);
    }

    #[test]
    fn readiness_flips_to_bailout_when_deadline_expires() {
        let state = setup_state();
        swap_stub_embedder(&state, 16);
        enable_embeddings(&state);
        seed_durable(&state, "s1", 1, "x", 1);
        let _ = run_retrieval_context(&state, "s1", "x", 5, Duration::from_millis(0));
        assert!(matches!(
            state.retrieval_readiness(),
            ReadinessState::NotReady {
                reason: NotReadyReason::Bailout
            }
        ));
    }

    #[test]
    fn readiness_recovers_from_not_ready_to_ready_on_next_success() {
        // Symmetric event-driven cadence — failure → not_ready, then
        // a successful invocation flips back to ready. Verifies the
        // indicator self-heals once Ollama recovers, without a
        // background poll.
        let state = setup_state();
        swap_stub_embedder(&state, 16);
        enable_embeddings(&state);
        seed_durable(&state, "s1", 1, "alpha", 1);
        // First: zero-duration deadline -> Bailout.
        let _ = run_retrieval_context(&state, "s1", "alpha", 5, Duration::from_millis(0));
        assert!(matches!(
            state.retrieval_readiness(),
            ReadinessState::NotReady { .. }
        ));
        // Second: full deadline -> Ready.
        let _ = run_retrieval_context(&state, "s1", "alpha", 5, DEFAULT_RETRIEVAL_DEADLINE);
        assert_eq!(state.retrieval_readiness(), ReadinessState::Ready);
    }

    #[test]
    fn readiness_state_serialises_to_stable_wire_form() {
        // The Tauri command surface relies on this shape — UI uses
        // `kind` to switch between rendering paths.
        let s = serde_json::to_string(&ReadinessState::Disabled).unwrap();
        assert_eq!(s, r#"{"kind":"disabled"}"#);
        let s = serde_json::to_string(&ReadinessState::Ready).unwrap();
        assert_eq!(s, r#"{"kind":"ready"}"#);
        let s = serde_json::to_string(&ReadinessState::NotReady {
            reason: NotReadyReason::ModelNotInstalled {
                model: "bge-m3".into(),
            },
        })
        .unwrap();
        assert!(s.contains(r#""kind":"not_ready""#));
        assert!(s.contains(r#""kind":"model_not_installed""#));
        assert!(s.contains(r#""model":"bge-m3""#));
    }

    #[test]
    fn off_by_default_returns_empty() {
        // ADR-0005 determinism guarantee: embeddings off → byte-identical
        // behaviour to today. The orchestrator must return [] without
        // touching providers.
        let state = setup_state();
        let hits = run_retrieval_context(&state, "s1", "hello", 5, DEFAULT_RETRIEVAL_DEADLINE);
        assert!(hits.is_empty());
    }

    #[test]
    fn max_items_zero_short_circuits() {
        let state = setup_state();
        enable_embeddings(&state);
        let hits = run_retrieval_context(&state, "s1", "hello", 0, DEFAULT_RETRIEVAL_DEADLINE);
        assert!(hits.is_empty());
    }

    #[test]
    fn returns_durable_hits_with_content_when_configured() {
        let state = setup_state();
        swap_stub_embedder(&state, 16);
        enable_embeddings(&state);
        // Seed one Durable row + its embedding via the direct helper.
        // Writing via memory_write would take the shell L5 path, which
        // is covered by memory_service tests; we want this test to
        // exercise the retrieval orchestrator against a known-good
        // seeded state.
        seed_durable(&state, "s1", 1, "the quick brown fox", 1_000);

        let hits = run_retrieval_context(
            &state,
            "s1",
            "the quick brown fox",
            5,
            DEFAULT_RETRIEVAL_DEADLINE,
        );
        assert!(!hits.is_empty(), "expected at least one hit");
        assert_eq!(hits[0].content, "the quick brown fox");
        assert_eq!(hits[0].domain, MemoryDomain::Durable);
        assert!(hits[0].score > 0.9, "same-string cosine should be ~1.0");
    }

    #[test]
    fn recency_decay_is_one_at_now_and_monotonically_decreases() {
        let now = 1_000_000_000_000u64;
        let one_day = 24 * 60 * 60 * 1000u64;
        let d_now = recency_decay(now, now, RECENCY_HALF_LIFE);
        let d_one_day = recency_decay(now - one_day, now, RECENCY_HALF_LIFE);
        let d_half = recency_decay(now - 7 * one_day, now, RECENCY_HALF_LIFE);
        let d_two = recency_decay(now - 14 * one_day, now, RECENCY_HALF_LIFE);
        assert!((d_now - 1.0).abs() < 1e-6);
        assert!(d_one_day < 1.0 && d_one_day > d_half);
        // 7-day half-life → exp(-1) ≈ 0.3679 at the half-life mark.
        assert!((d_half - (-1.0f32).exp()).abs() < 1e-3);
        assert!(d_two < d_half);
    }

    #[test]
    fn recency_decay_clamps_to_one_for_future_timestamps() {
        let now = 1_000_000_000_000u64;
        let future = now + 60_000;
        assert_eq!(recency_decay(future, now, RECENCY_HALF_LIFE), 1.0);
    }

    #[test]
    fn combined_rank_score_keeps_cosine_dominant_with_default_alpha() {
        // ADR-0010 Option A invariant: a higher cosine wins against a
        // lower cosine even when the lower-cosine row is fresher,
        // provided the cosine gap > α (the maximum recency lift).
        let now = 1_000_000_000_000u64;
        let one_day = 24 * 60 * 60 * 1000u64;
        let high_cos_old = combined_rank_score(
            0.80,
            now - 30 * one_day,
            now,
            RECENCY_WEIGHT_ALPHA,
            RECENCY_HALF_LIFE,
        );
        let low_cos_fresh = combined_rank_score(
            0.65, // 0.15 cosine gap > α (0.1 max recency contribution)
            now,
            now,
            RECENCY_WEIGHT_ALPHA,
            RECENCY_HALF_LIFE,
        );
        assert!(
            high_cos_old > low_cos_fresh,
            "cosine must dominate when gap > α: {high_cos_old} vs {low_cos_fresh}"
        );
    }

    #[test]
    fn combined_rank_score_breaks_near_ties_in_favour_of_recency() {
        // Near-ties get nudged toward the fresher row. This is the
        // behavioural lift Option A buys vs the old strict tiebreak.
        let now = 1_000_000_000_000u64;
        let one_day = 24 * 60 * 60 * 1000u64;
        let stale = combined_rank_score(
            0.70,
            now - 30 * one_day,
            now,
            RECENCY_WEIGHT_ALPHA,
            RECENCY_HALF_LIFE,
        );
        let fresh = combined_rank_score(0.70, now, now, RECENCY_WEIGHT_ALPHA, RECENCY_HALF_LIFE);
        assert!(fresh > stale, "fresh must outrank stale at equal cosine");
    }

    #[test]
    fn rank_puts_higher_score_first_and_caps_at_max_items() {
        let state = setup_state();
        swap_stub_embedder(&state, 16);
        enable_embeddings(&state);

        // Seed three rows directly. Sequence numbers 1/2/3 match what
        // InMemorySessionMemoryStore would auto-assign; embedding rows
        // reference them by mk_memory_id convention.
        seed_durable(&state, "s1", 1, "alpha fox", 1_000);
        seed_durable(&state, "s1", 2, "beta fox", 2_000);
        seed_durable(&state, "s1", 3, "gamma fox", 3_000);

        let hits = run_retrieval_context(&state, "s1", "alpha fox", 2, DEFAULT_RETRIEVAL_DEADLINE);
        assert_eq!(hits.len(), 2, "top-K=2 cap must hold");
        assert_eq!(hits[0].content, "alpha fox", "best score first");
        // Scores are monotonic non-increasing.
        assert!(
            hits[0].score >= hits[1].score,
            "rank order violated: {} vs {}",
            hits[0].score,
            hits[1].score
        );
    }

    #[test]
    fn stale_embedding_hit_is_silently_dropped() {
        // Seed an embedding row whose underlying memory row does not
        // exist (simulating a drift between flat-file embeddings and
        // the SQLite log). Orchestrator must drop the hit and return
        // an empty ranked set rather than erroring.
        let state = setup_state();
        swap_stub_embedder(&state, 16);
        enable_embeddings(&state);

        let provider = state.embedding_provider.read().unwrap().clone();
        let v = provider.embed("orphan").unwrap();
        state
            .embedding_store
            .upsert(EmbeddingRow {
                memory_id: MemoryId::new("mem-s1-999"),
                domain: MemoryDomain::Durable,
                vector: v,
            })
            .unwrap();

        // fetch_one returns None for sequence 999 (no row seeded in
        // durable_memory) — hit is dropped.
        let hits = run_retrieval_context(&state, "s1", "orphan", 5, DEFAULT_RETRIEVAL_DEADLINE);
        assert!(
            hits.is_empty(),
            "stale hit must drop, not surface malformed content"
        );
    }

    #[test]
    fn end_to_end_determinism_when_embeddings_off() {
        // The guarantee ADR-0005 ships under: with the flag off, the
        // composed pipeline produces the user's original utterance
        // byte-for-byte. If this test ever fails, the retrieval wiring
        // has introduced a side effect that would drift memory /
        // transcript state even when the user never opted in.
        let state = setup_state();
        let original = "what did we decide yesterday?";
        let hits = run_retrieval_context(&state, "s1", original, 5, DEFAULT_RETRIEVAL_DEADLINE);
        assert!(hits.is_empty());
        let block = format_retrieval_block(&hits);
        assert!(block.is_none());
        let augmented = augment_utterance(block.as_deref(), original);
        assert_eq!(augmented, original, "off-path must be byte-identical");
    }

    #[test]
    fn end_to_end_augments_when_embeddings_on_with_hits() {
        // Happy path: seed a durable row whose content matches the
        // query, flip embeddings on, compose the pipeline, and assert
        // the router sees the block-then-utterance shape.
        let state = setup_state();
        swap_stub_embedder(&state, 16);
        enable_embeddings(&state);
        seed_durable(&state, "s1", 1, "we decided to ship on friday", 1_000);

        let original = "we decided to ship on friday";
        let hits = run_retrieval_context(&state, "s1", original, 5, DEFAULT_RETRIEVAL_DEADLINE);
        assert!(!hits.is_empty());
        let block = format_retrieval_block(&hits).expect("non-empty block");
        let augmented = augment_utterance(Some(&block), original);
        assert!(augmented.starts_with("Relevant context (retrieval):"));
        assert!(augmented.ends_with(original));
        // The ORIGINAL is what memory records (via user_record_raw in
        // commands.rs); the augmented form is only what the router
        // forwards. That separation is enforced at the call site, not
        // here — this test just confirms the two strings differ when
        // retrieval fires, which is the invariant the call site relies
        // on.
        assert_ne!(augmented, original);
    }

    #[test]
    fn format_retrieval_block_none_on_empty() {
        assert!(format_retrieval_block(&[]).is_none());
    }

    #[test]
    fn format_retrieval_block_renders_rank_domain_id_content() {
        let hits = vec![
            RetrievalHit {
                memory_id: "mem-s1-1".into(),
                domain: MemoryDomain::Durable,
                score: 0.9,
                content: "alpha".into(),
                timestamp_ms: 1_000,
            },
            RetrievalHit {
                memory_id: "mem-s1-2".into(),
                domain: MemoryDomain::Facts,
                score: 0.8,
                content: "beta".into(),
                timestamp_ms: 2_000,
            },
        ];
        let out = format_retrieval_block(&hits).expect("non-empty");
        assert!(out.starts_with("Relevant context (retrieval):\n"));
        assert!(out.contains("[1] durable mem-s1-1: alpha"));
        assert!(out.contains("[2] facts mem-s1-2: beta"));
    }

    #[test]
    fn augment_utterance_noop_when_block_absent() {
        assert_eq!(augment_utterance(None, "hello"), "hello");
        assert_eq!(augment_utterance(Some(""), "hello"), "hello");
    }

    #[test]
    fn augment_utterance_prepends_block_then_newline_then_utterance() {
        let out = augment_utterance(Some("Relevant context:\n[1] x: y\n"), "do the thing");
        assert!(out.ends_with("do the thing"));
        assert!(out.starts_with("Relevant context:"));
    }

    #[test]
    fn bailout_returns_empty_when_deadline_already_passed() {
        let state = setup_state();
        swap_stub_embedder(&state, 16);
        enable_embeddings(&state);
        seed_durable(&state, "s1", 1, "content", 1_000);
        // Zero-duration deadline — the timed() gate trips before the
        // embed call runs.
        let hits = run_retrieval_context(&state, "s1", "content", 5, Duration::from_millis(0));
        assert!(hits.is_empty());
    }
}
