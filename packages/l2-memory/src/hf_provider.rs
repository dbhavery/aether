//! HuggingFace embedding provider, backed by a persistent Python
//! helper (`tools/hf_embed_helper/embed.py`).
//!
//! ## Why this exists
//!
//! ADR-0007 D7 named `bge-small-en-v1.5` as the Spark-tier embedding
//! default. The 2026-04-25 decisions log (D-001) recorded
//! the substitution to `nomic-embed-text` because the HF model couldn't
//! be loaded at the time. This provider closes that gap: with the
//! helper installed, `bge-small-en-v1.5` becomes a real provider option
//! again, and the substitution becomes optional rather than forced.
//!
//! ## Architecture
//!
//! - **Path X (chosen, this impl):** subprocess to a persistent Python
//!   helper that holds a `sentence_transformers` model in RAM and
//!   speaks newline-delimited JSON over stdin/stdout. Process startup
//!   cost (~10 s for the helper, ~5-15 s extra on the first model load)
//!   is paid ONCE per provider instance, then amortised across all
//!   subsequent embed calls.
//! - **Path Y (deferred):** native Rust via `candle-core` /
//!   `candle-transformers`. Tracked in DECISIONS_LOG D-012 as a
//!   follow-up ADR.
//!
//! ## Provider config string
//!
//! Two accepted forms in `memory.json::embeddings.provider`:
//! - `hf:BAAI/bge-small-en-v1.5` — canonical HuggingFace `org/repo`
//!   form. Preferred; matches the HF Hub URL shape.
//! - `hf:BAAI:bge-small-en-v1.5` — legacy three-segment form. Parsed
//!   for backward compatibility with the warn-only swap that shipped
//!   in `state.rs::swap_embedding_provider_for_config` before this
//!   provider landed; rewritten to the canonical form internally.
//!
//! ## Env vars
//!
//! - `AETHER_HF_HELPER_PYTHON` — Python interpreter to spawn (default
//!   `python`). Set this to point at a venv that has
//!   `sentence-transformers` installed if the system Python doesn't.
//! - `AETHER_HF_HELPER_SCRIPT` — path to `embed.py` (default resolves
//!   to `tools/hf_embed_helper/embed.py` relative to the current
//!   working directory; tests can override with an absolute path).
//!
//! ## Concurrency
//!
//! `embed()` is `&self` per the `EmbeddingProvider` trait but the
//! helper subprocess is single-stream (request → response → next
//! request). A `Mutex<HelperProcess>` serialises calls; embedding is
//! CPU-bound on the helper side anyway, so adding parallelism here
//! would just oversubscribe the helper's cores. Tests confirm a single
//! provider survives concurrent embed calls without protocol
//! corruption.
//!
//! ## Failure modes
//!
//! - Helper script missing → `L2Error::Embedding` with explicit path,
//!   surfaced at first `embed()` call (lazy spawn).
//! - Python interpreter missing → spawn error surfaced same way.
//! - `sentence-transformers` not installed → helper returns
//!   `kind=load`; we surface as `L2Error::Embedding` with the install
//!   instruction.
//! - Helper crash mid-conversation → next `embed()` call respawns the
//!   helper. The cached model will need to reload, paying first-load
//!   cost again.

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Mutex;

use serde::Deserialize;

use crate::embeddings::EmbeddingProvider;
use crate::error::L2Error;

/// Default Python interpreter command if `AETHER_HF_HELPER_PYTHON`
/// isn't set. `python` (not `python3`) because Windows ships `python`
/// only; on Linux/macOS `python` is conventionally a symlink or alias
/// at any sane Python install — the helper is for users who chose to
/// install `sentence-transformers`, who already have Python set up.
pub const DEFAULT_HF_HELPER_PYTHON: &str = "python";

/// Default helper script path relative to the repo root.
pub const DEFAULT_HF_HELPER_SCRIPT: &str = "tools/hf_embed_helper/embed.py";

/// Env var: override the Python interpreter the helper subprocess
/// uses. Set to a venv binary if `sentence-transformers` lives there.
pub const ENV_HF_HELPER_PYTHON: &str = "AETHER_HF_HELPER_PYTHON";

/// Env var: override the helper script path.
pub const ENV_HF_HELPER_SCRIPT: &str = "AETHER_HF_HELPER_SCRIPT";

/// HuggingFace embedding provider via persistent Python helper.
///
/// The helper subprocess is spawned lazily on first `embed()` call —
/// constructing the provider does NOT require the helper to be
/// installed; only using it does. This matches the rest of the
/// embedding surface (Ollama provider doesn't connect at construction
/// either).
pub struct HfEmbeddingProvider {
    model: String,
    python: String,
    script: String,
    helper: Mutex<Option<HelperProcess>>,
}

