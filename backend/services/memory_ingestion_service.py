"""Own trusted user-evidence ingestion and profile-promotion eligibility.

This module is the only automatic path from an exact user message to a cold
candidate.  Model output is advisory and cannot bypass source, intent, safety,
lifecycle, or independent-evidence checks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any

from config import settings
from memory_gate import SENSITIVE_CONTEXT_KEYWORDS, classify_user_message
from services.memory_extraction_agent import (
    MemoryCandidateDraft,
    MemoryExtractionAgent,
)
from services.memory_semantic_analyzer import (
    MemorySemanticAnalyzer,
    SemanticAnalysisRequest,
    SemanticCandidate,
)


logger = logging.getLogger(__name__)



from services.memory_ingestion import rules as _memory_ingestion_rules_module
from services.memory_ingestion.models import (
    MemoryEligibilityState,
    MemoryIngestionResult,
    UserEvidence,
    build_user_evidence,
)
from services.memory_ingestion.factory import create_memory_ingestion_service_impl
from services.memory_ingestion.rules import MemoryIngestionRulesMixin


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

    async def _complete_temporary_goal(
        self,
        evidence: UserEvidence,
    ) -> MemoryIngestionResult:
        """Retire one safely matched temporary goal without profile mutation.

        Completion text is lifecycle evidence, not a learner profile fact. An
        ambiguous match is rejected so one command cannot silently retire an
        unrelated goal.
        """

        now = datetime.now(timezone.utc)
        candidates = await self._active_candidates(evidence.user_id, "temporary_goal", now)
        completion_topic = self._normalize_goal_topic(evidence.raw_message_text)
        matches = [
            candidate for candidate in candidates
            if self._goal_topics_match(
                completion_topic,
                self._normalize_goal_topic(
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
            await self.store.complete_temporary_goal_candidate(
                evidence.user_id,
                "",
                self._evidence_record(evidence),
                reason=reason,
            )
            return self._result(
                MemoryEligibilityState.WORKING_CONTEXT_ONLY,
                reason,
                "temporary_goal_completed",
                evidence,
            )

        candidate = await self.store.complete_temporary_goal_candidate(
            evidence.user_id,
            str(matches[0]["hash"]),
            self._evidence_record(evidence),
            reason="explicit_user_completion",
        )
        if candidate is None:
            return self._result(
                MemoryEligibilityState.REJECTED,
                "temporary_goal_completion_blocked",
                "temporary_goal_completed",
                evidence,
            )

        working_memory = await self.store.get_working_memory(evidence.user_id)
        focus_matches_goal = self._goal_topics_match(
            self._normalize_goal_topic(str(working_memory.get("current_focus") or "")),
            self._normalize_goal_topic(
                str(candidate.get("source_text") or candidate.get("text") or "")
            ),
        )
        if focus_matches_goal:
            # Reminder suppression retires the matched goal, never unrelated focus.
            await self.store.update_working_memory(
                evidence.user_id,
                {"current_focus": "", "current_focus_conversation_id": ""},
            )
            logger.info(
                "memory.goal_focus_cleared user_id=%s candidate_id=%s cleared_keys=%s",
                evidence.user_id,
                candidate["hash"],
                "current_focus,current_focus_conversation_id",
            )
        return self._result(
            MemoryEligibilityState.WORKING_CONTEXT_ONLY,
            "temporary_goal_completed",
            "temporary_goal_completed",
            evidence,
            candidate_id=str(candidate["hash"]),
        )

    async def _promote_extracted_learning_preference(
        self,
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

        if self.extraction_agent is None:
            return None
        agent_name = self.extraction_agent.__class__.__name__
        logger.debug(
            "memory.extraction_started user_id=%s message_id=%s conversation_id=%s agent=%s whole_message_reason=%s",
            evidence.user_id,
            evidence.message_id,
            evidence.conversation_id,
            agent_name,
            whole_message_decision_reason,
        )
        try:
            extraction = await self.extraction_agent.extract_candidates(
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
            rejection_reason = self._profile_learning_preference_rejection_reason(draft)
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
            canonical_key = self._canonicalize_passive_preference(
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

            await self.store.perform_memory_operation(
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
            return self._result(
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


# Moved deterministic rule helpers still reference the historical facade name
# in their globals. Binding it here preserves private-helper compatibility
# after the mechanical split.
_memory_ingestion_rules_module.MemoryIngestionService = MemoryIngestionService
