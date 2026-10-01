"""Build structured visual blocks for illustrated assistant answers.

This module owns the privacy boundary for visual answer enrichment. It may use
the latest user message to query a search provider, but structured logs emitted
here never include raw user text, generated answer text, prompts, credentials,
or image URLs. Public output is limited to verified display metadata.
"""

from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urljoin, urlparse
import httpx
import redis.asyncio as aioredis
from config import settings
from services.query_policy.classifier import AttachmentTask, ResponsePolicy, VisualSupport
from services.visual_affordance_registry import match_visual_affordance
from services.visual_grounding_agent import VisualBrief, VisualGroundingAgent
from services.visual_answer.constants import (
    _INACCESSIBLE_IMAGE_DOMAIN_CACHE,
    _NEGATIVE_CACHE_SENTINEL,
    _NEGATIVE_CACHE_TTL_SECONDS,
    _POSITIVE_CACHE_TTL_SECONDS,
    _VISUAL_KEYWORDS,
)
from services.visual_answer.cache import VisualAnswerCacheMixin
from services.visual_answer.layout import VisualAnswerLayoutMixin
from services.visual_answer.models import (
    ImageBlock,
    ImageCandidate,
    PlannedImageSlot,
    VisualPreflightDecision,
)
from services.visual_answer.provider_clients import VisualAnswerProviderClientMixin
from services.visual_answer.provider_helpers import VisualAnswerProviderHelperMixin
from services.visual_answer.providers import VisualAnswerProviderMixin
from services.visual_answer.scoring import VisualAnswerScoringMixin
from services.visual_answer.selection import VisualAnswerSelectionMixin
from services.visual_answer.slots import VisualAnswerSlotMixin

logger = logging.getLogger(__name__)


