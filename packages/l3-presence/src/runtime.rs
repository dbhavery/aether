//! Avatar runtime renderer scaffold (pre-generated motion
//! library + runtime blend + lip-sync overlay).
//!
//! This module locks the **input contract** the runtime renderer will
//! consume so renderer work can advance in parallel with the GPU asset
//! pipeline that produces the motion clip libraries.
//! The actual rendering backend, the actual motion library, and the
//! actual lip-sync model do not exist yet. What lives here is:
//!
//! - the [`Renderer`] trait the future backend will implement,
//! - opaque [`MotionClipLibraryHandle`] / [`AudioStreamHandle`] /
//!   [`MotionClipId`] marker types so other layers can pass references
//!   across the boundary without importing this crate's internals,
//! - structured [`RendererEvent`] values produced on every L3 state
//!   transition (state-entered / clip-selected / lip-sync requested),
//! - a [`LogStubRenderer`] no-op implementation that emits structured
//!   `tracing` logs and retains a bounded in-memory event ring for
//!   tests and runtime introspection,
//! - a [`RenderingPresenceController`] adapter that wraps any
//!   [`PresenceController`] and forwards transitions to a renderer.
//!
//! ## What this scaffold deliberately does **not** do
//!
//! - No actual playback. No window, no canvas, no GPU, no audio device.
//! - No actual lip-sync. The lip-sync overlay is requested via an event;
//!   no model is loaded, no frames are produced.
//! - No I/O. Per `CLAUDE.md` §1.5 (single-writer policy) the renderer is
//!   observe-only — it consumes events, emits events, and writes logs.
//!   No file system, no network, no subprocess.
//! - No cross-layer imports. The L1 audio stream and the L6 motion
//!   library are passed as opaque handles that this crate defines; L1
//!   and L6 are responsible for constructing them.
//! - No selection of a real clip. The stub picks a deterministic
//!   placeholder clip id per state (e.g. `clip-listening-default`) so
//!   the event surface is exercisable end-to-end.
//!
//! ## How this composes with existing L3 surfaces
//!
//! `controller.rs` exposes the macro [`PresenceState`] machine
//! ([`InMemoryPresenceController`]). `bridge.rs` maps `PresenceState`
//! onto the frame-rate [`crate::engine::BehaviorClass`] vocabulary an
//! avatar / scheduler consumes. This module is one layer up from
//! `bridge.rs`: it consumes the **transitions** of the macro state
//! machine and turns each transition into an explicit instruction
//! ("enter Speaking, select clip X from library Y, overlay audio
//! handle Z") that a future backend can replay.
//!
//! When a real renderer ships, swap the [`LogStubRenderer`] used in
//! [`RenderingPresenceController::with_log_stub`] for the real
//! implementation. The contract — trait + handle types + event enum —
//! does not move.

use std::collections::VecDeque;
use std::path::PathBuf;
use std::sync::Mutex;

use serde::{Deserialize, Serialize};

use crate::controller::{PresenceController, PresenceSnapshot, PresenceState};
use crate::error::L3Error;

// ---------------------------------------------------------------------------
// Opaque handles — the renderer's typed inputs
// ---------------------------------------------------------------------------

/// Opaque handle to a motion clip library shipped with a persona pack.
///
/// The library itself is the output of the GPU asset pipeline. It does
/// not exist yet; this handle reserves the
/// contract surface so the renderer can be built and exercised before
/// any assets land. The renderer treats `root_path` as a black box —
/// it is the L6 / persona-pack layer's responsibility to construct
/// these handles pointing at on-disk libraries.
///
/// L3 deliberately does **not** import L6 to construct these. Anyone
/// can build one; this crate just defines the shape.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MotionClipLibraryHandle {
    /// Stable identifier for this library (e.g. `"aurora.v1"`).
    pub library_id: String,
    /// Root path of the on-disk library. Renderer treats as opaque.
    pub root_path: PathBuf,
}

impl MotionClipLibraryHandle {
    /// Build a handle. No I/O — the path is not validated here. The
    /// renderer (or a future loader) is responsible for confirming the
    /// library actually exists on disk before play time.
    pub fn new(library_id: impl Into<String>, root_path: impl Into<PathBuf>) -> Self {
        Self {
            library_id: library_id.into(),
            root_path: root_path.into(),
        }
    }
}

/// Opaque handle to a TTS audio stream produced by L1 (Voice).
///
/// L3 does **not** import L1; the actual stream type (samples,
/// channels, codec) lives in the L1 voice crate. This is a typed
/// marker carried across the L3 boundary so the renderer can request a
/// lip-sync overlay against the right stream without L3 having to know
/// what an audio buffer looks like.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AudioStreamHandle {
    /// Stable identifier for this stream within the current turn.
    pub stream_id: String,
}

