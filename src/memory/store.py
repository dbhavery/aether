"""ChromaDB vector store — hybrid BM25 + dense search, persistent on Drive I:.

Supports:
- Hybrid search: BM25 keyword + dense vector similarity, fused ranking
- Context-aware search depth: simple → Tier 1+2, complex → full cascade
- Category filtering: search within hierarchical categories
- Transparency modes: natural recall (default) or structured dump
"""

import hashlib
import time
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger
from rank_bm25 import BM25Okapi

from src.memory.embeddings import embed_text
from src.shared.config import get_settings

_client: chromadb.ClientAPI | None = None
_conversations_collection = None
_knowledge_collection = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        settings = get_settings()
        chroma_path = Path(settings.chroma_path)
        chroma_path.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        logger.info(f"Memory: ChromaDB client initialized at {chroma_path}")
    return _client


def _get_conversations_collection():
    global _conversations_collection
    if _conversations_collection is None:
        client = _get_client()
        _conversations_collection = client.get_or_create_collection(
            name="aether_conversations",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Memory: conversations collection ready ({_conversations_collection.count()} docs)")
    return _conversations_collection


def _get_knowledge_collection():
    global _knowledge_collection
    if _knowledge_collection is None:
        client = _get_client()
        _knowledge_collection = client.get_or_create_collection(
            name="aether_knowledge",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Memory: knowledge collection ready ({_knowledge_collection.count()} docs)")
    return _knowledge_collection


async def store_conversation_turn(
    role: str,
    content: str,
    timestamp: float,
    conversation_id: str = "default",
) -> str:
    """Store a conversation turn with embedding. Returns the doc ID."""
    doc_id = hashlib.sha256(f"{role}:{content}:{timestamp}".encode()).hexdigest()
    embedding = await embed_text(content)
    collection = _get_conversations_collection()
    collection.upsert(
        ids=[doc_id],
        documents=[content],
        embeddings=[embedding],
        metadatas=[
            {
                "role": role,
                "timestamp": timestamp,
                "conversation_id": conversation_id,
            }
        ],
    )
    logger.debug(f"Memory: stored {role} turn (id={doc_id}, len={len(content)})")
    return doc_id


def _bm25_rerank(query: str, documents: list[str], top_k: int = 20) -> list[tuple[int, float]]:
    """BM25 keyword scoring for a list of documents.

    Returns list of (original_index, bm25_score) sorted by score descending.
    """
    if not documents:
        return []
    tokenized_corpus = [doc.lower().split() for doc in documents]
    bm25 = BM25Okapi(tokenized_corpus)
    query_tokens = query.lower().split()
    scores = bm25.get_scores(query_tokens)
    indexed_scores = [(i, float(scores[i])) for i in range(len(scores))]
    indexed_scores.sort(key=lambda x: x[1], reverse=True)
    return indexed_scores[:top_k]


def _fuse_scores(
    dense_results: list[dict],
    bm25_ranked: list[tuple[int, float]],
    dense_weight: float = 0.6,
    bm25_weight: float = 0.4,
) -> list[dict]:
    """Fuse dense vector scores with BM25 keyword scores using weighted combination."""
    if not dense_results:
        return []

    # Build BM25 score lookup
    bm25_max = max((s for _, s in bm25_ranked), default=1.0) or 1.0
    bm25_scores = {idx: score / bm25_max for idx, score in bm25_ranked}

    fused = []
    for i, result in enumerate(dense_results):
        dense_score = result.get("relevance", 0.0)
        bm25_score = bm25_scores.get(i, 0.0)
        fused_score = dense_weight * dense_score + bm25_weight * bm25_score
        fused.append({**result, "relevance": fused_score})

    fused.sort(key=lambda c: c["relevance"], reverse=True)
    return fused


async def search_memory(
    query: str,
    n_results: int = 5,
    category: str | None = None,
    deep: bool = False,
) -> list[dict]:
    """Hybrid search across conversations and knowledge with BM25 fusion.

    Args:
        query: Search text
        n_results: Max results to return
        category: Optional hierarchical category filter (e.g., "personal.preferences")
        deep: If True, also search Tier 3 archive (slower, for complex queries)
    """
    embedding = await embed_text(query)
    chunks = []

    # Fetch more candidates than needed for BM25 fusion
    fetch_n = min(n_results * 4, 20)

    # Search conversations
    conv_collection = _get_conversations_collection()
    conv_count = conv_collection.count()
    if conv_count > 0:
        actual_n = min(fetch_n, conv_count)
        results = conv_collection.query(
            query_embeddings=[embedding],
            n_results=actual_n,
            include=["documents", "metadatas", "distances"],
        )
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            # Category filter
            if category and not meta.get("category", "").startswith(category):
                continue
            chunks.append(
                {
                    "content": doc,
                    "metadata": meta,
                    "relevance": 1 - results["distances"][0][i],
                    "source": "conversations",
                }
            )

    # Search knowledge
    know_collection = _get_knowledge_collection()
    know_count = know_collection.count()
    if know_count > 0:
        actual_n = min(fetch_n, know_count)
        results = know_collection.query(
            query_embeddings=[embedding],
            n_results=actual_n,
            include=["documents", "metadatas", "distances"],
        )
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            if category and not meta.get("category", "").startswith(category):
                continue
            chunks.append(
                {
                    "content": doc,
                    "metadata": meta,
                    "relevance": 1 - results["distances"][0][i],
                    "source": "knowledge",
                }
            )

    # Apply BM25 fusion if we have enough results
    if len(chunks) >= 2:
        documents = [c["content"] for c in chunks]
        bm25_ranked = _bm25_rerank(query, documents, top_k=len(chunks))
        chunks = _fuse_scores(chunks, bm25_ranked)

    # Deep search: also check tier 3 archive
    if deep:
        try:
            from src.memory.tier_manager import get_tier_manager

            tier_mgr = get_tier_manager()
            archive_results = tier_mgr.tier3.search(query, max_results=n_results)
            for record in archive_results:
                if category:
                    rec_cat = record.get("metadata", {}).get("category", "")
                    if not rec_cat.startswith(category):
                        continue
                chunks.append(
                    {
                        "content": record.get("content", ""),
                        "metadata": record.get("metadata", {}),
                        "relevance": 0.3,  # Archive results get a base relevance
                        "source": "archive",
                    }
                )
        except Exception as e:
            logger.warning(f"Memory: deep search archive failed: {e}")

    # Sort by relevance, return top N
    chunks.sort(key=lambda c: c["relevance"], reverse=True)
    chunks = chunks[:n_results]
    logger.debug(f"Memory: search '{query[:40]}...' -> {len(chunks)} results (deep={deep})")
    return chunks


async def get_recent_turns(limit: int = 20) -> list[dict]:
    """Return the last `limit` conversation turns, oldest first (for LLM context).

    ChromaDB .get(limit=N) returns arbitrary documents, NOT the most recent N.
    We fetch a larger batch, sort by timestamp, and slice the last N.

    Each item: {"role": str, "content": str, "timestamp": float}
    """
    import time as _time

    collection = _get_conversations_collection()
    count = collection.count()
    if count == 0:
        return []

    # For small collections, fetch all. For large ones, use a timestamp
    # cutoff to avoid ChromaDB's .get(limit=N) returning arbitrary docs.
    if count <= 500:
        results = collection.get(
            include=["documents", "metadatas"],
        )
    else:
        # Fetch turns from the last 7 days to bound the result set
        cutoff = _time.time() - (7 * 86400)
        results = collection.get(
            include=["documents", "metadatas"],
            where={"timestamp": {"$gte": cutoff}},
        )

    if not results or not results.get("documents"):
        return []

    turns = []
    for doc, meta in zip(results["documents"], results["metadatas"], strict=False):
        turns.append(
            {
                "role": meta.get("role", "user"),
                "content": doc,
                "timestamp": meta.get("timestamp", 0),
            }
        )

    # Sort by timestamp ascending (oldest first)
    turns.sort(key=lambda t: t["timestamp"])

    # Take the N most recent turns
    recent = turns[-limit:] if len(turns) > limit else turns

    return [{"role": t["role"], "content": t["content"], "timestamp": t["timestamp"]} for t in recent]


async def store_fact(key: str, value: str, importance: float = 0.5) -> None:
    """Store a named fact about the user or the world."""
    embedding = await embed_text(f"{key}: {value}")
    collection = _get_knowledge_collection()
    collection.upsert(
        ids=[key],
        documents=[f"{key}: {value}"],
        embeddings=[embedding],
        metadatas=[{"key": key, "importance": importance, "stored_at": time.time()}],
    )
    logger.info(f"Memory: stored fact '{key}'")
