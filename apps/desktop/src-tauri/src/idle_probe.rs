//! OS idle-time probe. Presence V1 step 2.
//!
//! The controller in `packages/l3-presence/src/attention.rs` is a
//! pure state machine — it does not know which platform it's on and
//! never calls into the OS. This module is the other half: a small
//! trait plus a Windows-first implementation plus explicit stubs for
//! macOS / Linux so the shell can ask "how many seconds since the
//! user last touched the keyboard or mouse?" without the controller
//! ever acquiring unsafe / platform code.
//!
//! ## Design choices
//!
//! - **No new dependency.** Windows impl uses the `GetLastInputInfo`
//!   + `GetTickCount` pair via raw FFI (`extern "system"`). The
//!   alternative — pulling the `user-idle` crate for ~50 lines of
//!   pure-Rust wrapping — was rejected: the single call site and
//!   platform-specific nature make an inline impl cleaner than a
//!   dependency. The handoff explicitly allows raw FFI or one new
//!   crate; raw FFI is the smaller blast radius.
//! - **macOS / Linux stubs are honest.** They return `None` rather
//!   than `Some(0)`. The controller treats `None` as "probe
//!   unsupported" and holds at `Active` with `probe_supported =
//!   false` in the snapshot. The Settings UI then surfaces that state
//!   truthfully instead of pretending the user is always attentive.
//!   macOS / Linux real probes are a future slice.
//! - **No background thread.** The probe is synchronous and cheap
//!   (one syscall pair on Windows, a no-op elsewhere). The shell's
//!   poll loop calls it directly.
//!
//! ## Platform notes
//!
//! Windows: `GetLastInputInfo` returns ticks (ms since boot) of the
//! last input event; `GetTickCount` returns ticks now. The wrap-around
//! (every ~49.7 days) is handled by `u32::wrapping_sub` — the real
//! idle time is always the short direction around the wheel.
//!
//! Linux: `XScreenSaverQueryInfo` is the honest probe but needs X11;
//! Wayland has no equivalent without compositor cooperation. Deferred.
//! macOS: `CGEventSourceSecondsSinceLastEventType` is the honest
//! probe. Deferred.

/// Minimal platform trait the shell polls from its tick loop. The
/// test mock lives in the same module and is used by the state-
/// machine tests in `packages/l3-presence` through composition — the
/// controller itself never depends on this trait.
pub trait IdleProbe: Send + Sync {
    /// Seconds since the user last interacted with the OS. `None`
    /// means "this platform doesn't support the probe"; the caller
    /// should treat that as "attention unobserved" rather than
    /// "never idle". Called every presence poll tick.
    fn idle_seconds(&self) -> Option<u64>;

    /// Short label used in logs to identify which probe variant is
    /// wired — handy when debugging whether mac/Linux fell through
    /// to the stub.
    fn label(&self) -> &'static str;
}

/// Platform-appropriate probe selected at compile time. Windows gets
/// the real `GetLastInputInfo` probe; other platforms fall through to
/// the stub. The shell's boot code constructs one of these and hands
/// it to the poll task.
pub fn platform_probe() -> Box<dyn IdleProbe> {
    #[cfg(windows)]
    {
        Box::new(WindowsIdleProbe::new())
    }
    #[cfg(not(windows))]
    {
        Box::new(UnsupportedIdleProbe)
    }
}

// ---------------------------------------------------------------------
// Windows — GetLastInputInfo
// ---------------------------------------------------------------------

#[cfg(windows)]
pub use windows_probe::WindowsIdleProbe;

#[cfg(windows)]
mod windows_probe {
    //! Raw FFI into the two Win32 calls we need.
    //!
    //! `GetLastInputInfo` populates a `LASTINPUTINFO` struct with
    //! `dwTime` = tick count (ms since system boot) of the most
    //! recent keyboard / mouse / stylus event. `GetTickCount` returns
    //! the current tick count on the same clock. Difference in ms,
    //! rounded to seconds. Both calls are documented as lightweight
    //! and safe to invoke from any thread.

    use std::mem::size_of;

    use super::IdleProbe;

    #[repr(C)]
    struct LASTINPUTINFO {
        cb_size: u32,
        dw_time: u32,
    }

    #[link(name = "user32")]
    extern "system" {
        fn GetLastInputInfo(plii: *mut LASTINPUTINFO) -> i32;
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn GetTickCount() -> u32;
    }

    /// Windows-native probe backed by `GetLastInputInfo`. Zero-sized
    /// handle — the probe carries no state across calls; each call
    /// reads the OS clocks directly.
    pub struct WindowsIdleProbe;

    impl WindowsIdleProbe {
        /// Construct a fresh probe. Infallible; the syscalls are
        /// made per `idle_seconds` call, not at construction.
        pub fn new() -> Self {
            Self
        }
    }

