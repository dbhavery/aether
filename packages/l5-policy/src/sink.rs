//! L5 event sink abstraction.
//!
//! Wave 3 uses a synchronous sink trait rather than a tokio broadcast channel.
//! L5's `evaluate` is sync and the audit write must commit before `Allow`
//! returns (L5 interface pack §5) — a sync sink keeps that invariant trivial
//! to uphold and side-steps the tokio dependency until a real async consumer
//! (Tauri bridge, L7 trust center stream) exists.
//!
//! Wave 4 or later will add a `BroadcastSink` that fans out to a
//! `tokio::sync::broadcast::Sender<L5Event>` and any consumer that needs it.

use std::sync::Mutex;

use crate::events::L5Event;

/// Synchronous event sink. Implementations must be cheap — `DefaultPolicyEngine`
/// publishes many events per `evaluate` call.
pub trait L5EventSink: Send + Sync {
    /// Deliver a single event. Must not panic.
    fn emit(&self, event: L5Event);
}

/// Collect-everything sink for tests.
#[derive(Debug, Default)]
pub struct InMemorySink {
    events: Mutex<Vec<L5Event>>,
}

impl InMemorySink {
    /// Empty sink.
    pub fn new() -> Self {
        Self::default()
    }

    /// Take everything seen so far and reset.
    pub fn drain(&self) -> Vec<L5Event> {
        let mut g = self.events.lock().unwrap();
        std::mem::take(&mut *g)
    }

    /// Copy of what's been seen so far.
    pub fn snapshot(&self) -> Vec<L5Event> {
        self.events.lock().unwrap().clone()
    }

    /// Count events matching a predicate.
    pub fn count_where<F: Fn(&L5Event) -> bool>(&self, f: F) -> usize {
        self.events.lock().unwrap().iter().filter(|e| f(e)).count()
    }
}

impl L5EventSink for InMemorySink {
    fn emit(&self, event: L5Event) {
        self.events.lock().unwrap().push(event);
    }
}

/// Drops every event. Cheap default for engines that don't observe events.
#[derive(Debug, Default, Clone, Copy)]
pub struct NullSink;

impl L5EventSink for NullSink {
    fn emit(&self, _event: L5Event) {}
}
