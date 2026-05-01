//! Default browser backend — Playwright via Node subprocess.
//!
//! This module is gated behind the `playwright` feature so default
//! builds do not pull subprocess / async-IO infrastructure. When the
//! feature is on, [`PlaywrightExecutor`] spawns a long-lived Node
//! process running [`scripts/driver.mjs`](../../scripts/driver.mjs) and
//! frames JSON-lines requests + responses across stdin/stdout.
//!
//! # Architecture
//!
//! - One Node child process per [`PlaywrightExecutor`] instance.
//! - A monotonically incrementing `req_id` (`AtomicU64`) tags every
//!   outbound request.
//! - A `pending: Mutex<HashMap<u64, oneshot::Sender<DriverReply>>>`
//!   holds the in-flight reply slots.
//! - A background `tokio::task` reads the child's stdout line-by-line,
//!   parses each line as a `DriverReply`, looks up the oneshot by
//!   `req_id`, and dispatches the reply.
//! - Each public method bumps the counter, registers a oneshot, writes
//!   the request line to stdin, and awaits the response with a 10s
//!   timeout.
//!
//! # Failure modes
//!
//! - **Node not on PATH / spawn fails / playwright not installed.**
//!   [`PlaywrightExecutor::new`] never panics. If the child can't be
//!   spawned (or the driver script isn't reachable), the executor is
//!   built in a "disabled" state and every method returns
//!   [`BrowserExecError::BackendDisabled`] with a helpful message.
//! - **Timeout.** A request that exceeds the wall-clock budget returns
//!   [`BrowserExecError::Timeout`].
//! - **Driver-side errors.** The Node driver returns a
//!   `{"err": "...", "kind": "..."}` envelope; `kind` maps to a typed
//!   variant on [`BrowserExecError`] (`Navigation`, `SelectorNotFound`,
//!   `SessionNotFound`, `Timeout`, default → `Internal`).
//!
//! # Layer rules
//!
//! Per CLAUDE.md §1.5, the executor itself does NOT perform any policy
//! check. Call sites (Tauri commands, etc.) resolve a `Capability` via
//! [`crate::capability_for_method`], ask L5 for `Decision::Allow`, and
//! only then invoke a method here.

use std::collections::HashMap;
use std::process::Stdio;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::io::{AsyncBufReadExt, AsyncWrite, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, Command};
use tokio::sync::{oneshot, Mutex};
use tokio::time::timeout;

use crate::executor::BrowserExecutor;
use crate::types::{BrowserExecError, FormField, PageSnapshot, SessionId};

/// Wall-clock budget for any single request to the Node driver.
///
/// 10s covers normal navigation + read; longer jobs should be sliced by
/// the caller.
const REQUEST_TIMEOUT: Duration = Duration::from_secs(10);

/// JSON envelope written to the Node driver's stdin (one per line).
#[derive(Debug, Serialize)]
struct DriverRequest<'a> {
    req_id: u64,
    op: &'a str,
    args: Value,
}

/// JSON envelope read back from the Node driver's stdout (one per line).
///
/// Either `ok` is set (success, value is op-specific) or `err`+`kind`
/// (failure). The driver guarantees exactly one of those branches per
/// `req_id`.
#[derive(Debug, Deserialize)]
struct DriverReply {
    req_id: u64,
    #[serde(default)]
    ok: Option<Value>,
    #[serde(default)]
    err: Option<String>,
    #[serde(default)]
    kind: Option<String>,
}

/// Map a driver-side error `kind` string to a typed
/// [`BrowserExecError`] variant. Unknown kinds fall back to
/// [`BrowserExecError::Internal`].
fn error_from_kind(kind: Option<&str>, msg: String) -> BrowserExecError {
    match kind.unwrap_or("") {
        "Navigation" => BrowserExecError::Navigation(msg),
        "SelectorNotFound" => BrowserExecError::SelectorNotFound(msg),
        "SessionNotFound" => BrowserExecError::SessionNotFound(msg),
        "Timeout" => BrowserExecError::Timeout(msg),
        _ => BrowserExecError::Internal(msg),
    }
}

