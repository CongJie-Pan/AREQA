"""Deterministic memory ingestion rule helpers.

This mixin owns normalization, provenance validation, active-candidate lookup,
and final result logging for ``MemoryIngestionService``. Logs use safe user,
message, conversation, candidate, state, and reason metadata only; raw prompts
and model reasoning must not be logged.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any

from config import settings
from services.memory_extraction_agent import MemoryCandidateDraft
from services.memory_ingestion.constants import (
    _ABSTRACT_CONCEPT_MARKERS,
    _CONCRETE_ABSTRACT_PREFERENCE_KEY,
    _CONCRETE_EXAMPLE_MARKERS,
    _GOAL_MATCH_NOISE,
    _NEGATIVE_PREFERENCE_MARKERS,
)
from services.memory_ingestion.models import MemoryEligibilityState, MemoryIngestionResult, UserEvidence

logger = logging.getLogger(__name__)


class MemoryIngestionRulesMixin:
    """Provide deterministic helper methods for memory ingestion workflows."""

    @staticmethod
    def _profile_learning_preference_rejection_reason(draft: MemoryCandidateDraft) -> str:
        """Return a safe reason when a draft cannot enter profile validation."""

        if draft.candidate_type != "learning_preference":
            return "non_learning_preference"
        if draft.durability != "profile_memory":
            return "non_profile_durability"
        if draft.confidence < settings.memory_extraction_min_confidence:
            return "low_confidence"
        return ""

    async def _active_candidates(
        self,
        user_id: str,
        category: str,
        now: datetime,
    ) -> list[dict[str, Any]]:
        """Return non-sensitive active candidates scoped to one user/category."""

        candidates = await self.store.get_cold_candidates(user_id)
        result = []
        for candidate in candidates:
            if candidate.get("user_id") != user_id or candidate.get("category") != category:
                continue
            if candidate.get("status") != "candidate" or candidate.get("requires_confirmation"):
                continue
            expires_at = candidate.get("expires_at")
            if expires_at:
                try:
                    expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=timezone.utc)
                    if expiry <= now:
                        continue
                except ValueError:
                    continue
            result.append(candidate)
        return result

    @staticmethod
    def _normalize_candidate(text: str) -> str:
        """Create a conservative key; semantic equivalence requires the analyzer."""

        return re.sub(r"[\s，,。！？!?：:；;]", "", text).lower()

    @staticmethod
    def _canonicalize_passive_preference(text: str, category: str) -> str:
        """Canonicalize one narrow, low-risk positive learning preference."""

        if category != "passive_preference":
            return ""
        normalized = MemoryIngestionService._normalize_candidate(text)
        if any(marker in normalized for marker in _NEGATIVE_PREFERENCE_MARKERS):
            return ""
        if not any(marker in normalized for marker in _CONCRETE_EXAMPLE_MARKERS):
            return ""
        if not any(marker in normalized for marker in _ABSTRACT_CONCEPT_MARKERS):
            return ""
        if not any(marker in normalized for marker in ("學", "理解", "偏好", "希望")):
            return ""
        return _CONCRETE_ABSTRACT_PREFERENCE_KEY

    @staticmethod
    def _normalize_goal_topic(text: str) -> str:
        """Remove lifecycle boilerplate while preserving a goal's topic."""

        normalized = MemoryIngestionService._normalize_candidate(text)
        for marker in _GOAL_MATCH_NOISE:
            normalized = normalized.replace(marker, "")
        return normalized

    @staticmethod
    def _goal_topics_match(completion_topic: str, candidate_topic: str) -> bool:
        """Match only non-empty deterministic topics, allowing added qualifiers."""

        if len(completion_topic) < 2 or len(candidate_topic) < 2:
            return False
        return completion_topic in candidate_topic or candidate_topic in completion_topic

    async def _has_promoted_canonical_profile(self, user_id: str, canonical_key: str) -> bool:
        """Return whether an equivalent canonical preference is already promoted."""

        candidates = await self.store.get_cold_candidates(user_id)
        return any(
            candidate.get("user_id") == user_id
            and candidate.get("status") == "promoted"
            and str(candidate.get("canonical_key") or "") == canonical_key
            for candidate in candidates
            if isinstance(candidate, dict)
        )

    @staticmethod
    def _rewrite_self_report_for_profile(text: str) -> str:
        """Convert exact first-person evidence into a concise profile statement."""

        cleaned = re.sub(r"\s+", " ", (text or "").strip()).strip("。 ")
        return re.sub(r"^我", "使用者", cleaned, count=1)

    @staticmethod
    def _evidence_record(evidence: UserEvidence) -> dict[str, str]:
        """Serialize immutable user evidence for candidate lifecycle updates."""

        return {
            "message_id": evidence.message_id,
            "conversation_id": evidence.conversation_id,
            "timestamp": evidence.timestamp,
            "source_role": evidence.source_role,
            "message": evidence.raw_message_text,
            "quote": evidence.raw_message_text,
        }

    @staticmethod
    def _validate_provenance(evidence: UserEvidence) -> str:
        """Return a stable rejection code for missing immutable provenance."""

        if evidence.source_role != "user":
            return "non_user_source"
        for field in ("user_id", "message_id", "conversation_id", "timestamp", "raw_message_text"):
            if not str(getattr(evidence, field, "")).strip():
                return f"missing_{field}"
        return ""

    @staticmethod
    def _result(
        state: MemoryEligibilityState,
        reason_code: str,
        category: str,
        evidence: UserEvidence,
        *,
        candidate_id: str | None = None,
        expires_at: str | None = None,
        promoted: bool = False,
    ) -> MemoryIngestionResult:
        logger.info(
            "memory.ingestion_decided user_id=%s message_id=%s conversation_id=%s candidate_id=%s state=%s reason=%s category=%s promoted=%s",
            evidence.user_id,
            evidence.message_id,
            evidence.conversation_id,
            candidate_id or "none",
            state.value,
            reason_code,
            category,
            promoted,
        )
        return MemoryIngestionResult(
            state=state,
            reason_code=reason_code,
            category=category,
            candidate_id=candidate_id,
            expires_at=expires_at,
            promoted=promoted,
        )
