"""Planned visual slot compatibility helpers.

This mixin owns slot metadata application and paper-section observability for
preverified PDF visuals. Logs use safe slot ids, section labels, and
conversation ids only; raw prompts, user text, image URLs, and model output must
not be emitted.
"""

from __future__ import annotations

import logging

from services.query_policy.classifier import AttachmentTask, ResponsePolicy
from services.visual_answer.models import ImageBlock, PlannedImageSlot

logger = logging.getLogger(__name__)


class VisualAnswerSlotMixin:
    """Apply planned-slot metadata and emit safe paper visual diagnostics."""

    @staticmethod
    def _apply_slot_metadata(block: ImageBlock, slot: PlannedImageSlot) -> ImageBlock:
        """Return a resolved image block anchored to a planned visual slot."""

        return ImageBlock(
            slot_id=slot.slot_id,
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
            explanatory_caption=slot.caption_hint or block.explanatory_caption,
            width=block.width,
            height=block.height,
            safety_status=block.safety_status,
            match_confidence=block.match_confidence,
            heuristic_score=block.heuristic_score,
            pedagogical_score=block.pedagogical_score,
            vision_summary=block.vision_summary,
            visible_elements=block.visible_elements,
            how_to_read=block.how_to_read,
            vision_confidence=block.vision_confidence,
            vision_limitations=block.vision_limitations,
            vision_source=block.vision_source,
            cache_key=block.cache_key,
            cache_ttl_seconds=block.cache_ttl_seconds,
            alternative_blocks=block.alternative_blocks,
            storage_bucket=block.storage_bucket,
            storage_path=block.storage_path,
            storage_expires_at=block.storage_expires_at,
            placement_section=block.placement_section,
            planner_hint=block.planner_hint,
            transient=block.transient,
        )

    @staticmethod
    def _log_missing_paper_required_sections(
        conversation_id: str,
        response_policy: ResponsePolicy,
        planned_slots: list[PlannedImageSlot],
        preverified_image_blocks: dict[str, ImageBlock],
    ) -> None:
        """Log paper sections that had a verified visual but no used marker."""

        attachment_task = getattr(
            response_policy.attachment_task,
            "value",
            response_policy.attachment_task,
        )
        if attachment_task != AttachmentTask.PAPER_AUTO_EXPLAIN.value:
            return
        used_slot_ids = {slot.slot_id for slot in planned_slots}
        required_sections = ("研究方法", "實驗設計與過程", "實驗結果")
        for required_section in required_sections:
            available_ids = [
                slot_id
                for slot_id, block in preverified_image_blocks.items()
                if block.placement_section == required_section
            ]
            if not available_ids:
                continue
            if any(slot_id in used_slot_ids for slot_id in available_ids):
                continue
            logger.info(
                "visual.paper_required_section_missing conversation_id=%s section=%s available=True used=False",
                conversation_id,
                required_section,
            )

    @staticmethod
    def _slot_visual_intent(slot: PlannedImageSlot) -> str:
        """Combine slot query and caption intent for visual grounding."""

        parts = [slot.query.strip(), slot.caption_hint.strip()]
        return "\n".join(part for part in parts if part)


# Moved methods still reference the historical facade name in their globals.
