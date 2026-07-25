//! T1.3 — Tauri command surface for the L5-gated browser automation
//! executor.
//!
//! This module is the call site that implements the wiring contract
//! documented in `packages/l5-browser/README.md` §"Wiring contract":
//!
//! 1. Resolve a `Capability` via
//!    [`aether_l5_browser::capability_for_method`] for the method
//!    being requested.
//! 2. Ask `aether_l5_policy::PolicyEngine::evaluate` for a
//!    `Decision::Allow` against an `ActionRequest` carrying that
//!    capability.
//! 3. Only on `Allow` invoke the matching method on
//!    `state.browser_executor.<method>(...).await`.
//! 4. `BrowserExecError` is mapped to `String` for the IPC boundary.
//!
//! `close` is intentionally ungated per the L5-browser README contract
//! — releasing session resources is always permitted.
//!
//! ## Backend status
//!
//! The active executor today is the
//! [`PlaywrightExecutor`](aether_l5_browser::playwright_stub::PlaywrightExecutor)
//! stub: every method returns
//! [`BrowserExecError::BackendDisabled`](aether_l5_browser::BrowserExecError::BackendDisabled).
//! This wiring is therefore end-to-end exercised today against the
//! stub's `BackendDisabled` returns, and the only change required when
//! the real Node-subprocess Playwright driver lands is the constructor
//! used in `state::AppState::build`.
//!
//! ## Resource scope
//!
//! `BrowserOpen` and `BrowserNavigate` (which both map to the
//! `BrowserOpen` capability) bind their `ResourceScope` to the URL the
//! command targets so the L5 scope-allowlist check has the right
//! information. The other browser capabilities are session-scoped at
//! the executor layer; we pass `ResourceScope::None` for them today,
//! matching the existing `backfill.rs` precedent for non-resource
//! capabilities. A later session can promote selector-bearing scopes
//! once L5 grows a `ResourceScope::Selector(...)` variant if that
//! granularity is wanted.

use std::sync::Arc;

use aether_l5_browser::{BrowserExecutor, FormField, PageSnapshot, SessionId};
use aether_l5_policy::capability::{Capability, ResourceScope};
use aether_l5_policy::common::{MonotonicTimestamp, RequestId, TurnId};
use aether_l5_policy::decision::Decision;
use aether_l5_policy::policy_engine::ActionRequest;
use aether_l5_policy::PersonaId;
use aether_l7_trust::{approval_prompt_from_ticket, human_capability, human_scope};
use tauri::{AppHandle, Emitter, Manager, State};

use crate::commands::ApprovalPayload;
use crate::state::{AppState, PendingApproval, PendingExecutorCall};

/// Build a one-off `ActionRequest` for a browser-method capability
/// gate.
///
/// The `request_id` / `turn_id` are deliberately synthetic (`browser-…`
/// prefix) so audit-row consumers can identify them as command-surface
/// gates rather than turn-engine emits. `actor_persona` is read from
/// the active engine, matching every other capability gate in the
/// shell.
fn build_request(
    state: &AppState,
    capability: Capability,
    resource: ResourceScope,
    method: &'static str,
) -> ActionRequest {
    let ts = state.next_ts();
    let persona = {
        let a = state.active.read().expect("active read lock");
        PersonaId(a.compiled.persona_id.0.clone())
    };
    ActionRequest {
        request_id: RequestId(format!("browser-{method}-{ts}")),
        turn_id: TurnId(format!("browser-{method}-turn-{ts}")),
        capability,
        resource,
        actor_persona: persona,
        emitted_at: MonotonicTimestamp(ts),
        task_id: None,
        provenance_tags: Vec::new(),
        intended_route: None,
        risk_class_hint: None,
        audit_extras: None,
    }
}

/// Outcome of the L5 gate evaluation. Wave 11 split this from the
/// previous binary `Result<(), String>` so a `Decision::Ask` can route
/// through the existing approval flow instead of being collapsed into
/// a "not permitted" error string.
pub(crate) enum GateOutcome {
    /// Policy granted the action. The executor invocation may proceed.
    Allow,
    /// Policy is asking for user approval. The caller should register a
    /// `PendingApproval::Executor` row keyed on `approval.ticket_id`,
    /// transition presence, emit `executor:awaiting_approval`, and
    /// return the sentinel error string built by
    /// [`awaiting_approval_sentinel`] so the IPC boundary signals
    /// "wait — UI will resolve" without inventing a new wire-success
    /// shape.
    ///
    /// Wave 12 added `ticket`: the live `ApprovalTicket` from the gate's
    /// `Decision::Ask { ticket, .. }`. Cached on `PendingApproval::Executor`
    /// so the reject path can call `respond_approval(Reject)` for L5
    /// audit-row completeness.
    AwaitingApproval {
        approval: ApprovalPayload,
        ticket: aether_l5_policy::ApprovalTicket,
    },
}