class VisualAnswerService(
    VisualAnswerCacheMixin,
    VisualAnswerLayoutMixin,
    VisualAnswerProviderMixin,
    VisualAnswerProviderClientMixin,
    VisualAnswerProviderHelperMixin,
    VisualAnswerScoringMixin,
    VisualAnswerSelectionMixin,
    VisualAnswerSlotMixin,
):
    """Create paragraph and image blocks without changing text streaming.

    The service is intentionally fail-soft: visual enrichment must never prevent
    the answer stream from completing. Expected structured logs:
    - INFO `visual.slots_planned`: safe slot count and reason code.
    - INFO `visual.image_selected`: safe source domain and confidence bucket.
    - INFO `visual.image_omitted`: safe omission reason.
    - WARNING `visual.enrichment_failed`: unexpected exception type only.
    """

    def __init__(
        self,
        *,
        page_timeout_seconds: float = 2.0,
        max_images: int = 2,
        open_provider_timeout_seconds: float = 3.0,
        redis_factory: Any = aioredis.from_url,
    ) -> None:
        """Initialize the visual enrichment service.

        Args:
            page_timeout_seconds: Timeout for source-page metadata extraction.
            max_images: Hard cap for image blocks per answer.
            open_provider_timeout_seconds: Timeout for Wikimedia/Openverse APIs.
            redis_factory: Redis factory injected by tests.
        """

        self.page_timeout_seconds = page_timeout_seconds
        self.open_provider_timeout_seconds = open_provider_timeout_seconds
        self.max_images = max(0, min(max_images, 2))
        self._redis_factory = redis_factory
        self._visual_grounding_agent = VisualGroundingAgent()

    def should_enrich(self, response_policy: ResponsePolicy, user_msg: str) -> bool:
        """Return whether this turn should attempt visual enrichment."""

        return self._should_attempt_preflight(response_policy, user_msg, None)


    async def build_answer_blocks(
        self,
        *,
        answer_text: str,
        user_msg: str,
        response_policy: ResponsePolicy,
        tool_registry: Any,
        tool_budget: Any,
        existing_web_results: list[dict[str, Any]] | None,
        user_id: str,
        conversation_id: str,
        planned_image_slots: list[dict[str, Any]] | None = None,
        model_client: Any = None,
        preverified_image_blocks: dict[str, ImageBlock] | None = None,
    ) -> list[dict[str, Any]]:
        """Build frontend answer blocks for the completed answer text.

        Args:
            answer_text: Completed public assistant answer.
            user_msg: Latest user message, used only for retrieval query creation.
            response_policy: Structured policy selected earlier in orchestration.
            planned_image_slots: Optional model-planned visual requests already
                stripped from the public answer stream.
            tool_registry: Existing tool registry for web search execution.
            tool_budget: Current run tool budget.
            existing_web_results: Web results already fetched for this turn.
                These are preferred so illustrated answers do not spend a second
                external tool call in WEB_REQUIRED turns.
            user_id: Current user identifier for tool cache scoping.
            conversation_id: Current conversation identifier for safe logs.
            model_client: Optional OpenAI-compatible client for visual grounding
                checks. When omitted, grounding fails open.
            preverified_image_blocks: Optional images resolved before main
                generation. When present, only model-used verified image markers
                are rendered; unresolved placeholders are not emitted.

        Returns:
            Ordered paragraph and image blocks. Returns an empty list when visual
            enrichment is not applicable or no verified image can be found.
        """

        paragraphs = self._split_paragraphs(answer_text)
        planned_slots = self._planned_slots_from_payload(
            planned_image_slots or [],
            require_query=preverified_image_blocks is None,
            max_slots=len(preverified_image_blocks) if preverified_image_blocks is not None else self.max_images,
        )
        if not paragraphs or (not planned_slots and not self.should_enrich(response_policy, user_msg)):
            return []

        logger.info(
            "visual.slots_planned conversation_id=%s slot_count=%s reason=%s",
            conversation_id,
            len(planned_slots) if planned_slots else min(self.max_images, len(paragraphs)),
            "model_planned" if planned_slots else "policy_or_explicit_visual",
        )

        try:
            if preverified_image_blocks is not None:
                self._log_missing_paper_required_sections(
                    conversation_id,
                    response_policy,
                    planned_slots,
                    preverified_image_blocks,
                )
                logger.info(
                    "visual.preverified_available conversation_id=%s available_image_count=%s planned_image_slot_count=%s",
                    conversation_id,
                    len(preverified_image_blocks),
                    len(planned_slots),
                )
                if not preverified_image_blocks:
                    logger.info(
                        "visual.preverified_unused conversation_id=%s available_image_count=0",
                        conversation_id,
                    )
                    return []
                if not planned_slots:
                    logger.info(
                        "visual.preverified_unused conversation_id=%s reason=no_model_marker available_image_count=%s",
                        conversation_id,
                        len(preverified_image_blocks),
                    )
                    return []
                rendered = self._interleave_blocks_at_planned_slots(
                    paragraphs,
                    planned_slots,
                    preverified_image_blocks,
                    include_pending=False,
                )
                resolved_count = sum(1 for block in rendered if block.get("type") == "image_block")
                if resolved_count == 0:
                    logger.info(
                        "visual.image_omitted conversation_id=%s reason=no_used_verified_image",
                        conversation_id,
                    )
                    return []
                return rendered

            if planned_slots:
                image_blocks = await self._resolve_planned_image_blocks(
                    planned_slots=planned_slots,
                    existing_web_results=existing_web_results,
                    tool_registry=tool_registry,
                    tool_budget=tool_budget,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    model_client=model_client,
                )
                if not image_blocks:
                    logger.info(
                        "visual.image_omitted conversation_id=%s reason=no_verified_image",
                        conversation_id,
                    )
                    return []
                return self._interleave_blocks_at_planned_slots(paragraphs, planned_slots, image_blocks)

            visual_query, rewrite_rule = self._visual_search_query(user_msg)
            if rewrite_rule != "identity":
                logger.info(
                    "visual.query_rewritten conversation_id=%s rule=%s",
                    conversation_id,
                    rewrite_rule,
                )
            cache_key = self._cache_key(visual_query, "diagram")
            cached_block = await self._read_cache(cache_key, conversation_id)
            if cached_block == _NEGATIVE_CACHE_SENTINEL:
                return []
            if isinstance(cached_block, dict):
                return self._interleave_blocks(paragraphs, [self._image_block_from_frontend(cached_block)])

            image_blocks = await self._resolve_images(
                user_msg=user_msg,
                visual_query=visual_query,
                visual_intent_text=user_msg,
                existing_web_results=existing_web_results,
                tool_registry=tool_registry,
                tool_budget=tool_budget,
                user_id=user_id,
                conversation_id=conversation_id,
                model_client=model_client,
            )
        except Exception as exc:
            logger.warning(
                "visual.enrichment_failed conversation_id=%s reason=%s",
                conversation_id,
                type(exc).__name__,
            )
            return []

        if not image_blocks:
            logger.info(
                "visual.image_omitted conversation_id=%s reason=no_verified_image",
                conversation_id,
            )
            await self._write_cache(
                cache_key,
                _NEGATIVE_CACHE_SENTINEL,
                _NEGATIVE_CACHE_TTL_SECONDS,
                conversation_id,
                negative_reason="no_verified_image",
            )
            return []

        return self._interleave_blocks(paragraphs, image_blocks)


    def preflight_decision(self, response_policy, user_msg, turn_plan=None):
        """Return the visual policy decision before any provider work."""
        from services.visual_answer.preflight import preflight_decision

        return preflight_decision(self, response_policy, user_msg, turn_plan)

    def _should_attempt_preflight(self, response_policy, user_msg, turn_plan):
        from services.visual_answer.preflight import _should_attempt_preflight

        return _should_attempt_preflight(self, response_policy, user_msg, turn_plan)

    async def prepare_preflight_image_blocks(self, **kwargs):
        """Prepare grounded images through the preflight workflow."""
        from services.visual_answer.preflight import prepare_preflight_image_blocks

        return await prepare_preflight_image_blocks(self, **kwargs)

    async def _resolve_planned_image_blocks(self, **kwargs):
        from services.visual_answer.slot_resolution import _resolve_planned_image_blocks

        return await _resolve_planned_image_blocks(self, **kwargs)
