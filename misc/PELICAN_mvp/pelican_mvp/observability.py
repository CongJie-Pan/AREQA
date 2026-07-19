"""Safe structured logging helpers for local PELICAN learning sessions."""

from __future__ import annotations

import hashlib
import logging
from typing import Any


LOGGER_NAME = "pelican_mvp"
_SAFE_FIELDS = frozenset({
    "schema_version",
    "phase",
    "plan_source",
    "node_count",
    "reason_code",
})


def get_logger() -> logging.Logger:
    """Return the package logger without configuring global logging handlers."""
    return logging.getLogger(LOGGER_NAME)


def learner_token(learner_id: str) -> str:
    """Return a stable non-reversible token for correlating local session events."""
    return hashlib.sha256(learner_id.encode("utf-8")).hexdigest()[:12]


def log_event(event: str, learner_id: str, *, level: int = logging.INFO, **fields: Any) -> None:
    """Emit an allow-listed structured event without raw learner content.

    This boundary intentionally ignores unknown fields so callers cannot accidentally
    include answers, prompts, model output, or persisted session payloads in logs.
    """
    safe_fields = {
        key: value
        for key, value in fields.items()
        if key in _SAFE_FIELDS and isinstance(value, (str, int, float, bool, type(None)))
    }
    get_logger().log(
        level,
        event,
        extra={"event": event, "learner_token": learner_token(learner_id), **safe_fields},
    )