/// Sentinel error string returned by `*_inner` when the gate Asks.
/// Stable wire format: `awaiting_approval:<ticket_id>` so the renderer
/// can route the response to the modal awaiter without parsing the
/// human-readable parts. The `executor:awaiting_approval` Tauri event
/// carries the full `ApprovalPayload`; this string is just a
/// machine-readable confirmation that a ticket was registered.
pub(crate) fn awaiting_approval_sentinel(ticket_id: &str) -> String {
    format!("awaiting_approval:{ticket_id}")
}

/// Resolve the capability for `method`, build an `ActionRequest`, run
/// it through the active L5 `PolicyEngine`, and translate the decision
/// into a [`GateOutcome`]. `Decision::Ask` is converted into an
/// [`ApprovalPayload`] suitable for the existing UI modal so the caller
/// can register pending state and emit the approval event.
pub(crate) fn gate(
    state: &AppState,
    method: &'static str,
    resource: ResourceScope,
) -> Result<GateOutcome, String> {
    let cap = aether_l5_browser::capability_for_method(method)
        .ok_or_else(|| format!("browser method {method:?} has no L5 capability mapping"))?;
    let request = build_request(state, cap, resource, method);
    let active = state.active.read().expect("active read lock");
    match active.policy.evaluate(request) {
        Ok(Decision::Allow { .. }) => Ok(GateOutcome::Allow),
        Ok(Decision::Ask { ticket, .. }) => {
            // Clone the live ticket so we can both build the human-shaped
            // payload (consumed by the UI modal) AND cache it on the
            // pending row (so the reject path can call respond_approval).
            let ticket_for_pending = ticket.clone();
            let prompt = approval_prompt_from_ticket(ticket, None);
            let side_effecting = crate::commands::capability_is_side_effecting(&prompt.capability);
            let approval = ApprovalPayload {
                ticket_id: prompt.ticket.ticket_id.0.clone(),
                capability: human_capability(&prompt.capability).to_string(),
                scope: human_scope(&prompt.resource),
                reason: prompt.reason.0.clone(),
                risk_hint:
                    "Session-only approval. This will not persist beyond this session.".into(),
                // Wave 15 — browser executor gates are never inside a
                // task lineage today (the gate's TurnRequest above has
                // task_id: None). Future task-aware paths flip this.
                task_id_present: false,
                side_effecting,
            };
            Ok(GateOutcome::AwaitingApproval {
                approval,
                ticket: ticket_for_pending,
            })
        }
        Ok(other) => Err(format!("browser_{method} not permitted: {other:?}")),
        Err(e) => Err(format!("browser_{method} policy evaluate error: {e}")),
    }
}

/// Register the `PendingApproval::Executor` row, transition presence to
/// AwaitingApproval (if an `AppHandle` was supplied), and emit
/// `executor:awaiting_approval` so the renderer can show the modal.
/// Returns the sentinel error string that the inner handler surfaces
/// across the IPC boundary.
fn register_executor_pending(
    state: &AppState,
    app: Option<&AppHandle>,
    call: PendingExecutorCall,
    approval: ApprovalPayload,
    ticket: aether_l5_policy::ApprovalTicket,
) -> String {
    let sentinel = awaiting_approval_sentinel(&approval.ticket_id);
    state.record_pending(
        approval.ticket_id.clone(),
        PendingApproval::Executor {
            call,
            approval: approval.clone(),
            ticket,
        },
    );
    if let Some(app) = app {
        // Best-effort presence transition + event emit. Both are UX
        // niceties; the renderer also listens for the inner's sentinel
        // error string ("awaiting_approval:<ticket_id>") and falls back
        // to the chat-surface modal flow if events are dropped.
        let _ = app.emit("executor:awaiting_approval", approval);
        // Presence transition mirrors `submit_turn`'s Ask path.
        let _ = state.presence.set_state(
            crate::state::SESSION_ID,
            aether_l3_presence::PresenceState::AwaitingApproval,
            state.next_ts(),
            Some(sentinel.clone()),
        );
    }
    sentinel
}

