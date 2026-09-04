"""External visual provider client methods and payload parsers.

This mixin contains outbound HTTP calls, provider-specific payload parsing, and
safe error classification for visual answer enrichment. Structured logs emitted
from these paths must use provider names, status buckets, counts, and
conversation ids only; raw queries, prompts, image URLs, credentials, and model
output are outside the logging boundary.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from config import settings
from services.visual_affordance_registry import match_visual_affordance
from services.visual_answer.constants import (
    _DEFAULT_VISUAL_USER_AGENT,
    _PROVIDER_PRIORITY,
    _VISUAL_QUERY_REWRITE_RULES,
    _VISUAL_TYPE_HINTS,
)
from services.visual_answer.models import ImageCandidate
from services.visual_grounding_agent import VisualBrief

logger = logging.getLogger(__name__)


class VisualAnswerProviderClientMixin:
    """Query visual providers and normalize their response payloads."""

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
