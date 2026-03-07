"""Local embeddings via Ollama nomic-embed-text. Zero API cost.

Model: nomic-embed-text — the model actually installed in Ollama.
"""

import aiohttp
from loguru import logger

from src.shared.config import get_settings, get_yaml_config
from src.shared.http_client import get_shared_session

# Default model — overridden by aether_config.yaml memory.embedding_model
_DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"


def _get_embedding_model() -> str:
    """Get the configured embedding model name."""
    yaml_config = get_yaml_config()
    return yaml_config.get("memory", {}).get("embedding_model", _DEFAULT_EMBEDDING_MODEL)


async def embed_text(text: str) -> list[float]:
    """Get embeddings for text using local Ollama embedding model."""
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
        logger.error(f"Memory/Embeddings: failed to get embedding ({model}): {e}")
        raise


async def ensure_embedding_model() -> bool:
    """Verify the configured embedding model is available in Ollama."""
    settings = get_settings()
    model = _get_embedding_model()
    url = f"{settings.ollama_base_url}/api/tags"
    try:
        session = await get_shared_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            models = [m["name"] for m in data.get("models", [])]
            available = any(model in m for m in models)
            if not available:
                logger.warning(f"Memory: {model} not found in Ollama — pull with: ollama pull {model}")
            return available
    except Exception as e:
        logger.error(f"Memory: could not check Ollama models: {e}")
        return False
