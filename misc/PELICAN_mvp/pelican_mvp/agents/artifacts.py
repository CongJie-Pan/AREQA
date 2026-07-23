"""Safe artifact helpers shared by PELICAN agent executors."""

from __future__ import annotations

import re
from typing import Any

from ..models import MethodologyRef


def bound_agent_text(value: Any, limit: int = 220) -> str:
    """Return bounded display text for agent proposal metadata.

    Args:
        value: Candidate value from an agent, validator, or fallback path.
        limit: Maximum number of characters to expose.

    Returns:
        A whitespace-normalized string capped to ``limit`` characters.

    Privacy:
        This helper is a display boundary, not a permission boundary. Callers
        must pass only safe summaries, references, reason codes, or previews
        that are allowed to appear in UI/export surfaces.
    """
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[: max(0, int(limit))]


def safe_artifact_ref(ref_type: str, ref_id: str | None, label: str) -> MethodologyRef:
    """Build a bounded artifact reference without raw payload content.

    Args:
        ref_type: Stable safe artifact category, such as ``skill_route``.
        ref_id: Safe identifier or route slug. Empty values become ``unknown``.
        label: Human-readable safe label for UI/export trace rows.

    Returns:
        A ``MethodologyRef`` with bounded fields suitable for proposals,
        methodology events, API metadata, and Markdown export.
    """
    return MethodologyRef(
        bound_agent_text(ref_type, 80) or "unknown",
        bound_agent_text(ref_id, 120) or "unknown",
        bound_agent_text(label, 160) or "agent artifact",
    )
