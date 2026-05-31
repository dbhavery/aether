//! Wave L3.1 — session-scoped presence controller.
//!
//! A narrow first slice of L3: a small, deterministic state machine that
//! reflects what Companion is *being* at turn granularity. Separate concern
//! from the frame-rate [`BehaviorClass`](crate::BehaviorClass) scheduler in
//! `engine.rs`, which drives avatar animation. This module exposes the
//! macro status a CLI or shell can bind to without knowing anything about
//! visemes, gaze, or render tiers.
//!
//! ## Scope
//!
//! - five macro states (Quiet / Listening / Thinking / AwaitingApproval /
//!   Responding),
//! - per-session isolation,
//! - a bounded transition log per session for debugging / tests,
//! - deterministic set/get API, no timers, no events.
//!
//! ## Out of scope
//!
//! - idle timers,
//! - typing/speaking granularity,
//! - avatar frames (already in [`crate::engine`]),
//! - notification posture,
//! - multi-tenant / user-switching semantics.
//!
//! ## Integration
//!
//! Intended composition point: the integration layer (the L1 CLI demo)
//! constructs an `InMemoryPresenceController`, calls `set_state` at key
//! turn milestones (listening → thinking → awaiting_approval → responding
//! → quiet), and renders transitions through [`render_presence`]. L1 / L5 /
//! L7 stay unaware.

use std::collections::{HashMap, VecDeque};
use std::sync::Mutex;

use serde::{Deserialize, Serialize};

use crate::error::L3Error;

/// Macro presence state reflecting what Companion is doing at turn granularity.
///
/// Transitions are driven by the integration layer; the controller does not
/// police them. Any state can follow any other — callers are free to jump
/// from `AwaitingApproval` straight back to `Quiet` on rejection, or from
/// `Quiet` straight to `Responding` for an unsolicited output later.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PresenceState {
    /// At rest. Between turns.
    Quiet,
    /// Receiving / parsing user input.
    Listening,
    /// Evaluating policy, routing, generating.
    Thinking,
    /// A `Decision::Ask` is open; waiting on a user approval resolution.
    AwaitingApproval,
    /// Emitting the assistant response.
    Responding,
}

impl PresenceState {
    /// Short lowercase label used by [`render_presence`] and log lines.
    pub fn label(self) -> &'static str {
        match self {
            PresenceState::Quiet => "quiet",
            PresenceState::Listening => "listening",
            PresenceState::Thinking => "thinking",
            PresenceState::AwaitingApproval => "awaiting-approval",
            PresenceState::Responding => "responding",
        }
    }
}

/// Snapshot of a session's presence. `updated_at_ms` is caller-supplied so
/// the controller stays pure (no implicit clock).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PresenceSnapshot {
    /// Session id this snapshot is for.
    pub session_id: String,
    /// Current state.
    pub state: PresenceState,
    /// Wall-clock milliseconds supplied at the most recent `set_state` call.
    pub updated_at_ms: u64,
    /// Optional short note (e.g. the ticket id that caused AwaitingApproval).
    pub detail: Option<String>,
}

/// Session-scoped presence surface.
///
/// Semantics:
/// - `set_state` replaces the current state and records the transition in a
///   bounded per-session log.
/// - `current` returns the last snapshot or a fresh `Quiet` snapshot for
///   unknown sessions (not an error).
/// - `recent_transitions` returns the bounded history (oldest-first) for
///   tests and debug output.
/// - `clear_session` drops all state for one session.
pub trait PresenceController: Send + Sync {
    /// Update the current state for `session_id`. `detail` is optional
    /// human-readable context.
    fn set_state(
        &self,
        session_id: &str,
        state: PresenceState,
        updated_at_ms: u64,
        detail: Option<String>,
    ) -> Result<PresenceSnapshot, L3Error>;

    /// Read the current snapshot for `session_id`.
    fn current(&self, session_id: &str) -> Result<PresenceSnapshot, L3Error>;

    /// Read the bounded transition log for `session_id` (oldest-first).
    fn recent_transitions(&self, session_id: &str) -> Result<Vec<PresenceSnapshot>, L3Error>;

    /// Drop all state for `session_id`. No-op for unknown sessions.
    fn clear_session(&self, session_id: &str) -> Result<(), L3Error>;
}

/// In-process implementation suitable for the CLI/demo, integration tests,
/// and any future single-process shell. Transition log is bounded to the
/// most recent `TRANSITION_LOG_CAP` snapshots per session.
pub struct InMemoryPresenceController {
    inner: Mutex<HashMap<String, SessionState>>,
}

struct SessionState {
    current: PresenceSnapshot,
    log: VecDeque<PresenceSnapshot>,
}

/// Maximum transitions retained per session before oldest-first eviction.
pub const TRANSITION_LOG_CAP: usize = 32;

impl InMemoryPresenceController {
    /// Build an empty controller. Sessions start at `Quiet` lazily on first
    /// query.
    pub fn new() -> Self {
        Self {
            inner: Mutex::new(HashMap::new()),
        }
    }

    fn quiet_snapshot(session_id: &str) -> PresenceSnapshot {
        PresenceSnapshot {
            session_id: session_id.to_string(),
            state: PresenceState::Quiet,
            updated_at_ms: 0,
            detail: None,
        }
    }
}

impl Default for InMemoryPresenceController {
    fn default() -> Self {
        Self::new()
    }
}

