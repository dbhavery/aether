//! Presence V1 step 2 — user-attention axis (`Active / Idle / Away`).
//!
//! Sibling concern to the assistant-posture axis owned by
//! [`crate::controller::PresenceController`]. Where the posture axis
//! reflects what Companion *is doing* at turn granularity (Quiet /
//! Listening / Thinking / …), this axis reflects what the *user* is
//! doing at OS-interaction granularity (Active / Idle / Away).
//!
//! Deliberately kept as a brand-new module so the existing posture
//! controller stays untouched. See
//! `docs/PRESENCE-V1-ARCHITECTURE.md` §2 for the three-axis design.
//!
//! ## Design contract
//!
//! - **Observational, not gated.** No L5 capability gate, no L5 audit
//!   rows. The user's two Settings toggles (`enabled`,
//!   `history_in_trust_drawer`) are the consent surface.
//! - **Pure state machine.** `tick()` takes a `(now_ms, idle_seconds)`
//!   pair and returns an optional transition event. No implicit clock,
//!   no OS calls. The shell owns the poll loop and the probe.
//! - **Transition-only emission.** The controller emits an event only
//!   when the state label actually changes; holding steady through a
//!   tick is silent.
//! - **Disabled is a first-class mode.** `set_enabled(false)` makes
//!   `tick()` a no-op and `snapshot()` return a sentinel with
//!   `enabled = false`. Flipping back to enabled resets `since_ms` to
//!   the current tick so the user doesn't get a spurious "you've
//!   been Away for 10 minutes" event on resume.
//! - **Hot-swappable thresholds.** `set_thresholds` takes effect on
//!   the next tick without restart.
//! - **Bounded transition log.** Same [`TRANSITION_LOG_CAP`] bound as
//!   the posture axis; cross-session leakage is not a concern because
//!   the shell drops the controller on app exit.
//!
//! ## Deliberately NOT here
//!
//! - OS idle probe: defined as a trait at the shell boundary
//!   (`apps/desktop/src-tauri/src/idle_probe.rs`). `packages/l3-presence`
//!   forbids `unsafe_code`, so the Windows `GetLastInputInfo` call
//!   lives in the shell. The controller does not know which platform
//!   it runs on.
//! - Event emission to the UI: the shell maps `AttentionEvent` onto
//!   `app.emit(...)` + telemetry. Keeping the controller
//!   infrastructure-free keeps it trivially testable.
//! - Posture composition: `PresenceSnapshot` (design §2) will compose
//!   this axis with the existing posture axis at the shell boundary
//!   in a later slice. The two controllers stay orthogonal.

use std::collections::VecDeque;
use std::sync::Mutex;

use serde::{Deserialize, Serialize};

use crate::controller::TRANSITION_LOG_CAP;
use crate::error::L3Error;

/// User-attention state per design §2. Coarse by design — three
/// buckets is enough to drive pacing and the History surface without
/// pretending to read minds.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum UserAttention {
    /// Recent OS input (keyboard / mouse). Assistant behaves normally.
    Active,
    /// No input for at least `idle_after_s`. Assistant defers
    /// non-critical notifications.
    Idle,
    /// No input for at least `away_after_s`. Assistant does not chat
    /// about nothing and queues anything that can wait.
    Away,
}

impl UserAttention {
    /// Short lowercase label for telemetry / UI.
    pub fn label(self) -> &'static str {
        match self {
            UserAttention::Active => "active",
            UserAttention::Idle => "idle",
            UserAttention::Away => "away",
        }
    }
}

/// Editable threshold pair. Cheap to clone; the controller holds its
/// own copy behind a lock and swaps in-place on `set_thresholds`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct AttentionThresholds {
    /// Seconds of OS idle that flip `Active → Idle`. Must be ≥ 1.
    pub idle_after_s: u32,
    /// Seconds of OS idle that flip `Idle → Away`. Must be
    /// `> idle_after_s` to make physical sense; if the caller supplies
    /// `away_after_s <= idle_after_s` the controller coerces it up to
    /// `idle_after_s + 1` so the state machine remains total (an
    /// `Idle` band of zero width would be nonsensical but not
    /// crash-worthy).
    pub away_after_s: u32,
}

impl AttentionThresholds {
    /// Canonical defaults mirroring `docs/PRESENCE-V1-ARCHITECTURE.md`
    /// §2: 120 s Active → Idle, 600 s Idle → Away.
    pub fn defaults() -> Self {
        Self {
            idle_after_s: 120,
            away_after_s: 600,
        }
    }