/// Map a `BrowserExecError` into the `String` shape the Tauri IPC
/// boundary expects. The `BackendDisabled` variant is preserved
/// verbatim so the renderer can recognise the stub-only state.
pub(crate) fn map_exec_err(e: aether_l5_browser::BrowserExecError) -> String {
    e.to_string()
}

// ----- Inner (test-friendly) handlers -------------------------------------
//
// Each Tauri command delegates to a `*_inner(&AppState, ...)` async fn
// so unit tests can drive the same wiring without constructing a
// `tauri::State` (which requires a real Tauri runtime). The thin
// `#[tauri::command]` wrappers below just unwrap the `State` and call
// the inner.

/// Dispatch on a [`GateOutcome`]. On `Allow`, returns `Ok(())` and the
/// caller fires the executor. On `AwaitingApproval`, registers the
/// pending row (carrying the `PendingExecutorCall` produced by `build`)
/// and returns the sentinel error string so the IPC boundary can hand
/// off to the modal-resolve flow.
fn dispatch_gate(
    state: &AppState,
    app: Option<&AppHandle>,
    outcome: GateOutcome,
    build: impl FnOnce() -> PendingExecutorCall,
) -> Result<(), String> {
    match outcome {
        GateOutcome::Allow => Ok(()),
        GateOutcome::AwaitingApproval { approval, ticket } => {
            let sentinel = register_executor_pending(state, app, build(), approval, ticket);
            Err(sentinel)
        }
    }
}

pub(crate) async fn browser_open_inner(
    state: &AppState,
    app: Option<&AppHandle>,
    url: String,
) -> Result<SessionId, String> {
    let outcome = gate(state, "open", ResourceScope::Url(url.clone()))?;
    dispatch_gate(state, app, outcome, || PendingExecutorCall::BrowserOpen {
        url: url.clone(),
    })?;
    let exec = state.browser_executor.clone();
    exec.open(&url).await.map_err(map_exec_err)
}

pub(crate) async fn browser_navigate_inner(
    state: &AppState,
    app: Option<&AppHandle>,
    session: SessionId,
    url: String,
) -> Result<(), String> {
    let outcome = gate(state, "navigate", ResourceScope::Url(url.clone()))?;
    dispatch_gate(state, app, outcome, || PendingExecutorCall::BrowserNavigate {
        session: session.clone(),
        url: url.clone(),
    })?;
    let exec = state.browser_executor.clone();
    exec.navigate(session, &url).await.map_err(map_exec_err)
}

pub(crate) async fn browser_read_page_inner(
    state: &AppState,
    app: Option<&AppHandle>,
    session: SessionId,
) -> Result<PageSnapshot, String> {
    let outcome = gate(state, "read_page", ResourceScope::None)?;
    dispatch_gate(state, app, outcome, || PendingExecutorCall::BrowserReadPage {
        session: session.clone(),
    })?;
    let exec = state.browser_executor.clone();
    exec.read_page(session).await.map_err(map_exec_err)
}

pub(crate) async fn browser_extract_inner(
    state: &AppState,
    app: Option<&AppHandle>,
    session: SessionId,
    selector: String,
) -> Result<Vec<String>, String> {
    let outcome = gate(state, "extract", ResourceScope::None)?;
    dispatch_gate(state, app, outcome, || PendingExecutorCall::BrowserExtract {
        session: session.clone(),
        selector: selector.clone(),
    })?;
    let exec = state.browser_executor.clone();
    exec.extract(session, &selector).await.map_err(map_exec_err)
}

pub(crate) async fn browser_fill_form_inner(
    state: &AppState,
    app: Option<&AppHandle>,
    session: SessionId,
    fields: Vec<FormField>,
) -> Result<(), String> {
    let outcome = gate(state, "fill_form", ResourceScope::None)?;
    dispatch_gate(state, app, outcome, || PendingExecutorCall::BrowserFillForm {
        session: session.clone(),
        fields: fields.clone(),
    })?;
    let exec = state.browser_executor.clone();
    exec.fill_form(session, &fields).await.map_err(map_exec_err)
}

