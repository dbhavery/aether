"""Structural subtyping interfaces for pluggable backends.

These are Protocol classes (PEP 544) — any class that implements the required
methods satisfies the protocol without explicit inheritance. This allows swapping
implementations (e.g., different TTS engines) without touching caller code.
"""

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class LLMClient(Protocol):
    """Any LLM client that can generate text from messages."""

    async def generate(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 2048,
    ) -> str: ...


@runtime_checkable
class MemoryBackend(Protocol):
    """Any memory storage backend that can store and search."""

    async def store(self, text: str, metadata: dict | None = None) -> str:
        """Store text, return ID."""
        ...

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Search for similar content, return ranked results."""
        ...


@runtime_checkable
class TTSEngine(Protocol):
    """Any text-to-speech engine that produces audio."""

    async def synthesize(self, text: str) -> np.ndarray:
        """Convert text to audio waveform (numpy array)."""
        ...


@runtime_checkable
class STTEngine(Protocol):
    """Any speech-to-text engine that produces text from audio."""

    async def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str | None:
        """Convert audio to text. Returns None if transcription fails."""
        ...


@runtime_checkable
class EmbeddingModel(Protocol):
    """Any embedding model that converts text to vectors."""

    async def embed(self, text: str) -> list[float]:
        """Convert text to embedding vector."""
        ...
