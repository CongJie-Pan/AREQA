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
from services.query_policy_service import ResponsePolicy, VisualSupport
from services.visual_affordance_registry import match_visual_affordance
from services.visual_grounding_agent import VisualBrief, VisualGroundingAgent

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
_NEGATIVE_CACHE_SENTINEL = {"status": "negative"}
_VISUAL_CACHE_VERSION = "v6"
_VISUAL_CACHE_CAPABILITY_SCHEMA = "capability_v1"
_NEGATIVE_CACHE_TTL_SECONDS = 21600
_POSITIVE_CACHE_TTL_SECONDS = 2592000
_INACCESSIBLE_IMAGE_DOMAIN_TTL_SECONDS = 21600
_INACCESSIBLE_IMAGE_DOMAIN_CACHE: dict[str, int] = {}
_PROVIDER_PRIORITY = {
    "perplexity_images": 0.3,
    "serpapi_images": 0.28,
    "tavily_images": 0.26,
    "wikimedia": 0.25,
    "openverse": 0.2,
    "og_image": 0.05,
}
_PLACEHOLDER_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
}
_IMAGE_CDN_DOMAIN_SUFFIXES = (
    "gstatic.com",
    "googleusercontent.com",
    "ggpht.com",
)
_PURPOSE_TERMS = {
    "diagram",
    "chart",
    "schematic",
    "plot",
    "graph",
    "illustration",
    "示意圖",
    "圖解",
}
_VISUAL_TYPE_HINTS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "map",
        ("地圖", "地图", "戰場", "战场", "戰況", "战况", "map", "battlefield"),
        "educational labeled map",
    ),
    ("chart", ("圖表", "图表", "統計", "统计", "chart", "graph", "plot"), "educational chart"),
    (
        "diagram",
        ("流程", "架構", "结构", "示意", "圖解", "图解", "diagram", "flow"),
        "educational explanatory diagram",
    ),
)
_TRUSTED_SOURCE_DOMAINS = (
    "commons.wikimedia.org",
    "wikimedia.org",
    "wikipedia.org",
    "worldhistory.org",
    "loc.gov",
    "archives.gov",
    "iwm.org.uk",
    "ushmm.org",
    ".edu",
    ".museum",
)
_LOW_QUALITY_SOURCE_DOMAINS = (
    "pinterest.",
    "reddit.com",
    "taobao.com",
    "tmall.",
    "carousell.",
    "quizlet.com",
    "teacherspayteachers.com",
    "studocu.com",
)
_UNSTABLE_IMAGE_INPUT_DOMAINS = {
    "researchgate.net",
}
_NEGATIVE_TERMS = {
    "logo",
    "icon",
    "placeholder",
    "avatar",
    "watermark",
    "sprite",
}
_DEFAULT_VISUAL_USER_AGENT = "AREQA/0.1 visual-answer-retrieval"
_VISUAL_QUERY_REWRITE_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "chinese_temple_church_comparison",
        re.compile(r"(寺廟.*教會|教會.*寺廟|temple.*church|church.*temple)", re.IGNORECASE),
        "Chinese temple folk religion Christian church social organization comparison diagram",
    ),
)


