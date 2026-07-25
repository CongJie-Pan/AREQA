"""Thread-safe runtime progress snapshots for long learner requests.

This module stores only bounded, learner-safe progress metadata in process
memory. It exists for the local MVP web UI: while ``/api/respond`` is still
running, the browser can poll ``/api/progress`` and update the existing loading
bubble without waiting for the final tutor response.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .observability import log_event


MAX_PROGRESS_EVENTS = 12


@dataclass(frozen=True)
class RuntimeProgressEvent:
    """Safe user-visible progress event for one in-flight backend request.

    Args:
        code: Stable stage code, such as ``skill_generation``.
        label: Localized learner-visible label.
        status: ``processing``, ``done``, or ``error``.
        detail: Safe bounded detail code. Never raw learner text, prompts, or
            model output.
        sequence: Monotonic per-learner event sequence.
        timestamp: UTC ISO timestamp for debugging stale polling states.

    Side Effects:
        None.
    """

    code: str
    label: str
    status: str
    detail: str
    sequence: int
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize the progress event for the web API."""
        return {
            "code": self.code,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
        }


_lock = threading.Lock()
_events_by_learner: dict[str, list[RuntimeProgressEvent]] = {}
_sequence_by_learner: dict[str, int] = {}


def reset_progress(learner_id: str) -> None:
    """Clear runtime progress for a new request.

    Args:
        learner_id: Local session identifier. It is used only as an in-process
            lookup key; logs receive the hashed learner token from ``log_event``.

    Side Effects:
        Removes existing in-memory progress events for this learner.
    """
    with _lock:
        _events_by_learner[learner_id] = []
        _sequence_by_learner[learner_id] = 0


def record_progress(
    learner_id: str,
    code: str,
    label: str,
    *,
    status: str = "processing",
    detail: str = "",
) -> RuntimeProgressEvent:
    """Append a safe runtime progress event and emit a structured debug log.

    Args:
        learner_id: Local session identifier.
        code: Stable stage code for UI rendering.
        label: Learner-visible label.
        status: Progress status. Unknown values normalize to ``processing``.
        detail: Safe detail code; truncated defensively.

    Returns:
        The appended progress event.

    Side Effects:
        Mutates the process-local progress store and emits
        ``pelican_progress_event``. The log contains only safe metadata:
        learner token, activity code/status, detail code, and sequence.
    """
    normalized_status = status if status in {"processing", "done", "error"} else "processing"
    safe_code = str(code)[:80]
    safe_label = str(label)[:120]
    safe_detail = str(detail)[:120]
    timestamp = datetime.now(timezone.utc).isoformat()
    with _lock:
        sequence = _sequence_by_learner.get(learner_id, 0) + 1
        _sequence_by_learner[learner_id] = sequence
        event = RuntimeProgressEvent(
            code=safe_code,
            label=safe_label,
            status=normalized_status,
            detail=safe_detail,
            sequence=sequence,
            timestamp=timestamp,
        )
        _events_by_learner[learner_id] = [*(_events_by_learner.get(learner_id, [])), event][
            -MAX_PROGRESS_EVENTS:
        ]

    log_event(
        "pelican_progress_event",
        learner_id=learner_id,
        activity_code=safe_code,
        activity_status=normalized_status,
        detail_code=safe_detail,
        sequence=sequence,
    )
    return event


def progress_snapshot(learner_id: str) -> dict[str, Any]:
    """Return the latest safe progress snapshot for frontend polling.

    Args:
        learner_id: Local session identifier.

    Returns:
        Dictionary with ``events``, ``latest``, and ``active``. ``active`` is
        true when the latest event is still processing.

    Side Effects:
        None.
    """
    with _lock:
        events = list(_events_by_learner.get(learner_id, []))
    serialized = [event.to_dict() for event in events]
    latest = serialized[-1] if serialized else None
    return {
        "events": serialized,
        "latest": latest,
        "active": bool(latest and latest.get("status") == "processing"),
    }
