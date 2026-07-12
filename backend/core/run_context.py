from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class SearchMode(StrEnum):
    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"


@dataclass(frozen=True, slots=True)
class RunContext:
    run_id: str
    user_id: str
    conversation_id: str
    request_id: str
    search_mode: SearchMode
    memory_scope: str = "policy_controlled"
    learner_state_version: int | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for field_name in ("run_id", "user_id", "conversation_id", "request_id"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")