pub(crate) async fn browser_submit_inner(
    state: &AppState,
    app: Option<&AppHandle>,
    session: SessionId,
    selector: String,
) -> Result<(), String> {
    let outcome = gate(state, "submit", ResourceScope::None)?;
    dispatch_gate(state, app, outcome, || PendingExecutorCall::BrowserSubmit {
        session: session.clone(),
        selector: selector.clone(),
    })?;
    let exec = state.browser_executor.clone();
    exec.submit(session, &selector).await.map_err(map_exec_err)
}

pub(crate) async fn browser_close_inner(
    state: &AppState,
    session: SessionId,
) -> Result<(), String> {
    // Intentionally ungated per the L5-browser wiring contract.
    let exec = state.browser_executor.clone();
    exec.close(session).await.map_err(map_exec_err)
}

// ----- Tauri commands -----------------------------------------------------

#[tauri::command]
pub async fn browser_open(
    url: String,
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
) -> Result<SessionId, String> {
    browser_open_inner(state.as_ref(), Some(&app), url).await
}

#[tauri::command]
pub async fn browser_navigate(
    session: SessionId,
    url: String,
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
) -> Result<(), String> {
    browser_navigate_inner(state.as_ref(), Some(&app), session, url).await
}

#[tauri::command]
pub async fn browser_read_page(
    session: SessionId,
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
) -> Result<PageSnapshot, String> {
    browser_read_page_inner(state.as_ref(), Some(&app), session).await
}

#[tauri::command]
pub async fn browser_extract(
    session: SessionId,
    selector: String,
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
) -> Result<Vec<String>, String> {
    browser_extract_inner(state.as_ref(), Some(&app), session, selector).await
}

#[tauri::command]
pub async fn browser_fill_form(
    session: SessionId,
    fields: Vec<FormField>,
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
) -> Result<(), String> {
    browser_fill_form_inner(state.as_ref(), Some(&app), session, fields).await
}

#[tauri::command]
pub async fn browser_submit(
    session: SessionId,
    selector: String,
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
) -> Result<(), String> {
    browser_submit_inner(state.as_ref(), Some(&app), session, selector).await
}

/// Close is intentionally ungated per the L5-browser README contract:
/// releasing session resources must always be permitted, otherwise a
/// denied close would leak browser processes.
#[tauri::command]
pub async fn browser_close(
    session: SessionId,
    state: State<'_, Arc<AppState>>,
) -> Result<(), String> {
    browser_close_inner(state.as_ref(), session).await
}

// ----- Tests --------------------------------------------------------------

#[cfg(test)]
mod tests {
    //! Unit tests for the browser command surface.
    //!
    //! These tests verify the wiring contract end-to-end against a
    //! tracking mock executor:
    //!
    //! 1. `capability_for_method` resolves the right capability for
    //!    each method (sanity-check against the upstream L5 map).
    //! 2. `close` skips the gate and always invokes the executor —
    //!    mandated by the L5-browser README.
    //! 3. The `gate(...)` helper produces an `Err` for non-`Allow`
    //!    decisions and the executor is NOT invoked when the gate
    //!    denies (security invariant).
    //! 4. When the gate `Allow`s and the stub returns
    //!    `BackendDisabled`, the wiring surfaces the stub's error
    //!    verbatim.

    use super::*;
    use aether_l5_browser::BrowserExecError;
    use async_trait::async_trait;
    use std::sync::Mutex;

    /// Tracking executor: records every method invoked. Returns the
    /// same `BackendDisabled` the real stub returns so failure-path
    /// shape is preserved.
    #[derive(Default)]
    struct MockExecutor {
        calls: Mutex<Vec<String>>,
    }

    impl MockExecutor {
        fn calls(&self) -> Vec<String> {
            self.calls.lock().unwrap().clone()
        }
    }

