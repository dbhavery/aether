"""Shared type definitions — the language all modules speak."""

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    # Core
    PING = "ping"
    PONG = "pong"
    HEALTH_CHECK = "health_check"  # Reserved — future health event broadcast
    MODULE_REGISTERED = "module_registered"  # Reserved — future module lifecycle
    MODULE_READY = "module_ready"
    # Conversation
    USER_MESSAGE = "user_message"
    RESPONSE_END = "response_end"
    RESPONSE_START = "response_start"
    RESPONSE_TEXT_CHUNK = "response_text_chunk"
    RESPONSE_TEXT_READY = "response_text_ready"
    TOOL_CALL_REQUESTED = "tool_call_requested"
    TOOL_RESULT_READY = "tool_result_ready"
    # Voice
    AUDIO_CHUNK_READY = "audio_chunk_ready"  # Reserved — future EventBus audio streaming
    RESPONSE_AUDIO_CHUNK = "response_audio_chunk"
    RESPONSE_AUDIO_END = "response_audio_end"
    TRANSCRIPT_READY = "transcript_ready"
    USER_SPEECH_END = "user_speech_end"
    USER_SPEECH_START = "user_speech_start"
    # Avatar
    AVATAR_STATE_CHANGED = "avatar_state_changed"
    # Memory
    MEMORY_QUERY_REQUEST = "memory_query_request"  # Reserved — future EventBus memory ops
    MEMORY_QUERY_RESULT = "memory_query_result"  # Reserved — future EventBus memory ops
    MEMORY_STORE_REQUEST = "memory_store_request"  # Reserved — future EventBus memory ops
    # Settings
    SETTINGS_CHANGED = "settings_changed"
    # Onboarding wizard
    ONBOARDING_COMPLETE = "onboarding_complete"
    WIZARD_STEP_RESULT = "wizard_step_result"
    WIZARD_STEP_SUBMIT = "wizard_step_submit"
    # Wizard probes
    LLM_KEY_TEST_REQUEST = "llm_key_test_request"
    LLM_KEY_TEST_RESULT = "llm_key_test_result"
    OLLAMA_PROBE_REQUEST = "ollama_probe_request"
    OLLAMA_PROBE_RESULT = "ollama_probe_result"
    VOICE_HARDWARE_PROBE_REQUEST = "voice_hardware_probe_request"
    VOICE_HARDWARE_PROBE_RESULT = "voice_hardware_probe_result"
    VOICE_PREVIEW_REQUEST = "voice_preview_request"
    # Wizard state
    WIZARD_STATE_REQUEST = "wizard_state_request"
    WIZARD_STATE_RESULT = "wizard_state_result"
    # Persona / provider lifecycle
    PERSONA_CHANGED = "persona_changed"
    PROVIDER_CHANGED = "provider_changed"
    # Status
    ERROR = "error"
    PROCESSING_SLOW = "processing_slow"  # Reserved — future latency alerting
    PROCESSING_VERY_SLOW = "processing_very_slow"  # Reserved — future latency alerting


class InteractionMode(StrEnum):
    TEXT = "text"
    VOICE = "voice"
    VIDEO = "video"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class AetherEvent:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    source_module: str = "unknown"
    request_id: str | None = None


@dataclass
class ConversationMessage:
    role: MessageRole
    content: str
    timestamp: float = field(default_factory=time.time)
    mode: InteractionMode = InteractionMode.TEXT
