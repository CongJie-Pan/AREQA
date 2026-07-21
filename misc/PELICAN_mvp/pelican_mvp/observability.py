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
    "category",
    "strategy",
    "learner_state",
    "evidence_count",
    "working_context_count",
    "skill_id",
    "skill_version",
    "domain_category",
    "intake_decision",
    "route",
    "skill_lifecycle",
    "activity_code",
    "activity_status",
    "node_id",
    "step_id",
    "detail_code",
    "skill_source",
    "diagnostic_source",
    "intake_source",
    "model_route",
    "api_status_code",
    "api_error_type",
    "remediation_reason",
    "edf_transition",
    "memory_event",
})


def get_logger(name: str | None = None) -> logging.Logger:
    """Return the package logger without configuring global logging handlers."""
    return logging.getLogger(name or LOGGER_NAME)


def learner_token(learner_id: str) -> str:
    """Return a stable non-reversible token for correlating local session events."""
    return hashlib.sha256(learner_id.encode("utf-8")).hexdigest()[:12]


def log_event(event: str, learner_id: str | None = None, *, level: int = logging.INFO, **fields: Any) -> None:
    """Emit an allow-listed structured event without raw learner content.

    This boundary intentionally ignores unknown fields so callers cannot accidentally
    include answers, prompts, model output, or persisted session payloads in logs.
    """
    safe_fields = {
        key: value
        for key, value in fields.items()
        if key in _SAFE_FIELDS and isinstance(value, (str, int, float, bool, type(None)))
    }
    extra_fields = {"event": event, **safe_fields}
    if learner_id:
        extra_fields["learner_token"] = learner_token(learner_id)
    get_logger().log(
        level,
        event,
        extra=extra_fields,
    )
