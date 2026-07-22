"""Extract advisory memory candidates from mixed user messages.

The extraction boundary is intentionally non-mutating. It may propose memory
drafts from a multi-intent message, but persistence remains owned by
``MemoryIngestionService`` and the deterministic memory gate. Structured logs
from this module use stable event names and safe metadata only; raw user text,
prompts, model output, and credentials must not be logged.
"""

from __future__ import annotations

import asyncio
from collections import Counter
import json
import logging
import re
from typing import Literal, Protocol

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from memory_gate import SENSITIVE_CONTEXT_KEYWORDS, classify_user_message


logger = logging.getLogger(__name__)

MemoryDraftType = Literal[
    "learning_preference",
    "temporary_context",
    "sensitive_context",
    "question",
    "other",
]
DurabilityProposal = Literal["profile_memory", "working_memory_only", "do_not_store"]


def _format_candidate_type_counts(candidates: list["MemoryCandidateDraft"]) -> str:
    """Return safe candidate-type counts for structured logs."""

    if not candidates:
        return "none"
    counts = Counter(candidate.candidate_type for candidate in candidates)
    return ",".join(f"{candidate_type}:{counts[candidate_type]}" for candidate_type in sorted(counts))


class MemoryCandidateDraft(BaseModel):
    """One advisory memory candidate extracted from user-authored text.

    The candidate is not a storage command. Callers must validate the text,
    category, sensitivity, and provenance before any persistence operation.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_type: MemoryDraftType
    text: str = Field(min_length=1)
    durability: DurabilityProposal
    confidence: float = Field(ge=0.0, le=1.0)
    reason_code: str


class MemoryExtractionResult(BaseModel):
    """Validated extraction output from the advisory memory agent."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[MemoryCandidateDraft] = Field(default_factory=list)


class MemoryExtractionAgent(Protocol):
    """Replaceable advisory extraction boundary used by memory ingestion."""

    async def extract_candidates(
        self,
        *,
        user_id: str,
        message_id: str,
        conversation_id: str,
        user_text: str,
    ) -> MemoryExtractionResult:
        """Extract candidate memory drafts without mutating storage.

        Args:
            user_id: Owner identifier, used only for correlation and excluded
                from model-visible payloads.
            message_id: Stable user-message identifier for observability.
            conversation_id: Conversation scope for observability.
            user_text: Exact user-authored text to analyze.

        Returns:
            A validated list of advisory candidates. Empty means fail-closed or
            no extractable memory evidence.
        """


class OpenRouterMemoryExtractionAgent:
    """Call a pinned OpenRouter model for bounded structured extraction."""

    def __init__(self, client: AsyncOpenAI, model: str, *, timeout_seconds: float = 3.0):
        """Initialize the extraction agent.

        Args:
            client: Async OpenRouter-compatible client.
            model: Model identifier configured by deployment.
            timeout_seconds: Hard upper bound for the extraction call. Timeout
                failures return no candidates and never block the chat turn.
        """

        self.client = client
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def extract_candidates(
        self,
        *,
        user_id: str,
        message_id: str,
        conversation_id: str,
        user_text: str,
    ) -> MemoryExtractionResult:
        """Return validated candidate drafts or fail closed.

        The model sees only the user-authored message. It must separate
        questions, temporary context, sensitive learner-state statements, and
        low-risk learning preferences. The result is advisory; callers must
        run deterministic validation before persistence.
        """

        prompt_payload = {
            "message_id": message_id,
            "user_text": user_text,
            "allowed_candidate_types": [
                "learning_preference",
                "temporary_context",
                "sensitive_context",
                "question",
                "other",
            ],
            "allowed_durability": [
                "profile_memory",
                "working_memory_only",
                "do_not_store",
            ],
        }
        prompt = (
            "Extract only explicit user-authored memory candidates from a mixed "
            "message. Separate independent sentences. Do not infer traits. "
            "Classify anxiety, health, family, finances, or negative ability "
            "statements as sensitive_context with do_not_store. Classify exam "
            "timing or current task context as temporary_context with "
            "working_memory_only. Classify durable teaching-style preferences "
            "as learning_preference. Return strict JSON only.\n"
            + json.dumps(prompt_payload, ensure_ascii=False)
        )
        try:
            async with asyncio.timeout(self.timeout_seconds):
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "memory_extraction",
                            "strict": True,
                            "schema": MemoryExtractionResult.model_json_schema(),
                        },
                    },
                    temperature=0.0,
                    max_tokens=500,
                    extra_body={
                        "provider": {
                            "zdr": True,
                            "require_parameters": True,
                            "allow_fallbacks": False,
                        }
                    },
                )
            result = MemoryExtractionResult.model_validate_json(
                response.choices[0].message.content
            )
        except (TimeoutError, ValidationError, json.JSONDecodeError, IndexError, AttributeError) as exc:
            logger.warning(
                "memory.extraction_unavailable user_id=%s message_id=%s conversation_id=%s model=%s reason=%s",
                user_id,
                message_id,
                conversation_id,
                self.model,
                type(exc).__name__,
            )
            return MemoryExtractionResult()
        except Exception as exc:
            logger.warning(
                "memory.extraction_unavailable user_id=%s message_id=%s conversation_id=%s model=%s reason=provider_%s",
                user_id,
                message_id,
                conversation_id,
                self.model,
                type(exc).__name__,
            )
            return MemoryExtractionResult()

        logger.debug(
            "memory.extraction_completed user_id=%s message_id=%s conversation_id=%s model=%s candidate_count=%s candidate_type_counts=%s",
            user_id,
            message_id,
            conversation_id,
            self.model,
            len(result.candidates),
            _format_candidate_type_counts(result.candidates),
        )
        return result


