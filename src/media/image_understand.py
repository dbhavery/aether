"""Image understanding — describe images using vision model via Ollama."""

import base64
from pathlib import Path

from loguru import logger

from src.shared.config import get_yaml_config


async def describe_image(
    image_path: str | Path,
    prompt: str = "Describe this image in detail.",
) -> str:
    """Describe an image using the local vision model."""
    image_path = Path(image_path)
    if not image_path.exists():
        return f"Image not found: {image_path}"
    try:
        import httpx

        config = get_yaml_config()
        ollama_url = config.get("llm", {}).get("ollama_base_url", "http://localhost:11434")

        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()

        vision_model = config.get("media", {}).get("vision_model", "llava:7b")
        payload = {
            "model": vision_model,
            "prompt": prompt,
            "images": [image_data],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{ollama_url}/api/generate", json=payload)
            result = resp.json()
            description = result.get("response", "").strip()
            logger.info(f"Media: described image '{image_path.name}': {description[:60]}")
            return description
    except Exception as e:
        logger.error(f"Media: image description failed: {e}")
        return f"I couldn't analyze that image: {e}"


async def describe_image_bytes(
    image_bytes: bytes,
    prompt: str = "Describe this image.",
) -> str:
    """Describe image from raw bytes (e.g., from screenshot tool)."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(image_bytes)
        tmp_path = f.name
    try:
        return await describe_image(tmp_path, prompt)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