struct HelperProcess {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

#[derive(Debug, Deserialize)]
struct HelperResponse {
    ok: bool,
    #[serde(default)]
    vector: Option<Vec<f32>>,
    #[serde(default)]
    error: Option<String>,
    #[serde(default)]
    kind: Option<String>,
}

impl HfEmbeddingProvider {
    /// Build with explicit model id. Accepts the canonical
    /// `BAAI/bge-small-en-v1.5` form; if you have the legacy
    /// three-segment string from `memory.json`, normalise via
    /// [`Self::normalise_model_id`] first.
    ///
    /// Python interpreter and script path resolve from env vars, with
    /// fallbacks to [`DEFAULT_HF_HELPER_PYTHON`] and
    /// [`DEFAULT_HF_HELPER_SCRIPT`].
    pub fn new(model: impl Into<String>) -> Self {
        let python =
            std::env::var(ENV_HF_HELPER_PYTHON).unwrap_or_else(|_| DEFAULT_HF_HELPER_PYTHON.into());
        let script =
            std::env::var(ENV_HF_HELPER_SCRIPT).unwrap_or_else(|_| DEFAULT_HF_HELPER_SCRIPT.into());
        Self::with_helper(model, python, script)
    }

    /// Build with explicit helper paths. Used by tests to avoid
    /// mutating process-wide env vars (which would race with parallel
    /// tests). Production code should prefer [`Self::new`].
    pub fn with_helper(
        model: impl Into<String>,
        python: impl Into<String>,
        script: impl Into<String>,
    ) -> Self {
        Self {
            model: model.into(),
            python: python.into(),
            script: script.into(),
            helper: Mutex::new(None),
        }
    }

    /// Normalise the legacy `org:repo:tag` form to canonical
    /// `org/repo` (or `org/repo-tag`) so HuggingFace recognises it.
    /// Pure function so callers can probe without spawning anything.
    ///
    /// Examples:
    /// - `"BAAI/bge-small-en-v1.5"` → `"BAAI/bge-small-en-v1.5"` (no
    ///   change).
    /// - `"BAAI:bge-small-en-v1.5"` → `"BAAI/bge-small-en-v1.5"`.
    /// - `"BAAI:bge:small-en-v1.5"` → `"BAAI/bge-small-en-v1.5"`
    ///   (joins remaining segments with `-`, matching the
    ///   `org/repo-tag` HF convention).
    pub fn normalise_model_id(raw: &str) -> String {
        if raw.contains('/') {
            return raw.to_string();
        }
        let parts: Vec<&str> = raw.splitn(2, ':').collect();
        match parts.as_slice() {
            [org, rest] => {
                // Any further `:` separators in `rest` collapse to `-`,
                // matching `bge-small-en-v1.5` shape.
                let rest_norm = rest.replace(':', "-");
                format!("{org}/{rest_norm}")
            }
            _ => raw.to_string(),
        }
    }

    /// Spawn the helper subprocess. Returns the live handles; the
    /// caller stashes them in `self.helper`.
    fn spawn(&self) -> Result<HelperProcess, L2Error> {
        let mut child = Command::new(&self.python)
            .arg(&self.script)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|e| {
                L2Error::Embedding(format!(
                    "spawn hf helper failed: python={} script={}: {e} \
                     (set {ENV_HF_HELPER_PYTHON} / {ENV_HF_HELPER_SCRIPT} to override)",
                    self.python, self.script,
                ))
            })?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| L2Error::Embedding("hf helper child stdin not captured".to_string()))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| L2Error::Embedding("hf helper child stdout not captured".to_string()))?;

        Ok(HelperProcess {
            child,
            stdin,
            stdout: BufReader::new(stdout),
        })
    }
}

impl EmbeddingProvider for HfEmbeddingProvider {
    fn embed_raw(&self, text: &str) -> Result<Vec<f32>, L2Error> {
        let mut guard = self
            .helper
            .lock()
            .map_err(|e| L2Error::Internal(format!("hf helper lock poisoned: {e}")))?;

        // Lazy spawn / respawn after a previous crash.
        if guard.is_none() {
            *guard = Some(self.spawn()?);
        }
        let helper = guard.as_mut().expect("helper must be Some after spawn");

        let request = serde_json::json!({
            "op": "embed",
            "model": self.model,
            "text": text,
        })
        .to_string();

        // Write request + newline. If write fails, drop the helper so
        // the next call respawns; surface the error.
        let write_result = (|| -> std::io::Result<()> {
            helper.stdin.write_all(request.as_bytes())?;
            helper.stdin.write_all(b"\n")?;
            helper.stdin.flush()
        })();
        if let Err(e) = write_result {
            *guard = None;
            return Err(L2Error::Embedding(format!(
                "hf helper write failed (helper will respawn next call): {e}"
            )));
        }

        // Read one line response. EOF before newline means helper died.
        let mut line = String::new();
        match helper.stdout.read_line(&mut line) {
            Ok(0) => {
                *guard = None;
                return Err(L2Error::Embedding(
                    "hf helper closed stdout before responding (likely crashed)".to_string(),
                ));
            }
            Ok(_) => {}
            Err(e) => {
                *guard = None;
                return Err(L2Error::Embedding(format!("hf helper read failed: {e}")));
            }
        }

        let response: HelperResponse = serde_json::from_str(line.trim()).map_err(|e| {
            L2Error::Embedding(format!(
                "hf helper produced unparseable response: {e}; raw={line:?}"
            ))
        })?;

        if !response.ok {
            let kind = response.kind.as_deref().unwrap_or("unknown");
            let error = response
                .error
                .unwrap_or_else(|| "(no error message)".into());
            return Err(L2Error::Embedding(format!(
                "hf helper error ({kind}): {error}"
            )));
        }

        let vector = response.vector.ok_or_else(|| {
            L2Error::Embedding("hf helper ok=true but no vector field".to_string())
        })?;

        if vector.is_empty() {
            return Err(L2Error::Embedding(
                "hf helper returned empty vector".to_string(),
            ));
        }

        Ok(vector)
    }

