"""Provider retrieval mixin for visual answer enrichment.

The mixin owns external image-provider calls and candidate parsing while the
main service facade owns high-level answer orchestration. Provider logs must use
safe metadata such as provider names, counts, status buckets, and conversation
ids; raw user text, prompts, credentials, and image URLs must not be logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from config import settings
from services.visual.affordance import match_visual_affordance
from services.visual_answer.constants import (
    _DEFAULT_VISUAL_USER_AGENT,
    _IMAGE_META_PATTERN,
    _PROVIDER_PRIORITY,
    _VISUAL_TYPE_HINTS,
    _VISUAL_QUERY_REWRITE_RULES,
)
from services.visual_answer.models import ImageBlock, ImageCandidate
from services.visual.grounding import VisualBrief

logger = logging.getLogger(__name__)


class VisualAnswerProviderMixin:
    """Provide image-provider lookup and provider payload normalization."""

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

    async def _resolve_preflight_parallel_images(self, **kwargs) -> list[ImageBlock]:
        """Resolve independent providers concurrently through the shared provider contract."""
        from services.visual_answer.provider_preflight import _resolve_preflight_parallel_images

        return await _resolve_preflight_parallel_images(self, **kwargs)
