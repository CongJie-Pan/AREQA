"""Resolve planned image slots using the shared cache, providers and grounding rules."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from config import settings
from services.visual_grounding_agent import VisualBrief

logger = logging.getLogger(__name__)

from services.visual_answer.constants import (
    _NEGATIVE_CACHE_SENTINEL,
    _NEGATIVE_CACHE_TTL_SECONDS,
    _POSITIVE_CACHE_TTL_SECONDS,
)
from services.visual_answer.models import (
    ImageBlock,
    PlannedImageSlot,
)


async def _resolve_planned_image_blocks(
    service,
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
    for slot in planned_slots[: service.max_images]:
        logger.info(
            "visual.slot_resolution_started conversation_id=%s slot_id=%s",
            conversation_id,
            slot.slot_id,
        )
        cache_key = (
            service._visual_brief_cache_key(visual_brief)
            if visual_brief is not None
            else service._cache_key(slot.query, "diagram")
        )
        if visual_brief is not None:
            logger.info(
                "visual.cache_scope_selected conversation_id=%s scope=preflight visual_type=%s",
                conversation_id,
                visual_brief.visual_type,
            )
        cached_block = await service._read_cache(cache_key, conversation_id)
        if cached_block == _NEGATIVE_CACHE_SENTINEL:
            logger.info(
                "visual.slot_resolution_failed conversation_id=%s slot_id=%s reason=negative_cache",
                conversation_id,
                slot.slot_id,
            )
            continue
        if isinstance(cached_block, dict):
            resolved[slot.slot_id] = service._apply_slot_metadata(
                service._image_block_from_frontend(cached_block),
                slot,
            )
            logger.info(
                "visual.slot_resolution_completed conversation_id=%s slot_id=%s source=cache",
                conversation_id,
                slot.slot_id,
            )
            continue

        image_blocks = await service._resolve_images(
            user_msg=slot.query,
            visual_query=slot.query,
            visual_intent_text=service._slot_visual_intent(slot),
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
            selection_limit=service.max_images + 1 if visual_brief is not None else service.max_images,
        )
        if not image_blocks:
            await service._write_cache(
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
        block = service._apply_slot_metadata(image_blocks[0], slot)
        alternative_blocks = tuple(
            replace(
                service._apply_slot_metadata(alternative, slot),
                cache_key=cache_key,
                cache_ttl_seconds=_POSITIVE_CACHE_TTL_SECONDS,
                alternative_blocks=(),
            )
            for alternative in image_blocks[1 : service.max_images + 1]
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
