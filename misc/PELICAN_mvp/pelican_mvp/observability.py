"""Safe structured logging helpers for local PELICAN learning sessions."""

from __future__ import annotations

import hashlib
import logging
from typing import Any


LOGGER_NAME = "pelican_mvp"
DEBUG_CHANNELS = (
    "api",
    "intake",
    "skill",
    "diagnosis",
    "state",
    "edf",
    "memory",
    "tutor",
    "methodology",
    "activity",
)
_EVENT_CHANNEL_PREFIXES = (
    ("pelican_api_", "api"),
    ("pelican_intake_", "intake"),
    ("pelican_topic_", "intake"),
    ("pelican_skill_", "skill"),
    ("pelican_plan_", "skill"),
    ("pelican_diagnostic_", "diagnosis"),
    ("pelican_diagnosis_", "diagnosis"),
    ("pelican_state_", "state"),
    ("pelican_session_", "state"),
    ("pelican_phase_", "state"),
    ("pelican_edf_", "edf"),
    ("pelican_memory_", "memory"),
    ("pelican_remediation_", "tutor"),
    ("pelican_scope_", "tutor"),
    ("pelican_scaffold_", "tutor"),
    ("pelican_agent_", "methodology"),
    ("pelican_methodology_", "methodology"),
    ("pelican_turn_", "methodology"),
    ("pelican_progress_", "activity"),
    ("pelican_activity", "activity"),
)
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
    "semantic_intent",
    "semantic_confidence",
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
    "turn_id",
    "cycle_id",
    "sequence",
    "proposal_id",
    "proposal_source",
    "pedagogical_move",
    "agent_stage",
    "agent_status",
    "artifact_type",
    "methodology_status",
    "event_type",
    "agent_role",
    "validation_status",
    "elapsed_ms",
    "attempt_count",
    "rejected_count",
    "fallback_used",
    "endpoint",
    "schema_mode",
    "schema_format",
    "schema_strict",
    "schema_fallback",
})


class DebugChannelFilter(logging.Filter):
    """Filter terminal logs by safe PELICAN feature channel.

    Args:
        channels: ``None`` to allow all channels, or a normalized collection of
            channel names from ``DEBUG_CHANNELS``.

    Returns:
        ``True`` when the record belongs to an enabled channel.

    Side Effects:
        None. The filter only reads the ``debug_channel`` attribute written by
        ``log_event`` and never inspects raw learner content.
    """

    def __init__(self, channels: frozenset[str] | None) -> None:
        super().__init__()
        self.channels = channels

    def filter(self, record: logging.LogRecord) -> bool:
        if self.channels is None:
            return True
        return getattr(record, "debug_channel", "activity") in self.channels


def get_logger(name: str | None = None) -> logging.Logger:
    """Return the package logger without configuring global logging handlers."""
    return logging.getLogger(name or LOGGER_NAME)


def learner_token(learner_id: str) -> str:
    """Return a stable non-reversible token for correlating local session events."""
    return hashlib.sha256(learner_id.encode("utf-8")).hexdigest()[:12]


def debug_channel_for_event(event: str) -> str:
    """Map a stable event name to one terminal debug channel.

    Args:
        event: Safe structured event name, normally beginning with
            ``pelican_``.

    Returns:
        One of ``DEBUG_CHANNELS``. Unknown event names are grouped under
        ``activity`` so they remain visible unless the operator narrows the
        terminal filter.
    """
    for prefix, channel in _EVENT_CHANNEL_PREFIXES:
        if event.startswith(prefix):
            return channel
    return "activity"


def normalize_debug_channels(raw_channels: str | None) -> frozenset[str] | None:
    """Normalize a comma-separated channel list for terminal filtering.

    Args:
        raw_channels: ``None``, ``all``, or a comma-separated list such as
            ``api,skill,tutor``.

    Returns:
        ``None`` when all channels should be shown, otherwise a frozenset of
        valid channel names.

    Raises:
        ValueError: If an unknown channel name is provided.
    """
    if raw_channels is None or raw_channels.strip().lower() in {"", "all", "*"}:
        return None
    channels = frozenset(item.strip().lower() for item in raw_channels.split(",") if item.strip())
    unknown = sorted(channels - set(DEBUG_CHANNELS))
    if unknown:
        raise ValueError(f"Unknown PELICAN log channel(s): {', '.join(unknown)}")
    return channels


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
    extra_fields = {"event": event, "debug_channel": debug_channel_for_event(event), **safe_fields}
    if learner_id:
        extra_fields["learner_token"] = learner_token(learner_id)
    get_logger().log(
        level,
        event,
        extra=extra_fields,
    )
