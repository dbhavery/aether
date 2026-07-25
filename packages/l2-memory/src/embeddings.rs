//! Memory V2 step 6 — embeddings (opt-in, local-only).
//!
//! See `docs/adr/ADR-0002-embeddings-provider-and-vector-backend.md`
//! and `docs/MEMORY-V2-ARCHITECTURE.md` §§8 (hard constraint 5), 9
//! (open questions), 10 item 6.
//!
//! ## Scope (step 6)
//!
//! - `EmbeddingProvider` trait — turns text into a Vec<f32>. One
//!   concrete impl: `OllamaEmbeddingProvider` (POST to
//!   `/api/embeddings`).
//! - `EmbeddingStore` trait — upsert, query (nearest cosine-similar),
//!   delete. One concrete impl: `FlatFileEmbeddingStore` with
//!   optional JSONL persistence.
//! - Local-only. No remote providers. Opt-in via
//!   `memory.json::embeddings.enabled`.
//!
//! ## Out of scope (intentional, per ADR-0002)
//!
//! - Retrieval wiring in the turn engine (separate slice).
//! - Vector index backends (sqlite-vec, lancedb, HNSW). The flat-file
//!   impl is the starting point; the trait is the integration
//!   contract a swap would honour.
//! - Embed-on-retention-sweep (waits for domain-typed durable store).
//!
//! The module compiles only when the `embeddings` cargo feature is
//! enabled. Default builds pay zero compile or binary cost.

use std::borrow::Cow;
use std::collections::{HashMap, HashSet};
use std::sync::Mutex;

use serde::{Deserialize, Serialize};

use crate::domain::MemoryDomain;
use crate::error::L2Error;

/// Domains eligible for embedding, per ADR-0002 §Decisions 5 and the
/// Run 3 prompt. Session is transient; Facts / Preferences are
/// structured/keyed and don't benefit from semantic indexing.
pub const EMBED_ELIGIBLE_DOMAINS: &[MemoryDomain] = &[
    MemoryDomain::Durable,
    MemoryDomain::Projects,
    MemoryDomain::Artifacts,
];

/// Stable identifier for a memory item. Scoped per-domain in the
/// embedding store — the same id string CAN appear in two different
/// domains (unlikely in practice; separation is defensive).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct MemoryId(pub String);

impl MemoryId {
    /// Construct from any `Into<String>` — matches the shell's
    /// `mk_memory_id("mem-{session}-{seq}")` pattern.
    pub fn new(s: impl Into<String>) -> Self {
        Self(s.into())
    }
}

/// One (id, vector) pair stored under one domain.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EmbeddingRow {
    /// Which memory row this vector is derived from.
    pub memory_id: MemoryId,
    /// Which domain the memory belongs to (partitions the store).
    pub domain: MemoryDomain,
    /// Dense vector, provider-dependent dimensionality.
    pub vector: Vec<f32>,
}

/// Source-of-truth for whether a memory row has an embedding attached,
/// for future telemetry / Memory-tab surfaces. Returned by
/// `query_nearest` so callers can render similarity scores.
#[derive(Debug, Clone, PartialEq)]
pub struct SimilarityHit {
    /// The indexed memory id.
    pub memory_id: MemoryId,
    /// Cosine similarity in `[-1.0, 1.0]`; higher = closer.
    pub score: f32,
}

/// Produce a vector for a given piece of text.
///
/// Kept deliberately synchronous: the shell today calls the embed
/// path from within an async command handler, and every consumer
/// already owns a tokio runtime. Blocking HTTP (`urlopen`-style) is
/// easier to reason about than a split async surface; the request
/// itself is single-digit milliseconds to Ollama on localhost.
pub trait EmbeddingProvider: Send + Sync {
    /// Return the embedding vector for `text` after input sanitization
    /// (see [`sanitize_for_embed`]). This is the entry point all
    /// callers should use; concrete providers implement [`Self::embed_raw`]
    /// instead. Implemented as a default method so every present and
    /// future `EmbeddingProvider` impl inherits sanitization for free —
    /// single source of truth, no missed call sites.
    ///
    /// Sanitization context: bge-m3 (Ollama) is documented to return
    /// NaN-vector embeddings when the input contains the U+FFFD
    /// replacement character (Phase 3A surfaced this on 6 of 848
    /// synthetic-corpus rows; recorded in the 2026-04-25 decisions
    /// log, D-015 / D-016). Cosine similarity over a NaN
    /// vector is NaN and silently breaks retrieval ranking — the
    /// boundary scrub is the cheapest, most defensible fix.
    fn embed(&self, text: &str) -> Result<Vec<f32>, L2Error> {
        let sanitized = sanitize_for_embed(text);
        self.embed_raw(sanitized.as_ref())
    }

