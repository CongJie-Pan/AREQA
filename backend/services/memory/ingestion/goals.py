"""Complete uniquely matched temporary goals through the ingestion rules and store."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.memory.ingestion.models import (
    MemoryEligibilityState,
    MemoryIngestionResult,
    UserEvidence,
)

logger = logging.getLogger(__name__)




async def _complete_temporary_goal(
    ingestion,
    evidence: UserEvidence,
) -> MemoryIngestionResult:
    """Retire one safely matched temporary goal without profile mutation.

        Completion text is lifecycle evidence, not a learner profile fact. An
        ambiguous match is rejected so one command cannot silently retire an
        unrelated goal.
        """

    now = datetime.now(timezone.utc)
    candidates = await ingestion._active_candidates(evidence.user_id, "temporary_goal", now)
    completion_topic = ingestion._normalize_goal_topic(evidence.raw_message_text)
    matches = [
        candidate for candidate in candidates
        if ingestion._goal_topics_match(
            completion_topic,
            ingestion._normalize_goal_topic(
                str(candidate.get("source_text") or candidate.get("text") or "")
            ),
        )
    ]

    if len(matches) != 1:
        reason = (
            "temporary_goal_completion_not_found"
            if not matches
            else "temporary_goal_completion_ambiguous"
        )
        await ingestion.store.complete_temporary_goal_candidate(
            evidence.user_id,
            "",
            ingestion._evidence_record(evidence),
            reason=reason,
        )
        return ingestion._result(
            MemoryEligibilityState.WORKING_CONTEXT_ONLY,
            reason,
            "temporary_goal_completed",
            evidence,
        )

    candidate = await ingestion.store.complete_temporary_goal_candidate(
        evidence.user_id,
        str(matches[0]["hash"]),
        ingestion._evidence_record(evidence),
        reason="explicit_user_completion",
    )
    if candidate is None:
        return ingestion._result(
            MemoryEligibilityState.REJECTED,
            "temporary_goal_completion_blocked",
            "temporary_goal_completed",
            evidence,
        )

    working_memory = await ingestion.store.get_working_memory(evidence.user_id)
    focus_matches_goal = ingestion._goal_topics_match(
        ingestion._normalize_goal_topic(str(working_memory.get("current_focus") or "")),
        ingestion._normalize_goal_topic(
            str(candidate.get("source_text") or candidate.get("text") or "")
        ),
    )
    if focus_matches_goal:
        # Reminder suppression retires the matched goal, never unrelated focus.
        await ingestion.store.update_working_memory(
            evidence.user_id,
            {"current_focus": "", "current_focus_conversation_id": ""},
        )
        logger.info(
            "memory.goal_focus_cleared user_id=%s candidate_id=%s cleared_keys=%s",
            evidence.user_id,
            candidate["hash"],
            "current_focus,current_focus_conversation_id",
        )
    return ingestion._result(
        MemoryEligibilityState.WORKING_CONTEXT_ONLY,
        "temporary_goal_completed",
        "temporary_goal_completed",
        evidence,
        candidate_id=str(candidate["hash"]),
    )
