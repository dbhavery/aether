//! Wave L2.1 — turn-scoped conversation memory.
//!
//! A deliberately narrow first slice of L2: a bounded, in-process, per-session
//! transcript buffer used by the demo/runtime path to preserve short
//! conversational continuity across turns.
//!
//! ## Scope
//!
//! - recent transcript only (role + text + sequence + timestamp),
//! - bounded by a [`RecentMemoryConfig`] (max turns and/or max characters),
//! - per-session isolation,
//! - no embeddings, no summarisation, no durable storage, no LLM calls.
//!
//! The richer durable-memory surface — retention sweep, embeddings,
//! cross-session recall — is a separate concern that grows through
//! Memory V2 steps 5+ (see `docs/MEMORY-V2-ARCHITECTURE.md`). This
//! module does **not** try to be the final memory system; it closes
//! the immediate amnesia gap only.
//!
//! ## Integration
//!
//! Intended composition point: the integration layer (e.g. the L1 CLI demo
//! app) constructs a `SessionMemoryStore`, appends both user and assistant
//! records around each turn, and renders [`RecentMemoryWindow`] into the
//! router prompt via [`render_transcript`] so the model sees short-range
//! continuity.
//!
//! L1 (`aether-l1-interaction`) does not depend on L2. Any wiring that uses
//! L2 must live in a layer allowed to depend on both (demo apps, integration
//! tests, future orchestration crates) — see `CLAUDE.md` §1.4 and the
//! layer-boundary linter.

use std::collections::{HashMap, VecDeque};
use std::sync::Mutex;

use serde::{Deserialize, Serialize};

use crate::error::L2Error;

/// Speaker role attached to a [`TurnMemoryRecord`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MemoryRole {
    /// The human user.
    User,
    /// The assistant / companion.
    Assistant,
    /// System / operational note (e.g. policy block summary).
    System,
}

impl MemoryRole {
    /// Short label used by [`render_transcript`].
    pub fn label(self) -> &'static str {
        match self {
            MemoryRole::User => "User",
            MemoryRole::Assistant => "Companion",
            MemoryRole::System => "System",
        }
    }
}

/// One entry in the recent-conversation buffer.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TurnMemoryRecord {
    /// Session this record belongs to.
    pub session_id: String,
    /// Monotonic per-session sequence number assigned at `append` time.
    /// Stable across calls; lower values are older.
    pub sequence: u64,
    /// Speaker role.
    pub role: MemoryRole,
    /// Raw text content.
    pub content: String,
    /// Wall-clock milliseconds since the Unix epoch. Supplied by the caller so
    /// the store remains pure and testable (no implicit clock dependency).
    pub timestamp_ms: u64,
}

/// A bounded slice of recent records for one session, oldest-first.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RecentMemoryWindow {
    /// Session id the window is for.
    pub session_id: String,
    /// Records in insertion order (oldest first).
    pub records: Vec<TurnMemoryRecord>,
}

impl RecentMemoryWindow {
    /// Convenience: is the window empty?
    pub fn is_empty(&self) -> bool {
        self.records.is_empty()
    }
}

/// Bounding policy for the in-memory store. Both dials are applied — whichever
/// limit hits first triggers eviction of the oldest record.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RecentMemoryConfig {
    /// Maximum records retained per session. Must be ≥ 1.
    pub max_turns: usize,
    /// Maximum total `content` characters retained per session. Must be ≥ 1.
    pub max_chars: usize,
}

impl RecentMemoryConfig {
    /// Conservative default tuned for a short CLI conversation: 16 records or
    /// 8 KiB of transcript, whichever fills first.
    pub const fn default_narrow() -> Self {
        Self {
            max_turns: 16,
            max_chars: 8 * 1024,
        }
    }
}

impl Default for RecentMemoryConfig {
    fn default() -> Self {
        Self::default_narrow()
    }
}

