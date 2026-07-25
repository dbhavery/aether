"""Wizard helper handlers — LLM/Ollama/voice probes + wizard-state readback.

Each handler subscribes to a request event, does one bounded piece of I/O,
and publishes the matching result event. Result payloads always echo the
inbound ``request_id`` so the frontend can correlate.

All network / disk / GPU work runs either ``async`` natively or inside
``asyncio.to_thread`` so nothing here blocks the event loop.
"""

from __future__ import annotations

import asyncio
import shutil
from typing import Any

import aiohttp
from loguru import logger

from src.core.events import event_bus
from src.onboarding.state import load_wizard_state
from src.onboarding.validators import OLLAMA_DEFAULT_URL, validate_llm_provider
from src.shared.config import get_settings
from src.shared.paths import get_data_dir
from src.shared.types import AetherEvent, EventType

_SOURCE_MODULE = "onboarding.probe_handler"

_OLLAMA_PROBE_TIMEOUT_SECONDS = 3.0
_GB: float = float(1024**3)

# Spec §Screen 6: 6 GB VRAM is the cut-off between local and cloud voice.
_LOCAL_VOICE_MIN_VRAM_BYTES = 6 * 1024**3
_LOCAL_VOICE_MIN_FREE_DISK_BYTES = 3 * 1024**3

_handlers_registered = False


def register_probe_handlers() -> None:
    """Subscribe every probe handler to the EventBus. Idempotent."""
    global _handlers_registered
    if _handlers_registered:
        return
    event_bus.subscribe(EventType.LLM_KEY_TEST_REQUEST, _handle_llm_key_test)
    event_bus.subscribe(EventType.OLLAMA_PROBE_REQUEST, _handle_ollama_probe)
    event_bus.subscribe(EventType.VOICE_HARDWARE_PROBE_REQUEST, _handle_voice_hardware_probe)
    event_bus.subscribe(EventType.VOICE_PREVIEW_REQUEST, _handle_voice_preview)
    event_bus.subscribe(EventType.WIZARD_STATE_REQUEST, _handle_wizard_state_request)
    _handlers_registered = True
    logger.info("Onboarding probe handlers registered")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request_id(event: AetherEvent) -> str | None:
    """Return the request_id from the event (native or data-embedded)."""
    native = getattr(event, "request_id", None)
    if isinstance(native, str) and native:
        return native
    raw = event.data.get("request_id") if isinstance(event.data, dict) else None
    if isinstance(raw, str) and raw:
        return raw
    return None


async def _publish(event_type: EventType, data: dict[str, Any], request_id: str | None) -> None:
    """Publish a result event with matching ``request_id`` plumbing."""
    payload = dict(data)
    if request_id is not None:
        payload["request_id"] = request_id
    await event_bus.publish(
        AetherEvent(
            type=event_type,
            data=payload,
            source_module=_SOURCE_MODULE,
            request_id=request_id,
        )
    )


# ---------------------------------------------------------------------------
# LLM key test
# ---------------------------------------------------------------------------


async def _handle_llm_key_test(event: AetherEvent) -> None:
    data = event.data if isinstance(event.data, dict) else {}
    request_id = _request_id(event)
    provider_raw = data.get("provider")
    provider = provider_raw.strip().lower() if isinstance(provider_raw, str) else ""
    key_raw = data.get("key")
    key = key_raw if isinstance(key_raw, str) and key_raw.strip() else None
    overrides = data.get("model_overrides")
    if not isinstance(overrides, dict):
        overrides = None

    if not provider:
        await _publish(
            EventType.LLM_KEY_TEST_RESULT,
            {"ok": False, "error": "Provider is required.", "provider": ""},
            request_id,
        )
        return

    try:
        ok, error = await validate_llm_provider(provider, key, overrides)
    except Exception as exc:
        logger.exception(f"LLM key test failed unexpectedly for {provider!r}: {exc!r}")
        await _publish(
            EventType.LLM_KEY_TEST_RESULT,
            {
                "ok": False,
                "error": "Internal error while testing the provider.",
                "provider": provider,
            },
            request_id,
        )
        return

    await _publish(
        EventType.LLM_KEY_TEST_RESULT,
        {"ok": ok, "error": None if ok else error, "provider": provider},
        request_id,
    )


# ---------------------------------------------------------------------------
# Ollama probe
# ---------------------------------------------------------------------------


async def _handle_ollama_probe(event: AetherEvent) -> None:
    request_id = _request_id(event)

    base_url = _ollama_base_url()
    tags_url = f"{base_url.rstrip('/')}/api/tags"

    try:
        timeout = aiohttp.ClientTimeout(total=_OLLAMA_PROBE_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session, session.get(tags_url) as resp:
            if resp.status != 200:
                await _publish(
                    EventType.OLLAMA_PROBE_RESULT,
                    {
                        "available": False,
                        "models": [],
                        "error": f"Ollama returned HTTP {resp.status}.",
                    },
                    request_id,
                )
                return
            payload = await resp.json()
    except (TimeoutError, aiohttp.ClientError) as exc:
        logger.warning(f"Ollama probe failed: {exc!r}")
        await _publish(
            EventType.OLLAMA_PROBE_RESULT,
            {"available": False, "models": [], "error": "Ollama isn't reachable."},
            request_id,
        )
        return

    models: list[str] = []
    for entry in payload.get("models") or []:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str):
                models.append(name)
    await _publish(
        EventType.OLLAMA_PROBE_RESULT,
        {"available": True, "models": models, "error": None},
        request_id,
    )