impl AudioStreamHandle {
    /// Build a handle from any string-like stream identifier.
    pub fn new(stream_id: impl Into<String>) -> Self {
        Self {
            stream_id: stream_id.into(),
        }
    }
}

/// Identifier for a clip selected out of a [`MotionClipLibraryHandle`].
///
/// The renderer is responsible for clip selection; the stub picks a
/// deterministic placeholder per state so the contract surface is
/// observable.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct MotionClipId(pub String);

impl MotionClipId {
    /// Construct from any string-like value.
    pub fn new(id: impl Into<String>) -> Self {
        Self(id.into())
    }

    /// Borrow the underlying string id.
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

// ---------------------------------------------------------------------------
// Renderer event vocabulary
// ---------------------------------------------------------------------------

/// Structured events the renderer emits on every L3 state transition.
///
/// Every variant is parseable: tests assert structure; future
/// observers (Trust drawer renderer-history view, audit overlay,
/// quality-eval replay) can subscribe to the same vocabulary.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum RendererEvent {
    /// L3 state machine entered a new state. Emitted on every
    /// transition (including same-state re-entry, distinguishable by
    /// `prev == state`).
    StateEntered {
        /// State just entered.
        state: PresenceState,
        /// State that was previously active.
        prev: PresenceState,
        /// Wall-clock milliseconds at the transition (caller-supplied).
        t_ms: u64,
    },
    /// Renderer chose a clip to play for the entered state.
    ClipSelected {
        /// State this clip was selected for.
        state: PresenceState,
        /// Clip the renderer picked.
        clip: MotionClipId,
        /// Library this clip came from.
        library: String,
        /// Wall-clock milliseconds at the selection.
        t_ms: u64,
    },
    /// Renderer requested a lip-sync overlay against an audio stream.
    /// Only emitted when the entered state is `Responding` AND an
    /// audio handle was supplied.
    LipSyncOverlayRequested {
        /// Speaking-base clip the overlay will composite against.
        clip: MotionClipId,
        /// Audio stream id the overlay will track.
        audio_stream_id: String,
        /// Wall-clock milliseconds at the request.
        t_ms: u64,
    },
}

// ---------------------------------------------------------------------------
// Renderer trait — the contract a real backend will implement
// ---------------------------------------------------------------------------

/// The runtime avatar renderer.
///
/// A `Renderer` consumes L3 presence-state transitions plus typed
/// handles for the motion library it can play from and (when entering
/// `Responding`) the TTS audio stream it can lip-sync against. The
/// production implementation will pre-load motion clips,
/// blend transitions, and overlay lip-sync. This trait is the surface
/// that swap is made against — `LogStubRenderer` today, a real
/// backend later, with no contract churn.
///
/// Implementations MUST be observe-only — no file I/O, no network, no
/// subprocess execution (`CLAUDE.md` §1.5). Logging, in-memory state,
/// and event emission are fine.
pub trait Renderer: Send + Sync {
    /// React to a presence-state transition.
    ///
    /// `prev` is the state we are leaving; `state` is the state we are
    /// entering. `t_ms` is the wall-clock millisecond at which the
    /// transition happened (caller-supplied — this trait is clock-pure
    /// for the same reasons [`PresenceController`] is).
    ///
    /// `audio` is `Some` only when the caller has a TTS stream ready
    /// for the entered state. The stub uses it only when entering
    /// `Responding`.
    ///
    /// Returns the structured events produced by this transition (in
    /// emission order). Real renderers may return an empty vec and
    /// publish events through a side channel; the stub returns the
    /// vec so tests can assert on it without subscribing to logs.
    fn on_transition(
        &self,
        prev: PresenceState,
        state: PresenceState,
        t_ms: u64,
        audio: Option<&AudioStreamHandle>,
    ) -> Result<Vec<RendererEvent>, L3Error>;

    /// Borrow the motion clip library handle this renderer is bound
    /// to. Lets observers know which library is in use without having
    /// to ask the persona-pack layer.
    fn library(&self) -> &MotionClipLibraryHandle;
}

// ---------------------------------------------------------------------------
// LogStubRenderer — no-op implementation that logs + records events
// ---------------------------------------------------------------------------

/// Maximum events retained in [`LogStubRenderer`]'s internal ring
/// before oldest-first eviction. Mirrors the
/// [`crate::controller::TRANSITION_LOG_CAP`] contract for
/// session-scoped state — short, bounded, debug-grade.
pub const RENDERER_EVENT_LOG_CAP: usize = 64;