/// Narrow session-memory surface. Implementations are thread-safe.
///
/// Semantics:
/// - `append` assigns a monotonic per-session `sequence` and applies the
///   bounding policy immediately (oldest-first eviction).
/// - `recent` returns a snapshot of the current window, oldest-first.
/// - `clear_session` removes all records for one session; other sessions are
///   untouched.
pub trait SessionMemoryStore: Send + Sync {
    /// Append one record. The record's own `sequence` field is ignored on
    /// input — the store assigns the next value and echoes it back via the
    /// window on the next `recent` call.
    fn append(&self, record: TurnMemoryRecord) -> Result<(), L2Error>;

    /// Snapshot the current window for `session_id`. Returns an empty window
    /// (not an error) for unknown sessions.
    fn recent(&self, session_id: &str) -> Result<RecentMemoryWindow, L2Error>;

    /// Remove all records for `session_id`. No-op if unknown.
    fn clear_session(&self, session_id: &str) -> Result<(), L2Error>;

    /// Remove one record by `(session_id, sequence)`. Returns `Ok(true)`
    /// when a matching row was removed, `Ok(false)` when no such row
    /// existed — either because the session is unknown or the sequence
    /// was never appended / has already been evicted. This silent
    /// no-op shape keeps the Memory V2 "forget item" UX honest: the
    /// Trust drawer can issue a forget against a row the retention
    /// sweep has already claimed without the call failing.
    ///
    /// `max_turns` / `max_chars` are NOT re-enforced after a remove —
    /// removal only ever shrinks the window.
    fn remove(&self, session_id: &str, sequence: u64) -> Result<bool, L2Error>;

    /// Replace the `content` of one record addressed by
    /// `(session_id, sequence)`. Returns `Ok(true)` when the target
    /// existed and was updated, `Ok(false)` otherwise. `role`,
    /// `timestamp_ms`, and `sequence` are preserved — callers expressing
    /// "the user edited this fact" should not rewrite provenance.
    ///
    /// `max_chars` IS re-enforced after an update so an overlong edit
    /// cannot sidestep the bound; the edited row itself is never
    /// evicted — only older rows if the new total exceeds the budget
    /// and there is still more than one row.
    fn update(&self, session_id: &str, sequence: u64, new_content: String)
        -> Result<bool, L2Error>;

    /// Delete every record in `session_id` whose `timestamp_ms` is
    /// strictly less than `cutoff_ms`. Returns the number of rows
    /// evicted. Memory V2 step 5 — the retention sweep calls this per
    /// session once a domain's `retention_days` cutoff is known.
    /// `cutoff_ms == 0` is a no-op (nothing is older than epoch);
    /// unknown sessions return `Ok(0)`.
    fn prune_before(&self, session_id: &str, cutoff_ms: u64) -> Result<usize, L2Error>;

    /// Enumerate every session that currently has at least one row in
    /// the store. Order is unspecified. Used by the retention sweep to
    /// walk the set without needing to know which sessions the shell
    /// has ever opened. Empty vec for an empty store.
    fn list_sessions(&self) -> Result<Vec<String>, L2Error>;

    /// ADR-0005: look up one row by `(session_id, sequence)`. Returns
    /// `Ok(None)` when the row has been evicted or never existed —
    /// the retrieval orchestrator treats a `None` as "stale embedding
    /// row; drop the hit". Returns `Err(_)` on storage failure.
    ///
    /// Separate from `recent` because retrieval touches one row at a
    /// time, not a bounded tail, and because the resulting
    /// `TurnMemoryRecord` carries the `timestamp_ms` that the
    /// retrieval rank step needs for its recency tiebreak.
    fn fetch_one(
        &self,
        session_id: &str,
        sequence: u64,
    ) -> Result<Option<TurnMemoryRecord>, L2Error>;
}

/// In-process implementation of [`SessionMemoryStore`]. Backed by a
/// per-session `VecDeque`; evicts from the front when bounds are exceeded.
///
/// Intended use: demo apps, integration tests, development runtime. A durable
/// backend lives in a later wave and is out of scope for L2.1.
pub struct InMemorySessionMemoryStore {
    config: RecentMemoryConfig,
    inner: Mutex<HashMap<String, SessionState>>,
}

