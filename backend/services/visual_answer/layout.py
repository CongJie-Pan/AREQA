"""Layout helpers for visual answer blocks.

The mixin validates model-planned visual slots and interleaves paragraph/image
blocks using the existing frontend answer-block contract. It performs no logging
because it may handle model-provided captions and queries that should stay out
of terminal logs.
"""

from __future__ import annotations

import re
from typing import Any

from services.visual_answer.models import ImageBlock, PlannedImageSlot


class VisualAnswerLayoutMixin:
    """Validate planned slots and interleave visual blocks into paragraphs."""

    @classmethod
    def _planned_slots_from_payload(
        cls,
        payload: list[dict[str, Any]],
        *,
        require_query: bool = True,
        max_slots: int = 2,
    ) -> list[PlannedImageSlot]:
        """Validate model-planned image slot payloads from the stream accumulator.

        Args:
            payload: Untrusted structured marker payload from the answer model.
            require_query: Whether an image search query is required. Verified
                preflight markers only need a slot id because retrieval already
                happened before generation.
            max_slots: Maximum number of marker payloads to accept. Web-search
                image requests use the service's normal cap; preverified PDF
                inventories may allow more already-rendered attachment images.

        Returns:
            A capped list of safe planned slots. Raw query and caption content
            are retained only for retrieval/display and are not logged here.
        """

        slots: list[PlannedImageSlot] = []
        seen: set[str] = set()
        bounded_max_slots = max(0, min(int(max_slots or 0), 4))
        for index, item in enumerate(payload[:bounded_max_slots]):
            slot_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(item.get("slot_id") or f"img_{index + 1}"))[:40]
            query = cls._clean_text(str(item.get("query") or ""))[:120]
            if not slot_id or slot_id in seen or (require_query and not query):
                continue
            seen.add(slot_id)
            caption_hint = cls._clean_text(str(item.get("caption_hint") or ""))[:180]
            anchor_after_paragraph = max(0, cls._optional_int(item.get("anchor_after_paragraph")) or 0)
            slots.append(
                PlannedImageSlot(
                    slot_id=slot_id,
                    query=query or slot_id,
                    caption_hint=caption_hint,
                    anchor_after_paragraph=anchor_after_paragraph,
                )
            )
        return slots

    @staticmethod
    def _pending_block(slot: PlannedImageSlot) -> dict[str, Any]:
        """Return a frontend pending block for unresolved planned visuals."""

        return {
            "type": "image_block",
            "slotId": slot.slot_id,
            "topic": slot.caption_hint or "Visual aid",
            "purpose": "diagram",
            "imageUrl": "",
            "thumbnailUrl": "",
            "sourceUrl": "",
            "sourceDomain": "",
            "caption": slot.caption_hint or "正在尋找合適圖片",
            "safetyStatus": "unavailable",
            "matchConfidence": 0.0,
            "status": "pending",
        }

    @classmethod
    def _interleave_pending_slots(cls, paragraphs: list[str], planned_slots: list[PlannedImageSlot]) -> list[dict[str, Any]]:
        """Interleave pending image placeholders at planned paragraph anchors."""

        return cls._interleave_blocks_at_planned_slots(paragraphs, planned_slots, {})

    @classmethod
    def _interleave_blocks_at_planned_slots(
        cls,
        paragraphs: list[str],
        planned_slots: list[PlannedImageSlot],
        image_blocks: dict[str, ImageBlock],
        *,
        include_pending: bool = True,
    ) -> list[dict[str, Any]]:
        """Interleave resolved or pending image blocks after planned anchors."""

        output: list[dict[str, Any]] = []
        slots_by_anchor: dict[int, list[PlannedImageSlot]] = {}
        max_anchor = max(len(paragraphs) - 1, 0)
        for slot in planned_slots:
            anchor = min(max(slot.anchor_after_paragraph, 0), max_anchor)
            slots_by_anchor.setdefault(anchor, []).append(slot)
        for paragraph_index, paragraph in enumerate(paragraphs):
            output.append({"type": "paragraph", "text": paragraph})
            for slot in slots_by_anchor.get(paragraph_index, []):
                block = image_blocks.get(slot.slot_id)
                if block:
                    output.append(block.to_frontend())
                elif include_pending:
                    output.append(cls._pending_block(slot))
        return output

    @staticmethod
    def _interleave_blocks(paragraphs: list[str], image_blocks: list[ImageBlock]) -> list[dict[str, Any]]:
        """Interleave image blocks after early paragraphs in stable order."""

        output: list[dict[str, Any]] = []
        image_index = 0
        for paragraph_index, paragraph in enumerate(paragraphs):
            output.append({"type": "paragraph", "text": paragraph})
            if image_index < len(image_blocks) and paragraph_index < 2:
                output.append(image_blocks[image_index].to_frontend())
                image_index += 1
        return output