    impl Default for WindowsIdleProbe {
        fn default() -> Self {
            Self::new()
        }
    }

    impl IdleProbe for WindowsIdleProbe {
        fn idle_seconds(&self) -> Option<u64> {
            let mut lii = LASTINPUTINFO {
                cb_size: size_of::<LASTINPUTINFO>() as u32,
                dw_time: 0,
            };
            // SAFETY: Both calls are FFI into documented Win32
            // functions available on every supported Windows version
            // (≥ XP for GetLastInputInfo, ≥ 2000 for GetTickCount).
            // `GetLastInputInfo` writes only into the struct we own;
            // `GetTickCount` has no pointer arguments. Failure is
            // signalled by a zero return from `GetLastInputInfo`, in
            // which case we surface `None` rather than guess.
            let (rc, now) = unsafe {
                let rc = GetLastInputInfo(&mut lii as *mut LASTINPUTINFO);
                let now = GetTickCount();
                (rc, now)
            };
            if rc == 0 {
                return None;
            }
            // `wrapping_sub` handles the 49.7-day tick wrap: when
            // `now` has wrapped past zero but `dw_time` has not, the
            // subtraction underflows into a small positive delta,
            // which is still the real idle time.
            let idle_ms = now.wrapping_sub(lii.dw_time);
            Some((idle_ms / 1000) as u64)
        }

        fn label(&self) -> &'static str {
            "windows:GetLastInputInfo"
        }
    }
}

// ---------------------------------------------------------------------
// macOS / Linux — honest "unsupported" stub
// ---------------------------------------------------------------------

/// Stub probe for platforms where a real implementation has not
/// shipped yet. Always returns `None`; the controller interprets that
/// as "probe unavailable, stay in Active, flag it in the snapshot".
#[allow(dead_code)] // Compiled on non-Windows; dead under #[cfg(windows)].
pub struct UnsupportedIdleProbe;

impl IdleProbe for UnsupportedIdleProbe {
    fn idle_seconds(&self) -> Option<u64> {
        None
    }

    fn label(&self) -> &'static str {
        "unsupported"
    }
}

// ---------------------------------------------------------------------
// Mock — used by shell tests that exercise the presence task without
// hitting the OS.
// ---------------------------------------------------------------------

/// Mock probe for unit / integration tests. Holds a canned reading
/// behind a `Mutex` so a test can drive the shell's poll task through
/// a scripted timeline.
#[cfg(test)]
pub mod mock {
    use std::sync::Mutex;

    use super::IdleProbe;

    /// Mock probe whose reading the test controls via `set`.
    pub struct MockIdleProbe {
        value: Mutex<Option<u64>>,
    }

    impl MockIdleProbe {
        /// Fresh probe initialised to `initial`. `None` mirrors the
        /// real unsupported-platform behaviour.
        pub fn new(initial: Option<u64>) -> Self {
            Self {
                value: Mutex::new(initial),
            }
        }

        /// Replace the canned reading. The next `idle_seconds` call
        /// returns this value.
        pub fn set(&self, v: Option<u64>) {
            *self.value.lock().expect("mock idle probe lock") = v;
        }
    }

    impl IdleProbe for MockIdleProbe {
        fn idle_seconds(&self) -> Option<u64> {
            *self.value.lock().expect("mock idle probe lock")
        }

        fn label(&self) -> &'static str {
            "mock"
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unsupported_probe_reports_none() {
        let p: Box<dyn IdleProbe> = Box::new(UnsupportedIdleProbe);
        assert!(p.idle_seconds().is_none());
        assert_eq!(p.label(), "unsupported");
    }

    #[test]
    fn mock_probe_roundtrips_canned_readings() {
        let m = mock::MockIdleProbe::new(Some(5));
        assert_eq!(m.idle_seconds(), Some(5));
        m.set(None);
        assert!(m.idle_seconds().is_none());
        m.set(Some(12345));
        assert_eq!(m.idle_seconds(), Some(12345));
        assert_eq!(m.label(), "mock");
    }

    #[cfg(windows)]
    #[test]
    fn windows_probe_returns_a_value() {
        // Can't assert an exact reading (depends on session activity),
        // but the call must not panic and must return Some on a real
        // Windows session.
        let p = WindowsIdleProbe::new();
        let v = p.idle_seconds();
        assert!(v.is_some(), "GetLastInputInfo returned None on Windows?");
        assert_eq!(p.label(), "windows:GetLastInputInfo");
    }

    #[test]
    fn platform_probe_factory_returns_something_sane() {
        // On Windows this is WindowsIdleProbe; elsewhere it's
        // UnsupportedIdleProbe. Both respond to the trait.
        let p = platform_probe();
        let _ = p.idle_seconds();
        let _ = p.label();
    }
}