struct SessionState {
    next_seq: u64,
    total_chars: usize,
    records: VecDeque<TurnMemoryRecord>,
}

impl SessionState {
    fn new() -> Self {
        Self {
            next_seq: 1,
            total_chars: 0,
            records: VecDeque::new(),
        }
    }
}

impl InMemorySessionMemoryStore {
    /// Build a new store with an explicit config.
    pub fn new(config: RecentMemoryConfig) -> Self {
        Self {
            config,
            inner: Mutex::new(HashMap::new()),
        }
    }

    /// Build a new store with [`RecentMemoryConfig::default_narrow`].
    pub fn new_default() -> Self {
        Self::new(RecentMemoryConfig::default_narrow())
    }

    fn trim(state: &mut SessionState, cfg: &RecentMemoryConfig) {
        while state.records.len() > cfg.max_turns {
            if let Some(r) = state.records.pop_front() {
                state.total_chars = state.total_chars.saturating_sub(r.content.len());
            }
        }
        while state.total_chars > cfg.max_chars && state.records.len() > 1 {
            if let Some(r) = state.records.pop_front() {
                state.total_chars = state.total_chars.saturating_sub(r.content.len());
            }
        }
    }
}

impl SessionMemoryStore for InMemorySessionMemoryStore {
    fn append(&self, record: TurnMemoryRecord) -> Result<(), L2Error> {
        let mut guard = self
            .inner
            .lock()
            .map_err(|e| L2Error::Internal(format!("session memory lock poisoned: {e}")))?;
        let state = guard
            .entry(record.session_id.clone())
            .or_insert_with(SessionState::new);
        let mut rec = record;
        rec.sequence = state.next_seq;
        state.next_seq += 1;
        state.total_chars += rec.content.len();
        state.records.push_back(rec);
        Self::trim(state, &self.config);
        Ok(())
    }

    fn recent(&self, session_id: &str) -> Result<RecentMemoryWindow, L2Error> {
        let guard = self
            .inner
            .lock()
            .map_err(|e| L2Error::Internal(format!("session memory lock poisoned: {e}")))?;
        let records = guard
            .get(session_id)
            .map(|s| s.records.iter().cloned().collect::<Vec<_>>())
            .unwrap_or_default();
        Ok(RecentMemoryWindow {
            session_id: session_id.to_string(),
            records,
        })
    }

    fn clear_session(&self, session_id: &str) -> Result<(), L2Error> {
        let mut guard = self
            .inner
            .lock()
            .map_err(|e| L2Error::Internal(format!("session memory lock poisoned: {e}")))?;
        guard.remove(session_id);
        Ok(())
    }

    fn remove(&self, session_id: &str, sequence: u64) -> Result<bool, L2Error> {
        let mut guard = self
            .inner
            .lock()
            .map_err(|e| L2Error::Internal(format!("session memory lock poisoned: {e}")))?;
        let Some(state) = guard.get_mut(session_id) else {
            return Ok(false);
        };
        // Linear scan is fine: session windows are bounded to tens of
        // records, and `VecDeque` has no indexed removal by predicate.
        let pos = state.records.iter().position(|r| r.sequence == sequence);
        match pos {
            Some(i) => {
                if let Some(rec) = state.records.remove(i) {
                    state.total_chars = state.total_chars.saturating_sub(rec.content.len());
                }
                Ok(true)
            }
            None => Ok(false),
        }
    }

