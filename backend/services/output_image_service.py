"""Coordinate output-image selection and vision understanding.

``OutputImageService`` is the orchestration-facing facade for illustrated
answers. It keeps candidate retrieval and metadata grounding in
``VisualAnswerService``/``VisualGroundingAgent`` while adding a separate
``VisualUnderstandingAgent`` step that actually sends the selected image to a
vision-capable model.
"""

from __future__ import annotations

import logging
from typing import Any

from config import settings
from services.visual_answer_service import ImageBlock, VisualAnswerService
from services.visual_understanding_agent import (
    VisualUnderstandingAgent,
    VisualUnderstandingResult,
)


logger = logging.getLogger(__name__)


class OutputImageService:
    """Facade that prepares verified output images for answer generation.

    The service intentionally preserves existing image retrieval behavior and
    owns only cross-agent coordination. Critical structured logs use
    ``conversation_id`` and bounded counts only; raw user text, prompts, model
    output, full URLs, credentials, and tokens are excluded from logs.
    """

    def __init__(
        self,
        *,
        understanding_agent: VisualUnderstandingAgent | None = None,
    ) -> None:
        """Initialize the output-image coordinator.

        Args:
            understanding_agent: Optional test double or custom vision agent.
        """

        self.understanding_agent = understanding_agent or VisualUnderstandingAgent()

    async def prepare_preflight_image_blocks(
        self,
        *,
        visual_answer_service: VisualAnswerService,
        user_msg: str,
        response_policy: Any,
        existing_web_results: list[dict[str, Any]] | None,
        tool_registry: Any,
        tool_budget: Any,
        user_id: str,
        conversation_id: str,
        model_client: Any = None,
        turn_plan: Any = None,
    ) -> dict[str, ImageBlock]:
        """Prepare verified images and enrich them with vision understanding.

        Args:
            visual_answer_service: Existing service that plans, retrieves,
                grounds, caches, and builds image blocks.
            user_msg: Latest user message. Sent only to downstream model calls,
                never logged by this service.
            response_policy: Current response policy from query classification.
            existing_web_results: Optional already-fetched web results.
            tool_registry: Existing tool registry for image-search fallback.
            tool_budget: Shared foreground tool budget.
            user_id: Current user id required by tool calls.
            conversation_id: Correlation id for structured logs.
            model_client: OpenAI-compatible async client.
            turn_plan: Optional deterministic turn plan metadata.

        Returns:
            A mapping from visual slot id to verified ``ImageBlock``. When
            visual understanding is disabled or unavailable, returns the
            original verified blocks so answer generation can continue.
        """

        blocks = await visual_answer_service.prepare_preflight_image_blocks(
            user_msg=user_msg,
            response_policy=response_policy,
            existing_web_results=existing_web_results,
            tool_registry=tool_registry,
            tool_budget=tool_budget,
            user_id=user_id,
            conversation_id=conversation_id,
            model_client=model_client,
            turn_plan=turn_plan,
        )
        if not blocks or not settings.enable_visual_understanding:
            return blocks

        enriched: dict[str, ImageBlock] = {}
        for slot_id, block in blocks.items():
            result = await self.understanding_agent.analyze(
                client=model_client,
                model=settings.model_visual_understanding,
                image_url=block.image_url,
                user_msg=user_msg,
                visual_brief=None,
                conversation_id=conversation_id,
            )
            enriched[slot_id] = self._apply_understanding(block, result)

        logger.info(
            "visual.output_images_prepared conversation_id=%s image_count=%s understanding_enabled=%s",
            conversation_id,
            len(enriched),
            settings.enable_visual_understanding,
        )
        return enriched

    @staticmethod
    def _apply_understanding(
        block: ImageBlock,
        result: VisualUnderstandingResult,
    ) -> ImageBlock:
        """Return ``block`` with vision-model analysis attached."""

        explanatory_caption = block.explanatory_caption
        if not explanatory_caption and result.summary:
            explanatory_caption = result.summary
        return ImageBlock(
            slot_id=block.slot_id,
            topic=block.topic,
            purpose=block.purpose,
            image_url=block.image_url,
            thumbnail_url=block.thumbnail_url,
            source_url=block.source_url,
            source_domain=block.source_domain,
            caption=block.caption,
            provider=block.provider,
            license=block.license,
            license_url=block.license_url,
            creator=block.creator,
            attribution_string=block.attribution_string,
            attribution_caption=block.attribution_caption,
            explanatory_caption=explanatory_caption,
            width=block.width,
            height=block.height,
            safety_status=block.safety_status,
            match_confidence=block.match_confidence,
            heuristic_score=block.heuristic_score,
            pedagogical_score=block.pedagogical_score,
            vision_summary=result.summary,
            visible_elements=result.visible_elements,
            how_to_read=result.how_to_read,
            vision_confidence=result.confidence,
            vision_limitations=result.limitations,
            vision_source=result.source,
        )
