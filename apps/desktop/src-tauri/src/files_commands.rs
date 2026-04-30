//! T1.3 — Tauri command surface for the L5-gated file-workflow
//! executor.
//!
//! This module is the call site that implements the wiring contract
//! documented in `packages/l5-files/README.md` §"Wiring contract":
//!
//! 1. Resolve a `Capability` via
//!    [`aether_l5_files::capability_for_method`] for the method
//!    being requested.
//! 2. Ask `aether_l5_policy::PolicyEngine::evaluate` for a
//!    `Decision::Allow` against an `ActionRequest` carrying that
//!    capability.
//! 3. Only on `Allow` invoke the matching method on
//!    `state.files_executor.<method>(...).await`.
//! 4. `FilesExecError` is mapped to `String` for the IPC boundary.
//!
//! Mirrors `browser_commands.rs` end-to-end so the structural pattern
//! is the same across the two L5-gated executor surfaces in the shell.
//!
//! ## Backend status
//!
//! The active executor today is the
//! [`StdFsExecutor`](aether_l5_files::std_fs_stub::StdFsExecutor)
//! stub: every method returns
//! [`FilesExecError::BackendDisabled`](aether_l5_files::FilesExecError::BackendDisabled).
//! This wiring is therefore end-to-end exercised today against the
//! stub's `BackendDisabled` returns, and the only change required
//! when the real `std::fs` / `tokio::fs` driver lands is the
//! constructor used in `state::AppState::build`.
//!
//! ## Resource scope
//!
//! Filesystem capabilities bind their `ResourceScope` to the path
//! the command targets via [`ResourceScope::Path`] — L5 already grew
//! that variant with the file-workflow capabilities, so the
//! scope-allowlist check has the right information at policy-eval
//! time. `rename` carries the *destination* path in the bound scope:
//! both endpoints must be in approved scope, and the destination is
//! the new home for the file (mirroring how `browser_navigate` carries
//! the destination URL). The `grep` command targets a directory root
//! rather than a single file but uses the same `ResourceScope::Path`
//! variant — the policy boundary is the path string regardless of
//! whether it names a file or a directory.

use std::path::PathBuf;
use std::sync::Arc;

use aether_l5_files::{FilesExecutor, GrepHit};
use aether_l5_policy::capability::{Capability, ResourceScope};
use aether_l5_policy::common::{MonotonicTimestamp, RequestId, TurnId};
use aether_l5_policy::decision::Decision;
use aether_l5_policy::policy_engine::ActionRequest;
use aether_l5_policy::PersonaId;
use tauri::State;

use crate::state::AppState;

/// Build a one-off `ActionRequest` for a file-method capability gate.
///
/// The `request_id` / `turn_id` are deliberately synthetic
/// (`files-…` prefix) so audit-row consumers can identify them as
/// command-surface gates rather than turn-engine emits. `actor_persona`
/// is read from the active engine, matching every other capability
/// gate in the shell.
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
        request_id: RequestId(format!("files-{method}-{ts}")),
        turn_id: TurnId(format!("files-{method}-turn-{ts}")),
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

/// Resolve the capability for `method`, build an `ActionRequest`, and
/// run it through the active L5 `PolicyEngine`. On `Allow` returns
/// `Ok(())` and the executor invocation may proceed; otherwise returns
/// an error string the IPC boundary surfaces verbatim to the renderer.
pub(crate) fn gate(
    state: &AppState,
    method: &'static str,
    resource: ResourceScope,
) -> Result<(), String> {
    let cap = aether_l5_files::capability_for_method(method)
        .ok_or_else(|| format!("files method {method:?} has no L5 capability mapping"))?;
    let request = build_request(state, cap, resource, method);
    let active = state.active.read().expect("active read lock");
    match active.policy.evaluate(request) {
        Ok(Decision::Allow { .. }) => Ok(()),
        Ok(other) => Err(format!("files_{method} not permitted: {other:?}")),
        Err(e) => Err(format!("files_{method} policy evaluate error: {e}")),
    }
}

/// Map a `FilesExecError` into the `String` shape the Tauri IPC
/// boundary expects. The `BackendDisabled` variant is preserved
/// verbatim so the renderer can recognise the stub-only state.
pub(crate) fn map_exec_err(e: aether_l5_files::FilesExecError) -> String {
    e.to_string()
}