    fn update(
        &self,
        session_id: &str,
        sequence: u64,
        new_content: String,
    ) -> Result<bool, L2Error> {
        let mut guard = self
            .inner
            .lock()
            .map_err(|e| L2Error::Internal(format!("session memory lock poisoned: {e}")))?;
        let Some(state) = guard.get_mut(session_id) else {
            return Ok(false);
        };
        let Some(rec) = state.records.iter_mut().find(|r| r.sequence == sequence) else {
            return Ok(false);
        };
        let old_len = rec.content.len();
        let new_len = new_content.len();
        rec.content = new_content;
        state.total_chars = state
            .total_chars
            .saturating_sub(old_len)
            .saturating_add(new_len);
        // Re-enforce max_chars only. We intentionally do NOT call
        // `Self::trim` because `trim` also enforces max_turns, and a
        // same-length edit must never evict neighbours. Evict older
        // rows only while the edited row is not the front, so an
        // oversized edit can never evict itself.
        let cfg = &self.config;
        while state.total_chars > cfg.max_chars && state.records.len() > 1 {
            // Only evict from the front if the front is not the
            // edited row itself.
            let front_is_target = state
                .records
                .front()
                .map(|r| r.sequence == sequence)
                .unwrap_or(false);
            if front_is_target {
                break;
            }
            if let Some(dropped) = state.records.pop_front() {
                state.total_chars = state.total_chars.saturating_sub(dropped.content.len());
            }
        }
        Ok(true)
    }

    fn prune_before(&self, session_id: &str, cutoff_ms: u64) -> Result<usize, L2Error> {
        let mut guard = self
            .inner
            .lock()
            .map_err(|e| L2Error::Internal(format!("session memory lock poisoned: {e}")))?;
        let Some(state) = guard.get_mut(session_id) else {
            return Ok(0);
        };
        let before = state.records.len();
        // `VecDeque::retain` preserves relative order. Each evicted row
        // reduces `total_chars` by its content length.
        let mut freed = 0usize;
        state.records.retain(|r| {
            if r.timestamp_ms < cutoff_ms {
                freed = freed.saturating_add(r.content.len());
                false
            } else {
                true
            }
        });
        state.total_chars = state.total_chars.saturating_sub(freed);
        Ok(before - state.records.len())
    }

    fn list_sessions(&self) -> Result<Vec<String>, L2Error> {
        let guard = self
            .inner
            .lock()
            .map_err(|e| L2Error::Internal(format!("session memory lock poisoned: {e}")))?;
        Ok(guard.keys().cloned().collect())
    }

    fn fetch_one(
        &self,
        session_id: &str,
        sequence: u64,
    ) -> Result<Option<TurnMemoryRecord>, L2Error> {
        let guard = self
            .inner
            .lock()
            .map_err(|e| L2Error::Internal(format!("session memory lock poisoned: {e}")))?;
        let Some(state) = guard.get(session_id) else {
            return Ok(None);
        };
        Ok(state
            .records
            .iter()
            .find(|r| r.sequence == sequence)
            .cloned())
    }
}