    /// Return a copy with nonsensical values coerced into a total,
    /// usable shape. Called every time the controller reads a fresh
    /// config so a bad file on disk can't wedge the state machine.
    fn sanitized(self) -> Self {
        let idle = self.idle_after_s.max(1);
        let away = if self.away_after_s > idle {
            self.away_after_s
        } else {
            idle.saturating_add(1)
        };
        Self {
            idle_after_s: idle,
            away_after_s: away,
        }
    }
}

impl Default for AttentionThresholds {
    fn default() -> Self {
        Self::defaults()
    }
}

/// Snapshot returned by [`UserAttentionController::snapshot`].
///
/// `state` is [`UserAttention::Active`] when `enabled = false`; the
/// `enabled` flag is what callers should branch on to decide whether
/// to render / emit at all.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct AttentionSnapshot {
    /// Current state. Meaningless when `enabled = false` — treat that
    /// case as "the controller is paused".
    pub state: UserAttention,
    /// When the controller entered the current `state` (monotonic ms
    /// as supplied by the shell — same clock the Tauri commands use).
    pub since_ms: u64,
    /// Seconds since the user's last OS interaction at snapshot time.
    /// Zero when `enabled = false` or the probe reported None.
    pub idle_seconds: u64,
    /// Whether the controller is active right now.
    pub enabled: bool,
    /// Whether the platform idle probe reported a value at the most
    /// recent tick. `false` on unsupported platforms (macOS / Linux
    /// stubs today) — the controller stays in `Active` and the UI
    /// should surface this as "idle probe unavailable" rather than
    /// pretending to know.
    pub probe_supported: bool,
}

/// Emitted on each `tick()` that actually changes state. Carried onto
/// the event bus and into the Trust drawer's bounded ring by the
/// shell.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct AttentionEvent {
    /// State before the transition.
    pub from: UserAttention,
    /// State after the transition.
    pub to: UserAttention,
    /// When the transition happened (shell-supplied monotonic ms).
    pub at_ms: u64,
    /// Idle-seconds reading that caused the transition. Useful for
    /// logs, debugging, and future calibration.
    pub idle_seconds: u64,
}

/// User-attention controller. Pure state machine; the shell owns the
/// clock and the probe.
///
/// Internals kept behind a single `Mutex` — contention is negligible
/// (one tick per poll interval, plus occasional hot-swap calls) and
/// the simplicity is worth more than finer-grained locking here.
pub struct UserAttentionController {
    inner: Mutex<AttentionInner>,
}

struct AttentionInner {
    enabled: bool,
    thresholds: AttentionThresholds,
    state: UserAttention,
    since_ms: u64,
    last_idle_seconds: u64,
    probe_supported: bool,
    log: VecDeque<AttentionEvent>,
}

impl UserAttentionController {
    /// Fresh controller in [`UserAttention::Active`] at `t = 0` with
    /// the supplied enabled flag and thresholds. When the shell boots,
    /// the first real `tick` call replaces `since_ms` with the first
    /// observation.
    pub fn new(enabled: bool, thresholds: AttentionThresholds) -> Self {
        Self {
            inner: Mutex::new(AttentionInner {
                enabled,
                thresholds: thresholds.sanitized(),
                state: UserAttention::Active,
                since_ms: 0,
                last_idle_seconds: 0,
                probe_supported: true,
                log: VecDeque::new(),
            }),
        }
    }

    /// Atomic thresholds swap — takes effect on the next `tick`. No
    /// automatic reclassification in between so the caller sees at
    /// most one transition per tick even around a config change.
    pub fn set_thresholds(&self, thresholds: AttentionThresholds) -> Result<(), L3Error> {
        let mut g = self.inner.lock().map_err(lock_err)?;
        g.thresholds = thresholds.sanitized();
        Ok(())
    }

    /// Toggle the active/disabled flag. Re-enabling resets `since_ms`
    /// on the next tick so the user doesn't instantly get an "Away"
    /// event from accumulated idle time across the paused window.
    pub fn set_enabled(&self, enabled: bool) -> Result<(), L3Error> {
        let mut g = self.inner.lock().map_err(lock_err)?;
        if g.enabled != enabled {
            g.enabled = enabled;
            // On re-enable, snap back to Active so the next real tick
            // re-classifies from a clean baseline. On disable, leave
            // the state as-is — snapshot will report `enabled = false`
            // and callers shouldn't care what `state` reads.
            if enabled {
                g.state = UserAttention::Active;
                g.since_ms = 0;
                g.last_idle_seconds = 0;
            }
        }
        Ok(())
    }