    /// Provider-specific embedding call. Implementors do the actual
    /// work here (HTTP, subprocess, hash, …). Callers MUST NOT invoke
    /// this directly — use [`Self::embed`] so input sanitization is
    /// always applied. Marked `#[doc(hidden)]`-style only by
    /// convention; the trait is `pub` because the embedding feature
    /// crosses crate boundaries.
    fn embed_raw(&self, text: &str) -> Result<Vec<f32>, L2Error>;

    /// Provider-identifying label for logs + config validation
    /// (e.g. `"ollama:bge-m3"`).
    fn label(&self) -> String;
}

/// Strip characters that have been observed to break downstream
/// embedding providers, returning a borrowed `Cow` for the common
/// (already-clean) case so the hot path pays no allocation cost.
///
/// Currently strips:
/// - `U+FFFD` REPLACEMENT CHARACTER. bge-m3 over Ollama returns
///   NaN-vector embeddings for inputs containing this codepoint
///   (Phase 3A finding; DECISIONS_LOG D-015). U+FFFD is the canonical
///   marker for mojibake — text that was decoded with the wrong
///   codec (e.g. cp1252-bytes-as-utf8 round-trip from a generator
///   model on Windows). Replaced with ASCII space, which preserves
///   token boundaries that the surrounding text relies on.
///
/// Other zero-width / non-character codepoints (U+FEFF BOM,
/// U+200B–U+200F joiners, U+2028/U+2029 line separators) are
/// **deliberately not** stripped here. They are speculation as a
/// failure source; only U+FFFD has a demonstrated NaN-on-embed
/// reproducer in the synthetic corpus. Tightening scope keeps the
/// fix auditable and avoids silently mutating user text. Adding
/// further classes is a follow-up if and when a new failure is
/// observed.
pub fn sanitize_for_embed(text: &str) -> Cow<'_, str> {
    if !text.contains('\u{FFFD}') {
        return Cow::Borrowed(text);
    }
    Cow::Owned(text.replace('\u{FFFD}', " "))
}

/// Persist + query embedding vectors. Domain-partitioned — a query
/// only walks the requested domain's rows, keeping the linear scan
/// bounded.
pub trait EmbeddingStore: Send + Sync {
    /// Upsert (memory_id, vector) for `domain`. A subsequent upsert
    /// of the same (domain, memory_id) replaces the vector.
    fn upsert(&self, row: EmbeddingRow) -> Result<(), L2Error>;

    /// Delete the row identified by (domain, memory_id). Returns
    /// `Ok(true)` if a row was removed, `Ok(false)` if none existed.
    fn delete(&self, domain: MemoryDomain, memory_id: &MemoryId) -> Result<bool, L2Error>;

    /// Count stored rows for a domain (UX + test convenience).
    fn count(&self, domain: MemoryDomain) -> Result<usize, L2Error>;

    /// Return the top-`k` nearest rows (by cosine similarity) within
    /// `domain`. `query` must have the same dimensionality as the
    /// stored vectors; mismatch is surfaced via `L2Error::Embedding`.
    fn query_nearest(
        &self,
        domain: MemoryDomain,
        query: &[f32],
        k: usize,
    ) -> Result<Vec<SimilarityHit>, L2Error>;

    /// Return the set of memory ids that already have an embedding
    /// stored for `domain`. Implementations should be cheap (an
    /// in-memory map snapshot or filesystem scan), not embedding-side
    /// I/O — callers use this to skip already-embedded rows during a
    /// second-pass backfill.
    ///
    /// `HashSet` (rather than `Vec`/`BTreeSet`) is the chosen return
    /// shape because the consumer pattern is `set.contains(&id)`
    /// inside a hot per-row loop; `HashSet` gives O(1) per probe and
    /// the keys are owned `MemoryId`s the store already holds.
    ///
    /// Default impl returns an empty set so existing implementations
    /// do not have to opt in immediately. The semantic contract of an
    /// empty set is "skip nothing", which preserves the prior
    /// brute-force-re-embed behaviour — safer than an over-eager
    /// "everything is already embedded" default that would silently
    /// drop work. Implementations SHOULD override.
    fn embedded_ids(&self, _domain: MemoryDomain) -> Result<HashSet<MemoryId>, L2Error> {
        Ok(HashSet::new())
    }
}