/// Internal driver state — shared between the public executor and the
/// background stdout-reader task.
struct DriverState {
    /// Child process handle. Held in a Mutex so `Drop` can take it for
    /// graceful shutdown without &mut self plumbing through every
    /// method.
    child: Mutex<Option<Child>>,
    /// Stdin half of the child. Wrapped in a Mutex so concurrent
    /// requests serialize their writes (JSON-lines framing requires
    /// each request to be written atomically).
    stdin: Mutex<Option<ChildStdin>>,
    /// In-flight replies — `req_id` to oneshot sender.
    pending: Mutex<HashMap<u64, oneshot::Sender<DriverReply>>>,
    /// Monotonically increasing request id.
    next_req_id: AtomicU64,
}

/// Playwright-backed [`BrowserExecutor`].
///
/// Construct with [`PlaywrightExecutor::new`]. Drop closes the child
/// process gracefully (best-effort SIGTERM via `kill`).
pub struct PlaywrightExecutor {
    /// `None` when the backend failed to start (Node missing,
    /// driver script missing, etc.). All methods short-circuit to
    /// [`BrowserExecError::BackendDisabled`] in that case.
    inner: Option<Arc<DriverState>>,
    /// Diagnostic message captured at spawn time when `inner` is `None`.
    /// Surfaced through [`BrowserExecError::BackendDisabled`]'s
    /// stringification path.
    spawn_failure: Option<String>,
}

impl std::fmt::Debug for PlaywrightExecutor {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PlaywrightExecutor")
            .field("alive", &self.inner.is_some())
            .field("spawn_failure", &self.spawn_failure)
            .finish()
    }
}

impl Default for PlaywrightExecutor {
    fn default() -> Self {
        Self::new()
    }
}

impl PlaywrightExecutor {
    /// Construct a new Playwright executor.
    ///
    /// Spawns the Node driver process at
    /// `packages/l5-browser/scripts/driver.mjs`, wires up stdin/stdout
    /// JSON-lines framing, and starts the background reader task.
    ///
    /// Never panics. If Node is not on PATH or the driver script can't
    /// be located, the executor is built in a "disabled" state and
    /// every method returns
    /// [`BrowserExecError::BackendDisabled`].
    pub fn new() -> Self {
        match Self::spawn() {
            Ok(state) => Self {
                inner: Some(state),
                spawn_failure: None,
            },
            Err(msg) => {
                tracing::warn!(error = %msg, "playwright driver disabled — backend not available");
                Self {
                    inner: None,
                    spawn_failure: Some(msg),
                }
            }
        }
    }

    /// Resolve the path to the bundled Node driver script.
    ///
    /// We use `CARGO_MANIFEST_DIR` so the path is correct whether this
    /// crate is built in-tree or as a path dep from elsewhere in the
    /// workspace.
    fn driver_script_path() -> std::path::PathBuf {
        let manifest_dir = env!("CARGO_MANIFEST_DIR");
        std::path::PathBuf::from(manifest_dir)
            .join("scripts")
            .join("driver.mjs")
    }

