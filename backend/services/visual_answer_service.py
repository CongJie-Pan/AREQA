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
from services.query_policy_service import AttachmentTask, ResponsePolicy, VisualSupport
from services.visual_affordance_registry import match_visual_affordance
from services.visual_grounding_agent import VisualBrief, VisualGroundingAgent

logger = logging.getLogger(__name__)

from services.visual_answer.constants import (
    _INACCESSIBLE_IMAGE_DOMAIN_CACHE,
    _NEGATIVE_CACHE_SENTINEL,
    _NEGATIVE_CACHE_TTL_SECONDS,
    _POSITIVE_CACHE_TTL_SECONDS,
    _VISUAL_KEYWORDS,
)
from services.visual_answer import cache as _visual_answer_cache_module
from services.visual_answer import layout as _visual_answer_layout_module
from services.visual_answer import provider_clients as _visual_answer_provider_clients_module
from services.visual_answer import provider_helpers as _visual_answer_provider_helpers_module
from services.visual_answer import providers as _visual_answer_providers_module
from services.visual_answer import scoring as _visual_answer_scoring_module
from services.visual_answer import selection as _visual_answer_selection_module
from services.visual_answer import slots as _visual_answer_slots_module
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

    def preflight_decision(
        self,
        response_policy: ResponsePolicy,
        user_msg: str,
        turn_plan: Any = None,
    ) -> VisualPreflightDecision:
        """Return privacy-safe metadata for the visual preflight gate.

        Args:
            response_policy: EDF policy selected for the current turn.
            user_msg: Latest user message used only for bounded visual intent
                checks; it must not be logged by callers.
            turn_plan: Optional deterministic turn plan retained for signature
                compatibility with orchestration paths.

        Returns:
            A ``VisualPreflightDecision`` containing only enum values, booleans,
            counters, and reason buckets suitable for backend logs.

        Side Effects:
            None. The stable log event emitted by orchestration is
            ``visual.preflight_policy_gate`` with request correlation metadata.
        """

        del turn_plan
        normalized = user_msg.lower()
        explicit_visual_request = any(keyword in normalized for keyword in _VISUAL_KEYWORDS)
        affordance = match_visual_affordance(user_msg)
        known_visual_affordance = bool(affordance and affordance.preflight_trigger)
        visual_support_value = getattr(
            response_policy.visual_support,
            "value",
            response_policy.visual_support,
        )
        agent_requires_visuals = visual_support_value == VisualSupport.REQUIRED.value
        agent_allows_visuals = visual_support_value in {
            VisualSupport.OPTIONAL.value,
            VisualSupport.REQUIRED.value,
        }
        allowed = bool(
            self.max_images > 0
            and (
                explicit_visual_request
                or known_visual_affordance
                or agent_allows_visuals
            )
        )
        blocking_allowed = bool(
            self.max_images > 0
            and (
                explicit_visual_request
                or agent_requires_visuals
            )
        )
        if self.max_images <= 0:
            trigger = "disabled"
        elif explicit_visual_request:
            trigger = "explicit_visual_request"
        elif known_visual_affordance:
            trigger = "known_visual_affordance"
        elif agent_requires_visuals:
            trigger = "response_policy_required"
        elif agent_allows_visuals:
            trigger = "response_policy_optional"
        else:
            trigger = "policy_gate"
        return VisualPreflightDecision(
            allowed=allowed,
            blocking_allowed=blocking_allowed,
            trigger=trigger,
            visual_support=response_policy.visual_support.value,
            visual_reason=response_policy.visual_reason.value,
            explicit_visual_request=explicit_visual_request,
            known_visual_affordance=known_visual_affordance,
            max_images=self.max_images,
        )

    def _should_attempt_preflight(
        self,
        response_policy: ResponsePolicy,
        user_msg: str,
        turn_plan: Any = None,
    ) -> bool:
        """Return whether the current turn should attempt visual retrieval.

        Response policy classification is the primary agent-level gate. Visual
        retrieval runs only when the EDF decision allows visual support, when
        the user explicitly asks for an image, or when a narrow deterministic
        affordance identifies a known graph-heavy educational concept. This
        keeps broad semantic classification out of this service and avoids paid
        provider/PDF-rendering cost for ordinary responses.
        """

        return self.preflight_decision(response_policy, user_msg, turn_plan).allowed

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

    async def prepare_preflight_image_blocks(
        self,
        *,
        user_msg: str,
        response_policy: ResponsePolicy,
        existing_web_results: list[dict[str, Any]] | None,
        tool_registry: Any,
        tool_budget: Any,
        user_id: str,
        conversation_id: str,
        model_client: Any = None,
        turn_plan: Any = None,
    ) -> dict[str, ImageBlock]:
        """Resolve verified images before the main answer model runs.

        The preflight path lets the answer model write with knowledge of actual
        verified images instead of requesting images after generation. It keeps
        image selection fail-soft: if no verified image is found, the main model
        simply receives no visual inventory.
        """

        if not settings.enable_visual_preflight:
            return {}
        if not self._should_attempt_preflight(response_policy, user_msg, turn_plan):
            return {}

        visual_query, rewrite_rule = self._visual_search_query(user_msg)
        if rewrite_rule != "identity":
            logger.info(
                "visual.preflight_query_rewritten conversation_id=%s rule=%s",
                conversation_id,
                rewrite_rule,
            )
        brief = await self._visual_grounding_agent.plan(
            client=model_client,
            model=settings.model_policy_classifier,
            user_msg=user_msg,
            fallback_query=visual_query,
            conversation_id=conversation_id,
            response_policy=response_policy,
            turn_plan=turn_plan,
        )
        slot = PlannedImageSlot(
            slot_id="img_1",
            query=brief.search_query,
            caption_hint="",
            anchor_after_paragraph=0,
        )
        logger.info(
            "visual.preflight_started conversation_id=%s slot_count=1 visual_type=%s brief_source=%s",
            conversation_id,
            brief.visual_type,
            brief.source,
        )
        timeout_seconds = max(0.1, float(settings.visual_preflight_timeout_seconds))
        try:
            blocks = await asyncio.wait_for(
                self._resolve_planned_image_blocks(
                    planned_slots=[slot],
                    existing_web_results=existing_web_results,
                    tool_registry=tool_registry,
                    tool_budget=tool_budget,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    model_client=model_client,
                    visual_brief=brief,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.info(
                "visual.preflight_timeout conversation_id=%s timeout_seconds=%.1f",
                conversation_id,
                timeout_seconds,
            )
            blocks = {}
        logger.info(
            "visual.preflight_completed conversation_id=%s resolved_image_count=%s",
            conversation_id,
            len(blocks),
        )
        return blocks

    async def _resolve_planned_image_blocks(
        self,
        *,
        planned_slots: list[PlannedImageSlot],
        existing_web_results: list[dict[str, Any]] | None,
        tool_registry: Any,
        tool_budget: Any,
        user_id: str,
        conversation_id: str,
        model_client: Any = None,
        visual_brief: VisualBrief | None = None,
    ) -> dict[str, ImageBlock]:
        """Resolve model-planned visual requests into verified image blocks.

        Args:
            planned_slots: Validated slot requests in model stream order.
            existing_web_results: Optional web results already available.
            tool_registry: Existing tool registry for fallback web search.
            tool_budget: Shared foreground tool budget.
            user_id: User id required by the search tool.
            conversation_id: Correlation id for privacy-safe logs.
            model_client: Optional OpenAI-compatible client for visual grounding.
            visual_brief: Optional preflight visual plan used for grounding.

        Returns:
            Mapping from planned slot id to selected image block.
        """

        resolved: dict[str, ImageBlock] = {}
        for slot in planned_slots[: self.max_images]:
            logger.info(
                "visual.slot_resolution_started conversation_id=%s slot_id=%s",
                conversation_id,
                slot.slot_id,
            )
            cache_key = (
                self._visual_brief_cache_key(visual_brief)
                if visual_brief is not None
                else self._cache_key(slot.query, "diagram")
            )
            if visual_brief is not None:
                logger.info(
                    "visual.cache_scope_selected conversation_id=%s scope=preflight visual_type=%s",
                    conversation_id,
                    visual_brief.visual_type,
                )
            cached_block = await self._read_cache(cache_key, conversation_id)
            if cached_block == _NEGATIVE_CACHE_SENTINEL:
                logger.info(
                    "visual.slot_resolution_failed conversation_id=%s slot_id=%s reason=negative_cache",
                    conversation_id,
                    slot.slot_id,
                )
                continue
            if isinstance(cached_block, dict):
                resolved[slot.slot_id] = self._apply_slot_metadata(
                    self._image_block_from_frontend(cached_block),
                    slot,
                )
                logger.info(
                    "visual.slot_resolution_completed conversation_id=%s slot_id=%s source=cache",
                    conversation_id,
                    slot.slot_id,
                )
                continue

            image_blocks = await self._resolve_images(
                user_msg=slot.query,
                visual_query=slot.query,
                visual_intent_text=self._slot_visual_intent(slot),
                existing_web_results=existing_web_results,
                tool_registry=tool_registry,
                tool_budget=tool_budget,
                user_id=user_id,
                conversation_id=conversation_id,
                model_client=model_client,
                visual_brief=visual_brief,
                allow_og_fallback=visual_brief is None,
                allow_open_provider_fallback=(
                    visual_brief is None or settings.enable_visual_preflight_open_provider_fallback
                ),
                selection_limit=self.max_images + 1 if visual_brief is not None else self.max_images,
            )
            if not image_blocks:
                await self._write_cache(
                    cache_key,
                    _NEGATIVE_CACHE_SENTINEL,
                    _NEGATIVE_CACHE_TTL_SECONDS,
                    conversation_id,
                    negative_reason="no_verified_image",
                )
                logger.info(
                    "visual.slot_resolution_failed conversation_id=%s slot_id=%s reason=no_verified_image",
                    conversation_id,
                    slot.slot_id,
                )
                continue
            block = self._apply_slot_metadata(image_blocks[0], slot)
            alternative_blocks = tuple(
                replace(
                    self._apply_slot_metadata(alternative, slot),
                    cache_key=cache_key,
                    cache_ttl_seconds=_POSITIVE_CACHE_TTL_SECONDS,
                    alternative_blocks=(),
                )
                for alternative in image_blocks[1 : self.max_images + 1]
            )
            block = replace(
                block,
                cache_key=cache_key,
                cache_ttl_seconds=_POSITIVE_CACHE_TTL_SECONDS,
                alternative_blocks=alternative_blocks,
            )
            resolved[slot.slot_id] = block
            logger.info(
                "visual.slot_resolution_completed conversation_id=%s slot_id=%s source=provider alternative_count=%s",
                conversation_id,
                slot.slot_id,
                len(alternative_blocks),
            )
        return resolved

# Binding it here preserves private-helper compatibility without rewriting the
# copied method bodies during the mechanical split.
_visual_answer_cache_module.VisualAnswerService = VisualAnswerService
_visual_answer_layout_module.VisualAnswerService = VisualAnswerService
_visual_answer_provider_clients_module.VisualAnswerService = VisualAnswerService
_visual_answer_provider_helpers_module.VisualAnswerService = VisualAnswerService
_visual_answer_providers_module.VisualAnswerService = VisualAnswerService
_visual_answer_scoring_module.VisualAnswerService = VisualAnswerService
_visual_answer_selection_module.VisualAnswerService = VisualAnswerService
_visual_answer_slots_module.VisualAnswerService = VisualAnswerService