/// In-process, domain-partitioned embedding store. Optional JSONL
/// persistence per domain — the shell wires a persistent path; tests
/// use the in-memory-only constructor.
///
/// Concurrency: one `Mutex` per instance guards the whole state
/// map. Personal-scale usage (tens of writes / day, tens of thousands
/// of rows at steady state) makes a coarse lock the right trade —
/// per-domain locking is a future refinement when measured contention
/// appears.
pub struct FlatFileEmbeddingStore {
    inner: Mutex<FlatFileState>,
    persist_dir: Option<std::path::PathBuf>,
}

struct FlatFileState {
    // domain → memory_id → vector
    rows: HashMap<MemoryDomain, HashMap<MemoryId, Vec<f32>>>,
}

impl FlatFileEmbeddingStore {
    /// Build a pure in-memory store. No persistence; intended for
    /// tests + default builds before a writable data dir is
    /// available.
    pub fn in_memory() -> Self {
        Self {
            inner: Mutex::new(FlatFileState {
                rows: HashMap::new(),
            }),
            persist_dir: None,
        }
    }

    /// Build a store that persists each domain as
    /// `<persist_dir>/<domain-label>.jsonl`. Reads existing rows at
    /// construction time; writes are append-or-rewrite per upsert /
    /// delete.
    pub fn with_persistence(persist_dir: impl Into<std::path::PathBuf>) -> Result<Self, L2Error> {
        let dir = persist_dir.into();
        std::fs::create_dir_all(&dir)
            .map_err(|e| L2Error::Storage(format!("embeddings dir {}: {e}", dir.display())))?;
        let mut rows: HashMap<MemoryDomain, HashMap<MemoryId, Vec<f32>>> = HashMap::new();
        for domain in EMBED_ELIGIBLE_DOMAINS.iter().copied() {
            let path = dir.join(format!("{}.jsonl", domain.label()));
            if !path.is_file() {
                continue;
            }
            let text = std::fs::read_to_string(&path).map_err(|e| {
                L2Error::Storage(format!("read embeddings {}: {e}", path.display()))
            })?;
            let entry = rows.entry(domain).or_default();
            for (line_no, line) in text.lines().enumerate() {
                let line = line.trim();
                if line.is_empty() {
                    continue;
                }
                let row: EmbeddingRow = serde_json::from_str(line).map_err(|e| {
                    L2Error::Storage(format!(
                        "parse embeddings {}:{}: {e}",
                        path.display(),
                        line_no + 1
                    ))
                })?;
                entry.insert(row.memory_id, row.vector);
            }
        }
        Ok(Self {
            inner: Mutex::new(FlatFileState { rows }),
            persist_dir: Some(dir),
        })
    }

    fn rewrite_domain(
        &self,
        domain: MemoryDomain,
        rows: &HashMap<MemoryId, Vec<f32>>,
    ) -> Result<(), L2Error> {
        let Some(dir) = self.persist_dir.as_ref() else {
            return Ok(());
        };
        let path = dir.join(format!("{}.jsonl", domain.label()));
        let tmp = path.with_extension("jsonl.tmp");
        use std::io::Write;
        let mut buf = Vec::with_capacity(rows.len() * 64);
        for (memory_id, vector) in rows {
            let row = EmbeddingRow {
                memory_id: memory_id.clone(),
                domain,
                vector: vector.clone(),
            };
            let line = serde_json::to_string(&row)
                .map_err(|e| L2Error::Storage(format!("serialize embedding: {e}")))?;
            writeln!(&mut buf, "{line}")
                .map_err(|e| L2Error::Storage(format!("embeddings buffer write: {e}")))?;
        }
        std::fs::write(&tmp, &buf)
            .map_err(|e| L2Error::Storage(format!("embeddings write {}: {e}", tmp.display())))?;
        std::fs::rename(&tmp, &path).map_err(|e| {
            L2Error::Storage(format!(
                "embeddings rename {} -> {}: {e}",
                tmp.display(),
                path.display()
            ))
        })?;
        Ok(())
    }
}

