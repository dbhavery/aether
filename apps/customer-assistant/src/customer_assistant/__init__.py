"""Customer Assistant — a per-company, fine-tunable AI support assistant.

Built on the Aether Companion concept: where a *persona* describes one character,
a *company profile* (``company.yaml``) describes one business's support voice,
scope, escalation rules, branding, and knowledge base.

This package is a self-contained local demo. It does NOT import the Rust
seven-layer core (``packages/l*``); it reuses the same conventions (typed
profiles compiled into a system prompt, Ollama-by-default LLM dispatch, local
ChromaDB retrieval) in a small Python service so the concept can be shown end
to end without a GPU.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
