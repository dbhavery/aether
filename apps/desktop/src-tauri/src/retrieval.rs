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

use crate::memory_config::MemoryDomain as ShellDomain;
use crate::state::AppState;

/// Default hard deadline for the full embed + query + fetch pipeline.
/// Per ADR-0005 §Decision 1.
pub const DEFAULT_RETRIEVAL_DEADLINE: Duration = Duration::from_secs(5);

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
        return Vec::new();
    }
    let cfg = state.memory_config();
    if !cfg.embeddings.enabled {
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
    };
    let decision = {
        let active = state.active.read().expect("active read lock");
        match active.policy.evaluate(gate_request) {
            Ok(d) => d,
            Err(e) => {
                tracing::warn!("retrieval policy evaluate: {e}");
                return Vec::new();
            }
        }
    };
    if !matches!(decision, Decision::Allow { .. }) {
        tracing::warn!("retrieval gate non-Allow; skipping");
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
                return Vec::new();
            }
            TimedResult::Timeout => {
                tracing::warn!(
                    "retrieval embed phase exceeded {}s deadline",
                    deadline.as_secs()
                );
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
    resolved.sort_by(|a, b| match b.score.partial_cmp(&a.score) {
        Some(Ordering::Equal) | None => b.timestamp_ms.cmp(&a.timestamp_ms),
        Some(ord) => ord,
    });
    resolved.truncate(max_items);
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