/// Default no-op [`Renderer`]. Emits a structured `tracing` event for
/// every produced [`RendererEvent`] and retains the last
/// [`RENDERER_EVENT_LOG_CAP`] events in a bounded ring for tests and
/// runtime introspection.
///
/// No playback. No lip-sync. No I/O. The clip-selection rule is
/// deterministic — `clip-{state-label}-default` — so tests can assert
/// on it and so the renderer's behavior is fully explainable when the
/// real backend swaps in.
pub struct LogStubRenderer {
    library: MotionClipLibraryHandle,
    log: Mutex<VecDeque<RendererEvent>>,
}

impl LogStubRenderer {
    /// Build a stub bound to the given library. The library is not
    /// validated — see [`MotionClipLibraryHandle::new`].
    pub fn new(library: MotionClipLibraryHandle) -> Self {
        Self {
            library,
            log: Mutex::new(VecDeque::new()),
        }
    }

    /// Build a stub bound to a deterministic placeholder library
    /// (`"stub.library"` at `<placeholder>`). Useful for tests and
    /// for early shell wiring before any real persona pack is loaded.
    pub fn placeholder() -> Self {
        Self::new(MotionClipLibraryHandle::new(
            "stub.library",
            PathBuf::from("<placeholder>"),
        ))
    }

    /// Snapshot the bounded event ring (oldest-first). Test- and
    /// debug-grade; not a durable record.
    pub fn recent_events(&self) -> Vec<RendererEvent> {
        let guard = self.log.lock().expect("renderer event log poisoned");
        guard.iter().cloned().collect()
    }

    /// Drop all retained events. Used by tests to isolate scenarios.
    pub fn clear_events(&self) {
        let mut guard = self.log.lock().expect("renderer event log poisoned");
        guard.clear();
    }

    fn push(&self, ev: RendererEvent) {
        let mut guard = self.log.lock().expect("renderer event log poisoned");
        guard.push_back(ev);
        while guard.len() > RENDERER_EVENT_LOG_CAP {
            guard.pop_front();
        }
    }

    fn placeholder_clip_for(state: PresenceState) -> MotionClipId {
        MotionClipId::new(format!("clip-{}-default", state.label()))
    }
}

impl Renderer for LogStubRenderer {
    fn on_transition(
        &self,
        prev: PresenceState,
        state: PresenceState,
        t_ms: u64,
        audio: Option<&AudioStreamHandle>,
    ) -> Result<Vec<RendererEvent>, L3Error> {
        let mut events = Vec::with_capacity(3);

        let entered = RendererEvent::StateEntered { state, prev, t_ms };
        tracing::info!(
            target: "aether::l3::renderer",
            event = "state_entered",
            state = state.label(),
            prev = prev.label(),
            t_ms = t_ms,
            library = %self.library.library_id,
            "renderer state-entered (stub)"
        );
        events.push(entered.clone());
        self.push(entered);

        let clip = Self::placeholder_clip_for(state);
        let selected = RendererEvent::ClipSelected {
            state,
            clip: clip.clone(),
            library: self.library.library_id.clone(),
            t_ms,
        };
        tracing::info!(
            target: "aether::l3::renderer",
            event = "clip_selected",
            state = state.label(),
            clip = clip.as_str(),
            library = %self.library.library_id,
            t_ms = t_ms,
            "renderer clip-selected (stub)"
        );
        events.push(selected.clone());
        self.push(selected);

        if matches!(state, PresenceState::Responding) {
            if let Some(audio) = audio {
                let req = RendererEvent::LipSyncOverlayRequested {
                    clip: clip.clone(),
                    audio_stream_id: audio.stream_id.clone(),
                    t_ms,
                };
                tracing::info!(
                    target: "aether::l3::renderer",
                    event = "lip_sync_overlay_requested",
                    clip = clip.as_str(),
                    audio_stream_id = %audio.stream_id,
                    t_ms = t_ms,
                    "renderer lip-sync-overlay-requested (stub)"
                );
                events.push(req.clone());
                self.push(req);
            }
        }

        Ok(events)
    }

    fn library(&self) -> &MotionClipLibraryHandle {
        &self.library
    }
}

// ---------------------------------------------------------------------------
// RenderingPresenceController — wires the existing state machine to a Renderer
// ---------------------------------------------------------------------------

/// Adapter that wraps any [`PresenceController`] and forwards every
/// `set_state` transition to a [`Renderer`]. Implements
/// [`PresenceController`] itself, so existing call sites keep working
/// — they just gain a renderer in the loop.
///
/// Construction:
///
/// - [`RenderingPresenceController::new`] — bring your own renderer
///   (typed; preserves the concrete type).
/// - [`RenderingPresenceController::boxed`] — bring a boxed renderer
///   when you want trait-object dynamic dispatch (e.g. the shell may
///   swap between `LogStubRenderer` and a real backend at runtime).
/// - [`RenderingPresenceController::with_log_stub`] — convenience
///   constructor returning a wrapper around an
///   [`InMemoryPresenceController`] driven by a [`LogStubRenderer`]
///   bound to a placeholder library. This is the **default** until a
///   real renderer ships.
///
/// Audio handles are attached per-session via
/// [`Self::attach_audio_stream`] / [`Self::detach_audio_stream`]. When
/// `set_state` transitions a session into `Responding`, the attached
/// stream (if any) is forwarded to the renderer for lip-sync. If no
/// stream is attached, the renderer still receives the transition but
/// does not request a lip-sync overlay.
pub struct RenderingPresenceController<C, R>
where
    C: PresenceController,
    R: Renderer,
{
    inner: C,
    renderer: R,
    audio: Mutex<std::collections::HashMap<String, AudioStreamHandle>>,
}