impl PresenceController for InMemoryPresenceController {
    fn set_state(
        &self,
        session_id: &str,
        state: PresenceState,
        updated_at_ms: u64,
        detail: Option<String>,
    ) -> Result<PresenceSnapshot, L3Error> {
        let snap = PresenceSnapshot {
            session_id: session_id.to_string(),
            state,
            updated_at_ms,
            detail,
        };
        let mut guard = self
            .inner
            .lock()
            .map_err(|e| L3Error::Internal(format!("presence lock poisoned: {e}")))?;
        let entry = guard
            .entry(session_id.to_string())
            .or_insert_with(|| SessionState {
                current: Self::quiet_snapshot(session_id),
                log: VecDeque::new(),
            });
        entry.current = snap.clone();
        entry.log.push_back(snap.clone());
        while entry.log.len() > TRANSITION_LOG_CAP {
            entry.log.pop_front();
        }
        Ok(snap)
    }

    fn current(&self, session_id: &str) -> Result<PresenceSnapshot, L3Error> {
        let guard = self
            .inner
            .lock()
            .map_err(|e| L3Error::Internal(format!("presence lock poisoned: {e}")))?;
        Ok(guard
            .get(session_id)
            .map(|s| s.current.clone())
            .unwrap_or_else(|| Self::quiet_snapshot(session_id)))
    }

    fn recent_transitions(&self, session_id: &str) -> Result<Vec<PresenceSnapshot>, L3Error> {
        let guard = self
            .inner
            .lock()
            .map_err(|e| L3Error::Internal(format!("presence lock poisoned: {e}")))?;
        Ok(guard
            .get(session_id)
            .map(|s| s.log.iter().cloned().collect())
            .unwrap_or_default())
    }

    fn clear_session(&self, session_id: &str) -> Result<(), L3Error> {
        let mut guard = self
            .inner
            .lock()
            .map_err(|e| L3Error::Internal(format!("presence lock poisoned: {e}")))?;
        guard.remove(session_id);
        Ok(())
    }
}

/// Deterministic single-line rendering for a snapshot. Format:
/// `"[presence] <label>"` or `"[presence] <label> — <detail>"`.
pub fn render_presence(snapshot: &PresenceSnapshot) -> String {
    match &snapshot.detail {
        Some(d) if !d.is_empty() => format!("[presence] {} — {d}", snapshot.state.label()),
        _ => format!("[presence] {}", snapshot.state.label()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unknown_session_reads_as_quiet() {
        let c = InMemoryPresenceController::new();
        let s = c.current("nope").unwrap();
        assert_eq!(s.state, PresenceState::Quiet);
        assert_eq!(s.session_id, "nope");
        assert_eq!(s.updated_at_ms, 0);
        assert!(c.recent_transitions("nope").unwrap().is_empty());
    }

    #[test]
    fn set_state_updates_current_and_logs() {
        let c = InMemoryPresenceController::new();
        c.set_state("s1", PresenceState::Listening, 10, None)
            .unwrap();
        c.set_state("s1", PresenceState::Thinking, 20, None)
            .unwrap();
        c.set_state("s1", PresenceState::Responding, 30, Some("route ok".into()))
            .unwrap();

        let cur = c.current("s1").unwrap();
        assert_eq!(cur.state, PresenceState::Responding);
        assert_eq!(cur.updated_at_ms, 30);
        assert_eq!(cur.detail.as_deref(), Some("route ok"));

        let log = c.recent_transitions("s1").unwrap();
        assert_eq!(log.len(), 3);
        assert_eq!(log[0].state, PresenceState::Listening);
        assert_eq!(log[1].state, PresenceState::Thinking);
        assert_eq!(log[2].state, PresenceState::Responding);
    }

    #[test]
    fn transition_log_is_bounded() {
        let c = InMemoryPresenceController::new();
        for i in 0..(TRANSITION_LOG_CAP + 5) {
            c.set_state("s1", PresenceState::Thinking, i as u64, None)
                .unwrap();
        }
        assert_eq!(
            c.recent_transitions("s1").unwrap().len(),
            TRANSITION_LOG_CAP
        );
    }

    #[test]
    fn sessions_are_isolated() {
        let c = InMemoryPresenceController::new();
        c.set_state("a", PresenceState::Listening, 1, None).unwrap();
        c.set_state("b", PresenceState::Thinking, 1, None).unwrap();
        assert_eq!(c.current("a").unwrap().state, PresenceState::Listening);
        assert_eq!(c.current("b").unwrap().state, PresenceState::Thinking);
    }

    #[test]
    fn clear_session_removes_only_one() {
        let c = InMemoryPresenceController::new();
        c.set_state("a", PresenceState::Listening, 1, None).unwrap();
        c.set_state("b", PresenceState::Thinking, 1, None).unwrap();
        c.clear_session("a").unwrap();
        assert_eq!(c.current("a").unwrap().state, PresenceState::Quiet);
        assert_eq!(c.current("b").unwrap().state, PresenceState::Thinking);
    }

    #[test]
    fn render_presence_plain_and_with_detail() {
        let s = PresenceSnapshot {
            session_id: "s".into(),
            state: PresenceState::Thinking,
            updated_at_ms: 0,
            detail: None,
        };
        assert_eq!(render_presence(&s), "[presence] thinking");
        let s = PresenceSnapshot {
            session_id: "s".into(),
            state: PresenceState::AwaitingApproval,
            updated_at_ms: 0,
            detail: Some("ticket-1".into()),
        };
        assert_eq!(
            render_presence(&s),
            "[presence] awaiting-approval — ticket-1"
        );
    }

    #[test]
    fn labels_are_stable() {
        assert_eq!(PresenceState::Quiet.label(), "quiet");
        assert_eq!(PresenceState::Listening.label(), "listening");
        assert_eq!(PresenceState::Thinking.label(), "thinking");
        assert_eq!(PresenceState::AwaitingApproval.label(), "awaiting-approval");
        assert_eq!(PresenceState::Responding.label(), "responding");
    }
}
