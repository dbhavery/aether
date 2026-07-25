//! Unit tests for the L3 runtime renderer scaffold.
//!
//! Coverage matrix:
//!
//! 1. Every L3 state transition produces at least the
//!    `state_entered` + `clip_selected` events on the renderer.
//! 2. Same-state re-entry still emits a transition (renderer is the
//!    fan-out point — the controller decides whether to call us).
//! 3. Lip-sync overlay event is emitted only when entering
//!    `Responding` AND an audio handle is attached for that session.
//! 4. The `LogStubRenderer` event ring is bounded to
//!    `RENDERER_EVENT_LOG_CAP`.
//! 5. The structured event vocabulary round-trips through serde —
//!    parseable by any future observer.
//! 6. `Renderer` is dyn-compatible — `&dyn Renderer` and
//!    `Box<dyn Renderer>` both work end-to-end.
//! 7. Audio handle attach/detach behavior per session.
//! 8. Multi-session isolation through the wired controller.

use std::path::PathBuf;

use aether_l3_presence::{
    AudioStreamHandle, BoxedRendererController, InMemoryPresenceController, LogStubRenderer,
    MotionClipId, MotionClipLibraryHandle, PresenceController, PresenceState, Renderer,
    RendererEvent, RenderingPresenceController, RENDERER_EVENT_LOG_CAP,
};

const ALL_STATES: &[PresenceState] = &[
    PresenceState::Quiet,
    PresenceState::Listening,
    PresenceState::Thinking,
    PresenceState::AwaitingApproval,
    PresenceState::Responding,
];

fn fresh_controller() -> RenderingPresenceController<InMemoryPresenceController, LogStubRenderer> {
    RenderingPresenceController::with_log_stub()
}

#[test]
fn every_state_transition_emits_state_entered_and_clip_selected() {
    let ctrl = fresh_controller();

    // Drive the controller through every state. Each set_state should
    // emit at least StateEntered + ClipSelected on the renderer.
    let mut t = 0u64;
    for state in ALL_STATES {
        t += 10;
        ctrl.set_state("s1", *state, t, None).unwrap();
    }

    let events = ctrl.renderer().recent_events();
    let entered: Vec<_> = events
        .iter()
        .filter(|e| matches!(e, RendererEvent::StateEntered { .. }))
        .collect();
    let selected: Vec<_> = events
        .iter()
        .filter(|e| matches!(e, RendererEvent::ClipSelected { .. }))
        .collect();

    assert_eq!(entered.len(), ALL_STATES.len());
    assert_eq!(selected.len(), ALL_STATES.len());
}

#[test]
fn each_state_gets_its_own_placeholder_clip_id() {
    let ctrl = fresh_controller();

    let mut t = 0u64;
    for state in ALL_STATES {
        t += 10;
        ctrl.set_state("s1", *state, t, None).unwrap();
    }

    let events = ctrl.renderer().recent_events();
    let mut clips_by_state = std::collections::HashMap::new();
    for ev in &events {
        if let RendererEvent::ClipSelected { state, clip, .. } = ev {
            clips_by_state.insert(*state, clip.clone());
        }
    }

    for state in ALL_STATES {
        let clip = clips_by_state
            .get(state)
            .expect("every state should have selected a clip");
        let expected = format!("clip-{}-default", state.label());
        assert_eq!(clip.as_str(), expected, "stub clip id rule changed");
    }
}

#[test]
fn same_state_reentry_still_emits_transition() {
    // The renderer is downstream of the controller — if the caller
    // chooses to re-set the same state, the renderer must still see
    // it. (The controller does not coalesce; that's by design.)
    let ctrl = fresh_controller();
    ctrl.set_state("s1", PresenceState::Listening, 1, None)
        .unwrap();
    ctrl.set_state("s1", PresenceState::Listening, 2, None)
        .unwrap();

    let entered: Vec<_> = ctrl
        .renderer()
        .recent_events()
        .into_iter()
        .filter(|e| matches!(e, RendererEvent::StateEntered { .. }))
        .collect();
    assert_eq!(entered.len(), 2);
}