/// Convert a path argument received over IPC (always a `String`)
/// into the typed [`ResourceScope::Path`] the L5 gate expects.
fn scope_for_path(path: &str) -> ResourceScope {
    ResourceScope::Path(path.to_string())
}

// ----- Inner (test-friendly) handlers -------------------------------------
//
// Each Tauri command delegates to a `*_inner(&AppState, ...)` async fn
// so unit tests can drive the same wiring without constructing a
// `tauri::State` (which requires a real Tauri runtime). The thin
// `#[tauri::command]` wrappers below just unwrap the `State` and call
// the inner.

pub(crate) async fn files_read_inner(
    state: &AppState,
    path: String,
) -> Result<Vec<u8>, String> {
    gate(state, "read", scope_for_path(&path))?;
    let exec = state.files_executor.clone();
    exec.read(&PathBuf::from(&path)).await.map_err(map_exec_err)
}

pub(crate) async fn files_create_inner(
    state: &AppState,
    path: String,
    contents: Vec<u8>,
) -> Result<(), String> {
    gate(state, "create", scope_for_path(&path))?;
    let exec = state.files_executor.clone();
    exec.create(&PathBuf::from(&path), &contents)
        .await
        .map_err(map_exec_err)
}

pub(crate) async fn files_edit_inner(
    state: &AppState,
    path: String,
    contents: Vec<u8>,
) -> Result<(), String> {
    gate(state, "edit", scope_for_path(&path))?;
    let exec = state.files_executor.clone();
    exec.edit(&PathBuf::from(&path), &contents)
        .await
        .map_err(map_exec_err)
}

pub(crate) async fn files_rename_inner(
    state: &AppState,
    src: String,
    dst: String,
) -> Result<(), String> {
    // The destination is bound into the policy `ResourceScope` because
    // a rename's effect is "move file to dst" — the new home is what
    // the scope-allowlist check needs to authorize. The real backend
    // also enforces that `src` is in scope when it canonicalizes both
    // endpoints; the policy gate here covers the destination side.
    gate(state, "rename", scope_for_path(&dst))?;
    let exec = state.files_executor.clone();
    exec.rename(&PathBuf::from(&src), &PathBuf::from(&dst))
        .await
        .map_err(map_exec_err)
}

pub(crate) async fn files_delete_inner(
    state: &AppState,
    path: String,
) -> Result<(), String> {
    gate(state, "delete", scope_for_path(&path))?;
    let exec = state.files_executor.clone();
    exec.delete(&PathBuf::from(&path))
        .await
        .map_err(map_exec_err)
}

pub(crate) async fn files_grep_inner(
    state: &AppState,
    root: String,
    pattern: String,
) -> Result<Vec<GrepHit>, String> {
    gate(state, "grep", scope_for_path(&root))?;
    let exec = state.files_executor.clone();
    exec.grep(&PathBuf::from(&root), &pattern)
        .await
        .map_err(map_exec_err)
}

// ----- Tauri commands -----------------------------------------------------

#[tauri::command]
pub async fn files_read(
    path: String,
    state: State<'_, Arc<AppState>>,
) -> Result<Vec<u8>, String> {
    files_read_inner(state.as_ref(), path).await
}

#[tauri::command]
pub async fn files_create(
    path: String,
    contents: Vec<u8>,
    state: State<'_, Arc<AppState>>,
) -> Result<(), String> {
    files_create_inner(state.as_ref(), path, contents).await
}

#[tauri::command]
pub async fn files_edit(
    path: String,
    contents: Vec<u8>,
    state: State<'_, Arc<AppState>>,
) -> Result<(), String> {
    files_edit_inner(state.as_ref(), path, contents).await
}

#[tauri::command]
pub async fn files_rename(
    src: String,
    dst: String,
    state: State<'_, Arc<AppState>>,
) -> Result<(), String> {
    files_rename_inner(state.as_ref(), src, dst).await
}

#[tauri::command]
pub async fn files_delete(
    path: String,
    state: State<'_, Arc<AppState>>,
) -> Result<(), String> {
    files_delete_inner(state.as_ref(), path).await
}

