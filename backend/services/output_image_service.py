"""Coordinate output-image selection and vision understanding.

``OutputImageService`` is the orchestration-facing facade for illustrated
answers. It keeps candidate retrieval and metadata grounding in
``VisualAnswerService``/``VisualGroundingAgent`` while adding a separate
``VisualUnderstandingAgent`` step that actually sends the selected image to a
vision-capable model.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from config import settings
from services.attachment_image_storage_service import AttachmentImageStorageService
from services.visual_answer_service import ImageBlock, VisualAnswerService
from services.visual_input_service import VisualInputService
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
        visual_input_service: VisualInputService | None = None,
        attachment_image_storage_service: AttachmentImageStorageService | None = None,
    ) -> None:
        """Initialize the output-image coordinator.

        Args:
            understanding_agent: Optional test double or custom vision agent.
            visual_input_service: Optional test double or custom image input
                preparation service.
            attachment_image_storage_service: Optional test double or custom
                persistence adapter for PDF attachment images.
        """

        self.understanding_agent = understanding_agent or VisualUnderstandingAgent()
        self.visual_input_service = visual_input_service or VisualInputService()
        self.attachment_image_storage_service = (
            attachment_image_storage_service or AttachmentImageStorageService()
        )

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
            A mapping from visual slot id to verified ``ImageBlock`` values
            enriched with usable vision evidence. When visual understanding is
            enabled but the selected image cannot be converted to a data URI or
            read by the model, the affected image is omitted so answer
            generation cannot place an ungrounded image.
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
            result: VisualUnderstandingResult | None = None
            understood_block = block
            candidate_blocks = [block, *block.alternative_blocks]
            budget_seconds = self._understanding_budget_seconds()
            loop = asyncio.get_running_loop()
            deadline = loop.time() + budget_seconds
            attempt_count = 0
            for candidate_index, candidate_block in enumerate(candidate_blocks):
                try:
                    candidate_result, candidate_attempts = await self._understand_image_block(
                        block=candidate_block,
                        user_msg=user_msg,
                        conversation_id=conversation_id,
                        model_client=model_client,
                        deadline=deadline,
                    )
                except TimeoutError:
                    logger.info(
                        "visual.output_understanding_budget_exhausted conversation_id=%s slot_id=%s budget_seconds=%.1f",
                        conversation_id,
                        slot_id,
                        budget_seconds,
                    )
                    break
                attempt_count += candidate_attempts
                if self._has_usable_understanding(candidate_result):
                    result = candidate_result
                    understood_block = candidate_block
                    if candidate_index > 0:
                        logger.info(
                            "visual.output_candidate_retry_succeeded conversation_id=%s slot_id=%s candidate_index=%s",
                            conversation_id,
                            slot_id,
                            candidate_index,
                        )
                    break
                if candidate_index < len(candidate_blocks) - 1:
                    logger.info(
                        "visual.output_candidate_retry conversation_id=%s slot_id=%s next_candidate_index=%s",
                        conversation_id,
                        slot_id,
                        candidate_index + 1,
                    )

            if result is None:
                logger.info(
                    "visual.output_image_omitted conversation_id=%s slot_id=%s reason=understanding_unavailable attempt_count=%s",
                    conversation_id,
                    slot_id,
                    attempt_count,
                )
                continue
            enriched_block = self._apply_understanding(understood_block, result)
            await visual_answer_service.commit_positive_cache(
                enriched_block,
                conversation_id=conversation_id,
            )
            enriched[slot_id] = enriched_block

        logger.info(
            "visual.output_images_prepared conversation_id=%s selected_image_count=%s understood_image_count=%s omitted_image_count=%s understanding_enabled=%s",
            conversation_id,
            len(blocks),
            len(enriched),
            len(blocks) - len(enriched),
            settings.enable_visual_understanding,
        )
        return enriched

    async def _understand_image_block(
        self,
        *,
        block: ImageBlock,
        user_msg: str,
        conversation_id: str,
        model_client: Any,
        deadline: float,
    ) -> tuple[VisualUnderstandingResult | None, int]:
        """Try to produce usable vision evidence for one selected image block.

        Args:
            block: Selected or fallback image block.
            user_msg: Latest user message sent only to the vision model.
            conversation_id: Correlation id for privacy-safe logs.
            model_client: OpenAI-compatible async client.
            deadline: Monotonic event-loop deadline shared by all candidates.

        Returns:
            Tuple of optional vision result and attempted URL count.

        Raises:
            TimeoutError: If the shared understanding budget is exhausted.

        Side Effects:
            May download selected image URLs and call the vision model. Logs
            safe reason/domain metadata only. HTTP 403-like image input failures
            temporarily penalize the image domain through ``VisualAnswerService``
            so future selection avoids repeatedly choosing blocked hosts.
        """

        attempted_urls = self._understanding_image_urls(block)
        if not attempted_urls:
            return None, 0
        loop = asyncio.get_running_loop()
        attempts = 0
        for image_url in attempted_urls:
            attempts += 1
            try:
                remaining_seconds = deadline - loop.time()
                if remaining_seconds <= 0:
                    raise TimeoutError
                image_input = await asyncio.wait_for(
                    self.visual_input_service.prepare_image_part(
                        image_url=image_url,
                        conversation_id=conversation_id,
                    ),
                    timeout=remaining_seconds,
                )
                input_source = getattr(image_input, "source", "unknown")
                if input_source != "data_uri":
                    unavailable_reason = getattr(image_input, "reason", None) or "unknown"
                    logger.info(
                        "visual.output_understanding_input_unavailable conversation_id=%s slot_id=%s source_domain=%s input_source=%s reason=%s",
                        conversation_id,
                        block.slot_id,
                        self._safe_domain(image_url) or "unknown",
                        input_source,
                        unavailable_reason,
                    )
                    if unavailable_reason in {"HTTPStatusError:403", "HTTPStatusError:401"}:
                        VisualAnswerService.mark_inaccessible_image_domain(
                            image_url,
                            reason=unavailable_reason,
                        )
                    continue
                remaining_seconds = deadline - loop.time()
                if remaining_seconds <= 0:
                    raise TimeoutError
                candidate_result = await asyncio.wait_for(
                    self.understanding_agent.analyze(
                        client=model_client,
                        model=settings.model_visual_understanding,
                        image_url=image_url,
                        image_part=image_input.content_part,
                        user_msg=user_msg,
                        visual_brief=None,
                        conversation_id=conversation_id,
                    ),
                    timeout=remaining_seconds,
                )
            except TimeoutError:
                raise
            except Exception as exc:
                logger.info(
                    "visual.output_understanding_attempt_failed conversation_id=%s slot_id=%s reason=%s",
                    conversation_id,
                    block.slot_id,
                    type(exc).__name__,
                )
                continue
            if self._has_usable_understanding(candidate_result):
                return candidate_result, attempts
        return None, attempts

    async def prepare_attachment_image_blocks(
        self,
        *,
        candidates: list[Any] | tuple[Any, ...],
        user_msg: str,
        conversation_id: str,
        model_client: Any = None,
    ) -> dict[str, ImageBlock]:
        """Prepare verified image blocks from request-scoped attachment visuals.

        Args:
            candidates: PDF visual candidates from attachment processing.
            user_msg: Latest user message. Sent to the vision model for task
                context but never logged by this service.
            conversation_id: Correlation id for safe structured logs.
            model_client: OpenAI-compatible async client for vision analysis.

        Returns:
            Mapping from slot id to image blocks. When visual understanding is
            enabled, candidates without usable vision output are omitted so the
            answer model cannot cite unseen attachment pixels.

        Side Effects:
            May call the configured vision model with in-memory data URI images.
            Logs only candidate counts, slot ids, and bounded reason codes.
        """

        if not candidates:
            return {}

        blocks: dict[str, ImageBlock] = {}
        for candidate in list(candidates)[:4]:
            if not hasattr(candidate, "to_image_block"):
                continue
            block = candidate.to_image_block()
            if settings.enable_visual_understanding:
                try:
                    result = await self.understanding_agent.analyze(
                        client=model_client,
                        model=settings.model_visual_understanding,
                        image_url=block.image_url,
                        image_part={
                            "type": "image_url",
                            "image_url": {"url": block.image_url},
                        },
                        user_msg=user_msg,
                        visual_brief=None,
                        conversation_id=conversation_id,
                    )
                except Exception as exc:
                    logger.info(
                        "visual.attachment_understanding_failed_soft conversation_id=%s slot_id=%s reason=%s",
                        conversation_id,
                        block.slot_id,
                        type(exc).__name__,
                    )
                    result = None
                if not self._has_usable_understanding(result):
                    logger.info(
                        "visual.attachment_understanding_failed_soft conversation_id=%s slot_id=%s reason=understanding_unavailable",
                        conversation_id,
                        block.slot_id,
                    )
                else:
                    block = self._apply_understanding(block, result)
            block = await self.attachment_image_storage_service.persist_pdf_image_block(
                block=block,
                conversation_id=conversation_id,
            )
            blocks[block.slot_id] = block

        logger.info(
            "visual.attachment_images_prepared conversation_id=%s candidate_count=%s selected_image_count=%s understanding_enabled=%s",
            conversation_id,
            len(candidates),
            len(blocks),
            settings.enable_visual_understanding,
        )
        return blocks

    def _understanding_budget_seconds(self) -> float:
        """Return one latency budget shared by all URLs for a selected image.

        The budget preserves the previous worst-case foreground latency: one
        image download timeout plus one vision-model timeout. Thumbnail retry
        consumes only time left by the original attempt instead of doubling
        time-to-first-answer.

        Returns:
            Positive timeout in seconds for all understanding attempts.
        """

        input_timeout = float(getattr(self.visual_input_service, "timeout_seconds", 3.0))
        model_timeout = float(
            getattr(
                self.understanding_agent,
                "timeout_seconds",
                settings.visual_understanding_timeout_seconds,
            )
        )
        return max(0.1, input_timeout + model_timeout)

    @staticmethod
    def _understanding_image_urls(block: ImageBlock) -> list[str]:
        """Return unique image URLs to try for visual understanding.

        The original image remains the preferred model input. A distinct
        thumbnail can still represent the same selected image when a source
        blocks server-side access to its full-resolution asset.

        Args:
            block: Selected and grounded image metadata.

        Returns:
            Original and thumbnail URLs in priority order with blanks and
            duplicates removed.
        """

        urls: list[str] = []
        for value in (block.image_url, block.thumbnail_url):
            image_url = str(value or "").strip()
            if image_url and image_url not in urls:
                urls.append(image_url)
        return urls

    @staticmethod
    def _safe_domain(image_url: str) -> str:
        """Extract a safe domain label for output-image coordination logs.

        Args:
            image_url: Candidate image URL considered for understanding.

        Returns:
            Lowercase host without a leading ``www.`` prefix.

        Side Effects:
            None. This helper intentionally avoids returning paths or query
            strings because image URLs can contain provider identifiers.
        """

        return urlparse(str(image_url or "")).netloc.lower().removeprefix("www.")

    @staticmethod
    def _has_usable_understanding(result: VisualUnderstandingResult | None) -> bool:
        """Return whether vision output is sufficient for grounded answer prose.

        Args:
            result: Bounded output from ``VisualUnderstandingAgent``.

        Returns:
            ``True`` only for model-observed summaries with at least one
            concrete visible element or reading instruction.
        """

        return bool(
            result
            and result.source == "vision_model"
            and result.summary.strip()
            and (result.visible_elements or result.how_to_read)
        )

    @staticmethod
    def _apply_understanding(
        block: ImageBlock,
        result: VisualUnderstandingResult,
    ) -> ImageBlock:
        """Return ``block`` with vision-model analysis attached."""

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
            # Vision summaries ground answer generation but are not localized,
            # reviewed user-facing copy. Only explicit captions may reach UI.
            explanatory_caption=block.explanatory_caption,
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
            cache_key=block.cache_key,
            cache_ttl_seconds=block.cache_ttl_seconds,
            alternative_blocks=(),
            storage_bucket=block.storage_bucket,
            storage_path=block.storage_path,
            storage_expires_at=block.storage_expires_at,
            transient=block.transient,
        )
