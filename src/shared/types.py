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
    RESPONSE_TEXT_READY = "response_text_ready"
    TOOL_CALL_REQUESTED = "tool_call_requested"
    TOOL_RESULT_READY = "tool_result_ready"
    # Voice
    TRANSCRIPT_READY = "transcript_ready"
    AUDIO_CHUNK_READY = "audio_chunk_ready"  # Reserved — future EventBus audio streaming
    # Memory
    MEMORY_STORE_REQUEST = "memory_store_request"  # Reserved — future EventBus memory ops
    MEMORY_QUERY_REQUEST = "memory_query_request"  # Reserved — future EventBus memory ops
    MEMORY_QUERY_RESULT = "memory_query_result"  # Reserved — future EventBus memory ops
    # Settings
    SETTINGS_CHANGED = "settings_changed"
    # Onboarding wizard
    WIZARD_STEP_SUBMIT = "wizard_step_submit"
    WIZARD_STEP_RESULT = "wizard_step_result"
    ONBOARDING_COMPLETE = "onboarding_complete"
    # Persona / provider lifecycle
    PERSONA_CHANGED = "persona_changed"
    PROVIDER_CHANGED = "provider_changed"
    # Status
    PROCESSING_SLOW = "processing_slow"  # Reserved — future latency alerting
    PROCESSING_VERY_SLOW = "processing_very_slow"  # Reserved — future latency alerting
    ERROR = "error"


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


@dataclass
class ConversationMessage:
    role: MessageRole
    content: str
    timestamp: float = field(default_factory=time.time)
    mode: InteractionMode = InteractionMode.TEXT
