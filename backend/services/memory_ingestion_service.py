"""Own trusted user-evidence ingestion and profile-promotion eligibility.

This module is the only automatic path from an exact user message to a cold
candidate.  Model output is advisory and cannot bypass source, intent, safety,
lifecycle, or independent-evidence checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
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


_CONCRETE_EXAMPLE_MARKERS = ("具體例子", "具體案例", "實際例子", "實際情境")
_ABSTRACT_CONCEPT_MARKERS = ("抽象概念", "抽象原理")
_NEGATIVE_PREFERENCE_MARKERS = ("不喜歡", "討厭", "不希望", "不想要")
_CONCRETE_ABSTRACT_PREFERENCE_KEY = (
    "learning_preference:abstract_concepts:concrete_examples"
)
_GOAL_MATCH_NOISE = (
    "請在這段期間協助我安排練習",
    "請不要再提醒我",
    "不要再提醒我",
    "不用再提醒我",
    "停止提醒",
    "我已經",
    "我想",
    "這個月",
    "這週",
    "下週",
    "目前",
    "已經",
    "完成了",
    "完成",
    "複習目標",
    "學習目標",
    "讀書計畫",
    "目標",
    "複習",
    "請",
    "的",
)


class MemoryEligibilityState(str, Enum):
    """Describe the server-owned outcome of one evidence ingestion."""

    REJECTED = "rejected"
    WORKING_CONTEXT_ONLY = "working_context_only"
    CANDIDATE = "candidate"
    PROMOTION_ELIGIBLE = "promotion_eligible"


@dataclass(frozen=True)
class UserEvidence:
    """Immutable provenance for one exact user-authored message."""

    user_id: str
    message_id: str
    conversation_id: str
    timestamp: str
    raw_message_text: str
    source_role: str = "user"


@dataclass(frozen=True)
class MemoryIngestionResult:
    """Typed policy result returned without exposing model reasoning."""

    state: MemoryEligibilityState
    reason_code: str
    category: str
    candidate_id: str | None = None
    expires_at: str | None = None
    promoted: bool = False


def build_user_evidence(
    user_id: str,
    conversation_id: str,
    raw_message_text: str,
    *,
    message_id: str = "",
    timestamp: str = "",
) -> UserEvidence:
    """Build stable provenance when the transport lacks a message identifier.

    The digest is deterministic for one conversation/message pair, preventing
    background reprocessing from counting the same message twice.
    """

    text = (raw_message_text or "").strip()
    stable_id = message_id or hashlib.sha256(
        f"{user_id}|{conversation_id}|{text}".encode("utf-8")
    ).hexdigest()[:24]
    return UserEvidence(
        user_id=user_id,
        message_id=stable_id,
        conversation_id=conversation_id,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        raw_message_text=text,
        source_role="user",
    )


class MemoryIngestionService:
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

    analyzer = None
    extraction_agent = None
    semantic_enabled = bool(
        settings.memory_semantic_analysis_enabled
        and settings.memory_semantic_external_processing_acknowledged
    )
    if (
        settings.memory_extraction_agent_enabled
        and settings.memory_semantic_external_processing_acknowledged
        and client is not None
    ):
        from services.memory_extraction_agent import OpenRouterMemoryExtractionAgent

        extraction_agent = OpenRouterMemoryExtractionAgent(
            client,
            settings.model_memory_semantic_analyzer,
            timeout_seconds=settings.memory_extraction_timeout_seconds,
        )
        logger.debug(
            "memory.extraction_agent_configured mode=external model=%s timeout_seconds=%s min_confidence=%s privacy_acknowledged=%s client_available=%s",
            settings.model_memory_semantic_analyzer,
            settings.memory_extraction_timeout_seconds,
            settings.memory_extraction_min_confidence,
            settings.memory_semantic_external_processing_acknowledged,
            client is not None,
        )
    elif settings.memory_extraction_agent_enabled:
        from services.memory_extraction_agent import LocalMemoryExtractionAgent

        extraction_agent = LocalMemoryExtractionAgent()
        logger.debug(
            "memory.extraction_agent_configured mode=local model=none timeout_seconds=%s min_confidence=%s privacy_acknowledged=%s client_available=%s",
            settings.memory_extraction_timeout_seconds,
            settings.memory_extraction_min_confidence,
            settings.memory_semantic_external_processing_acknowledged,
            client is not None,
        )
    else:
        logger.debug(
            "memory.extraction_agent_configured mode=disabled model=none timeout_seconds=%s min_confidence=%s privacy_acknowledged=%s client_available=%s",
            settings.memory_extraction_timeout_seconds,
            settings.memory_extraction_min_confidence,
            settings.memory_semantic_external_processing_acknowledged,
            client is not None,
        )

    if semantic_enabled and client is not None:
        from services.memory_semantic_analyzer import OpenRouterMemorySemanticAnalyzer

        analyzer = OpenRouterMemorySemanticAnalyzer(
            client,
            settings.model_memory_semantic_analyzer,
            timeout_seconds=settings.memory_semantic_timeout_seconds,
        )
    elif settings.memory_semantic_analysis_enabled:
        logger.warning(
            "memory.semantic_analysis_blocked reason=%s",
            "privacy_acknowledgement_missing"
            if not settings.memory_semantic_external_processing_acknowledged
            else "client_unavailable",
        )
    return MemoryIngestionService(
        store,
        extraction_agent=extraction_agent,
        semantic_analyzer=analyzer,
        semantic_enabled=semantic_enabled,
    )
