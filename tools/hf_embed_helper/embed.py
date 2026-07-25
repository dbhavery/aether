#!/usr/bin/env python3
"""Persistent stdin/stdout helper for HuggingFace sentence-transformers
embeddings.

Used by `packages/l2-memory/src/hf_provider.rs::HfEmbeddingProvider` to
embed text via the `sentence-transformers` library without paying
process-startup cost on every embed call. Loaded once per provider
instance, then cached in-memory for the lifetime of the helper.

# Wire protocol

Single-line JSON over stdin → single-line JSON over stdout. One request
per line; one response per line; both ASCII-safe (no embedded newlines
in the payload — the model id and text are placed in JSON strings, so
sentence-transformers' newline handling is unaffected).

## Request shape

```json
{"op": "embed", "model": "BAAI/bge-small-en-v1.5", "text": "hello world"}
```

The model id is included on every request so the helper can lazy-load
new models on demand. In typical use a single provider instance will
embed many texts against one model; the model is loaded on first
request and cached in `_models[model_id]` thereafter.

## Response shape

Success:
```json
{"ok": true, "vector": [0.123, ...], "dim": 384}
```

Failure:
```json
{"ok": false, "error": "transport: ConnectionError ...", "kind": "load|embed|protocol"}
```

The `kind` field lets the Rust caller distinguish between recoverable
errors (model load failed — could retry with a different model) and
transport / protocol errors (helper is broken — fail loudly).

## Lifecycle

The helper exits cleanly on EOF (stdin closed by the parent) with code
0. Any unhandled exception during request loop is logged to stderr and
the helper continues to serve subsequent requests; only protocol-level
catastrophes (stdin/stdout broken) cause exit.

## Heavy-usage cost

First request for a given model:
- `bge-small-en-v1.5`: ~130 MB download to `~/.cache/huggingface/hub/`
  on first use, then ~5-15 s wall-clock to load the model into RAM.
- Subsequent requests: <50 ms per single-text embed on CPU.

Subsequent requests against an already-loaded model: <100 ms typical.

# Why a persistent helper instead of `python -c`-per-request

`python -c` startup + sentence-transformers import + model load is
~10 seconds *per call*. A 1000-row backfill would take 2-3 hours
instead of 2-3 minutes. The helper amortises both costs across all
requests in its lifetime.

# Why subprocess instead of native Rust (candle)

`candle-transformers` would give in-process embeddings with no Python
dependency, but pulls a large dependency tree (~50 crates including
CUDA bindings) and needs custom BERT pipeline code per model family.
The subprocess + sentence-transformers path matches existing repo
infrastructure (`tools/evals/` and its bench scripts) and lets
`bge-small-en-v1.5` work today. A native-Rust follow-up is captured
in the decisions log (D-012) as deferred work.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any


_MODELS: dict[str, Any] = {}
_RERANKERS: dict[str, Any] = {}


def _log(msg: str) -> None:
    """Log to stderr (stdout is reserved for protocol responses)."""
    print(f"[hf_embed_helper] {msg}", file=sys.stderr, flush=True)


def _load_model(model_id: str) -> Any:
    """Lazily load and cache a SentenceTransformer model.

    Raises if `sentence_transformers` is not installed or the model id
    cannot be resolved (no network, bad name, etc). The caller is
    expected to surface this as a `kind=load` error.
    """
    if model_id in _MODELS:
        return _MODELS[model_id]

    # Defer the import so a healthy stdin EOF still exits cleanly even
    # if the user does not have sentence-transformers installed.
    from sentence_transformers import SentenceTransformer

    _log(f"loading model {model_id} (first request)")
    model = SentenceTransformer(model_id)
    _MODELS[model_id] = model
    _log(f"model {model_id} loaded")
    return model


def _load_reranker(model_id: str) -> Any:
    """Lazily load and cache a CrossEncoder re-ranker model.

    Used for ADR-0010 Option B (cross-encoder re-rank pass on top-N
    candidates). Held in a separate cache from `_MODELS` so a single
    helper instance can serve both embed and rerank ops without one
    op's model id colliding with the other's. The caller is expected
    to surface load failures as `kind=load`.
    """
    if model_id in _RERANKERS:
        return _RERANKERS[model_id]

    from sentence_transformers import CrossEncoder

    _log(f"loading reranker {model_id} (first request)")
    model = CrossEncoder(model_id)
    _RERANKERS[model_id] = model
    _log(f"reranker {model_id} loaded")
    return model


def _embed(model_id: str, text: str) -> list[float]:
    """Embed `text` via the cached SentenceTransformer."""
    model = _load_model(model_id)
    # `convert_to_numpy=True` returns a numpy.ndarray; we tolist() to
    # produce a JSON-serialisable list[float].
    vector = model.encode(text, convert_to_numpy=True, normalize_embeddings=False)
    return [float(x) for x in vector.tolist()]


def _rerank(model_id: str, query: str, candidates: list[str]) -> list[float]:
    """Score every (query, candidate) pair via the cached CrossEncoder.

    Returns one float per candidate, in input order. Higher = more
    relevant. Scores are raw model outputs (not normalised); callers
    sort descending. Empty `candidates` returns `[]` without loading
    the model.
    """
    if not candidates:
        return []
    model = _load_reranker(model_id)
    pairs = [(query, c) for c in candidates]
    scores = model.predict(pairs, convert_to_numpy=True)
    return [float(x) for x in scores.tolist()]


def _handle(req: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one request dict to a response dict.

    Never raises — converts exceptions into structured error payloads
    so the caller never sees a partial line on stdout.
    """
    op = req.get("op")
    if op == "embed":
        model_id = req.get("model")
        text = req.get("text")
        if not isinstance(model_id, str) or not model_id:
            return {"ok": False, "error": "missing or empty `model`", "kind": "protocol"}
        if not isinstance(text, str):
            return {"ok": False, "error": "missing `text`", "kind": "protocol"}

        try:
            vector = _embed(model_id, text)
        except ImportError as e:
            return {
                "ok": False,
                "error": f"sentence-transformers not installed: {e}",
                "kind": "load",
            }
        except Exception as e:
            # Distinguish load failures (model id wrong, no network on first
            # download) from embed failures (rare — empty input handled below).
            is_load = model_id not in _MODELS
            return {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "kind": "load" if is_load else "embed",
            }

        return {"ok": True, "vector": vector, "dim": len(vector)}

    if op == "rerank":
        # ADR-0010 Option B — cross-encoder re-rank pass. Returns one
        # score per candidate in input order; caller sorts descending.
        model_id = req.get("model")
        query = req.get("query")
        candidates = req.get("candidates")
        if not isinstance(model_id, str) or not model_id:
            return {"ok": False, "error": "missing or empty `model`", "kind": "protocol"}
        if not isinstance(query, str):
            return {"ok": False, "error": "missing `query`", "kind": "protocol"}
        if not isinstance(candidates, list) or not all(isinstance(c, str) for c in candidates):
            return {
                "ok": False,
                "error": "missing or non-string `candidates`",
                "kind": "protocol",
            }

        try:
            scores = _rerank(model_id, query, candidates)
        except ImportError as e:
            return {
                "ok": False,
                "error": f"sentence-transformers not installed: {e}",
                "kind": "load",
            }
        except Exception as e:
            is_load = model_id not in _RERANKERS
            return {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "kind": "load" if is_load else "embed",
            }

        return {"ok": True, "scores": scores}

    return {
        "ok": False,
        "error": f"unsupported op: {op!r}",
        "kind": "protocol",
    }


def main() -> int:
    """Read newline-delimited JSON requests, emit newline-delimited
    JSON responses. Exit 0 on clean EOF.
    """
    _log("ready")
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            response = {
                "ok": False,
                "error": f"invalid JSON: {e}",
                "kind": "protocol",
            }
        else:
            try:
                response = _handle(req)
            except Exception as e:
                _log(f"unhandled error: {e}\n{traceback.format_exc()}")
                response = {
                    "ok": False,
                    "error": f"unhandled: {type(e).__name__}: {e}",
                    "kind": "protocol",
                }

        sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
        sys.stdout.flush()

    _log("eof; exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