def _ollama_base_url() -> str:
    """Resolve the configured Ollama base URL, falling back to the default."""
    try:
        configured = (get_settings().ollama_base_url or "").strip()
    except Exception:
        configured = ""
    return configured or OLLAMA_DEFAULT_URL


# ---------------------------------------------------------------------------
# Voice hardware probe
# ---------------------------------------------------------------------------


async def _handle_voice_hardware_probe(event: AetherEvent) -> None:
    request_id = _request_id(event)

    probe = await asyncio.to_thread(_collect_voice_hardware_snapshot)
    recommendation = _recommend_voice_mode(
        gpu_available=probe["gpu_available"],
        vram_gb=probe["vram_gb"],
        disk_free_gb=probe["disk_free_gb"],
    )
    await _publish(
        EventType.VOICE_HARDWARE_PROBE_RESULT,
        {**probe, "recommended": recommendation},
        request_id,
    )


def _collect_voice_hardware_snapshot() -> dict[str, Any]:
    """Synchronously inspect GPU/disk. Intended for ``asyncio.to_thread``."""
    gpu_available = False
    gpu_name: str | None = None
    vram_gb: float | None = None

    try:
        import torch
    except ImportError:
        logger.debug("voice hardware probe: torch not installed")
        torch = None  # type: ignore[assignment]

    if torch is not None:
        try:
            if torch.cuda.is_available():
                gpu_available = True
                props = torch.cuda.get_device_properties(0)
                raw_name = getattr(props, "name", None)
                if isinstance(raw_name, str):
                    gpu_name = raw_name
                total = int(getattr(props, "total_memory", 0))
                if total > 0:
                    vram_gb = round(total / _GB, 2)
        except Exception as exc:
            logger.warning(f"voice hardware probe: torch.cuda inspection failed: {exc!r}")

    try:
        free_bytes = shutil.disk_usage(str(get_data_dir())).free
        disk_free_gb = round(free_bytes / _GB, 2)
    except OSError as exc:
        logger.warning(f"voice hardware probe: disk_usage failed: {exc!r}")
        disk_free_gb = 0.0

    return {
        "gpu_available": gpu_available,
        "gpu_name": gpu_name,
        "vram_gb": vram_gb,
        "disk_free_gb": disk_free_gb,
    }


def _recommend_voice_mode(
    *,
    gpu_available: bool,
    vram_gb: float | None,
    disk_free_gb: float,
) -> str:
    """Return one of ``"local"`` | ``"cloud"`` | ``"off"`` per the spec.

    * ``off`` only when there's not enough disk to land even the cloud models.
    * ``local`` when we have a CUDA GPU with the spec'd VRAM and disk headroom.
    * ``cloud`` otherwise (CPU-only machines, low-VRAM GPUs, laptops on battery).
    """
    disk_free_bytes = disk_free_gb * _GB
    if disk_free_bytes < _LOCAL_VOICE_MIN_FREE_DISK_BYTES / 3:
        # Less than ~1 GB free — don't recommend any on-device voice at all.
        return "off"
    if gpu_available and vram_gb is not None and vram_gb * _GB >= _LOCAL_VOICE_MIN_VRAM_BYTES:
        if disk_free_bytes >= _LOCAL_VOICE_MIN_FREE_DISK_BYTES:
            return "local"
    return "cloud"


# ---------------------------------------------------------------------------
# Voice preview (fire-and-forget)
# ---------------------------------------------------------------------------


async def _handle_voice_preview(event: AetherEvent) -> None:
    data = event.data if isinstance(event.data, dict) else {}
    persona_id_raw = data.get("persona_id")
    if not isinstance(persona_id_raw, str) or not persona_id_raw.strip():
        logger.debug("voice preview: missing persona_id — no-op")
        return
    persona_id = persona_id_raw.strip()

    try:
        from src.personas import get_persona_manager

        pack = get_persona_manager().get(persona_id)
    except Exception as exc:
        logger.warning(f"voice preview: persona manager lookup failed: {exc!r}")
        return

    if pack is None:
        logger.info(f"voice preview: unknown persona '{persona_id}' — no-op")
        return

    sample_path = pack.sample_wav_path
    if not sample_path.exists():
        logger.info(f"voice preview: no sample.wav for persona '{persona_id}' — no-op")
        return

    await asyncio.to_thread(_play_sample_wav, str(sample_path))


def _play_sample_wav(path: str) -> None:
    """Play ``path`` through the default output device. Best-effort, logs on failure."""
    try:
        import sounddevice
        import soundfile
    except ImportError:
        logger.info("voice preview: sounddevice/soundfile not installed — no-op")
        return

    try:
        samples, samplerate = soundfile.read(path, always_2d=False)
        sounddevice.play(samples, samplerate)
        sounddevice.wait()
    except Exception as exc:
        logger.warning(f"voice preview: playback failed for {path}: {exc!r}")


# ---------------------------------------------------------------------------
# Wizard state readback
# ---------------------------------------------------------------------------


async def _handle_wizard_state_request(event: AetherEvent) -> None:
    request_id = _request_id(event)

    state_model = await asyncio.to_thread(load_wizard_state)
    if state_model is None:
        await _publish(EventType.WIZARD_STATE_RESULT, {"state": None}, request_id)
        return

    try:
        state_dict = state_model.model_dump(mode="json")
    except Exception as exc:
        logger.error(f"Could not serialise wizard state: {exc!r}")
        state_dict = None
    await _publish(EventType.WIZARD_STATE_RESULT, {"state": state_dict}, request_id)