/// Render a [`RecentMemoryWindow`] as a deterministic, line-per-entry
/// transcript block suitable for prepending to a prompt. Returns an empty
/// string for an empty window so callers can unconditionally concatenate.
pub fn render_transcript(window: &RecentMemoryWindow) -> String {
    if window.records.is_empty() {
        return String::new();
    }
    let mut s = String::with_capacity(window.records.len() * 48);
    s.push_str("Recent conversation:\n");
    for r in &window.records {
        s.push_str("- ");
        s.push_str(r.role.label());
        s.push_str(": ");
        s.push_str(&r.content);
        s.push('\n');
    }
    s
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rec(session: &str, role: MemoryRole, content: &str, ts: u64) -> TurnMemoryRecord {
        TurnMemoryRecord {
            session_id: session.to_string(),
            sequence: 0,
            role,
            content: content.to_string(),
            timestamp_ms: ts,
        }
    }

    #[test]
    fn append_preserves_order_and_assigns_sequences() {
        let store = InMemorySessionMemoryStore::new_default();
        store.append(rec("s1", MemoryRole::User, "hi", 1)).unwrap();
        store
            .append(rec("s1", MemoryRole::Assistant, "hello", 2))
            .unwrap();
        store
            .append(rec("s1", MemoryRole::User, "how are you", 3))
            .unwrap();
        let w = store.recent("s1").unwrap();
        assert_eq!(w.records.len(), 3);
        assert_eq!(w.records[0].content, "hi");
        assert_eq!(w.records[1].content, "hello");
        assert_eq!(w.records[2].content, "how are you");
        assert_eq!(w.records[0].sequence, 1);
        assert_eq!(w.records[1].sequence, 2);
        assert_eq!(w.records[2].sequence, 3);
    }

    #[test]
    fn max_turns_evicts_oldest() {
        let cfg = RecentMemoryConfig {
            max_turns: 3,
            max_chars: 10_000,
        };
        let store = InMemorySessionMemoryStore::new(cfg);
        for i in 0..5 {
            store
                .append(rec("s1", MemoryRole::User, &format!("u{i}"), i as u64))
                .unwrap();
        }
        let w = store.recent("s1").unwrap();
        assert_eq!(w.records.len(), 3);
        assert_eq!(w.records[0].content, "u2");
        assert_eq!(w.records[2].content, "u4");
    }

    #[test]
    fn max_chars_evicts_oldest() {
        // 4 records * 5 chars = 20 > budget 12; evict front until fits.
        let cfg = RecentMemoryConfig {
            max_turns: 100,
            max_chars: 12,
        };
        let store = InMemorySessionMemoryStore::new(cfg);
        for i in 0..4 {
            store
                .append(rec("s1", MemoryRole::User, &format!("abcd{i}"), i as u64))
                .unwrap();
        }
        let w = store.recent("s1").unwrap();
        // At least the most recent record is retained; oldest are gone.
        assert!(!w.records.is_empty());
        assert!(w.records.len() < 4);
        let total: usize = w.records.iter().map(|r| r.content.len()).sum();
        assert!(total <= 12 || w.records.len() == 1);
        assert_eq!(w.records.last().unwrap().content, "abcd3");
    }

    #[test]
    fn sessions_are_isolated() {
        let store = InMemorySessionMemoryStore::new_default();
        store
            .append(rec("s1", MemoryRole::User, "alpha", 1))
            .unwrap();
        store
            .append(rec("s2", MemoryRole::User, "beta", 1))
            .unwrap();
        let w1 = store.recent("s1").unwrap();
        let w2 = store.recent("s2").unwrap();
        assert_eq!(w1.records.len(), 1);
        assert_eq!(w1.records[0].content, "alpha");
        assert_eq!(w2.records.len(), 1);
        assert_eq!(w2.records[0].content, "beta");
    }

    #[test]
    fn clear_session_removes_only_one_session() {
        let store = InMemorySessionMemoryStore::new_default();
        store.append(rec("s1", MemoryRole::User, "x", 1)).unwrap();
        store.append(rec("s2", MemoryRole::User, "y", 1)).unwrap();
        store.clear_session("s1").unwrap();
        assert!(store.recent("s1").unwrap().is_empty());
        assert_eq!(store.recent("s2").unwrap().records.len(), 1);
    }

    #[test]
    fn recent_on_unknown_session_is_empty_not_error() {
        let store = InMemorySessionMemoryStore::new_default();
        let w = store.recent("never-seen").unwrap();
        assert!(w.is_empty());
        assert_eq!(w.session_id, "never-seen");
    }

    // ----- remove / update (Memory V2 step 4 surface) -----

    #[test]
    fn remove_deletes_single_record_and_returns_true() {
        let store = InMemorySessionMemoryStore::new_default();
        store
            .append(rec("s1", MemoryRole::User, "keep-a", 1))
            .unwrap();
        store
            .append(rec("s1", MemoryRole::User, "drop-me", 2))
            .unwrap();
        store
            .append(rec("s1", MemoryRole::User, "keep-b", 3))
            .unwrap();
        let removed = store.remove("s1", 2).unwrap();
        assert!(removed);
        let w = store.recent("s1").unwrap();
        assert_eq!(w.records.len(), 2);
        assert_eq!(w.records[0].content, "keep-a");
        assert_eq!(w.records[1].content, "keep-b");
    }

    #[test]
    fn remove_unknown_sequence_is_false_not_error() {
        let store = InMemorySessionMemoryStore::new_default();
        store.append(rec("s1", MemoryRole::User, "x", 1)).unwrap();
        assert!(!store.remove("s1", 999).unwrap());
        assert!(!store.remove("unknown-session", 1).unwrap());
        // Existing row is untouched.
        assert_eq!(store.recent("s1").unwrap().records.len(), 1);
    }

    #[test]
    fn remove_adjusts_total_chars_for_future_inserts() {
        // Tight budget so char accounting matters.
        let cfg = RecentMemoryConfig {
            max_turns: 100,
            max_chars: 10,
        };
        let store = InMemorySessionMemoryStore::new(cfg);
        store
            .append(rec("s1", MemoryRole::User, "aaaa", 1))
            .unwrap(); // seq 1, 4 chars
        store
            .append(rec("s1", MemoryRole::User, "bbbb", 2))
            .unwrap(); // seq 2, 4 chars; total=8
        assert!(store.remove("s1", 1).unwrap());
        // Budget freed — a 4-char append should not evict seq 2.
        store
            .append(rec("s1", MemoryRole::User, "cccc", 3))
            .unwrap();
        let w = store.recent("s1").unwrap();
        assert_eq!(w.records.len(), 2);
        assert_eq!(w.records[0].content, "bbbb");
        assert_eq!(w.records[1].content, "cccc");
    }

    #[test]
    fn update_replaces_content_preserves_role_and_timestamp() {
        let store = InMemorySessionMemoryStore::new_default();
        store
            .append(rec("s1", MemoryRole::User, "original", 42))
            .unwrap();
        let updated = store.update("s1", 1, "edited".into()).unwrap();
        assert!(updated);
        let w = store.recent("s1").unwrap();
        assert_eq!(w.records.len(), 1);
        assert_eq!(w.records[0].content, "edited");
        assert_eq!(w.records[0].sequence, 1);
        assert_eq!(w.records[0].role, MemoryRole::User);
        assert_eq!(w.records[0].timestamp_ms, 42);
    }

    #[test]
    fn update_unknown_returns_false() {
        let store = InMemorySessionMemoryStore::new_default();
        assert!(!store.update("never", 1, "x".into()).unwrap());
        store.append(rec("s1", MemoryRole::User, "a", 1)).unwrap();
        assert!(!store.update("s1", 999, "x".into()).unwrap());
        assert_eq!(store.recent("s1").unwrap().records[0].content, "a");
    }

    #[test]
    fn update_enforces_max_chars_but_never_evicts_edited_row() {
        let cfg = RecentMemoryConfig {
            max_turns: 100,
            max_chars: 10,
        };
        let store = InMemorySessionMemoryStore::new(cfg);
        store.append(rec("s1", MemoryRole::User, "aa", 1)).unwrap(); // 2 chars
        store.append(rec("s1", MemoryRole::User, "bb", 2)).unwrap(); // 4 total
        store.append(rec("s1", MemoryRole::User, "cc", 3)).unwrap(); // 6 total
                                                                     // Grow seq 3 to 20 chars. Budget is 10. Oldest rows (seq 1, 2)
                                                                     // must be evicted to fit — but seq 3 itself must remain.
        assert!(store.update("s1", 3, "x".repeat(20)).unwrap());
        let w = store.recent("s1").unwrap();
        assert!(w.records.iter().any(|r| r.sequence == 3));
        assert_eq!(w.records.last().unwrap().content.len(), 20);
    }

    // ----- prune_before / list_sessions (Memory V2 step 5 surface) -----

    #[test]
    fn prune_before_drops_rows_older_than_cutoff() {
        let store = InMemorySessionMemoryStore::new_default();
        // timestamps: 100, 200, 300; cutoff 250 → keep 300, drop 100+200.
        store
            .append(rec("s1", MemoryRole::User, "old-a", 100))
            .unwrap();
        store
            .append(rec("s1", MemoryRole::User, "old-b", 200))
            .unwrap();
        store
            .append(rec("s1", MemoryRole::User, "fresh", 300))
            .unwrap();
        let removed = store.prune_before("s1", 250).unwrap();
        assert_eq!(removed, 2);
        let w = store.recent("s1").unwrap();
        assert_eq!(w.records.len(), 1);
        assert_eq!(w.records[0].content, "fresh");
    }

    #[test]
    fn prune_before_leaves_rows_at_or_after_cutoff() {
        let store = InMemorySessionMemoryStore::new_default();
        store.append(rec("s1", MemoryRole::User, "a", 100)).unwrap();
        // Cutoff equal to timestamp — strict "<" keeps the boundary row.
        let removed = store.prune_before("s1", 100).unwrap();
        assert_eq!(removed, 0);
        assert_eq!(store.recent("s1").unwrap().records.len(), 1);
    }

    #[test]
    fn prune_before_unknown_session_is_zero_not_error() {
        let store = InMemorySessionMemoryStore::new_default();
        assert_eq!(store.prune_before("never-seen", 9_999).unwrap(), 0);
    }

    #[test]
    fn prune_before_isolates_sessions() {
        let store = InMemorySessionMemoryStore::new_default();
        store.append(rec("s1", MemoryRole::User, "x", 100)).unwrap();
        store.append(rec("s2", MemoryRole::User, "y", 100)).unwrap();
        assert_eq!(store.prune_before("s1", 9_999).unwrap(), 1);
        assert!(store.recent("s1").unwrap().is_empty());
        assert_eq!(store.recent("s2").unwrap().records.len(), 1);
    }

    #[test]
    fn prune_before_frees_total_chars_budget() {
        let cfg = RecentMemoryConfig {
            max_turns: 100,
            max_chars: 10,
        };
        let store = InMemorySessionMemoryStore::new(cfg);
        store
            .append(rec("s1", MemoryRole::User, "aaaa", 100))
            .unwrap(); // 4 chars
        store
            .append(rec("s1", MemoryRole::User, "bbbb", 500))
            .unwrap(); // 8 chars total
        assert_eq!(store.prune_before("s1", 200).unwrap(), 1); // evicts "aaaa"
                                                               // Budget freed — a 4-char append should not evict bbbb.
        store
            .append(rec("s1", MemoryRole::User, "cccc", 600))
            .unwrap();
        let w = store.recent("s1").unwrap();
        assert_eq!(w.records.len(), 2);
        assert_eq!(w.records[0].content, "bbbb");
        assert_eq!(w.records[1].content, "cccc");
    }

    #[test]
    fn list_sessions_enumerates_active_sessions() {
        let store = InMemorySessionMemoryStore::new_default();
        assert!(store.list_sessions().unwrap().is_empty());
        store.append(rec("s1", MemoryRole::User, "a", 1)).unwrap();
        store.append(rec("s2", MemoryRole::User, "b", 1)).unwrap();
        let mut sessions = store.list_sessions().unwrap();
        sessions.sort();
        assert_eq!(sessions, vec!["s1".to_string(), "s2".to_string()]);
    }

    #[test]
    fn render_transcript_is_deterministic_and_skips_empty() {
        let store = InMemorySessionMemoryStore::new_default();
        let empty = store.recent("s1").unwrap();
        assert_eq!(render_transcript(&empty), "");

        store.append(rec("s1", MemoryRole::User, "hi", 1)).unwrap();
        store
            .append(rec("s1", MemoryRole::Assistant, "hello", 2))
            .unwrap();
        let w = store.recent("s1").unwrap();
        let rendered = render_transcript(&w);
        assert_eq!(
            rendered,
            "Recent conversation:\n- User: hi\n- Companion: hello\n"
        );
    }
}