impl<C, R> RenderingPresenceController<C, R>
where
    C: PresenceController,
    R: Renderer,
{
    /// Wrap an existing controller and renderer.
    pub fn new(inner: C, renderer: R) -> Self {
        Self {
            inner,
            renderer,
            audio: Mutex::new(std::collections::HashMap::new()),
        }
    }

    /// Borrow the wrapped renderer (for tests / introspection).
    pub fn renderer(&self) -> &R {
        &self.renderer
    }

    /// Borrow the wrapped controller.
    pub fn inner(&self) -> &C {
        &self.inner
    }

    /// Attach a TTS audio stream to a session. The next transition
    /// into `Responding` for this session will pass the stream to the
    /// renderer.
    pub fn attach_audio_stream(&self, session_id: &str, audio: AudioStreamHandle) {
        let mut guard = self.audio.lock().expect("renderer audio map poisoned");
        guard.insert(session_id.to_string(), audio);
    }

    /// Drop the TTS audio stream for a session. Subsequent transitions
    /// into `Responding` will not request a lip-sync overlay.
    pub fn detach_audio_stream(&self, session_id: &str) {
        let mut guard = self.audio.lock().expect("renderer audio map poisoned");
        guard.remove(session_id);
    }
}

impl RenderingPresenceController<crate::controller::InMemoryPresenceController, LogStubRenderer> {
    /// Default wiring: in-memory controller + log-stub renderer bound
    /// to a placeholder library. The right starting point until a
    /// real renderer ships.
    pub fn with_log_stub() -> Self {
        Self::new(
            crate::controller::InMemoryPresenceController::new(),
            LogStubRenderer::placeholder(),
        )
    }
}

impl<C, R> PresenceController for RenderingPresenceController<C, R>
where
    C: PresenceController,
    R: Renderer,
{
    fn set_state(
        &self,
        session_id: &str,
        state: PresenceState,
        updated_at_ms: u64,
        detail: Option<String>,
    ) -> Result<PresenceSnapshot, L3Error> {
        // Capture the previous state BEFORE mutating. `current` returns
        // a fresh `Quiet` snapshot for unknown sessions, which is the
        // correct semantic for a renderer's "where were we before this
        // transition" question.
        let prev = self.inner.current(session_id)?.state;
        let snap = self
            .inner
            .set_state(session_id, state, updated_at_ms, detail)?;

        let audio = {
            let guard = self.audio.lock().expect("renderer audio map poisoned");
            guard.get(session_id).cloned()
        };
        let _events =
            self.renderer
                .on_transition(prev, snap.state, snap.updated_at_ms, audio.as_ref())?;

        Ok(snap)
    }

    fn current(&self, session_id: &str) -> Result<PresenceSnapshot, L3Error> {
        self.inner.current(session_id)
    }

    fn recent_transitions(&self, session_id: &str) -> Result<Vec<PresenceSnapshot>, L3Error> {
        self.inner.recent_transitions(session_id)
    }

    fn clear_session(&self, session_id: &str) -> Result<(), L3Error> {
        self.inner.clear_session(session_id)
    }
}

// ---------------------------------------------------------------------------
// Boxed-renderer convenience — confirms the trait is dyn-compatible.
// ---------------------------------------------------------------------------

/// A controller wired to a `Box<dyn Renderer>` so the renderer can be
/// swapped at runtime (e.g. log-stub at boot, a real backend once a
/// persona pack with a motion library is loaded). This alias also
/// serves as a compile-time proof that [`Renderer`] is dyn-compatible.
pub type BoxedRendererController<C> = RenderingPresenceController<C, Box<dyn Renderer>>;

impl<R: Renderer + ?Sized> Renderer for Box<R> {
    fn on_transition(
        &self,
        prev: PresenceState,
        state: PresenceState,
        t_ms: u64,
        audio: Option<&AudioStreamHandle>,
    ) -> Result<Vec<RendererEvent>, L3Error> {
        (**self).on_transition(prev, state, t_ms, audio)
    }

    fn library(&self) -> &MotionClipLibraryHandle {
        (**self).library()
    }
}
