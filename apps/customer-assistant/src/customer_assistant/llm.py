"""Minimal Ollama chat client with graceful degradation.

Mirrors Aether's default LLM dispatch (provider ``ollama``, local models from
``configs/default_config.yaml`` ``llm.tier_map``) but kept deliberately small:
a single non-streaming ``chat`` call over Ollama's HTTP ``/api/chat`` endpoint
using ``httpx`` (already an Aether dependency). No litellm, no API keys.

If Ollama is unreachable or the model is missing, :class:`OllamaClient.chat`
raises :class:`OllamaUnavailable`; the assistant core catches this and returns
a clear, grounded stub answer so the demo still loads and responds.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# Ollama default base URL; override with OLLAMA_HOST (matches Ollama's own env).
DEFAULT_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


class OllamaUnavailable(RuntimeError):
    """Raised when Ollama cannot be reached or the model is not available."""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One chat message in the Ollama messages array."""

    role: str  # "system" | "user" | "assistant"
    content: str


class OllamaClient:
    """Thin synchronous client over Ollama's /api/chat endpoint."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, *, timeout: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def is_up(self) -> bool:
        """Best-effort liveness check against Ollama's root endpoint."""
        try:
            resp = httpx.get(f"{self._base_url}/api/tags", timeout=3.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.3,
        max_tokens: int = 512,
    ) -> str:
        """Send a chat completion request and return the assistant's text.

        Raises:
            OllamaUnavailable: on connection errors, timeouts, missing model,
                or any non-2xx response. The message is human-readable.
        """
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        try:
            resp = httpx.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise OllamaUnavailable(
                f"Ollama timed out after {self._timeout}s calling model {model!r}"
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaUnavailable(
                f"could not reach Ollama at {self._base_url} ({exc}); "
                "is `ollama serve` running?"
            ) from exc

        if resp.status_code == 404:
            raise OllamaUnavailable(
                f"Ollama has no model named {model!r}. Pull it with: ollama pull {model}"
            )
        if resp.status_code >= 400:
            raise OllamaUnavailable(
                f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            data = resp.json()
            content = data["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise OllamaUnavailable(
                f"unexpected Ollama response shape: {exc}"
            ) from exc

        if not isinstance(content, str):
            raise OllamaUnavailable("Ollama response message.content was not a string")
        return content.strip()