impl EmbeddingStore for FlatFileEmbeddingStore {
    fn upsert(&self, row: EmbeddingRow) -> Result<(), L2Error> {
        if !EMBED_ELIGIBLE_DOMAINS.contains(&row.domain) {
            return Err(L2Error::Embedding(format!(
                "domain {} is not embed-eligible",
                row.domain.label()
            )));
        }
        let snapshot = {
            let mut guard = self
                .inner
                .lock()
                .map_err(|e| L2Error::Internal(format!("embedding lock poisoned: {e}")))?;
            let entry = guard.rows.entry(row.domain).or_default();
            entry.insert(row.memory_id.clone(), row.vector.clone());
            entry.clone()
        };
        self.rewrite_domain(row.domain, &snapshot)
    }

    fn delete(&self, domain: MemoryDomain, memory_id: &MemoryId) -> Result<bool, L2Error> {
        let (removed, snapshot) = {
            let mut guard = self
                .inner
                .lock()
                .map_err(|e| L2Error::Internal(format!("embedding lock poisoned: {e}")))?;
            let Some(entry) = guard.rows.get_mut(&domain) else {
                return Ok(false);
            };
            let removed = entry.remove(memory_id).is_some();
            (removed, entry.clone())
        };
        if removed {
            self.rewrite_domain(domain, &snapshot)?;
        }
        Ok(removed)
    }

    fn count(&self, domain: MemoryDomain) -> Result<usize, L2Error> {
        let guard = self
            .inner
            .lock()
            .map_err(|e| L2Error::Internal(format!("embedding lock poisoned: {e}")))?;
        Ok(guard.rows.get(&domain).map(|m| m.len()).unwrap_or(0))
    }

    fn embedded_ids(&self, domain: MemoryDomain) -> Result<HashSet<MemoryId>, L2Error> {
        let guard = self
            .inner
            .lock()
            .map_err(|e| L2Error::Internal(format!("embedding lock poisoned: {e}")))?;
        Ok(guard
            .rows
            .get(&domain)
            .map(|m| m.keys().cloned().collect())
            .unwrap_or_default())
    }

    fn query_nearest(
        &self,
        domain: MemoryDomain,
        query: &[f32],
        k: usize,
    ) -> Result<Vec<SimilarityHit>, L2Error> {
        if k == 0 {
            return Ok(Vec::new());
        }
        let guard = self
            .inner
            .lock()
            .map_err(|e| L2Error::Internal(format!("embedding lock poisoned: {e}")))?;
        let Some(entry) = guard.rows.get(&domain) else {
            return Ok(Vec::new());
        };
        let query_norm = norm(query);
        if query_norm == 0.0 {
            return Err(L2Error::Embedding(
                "query vector has zero magnitude".to_string(),
            ));
        }
        let mut scored: Vec<SimilarityHit> = entry
            .iter()
            .filter_map(|(id, v)| {
                if v.len() != query.len() {
                    return None;
                }
                let v_norm = norm(v);
                if v_norm == 0.0 {
                    return None;
                }
                let score = dot(query, v) / (query_norm * v_norm);
                Some(SimilarityHit {
                    memory_id: id.clone(),
                    score,
                })
            })
            .collect();
        scored.sort_by(|a, b| {
            b.score
                .partial_cmp(&a.score)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        scored.truncate(k);
        Ok(scored)
    }
}

fn dot(a: &[f32], b: &[f32]) -> f32 {
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum()
}

fn norm(v: &[f32]) -> f32 {
    dot(v, v).sqrt()
}

// ---------------------------------------------------------------------------
// Ollama provider
// ---------------------------------------------------------------------------

/// Default Ollama embedding model. Chosen by ADR-0003 (supersedes
/// ADR-0002 Decision 1): BGE-M3, 1024-dim dense output, multi-functional
/// (dense + sparse + multi-vector capable), MIT licence, 8K context,
/// ~1.2 GB pull. ~25-point retrieval accuracy lift over
/// `nomic-embed-text` on April 2026 RAG benchmarks; still CPU-viable
/// at personal scale.
pub const DEFAULT_OLLAMA_EMBED_MODEL: &str = "bge-m3";

/// Default Ollama base URL. Matches the existing text-generation
/// default shared by the router and Quality-Eval harness.
pub const DEFAULT_OLLAMA_BASE_URL: &str = "http://127.0.0.1:11434";

/// POSTs text to a local Ollama `/api/embeddings` endpoint. Stdlib-
/// only (urllib via `ureq`-free path) — uses the same `urlopen`
/// pattern the Quality-Eval harness already ships, except in Rust.
/// Blocking by design (see trait doc comment).
pub struct OllamaEmbeddingProvider {
    base_url: String,
    model: String,
    timeout: std::time::Duration,
}

impl OllamaEmbeddingProvider {
    /// Build with explicit model + base URL.
    pub fn new(base_url: impl Into<String>, model: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into(),
            model: model.into(),
            timeout: std::time::Duration::from_secs(30),
        }
    }

    /// Build from env vars, falling back to the ADR-0002 defaults:
    ///
    /// - `AETHER_EMBED_OLLAMA_BASE_URL` — default
    ///   `http://127.0.0.1:11434`.
    /// - `AETHER_EMBED_OLLAMA_MODEL` — default `bge-m3` (ADR-0003).
    pub fn from_env() -> Self {
        let base = std::env::var("AETHER_EMBED_OLLAMA_BASE_URL")
            .unwrap_or_else(|_| DEFAULT_OLLAMA_BASE_URL.to_string());
        let model = std::env::var("AETHER_EMBED_OLLAMA_MODEL")
            .unwrap_or_else(|_| DEFAULT_OLLAMA_EMBED_MODEL.to_string());
        Self::new(base, model)
    }
}

impl EmbeddingProvider for OllamaEmbeddingProvider {
    fn embed_raw(&self, text: &str) -> Result<Vec<f32>, L2Error> {
        let url = format!("{}/api/embeddings", self.base_url.trim_end_matches('/'));
        let body = serde_json::json!({
            "model": self.model,
            "prompt": text,
        });
        let body_str = body.to_string();
        let agent = ureq::AgentBuilder::new().timeout(self.timeout).build();
        let response = agent
            .post(&url)
            .set("Content-Type", "application/json")
            .send_string(&body_str)
            .map_err(|e| L2Error::Embedding(format!("ollama embeddings transport: {e}")))?;
        let payload: serde_json::Value = response
            .into_json()
            .map_err(|e| L2Error::Embedding(format!("ollama embeddings payload: {e}")))?;
        let Some(arr) = payload.get("embedding").and_then(|v| v.as_array()) else {
            return Err(L2Error::Embedding(format!(
                "ollama embeddings response missing `embedding` array: {payload}"
            )));
        };
        let mut out = Vec::with_capacity(arr.len());
        for v in arr {
            let Some(f) = v.as_f64() else {
                return Err(L2Error::Embedding(format!(
                    "ollama embeddings non-numeric entry: {v}"
                )));
            };
            out.push(f as f32);
        }
        if out.is_empty() {
            return Err(L2Error::Embedding(
                "ollama embeddings returned empty vector".to_string(),
            ));
        }
        Ok(out)
    }

