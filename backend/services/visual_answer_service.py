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
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import redis.asyncio as aioredis

from config import settings
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
_NEGATIVE_CACHE_SENTINEL = {"status": "negative"}
_VISUAL_CACHE_VERSION = "v2"
_PROVIDER_PRIORITY = {
    "wikimedia": 0.25,
    "openverse": 0.2,
    "og_image": 0.05,
}
_PLACEHOLDER_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
}
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
_NEGATIVE_TERMS = {
    "logo",
    "icon",
    "placeholder",
    "avatar",
    "watermark",
    "sprite",
}
_DEFAULT_VISUAL_USER_AGENT = "AREQA/0.1 visual-answer-retrieval"


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
        width: Optional image width.
        height: Optional image height.
        safety_status: Backend safety gate result.
        match_confidence: Conservative confidence score from metadata matching.
        heuristic_score: Cheap metadata-only relevance score.
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
    width: int | None = None
    height: int | None = None
    safety_status: str = "pass"
    match_confidence: float = 0.0
    heuristic_score: float = 0.0

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
            "license": self.license,
            "safetyStatus": self.safety_status,
            "matchConfidence": self.match_confidence,
            "heuristicScore": self.heuristic_score,
        }
        if self.license_url:
            payload["licenseUrl"] = self.license_url
        if self.creator:
            payload["creator"] = self.creator
        if self.attribution_string:
            payload["attributionString"] = self.attribution_string
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
        existing_web_results: list[dict[str, Any]] | None,
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
            existing_web_results: Web results already fetched for this turn.
                These are preferred so illustrated answers do not spend a second
                external tool call in WEB_REQUIRED turns.
            user_id: Current user identifier for tool cache scoping.
            conversation_id: Current conversation identifier for safe logs.

        Returns:
            Ordered paragraph and image blocks. Returns an empty list when visual
            enrichment is not applicable or no verified image can be found.
        """

        paragraphs = self._split_paragraphs(answer_text)
        if not paragraphs or not self.should_enrich(response_policy, user_msg):
            return []

        logger.info(
            "visual.slots_planned conversation_id=%s slot_count=%s reason=%s",
            conversation_id,
            min(self.max_images, len(paragraphs)),
            "policy_or_explicit_visual",
        )

        try:
            cache_key = self._cache_key(user_msg, "diagram")
            cached_block = await self._read_cache(cache_key, conversation_id)
            if cached_block == _NEGATIVE_CACHE_SENTINEL:
                return []
            if isinstance(cached_block, dict):
                return self._interleave_blocks(paragraphs, [self._image_block_from_frontend(cached_block)])

            image_blocks = await self._resolve_images(
                user_msg=user_msg,
                existing_web_results=existing_web_results,
                tool_registry=tool_registry,
                tool_budget=tool_budget,
                user_id=user_id,
                conversation_id=conversation_id,
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
            await self._write_cache(cache_key, _NEGATIVE_CACHE_SENTINEL, 604800, conversation_id)
            return []

        await self._write_cache(cache_key, image_blocks[0].to_frontend(), 2592000, conversation_id)
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
        *,
        user_msg: str,
        existing_web_results: list[dict[str, Any]] | None,
        tool_registry: Any,
        tool_budget: Any,
        user_id: str,
        conversation_id: str,
    ) -> list[ImageBlock]:
        """Resolve open-source providers first, then existing og:image fallback."""

        blocks: list[ImageBlock] = []
        async with httpx.AsyncClient(timeout=self.open_provider_timeout_seconds, follow_redirects=True) as client:
            candidates = await self._query_provider_candidates(
                provider="wikimedia",
                query_func=self._query_wikimedia,
                client=client,
                query=user_msg,
                conversation_id=conversation_id,
            )
            block = self._select_image_block(candidates, user_msg, "wikimedia", conversation_id)
            if block:
                return [block]

            candidates = await self._query_provider_candidates(
                provider="openverse",
                query_func=self._query_openverse,
                client=client,
                query=user_msg,
                conversation_id=conversation_id,
            )
            block = self._select_image_block(candidates, user_msg, "openverse", conversation_id)
            if block:
                return [block]

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
            results = await self._search_image_sources(
                user_msg=user_msg,
                tool_registry=tool_registry,
                tool_budget=tool_budget,
                user_id=user_id,
                conversation_id=conversation_id,
                api_key=api_key,
            )

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

    async def _query_wikimedia(
        self,
        client: httpx.AsyncClient,
        query: str,
        conversation_id: str,
    ) -> list[ImageCandidate]:
        """Query Wikimedia Commons for openly licensed image candidates."""

        endpoint = os.environ.get("WIKIMEDIA_COMMONS_API_URL", "https://commons.wikimedia.org/w/api.php")
        logger.info("visual.provider_started conversation_id=%s provider=wikimedia", conversation_id)
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
        logger.info("visual.provider_started conversation_id=%s provider=openverse", conversation_id)
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
    def _http_status_code(exc: Exception) -> int | None:
        """Extract an HTTP status code from httpx exceptions when available."""

        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        return status_code if isinstance(status_code, int) else None

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

    def _select_image_block(
        self,
        candidates: list[ImageCandidate],
        query: str,
        provider: str,
        conversation_id: str,
    ) -> ImageBlock | None:
        """Select the strongest candidate using cheap metadata heuristics."""

        scored = [
            (self._heuristic_score(candidate, query), candidate)
            for candidate in candidates
            if self._is_safe_candidate(candidate)
        ]
        if not scored:
            return None
        score, candidate = max(scored, key=lambda item: item[0])
        if score < 0.4:
            logger.info(
                "visual.image_omitted conversation_id=%s reason=low_score provider=%s",
                conversation_id,
                provider,
            )
            return None
        block = self._candidate_to_block(candidate, score, 1)
        logger.info(
            "visual.image_selected conversation_id=%s source_domain=%s provider=%s confidence_bucket=%s",
            conversation_id,
            block.source_domain,
            block.provider,
            "high" if score >= 0.65 else "medium",
        )
        return block

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
            safety_status="pass",
            match_confidence=0.6,
            heuristic_score=0.45,
        )

    def _candidate_to_block(self, candidate: ImageCandidate, score: float, index: int) -> ImageBlock:
        """Convert a provider candidate into the frontend image block model."""

        parsed = urlparse(candidate.source_url)
        domain = parsed.netloc.replace("www.", "")
        caption = candidate.caption or candidate.title or f"Illustration from {domain}"
        return ImageBlock(
            slot_id=f"visual-{index}",
            topic=(candidate.title or caption)[:80],
            purpose="diagram",
            image_url=candidate.image_url,
            thumbnail_url=candidate.thumbnail_url or candidate.image_url,
            source_url=candidate.source_url,
            source_domain=domain,
            caption=caption[:140],
            provider=candidate.provider,
            license=candidate.license or "unknown",
            license_url=candidate.license_url,
            creator=candidate.creator,
            attribution_string=candidate.attribution_string,
            width=candidate.width,
            height=candidate.height,
            safety_status="pass",
            match_confidence=score,
            heuristic_score=score,
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
        return min(overlap + purpose_bonus + provider_bonus + dimension_bonus, 1.0)

    @staticmethod
    def _is_safe_candidate(candidate: ImageCandidate) -> bool:
        """Reject candidates that cannot be safely rendered or attributed."""

        for url in (candidate.image_url, candidate.source_url):
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
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
    ) -> None:
        """Write a selected image block or negative sentinel to Redis."""

        redis_url = os.environ.get("REDIS_URL", "")
        if not redis_url:
            return
        redis_client = None
        try:
            redis_client = self._redis_factory(redis_url, decode_responses=True)
            status = "negative" if image_block == _NEGATIVE_CACHE_SENTINEL else "hit"
            await redis_client.set(
                cache_key,
                json.dumps(
                    {
                        "status": status,
                        "image_block": None if status == "negative" else image_block,
                        "retrieved_at": int(time.time()),
                    },
                    ensure_ascii=False,
                ),
                ex=ttl_seconds,
            )
        except Exception:
            logger.info("visual.cache_write_skipped conversation_id=%s", conversation_id)
        finally:
            if redis_client:
                await redis_client.aclose()

    @classmethod
    def _cache_key(cls, query: str, purpose: str) -> str:
        """Return a privacy-preserving cache key for a visual slot."""

        normalized = " ".join(sorted(cls._tokens(query)))
        digest = hashlib.sha256(f"{_VISUAL_CACHE_VERSION}:{purpose}:{normalized}".encode("utf-8")).hexdigest()
        return f"visual_image:{_VISUAL_CACHE_VERSION}:{purpose}:{digest}"

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

        if provider not in {"wikimedia", "openverse", "og_image"}:
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
            width=VisualAnswerService._optional_int(payload.get("width")),
            height=VisualAnswerService._optional_int(payload.get("height")),
            safety_status=str(payload.get("safetyStatus") or "pass"),
            match_confidence=float(payload.get("matchConfidence") or 0.0),
            heuristic_score=float(payload.get("heuristicScore") or 0.0),
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