@dataclass(frozen=True, slots=True)
class VisualPreflightDecision:
    """Privacy-safe decision metadata for visual preflight cost gating.

    Args:
        allowed: Whether provider lookup or PDF rendering may run this turn.
        trigger: Stable reason bucket that made the gate allow or deny work.
        visual_support: EDF response-policy visual support enum value.
        visual_reason: EDF response-policy visual reason enum value.
        explicit_visual_request: Whether the user explicitly asked for visual
            output using a bounded keyword allowlist.
        known_visual_affordance: Whether a deterministic educational affordance
            matched a graph-heavy concept.
        max_images: Effective service image cap.

    Side Effects:
        None. Callers own structured logging so they can add request-scoped
        correlation fields without passing raw user text into log metadata.
    """

    allowed: bool
    trigger: str
    visual_support: str
    visual_reason: str
    explicit_visual_request: bool
    known_visual_affordance: bool
    max_images: int


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
        provider: Source provider that produced the image.
        license: Best-effort license label.
        license_url: Optional provider license URL.
        creator: Optional creator/author display string.
        attribution_string: Optional attribution required by the provider.
        attribution_caption: Short factual caption shown near attribution.
        explanatory_caption: Pedagogical caption tied to the visible image.
        width: Optional image width.
        height: Optional image height.
        safety_status: Backend safety gate result.
        match_confidence: Conservative confidence score from metadata matching.
        heuristic_score: Cheap metadata-only relevance score.
        pedagogical_score: Cheap instructional usefulness score.
        vision_summary: Optional vision-model summary of visible content.
        visible_elements: Optional bounded list of visible image elements.
        how_to_read: Optional ordered reading guidance from the vision model.
        vision_confidence: Optional confidence label from the vision model.
        vision_limitations: Optional bounded uncertainty notes.
        vision_source: Stable source label for image-understanding metadata.
        cache_key: Internal cache key that may be committed only after output
            understanding succeeds. This field is intentionally not serialized
            to the frontend.
        cache_ttl_seconds: Internal positive-cache TTL paired with cache_key.
        alternative_blocks: Internal fallback image blocks for the same planned
            slot. These are attempted when the initially selected image cannot
            be downloaded or understood.
        storage_bucket: Optional Supabase Storage bucket for persisted
            attachment-derived images.
        storage_path: Optional Supabase Storage object path for persisted
            attachment-derived images.
        storage_expires_at: Unix timestamp when a signed image URL expires.
        transient: Whether the block contains request-scoped attachment pixels
            that clients must not write to durable stores.
    """

    slot_id: str
    topic: str
    purpose: str
    image_url: str
    thumbnail_url: str
    source_url: str
    source_domain: str
    caption: str
    provider: str = "og_image"
    license: str = "unknown"
    license_url: str = ""
    creator: str = ""
    attribution_string: str = ""
    attribution_caption: str = ""
    explanatory_caption: str = ""
    width: int | None = None
    height: int | None = None
    safety_status: str = "pass"
    match_confidence: float = 0.0
    heuristic_score: float = 0.0
    pedagogical_score: float = 0.0
    vision_summary: str = ""
    visible_elements: tuple[str, ...] = ()
    how_to_read: tuple[str, ...] = ()
    vision_confidence: str = "unknown"
    vision_limitations: tuple[str, ...] = ()
    vision_source: str = "unavailable"
    cache_key: str = ""
    cache_ttl_seconds: int = 0
    alternative_blocks: tuple["ImageBlock", ...] = ()
    storage_bucket: str = ""
    storage_path: str = ""
    storage_expires_at: int | None = None
    transient: bool = False

    def to_frontend(self) -> dict[str, Any]:
        """Return the camelCase wire shape consumed by the frontend."""

        payload: dict[str, Any] = {
            "type": "image_block",
            "slotId": self.slot_id,
            "topic": self.topic,
            "purpose": self.purpose,
            "imageUrl": self.image_url,
            "thumbnailUrl": self.thumbnail_url,
            "sourceUrl": self.source_url,
            "sourceDomain": self.source_domain,
            "caption": self.caption,
            "provider": self.provider,
            "tier": self.provider,
            "license": self.license,
            "status": "resolved",
            "safetyStatus": self.safety_status,
            "matchConfidence": self.match_confidence,
            "heuristicScore": self.heuristic_score,
            "pedagogicalScore": self.pedagogical_score,
        }
        if self.attribution_caption:
            payload["attributionCaption"] = self.attribution_caption
        if self.explanatory_caption:
            payload["explanatoryCaption"] = self.explanatory_caption
        if self.license_url:
            payload["licenseUrl"] = self.license_url
        if self.creator:
            payload["creator"] = self.creator
        if self.attribution_string:
            payload["attributionString"] = self.attribution_string
        if self.vision_summary:
            payload["visionSummary"] = self.vision_summary
        if self.visible_elements:
            payload["visibleElements"] = list(self.visible_elements)
        if self.how_to_read:
            payload["howToRead"] = list(self.how_to_read)
        if self.vision_confidence and self.vision_confidence != "unknown":
            payload["visionConfidence"] = self.vision_confidence
        if self.vision_limitations:
            payload["visionLimitations"] = list(self.vision_limitations)
        if self.vision_source and self.vision_source != "unavailable":
            payload["visionSource"] = self.vision_source
        if self.storage_bucket:
            payload["storageBucket"] = self.storage_bucket
        if self.storage_path:
            payload["storagePath"] = self.storage_path
        if self.storage_expires_at is not None:
            payload["storageExpiresAt"] = self.storage_expires_at
        if self.transient:
            payload["transient"] = True
        if self.width is not None:
            payload["width"] = self.width
        if self.height is not None:
            payload["height"] = self.height
        return payload


@dataclass(frozen=True, slots=True)
class ImageCandidate:
    """Provider-normalized image candidate before final ranking.

    Args:
        provider: Candidate provider identifier.
        image_url: Direct image URL.
        thumbnail_url: Thumbnail URL for card rendering.
        source_url: Attribution/click-through URL.
        title: Candidate title.
        caption: Candidate caption or description.
        license: Provider license label.
        license_url: Optional license URL.
        creator: Optional creator/author.
        attribution_string: Optional attribution text.
        width: Optional width.
        height: Optional height.
    """

    provider: str
    image_url: str
    thumbnail_url: str
    source_url: str
    title: str
    caption: str
    license: str
    license_url: str = ""
    creator: str = ""
    attribution_string: str = ""
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True, slots=True)
class PlannedImageSlot:
    """Validated internal visual placement request from the answer model.

    Args:
        slot_id: Stable slot identifier used to anchor the resolved block.
        query: Provider-search query. This is model output and must not be
            written to logs.
        caption_hint: Optional pedagogical intent for the visual.
        anchor_after_paragraph: Zero-based paragraph index after which the
            image should be inserted.
    """

    slot_id: str
    query: str
    caption_hint: str = ""
    anchor_after_paragraph: int = 0


class VisualAnswerService:
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
        agent_allows_visuals = response_policy.visual_support in {
            VisualSupport.OPTIONAL,
            VisualSupport.REQUIRED,
        }
        allowed = bool(
            self.max_images > 0
            and (
                explicit_visual_request
                or known_visual_affordance
                or agent_allows_visuals
            )
        )
        if self.max_images <= 0:
            trigger = "disabled"
        elif explicit_visual_request:
            trigger = "explicit_visual_request"
        elif known_visual_affordance:
            trigger = "known_visual_affordance"
        elif agent_allows_visuals:
            trigger = "response_policy"
        else:
            trigger = "policy_gate"
        return VisualPreflightDecision(
            allowed=allowed,
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
            transient=block.transient,
        )

    @staticmethod
    def _slot_visual_intent(slot: PlannedImageSlot) -> str:
        """Combine slot query and caption intent for visual grounding."""

        parts = [slot.query.strip(), slot.caption_hint.strip()]
        return "\n".join(part for part in parts if part)

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
        *,
        user_msg: str,
        existing_web_results: list[dict[str, Any]] | None,
        tool_registry: Any,
        tool_budget: Any,
        user_id: str,
        conversation_id: str,
        visual_query: str | None = None,
        visual_intent_text: str | None = None,
        model_client: Any = None,
        visual_brief: VisualBrief | None = None,
        allow_og_fallback: bool = True,
        allow_open_provider_fallback: bool = True,
        selection_limit: int | None = None,
    ) -> list[ImageBlock]:
        """Resolve provider images with caller-controlled fallback breadth.

        The provider waterfall keeps the existing verified-image privacy and
        safety contract: every external provider only yields normalized
        ``ImageCandidate`` metadata, and this service still owns scoring,
        visual grounding, cache writes, and final ``ImageBlock`` creation.
        Structured logs emitted from this path use stable provider identifiers,
        correlation ids, counts, and safe reason codes only; they must not log
        raw prompts, full URLs, credentials, or model output.

        Args:
            selection_limit: Optional internal candidate count. Preflight can
                ask for more candidates than the visible image limit so output
                understanding may retry if the primary image host blocks
                backend-side download.
        """

        resolved_query = visual_query or self._visual_search_query(user_msg)[0]
        visual_context = visual_intent_text or resolved_query
        blocks: list[ImageBlock] = []
        if visual_brief is not None and settings.enable_visual_preflight_parallel_providers:
            return await self._resolve_preflight_parallel_images(
                resolved_query=resolved_query,
                visual_context=visual_context,
                conversation_id=conversation_id,
                model_client=model_client,
                visual_brief=visual_brief,
                allow_open_provider_fallback=allow_open_provider_fallback,
                selection_limit=selection_limit,
            )

        if settings.enable_perplexity_visual_search:
            async def query_perplexity_images(
                client: httpx.AsyncClient,
                query: str,
                conversation_id: str,
            ) -> list[ImageCandidate]:
                return await self._query_perplexity_images(client, query, conversation_id, visual_brief)

            async with httpx.AsyncClient(
                timeout=settings.perplexity_visual_search_timeout_seconds,
                follow_redirects=True,
            ) as client:
                candidates = await self._query_provider_candidates(
                    provider="perplexity_images",
                    query_func=query_perplexity_images,
                    client=client,
                    query=resolved_query,
                    conversation_id=conversation_id,
                )
                block = await self._select_image_block(
                    candidates,
                    resolved_query,
                    "perplexity_images",
                    conversation_id,
                    visual_context,
                    model_client,
                    visual_brief,
                )
                if block:
                    self._log_image_block_selected(conversation_id, block, "perplexity_images")
                    return [block]

        if not allow_open_provider_fallback:
            logger.info(
                "visual.open_provider_fallback_skipped conversation_id=%s reason=preflight_budget",
                conversation_id,
            )
            return []

        async with httpx.AsyncClient(timeout=self.open_provider_timeout_seconds, follow_redirects=True) as client:
            candidates = await self._query_provider_candidates(
                provider="wikimedia",
                query_func=self._query_wikimedia,
                client=client,
                query=resolved_query,
                conversation_id=conversation_id,
            )
            block = await self._select_image_block(
                candidates,
                resolved_query,
                "wikimedia",
                conversation_id,
                visual_context,
                model_client,
                visual_brief,
            )
            if block:
                self._log_image_block_selected(conversation_id, block, "open_provider")
                return [block]

            candidates = await self._query_provider_candidates(
                provider="openverse",
                query_func=self._query_openverse,
                client=client,
                query=resolved_query,
                conversation_id=conversation_id,
            )
            block = await self._select_image_block(
                candidates,
                resolved_query,
                "openverse",
                conversation_id,
                visual_context,
                model_client,
                visual_brief,
            )
            if block:
                self._log_image_block_selected(conversation_id, block, "open_provider")
                return [block]

        block = await self._resolve_paid_provider_image(
            provider="tavily_images",
            query=resolved_query,
            conversation_id=conversation_id,
            visual_context=visual_context,
            model_client=model_client,
            visual_brief=visual_brief,
        )
        if block:
            return [block]

        block = await self._resolve_paid_provider_image(
            provider="serpapi_images",
            query=resolved_query,
            conversation_id=conversation_id,
            visual_context=visual_context,
            model_client=model_client,
            visual_brief=visual_brief,
        )
        if block:
            return [block]

        if not allow_og_fallback:
            logger.info(
                "visual.og_fallback_skipped conversation_id=%s reason=preflight_requires_grounded_provider",
                conversation_id,
            )
            return []

        results = list(existing_web_results or [])
        if results:
            logger.info(
                "visual.search_reused conversation_id=%s result_count=%s",
                conversation_id,
                len(results),
            )
        else:
            api_key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
            if not api_key:
                logger.info(
                    "visual.image_omitted conversation_id=%s reason=missing_search_api_key",
                    conversation_id,
                )
                return []
            if not hasattr(tool_registry, "execute"):
                logger.info(
                    "visual.image_omitted conversation_id=%s reason=missing_search_tool",
                    conversation_id,
                )
                return []
            results = await self._search_image_sources(
                user_msg=resolved_query,
                tool_registry=tool_registry,
                tool_budget=tool_budget,
                user_id=user_id,
                conversation_id=conversation_id,
                api_key=api_key,
            )

        async with httpx.AsyncClient(timeout=self.page_timeout_seconds, follow_redirects=True) as client:
            logger.info(
                "visual.og_image_scan_started conversation_id=%s result_count=%s timeout_seconds=%.1f",
                conversation_id,
                len(results),
                self.page_timeout_seconds,
            )
            for result in results:
                if len(blocks) >= self.max_images:
                    break
                block = await self._block_from_result_safe(
                    client,
                    result,
                    len(blocks) + 1,
                    conversation_id,
                )
                if not block:
                    continue
                blocks.append(block)
                logger.info(
                    "visual.image_selected conversation_id=%s source_domain=%s confidence_bucket=%s",
                    conversation_id,
                    block.source_domain,
                    "medium",
                )
                self._log_image_block_selected(conversation_id, block, "og_image")
        return blocks

    async def _resolve_preflight_parallel_images(
        self,
        *,
        resolved_query: str,
        visual_context: str,
        conversation_id: str,
        model_client: Any = None,
        visual_brief: VisualBrief,
        allow_open_provider_fallback: bool,
        selection_limit: int | None = None,
    ) -> list[ImageBlock]:
        """Query preflight providers concurrently and select one grounded image.

        Preflight runs before the main answer model, so total latency matters
        more than exhausting every provider in sequence. Each provider keeps its
        own timeout and error logs, while this coordinator only logs safe
        provider counts and merged candidate counts.

        Args:
            selection_limit: Optional number of grounded image blocks to return
                for downstream understanding retries. This is not the frontend
                display limit.
        """

        provider_tasks: list[asyncio.Task[tuple[str, list[ImageCandidate]]]] = []

        async def run_perplexity() -> tuple[str, list[ImageCandidate]]:
            async def query_perplexity_images(
                client: httpx.AsyncClient,
                query: str,
                conversation_id: str,
            ) -> list[ImageCandidate]:
                return await self._query_perplexity_images(client, query, conversation_id, visual_brief)

            async with httpx.AsyncClient(
                timeout=settings.perplexity_visual_search_timeout_seconds,
                follow_redirects=True,
            ) as client:
                return (
                    "perplexity_images",
                    await self._query_provider_candidates(
                        provider="perplexity_images",
                        query_func=query_perplexity_images,
                        client=client,
                        query=resolved_query,
                        conversation_id=conversation_id,
                    ),
                )

        async def run_open_provider(provider: str) -> tuple[str, list[ImageCandidate]]:
            query_func = self._query_wikimedia if provider == "wikimedia" else self._query_openverse
            async with httpx.AsyncClient(timeout=self.open_provider_timeout_seconds, follow_redirects=True) as client:
                return (
                    provider,
                    await self._query_provider_candidates(
                        provider=provider,
                        query_func=query_func,
                        client=client,
                        query=resolved_query,
                        conversation_id=conversation_id,
                    ),
                )

        async def run_paid_provider(provider: str) -> tuple[str, list[ImageCandidate]]:
            if provider == "tavily_images":
                query_func = self._query_tavily_images
                timeout_seconds = settings.tavily_visual_search_timeout_seconds
            else:
                query_func = self._query_serpapi_images
                timeout_seconds = settings.serpapi_visual_search_timeout_seconds
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                return (
                    provider,
                    await self._query_provider_candidates(
                        provider=provider,
                        query_func=query_func,
                        client=client,
                        query=resolved_query,
                        conversation_id=conversation_id,
                    ),
                )

        if settings.enable_perplexity_visual_search:
            provider_tasks.append(asyncio.create_task(run_perplexity()))
        if allow_open_provider_fallback:
            provider_tasks.append(asyncio.create_task(run_open_provider("wikimedia")))
            provider_tasks.append(asyncio.create_task(run_open_provider("openverse")))
        else:
            logger.info(
                "visual.open_provider_fallback_skipped conversation_id=%s reason=preflight_budget",
                conversation_id,
            )
        if settings.enable_tavily_visual_search:
            provider_tasks.append(asyncio.create_task(run_paid_provider("tavily_images")))
        if settings.enable_serpapi_visual_search:
            provider_tasks.append(asyncio.create_task(run_paid_provider("serpapi_images")))

        if not provider_tasks:
            return []

        logger.info(
            "visual.parallel_provider_started conversation_id=%s provider_count=%s",
            conversation_id,
            len(provider_tasks),
        )
        candidates: list[ImageCandidate] = []
        completed_provider_count = 0
        pending = set(provider_tasks)
        try:
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    try:
                        provider, provider_candidates = task.result()
                    except Exception as exc:
                        logger.info(
                            "visual.parallel_provider_failed conversation_id=%s reason=%s",
                            conversation_id,
                            type(exc).__name__,
                        )
                        continue
                    completed_provider_count += 1
                    candidates.extend(provider_candidates)
                    logger.info(
                        "visual.parallel_provider_completed conversation_id=%s provider=%s candidate_count=%s",
                        conversation_id,
                        provider,
                        len(provider_candidates),
                    )
                    logger.info(
                        "visual.parallel_candidates_merged conversation_id=%s provider_count=%s candidate_count=%s pending_provider_count=%s",
                        conversation_id,
                        completed_provider_count,
                        len(candidates),
                        len(pending),
                    )
                    if not provider_candidates:
                        continue
                    blocks = await self._select_image_blocks(
                        provider_candidates,
                        resolved_query,
                        provider,
                        conversation_id,
                        visual_context,
                        model_client,
                        visual_brief,
                        limit=max(1, int(selection_limit or self.max_images)),
                    )
                    if blocks:
                        for pending_task in pending:
                            pending_task.cancel()
                        block = blocks[0]
                        self._log_image_block_selected(conversation_id, block, provider)
                        return blocks
        finally:
            for task in pending:
                task.cancel()

        return []

    async def _resolve_paid_provider_image(
        self,
        *,
        provider: str,
        query: str,
        conversation_id: str,
        visual_context: str,
        model_client: Any = None,
        visual_brief: VisualBrief | None = None,
    ) -> ImageBlock | None:
        """Resolve one optional paid image provider into a verified block.

        Args:
            provider: Provider identifier, currently ``tavily_images`` or
                ``serpapi_images``.
            query: Provider-ready visual query. This is not written to logs.
            conversation_id: Correlation id for safe structured logs.
            visual_context: Bounded visual intent sent only to grounding.
            model_client: Optional OpenAI-compatible grounding client.
            visual_brief: Optional preflight brief used by grounding.

        Returns:
            The first verified image block selected from the provider, or
            ``None`` when the provider is disabled, unconfigured, fails, returns
            no candidates, or all candidates fail the existing gates.
        """

        if provider == "tavily_images":
            enabled = bool(settings.enable_tavily_visual_search)
            timeout_seconds = float(settings.tavily_visual_search_timeout_seconds)
            query_func = self._query_tavily_images
        elif provider == "serpapi_images":
            enabled = bool(settings.enable_serpapi_visual_search)
            timeout_seconds = float(settings.serpapi_visual_search_timeout_seconds)
            query_func = self._query_serpapi_images
        else:
            return None

        if not enabled:
            logger.info(
                "visual.provider_skipped conversation_id=%s provider=%s reason=disabled",
                conversation_id,
                provider,
            )
            return None

        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            candidates = await self._query_provider_candidates(
                provider=provider,
                query_func=query_func,
                client=client,
                query=query,
                conversation_id=conversation_id,
            )
        block = await self._select_image_block(
            candidates,
            query,
            provider,
            conversation_id,
            visual_context,
            model_client,
            visual_brief,
        )
        if block:
            self._log_image_block_selected(conversation_id, block, provider)
        return block

    async def _block_from_result_safe(
        self,
        client: httpx.AsyncClient,
        result: dict[str, Any],
        index: int,
        conversation_id: str,
    ) -> ImageBlock | None:
        """Extract an og:image block without aborting fallback iteration.

        Existing web results point at arbitrary third-party pages. Slow or
        unreachable pages are expected, so one timeout should not suppress all
        remaining image candidates for the turn.
        """

        try:
            return await self._block_from_result(client, result, index)
        except Exception as exc:
            source_domain = self._safe_result_domain(result)
            logger.info(
                "visual.og_image_failed conversation_id=%s source_domain=%s reason=%s status_code=%s",
                conversation_id,
                source_domain or "unknown",
                type(exc).__name__,
                self._http_status_code(exc) or "unknown",
            )
            return None

    async def _query_provider_candidates(
        self,
        *,
        provider: str,
        query_func: Any,
        client: httpx.AsyncClient,
        query: str,
        conversation_id: str,
    ) -> list[ImageCandidate]:
        """Query one image provider without aborting the whole visual flow.

        Provider APIs are external dependencies with independent availability
        and rate-limit behavior. A single provider failure should only remove
        that provider from the current turn, then allow the remaining open
        provider and existing web-result fallback to run. The structured log
        records only the provider identifier and exception type.
        """

        try:
            return await query_func(client, query, conversation_id)
        except Exception as exc:
            status_code = self._http_status_code(exc)
            logger.info(
                "visual.provider_failed conversation_id=%s provider=%s reason=%s status_code=%s",
                conversation_id,
                provider,
                type(exc).__name__,
                status_code or "unknown",
            )
            if provider == "wikimedia" and self._wikimedia_debug_logs_enabled():
                logger.info(
                    "visual.wikimedia_failed_debug conversation_id=%s status_code=%s content_type=%s retry_after=%s wiki_error_code=%s",
                    conversation_id,
                    status_code or "unknown",
                    self._http_response_header(exc, "content-type") or "unknown",
                    self._http_response_header(exc, "retry-after") or "none",
                    self._wikimedia_error_code(exc) or "unknown",
                )
            return []

    async def _query_perplexity_images(
        self,
        client: httpx.AsyncClient,
        query: str,
        conversation_id: str,
        visual_brief: VisualBrief | None = None,
    ) -> list[ImageCandidate]:
        """Query Perplexity Sonar image results as the first visual provider.

        Sonar can return structured image results in addition to textual search
        context. AREQA uses only the bounded image metadata here, then sends the
        candidates through the same safety and grounding gates as Wikimedia and
        Openverse. Structured logs expose only provider status and counts; they
        never include raw queries, prompts, answer text, credentials, or URLs.
        """

        api_key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
        if not api_key:
            logger.info(
                "visual.provider_skipped conversation_id=%s provider=perplexity_images reason=missing_api_key",
                conversation_id,
            )
            return []

        logger.info(
            "visual.provider_started conversation_id=%s provider=perplexity_images timeout_seconds=%.1f",
            conversation_id,
            settings.perplexity_visual_search_timeout_seconds,
        )
        response = await client.post(
            settings.perplexity_sonar_api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.perplexity_visual_search_model,
                "messages": self._perplexity_image_messages(query, visual_brief),
                "return_images": True,
                "num_images": max(self.max_images * 4, 4),
                "web_search_options": {
                    "search_context_size": "low",
                },
            },
        )
        response.raise_for_status()
        candidates = [
            candidate
            for item in response.json().get("images") or []
            if (candidate := self._perplexity_image_candidate(item)) is not None
        ]
        logger.info(
            "visual.provider_completed conversation_id=%s provider=perplexity_images candidate_count=%s",
            conversation_id,
            len(candidates),
        )
        return candidates

    async def _query_wikimedia(
        self,
        client: httpx.AsyncClient,
        query: str,
        conversation_id: str,
    ) -> list[ImageCandidate]:
        """Query Wikimedia Commons for openly licensed image candidates."""

        endpoint = os.environ.get("WIKIMEDIA_COMMONS_API_URL", "https://commons.wikimedia.org/w/api.php")
        logger.info(
            "visual.provider_started conversation_id=%s provider=wikimedia timeout_seconds=%.1f",
            conversation_id,
            self.open_provider_timeout_seconds,
        )
        response = await client.get(
            endpoint,
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": "6",
                "gsrlimit": "8",
                "prop": "imageinfo",
                "iiprop": "url|mime|size|extmetadata",
                "iiurlwidth": "800",
                "format": "json",
                "origin": "*",
            },
            headers=self._provider_headers("wikimedia"),
        )
        response.raise_for_status()
        pages = (response.json().get("query") or {}).get("pages") or {}
        candidates: list[ImageCandidate] = []
        for page in pages.values():
            image_info = next(iter(page.get("imageinfo") or []), None)
            if not image_info:
                continue
            metadata = image_info.get("extmetadata") or {}
            title = self._clean_text(str(page.get("title") or "").removeprefix("File:"))
            license_name = self._metadata_value(metadata, "LicenseShortName") or self._metadata_value(metadata, "UsageTerms")
            license_url = self._metadata_value(metadata, "LicenseUrl")
            creator = self._clean_html(self._metadata_value(metadata, "Artist"))
            attribution = self._clean_html(self._metadata_value(metadata, "Attribution") or creator)
            candidates.append(
                ImageCandidate(
                    provider="wikimedia",
                    image_url=str(image_info.get("url") or ""),
                    thumbnail_url=str(image_info.get("thumburl") or image_info.get("url") or ""),
                    source_url=str(image_info.get("descriptionurl") or ""),
                    title=title,
                    caption=self._clean_html(self._metadata_value(metadata, "ImageDescription")) or title,
                    license=license_name or "unknown",
                    license_url=license_url,
                    creator=creator,
                    attribution_string=attribution,
                    width=self._optional_int(image_info.get("width")),
                    height=self._optional_int(image_info.get("height")),
                )
            )
        logger.info(
            "visual.provider_completed conversation_id=%s provider=wikimedia candidate_count=%s",
            conversation_id,
            len(candidates),
        )
        return candidates

    async def _query_openverse(
        self,
        client: httpx.AsyncClient,
        query: str,
        conversation_id: str,
    ) -> list[ImageCandidate]:
        """Query Openverse for Creative Commons image candidates."""

        endpoint = os.environ.get("OPENVERSE_IMAGE_API_URL", "https://api.openverse.org/v1/images")
        logger.info(
            "visual.provider_started conversation_id=%s provider=openverse timeout_seconds=%.1f",
            conversation_id,
            self.open_provider_timeout_seconds,
        )
        response = await client.get(
            endpoint,
            params={
                "q": query,
                "license": "cc0,by,by-sa,pdm",
                "page_size": "8",
            },
            headers=self._provider_headers("openverse"),
        )
        response.raise_for_status()
        results = response.json().get("results") or []
        candidates = [
            ImageCandidate(
                provider="openverse",
                image_url=str(item.get("url") or ""),
                thumbnail_url=str(item.get("thumbnail") or item.get("url") or ""),
                source_url=str(item.get("foreign_landing_url") or item.get("url") or ""),
                title=self._clean_text(str(item.get("title") or "")),
                caption=self._clean_text(str(item.get("title") or "")),
                license=str(item.get("license") or "unknown"),
                license_url=str(item.get("license_url") or ""),
                creator=self._clean_text(str(item.get("creator") or "")),
                attribution_string=self._clean_text(str(item.get("attribution") or item.get("creator") or "")),
                width=self._optional_int(item.get("width")),
                height=self._optional_int(item.get("height")),
            )
            for item in results
        ]
        logger.info(
            "visual.provider_completed conversation_id=%s provider=openverse candidate_count=%s",
            conversation_id,
            len(candidates),
        )
        return candidates

    async def _query_tavily_images(
        self,
        client: httpx.AsyncClient,
        query: str,
        conversation_id: str,
    ) -> list[ImageCandidate]:
        """Query Tavily Search for source-grounded image candidates.

        Args:
            client: Async HTTP client configured with provider timeout.
            query: Provider-ready visual query. Never logged.
            conversation_id: Correlation id for privacy-safe structured logs.

        Returns:
            Normalized image candidates from Tavily's top-level image results
            and result-scoped images. Missing API keys and malformed image
            payloads fail soft by returning an empty list.
        """

        api_key = os.environ.get("TAVILY_API_KEY", "").strip()
        if not api_key:
            logger.info(
                "visual.provider_skipped conversation_id=%s provider=tavily_images reason=missing_api_key",
                conversation_id,
            )
            return []

        logger.info(
            "visual.provider_started conversation_id=%s provider=tavily_images timeout_seconds=%.1f",
            conversation_id,
            settings.tavily_visual_search_timeout_seconds,
        )
        response = await client.post(
            settings.tavily_search_api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
                "include_images": True,
                "include_image_descriptions": True,
            },
        )
        response.raise_for_status()
        payload = response.json()
        candidates = self._tavily_image_candidates(payload)
        logger.info(
            "visual.provider_completed conversation_id=%s provider=tavily_images candidate_count=%s",
            conversation_id,
            len(candidates),
        )
        return candidates

    async def _query_serpapi_images(
        self,
        client: httpx.AsyncClient,
        query: str,
        conversation_id: str,
    ) -> list[ImageCandidate]:
        """Query SerpAPI Google Images for broad public-web image candidates.

        Args:
            client: Async HTTP client configured with provider timeout.
            query: Provider-ready visual query. Never logged.
            conversation_id: Correlation id for privacy-safe structured logs.

        Returns:
            Normalized Google Images candidates from SerpAPI's
            ``images_results`` array. Missing API keys and malformed payloads
            fail soft by returning an empty list.
        """

        api_key = os.environ.get("SERPAPI_API_KEY", "").strip()
        if not api_key:
            logger.info(
                "visual.provider_skipped conversation_id=%s provider=serpapi_images reason=missing_api_key",
                conversation_id,
            )
            return []

        logger.info(
            "visual.provider_started conversation_id=%s provider=serpapi_images timeout_seconds=%.1f",
            conversation_id,
            settings.serpapi_visual_search_timeout_seconds,
        )
        response = await client.get(
            settings.serpapi_google_images_api_url,
            params={
                "engine": "google_images",
                "q": query,
                "ijn": "0",
                "safe": "active",
                "api_key": api_key,
            },
            headers=self._provider_headers("serpapi_images"),
        )
        response.raise_for_status()
        payload = response.json()
        image_results = payload.get("images_results") or payload.get("image_results") or []
        candidates = [
            candidate
            for item in image_results
            if (candidate := self._serpapi_image_candidate(item)) is not None
        ]
        logger.info(
            "visual.provider_completed conversation_id=%s provider=serpapi_images candidate_count=%s",
            conversation_id,
            len(candidates),
        )
        return candidates

    @classmethod
    def _provider_headers(cls, provider: str) -> dict[str, str]:
        """Build provider request headers without exposing credentials in logs.

        Wikimedia and Openverse both accept public requests, but a stable
        User-Agent makes AREQA identifiable to provider infrastructure and
        reduces anonymous-client blocking. Openverse can optionally use an
        OAuth bearer token to raise rate limits when configured.
        """

        headers = {
            "User-Agent": settings.areqa_visual_user_agent.strip() or _DEFAULT_VISUAL_USER_AGENT,
        }
        if provider == "openverse":
            token = (
                os.environ.get("OPENVERSE_ACCESS_TOKEN", "").strip()
                or os.environ.get("OPENVERSE_API_TOKEN", "").strip()
            )
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _perplexity_image_messages(query: str, visual_brief: VisualBrief | None) -> list[dict[str, str]]:
        """Build the Sonar prompt used only for image retrieval."""

        system_prompt = (
            "You are retrieving images for an educational answer. Find concrete, "
            "non-decorative images that directly support the current teaching "
            "strategy, not just the topic keywords. Match the requested visual "
            "type and learning purpose so the image can be embedded next to an "
            "explanation. Prefer diagrams, maps, charts, timelines, labeled "
            "figures, or historically/source-relevant photos when those match "
            "the request. Prefer educational, museum, archive, university, and "
            "Wikimedia-style sources. Avoid book covers, document scans, logos, "
            "shopping/product pages, unrelated photos, and generic thumbnails "
            "unless the user explicitly asks for them."
        )
        teaching_context = (
            visual_brief.teaching_context.to_prompt_payload()
            if visual_brief and visual_brief.teaching_context is not None
            else None
        )
        user_payload = {
            "image_search_query": query,
            "visual_brief": (
                {
                    "visual_type": visual_brief.visual_type,
                    "caption_goal": visual_brief.caption_goal,
                    "reject_if": list(visual_brief.reject_if),
                    "teaching_context": teaching_context,
                }
                if visual_brief
                else None
            ),
            "source_preferences": {
                "prefer": [
                    "educational diagrams",
                    "labeled maps",
                    "timelines",
                    "charts",
                    "museums",
                    "archives",
                    "universities",
                    "Wikimedia Commons",
                ],
                "reject": [
                    "shopping pages",
                    "product photos",
                    "book covers",
                    "document scans",
                    "decorative thumbnails",
                    "generic stock images",
                ],
            },
            "instruction": "Return image results with direct image URLs and source/origin URLs.",
        }
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]

    @classmethod
    def _perplexity_image_candidate(cls, item: Any) -> ImageCandidate | None:
        """Convert one Sonar image result into AREQA's provider candidate model."""

        if not isinstance(item, dict):
            return None
        image_url = str(item.get("image_url") or item.get("url") or "").strip()
        source_url = str(item.get("origin_url") or item.get("source_url") or image_url).strip()
        title = cls._clean_text(str(item.get("title") or ""))
        if not image_url or not source_url:
            return None
        return ImageCandidate(
            provider="perplexity_images",
            image_url=image_url,
            thumbnail_url=str(item.get("thumbnail_url") or image_url).strip(),
            source_url=source_url,
            title=title,
            caption=title,
            license="unknown",
            width=cls._optional_int(item.get("width")),
            height=cls._optional_int(item.get("height")),
        )

    @classmethod
    def _tavily_image_candidates(cls, payload: Any) -> list[ImageCandidate]:
        """Normalize Tavily image payloads into provider-agnostic candidates."""

        if not isinstance(payload, dict):
            return []

        candidates: list[ImageCandidate] = []
        for item in payload.get("images") or []:
            candidate = cls._tavily_image_candidate(item, None)
            if candidate is not None:
                candidates.append(candidate)

        for result in payload.get("results") or []:
            if not isinstance(result, dict):
                continue
            source_url = str(result.get("url") or "").strip() or None
            result_title = cls._clean_text(str(result.get("title") or ""))
            for item in result.get("images") or []:
                candidate = cls._tavily_image_candidate(item, source_url, result_title)
                if candidate is not None:
                    candidates.append(candidate)

        return candidates

    @classmethod
    def _tavily_image_candidate(
        cls,
        item: Any,
        source_url: str | None,
        fallback_title: str = "",
    ) -> ImageCandidate | None:
        """Convert one Tavily image result into AREQA's candidate model."""

        if isinstance(item, str):
            image_url = item.strip()
            title = fallback_title
            description = fallback_title
            resolved_source_url = source_url or image_url
        elif isinstance(item, dict):
            image_url = str(item.get("url") or item.get("image_url") or item.get("src") or "").strip()
            title = cls._clean_text(str(item.get("title") or fallback_title))
            description = cls._clean_text(str(item.get("description") or item.get("alt") or title))
            resolved_source_url = str(
                item.get("source_url")
                or item.get("source")
                or item.get("origin_url")
                or source_url
                or image_url
            ).strip()
        else:
            return None

        if not image_url or not resolved_source_url:
            return None
        return ImageCandidate(
            provider="tavily_images",
            image_url=image_url,
            thumbnail_url=image_url,
            source_url=resolved_source_url,
            title=title,
            caption=description or title,
            license="unknown",
        )

    @classmethod
    def _serpapi_image_candidate(cls, item: Any) -> ImageCandidate | None:
        """Convert one SerpAPI Google Images result into AREQA's candidate model."""

        if not isinstance(item, dict):
            return None
        image_url = str(item.get("original") or item.get("image") or "").strip()
        thumbnail_url = str(item.get("thumbnail") or image_url).strip()
        source_url = str(item.get("link") or item.get("source_url") or image_url).strip()
        title = cls._clean_text(str(item.get("title") or item.get("source") or ""))
        if not image_url or not source_url:
            return None
        return ImageCandidate(
            provider="serpapi_images",
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            source_url=source_url,
            title=title,
            caption=title,
            license="unknown",
            creator=cls._clean_text(str(item.get("source") or "")),
            width=cls._optional_int(item.get("original_width") or item.get("width")),
            height=cls._optional_int(item.get("original_height") or item.get("height")),
        )

    @staticmethod
    def _visual_search_query(user_msg: str) -> tuple[str, str]:
        """Rewrite a user prompt into image-provider metadata language.

        Open image providers primarily match titles, captions, and filenames.
        For abstract learning questions, stable rule-based rewrites improve hit
        rate without adding another foreground model call. Unknown non-English
        prompts keep a bounded topic string and append generic visual/source
        hints so public image search has enough topic context. Structured logs
        only emit the rewrite rule name, never this provider query.
        """

        normalized = " ".join(str(user_msg or "").strip().split())
        affordance = match_visual_affordance(normalized)
        if affordance is not None:
            return affordance.search_query, affordance.rule_name
        for rule_name, pattern, rewritten_query in _VISUAL_QUERY_REWRITE_RULES:
            if pattern.search(normalized):
                return rewritten_query, rule_name
        if normalized and not normalized.isascii():
            return (
                VisualAnswerService._generic_visual_search_query(normalized),
                "generic_non_english_visual_query",
            )
        fallback = normalized[:120] if normalized else "educational diagram"
        return fallback, "identity"

    @staticmethod
    def _generic_visual_search_query(normalized_prompt: str) -> str:
        """Build a provider-ready query for non-English prompts without topic loss.

        Args:
            normalized_prompt: User text after whitespace normalization.

        Returns:
            A bounded query that preserves the topic and adds provider-neutral
            visual/source hints. The string is intended for outbound image
            provider requests only and must not be written to structured logs.
        """

        lowered = normalized_prompt.lower()
        visual_hint = "educational explanatory diagram"
        source_hint = "Wikimedia Commons educational source"
        for _, keywords, hint in _VISUAL_TYPE_HINTS:
            if any(keyword in lowered for keyword in keywords):
                visual_hint = hint
                if "map" in hint:
                    source_hint = "Wikimedia Commons archive university source"
                break
        topic = normalized_prompt[:90].strip()
        return f"{topic} {visual_hint} {source_hint}".strip()[:160]

    @staticmethod
    def _http_status_code(exc: Exception) -> int | None:
        """Extract an HTTP status code from httpx exceptions when available."""

        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        return status_code if isinstance(status_code, int) else None

    @staticmethod
    def _safe_result_domain(result: dict[str, Any]) -> str:
        """Return a sanitized source domain for fallback logs."""

        source_url = str(result.get("url") or "")
        parsed = urlparse(source_url)
        return parsed.netloc.replace("www.", "") if parsed.netloc else ""

    @staticmethod
    def _http_response_header(exc: Exception, header: str) -> str:
        """Return one safe response header from an httpx exception."""

        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if not headers:
            return ""
        return str(headers.get(header, "")).strip()[:80]

    @staticmethod
    def _wikimedia_error_code(exc: Exception) -> str:
        """Return the MediaWiki API error code for debug logs, if present."""

        response = getattr(exc, "response", None)
        if not response:
            return ""
        try:
            payload = response.json()
        except Exception:
            return ""
        error = payload.get("error") if isinstance(payload, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        return str(code or "").strip()[:80]

    @staticmethod
    def _wikimedia_debug_logs_enabled() -> bool:
        """Return whether detailed Wikimedia failure logs are enabled."""

        return bool(settings.wikimedia_image_debug_logs)

    async def _select_image_block(
        self,
        candidates: list[ImageCandidate],
        query: str,
        provider: str,
        conversation_id: str,
        visual_intent_text: str = "",
        model_client: Any = None,
        visual_brief: VisualBrief | None = None,
    ) -> ImageBlock | None:
        """Select the strongest grounded candidate using metadata and an agent."""

        blocks = await self._select_image_blocks(
            candidates,
            query,
            provider,
            conversation_id,
            visual_intent_text,
            model_client,
            visual_brief,
            limit=1,
        )
        return blocks[0] if blocks else None

    async def _select_image_blocks(
        self,
        candidates: list[ImageCandidate],
        query: str,
        provider: str,
        conversation_id: str,
        visual_intent_text: str = "",
        model_client: Any = None,
        visual_brief: VisualBrief | None = None,
        *,
        limit: int = 1,
    ) -> list[ImageBlock]:
        """Select grounded candidates for downstream understanding retries.

        Args:
            candidates: Provider-normalized image metadata.
            query: Search query used for metadata scoring.
            provider: Stable provider identifier for logs.
            conversation_id: Correlation id for safe structured logs.
            visual_intent_text: Bounded visual intent used by the grounding
                agent. This is not logged.
            model_client: Optional OpenAI-compatible model client.
            visual_brief: Optional preflight brief for stricter grounding.
            limit: Maximum accepted image blocks to return.

        Returns:
            Ordered image blocks accepted by cheap scoring and visual grounding.

        Side Effects:
            May call the visual grounding agent. Logs only safe provider,
            count, score, and reason metadata.
        """

        scored = [
            (self._heuristic_score(candidate, query), candidate)
            for candidate in candidates
            if self._is_safe_candidate(candidate)
        ]
        if not scored:
            logger.info(
                "visual.image_omitted conversation_id=%s reason=no_safe_candidates provider=%s candidate_count=%s threshold=0.40",
                conversation_id,
                provider,
                len(candidates),
            )
            return []
        scored.sort(key=lambda item: item[0], reverse=True)
        score, candidate = scored[0]
        self._log_candidate_decision(
            conversation_id=conversation_id,
            provider=provider,
            candidate=candidate,
            candidate_count=len(candidates),
            safe_candidate_count=len(scored),
            top_score=score,
            threshold=0.4,
        )
        if score < 0.4:
            logger.info(
                "visual.image_omitted conversation_id=%s reason=low_score provider=%s top_score=%.2f threshold=0.40",
                conversation_id,
                provider,
                score,
            )
            return []

        selected_blocks: list[ImageBlock] = []
        max_grounding_candidates = (
            max(
                limit + 1,
                int(getattr(settings, "visual_preflight_grounding_max_candidates", 1)),
            )
            if visual_brief is not None
            else max(1, int(getattr(settings, "visual_grounding_max_candidates", 3)))
        )
        for candidate_score, candidate in scored[:max_grounding_candidates]:
            if candidate_score < 0.4:
                continue
            decision = await self._visual_grounding_agent.evaluate(
                client=model_client,
                model=settings.model_policy_classifier,
                visual_intent=visual_intent_text or query,
                candidate=candidate,
                conversation_id=conversation_id,
                visual_brief=visual_brief,
            )
            if decision.accepted and not (visual_brief is not None and decision.reason == "model_unavailable"):
                selected_blocks.append(
                    self._candidate_to_block(candidate, candidate_score, len(selected_blocks) + 1)
                )
                if len(selected_blocks) >= max(1, limit):
                    break
                continue
            logger.info(
                "visual.candidate_rejected conversation_id=%s provider=%s reason=grounding_%s expected_type=%s candidate_type=%s",
                conversation_id,
                provider,
                decision.reason,
                decision.expected_visual_type,
                decision.candidate_visual_type,
            )

        if not selected_blocks:
            logger.info(
                "visual.image_omitted conversation_id=%s reason=grounding_rejected provider=%s checked_candidate_count=%s threshold=0.40",
                conversation_id,
                provider,
                min(max_grounding_candidates, len(scored)),
            )
            return []

        block = selected_blocks[0]
        logger.info(
            "visual.image_selected conversation_id=%s source_domain=%s provider=%s confidence_bucket=%s",
            conversation_id,
            block.source_domain,
            block.provider,
            "high" if block.match_confidence >= 0.65 else "medium",
        )
        return selected_blocks

    @staticmethod
    def _log_candidate_decision(
        *,
        conversation_id: str,
        provider: str,
        candidate: ImageCandidate,
        candidate_count: int,
        safe_candidate_count: int,
        top_score: float,
        threshold: float,
    ) -> None:
        """Log safe candidate-ranking metadata for image retrieval debugging.

        The event intentionally excludes raw search queries, user prompts,
        model output, and full image/source URLs. It records only the provider,
        source domain, license label, dimension bucket, candidate counts, and
        score threshold needed to explain selection or low-score omission.
        """

        domain = urlparse(candidate.source_url).netloc.replace("www.", "") or "unknown"
        if candidate.width and candidate.height:
            if candidate.width >= 800 and candidate.height >= 400:
                dimension_bucket = "large"
            elif candidate.width >= 400 and candidate.height >= 250:
                dimension_bucket = "medium"
            else:
                dimension_bucket = "small"
        else:
            dimension_bucket = "unknown"
        logger.info(
            "visual.candidate_top_scored conversation_id=%s provider=%s candidate_count=%s safe_candidate_count=%s top_score=%.2f threshold=%.2f source_domain=%s license=%s dimension_bucket=%s",
            conversation_id,
            provider,
            candidate_count,
            safe_candidate_count,
            top_score,
            threshold,
            domain,
            candidate.license or "unknown",
            dimension_bucket,
        )

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
            provider="og_image",
            license="unknown",
            attribution_caption=caption[:140],
            safety_status="pass",
            match_confidence=0.6,
            heuristic_score=0.45,
            pedagogical_score=0.0,
        )

    @staticmethod
    def _log_image_block_selected(conversation_id: str, block: ImageBlock, stage: str) -> None:
        """Emit opt-in visual diagnostics without logging image URLs or prompts."""

        if not settings.enable_visual_answer_debug_logs:
            return
        logger.info(
            "visual.image_block_ready conversation_id=%s stage=%s provider=%s source_domain=%s has_explanatory_caption=%s pedagogical_score=%.2f",
            conversation_id,
            stage,
            block.provider,
            block.source_domain or "unknown",
            bool(block.explanatory_caption),
            block.pedagogical_score,
        )

    def _candidate_to_block(self, candidate: ImageCandidate, score: float, index: int) -> ImageBlock:
        """Convert a provider candidate into the frontend image block model."""

        parsed = urlparse(candidate.source_url)
        domain = parsed.netloc.replace("www.", "")
        caption = candidate.caption or candidate.title or f"Illustration from {domain}"
        pedagogical_score = self._pedagogical_score(candidate)
        display_image_url = self._display_image_url(candidate)
        return ImageBlock(
            slot_id=f"visual-{index}",
            topic=(candidate.title or caption)[:80],
            purpose="diagram",
            image_url=candidate.image_url,
            thumbnail_url=display_image_url,
            source_url=candidate.source_url,
            source_domain=domain,
            caption=caption[:140],
            provider=candidate.provider,
            license=candidate.license or "unknown",
            license_url=candidate.license_url,
            creator=candidate.creator,
            attribution_string=candidate.attribution_string,
            attribution_caption=caption[:140],
            width=candidate.width,
            height=candidate.height,
            safety_status="pass",
            match_confidence=score,
            heuristic_score=score,
            pedagogical_score=pedagogical_score,
        )

    def _heuristic_score(self, candidate: ImageCandidate, query: str) -> float:
        """Score candidate relevance using provider metadata only."""

        query_tokens = self._tokens(query)
        metadata = " ".join(
            [candidate.title, candidate.caption, candidate.creator, candidate.attribution_string]
        )
        metadata_tokens = self._tokens(metadata)
        overlap = len(query_tokens & metadata_tokens) / max(len(query_tokens), 1)
        purpose_bonus = 0.12 if _PURPOSE_TERMS & metadata_tokens else 0.0
        provider_bonus = _PROVIDER_PRIORITY.get(candidate.provider, 0.0)
        dimension_bonus = 0.08 if self._has_useful_dimensions(candidate) else 0.0
        pedagogy_bonus = min(self._pedagogical_score(candidate) * 0.2, 0.2)
        source_quality = self._source_quality_score(candidate)
        score = (
            overlap
            + purpose_bonus
            + provider_bonus
            + dimension_bonus
            + pedagogy_bonus
            + source_quality
        )
        return min(max(score, 0.0), 1.0)

    @staticmethod
    def _source_quality_score(candidate: ImageCandidate) -> float:
        """Score source-domain reliability using provider metadata only.

        Returns:
            A small positive boost for stable educational/archive/encyclopedic
            sources and a penalty for social, marketplace, or worksheet-hosting
            domains that often rank highly in image search but fail grounding.
        """

        domain = urlparse(candidate.source_url).netloc.lower().removeprefix("www.")
        if not domain:
            return 0.0
        if any(source in domain for source in _LOW_QUALITY_SOURCE_DOMAINS):
            return -0.25
        if any(
            VisualAnswerService._domain_matches_source_quality_pattern(domain, source)
            for source in _TRUSTED_SOURCE_DOMAINS
        ):
            return 0.18
        return 0.0

    @staticmethod
    def _domain_matches_source_quality_pattern(domain: str, pattern: str) -> bool:
        """Return whether a sanitized domain matches a source-quality pattern."""

        if pattern.startswith("."):
            return domain.endswith(pattern)
        return domain == pattern or domain.endswith(f".{pattern}") or pattern in domain

    @staticmethod
    def _pedagogical_score(candidate: ImageCandidate) -> float:
        """Score cheap metadata signals for instructional usefulness."""

        metadata = f"{candidate.title} {candidate.caption} {candidate.attribution_string}".lower()
        signals = (
            "annotated",
            "labeled",
            "diagram",
            "chart",
            "map",
            "timeline",
            "process",
            "flow",
            "overview",
            "comparison",
            "structure",
            "model",
            "figure",
            "illustration",
            "visualization",
            "framework",
            "steps",
            "axis",
            "legend",
        )
        score = sum(0.1 for signal in signals if signal in metadata)
        if candidate.provider == "wikimedia":
            score += 0.15
        if len(candidate.caption) >= 80:
            score += 0.1
        if VisualAnswerService._has_useful_dimensions(candidate):
            score += 0.1
        return min(score, 1.0)

    @classmethod
    def mark_inaccessible_image_domain(cls, image_url: str, *, reason: str) -> None:
        """Temporarily penalize domains that block backend image input.

        Args:
            image_url: Selected image URL that failed backend-side download.
            reason: Stable reason code such as ``HTTPStatusError:403``.

        Side Effects:
            Writes an in-process TTL entry used by candidate safety checks.
            Logs only the domain and reason code, never the full image URL.
        """

        domain = cls._safe_image_domain(image_url)
        if not domain:
            return
        _INACCESSIBLE_IMAGE_DOMAIN_CACHE[domain] = int(time.time()) + _INACCESSIBLE_IMAGE_DOMAIN_TTL_SECONDS
        logger.info(
            "visual.input_domain_penalized source_domain=%s reason=%s ttl_seconds=%s",
            domain,
            cls._safe_cache_reason(reason),
            _INACCESSIBLE_IMAGE_DOMAIN_TTL_SECONDS,
        )

    @classmethod
    def _is_safe_candidate(cls, candidate: ImageCandidate) -> bool:
        """Reject candidates that cannot be safely rendered or attributed."""

        for url in (candidate.image_url, candidate.source_url):
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return False
            domain = parsed.netloc.lower().removeprefix("www.")
            if domain in _UNSTABLE_IMAGE_INPUT_DOMAINS:
                return False
            if cls._is_inaccessible_image_domain(domain):
                return False
        if not cls._display_image_url(candidate):
            return False
        lowered = f"{candidate.image_url} {candidate.title} {candidate.caption}".lower()
        if any(term in lowered for term in _NEGATIVE_TERMS):
            return False
        if candidate.width is not None and candidate.width < 240:
            return False
        if candidate.height is not None and candidate.height < 160:
            return False
        return True

    @staticmethod
    def _safe_image_domain(image_url: str) -> str:
        """Return a safe lowercase domain label for an image URL."""

        parsed = urlparse(str(image_url or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        return parsed.netloc.lower().removeprefix("www.")

    @staticmethod
    def _is_inaccessible_image_domain(domain: str) -> bool:
        """Return whether a domain is temporarily blocked for image input."""

        normalized = str(domain or "").lower().removeprefix("www.")
        if not normalized:
            return False
        expires_at = _INACCESSIBLE_IMAGE_DOMAIN_CACHE.get(normalized)
        if not expires_at:
            return False
        if expires_at <= int(time.time()):
            _INACCESSIBLE_IMAGE_DOMAIN_CACHE.pop(normalized, None)
            return False
        return True

    @staticmethod
    def _display_image_url(candidate: ImageCandidate) -> str:
        """Return the best browser-displayable image URL for a candidate."""

        for url in (candidate.thumbnail_url, candidate.image_url):
            if VisualAnswerService._is_browser_display_image_url(url):
                return url
        return ""

    @staticmethod
    def _is_browser_display_image_url(url: str) -> bool:
        """Return whether a URL is likely renderable by browser img/lightbox."""

        parsed = urlparse(str(url or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        domain = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.lower()
        unsupported_extensions = (".tif", ".tiff", ".pdf", ".djvu", ".jp2")
        supported_extensions = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")
        if path.endswith(unsupported_extensions):
            return False
        if path.endswith(supported_extensions):
            return True
        if any(f"{extension}/" in path for extension in supported_extensions):
            return True
        return any(domain == suffix or domain.endswith(f".{suffix}") for suffix in _IMAGE_CDN_DOMAIN_SUFFIXES)

    @staticmethod
    def _has_useful_dimensions(candidate: ImageCandidate) -> bool:
        """Return whether known dimensions are suitable for a learning card."""

        if candidate.width is None or candidate.height is None:
            return False
        ratio = candidate.width / max(candidate.height, 1)
        return candidate.width >= 480 and candidate.height >= 240 and 0.4 <= ratio <= 3.2

    async def _read_cache(self, cache_key: str, conversation_id: str) -> dict[str, Any] | None:
        """Read a cached visual image block or negative sentinel from Redis."""

        redis_url = os.environ.get("REDIS_URL", "")
        if not redis_url:
            return None
        redis_client = None
        try:
            redis_client = self._redis_factory(redis_url, decode_responses=True)
            cached = await redis_client.get(cache_key)
            if not cached:
                logger.info("visual.cache_miss conversation_id=%s", conversation_id)
                return None
            payload = json.loads(cached)
            logger.info(
                "visual.cache_hit conversation_id=%s status=%s",
                conversation_id,
                payload.get("status", "hit"),
            )
            if payload.get("status") == "negative":
                cached_capability = str(payload.get("capability_fingerprint") or "")
                if cached_capability != self._visual_cache_capability_fingerprint():
                    logger.info(
                        "visual.cache_rejected conversation_id=%s reason=stale_negative_capability",
                        conversation_id,
                    )
                    return None
                return _NEGATIVE_CACHE_SENTINEL
            image_block = payload.get("image_block")
            if not isinstance(image_block, dict):
                return None
            if not self._is_safe_cached_image_block(image_block):
                logger.info(
                    "visual.cache_rejected conversation_id=%s reason=unsafe_cached_image",
                    conversation_id,
                )
                return None
            return image_block
        except Exception:
            logger.info("visual.cache_miss conversation_id=%s", conversation_id)
            return None
        finally:
            if redis_client:
                await redis_client.aclose()

    async def _write_cache(
        self,
        cache_key: str,
        image_block: dict[str, Any],
        ttl_seconds: int,
        conversation_id: str,
        *,
        negative_reason: str = "",
    ) -> None:
        """Write a selected image block or negative sentinel to Redis.

        Negative entries include a capability fingerprint so transient misses
        from an older vision/provider configuration do not suppress image
        retrieval after deployment changes. Logs only expose cache state and
        safe correlation ids; user text, prompts, image URLs, and credentials
        remain outside the logging boundary.
        """

        redis_url = os.environ.get("REDIS_URL", "")
        if not redis_url:
            return
        redis_client = None
        try:
            redis_client = self._redis_factory(redis_url, decode_responses=True)
            status = "negative" if image_block == _NEGATIVE_CACHE_SENTINEL else "hit"
            payload: dict[str, Any] = {
                "status": status,
                "image_block": None if status == "negative" else image_block,
                "retrieved_at": int(time.time()),
                "cache_version": _VISUAL_CACHE_VERSION,
                "capability_fingerprint": self._visual_cache_capability_fingerprint(),
            }
            if status == "negative":
                payload["negative_reason"] = self._safe_cache_reason(negative_reason)
            await redis_client.set(
                cache_key,
                json.dumps(payload, ensure_ascii=False),
                ex=ttl_seconds,
            )
        except Exception:
            logger.info("visual.cache_write_skipped conversation_id=%s", conversation_id)
        finally:
            if redis_client:
                await redis_client.aclose()

    async def commit_positive_cache(self, block: ImageBlock, *, conversation_id: str) -> None:
        """Commit a selected image to cache after vision understanding succeeds.

        Args:
            block: Image block that survived output understanding.
            conversation_id: Correlation id for safe structured logs.

        Side Effects:
            Writes a positive Redis cache entry only when ``block.cache_key`` is
            present. This deliberately moves positive-cache ownership after the
            output understanding gate so inaccessible provider URLs do not get
            cached as successful image answers.
        """

        if not block.cache_key:
            logger.info(
                "visual.output_cache_rejected conversation_id=%s slot_id=%s reason=missing_cache_key",
                conversation_id,
                block.slot_id,
            )
            return
        await self._write_cache(
            block.cache_key,
            block.to_frontend(),
            block.cache_ttl_seconds or _POSITIVE_CACHE_TTL_SECONDS,
            conversation_id,
        )
        logger.info(
            "visual.output_cache_committed conversation_id=%s slot_id=%s provider=%s source_domain=%s",
            conversation_id,
            block.slot_id,
            block.provider,
            block.source_domain or "unknown",
        )

    @classmethod
    def _cache_key(cls, query: str, purpose: str) -> str:
        """Return a privacy-preserving cache key for a visual slot."""

        normalized = " ".join(sorted(cls._tokens(query)))
        capability = cls._visual_cache_capability_fingerprint()
        digest = hashlib.sha256(
            f"{_VISUAL_CACHE_VERSION}:{purpose}:{normalized}:{capability}".encode("utf-8")
        ).hexdigest()
        return f"visual_image:{_VISUAL_CACHE_VERSION}:{purpose}:{digest}"

    @classmethod
    def _visual_cache_capability_fingerprint(cls) -> str:
        """Return a non-secret fingerprint for visual retrieval capabilities.

        The fingerprint intentionally excludes raw queries, prompts, image URLs,
        API keys, and provider credentials. It includes only coarse capability
        switches and safety policy inputs that affect whether a previously empty
        visual result should still be trusted.
        """

        payload = {
            "schema": _VISUAL_CACHE_CAPABILITY_SCHEMA,
            "cache_version": _VISUAL_CACHE_VERSION,
            "enable_perplexity_visual_search": bool(settings.enable_perplexity_visual_search),
            "enable_serpapi_visual_search": bool(settings.enable_serpapi_visual_search),
            "enable_tavily_visual_search": bool(settings.enable_tavily_visual_search),
            "enable_visual_preflight_open_provider_fallback": bool(
                settings.enable_visual_preflight_open_provider_fallback
            ),
            "enable_visual_understanding": bool(settings.enable_visual_understanding),
            "model_visual_understanding": str(settings.model_visual_understanding or ""),
            "unstable_image_input_domains": sorted(_UNSTABLE_IMAGE_INPUT_DOMAINS),
            "visual_grounding_max_candidates": int(settings.visual_grounding_max_candidates),
            "visual_preflight_grounding_max_candidates": int(
                settings.visual_preflight_grounding_max_candidates
            ),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def _visual_brief_cache_key(cls, brief: VisualBrief) -> str:
        """Return a preflight cache key scoped to the agent's visual intent.

        Preflight images are selected before answer generation and grounded
        against a model-planned brief. They must not reuse older generic
        diagram cache entries, because stale images can bypass the stricter
        grounding path. The key intentionally hashes normalized brief metadata
        and logs only the safe scope/type metadata at call sites.
        """

        purpose = f"preflight_{cls._safe_cache_purpose(brief.visual_type)}"
        fingerprint = json.dumps(
            {
                "caption_goal": brief.caption_goal,
                "reject_if": list(brief.reject_if),
                "search_query": brief.search_query,
                "teaching_context": (
                    brief.teaching_context.to_prompt_payload()
                    if brief.teaching_context is not None
                    else None
                ),
                "visual_type": brief.visual_type,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return cls._cache_key(fingerprint, purpose)

    @staticmethod
    def _safe_cache_purpose(value: str) -> str:
        """Normalize cache purpose fragments to stable non-empty identifiers."""

        normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").lower()).strip("_")
        return normalized or "visual"

    @staticmethod
    def _safe_cache_reason(value: str) -> str:
        """Normalize negative cache reasons to bounded operational labels."""

        normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").lower()).strip("_")
        return (normalized or "unknown")[:64]

    @staticmethod
    def _is_safe_cached_image_block(payload: dict[str, Any]) -> bool:
        """Return whether a cached frontend image block is still renderable.

        Cached visual blocks can outlive provider behavior changes. Revalidating
        the public URL shape on read prevents stale placeholder blocks from
        bypassing the provider safety gates after a deployment.
        """

        image_url = str(payload.get("imageUrl") or "")
        thumbnail_url = str(payload.get("thumbnailUrl") or image_url)
        source_url = str(payload.get("sourceUrl") or "")
        source_domain = str(payload.get("sourceDomain") or "")
        provider = str(payload.get("provider") or "")

        if provider not in {"perplexity_images", "wikimedia", "openverse", "og_image"}:
            return False

        for url in (image_url, thumbnail_url, source_url):
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return False
            if parsed.netloc.lower().removeprefix("www.") in _PLACEHOLDER_DOMAINS:
                return False

        parsed_source = urlparse(source_url)
        normalized_source_domain = parsed_source.netloc.lower().removeprefix("www.")
        if source_domain and source_domain.lower().removeprefix("www.") in _PLACEHOLDER_DOMAINS:
            return False
        if normalized_source_domain in _PLACEHOLDER_DOMAINS:
            return False

        return True

    @staticmethod
    def _image_block_from_frontend(payload: dict[str, Any]) -> ImageBlock:
        """Convert cached frontend payload back into an ImageBlock."""

        return ImageBlock(
            slot_id=str(payload.get("slotId") or "visual-1"),
            topic=str(payload.get("topic") or ""),
            purpose=str(payload.get("purpose") or "diagram"),
            image_url=str(payload.get("imageUrl") or ""),
            thumbnail_url=str(payload.get("thumbnailUrl") or payload.get("imageUrl") or ""),
            source_url=str(payload.get("sourceUrl") or ""),
            source_domain=str(payload.get("sourceDomain") or ""),
            caption=str(payload.get("caption") or ""),
            provider=str(payload.get("provider") or "cache"),
            license=str(payload.get("license") or "unknown"),
            license_url=str(payload.get("licenseUrl") or ""),
            creator=str(payload.get("creator") or ""),
            attribution_string=str(payload.get("attributionString") or ""),
            attribution_caption=str(payload.get("attributionCaption") or ""),
            explanatory_caption=str(payload.get("explanatoryCaption") or ""),
            width=VisualAnswerService._optional_int(payload.get("width")),
            height=VisualAnswerService._optional_int(payload.get("height")),
            safety_status=str(payload.get("safetyStatus") or "pass"),
            match_confidence=float(payload.get("matchConfidence") or 0.0),
            heuristic_score=float(payload.get("heuristicScore") or 0.0),
            pedagogical_score=float(payload.get("pedagogicalScore") or 0.0),
            vision_summary=str(payload.get("visionSummary") or ""),
            visible_elements=VisualAnswerService._string_tuple(payload.get("visibleElements"), 10, 140),
            how_to_read=VisualAnswerService._string_tuple(payload.get("howToRead"), 8, 180),
            vision_confidence=str(payload.get("visionConfidence") or "unknown"),
            vision_limitations=VisualAnswerService._string_tuple(payload.get("visionLimitations"), 6, 160),
            vision_source=str(payload.get("visionSource") or "unavailable"),
            storage_bucket=str(payload.get("storageBucket") or ""),
            storage_path=str(payload.get("storagePath") or ""),
            storage_expires_at=VisualAnswerService._optional_int(payload.get("storageExpiresAt")),
            transient=bool(payload.get("transient")),
        )

    @staticmethod
    def _string_tuple(value: Any, max_items: int, max_length: int) -> tuple[str, ...]:
        """Convert cached list payloads into bounded string tuples."""

        if not isinstance(value, list):
            return ()
        output: list[str] = []
        for item in value[:max_items]:
            text = VisualAnswerService._clean_text(str(item or ""))[:max_length]
            if text:
                output.append(text)
        return tuple(output)

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
    def _clean_html(text: str) -> str:
        """Remove simple HTML tags frequently returned by provider metadata."""

        return VisualAnswerService._clean_text(re.sub(r"<[^>]+>", "", text))

    @staticmethod
    def _metadata_value(metadata: dict[str, Any], key: str) -> str:
        """Read Wikimedia extmetadata values safely."""

        value = metadata.get(key)
        if isinstance(value, dict):
            return str(value.get("value") or "")
        return ""

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        """Convert provider numeric metadata to optional int."""

        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _tokens(text: str) -> set[str]:
        """Tokenize mixed Chinese/English metadata for cheap relevance scoring."""

        lowered = text.lower()
        ascii_tokens = re.findall(r"[a-z0-9]{2,}", lowered)
        cjk_tokens = re.findall(r"[\u4e00-\u9fff]{2,}", lowered)
        return set(ascii_tokens + cjk_tokens)

    @staticmethod
    def _planned_slots_from_payload(
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
            query = VisualAnswerService._clean_text(str(item.get("query") or ""))[:120]
            if not slot_id or slot_id in seen or (require_query and not query):
                continue
            seen.add(slot_id)
            caption_hint = VisualAnswerService._clean_text(str(item.get("caption_hint") or ""))[:180]
            anchor_after_paragraph = max(0, VisualAnswerService._optional_int(item.get("anchor_after_paragraph")) or 0)
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

    @staticmethod
    def _interleave_pending_slots(paragraphs: list[str], planned_slots: list[PlannedImageSlot]) -> list[dict[str, Any]]:
        """Interleave pending image placeholders at planned paragraph anchors."""

        return VisualAnswerService._interleave_blocks_at_planned_slots(paragraphs, planned_slots, {})

    @staticmethod
    def _interleave_blocks_at_planned_slots(
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
                    output.append(VisualAnswerService._pending_block(slot))
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
