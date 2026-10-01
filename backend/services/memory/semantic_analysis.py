"""Provide advisory semantic matching for already eligible user evidence.

The analyzer deliberately has no persistence dependency.  Its result can help
associate evidence with a candidate, but deterministic server policy remains
the only authority for retention, evidence counting, expiry, and promotion.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal, Protocol

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


class SemanticCandidate(BaseModel):
    """Minimal same-user candidate context allowed to leave the service."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    category: str
    canonical_summary: str


class SemanticAnalysisRequest(BaseModel):
    """Sanitized semantic-analysis input after deterministic eligibility."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(exclude=True)
    message_id: str
    category: str
    user_text: str
    candidates: list[SemanticCandidate] = Field(default_factory=list)


class SemanticAnalysisResult(BaseModel):
    """Closed advisory output that cannot encode a retention action."""

    model_config = ConfigDict(extra="forbid")

    canonical_key: str | None = None
    relation: Literal["match_existing", "create_candidate", "uncertain"]
    matched_candidate_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason_code: str


class MemorySemanticAnalyzer(Protocol):
    """Define a replaceable advisory semantic-analysis boundary."""

    async def analyze(self, request: SemanticAnalysisRequest) -> SemanticAnalysisResult:
        """Analyze eligible evidence without mutating memory."""


class OpenRouterMemorySemanticAnalyzer:
    """Call a pinned OpenRouter model using strict structured output."""

    def __init__(self, client: AsyncOpenAI, model: str, *, timeout_seconds: float = 3.0):
        self.client = client
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def analyze(self, request: SemanticAnalysisRequest) -> SemanticAnalysisResult:
        """Return a validated advisory result or a fail-closed uncertainty."""

        prompt_payload = {
            "message_id": request.message_id,
            "category": request.category,
            "user_text": request.user_text,
            "candidates": [candidate.model_dump() for candidate in request.candidates],
        }
        prompt = (
            "Compare one already policy-eligible user statement with candidates from "
            "the same user and category. Return match_existing only when the meanings "
            "express the same durable preference or goal. Return uncertain when wording "
            "is ambiguous. Never infer traits, sensitivity, retention, expiry, or promotion.\n"
            + json.dumps(prompt_payload, ensure_ascii=False)
        )
        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "memory_semantic_analysis",
                            "strict": True,
                            "schema": SemanticAnalysisResult.model_json_schema(),
                        },
                    },
                    temperature=0.0,
                    max_tokens=180,
                    extra_body={
                        "provider": {
                            "zdr": True,
                            "require_parameters": True,
                            "allow_fallbacks": False,
                        }
                    },
                ),
                timeout=self.timeout_seconds,
            )
            result = SemanticAnalysisResult.model_validate_json(
                response.choices[0].message.content
            )
        except (TimeoutError, ValidationError, json.JSONDecodeError, IndexError, AttributeError) as exc:
            logger.warning(
                "memory.semantic_analysis_unavailable model=%s reason=%s",
                self.model,
                type(exc).__name__,
            )
            return SemanticAnalysisResult(
                relation="uncertain",
                confidence=0.0,
                reason_code=f"analysis_{type(exc).__name__.lower()}",
            )
        except Exception as exc:
            logger.warning(
                "memory.semantic_analysis_unavailable model=%s reason=provider_%s",
                self.model,
                type(exc).__name__,
            )
            return SemanticAnalysisResult(
                relation="uncertain",
                confidence=0.0,
                reason_code="analysis_provider_error",
            )

        allowed_ids = {candidate.candidate_id for candidate in request.candidates}
        if result.relation == "match_existing":
            if not result.matched_candidate_id or result.matched_candidate_id not in allowed_ids:
                logger.warning(
                    "memory.semantic_analysis_unavailable model=%s reason=invalid_candidate_reference",
                    self.model,
                )
                return SemanticAnalysisResult(
                    relation="uncertain",
                    confidence=0.0,
                    reason_code="invalid_candidate_reference",
                )
        elif result.matched_candidate_id is not None:
            return SemanticAnalysisResult(
                relation="uncertain",
                confidence=0.0,
                reason_code="unexpected_candidate_reference",
            )
        return result
