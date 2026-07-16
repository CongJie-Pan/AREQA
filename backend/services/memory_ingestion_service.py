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
from services.memory_semantic_analyzer import (
    MemorySemanticAnalyzer,
    SemanticAnalysisRequest,
    SemanticCandidate,
)


logger = logging.getLogger(__name__)


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
        semantic_analyzer: MemorySemanticAnalyzer | None = None,
        semantic_enabled: bool | None = None,
        semantic_shadow_mode: bool | None = None,
    ):
        self.store = store
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
        if any(keyword in evidence.raw_message_text for keyword in SENSITIVE_CONTEXT_KEYWORDS):
            return self._result(
                MemoryEligibilityState.REJECTED,
                "sensitive_content_not_durable",
                "sensitive",
                evidence,
            )

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
        canonical_key = normalized_text
        candidate_hash_override = ""

        active_candidates = await self._active_candidates(evidence.user_id, category, now)
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
                not self.semantic_shadow_mode
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
            "memory.ingestion_decided user_id=%s message_id=%s state=%s reason=%s category=%s",
            evidence.user_id,
            evidence.message_id,
            state.value,
            reason_code,
            category,
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

    Exact user evidence is sent to the external semantic provider only when
    both semantic analysis and the deployment privacy acknowledgement are
    enabled. This keeps an environment toggle from silently changing the data
    processing boundary.
    """

    analyzer = None
    semantic_enabled = bool(
        settings.memory_semantic_analysis_enabled
        and settings.memory_semantic_external_processing_acknowledged
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
        semantic_analyzer=analyzer,
        semantic_enabled=semantic_enabled,
    )