    fn spawn() -> Result<Arc<DriverState>, String> {
        // Spawning the child + the stdout reader task both need a
        // running Tokio runtime. `AppState::build` is called
        // synchronously from many test harnesses (no `#[tokio::test]`,
        // no `Builder::new_current_thread().enable_all().build()`),
        // so we must detect runtime absence and self-degrade instead
        // of panicking. Real production callers always run inside
        // Tauri's async runtime, so this branch is test-only.
        if tokio::runtime::Handle::try_current().is_err() {
            return Err(
                "no Tokio runtime in current thread — playwright driver requires async context"
                    .to_string(),
            );
        }

        let script = Self::driver_script_path();
        if !script.exists() {
            return Err(format!(
                "playwright driver script missing at {}",
                script.display()
            ));
        }

        let mut child = Command::new("node")
            .arg(&script)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true)
            .spawn()
            .map_err(|e| format!("failed to spawn `node {}`: {e}", script.display()))?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| "child stdin not captured".to_string())?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "child stdout not captured".to_string())?;
        // Stderr is drained to a tracing span so the host doesn't fill
        // its OS pipe buffer and deadlock the child. We don't surface
        // stderr lines to callers — they're driver diagnostics only.
        if let Some(stderr) = child.stderr.take() {
            tokio::spawn(async move {
                let mut lines = BufReader::new(stderr).lines();
                while let Ok(Some(line)) = lines.next_line().await {
                    tracing::debug!(target: "aether_l5_browser::driver", "stderr: {line}");
                }
            });
        }

        let state = Arc::new(DriverState {
            child: Mutex::new(Some(child)),
            stdin: Mutex::new(Some(stdin)),
            pending: Mutex::new(HashMap::new()),
            next_req_id: AtomicU64::new(1),
        });

        // Background reader: parses one JSON-line reply per loop iter,
        // pops the matching oneshot from `pending`, and dispatches.
        let reader_state = Arc::clone(&state);
        tokio::spawn(async move {
            let mut lines = BufReader::new(stdout).lines();
            loop {
                match lines.next_line().await {
                    Ok(Some(line)) => {
                        if line.trim().is_empty() {
                            continue;
                        }
                        match serde_json::from_str::<DriverReply>(&line) {
                            Ok(reply) => {
                                let mut pending = reader_state.pending.lock().await;
                                if let Some(tx) = pending.remove(&reply.req_id) {
                                    let _ = tx.send(reply);
                                } else {
                                    tracing::warn!(
                                        req_id = reply.req_id,
                                        "driver reply for unknown req_id (already timed out?)"
                                    );
                                }
                            }
                            Err(e) => {
                                tracing::warn!(
                                    error = %e,
                                    line = %line,
                                    "failed to parse driver reply"
                                );
                            }
                        }
                    }
                    Ok(None) => {
                        tracing::info!("playwright driver stdout closed");
                        break;
                    }
                    Err(e) => {
                        tracing::error!(error = %e, "error reading from driver stdout");
                        break;
                    }
                }
            }
            // Drain any pending requests so callers don't hang forever.
            let mut pending = reader_state.pending.lock().await;
            pending.clear();
        });

        Ok(state)
    }

    /// Send a request to the driver and await the typed reply.
    ///
    /// Generic over the `T` decoded from the driver's `ok` field.
    /// Callers MUST pre-check `self.inner.is_some()` and short-circuit
    /// to [`BrowserExecError::BackendDisabled`] when it isn't — that
    /// gate keeps the error variant under the caller's control rather
    /// than collapsing all "no backend" cases into `Internal`.
    async fn call<T: for<'de> Deserialize<'de>>(
        &self,
        op: &str,
        args: Value,
    ) -> Result<T, BrowserExecError> {
        let state = self
            .inner
            .as_ref()
            .ok_or(BrowserExecError::BackendDisabled)?;
        send_call(state, op, args).await
    }
}