    fn label(&self) -> String {
        format!("ollama:{}", self.model)
    }
}

// ---------------------------------------------------------------------------
// Hash-based stub provider (TESTS ONLY)
// ---------------------------------------------------------------------------

/// Deterministic, dependency-free embedding provider intended for
/// tests and CI. Not a shipped default — a real user should see real
/// embeddings via `OllamaEmbeddingProvider`. Distributes token hashes
/// across a fixed dimension so "similar text → similar vector" holds
/// approximately for unit tests.
pub struct StubEmbedder {
    dim: usize,
    label: String,
}

impl StubEmbedder {
    /// Build with explicit dimensionality.
    pub fn new(dim: usize) -> Self {
        Self {
            dim,
            label: format!("stub:{dim}"),
        }
    }
}

impl EmbeddingProvider for StubEmbedder {
    fn embed_raw(&self, text: &str) -> Result<Vec<f32>, L2Error> {
        if self.dim == 0 {
            return Err(L2Error::Embedding("stub dim must be > 0".to_string()));
        }
        let mut v = vec![0.0f32; self.dim];
        for (i, byte) in text.as_bytes().iter().enumerate() {
            v[i % self.dim] += (*byte as f32) / 255.0;
        }
        // Normalise so unit-test comparisons with cosine similarity
        // behave sensibly.
        let n = norm(&v);
        if n > 0.0 {
            for x in &mut v {
                *x /= n;
            }
        }
        Ok(v)
    }

