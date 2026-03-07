"""Base agent type and shared utilities for all Aether specialist agents."""

from dataclasses import dataclass, field
from enum import StrEnum


class AgentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class AgentTask:
    task_id: str
    agent_name: str
    instruction: str
    status: AgentStatus = AgentStatus.PENDING
    result: str | None = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)
