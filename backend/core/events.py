from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class EventType(str, Enum):
    METADATA = "metadata"
    STATUS = "status"
    ACTION = "action"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    SOURCES = "sources"
    ANSWER_DELTA = "answer_delta"
    SUGGESTIONS = "suggestions"
    WARNING = "warning"
    DONE = "done"
    ERROR = "error"


TERMINAL_EVENT_TYPES = frozenset({EventType.DONE, EventType.ERROR})


@dataclass(frozen=True, slots=True)
class AgentEvent:
    type: EventType
    payload: Any
    run_id: str
    sequence: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.sequence < 1:
            raise ValueError("sequence must be greater than zero")
        if self.schema_version < 1:
            raise ValueError("schema_version must be greater than zero")