    #[async_trait]
    impl BrowserExecutor for MockExecutor {
        async fn open(&self, _url: &str) -> Result<SessionId, BrowserExecError> {
            self.calls.lock().unwrap().push("open".into());
            Err(BrowserExecError::BackendDisabled)
        }
        async fn navigate(
            &self,
            _s: SessionId,
            _u: &str,
        ) -> Result<(), BrowserExecError> {
            self.calls.lock().unwrap().push("navigate".into());
            Err(BrowserExecError::BackendDisabled)
        }
        async fn read_page(
            &self,
            _s: SessionId,
        ) -> Result<PageSnapshot, BrowserExecError> {
            self.calls.lock().unwrap().push("read_page".into());
            Err(BrowserExecError::BackendDisabled)
        }
        async fn extract(
            &self,
            _s: SessionId,
            _sel: &str,
        ) -> Result<Vec<String>, BrowserExecError> {
            self.calls.lock().unwrap().push("extract".into());
            Err(BrowserExecError::BackendDisabled)
        }
        async fn fill_form(
            &self,
            _s: SessionId,
            _f: &[FormField],
        ) -> Result<(), BrowserExecError> {
            self.calls.lock().unwrap().push("fill_form".into());
            Err(BrowserExecError::BackendDisabled)
        }
        async fn submit(
            &self,
            _s: SessionId,
            _sel: &str,
        ) -> Result<(), BrowserExecError> {
            self.calls.lock().unwrap().push("submit".into());
            Err(BrowserExecError::BackendDisabled)
        }
        async fn close(&self, _s: SessionId) -> Result<(), BrowserExecError> {
            self.calls.lock().unwrap().push("close".into());
            Err(BrowserExecError::BackendDisabled)
        }
    }

    /// Synchronous block-on for these tests — the executor is a fast
    /// path so we avoid spinning up tokio.
    fn block_on<F: std::future::Future>(fut: F) -> F::Output {
        use std::sync::Arc as StdArc;
        use std::task::{Context, Poll, Wake, Waker};
        struct NoopWaker;
        impl Wake for NoopWaker {
            fn wake(self: StdArc<Self>) {}
        }
        let waker = Waker::from(StdArc::new(NoopWaker));
        let mut ctx = Context::from_waker(&waker);
        let mut fut = Box::pin(fut);
        loop {
            if let Poll::Ready(v) = fut.as_mut().poll(&mut ctx) {
                return v;
            }
        }
    }

    /// Build an in-memory `AppState` and swap its `browser_executor`
    /// field for a tracking mock.
    fn state_with_mock() -> (AppState, Arc<MockExecutor>) {
        let mock = Arc::new(MockExecutor::default());
        let mut state = AppState::new().expect("AppState::new in-memory");
        state.browser_executor = mock.clone() as Arc<dyn BrowserExecutor>;
        (state, mock)
    }

    #[test]
    fn capability_resolution_matches_l5_browser_map() {
        // Sanity — the wiring contract this module implements depends
        // on `capability_for_method` returning the expected variants.
        // If the upstream map ever drifts, the gate() body breaks
        // silently; this guard fails loudly first.
        assert_eq!(
            aether_l5_browser::capability_for_method("open"),
            Some(Capability::BrowserOpen)
        );
        assert_eq!(
            aether_l5_browser::capability_for_method("navigate"),
            Some(Capability::BrowserOpen)
        );
        assert_eq!(
            aether_l5_browser::capability_for_method("read_page"),
            Some(Capability::BrowserReadPage)
        );
        assert_eq!(
            aether_l5_browser::capability_for_method("extract"),
            Some(Capability::BrowserExtractData)
        );
        assert_eq!(
            aether_l5_browser::capability_for_method("fill_form"),
            Some(Capability::BrowserFillForm)
        );
        assert_eq!(
            aether_l5_browser::capability_for_method("submit"),
            Some(Capability::BrowserSubmit)
        );
        assert_eq!(aether_l5_browser::capability_for_method("close"), None);
    }

    #[test]
    fn map_exec_err_preserves_backend_disabled_signal() {
        let msg = map_exec_err(BrowserExecError::BackendDisabled);
        assert!(
            msg.contains("disabled"),
            "BackendDisabled string must mention 'disabled'; got {msg:?}"
        );
    }

    #[test]
    fn close_is_ungated_and_always_calls_executor() {
        // Even if the gate would deny, close must invoke the executor
        // so that browser processes are not leaked.
        let (state, mock) = state_with_mock();
        let res = block_on(browser_close_inner(&state, SessionId::new("s1")));
        assert!(
            matches!(res, Err(ref s) if s.contains("disabled")),
            "expected BackendDisabled error string, got {res:?}"
        );
        assert_eq!(mock.calls(), vec!["close".to_string()]);
    }