    fn label(&self) -> String {
        self.label.clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(domain: MemoryDomain, id: &str, vector: Vec<f32>) -> EmbeddingRow {
        EmbeddingRow {
            memory_id: MemoryId::new(id),
            domain,
            vector,
        }
    }

    #[test]
    fn embed_eligible_domains_locked_to_three() {
        // Session + Facts + Preferences are intentionally excluded.
        assert_eq!(EMBED_ELIGIBLE_DOMAINS.len(), 3);
        assert!(EMBED_ELIGIBLE_DOMAINS.contains(&MemoryDomain::Durable));
        assert!(EMBED_ELIGIBLE_DOMAINS.contains(&MemoryDomain::Projects));
        assert!(EMBED_ELIGIBLE_DOMAINS.contains(&MemoryDomain::Artifacts));
        assert!(!EMBED_ELIGIBLE_DOMAINS.contains(&MemoryDomain::Session));
    }

    #[test]
    fn flat_file_upsert_and_count_roundtrip() {
        let store = FlatFileEmbeddingStore::in_memory();
        assert_eq!(store.count(MemoryDomain::Durable).unwrap(), 0);
        store
            .upsert(row(MemoryDomain::Durable, "a", vec![1.0, 0.0]))
            .unwrap();
        store
            .upsert(row(MemoryDomain::Durable, "b", vec![0.0, 1.0]))
            .unwrap();
        assert_eq!(store.count(MemoryDomain::Durable).unwrap(), 2);
        // Upsert with same id replaces (not appends).
        store
            .upsert(row(MemoryDomain::Durable, "a", vec![0.5, 0.5]))
            .unwrap();
        assert_eq!(store.count(MemoryDomain::Durable).unwrap(), 2);
    }

    #[test]
    fn flat_file_rejects_ineligible_domain() {
        let store = FlatFileEmbeddingStore::in_memory();
        let err = store
            .upsert(row(MemoryDomain::Session, "x", vec![1.0, 0.0]))
            .unwrap_err();
        match err {
            L2Error::Embedding(_) => {}
            other => panic!("expected Embedding error, got {other:?}"),
        }
        // Facts and Preferences also rejected.
        assert!(store
            .upsert(row(MemoryDomain::Facts, "x", vec![1.0, 0.0]))
            .is_err());
        assert!(store
            .upsert(row(MemoryDomain::Preferences, "x", vec![1.0, 0.0]))
            .is_err());
    }

    #[test]
    fn flat_file_delete_returns_bool() {
        let store = FlatFileEmbeddingStore::in_memory();
        store
            .upsert(row(MemoryDomain::Projects, "a", vec![1.0, 0.0]))
            .unwrap();
        assert!(store
            .delete(MemoryDomain::Projects, &MemoryId::new("a"))
            .unwrap());
        assert!(!store
            .delete(MemoryDomain::Projects, &MemoryId::new("a"))
            .unwrap());
        assert!(!store
            .delete(MemoryDomain::Projects, &MemoryId::new("never-existed"))
            .unwrap());
    }

    #[test]
    fn flat_file_query_returns_top_k_by_cosine() {
        let store = FlatFileEmbeddingStore::in_memory();
        store
            .upsert(row(MemoryDomain::Durable, "east", vec![1.0, 0.0]))
            .unwrap();
        store
            .upsert(row(MemoryDomain::Durable, "north", vec![0.0, 1.0]))
            .unwrap();
        store
            .upsert(row(MemoryDomain::Durable, "ne", vec![1.0, 1.0]))
            .unwrap();
        // Query slightly east of north-east: expect `east` then `ne`.
        let hits = store
            .query_nearest(MemoryDomain::Durable, &[0.9, 0.3], 2)
            .unwrap();
        assert_eq!(hits.len(), 2);
        assert_eq!(hits[0].memory_id, MemoryId::new("east"));
        assert!(hits[0].score > hits[1].score);
    }

    #[test]
    fn flat_file_query_k_zero_is_empty() {
        let store = FlatFileEmbeddingStore::in_memory();
        store
            .upsert(row(MemoryDomain::Durable, "a", vec![1.0, 0.0]))
            .unwrap();
        assert!(store
            .query_nearest(MemoryDomain::Durable, &[1.0, 0.0], 0)
            .unwrap()
            .is_empty());
    }

    #[test]
    fn flat_file_query_empty_store_is_empty() {
        let store = FlatFileEmbeddingStore::in_memory();
        assert!(store
            .query_nearest(MemoryDomain::Durable, &[1.0, 0.0], 5)
            .unwrap()
            .is_empty());
    }

    #[test]
    fn flat_file_query_zero_vector_errors() {
        let store = FlatFileEmbeddingStore::in_memory();
        store
            .upsert(row(MemoryDomain::Durable, "a", vec![1.0, 0.0]))
            .unwrap();
        assert!(matches!(
            store.query_nearest(MemoryDomain::Durable, &[0.0, 0.0], 1),
            Err(L2Error::Embedding(_))
        ));
    }

    #[test]
    fn flat_file_persistence_roundtrip() {
        let tmp = tempfile::TempDir::new().unwrap();
        {
            let store = FlatFileEmbeddingStore::with_persistence(tmp.path()).unwrap();
            store
                .upsert(row(MemoryDomain::Durable, "a", vec![0.3, 0.4]))
                .unwrap();
            store
                .upsert(row(MemoryDomain::Projects, "p1", vec![1.0, 0.0]))
                .unwrap();
        }
        // Reopen — rows should be there.
        let reopened = FlatFileEmbeddingStore::with_persistence(tmp.path()).unwrap();
        assert_eq!(reopened.count(MemoryDomain::Durable).unwrap(), 1);
        assert_eq!(reopened.count(MemoryDomain::Projects).unwrap(), 1);
        let hits = reopened
            .query_nearest(MemoryDomain::Durable, &[0.3, 0.4], 1)
            .unwrap();
        assert_eq!(hits[0].memory_id, MemoryId::new("a"));
    }

    #[test]
    fn stub_embedder_is_deterministic() {
        let e = StubEmbedder::new(16);
        let a = e.embed("hello world").unwrap();
        let b = e.embed("hello world").unwrap();
        assert_eq!(a, b);
        assert_eq!(a.len(), 16);
    }

    #[test]
    fn stub_embedder_similar_texts_have_higher_similarity() {
        let e = StubEmbedder::new(32);
        let a = e.embed("the quick brown fox").unwrap();
        let b = e.embed("the quick brown cat").unwrap();
        let c = e.embed("completely different sentence").unwrap();
        let ab = dot(&a, &b);
        let ac = dot(&a, &c);
        assert!(
            ab > ac,
            "similar sentences should score higher: ab={ab} ac={ac}"
        );
    }

    #[test]
    fn embedded_ids_empty_store_returns_empty_set() {
        let store = FlatFileEmbeddingStore::in_memory();
        let ids = store.embedded_ids(MemoryDomain::Durable).unwrap();
        assert!(ids.is_empty());
    }

    #[test]
    fn embedded_ids_returns_only_requested_domain() {
        let store = FlatFileEmbeddingStore::in_memory();
        store
            .upsert(row(MemoryDomain::Durable, "d-a", vec![1.0, 0.0]))
            .unwrap();
        store
            .upsert(row(MemoryDomain::Durable, "d-b", vec![0.0, 1.0]))
            .unwrap();
        store
            .upsert(row(MemoryDomain::Projects, "p-a", vec![1.0, 0.0]))
            .unwrap();

        let durable = store.embedded_ids(MemoryDomain::Durable).unwrap();
        assert_eq!(durable.len(), 2);
        assert!(durable.contains(&MemoryId::new("d-a")));
        assert!(durable.contains(&MemoryId::new("d-b")));
        assert!(!durable.contains(&MemoryId::new("p-a")));

        let projects = store.embedded_ids(MemoryDomain::Projects).unwrap();
        assert_eq!(projects.len(), 1);
        assert!(projects.contains(&MemoryId::new("p-a")));

        // A domain with no rows ever inserted returns an empty set
        // rather than erroring — the consumer treats "no entry" and
        // "empty entry" the same way.
        let artifacts = store.embedded_ids(MemoryDomain::Artifacts).unwrap();
        assert!(artifacts.is_empty());
    }

    #[test]
    fn embedded_ids_reflects_upsert_replace_and_delete() {
        let store = FlatFileEmbeddingStore::in_memory();
        store
            .upsert(row(MemoryDomain::Durable, "a", vec![1.0, 0.0]))
            .unwrap();
        store
            .upsert(row(MemoryDomain::Durable, "a", vec![0.5, 0.5]))
            .unwrap();
        // Replace must not duplicate.
        let after_replace = store.embedded_ids(MemoryDomain::Durable).unwrap();
        assert_eq!(after_replace.len(), 1);
        // Delete removes from the set.
        store
            .delete(MemoryDomain::Durable, &MemoryId::new("a"))
            .unwrap();
        let after_delete = store.embedded_ids(MemoryDomain::Durable).unwrap();
        assert!(after_delete.is_empty());
    }

    #[test]
    fn embedded_ids_persistence_roundtrip() {
        let tmp = tempfile::TempDir::new().unwrap();
        {
            let store = FlatFileEmbeddingStore::with_persistence(tmp.path()).unwrap();
            store
                .upsert(row(MemoryDomain::Durable, "a", vec![0.3, 0.4]))
                .unwrap();
            store
                .upsert(row(MemoryDomain::Durable, "b", vec![0.1, 0.9]))
                .unwrap();
        }
        let reopened = FlatFileEmbeddingStore::with_persistence(tmp.path()).unwrap();
        let ids = reopened.embedded_ids(MemoryDomain::Durable).unwrap();
        assert_eq!(ids.len(), 2);
        assert!(ids.contains(&MemoryId::new("a")));
        assert!(ids.contains(&MemoryId::new("b")));
    }

    #[test]
    fn ollama_provider_label_includes_model() {
        let p = OllamaEmbeddingProvider::new("http://localhost:11434", "bge-m3");
        assert_eq!(p.label(), "ollama:bge-m3");
    }

    // -----------------------------------------------------------------
    // Sanitization (DECISIONS_LOG D-016 / Phase 3A NaN-on-U+FFFD fix)
    // -----------------------------------------------------------------

    #[test]
    fn sanitize_replaces_ffffd_with_space() {
        // The exact case Phase 3A surfaced: an en-dash mojibaked into
        // U+FFFD between two words. Result must contain neither U+FFFD
        // nor a token-merging artefact (so we replace, not strip).
        let out = sanitize_for_embed("hello\u{FFFD}world");
        assert_eq!(out.as_ref(), "hello world");
        assert!(!out.contains('\u{FFFD}'));
    }

    #[test]
    fn sanitize_clean_text_is_borrowed_no_alloc() {
        let input = "perfectly clean utf-8 text — with an em dash";
        let out = sanitize_for_embed(input);
        // Cow::Borrowed for the common case: input pointer equals
        // output pointer.
        assert!(matches!(out, Cow::Borrowed(_)));
        assert_eq!(out.as_ref(), input);
    }

    #[test]
    fn sanitize_multiple_ffffd_all_replaced() {
        let out = sanitize_for_embed("a\u{FFFD}b\u{FFFD}c\u{FFFD}");
        assert_eq!(out.as_ref(), "a b c ");
        assert!(!out.contains('\u{FFFD}'));
    }

    #[test]
    fn sanitize_empty_string_is_borrowed() {
        let out = sanitize_for_embed("");
        assert!(matches!(out, Cow::Borrowed(_)));
        assert_eq!(out.as_ref(), "");
    }

    #[test]
    fn sanitize_leaves_other_unicode_alone() {
        // Scope is intentionally narrow: BOM, ZWJ, line separators are
        // NOT touched. They are speculative as a failure source; only
        // U+FFFD has a demonstrated repro. This test pins that scope so
        // a future widening is a deliberate, reviewed change.
        let input = "bom\u{FEFF}zwj\u{200D}sep\u{2028}end";
        let out = sanitize_for_embed(input);
        assert_eq!(out.as_ref(), input);
        assert!(matches!(out, Cow::Borrowed(_)));
    }

    /// Test-only embed provider that records the exact text it
    /// receives, so we can verify the trait-default `embed` runs
    /// sanitization before reaching `embed_raw`.
    struct CapturingProvider {
        last_seen: Mutex<Option<String>>,
    }

    impl CapturingProvider {
        fn new() -> Self {
            Self {
                last_seen: Mutex::new(None),
            }
        }
    }

    impl EmbeddingProvider for CapturingProvider {
        fn embed_raw(&self, text: &str) -> Result<Vec<f32>, L2Error> {
            *self.last_seen.lock().unwrap() = Some(text.to_string());
            Ok(vec![0.0, 1.0])
        }
        fn label(&self) -> String {
            "capturing".to_string()
        }
    }

    #[test]
    fn trait_default_embed_sanitizes_before_calling_embed_raw() {
        let p = CapturingProvider::new();
        // Public entry point — not embed_raw.
        let _ = p.embed("clean\u{FFFD}input").unwrap();
        let seen = p.last_seen.lock().unwrap().clone().unwrap();
        assert_eq!(seen, "clean input");
        assert!(!seen.contains('\u{FFFD}'));
    }

    #[test]
    fn trait_default_embed_passes_clean_text_through_unchanged() {
        let p = CapturingProvider::new();
        let _ = p.embed("already clean").unwrap();
        let seen = p.last_seen.lock().unwrap().clone().unwrap();
        assert_eq!(seen, "already clean");
    }
}