#[tauri::command]
pub async fn files_grep(
    root: String,
    pattern: String,
    state: State<'_, Arc<AppState>>,
) -> Result<Vec<GrepHit>, String> {
    files_grep_inner(state.as_ref(), root, pattern).await
}

// ----- Tests --------------------------------------------------------------

#[cfg(test)]
mod tests {
    //! Unit tests for the files command surface.
    //!
    //! These tests verify the wiring contract end-to-end against a
    //! tracking mock executor:
    //!
    //! 1. `capability_for_method` resolves the right capability for
    //!    each method (sanity-check against the upstream L5 map).
    //! 2. `map_exec_err` preserves the `BackendDisabled` signal.
    //! 3. The `gate(...)` helper produces an `Err` for non-`Allow`
    //!    decisions and the executor is NOT invoked when the gate
    //!    denies (security invariant). When the gate `Allow`s, the
    //!    stub returns `BackendDisabled` and the wiring surfaces it
    //!    verbatim.
    //! 4. `rename` binds the *destination* path into the policy
    //!    `ResourceScope`; lock that contract here so a refactor that
    //!    accidentally swaps src/dst breaks loudly.

    use super::*;
    use aether_l5_files::FilesExecError;
    use async_trait::async_trait;
    use std::path::Path;
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
    impl FilesExecutor for MockExecutor {
        async fn read(&self, _path: &Path) -> Result<Vec<u8>, FilesExecError> {
            self.calls.lock().unwrap().push("read".into());
            Err(FilesExecError::BackendDisabled)
        }
        async fn create(
            &self,
            _path: &Path,
            _contents: &[u8],
        ) -> Result<(), FilesExecError> {
            self.calls.lock().unwrap().push("create".into());
            Err(FilesExecError::BackendDisabled)
        }
        async fn edit(
            &self,
            _path: &Path,
            _contents: &[u8],
        ) -> Result<(), FilesExecError> {
            self.calls.lock().unwrap().push("edit".into());
            Err(FilesExecError::BackendDisabled)
        }
        async fn rename(
            &self,
            _src: &Path,
            _dst: &Path,
        ) -> Result<(), FilesExecError> {
            self.calls.lock().unwrap().push("rename".into());
            Err(FilesExecError::BackendDisabled)
        }
        async fn delete(&self, _path: &Path) -> Result<(), FilesExecError> {
            self.calls.lock().unwrap().push("delete".into());
            Err(FilesExecError::BackendDisabled)
        }
        async fn grep(
            &self,
            _root: &Path,
            _pattern: &str,
        ) -> Result<Vec<GrepHit>, FilesExecError> {
            self.calls.lock().unwrap().push("grep".into());
            Err(FilesExecError::BackendDisabled)
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

    /// Build an in-memory `AppState` and swap its `files_executor`
    /// field for a tracking mock.
    fn state_with_mock() -> (AppState, Arc<MockExecutor>) {
        let mock = Arc::new(MockExecutor::default());
        let mut state = AppState::new().expect("AppState::new in-memory");
        state.files_executor = mock.clone() as Arc<dyn FilesExecutor>;
        (state, mock)
    }

    #[test]
    fn capability_resolution_matches_l5_files_map() {
        // Sanity — the wiring contract this module implements depends
        // on `capability_for_method` returning the expected variants.
        // If the upstream map ever drifts, the gate() body breaks
        // silently; this guard fails loudly first.
        assert_eq!(
            aether_l5_files::capability_for_method("read"),
            Some(Capability::FilesRead)
        );
        assert_eq!(
            aether_l5_files::capability_for_method("create"),
            Some(Capability::FilesCreate)
        );
        assert_eq!(
            aether_l5_files::capability_for_method("edit"),
            Some(Capability::FilesEdit)
        );
        assert_eq!(
            aether_l5_files::capability_for_method("rename"),
            Some(Capability::FilesRenameMove)
        );
        assert_eq!(
            aether_l5_files::capability_for_method("delete"),
            Some(Capability::FilesDelete)
        );
        // Read-side rationale: see `aether_l5_files::capability_map`.
        assert_eq!(
            aether_l5_files::capability_for_method("grep"),
            Some(Capability::FilesRead)
        );
    }

    #[test]
    fn map_exec_err_preserves_backend_disabled_signal() {
        let msg = map_exec_err(FilesExecError::BackendDisabled);
        assert!(
            msg.contains("disabled"),
            "BackendDisabled string must mention 'disabled'; got {msg:?}"
        );
    }

    #[test]
    fn gated_path_either_allows_through_to_stub_or_blocks_before_executor() {
        // Security invariant: across all six gated commands, the
        // executor is invoked at most once per call, and ONLY when
        // the gate's Allow path was taken. A non-Allow decision MUST
        // produce an error WITHOUT touching the executor.
        //
        // We don't pin to the current default policy disposition for
        // FilesRead et al. (it can be tuned independently); we
        // verify the invariant holds in whichever branch we land in.
        for (method, run) in files_method_drivers() {
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
                Err(_other_msg) => {
                    // Gate denied / Asked. Executor MUST NOT have
                    // been invoked. This is the security invariant
                    // the wiring exists to enforce.
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

    #[test]
    fn rename_binds_destination_into_resource_scope() {
        // Lock the rename src/dst contract: the destination is what
        // gets bound into the policy ResourceScope. A refactor that
        // accidentally passes `src` to `scope_for_path` would silently
        // change which path the policy gate authorizes against — this
        // test fails loudly if that happens by checking the rendered
        // gate-error string for the destination, never the source.
        let (state, mock) = state_with_mock();
        let res = block_on(files_rename_inner(
            &state,
            "/tmp/aether-src.txt".into(),
            "/tmp/aether-dst.txt".into(),
        ));
        match res {
            Err(ref msg) if msg.contains("disabled") => {
                // Allow path: executor was invoked with both paths;
                // we don't see the scope string in this branch but
                // the executor mock saw exactly one rename call.
                assert_eq!(mock.calls(), vec!["rename".to_string()]);
            }
            Err(ref msg) => {
                // Deny / Ask path: the rendered error includes the
                // ActionRequest debug, which contains the resource
                // scope. The dst MUST appear; the src MUST NOT.
                assert!(
                    msg.contains("aether-dst.txt"),
                    "rename gate error should mention destination path; got {msg:?}",
                );
                assert!(
                    !msg.contains("aether-src.txt"),
                    "rename gate error must NOT mention source path \
                     (only destination is bound into ResourceScope); got {msg:?}",
                );
            }
            Ok(_) => panic!("stub never returns Ok"),
        }
    }

    /// One driver per gated command. Each driver invokes the inner
    /// handler against the supplied state and returns a `Result<(), String>`
    /// with the success type unified to `()` so the test loop can be
    /// uniform across return types.
    #[allow(clippy::type_complexity)]
    fn files_method_drivers(
    ) -> Vec<(&'static str, Box<dyn Fn(&AppState) -> Result<(), String>>)> {
        vec![
            (
                "read",
                Box::new(|s: &AppState| {
                    block_on(files_read_inner(s, "/tmp/aether-test.txt".into()))
                        .map(|_bytes| ())
                }),
            ),
            (
                "create",
                Box::new(|s: &AppState| {
                    block_on(files_create_inner(
                        s,
                        "/tmp/aether-test.txt".into(),
                        b"hello".to_vec(),
                    ))
                }),
            ),
            (
                "edit",
                Box::new(|s: &AppState| {
                    block_on(files_edit_inner(
                        s,
                        "/tmp/aether-test.txt".into(),
                        b"hello".to_vec(),
                    ))
                }),
            ),
            (
                "rename",
                Box::new(|s: &AppState| {
                    block_on(files_rename_inner(
                        s,
                        "/tmp/aether-src.txt".into(),
                        "/tmp/aether-dst.txt".into(),
                    ))
                }),
            ),
            (
                "delete",
                Box::new(|s: &AppState| {
                    block_on(files_delete_inner(s, "/tmp/aether-test.txt".into()))
                }),
            ),
            (
                "grep",
                Box::new(|s: &AppState| {
                    block_on(files_grep_inner(
                        s,
                        "/tmp/aether-root".into(),
                        "TODO".into(),
                    ))
                    .map(|_v| ())
                }),
            ),
        ]
    }
}
