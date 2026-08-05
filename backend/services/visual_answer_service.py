"""Build structured visual blocks for illustrated assistant answers.

This module owns the privacy boundary for visual answer enrichment. It may use
the latest user message to query a search provider, but structured logs emitted
here never include raw user text, generated answer text, prompts, credentials,
or image URLs. Public output is limited to verified display metadata.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from services.query_policy_service import ResponsePolicy, TaskIntent

logger = logging.getLogger(__name__)

_VISUAL_KEYWORDS = (
    "圖",
    "圖片",
    "圖解",
    "示意圖",
    "範例圖",
    "diagram",
    "image",
    "visual",
    "chart",
    "plot",
)

_IMAGE_META_PATTERN = re.compile(
    r'<meta\s+(?:property|name)=["\'](?:og:image|twitter:image)["\']\s+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True, slots=True)
class ImageBlock:
    """Verified image display metadata for the frontend.

    Args:
        slot_id: Stable per-answer slot identifier.
        topic: Short display topic derived from the source title or query.
        purpose: Visual purpose used by the frontend for future styling.
        image_url: Direct image URL resolved from source page metadata.
        thumbnail_url: Optional thumbnail URL. Defaults to the direct image.
        source_url: Source page URL used for attribution and click-through.
        source_domain: Safe display domain extracted from source_url.
        caption: User-visible caption.
        license: Best-effort license label.
        safety_status: Backend safety gate result.
        match_confidence: Conservative confidence score from metadata matching.
    """

    slot_id: str
    topic: str
    purpose: str
    image_url: str
    thumbnail_url: str
    source_url: str
    source_domain: str
    caption: str
    license: str
    safety_status: str
    match_confidence: float

    def to_frontend(self) -> dict[str, Any]:
        """Return the camelCase wire shape consumed by the frontend."""

        return {
            "type": "image_block",
            "slotId": self.slot_id,
            "topic": self.topic,
            "purpose": self.purpose,
            "imageUrl": self.image_url,
            "thumbnailUrl": self.thumbnail_url,
            "sourceUrl": self.source_url,
            "sourceDomain": self.source_domain,
            "caption": self.caption,
            "license": self.license,
            "safetyStatus": self.safety_status,
            "matchConfidence": self.match_confidence,
        }


class VisualAnswerService:
    """Create paragraph and image blocks without changing text streaming.

    The service is intentionally fail-soft: visual enrichment must never prevent
    the answer stream from completing. Expected structured logs:
    - INFO `visual.slots_planned`: safe slot count and reason code.
    - INFO `visual.image_selected`: safe source domain and confidence bucket.
    - INFO `visual.image_omitted`: safe omission reason.
    - WARNING `visual.enrichment_failed`: unexpected exception type only.
    """

    def __init__(self, *, page_timeout_seconds: float = 2.0, max_images: int = 2) -> None:
        """Initialize the visual enrichment service.

        Args:
            page_timeout_seconds: Timeout for source-page metadata extraction.
            max_images: Hard cap for image blocks per answer.
        """

        self.page_timeout_seconds = page_timeout_seconds
        self.max_images = max(0, min(max_images, 2))

    def should_enrich(self, response_policy: ResponsePolicy, user_msg: str) -> bool:
        """Return whether this turn should attempt visual enrichment."""

        normalized = user_msg.lower()
        explicit_visual_request = any(keyword in normalized for keyword in _VISUAL_KEYWORDS)
        return bool(
            self.max_images > 0
            and (
                explicit_visual_request
                or response_policy.task_intent == TaskIntent.EXPLAIN_TEXT
            )
        )

    async def build_answer_blocks(
        self,
        *,
        answer_text: str,
        user_msg: str,
        response_policy: ResponsePolicy,
        tool_registry: Any,
        tool_budget: Any,
        user_id: str,
        conversation_id: str,
    ) -> list[dict[str, Any]]:
        """Build frontend answer blocks for the completed answer text.

        Args:
            answer_text: Completed public assistant answer.
            user_msg: Latest user message, used only for retrieval query creation.
            response_policy: Structured policy selected earlier in orchestration.
            tool_registry: Existing tool registry for web search execution.
            tool_budget: Current run tool budget.
            user_id: Current user identifier for tool cache scoping.
            conversation_id: Current conversation identifier for safe logs.

        Returns:
            Ordered paragraph and image blocks. Returns an empty list when visual
            enrichment is not applicable or no verified image can be found.
        """

        paragraphs = self._split_paragraphs(answer_text)
        if not paragraphs or not self.should_enrich(response_policy, user_msg):
            return []

        api_key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
        if not api_key:
            logger.info(
                "visual.image_omitted conversation_id=%s reason=missing_search_api_key",
                conversation_id,
            )
            return []

        logger.info(
            "visual.slots_planned conversation_id=%s slot_count=%s reason=%s",
            conversation_id,
            min(self.max_images, len(paragraphs)),
            "policy_or_explicit_visual",
        )

        try:
            results = await self._search_image_sources(
                user_msg=user_msg,
                tool_registry=tool_registry,
                tool_budget=tool_budget,
                user_id=user_id,
                conversation_id=conversation_id,
                api_key=api_key,
            )
            image_blocks = await self._resolve_images(results, conversation_id)
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
            return []

        return self._interleave_blocks(paragraphs, image_blocks)

    async def _search_image_sources(
        self,
        *,
        user_msg: str,
        tool_registry: Any,
        tool_budget: Any,
        user_id: str,
        conversation_id: str,
        api_key: str,
    ) -> list[dict[str, Any]]:
        """Run the existing web search tool with an image-oriented query."""

        query = f"{user_msg} diagram example image"
        tool_result = await tool_registry.execute(
            "web_search",
            {
                "query": query,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "api_key": api_key,
                "max_results": 5,
                "search_context_size": "low",
                "redis_url": os.environ.get("REDIS_URL", "redis://localhost:6379"),
            },
            tool_budget,
        )
        return list(tool_result.content.get("results", []))

    async def _resolve_images(
        self,
        results: list[dict[str, Any]],
        conversation_id: str,
    ) -> list[ImageBlock]:
        """Resolve candidate source pages into verified image blocks."""

        blocks: list[ImageBlock] = []
        async with httpx.AsyncClient(timeout=self.page_timeout_seconds, follow_redirects=True) as client:
            for result in results:
                if len(blocks) >= self.max_images:
                    break
                block = await self._block_from_result(client, result, len(blocks) + 1)
                if not block:
                    continue
                blocks.append(block)
                logger.info(
                    "visual.image_selected conversation_id=%s source_domain=%s confidence_bucket=%s",
                    conversation_id,
                    block.source_domain,
                    "medium",
                )
        return blocks

    async def _block_from_result(
        self,
        client: httpx.AsyncClient,
        result: dict[str, Any],
        index: int,
    ) -> ImageBlock | None:
        """Extract one OpenGraph/Twitter image from a search result page."""

        source_url = str(result.get("url") or "").strip()
        parsed_source = urlparse(source_url)
        if parsed_source.scheme not in {"http", "https"} or not parsed_source.netloc:
            return None

        response = await client.get(source_url)
        if response.status_code >= 400:
            return None

        html = response.text[:80_000]
        match = _IMAGE_META_PATTERN.search(html)
        if not match:
            return None

        image_url = urljoin(source_url, match.group(1).strip())
        parsed_image = urlparse(image_url)
        if parsed_image.scheme not in {"http", "https"} or not parsed_image.netloc:
            return None

        title = self._clean_text(str(result.get("title") or "") or self._extract_title(html))
        domain = parsed_source.netloc.replace("www.", "")
        caption = title or f"Illustration from {domain}"
        return ImageBlock(
            slot_id=f"visual-{index}",
            topic=caption[:80],
            purpose="diagram",
            image_url=image_url,
            thumbnail_url=image_url,
            source_url=source_url,
            source_domain=domain,
            caption=caption[:140],
            license="unknown",
            safety_status="pass",
            match_confidence=0.6,
        )

    @staticmethod
    def _split_paragraphs(answer_text: str) -> list[str]:
        """Split completed answer Markdown into non-empty paragraph blocks."""

        return [part.strip() for part in re.split(r"\n{2,}", answer_text) if part.strip()]

    @staticmethod
    def _extract_title(html: str) -> str:
        """Extract a plain page title from HTML."""

        match = _TITLE_PATTERN.search(html)
        return match.group(1) if match else ""

    @staticmethod
    def _clean_text(text: str) -> str:
        """Collapse whitespace for safe captions."""

        return re.sub(r"\s+", " ", text).strip()

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
