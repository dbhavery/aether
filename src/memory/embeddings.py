"""Local embeddings via Ollama nomic-embed-text. Zero API cost.

Model: nomic-embed-text — the model actually installed in Ollama.

Unavailability is cached for 60s so a stopped / unreachable Ollama does not spam
the log on every turn. First failure logs a WARNING with a human-readable note;
subsequent attempts within the window raise EmbeddingsUnavailable silently.
"""

import asyncio
import time

import aiohttp
from loguru import logger

from src.shared.config import get_settings, get_yaml_config
from src.shared.http_client import get_shared_session

# Default model — overridden by aether_config.yaml memory.embedding_model
_DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"

# Ollama-unavailable retry backoff (seconds). When embed_text fails we suppress
# subsequent errors for this long so callers (memory store, RAG, fact writes)
# don't each stamp an ERROR line into the log on every turn.
_UNAVAILABLE_BACKOFF_SECONDS = 60.0

_unavailable_until: float = 0.0
_unavailable_lock = asyncio.Lock()


class EmbeddingsUnavailable(RuntimeError):
    """Raised when the embeddings backend is known-unavailable (cached)."""


def _get_embedding_model() -> str:
    """Get the configured embedding model name."""
    yaml_config = get_yaml_config()
    return yaml_config.get("memory", {}).get("embedding_model", _DEFAULT_EMBEDDING_MODEL)


async def _mark_unavailable(reason: str) -> None:
    """Record that Ollama is unavailable; log once per backoff window."""
    global _unavailable_until
    async with _unavailable_lock:
        now = time.monotonic()
        if now >= _unavailable_until:
            logger.warning(
                f"Memory/Embeddings: Ollama unavailable ({reason}); "
                f"suppressing follow-up errors for {int(_UNAVAILABLE_BACKOFF_SECONDS)}s"
            )
        _unavailable_until = now + _UNAVAILABLE_BACKOFF_SECONDS


def _is_unavailable() -> bool:
    return time.monotonic() < _unavailable_until


async def embed_text(text: str) -> list[float]:
    """Get embeddings for text using local Ollama embedding model.

    Raises EmbeddingsUnavailable (a RuntimeError) when Ollama is known-down.
    Callers in the memory store already catch RuntimeError at DEBUG level.
    """
    if _is_unavailable():
        raise EmbeddingsUnavailable("embeddings backend in cooldown")

    settings = get_settings()
    model = _get_embedding_model()
    url = f"{settings.ollama_base_url}/api/embeddings"
    payload = {"model": model, "prompt": text}
    try:
        session = await get_shared_session()
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Ollama embeddings returned {resp.status}: {body}")
            data = await resp.json()
            return data["embedding"]
    except Exception as e:
        await _mark_unavailable(f"{type(e).__name__}: {e}")
        raise EmbeddingsUnavailable(str(e)) from e


async def ensure_embedding_model() -> bool:
    """Verify the configured embedding model is available in Ollama.

    Startup probe. On success the unavailability cache is cleared so the next
    embed_text() call attempts HTTP immediately instead of waiting the backoff.
    """
    global _unavailable_until
    settings = get_settings()
    model = _get_embedding_model()
    url = f"{settings.ollama_base_url}/api/tags"
    try:
        session = await get_shared_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            models = [m["name"] for m in data.get("models", [])]
            available = any(model in m for m in models)
            if available:
                async with _unavailable_lock:
                    _unavailable_until = 0.0
            else:
                logger.warning(f"Memory: {model} not found in Ollama — pull with: ollama pull {model}")
                await _mark_unavailable(f"model {model} not installed")
            return available
    except Exception as e:
        await _mark_unavailable(f"probe failed: {type(e).__name__}: {e}")
        return False