#[test]
fn first_transition_records_quiet_as_prev_for_unknown_session() {
    // Before any set_state, the controller reports Quiet for unknown
    // sessions. The first transition's renderer event must reflect
    // that.
    let ctrl = fresh_controller();
    ctrl.set_state("brand-new", PresenceState::Listening, 5, None)
        .unwrap();

    let evs = ctrl.renderer().recent_events();
    let first = evs
        .iter()
        .find_map(|e| match e {
            RendererEvent::StateEntered { state, prev, t_ms } => Some((*state, *prev, *t_ms)),
            _ => None,
        })
        .expect("expected a StateEntered event");
    assert_eq!(first.0, PresenceState::Listening);
    assert_eq!(first.1, PresenceState::Quiet);
    assert_eq!(first.2, 5);
}

#[test]
fn lip_sync_overlay_only_on_responding_with_audio_attached() {
    let ctrl = fresh_controller();

    // Without audio attached, transitioning into Responding must NOT
    // request lip-sync.
    ctrl.set_state("s1", PresenceState::Responding, 1, None)
        .unwrap();
    let pre = ctrl.renderer().recent_events();
    assert!(
        !pre.iter()
            .any(|e| matches!(e, RendererEvent::LipSyncOverlayRequested { .. })),
        "lip-sync should not fire without an attached audio stream"
    );

    // Attach audio and re-enter Responding — now lip-sync must fire.
    ctrl.attach_audio_stream("s1", AudioStreamHandle::new("turn-42"));
    ctrl.set_state("s1", PresenceState::Responding, 2, None)
        .unwrap();
    let post = ctrl.renderer().recent_events();
    let lip: Vec<_> = post
        .iter()
        .filter_map(|e| match e {
            RendererEvent::LipSyncOverlayRequested {
                clip,
                audio_stream_id,
                t_ms,
            } => Some((clip.clone(), audio_stream_id.clone(), *t_ms)),
            _ => None,
        })
        .collect();
    assert_eq!(lip.len(), 1, "exactly one lip-sync request expected");
    let (clip, stream_id, t_ms) = &lip[0];
    assert_eq!(stream_id, "turn-42");
    assert_eq!(*t_ms, 2);
    assert_eq!(clip, &MotionClipId::new("clip-responding-default"));
}

#[test]
fn lip_sync_does_not_fire_on_non_responding_states_even_with_audio() {
    let ctrl = fresh_controller();
    ctrl.attach_audio_stream("s1", AudioStreamHandle::new("turn-7"));
    for state in ALL_STATES
        .iter()
        .filter(|s| **s != PresenceState::Responding)
    {
        ctrl.set_state("s1", *state, 1, None).unwrap();
    }
    let evs = ctrl.renderer().recent_events();
    assert!(
        !evs.iter()
            .any(|e| matches!(e, RendererEvent::LipSyncOverlayRequested { .. })),
        "lip-sync must only fire on Responding"
    );
}

#[test]
fn detach_audio_stops_lip_sync_requests() {
    let ctrl = fresh_controller();
    ctrl.attach_audio_stream("s1", AudioStreamHandle::new("a"));
    ctrl.set_state("s1", PresenceState::Responding, 1, None)
        .unwrap();
    ctrl.detach_audio_stream("s1");
    ctrl.set_state("s1", PresenceState::Responding, 2, None)
        .unwrap();

    let lip = ctrl
        .renderer()
        .recent_events()
        .into_iter()
        .filter(|e| matches!(e, RendererEvent::LipSyncOverlayRequested { .. }))
        .count();
    assert_eq!(lip, 1, "second Responding (after detach) must not lip-sync");
}

#[test]
fn renderer_event_log_is_bounded() {
    let ctrl = fresh_controller();
    // Fire enough transitions to overflow the ring. Each transition
    // produces 2 events (state_entered + clip_selected) under no-audio.
    let n = RENDERER_EVENT_LOG_CAP + 20;
    for i in 0..n {
        ctrl.set_state("s1", PresenceState::Listening, i as u64, None)
            .unwrap();
    }
    let evs = ctrl.renderer().recent_events();
    assert_eq!(evs.len(), RENDERER_EVENT_LOG_CAP);
}