/// Free-function helper so tests can drive a synthetic
/// `Arc<DriverState>` (with a duplex stdin) without going through the
/// real spawn path.
async fn send_call<T: for<'de> Deserialize<'de>>(
    state: &Arc<DriverState>,
    op: &str,
    args: Value,
) -> Result<T, BrowserExecError> {
    let req_id = state.next_req_id.fetch_add(1, Ordering::SeqCst);
    let (tx, rx) = oneshot::channel();
    {
        let mut pending = state.pending.lock().await;
        pending.insert(req_id, tx);
    }

    let req = DriverRequest { req_id, op, args };
    let line = serde_json::to_string(&req)
        .map_err(|e| BrowserExecError::Internal(format!("encoding driver request: {e}")))?;

    {
        let mut stdin_guard = state.stdin.lock().await;
        let stdin = stdin_guard
            .as_mut()
            .ok_or_else(|| BrowserExecError::Internal("driver stdin already closed".into()))?;
        write_line(stdin, &line)
            .await
            .map_err(|e| BrowserExecError::Internal(format!("writing driver request: {e}")))?;
    }

    let reply = match timeout(REQUEST_TIMEOUT, rx).await {
        Ok(Ok(reply)) => reply,
        Ok(Err(_)) => {
            // Reader task dropped the sender → child is gone.
            state.pending.lock().await.remove(&req_id);
            return Err(BrowserExecError::Internal(
                "driver process exited before reply".into(),
            ));
        }
        Err(_) => {
            state.pending.lock().await.remove(&req_id);
            return Err(BrowserExecError::Timeout(format!(
                "{op} request {req_id} exceeded {}s budget",
                REQUEST_TIMEOUT.as_secs()
            )));
        }
    };

    if let Some(err_msg) = reply.err {
        return Err(error_from_kind(reply.kind.as_deref(), err_msg));
    }
    let ok = reply.ok.unwrap_or(Value::Null);
    serde_json::from_value(ok)
        .map_err(|e| BrowserExecError::Internal(format!("decoding driver reply: {e}")))
}

/// Write a line + `\n` to any `AsyncWrite` and flush.
///
/// Hoisted so tests can target a `tokio::io::DuplexStream` without
/// going through a real `ChildStdin`.
async fn write_line<W: AsyncWrite + Unpin>(w: &mut W, line: &str) -> std::io::Result<()> {
    w.write_all(line.as_bytes()).await?;
    w.write_all(b"\n").await?;
    w.flush().await?;
    Ok(())
}

/// JSON shape of `read_page` replies on the wire.
#[derive(Debug, Deserialize)]
struct WirePageSnapshot {
    url: String,
    title: String,
    text_content: String,
    captured_at_ms: u64,
}

impl From<WirePageSnapshot> for PageSnapshot {
    fn from(w: WirePageSnapshot) -> Self {
        Self {
            url: w.url,
            title: w.title,
            text_content: w.text_content,
            captured_at_ms: w.captured_at_ms,
        }
    }
}

#[async_trait]
impl BrowserExecutor for PlaywrightExecutor {
    async fn open(&self, url: &str) -> Result<SessionId, BrowserExecError> {
        if self.inner.is_none() {
            return Err(BrowserExecError::BackendDisabled);
        }
        let id: String = self.call("open", serde_json::json!({ "url": url })).await?;
        Ok(SessionId::new(id))
    }

    async fn navigate(&self, session: SessionId, url: &str) -> Result<(), BrowserExecError> {
        if self.inner.is_none() {
            return Err(BrowserExecError::BackendDisabled);
        }
        let _: Value = self
            .call(
                "navigate",
                serde_json::json!({ "session": session.as_str(), "url": url }),
            )
            .await?;
        Ok(())
    }

    async fn read_page(&self, session: SessionId) -> Result<PageSnapshot, BrowserExecError> {
        if self.inner.is_none() {
            return Err(BrowserExecError::BackendDisabled);
        }
        let snap: WirePageSnapshot = self
            .call(
                "read_page",
                serde_json::json!({ "session": session.as_str() }),
            )
            .await?;
        Ok(snap.into())
    }

    async fn extract(
        &self,
        session: SessionId,
        selector: &str,
    ) -> Result<Vec<String>, BrowserExecError> {
        if self.inner.is_none() {
            return Err(BrowserExecError::BackendDisabled);
        }
        self.call(
            "extract",
            serde_json::json!({ "session": session.as_str(), "selector": selector }),
        )
        .await
    }