class LocalMemoryExtractionAgent:
    """Extract explicit sentence-level candidates without external processing.

    This local micro-agent is intentionally narrow. It solves mixed-message
    speech-act separation without sending user text to a provider: each segment
    is classified by the deterministic memory gate and only explicit passive
    preferences are proposed as profile-memory drafts.
    """

    async def extract_candidates(
        self,
        *,
        user_id: str,
        message_id: str,
        conversation_id: str,
        user_text: str,
    ) -> MemoryExtractionResult:
        """Return local sentence-level advisory drafts.

        Args:
            user_id: Owner identifier for safe structured logs.
            message_id: Stable user-message identifier.
            conversation_id: Conversation scope.
            user_text: Exact user-authored text. It is never logged here.

        Returns:
            Candidate drafts derived from deterministic segment classification.
        """

        candidates: list[MemoryCandidateDraft] = []
        for segment in self._split_segments(user_text):
            if any(keyword in segment for keyword in SENSITIVE_CONTEXT_KEYWORDS):
                candidates.append(
                    MemoryCandidateDraft(
                        candidate_type="sensitive_context",
                        text=segment,
                        durability="do_not_store",
                        confidence=1.0,
                        reason_code="sensitive_segment",
                    )
                )
                continue

            decision = classify_user_message(segment)
            if decision.category == "passive_preference":
                candidates.append(
                    MemoryCandidateDraft(
                        candidate_type="learning_preference",
                        text=decision.proposition,
                        durability="profile_memory",
                        confidence=1.0,
                        reason_code=decision.reason,
                    )
                )
            elif decision.category == "temporary_goal":
                candidates.append(
                    MemoryCandidateDraft(
                        candidate_type="temporary_context",
                        text=decision.proposition,
                        durability="working_memory_only",
                        confidence=1.0,
                        reason_code=decision.reason,
                    )
                )
            elif decision.category == "current_focus" and decision.reason == "interrogative_not_memory_evidence":
                candidates.append(
                    MemoryCandidateDraft(
                        candidate_type="question",
                        text=decision.proposition,
                        durability="do_not_store",
                        confidence=1.0,
                        reason_code=decision.reason,
                    )
                )

        logger.debug(
            "memory.local_extraction_completed user_id=%s message_id=%s conversation_id=%s candidate_count=%s candidate_type_counts=%s",
            user_id,
            message_id,
            conversation_id,
            len(candidates),
            _format_candidate_type_counts(candidates),
        )
        return MemoryExtractionResult(candidates=candidates)

    @staticmethod
    def _split_segments(user_text: str) -> list[str]:
        """Split user text into conservative sentence-like segments."""

        raw_segments = re.split(r"[\n\r]+|(?<=[。！？!?])", user_text or "")
        return [
            re.sub(r"\s+", " ", segment).strip()
            for segment in raw_segments
            if re.sub(r"\s+", " ", segment).strip()
        ]