#[test]
fn structured_log_output_round_trips_through_serde() {
    // The event vocabulary is the renderer's "log output" — any
    // future observer (Trust drawer, audit overlay, replay tooling)
    // must be able to parse it. Round-trip through JSON to confirm.
    let ctrl = fresh_controller();
    ctrl.attach_audio_stream("s1", AudioStreamHandle::new("turn-99"));
    for state in ALL_STATES {
        ctrl.set_state("s1", *state, 100, None).unwrap();
    }

    let evs = ctrl.renderer().recent_events();
    assert!(!evs.is_empty());
    for ev in evs {
        let s = serde_json::to_string(&ev).expect("serialise");
        assert!(
            s.contains("\"kind\":"),
            "serde-tagged 'kind' must appear: {s}"
        );
        let back: RendererEvent = serde_json::from_str(&s).expect("deserialise");
        assert_eq!(back, ev, "round-trip must be lossless");
    }
}

#[test]
fn renderer_is_dyn_compatible_via_dyn_ref() {
    // Build a stub, hand out a &dyn Renderer, exercise the trait
    // through the trait-object boundary.
    let stub = LogStubRenderer::new(MotionClipLibraryHandle::new(
        "test.lib",
        PathBuf::from("/dev/null"),
    ));
    let dyn_ref: &dyn Renderer = &stub;

    let evs = dyn_ref
        .on_transition(PresenceState::Quiet, PresenceState::Listening, 1, None)
        .expect("dyn renderer call");
    assert!(!evs.is_empty());
    assert_eq!(dyn_ref.library().library_id, "test.lib");
}

#[test]
fn renderer_is_dyn_compatible_via_boxed_controller() {
    // Build a controller wired to a Box<dyn Renderer> — confirms the
    // trait-object boundary survives all the way through the
    // PresenceController adapter.
    let library = MotionClipLibraryHandle::new("boxed.lib", PathBuf::from("/tmp/x"));
    let stub: Box<dyn Renderer> = Box::new(LogStubRenderer::new(library.clone()));
    let ctrl: BoxedRendererController<InMemoryPresenceController> =
        RenderingPresenceController::new(InMemoryPresenceController::new(), stub);

    ctrl.set_state("s1", PresenceState::Thinking, 50, None)
        .unwrap();
    let snap = ctrl.current("s1").unwrap();
    assert_eq!(snap.state, PresenceState::Thinking);
    assert_eq!(ctrl.renderer().library().library_id, "boxed.lib");
}

#[test]
fn wrapping_preserves_underlying_controller_semantics() {
    // The adapter must remain a faithful PresenceController — the
    // existing 22-test contract on InMemoryPresenceController must
    // continue to hold when seen through the wrapper.
    let ctrl = fresh_controller();
    ctrl.set_state("a", PresenceState::Listening, 1, None)
        .unwrap();
    ctrl.set_state("b", PresenceState::Thinking, 1, None)
        .unwrap();

    assert_eq!(ctrl.current("a").unwrap().state, PresenceState::Listening);
    assert_eq!(ctrl.current("b").unwrap().state, PresenceState::Thinking);
    assert_eq!(ctrl.current("ghost").unwrap().state, PresenceState::Quiet);

    ctrl.clear_session("a").unwrap();
    assert_eq!(ctrl.current("a").unwrap().state, PresenceState::Quiet);
    assert_eq!(ctrl.current("b").unwrap().state, PresenceState::Thinking);
}

#[test]
fn audio_attach_is_per_session() {
    // Audio attached to session A must not bleed into session B.
    let ctrl = fresh_controller();
    ctrl.attach_audio_stream("a", AudioStreamHandle::new("a-stream"));
    ctrl.set_state("a", PresenceState::Responding, 1, None)
        .unwrap();
    ctrl.set_state("b", PresenceState::Responding, 2, None)
        .unwrap();

    let lip: Vec<_> = ctrl
        .renderer()
        .recent_events()
        .into_iter()
        .filter_map(|e| match e {
            RendererEvent::LipSyncOverlayRequested {
                audio_stream_id, ..
            } => Some(audio_stream_id),
            _ => None,
        })
        .collect();
    assert_eq!(lip, vec!["a-stream"], "only session a should lip-sync");
}
