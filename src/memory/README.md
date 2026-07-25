# Module 08: Memory

Persistent vector storage, RAG retrieval, and conversation history for Aether.

## Responsibility

Stores every conversation turn and named fact in ChromaDB using dense vector embeddings
produced by a local Ollama nomic-embed-text model. Provides hybrid search across two
collections (conversations and knowledge) sorted by cosine relevance. Listens on the
EventBus to persist turns automatically as they happen, so Brain can retrieve context
on the next query without any explicit calls from the voice or text pipeline.

## Key Files

- `store.py` — core storage and retrieval: `store_conversation_turn()`,
  `search_memory()`, `get_recent_turns()`, `store_fact()`; manages two ChromaDB
  collections (`aether_conversations`, `aether_knowledge`) with lazy-initialized
  persistent client at `./data/chroma\`
- `embeddings.py` — `embed_text()`: HTTP call to Ollama `/api/embeddings` with
  `nomic-embed-text`; `ensure_embedding_model()` verifies model availability at startup
- `handler.py` — `register_memory_handlers()`: subscribes to `USER_MESSAGE` and
  `RESPONSE_TEXT_READY` events; auto-persists turns without caller involvement;
  skips interim/partial responses

## Interface Contract

Subscribes to:
- `USER_MESSAGE` — persists the user turn to `aether_conversations`
- `RESPONSE_TEXT_READY` — persists the assistant turn (non-interim only)

Exports:
- `store_conversation_turn(role, content, timestamp, conversation_id) -> str`
- `search_memory(query, n_results=5) -> list[dict]` — returns chunks with `content`,
  `metadata`, `relevance` (0-1), `source` ("conversations" or "knowledge")
- `get_recent_turns(limit=20) -> list[dict]` — returns `{"role", "content"}` ordered
  oldest-first for LLM context injection
- `store_fact(key, value, importance) -> None`
- `register_memory_handlers()` — called at startup by orchestration
- `embed_text(text) -> list[float]` — used internally and by other modules needing embeddings
- `ensure_embedding_model() -> bool` — startup health check

## Dependencies

External packages:
- `chromadb==1.5.2` — persistent vector store with HNSW cosine index
- `aiohttp` — async HTTP for Ollama embedding API calls
- `loguru` — structured logging

Internal modules:
- `src.core.events` — EventBus pub/sub
- `src.shared.config` — `get_settings()` for `chroma_path`, `ollama_base_url`
- `src.shared.types` — `EventType`, `AetherEvent`