    /// Apply one poll-tick worth of signal.
    ///
    /// `now_ms` is the shell's monotonic wall clock. `idle_seconds` is
    /// the probe result: `None` means "probe unsupported on this
    /// platform" — the controller records that fact, holds at
    /// `Active`, and does not emit.
    ///
    /// Returns `Some(event)` iff the state label changed; otherwise
    /// `None`. Safe to call even when `enabled = false` — silently
    /// a no-op in that case.
    pub fn tick(&self, now_ms: u64, idle_seconds: Option<u64>) -> Option<AttentionEvent> {
        let mut g = match self.inner.lock() {
            Ok(g) => g,
            Err(_) => return None,
        };
        if !g.enabled {
            return None;
        }
        let supported = idle_seconds.is_some();
        g.probe_supported = supported;
        let idle = idle_seconds.unwrap_or(0);
        g.last_idle_seconds = idle;
        let want = classify(idle, g.thresholds);
        if want == g.state {
            return None;
        }
        let event = AttentionEvent {
            from: g.state,
            to: want,
            at_ms: now_ms,
            idle_seconds: idle,
        };
        g.state = want;
        g.since_ms = now_ms;
        g.log.push_back(event);
        while g.log.len() > TRANSITION_LOG_CAP {
            g.log.pop_front();
        }
        Some(event)
    }

    /// Read the current snapshot. Cheap; no mutation.
    pub fn snapshot(&self) -> AttentionSnapshot {
        let g = self
            .inner
            .lock()
            .expect("attention lock poisoned on snapshot");
        if !g.enabled {
            return AttentionSnapshot {
                state: UserAttention::Active,
                since_ms: 0,
                idle_seconds: 0,
                enabled: false,
                probe_supported: g.probe_supported,
            };
        }
        AttentionSnapshot {
            state: g.state,
            since_ms: g.since_ms,
            idle_seconds: g.last_idle_seconds,
            enabled: true,
            probe_supported: g.probe_supported,
        }
    }

    /// Bounded transition log (oldest-first). Used by the shell's
    /// Trust drawer History surface and by tests.
    pub fn recent_transitions(&self) -> Vec<AttentionEvent> {
        let g = self
            .inner
            .lock()
            .expect("attention lock poisoned on log read");
        g.log.iter().copied().collect()
    }

    /// Current thresholds. Used by tests and by the `presence_status`
    /// command so the UI can display "thresholds applied: …" without
    /// re-reading `presence.json`.
    pub fn thresholds(&self) -> AttentionThresholds {
        let g = self
            .inner
            .lock()
            .expect("attention lock poisoned on thresholds read");
        g.thresholds
    }
}

fn lock_err(e: impl std::fmt::Display) -> L3Error {
    L3Error::Internal(format!("attention lock poisoned: {e}"))
}