    fn label(&self) -> String {
        format!("hf:{}", self.model)
    }
}

impl Drop for HfEmbeddingProvider {
    /// Best-effort: close stdin (helper exits on EOF), then wait
    /// briefly for the child to exit. We do NOT block forever — a
    /// stuck helper shouldn't pin shutdown. `kill` on timeout would
    /// require an async runtime; we trust EOF + the OS to clean up
    /// the child if it's wedged.
    fn drop(&mut self) {
        if let Ok(mut guard) = self.helper.lock() {
            if let Some(mut helper) = guard.take() {
                // Closing stdin tells the helper to exit cleanly.
                drop(helper.stdin);
                // try_wait avoids blocking on a wedged helper.
                let _ = helper.child.try_wait();
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn label_includes_model_id() {
        let p = HfEmbeddingProvider::new("BAAI/bge-small-en-v1.5");
        assert_eq!(p.label(), "hf:BAAI/bge-small-en-v1.5");
    }

    #[test]
    fn normalise_passes_canonical_form_through() {
        assert_eq!(
            HfEmbeddingProvider::normalise_model_id("BAAI/bge-small-en-v1.5"),
            "BAAI/bge-small-en-v1.5"
        );
    }

    #[test]
    fn normalise_legacy_two_segment_form() {
        assert_eq!(
            HfEmbeddingProvider::normalise_model_id("BAAI:bge-small-en-v1.5"),
            "BAAI/bge-small-en-v1.5"
        );
    }

    #[test]
    fn normalise_legacy_three_segment_form_collapses_to_dashes() {
        assert_eq!(
            HfEmbeddingProvider::normalise_model_id("BAAI:bge:small-en-v1.5"),
            "BAAI/bge-small-en-v1.5"
        );
    }

    #[test]
    fn normalise_handles_empty_and_single_segment() {
        // Single segment with no separator is left alone — the helper
        // will reject it and surface a clear error.
        assert_eq!(HfEmbeddingProvider::normalise_model_id("foo"), "foo");
        assert_eq!(HfEmbeddingProvider::normalise_model_id(""), "");
    }

    #[test]
    fn embed_with_missing_python_returns_clear_error() {
        // Use the explicit `with_helper` constructor to avoid touching
        // process-wide env vars (which would race with other tests).
        let p = HfEmbeddingProvider::with_helper(
            "BAAI/bge-small-en-v1.5",
            "definitely-not-a-real-python-binary-xyzzy",
            "definitely-not-a-real-script.py",
        );
        let err = p.embed("hello").unwrap_err();
        match err {
            L2Error::Embedding(msg) => {
                assert!(
                    msg.contains("spawn hf helper failed"),
                    "expected spawn error message, got: {msg}"
                );
                assert!(
                    msg.contains(ENV_HF_HELPER_PYTHON),
                    "error should mention the env var override path"
                );
            }
            other => panic!("expected Embedding error, got {other:?}"),
        }
    }

    #[test]
    fn embed_against_live_helper_returns_expected_dim() {
        // Smoke test against the real Python helper + sentence-transformers.
        // Env-gated: skipped unless AETHER_HF_TEST=1, because the model
        // download is ~130 MB and the test is slow on first run.
        if std::env::var("AETHER_HF_TEST").ok().as_deref() != Some("1") {
            eprintln!("AETHER_HF_TEST!=1; skipping live HF helper smoke test");
            return;
        }
        // Use a workspace-relative script path. CWD when cargo tests
        // run a package crate is the package directory, so reach back
        // up to the repo root.
        let script = "../../tools/hf_embed_helper/embed.py";
        let p = HfEmbeddingProvider::with_helper(
            "BAAI/bge-small-en-v1.5",
            DEFAULT_HF_HELPER_PYTHON,
            script,
        );
        let v = p.embed("hello world").expect("embed must succeed");
        assert_eq!(v.len(), 384, "bge-small-en-v1.5 emits 384-dim vectors");
    }
}
