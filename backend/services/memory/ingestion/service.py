"""Own trusted user-evidence ingestion and profile-promotion eligibility.

This module is the only automatic path from an exact user message to a cold
candidate.  Model output is advisory and cannot bypass source, intent, safety,
lifecycle, or independent-evidence checks.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from config import settings
from services.memory.extraction import (
    MemoryCandidateDraft as MemoryCandidateDraft,
)
from services.memory.extraction import (
    MemoryExtractionAgent,
)
from services.memory.gate import SENSITIVE_CONTEXT_KEYWORDS, classify_user_message
from services.memory.ingestion.factory import create_memory_ingestion_service_impl
from services.memory.ingestion.models import (
    MemoryEligibilityState,
    MemoryIngestionResult,
    UserEvidence,
)
from services.memory.ingestion.models import (
    build_user_evidence as build_user_evidence,
)
from services.memory.ingestion.rules import MemoryIngestionRulesMixin
from services.memory.semantic_analysis import (
    MemorySemanticAnalyzer,
    SemanticAnalysisRequest,
    SemanticCandidate,
)

logger = logging.getLogger(__name__)




class MemoryIngestionService(MemoryIngestionRulesMixin):
    """Apply deterministic memory policy with optional advisory matching."""

    def __init__(
        self,
        store: Any,
        *,
        extraction_agent: MemoryExtractionAgent | None = None,
        semantic_analyzer: MemorySemanticAnalyzer | None = None,
        semantic_enabled: bool | None = None,
        semantic_shadow_mode: bool | None = None,
    ):
        self.store = store
        self.extraction_agent = extraction_agent
        self.semantic_analyzer = semantic_analyzer
        self.semantic_enabled = (
            settings.memory_semantic_analysis_enabled
            if semantic_enabled is None
            else semantic_enabled
        )
        self.semantic_shadow_mode = (
            settings.memory_semantic_shadow_mode
            if semantic_shadow_mode is None
            else semantic_shadow_mode
        )

    async def ingest_user_evidence(self, evidence: UserEvidence) -> MemoryIngestionResult:
        """Validate, classify, and persist one user evidence record.

        Questions and sensitive text are rejected before semantic analysis.
        Analyzer failure creates no semantic corroboration; a deterministic new
        candidate may still preserve an otherwise eligible user statement.
        """

        invalid_reason = self._validate_provenance(evidence)
        if invalid_reason:
            return self._result(
                MemoryEligibilityState.REJECTED,
                invalid_reason,
                "none",
                evidence,
            )

        decision = classify_user_message(evidence.raw_message_text)
        extracted_result = await self._promote_extracted_learning_preference(
            evidence,
            whole_message_decision_reason=decision.reason,
        )
        if extracted_result is not None:
            return extracted_result

        if any(keyword in evidence.raw_message_text for keyword in SENSITIVE_CONTEXT_KEYWORDS):
            return self._result(
                MemoryEligibilityState.REJECTED,
                "sensitive_content_not_durable",
                "sensitive",
                evidence,
            )

        if decision.category == "temporary_goal_completed":
            return await self._complete_temporary_goal(evidence)

        if decision.should_prompt:
            await self.store.update_working_memory(
                evidence.user_id,
                {
                    "current_focus": decision.proposition,
                    "current_focus_conversation_id": evidence.conversation_id,
                },
            )

        if decision.category in {"empty", "smalltalk", "current_focus"}:
            return self._result(
                MemoryEligibilityState.WORKING_CONTEXT_ONLY,
                decision.reason,
                decision.category,
                evidence,
            )

        if decision.category == "explicit_memory":
            await self.store.perform_memory_operation(
                evidence.user_id,
                "user",
                "add",
                decision.proposition,
                source="explicit_user_request",
            )
            return self._result(
                MemoryEligibilityState.PROMOTION_ELIGIBLE,
                "explicit_command_promoted",
                "explicit_memory",
                evidence,
                promoted=True,
            )

        if decision.category == "explicit_self_report":
            profile_text = self._rewrite_self_report_for_profile(decision.proposition)
            canonical_key = self._canonicalize_passive_preference(
                decision.proposition,
                "passive_preference",
            )
            if canonical_key and await self._has_promoted_canonical_profile(
                evidence.user_id,
                canonical_key,
            ):
                return self._result(
                    MemoryEligibilityState.PROMOTION_ELIGIBLE,
                    "explicit_self_report_duplicate_profile",
                    "explicit_self_report",
                    evidence,
                    promoted=False,
                )
            await self.store.perform_memory_operation(
                evidence.user_id,
                "user",
                "add",
                profile_text,
                source="verified_user_evidence",
            )
            return self._result(
                MemoryEligibilityState.PROMOTION_ELIGIBLE,
                "explicit_self_report_promoted",
                "explicit_self_report",
                evidence,
                promoted=True,
            )

        route = {
            "passive_preference": ("passive_preference", 90, False),
            "temporary_goal": ("temporary_goal", 30, False),
            "stable_fact_candidate": ("stable_fact_candidate", None, True),
        }.get(decision.category)
        if route is None:
            return self._result(
                MemoryEligibilityState.REJECTED,
                "unsupported_memory_category",
                decision.category,
                evidence,
            )

        category, ttl_days, requires_confirmation = route
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(days=ttl_days)).isoformat() if ttl_days else None
        normalized_text = self._normalize_candidate(evidence.raw_message_text)
        canonical_key = self._canonicalize_passive_preference(
            evidence.raw_message_text,
            category,
        ) or normalized_text
        candidate_hash_override = ""

        active_candidates = await self._active_candidates(evidence.user_id, category, now)
        if canonical_key != normalized_text:
            canonical_matches = [
                item for item in active_candidates
                if str(item.get("canonical_key") or "") == canonical_key
            ]
            if len(canonical_matches) == 1:
                matched = canonical_matches[0]
                candidate_hash_override = str(matched["hash"])
                normalized_text = str(matched.get("normalized_text") or canonical_key)
                logger.info(
                    "memory.canonical_match_accepted user_id=%s message_id=%s candidate_id=%s category=%s reason=canonical_key_match",
                    evidence.user_id,
                    evidence.message_id,
                    candidate_hash_override,
                    category,
                )
            elif len(canonical_matches) > 1:
                logger.warning(
                    "memory.canonical_match_rejected user_id=%s message_id=%s category=%s reason=ambiguous_candidates",
                    evidence.user_id,
                    evidence.message_id,
                    category,
                )
            else:
                # The canonical key becomes the deterministic identity for the
                # first allowlisted candidate; later equivalent phrasing joins it.
                normalized_text = canonical_key

        if self.semantic_enabled and self.semantic_analyzer is not None:
            analysis = await self.semantic_analyzer.analyze(
                SemanticAnalysisRequest(
                    user_id=evidence.user_id,
                    message_id=evidence.message_id,
                    category=category,
                    user_text=evidence.raw_message_text,
                    candidates=[
                        SemanticCandidate(
                            candidate_id=item["hash"],
                            category=item["category"],
                            canonical_summary=str(
                                item.get("canonical_key") or item.get("normalized_text") or ""
                            ),
                        )
                        for item in active_candidates[: settings.memory_semantic_candidate_limit]
                    ],
                )
            )
            logger.info(
                "memory.semantic_shadow_result user_id=%s message_id=%s relation=%s reason=%s shadow=%s",
                evidence.user_id,
                evidence.message_id,
                analysis.relation,
                analysis.reason_code,
                self.semantic_shadow_mode,
            )
            if (
                not candidate_hash_override
                and not self.semantic_shadow_mode
                and analysis.relation == "match_existing"
                and analysis.confidence >= settings.memory_semantic_match_min_confidence
            ):
                matched = next(
                    (item for item in active_candidates if item["hash"] == analysis.matched_candidate_id),
                    None,
                )
                if matched is not None:
                    candidate_hash_override = matched["hash"]
                    normalized_text = str(matched.get("normalized_text") or normalized_text)
                    canonical_key = str(matched.get("canonical_key") or normalized_text)
                    logger.info(
                        "memory.semantic_match_accepted user_id=%s message_id=%s candidate_id=%s",
                        evidence.user_id,
                        evidence.message_id,
                        candidate_hash_override,
                    )
            elif not self.semantic_shadow_mode and analysis.relation == "match_existing":
                logger.warning(
                    "memory.semantic_match_rejected user_id=%s message_id=%s reason=low_confidence",
                    evidence.user_id,
                    evidence.message_id,
                )

        evidence_record = {
            "message_id": evidence.message_id,
            "conversation_id": evidence.conversation_id,
            "timestamp": evidence.timestamp,
            "source_role": evidence.source_role,
            "message": evidence.raw_message_text,
            "quote": evidence.raw_message_text,
        }
        candidate = await self.store.append_cold_candidate(
            evidence.user_id,
            evidence.raw_message_text,
            category=category,
            source="verified_user_evidence",
            reason=decision.reason,
            confidence=10.0,
            normalized_text=normalized_text,
            canonical_key=canonical_key,
            candidate_hash_override=candidate_hash_override,
            evidence=evidence_record,
            source_text=evidence.raw_message_text,
            conversation_id=evidence.conversation_id,
            requires_confirmation=requires_confirmation,
            expires_at=expires_at,
        )
        if candidate is None:
            return self._result(
                MemoryEligibilityState.REJECTED,
                "candidate_persistence_rejected",
                category,
                evidence,
            )

        promoted = False
        if category == "passive_preference":
            promoted_candidate = await self.store.promote_cold_candidate(
                evidence.user_id,
                candidate["hash"],
                source="automatic_candidate_promotion",
            )
            promoted = promoted_candidate is not None

        return self._result(
            MemoryEligibilityState.PROMOTION_ELIGIBLE if promoted else MemoryEligibilityState.CANDIDATE,
            "candidate_promoted" if promoted else "candidate_created_or_updated",
            category,
            evidence,
            candidate_id=candidate["hash"],
            expires_at=expires_at,
            promoted=promoted,
        )


    async def _complete_temporary_goal(self, evidence: UserEvidence) -> MemoryIngestionResult:
        """Complete only a uniquely matched goal under the ingestion rules."""
        from services.memory.ingestion.goals import _complete_temporary_goal

        return await _complete_temporary_goal(self, evidence)

    async def _promote_extracted_learning_preference(self, evidence, *, whole_message_decision_reason):
        """Promote extracted preferences only after deterministic validation."""
        from services.memory.ingestion.preferences import (
            _promote_extracted_learning_preference,
        )

        return await _promote_extracted_learning_preference(
            self, evidence, whole_message_decision_reason=whole_message_decision_reason,
        )


def create_memory_ingestion_service(
    store: Any,
    *,
    client: Any = None,
) -> MemoryIngestionService:
    """Create the configured ingestion boundary with privacy fail-closed.

    Mixed-message extraction defaults to the local deterministic micro-agent.
    Exact user evidence is sent to external memory-analysis providers only when
    the feature flag and deployment privacy acknowledgement are both enabled.
    This keeps an environment toggle from silently changing the data processing
    boundary.
    """

    return create_memory_ingestion_service_impl(MemoryIngestionService, store, client=client)