fn classify(idle_seconds: u64, t: AttentionThresholds) -> UserAttention {
    if idle_seconds >= t.away_after_s as u64 {
        UserAttention::Away
    } else if idle_seconds >= t.idle_after_s as u64 {
        UserAttention::Idle
    } else {
        UserAttention::Active
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tight() -> AttentionThresholds {
        // Short thresholds so transitions are readable in tests.
        AttentionThresholds {
            idle_after_s: 10,
            away_after_s: 30,
        }
    }

    #[test]
    fn labels_are_stable() {
        assert_eq!(UserAttention::Active.label(), "active");
        assert_eq!(UserAttention::Idle.label(), "idle");
        assert_eq!(UserAttention::Away.label(), "away");
    }

    #[test]
    fn defaults_match_design_doc() {
        let d = AttentionThresholds::defaults();
        assert_eq!(d.idle_after_s, 120);
        assert_eq!(d.away_after_s, 600);
    }

    #[test]
    fn classify_boundaries_are_inclusive_at_the_threshold() {
        let t = tight();
        assert_eq!(classify(0, t), UserAttention::Active);
        assert_eq!(classify(9, t), UserAttention::Active);
        // The second the threshold is reached, we flip.
        assert_eq!(classify(10, t), UserAttention::Idle);
        assert_eq!(classify(29, t), UserAttention::Idle);
        assert_eq!(classify(30, t), UserAttention::Away);
        assert_eq!(classify(100_000, t), UserAttention::Away);
    }

    #[test]
    fn active_to_idle_to_away_then_back_to_active() {
        let c = UserAttentionController::new(true, tight());
        // Starts Active; first tick under threshold is a no-op.
        assert!(c.tick(1_000, Some(0)).is_none());

        let e1 = c.tick(10_000, Some(10)).expect("Active → Idle");
        assert_eq!(e1.from, UserAttention::Active);
        assert_eq!(e1.to, UserAttention::Idle);
        assert_eq!(e1.idle_seconds, 10);
        assert_eq!(e1.at_ms, 10_000);

        // Staying inside Idle: no event.
        assert!(c.tick(15_000, Some(20)).is_none());

        let e2 = c.tick(30_000, Some(30)).expect("Idle → Away");
        assert_eq!(e2.from, UserAttention::Idle);
        assert_eq!(e2.to, UserAttention::Away);

        // User touches the keyboard → idle seconds resets → back to Active.
        let e3 = c.tick(31_000, Some(0)).expect("Away → Active");
        assert_eq!(e3.from, UserAttention::Away);
        assert_eq!(e3.to, UserAttention::Active);

        assert_eq!(c.recent_transitions().len(), 3);
    }

    #[test]
    fn disabled_controller_is_a_no_op() {
        let c = UserAttentionController::new(false, tight());
        assert!(c.tick(1_000, Some(1_000)).is_none());
        let snap = c.snapshot();
        assert!(!snap.enabled);
        assert_eq!(snap.state, UserAttention::Active);
        assert_eq!(snap.idle_seconds, 0);
        assert!(c.recent_transitions().is_empty());
    }

    #[test]
    fn re_enable_resets_since_ms_and_state() {
        let c = UserAttentionController::new(true, tight());
        c.tick(10_000, Some(40)).unwrap();
        assert_eq!(c.snapshot().state, UserAttention::Away);

        c.set_enabled(false).unwrap();
        // Disabled: snapshot reports paused.
        let paused = c.snapshot();
        assert!(!paused.enabled);

        c.set_enabled(true).unwrap();
        // Just re-enabled: snapshot is Active with zeroed fields,
        // pending the next tick.
        let resumed = c.snapshot();
        assert!(resumed.enabled);
        assert_eq!(resumed.state, UserAttention::Active);
        assert_eq!(resumed.idle_seconds, 0);
    }

    #[test]
    fn set_thresholds_takes_effect_on_next_tick() {
        // Start with a wide config; tick under it to Idle.
        let c = UserAttentionController::new(
            true,
            AttentionThresholds {
                idle_after_s: 10,
                away_after_s: 100,
            },
        );
        c.tick(10_000, Some(15)).unwrap();
        assert_eq!(c.snapshot().state, UserAttention::Idle);

        // Tighten thresholds — the same idle reading should flip us to Away
        // on the next tick.
        c.set_thresholds(AttentionThresholds {
            idle_after_s: 5,
            away_after_s: 10,
        })
        .unwrap();
        let ev = c.tick(11_000, Some(15)).expect("tightened → Away");
        assert_eq!(ev.to, UserAttention::Away);
    }

    #[test]
    fn unsupported_probe_stays_active_and_flags_snapshot() {
        // The probe reporting None is the macOS / Linux stub today.
        let c = UserAttentionController::new(true, tight());
        assert!(c.tick(1_000, None).is_none());
        let snap = c.snapshot();
        assert_eq!(snap.state, UserAttention::Active);
        assert_eq!(snap.idle_seconds, 0);
        assert!(snap.enabled);
        assert!(!snap.probe_supported);
    }

    #[test]
    fn nonsensical_thresholds_are_sanitized() {
        // idle_after_s = 0 is nonsense; coerce to 1. away_after_s <= idle
        // is nonsense; coerce to idle + 1.
        let c = UserAttentionController::new(
            true,
            AttentionThresholds {
                idle_after_s: 0,
                away_after_s: 0,
            },
        );
        let t = c.thresholds();
        assert!(t.idle_after_s >= 1);
        assert!(t.away_after_s > t.idle_after_s);
    }

    #[test]
    fn transition_log_is_bounded() {
        let c = UserAttentionController::new(true, tight());
        // Oscillate across thresholds to pile up transitions.
        for i in 0..(TRANSITION_LOG_CAP as u64 + 10) {
            let idle = if i % 2 == 0 { 40 } else { 0 };
            c.tick(i * 1000, Some(idle));
        }
        assert_eq!(c.recent_transitions().len(), TRANSITION_LOG_CAP);
    }

    #[test]
    fn snapshot_reflects_since_ms_of_last_transition() {
        let c = UserAttentionController::new(true, tight());
        let _ = c.tick(5_000, Some(0));
        c.tick(20_000, Some(15)).expect("→ Idle");
        let s = c.snapshot();
        assert_eq!(s.state, UserAttention::Idle);
        assert_eq!(s.since_ms, 20_000);
        assert_eq!(s.idle_seconds, 15);
    }

    #[test]
    fn no_event_emitted_when_probe_bounces_within_same_bucket() {
        let c = UserAttentionController::new(true, tight());
        // Step into Idle.
        c.tick(10_000, Some(15)).unwrap();
        // Several ticks that stay within Idle band: silent.
        assert!(c.tick(11_000, Some(16)).is_none());
        assert!(c.tick(12_000, Some(25)).is_none());
        assert!(c.tick(13_000, Some(29)).is_none());
    }
}