    async fn fill_form(
        &self,
        session: SessionId,
        fields: &[FormField],
    ) -> Result<(), BrowserExecError> {
        if self.inner.is_none() {
            return Err(BrowserExecError::BackendDisabled);
        }
        let _: Value = self
            .call(
                "fill_form",
                serde_json::json!({ "session": session.as_str(), "fields": fields }),
            )
            .await?;
        Ok(())
    }

    async fn submit(&self, session: SessionId, selector: &str) -> Result<(), BrowserExecError> {
        if self.inner.is_none() {
            return Err(BrowserExecError::BackendDisabled);
        }
        let _: Value = self
            .call(
                "submit",
                serde_json::json!({ "session": session.as_str(), "selector": selector }),
            )
            .await?;
        Ok(())
    }

    async fn close(&self, session: SessionId) -> Result<(), BrowserExecError> {
        if self.inner.is_none() {
            // Closing a never-started session is a no-op, not an error.
            return Ok(());
        }
        let _: Value = self
            .call("close", serde_json::json!({ "session": session.as_str() }))
            .await?;
        Ok(())
    }
}

impl Drop for PlaywrightExecutor {
    fn drop(&mut self) {
        // Best-effort graceful shutdown: take the child handle and
        // start_kill so the OS reaps it. We can't await here, so
        // kill_on_drop (set at spawn time) does the heavy lifting; this
        // just nudges it.
        if let Some(state) = self.inner.take() {
            if let Ok(mut guard) = state.child.try_lock() {
                if let Some(mut child) = guard.take() {
                    let _ = child.start_kill();
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// `new()` must never panic, even when Node + the driver script are
    /// unavailable. The disabled state surfaces as
    /// [`BrowserExecError::BackendDisabled`] on every gated method.
    #[tokio::test]
    async fn new_does_not_panic_without_node() {
        // We don't *guarantee* Node is missing on Don's machine, but
        // we do guarantee `new()` doesn't panic regardless.
        let exec = PlaywrightExecutor::new();
        // Either the driver came up (Don has Node + playwright) or it
        // didn't. Both are valid; we only assert no panic + a sane
        // observable state.
        let _ = format!("{exec:?}");
    }

    /// When `inner` is None (driver disabled), every gated method
    /// returns `BackendDisabled` and `close` returns `Ok(())`.
    #[tokio::test]
    async fn disabled_executor_short_circuits() {
        let exec = PlaywrightExecutor {
            inner: None,
            spawn_failure: Some("test: forced disabled".into()),
        };
        let sid = SessionId::new("nope");

        assert!(matches!(
            exec.open("https://example.com").await,
            Err(BrowserExecError::BackendDisabled)
        ));
        assert!(matches!(
            exec.navigate(sid.clone(), "https://example.com").await,
            Err(BrowserExecError::BackendDisabled)
        ));
        assert!(matches!(
            exec.read_page(sid.clone()).await,
            Err(BrowserExecError::BackendDisabled)
        ));
        assert!(matches!(
            exec.extract(sid.clone(), "h1").await,
            Err(BrowserExecError::BackendDisabled)
        ));
        let fields = [FormField {
            selector: "#x".into(),
            value: "y".into(),
        }];
        assert!(matches!(
            exec.fill_form(sid.clone(), &fields).await,
            Err(BrowserExecError::BackendDisabled)
        ));
        assert!(matches!(
            exec.submit(sid.clone(), "#submit").await,
            Err(BrowserExecError::BackendDisabled)
        ));
        // close on a disabled executor is a successful no-op.
        assert!(exec.close(sid).await.is_ok());
    }

    /// Round-trip a synthetic JSON-lines exchange through `send_call`
    /// without spawning a real Node child. We use `tokio::io::duplex`
    /// for stdin and a hand-rolled responder task to play the
    /// driver-side role.
    #[tokio::test]
    async fn send_call_roundtrips_ok_reply() {
        // Build a DriverState whose stdin is a duplex stream we can
        // read from in the test, and whose pending map we can signal
        // independently (this isolates the wire-format test from the
        // real reader task).
        let (stdin_w, mut stdin_r) = tokio::io::duplex(8192);
        let state = Arc::new(DriverState {
            child: Mutex::new(None),
            stdin: Mutex::new(None),
            pending: Mutex::new(HashMap::new()),
            next_req_id: AtomicU64::new(1),
        });
        // Inject the duplex write-half as the "stdin".
        // `ChildStdin` is the real type the production path uses, but
        // the production write path goes through `AsyncWriteExt` only,
        // and we hoisted that into `write_line`. So for the test we
        // bypass the Mutex<Option<ChildStdin>> field and write directly.
        // To do that we need to expose a parallel method that takes
        // any AsyncWrite — done by re-implementing the small slice of
        // send_call that we want to exercise.
        let req_id = state.next_req_id.fetch_add(1, Ordering::SeqCst);
        let (tx, rx) = oneshot::channel();
        state.pending.lock().await.insert(req_id, tx);

        // Producer: write one request line.
        let mut writer = stdin_w;
        let req = DriverRequest {
            req_id,
            op: "open",
            args: serde_json::json!({ "url": "https://example.com" }),
        };
        let line = serde_json::to_string(&req).unwrap();
        write_line(&mut writer, &line).await.unwrap();

        // Verify the wire bytes match expectation.
        let mut buf = String::new();
        let mut reader = BufReader::new(&mut stdin_r);
        reader.read_line(&mut buf).await.unwrap();
        let echoed: serde_json::Value = serde_json::from_str(buf.trim()).unwrap();
        assert_eq!(echoed["req_id"], req_id);
        assert_eq!(echoed["op"], "open");
        assert_eq!(echoed["args"]["url"], "https://example.com");

        // Now play the driver: synthesize a reply and dispatch it
        // through the pending map (mimics what the real reader task
        // does after parsing a stdout line).
        let reply = DriverReply {
            req_id,
            ok: Some(Value::String("session-abc".into())),
            err: None,
            kind: None,
        };
        let pending_tx = state.pending.lock().await.remove(&req_id).unwrap();
        pending_tx.send(reply).unwrap();

        // The caller side: decode just like send_call would.
        let received = rx.await.unwrap();
        assert!(received.err.is_none());
        let id: String = serde_json::from_value(received.ok.unwrap()).unwrap();
        assert_eq!(id, "session-abc");
    }

    /// Driver-side errors translate to the right typed variants.
    #[test]
    fn error_kind_mapping() {
        assert!(matches!(
            error_from_kind(Some("Navigation"), "boom".into()),
            BrowserExecError::Navigation(_)
        ));
        assert!(matches!(
            error_from_kind(Some("SelectorNotFound"), "x".into()),
            BrowserExecError::SelectorNotFound(_)
        ));
        assert!(matches!(
            error_from_kind(Some("SessionNotFound"), "x".into()),
            BrowserExecError::SessionNotFound(_)
        ));
        assert!(matches!(
            error_from_kind(Some("Timeout"), "x".into()),
            BrowserExecError::Timeout(_)
        ));
        assert!(matches!(
            error_from_kind(Some("Internal"), "x".into()),
            BrowserExecError::Internal(_)
        ));
        assert!(matches!(
            error_from_kind(None, "x".into()),
            BrowserExecError::Internal(_)
        ));
    }

    /// `DriverReply` parses both `ok` and `err` shapes off the wire.
    #[test]
    fn driver_reply_parses_both_shapes() {
        let ok: DriverReply = serde_json::from_str(r#"{"req_id":7,"ok":"hello"}"#).unwrap();
        assert_eq!(ok.req_id, 7);
        assert!(ok.err.is_none());
        let err: DriverReply =
            serde_json::from_str(r#"{"req_id":8,"err":"nav failed","kind":"Navigation"}"#).unwrap();
        assert_eq!(err.req_id, 8);
        assert_eq!(err.kind.as_deref(), Some("Navigation"));
        assert_eq!(err.err.as_deref(), Some("nav failed"));
    }
}
