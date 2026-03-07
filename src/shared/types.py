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
    WAKE_WORD_DETECTED = "wake_word_detected"
    TRANSCRIPT_READY = "transcript_ready"
    SPEAKER_VERIFIED = "speaker_verified"
    AUDIO_CHUNK_READY = "audio_chunk_ready"  # Reserved — future EventBus audio streaming
    # Memory
    MEMORY_STORE_REQUEST = "memory_store_request"  # Reserved — future EventBus memory ops
    MEMORY_QUERY_REQUEST = "memory_query_request"  # Reserved — future EventBus memory ops
    MEMORY_QUERY_RESULT = "memory_query_result"  # Reserved — future EventBus memory ops
    # Notifications
    NOTIFICATION_REQUEST = "notification_request"
    NOTIFICATION_DELIVERED = "notification_delivered"  # Reserved — future delivery confirmation
    # Agents
    AGENT_TASK_COMPLETE = "agent_task_complete"
    # Settings
    SETTINGS_CHANGED = "settings_changed"
    # Persona / Proactive
    PROACTIVE_MESSAGE = "proactive_message"
    MEMORY_CORRECTION = "memory_correction"
    # Approval
    APPROVAL_REQUESTED = "approval_requested"
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