    #[test]
    fn gated_path_either_allows_through_to_stub_or_asks_or_blocks_before_executor() {
        // Security invariant: across all six gated commands, the
        // executor is invoked at most once per call, and ONLY when the
        // gate's Allow path was taken. Wave 11 added a third branch:
        // `Decision::Ask` now routes through the pending-approval
        // registry — the inner returns the
        // `awaiting_approval:<ticket_id>` sentinel, registers a
        // `PendingApproval::Executor`, and the executor is NOT invoked
        // until `resolve_approval(approve=true)` fires the second pass.
        //
        // We don't pin to the current default policy disposition for
        // BrowserOpen et al. (it can be tuned independently); we verify
        // the invariant holds in whichever branch we land in.
        for (method, run) in browser_method_drivers() {
            let (state, mock) = state_with_mock();
            let res = run(&state);
            let calls = mock.calls();
            match res {
                Err(ref msg) if msg.contains("disabled") => {
                    // Allow path → stub → BackendDisabled. The mock
                    // saw exactly one call and it matches the method
                    // we drove.
                    assert_eq!(
                        calls,
                        vec![method.to_string()],
                        "Allow path: expected single executor call to {method:?}, got {calls:?}",
                    );
                }
                Err(ref msg) if msg.starts_with("awaiting_approval:") => {
                    // Wave 11 — gate Asked. Executor MUST NOT have
                    // been invoked; the pending registry MUST hold
                    // exactly one row keyed on the ticket id embedded
                    // in the sentinel.
                    assert!(
                        calls.is_empty(),
                        "{method:?} Asked by gate but executor was still called: {calls:?}",
                    );
                    let ticket_id = msg
                        .strip_prefix("awaiting_approval:")
                        .expect("sentinel prefix");
                    assert!(
                        state.take_pending(ticket_id).is_some(),
                        "{method:?}: pending registry should hold a row keyed on the sentinel \
                         ticket id ({ticket_id})",
                    );
                }
                Err(_other_msg) => {
                    // Gate denied. Executor MUST NOT have been
                    // invoked. This is the security invariant the
                    // wiring exists to enforce.
                    assert!(
                        calls.is_empty(),
                        "{method:?} denied by gate but executor was still called: {calls:?}",
                    );
                }
                Ok(_) => {
                    panic!(
                        "{method:?} returned Ok, but the stub always returns BackendDisabled \
                         which must surface as Err",
                    );
                }
            }
        }
    }

    /// One driver per gated command. Each driver invokes the inner
    /// handler against the supplied state and returns a `Result<(), String>`
    /// with the success type unified to `()` so the test loop can be
    /// uniform across return types. Tests pass `None` for the optional
    /// `AppHandle` so the registry-side path is exercised without
    /// requiring a Tauri runtime.
    #[allow(clippy::type_complexity)]
    fn browser_method_drivers(
    ) -> Vec<(&'static str, Box<dyn Fn(&AppState) -> Result<(), String>>)> {
        vec![
            (
                "open",
                Box::new(|s: &AppState| {
                    block_on(browser_open_inner(s, None, "https://example.com".into()))
                        .map(|_sid| ())
                }),
            ),
            (
                "navigate",
                Box::new(|s: &AppState| {
                    block_on(browser_navigate_inner(
                        s,
                        None,
                        SessionId::new("s1"),
                        "https://example.com".into(),
                    ))
                }),
            ),
            (
                "read_page",
                Box::new(|s: &AppState| {
                    block_on(browser_read_page_inner(s, None, SessionId::new("s1")))
                        .map(|_snap| ())
                }),
            ),
            (
                "extract",
                Box::new(|s: &AppState| {
                    block_on(browser_extract_inner(
                        s,
                        None,
                        SessionId::new("s1"),
                        "h1".into(),
                    ))
                    .map(|_v| ())
                }),
            ),
            (
                "fill_form",
                Box::new(|s: &AppState| {
                    block_on(browser_fill_form_inner(
                        s,
                        None,
                        SessionId::new("s1"),
                        vec![FormField {
                            selector: "#name".into(),
                            value: "Don".into(),
                        }],
                    ))
                }),
            ),
            (
                "submit",
                Box::new(|s: &AppState| {
                    block_on(browser_submit_inner(
                        s,
                        None,
                        SessionId::new("s1"),
                        "#submit".into(),
                    ))
                }),
            ),
        ]
    }
}
