"""Validate extracted preferences before allowing writes to durable profile memory."""

from __future__ import annotations

import logging

from services.memory.gate import SENSITIVE_CONTEXT_KEYWORDS, classify_user_message
from services.memory.ingestion.models import (
    MemoryEligibilityState,
    MemoryIngestionResult,
    UserEvidence,
)

logger = logging.getLogger(__name__)




async def _promote_extracted_learning_preference(
    ingestion,
    evidence: UserEvidence,
    *,
    whole_message_decision_reason: str,
) -> MemoryIngestionResult | None:
    """Promote one model-proposed learning preference after validation.

        The extraction agent is advisory and may see a mixed message that the
        whole-message gate classifies as a question. This method owns the
        persistence boundary: each draft is reclassified by deterministic
        policy, sensitive drafts fail closed, and only an allowlisted low-risk
        learning preference can reach user profile memory. Structured logs in
        this method intentionally expose only correlation IDs, candidate
        metadata, and policy reasons; raw user text and extracted text stay out
        of terminal logs.
        """

    if ingestion.extraction_agent is None:
        return None
    agent_name = ingestion.extraction_agent.__class__.__name__
    logger.debug(
        "memory.extraction_started user_id=%s message_id=%s conversation_id=%s agent=%s whole_message_reason=%s",
        evidence.user_id,
        evidence.message_id,
        evidence.conversation_id,
        agent_name,
        whole_message_decision_reason,
    )
    try:
        extraction = await ingestion.extraction_agent.extract_candidates(
            user_id=evidence.user_id,
            message_id=evidence.message_id,
            conversation_id=evidence.conversation_id,
            user_text=evidence.raw_message_text,
        )
    except Exception as exc:
        logger.warning(
            "memory.extraction_failed user_id=%s message_id=%s conversation_id=%s reason=%s",
            evidence.user_id,
            evidence.message_id,
            evidence.conversation_id,
            type(exc).__name__,
        )
        return None

    logger.debug(
        "memory.extraction_received user_id=%s message_id=%s conversation_id=%s agent=%s candidate_count=%s",
        evidence.user_id,
        evidence.message_id,
        evidence.conversation_id,
        agent_name,
        len(extraction.candidates),
    )

    for index, draft in enumerate(extraction.candidates):
        rejection_reason = ingestion._profile_learning_preference_rejection_reason(draft)
        if rejection_reason:
            logger.debug(
                "memory.extraction_candidate_skipped user_id=%s message_id=%s conversation_id=%s agent=%s candidate_index=%s candidate_type=%s durability=%s reason=%s",
                evidence.user_id,
                evidence.message_id,
                evidence.conversation_id,
                agent_name,
                index,
                draft.candidate_type,
                draft.durability,
                rejection_reason,
            )
            continue
        draft_text = draft.text.strip()
        if any(keyword in draft_text for keyword in SENSITIVE_CONTEXT_KEYWORDS):
            logger.warning(
                "memory.extraction_candidate_blocked user_id=%s message_id=%s conversation_id=%s agent=%s candidate_index=%s candidate_type=%s reason=sensitive_candidate",
                evidence.user_id,
                evidence.message_id,
                evidence.conversation_id,
                agent_name,
                index,
                draft.candidate_type,
            )
            continue

        draft_decision = classify_user_message(draft_text)
        canonical_key = ingestion._canonicalize_passive_preference(
            draft_decision.proposition or draft_text,
            "passive_preference",
        )
        if draft_decision.category != "passive_preference" or not canonical_key:
            logger.debug(
                "memory.extraction_candidate_blocked user_id=%s message_id=%s conversation_id=%s agent=%s candidate_index=%s candidate_type=%s deterministic_category=%s reason=deterministic_validation_failed",
                evidence.user_id,
                evidence.message_id,
                evidence.conversation_id,
                agent_name,
                index,
                draft.candidate_type,
                draft_decision.category,
            )
            continue

        await ingestion.store.perform_memory_operation(
            evidence.user_id,
            "user",
            "add",
            draft_decision.proposition,
            source="verified_user_evidence",
        )
        logger.info(
            "memory.extraction_candidate_promoted user_id=%s message_id=%s conversation_id=%s agent=%s candidate_index=%s candidate_type=%s reason=validated_learning_preference whole_message_reason=%s",
            evidence.user_id,
            evidence.message_id,
            evidence.conversation_id,
            agent_name,
            index,
            draft.candidate_type,
            whole_message_decision_reason,
        )
        return ingestion._result(
            MemoryEligibilityState.PROMOTION_ELIGIBLE,
            "extracted_learning_preference_promoted",
            "learning_preference",
            evidence,
            promoted=True,
        )
    logger.debug(
        "memory.extraction_no_promotion user_id=%s message_id=%s conversation_id=%s agent=%s candidate_count=%s reason=no_valid_learning_preference",
        evidence.user_id,
        evidence.message_id,
        evidence.conversation_id,
        agent_name,
        len(extraction.candidates),
    )
    return None
