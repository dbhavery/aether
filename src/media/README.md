# Module 09: Media

Aether's eyes — local image understanding and face recognition.

## Responsibility

Provides two capabilities: describing the content of images using a local vision
model (LLaVA via Ollama), and identifying known people in images using InsightFace
face embeddings. All processing runs locally with zero API cost. Known faces are
enrolled by dropping a reference JPEG into `./data\known_faces\<name>.jpg`.

## Key Files

- `image_understand.py` — `describe_image(path)` and `describe_image_bytes(bytes)`:
  base64-encodes the image, sends it to the configured vision model via Ollama
  (default `llava:7b`, target `qwen3.5-vl:8b`), returns a text description.
  Accepts a file path or raw bytes (e.g., from a screenshot tool).
- `face_recognize.py` — `identify_faces_in_image(path)`: loads InsightFace with
  CUDA, computes normed embeddings for all detected faces, compares against the
  known-faces library using dot-product similarity (threshold 0.4), returns a list
  of matched names.

## Interface Contract

- Exports (called directly by Brain/Tools, not via EventBus):
  - `describe_image(image_path: str | Path, prompt: str) -> str`
  - `describe_image_bytes(image_bytes: bytes, prompt: str) -> str`
  - `identify_faces_in_image(image_path: str | Path) -> list[str]`
- Does not subscribe to or publish any EventBus events.
- Known faces directory: `./data\known_faces\` (one `.jpg` per person,
  filename is the person's name).

## Dependencies

- `insightface` — face detection and embedding (personal use only, no commercial)
- `opencv-python` (`cv2`) — image loading for InsightFace
- `numpy` — embedding dot-product similarity
- `httpx` — async HTTP client for Ollama API calls
- `loguru` — structured logging
- `src.shared.config` — reads `ollama_base_url` from `aether_config.yaml`
- Ollama must be running with the vision model pulled (default: `ollama pull llava:7b`,
  target: `ollama pull qwen3.5-vl:8b`). Model configured via `media.vision_model` in YAML.
