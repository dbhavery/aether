"""RAG knowledge base — local ChromaDB + on-device embeddings.

Ingests a folder of a company's markdown docs (FAQs, policies), splits them
into overlapping chunks, embeds them with a small CPU embedding model, and
persists them in a per-company ChromaDB collection. Retrieval returns grounded
context chunks with their source filenames so the assistant can cite them.

Embeddings
----------
Uses ChromaDB's built-in :class:`DefaultEmbeddingFunction` — an ONNX build of
``all-MiniLM-L6-v2`` that runs on CPU and needs no API key. The model is
downloaded once on first use and cached locally by ChromaDB. This keeps the
demo self-contained: retrieval works even when Ollama is not running.

(The main Aether memory layer embeds via Ollama ``nomic-embed-text``; we
deliberately use the bundled MiniLM here so the customer-assistant demo has
zero hard dependency on a running Ollama for the *retrieval* path.)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions

from customer_assistant.config import CompanyProfile

logger = logging.getLogger(__name__)

# Where persistent Chroma collections live by default (per company root).
_DEFAULT_PERSIST_SUBDIR = ".chroma"


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """One retrieved context chunk plus provenance for citation."""

    text: str
    source: str  # source filename, e.g. "returns-policy.md"
    chunk_index: int
    distance: float  # cosine distance (lower = more similar)


def _split_markdown(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks on paragraph boundaries.

    Greedy pack of paragraphs up to ``chunk_size`` characters, then carry an
    ``overlap``-sized tail into the next chunk so context isn't cut mid-thought.
    Paragraphs larger than ``chunk_size`` are hard-split.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    def _flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for para in paragraphs:
        if len(para) > chunk_size:
            _flush()
            for i in range(0, len(para), chunk_size - overlap):
                chunks.append(para[i : i + chunk_size].strip())
            continue
        if len(current) + len(para) + 2 > chunk_size:
            tail = current[-overlap:] if overlap and current else ""
            _flush()
            current = (tail + "\n\n" + para).strip() if tail else para
        else:
            current = f"{current}\n\n{para}".strip() if current else para
    _flush()
    return [c for c in chunks if c]


class KnowledgeBase:
    """Per-company persistent vector store over the company's docs folder."""

    def __init__(self, profile: CompanyProfile, *, persist_dir: Path | None = None) -> None:
        self._profile = profile
        if persist_dir is not None:
            self._persist_dir = Path(persist_dir).resolve()
        else:
            base = profile.base_dir or Path.cwd()
            self._persist_dir = (base / _DEFAULT_PERSIST_SUBDIR).resolve()
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(self._persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        # CPU ONNX MiniLM — no API key, downloaded + cached on first use.
        self._embed_fn = embedding_functions.DefaultEmbeddingFunction()
        self._collection = self._client.get_or_create_collection(
            name=profile.collection_name,
            embedding_function=self._embed_fn,
            metadata={"hnsw:space": "cosine", "company_id": profile.company.id},
        )

    @property
    def collection_name(self) -> str:
        return self._profile.collection_name

    def count(self) -> int:
        """Number of chunks currently indexed."""
        return self._collection.count()

    def ingest(self, *, reset: bool = True) -> int:
        """Ingest the company's knowledge folder.

        Args:
            reset: when True (default) the collection is rebuilt from scratch so
                stale chunks from removed/edited docs don't linger.

        Returns:
            Number of chunks indexed.

        Raises:
            FileNotFoundError: if the knowledge folder does not exist.
        """
        kb_dir = self._profile.knowledge_dir()
        if not kb_dir.is_dir():
            raise FileNotFoundError(f"knowledge folder not found: {kb_dir}")

        if reset:
            # Recreate the collection to drop any previous content.
            self._client.delete_collection(self._profile.collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self._profile.collection_name,
                embedding_function=self._embed_fn,
                metadata={"hnsw:space": "cosine", "company_id": self._profile.company.id},
            )

        docs = sorted(kb_dir.rglob("*.md"))
        if not docs:
            logger.warning("no .md files found under %s", kb_dir)
            return 0

        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, str | int]] = []

        for doc in docs:
            source = doc.relative_to(kb_dir).as_posix()
            content = doc.read_text(encoding="utf-8")
            chunks = _split_markdown(
                content,
                chunk_size=self._profile.knowledge_base.chunk_size,
                overlap=self._profile.knowledge_base.chunk_overlap,
            )
            for idx, chunk in enumerate(chunks):
                ids.append(f"{source}::{idx}")
                texts.append(chunk)
                metadatas.append({"source": source, "chunk_index": idx})

        if not texts:
            logger.warning("no chunks produced from %d docs under %s", len(docs), kb_dir)
            return 0

        # Batch add; ChromaDB computes embeddings via the collection's embed fn.
        self._collection.add(ids=ids, documents=texts, metadatas=metadatas)
        logger.info(
            "ingested %d chunks from %d docs into collection %r",
            len(texts),
            len(docs),
            self._profile.collection_name,
        )
        return len(texts)

    def retrieve(self, query: str, *, top_k: int = 4) -> list[RetrievedChunk]:
        """Return the ``top_k`` most relevant chunks for ``query``."""
        if not query.strip():
            return []
        n = self._collection.count()
        if n == 0:
            return []
        result = self._collection.query(
            query_texts=[query],
            n_results=min(top_k, n),
            include=["documents", "metadatas", "distances"],
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        chunks: list[RetrievedChunk] = []
        for text, meta, dist in zip(documents, metadatas, distances, strict=False):
            meta = meta or {}
            chunks.append(
                RetrievedChunk(
                    text=text,
                    source=str(meta.get("source", "unknown")),
                    chunk_index=int(meta.get("chunk_index", 0)),
                    distance=float(dist),
                )
            )
        return chunks
