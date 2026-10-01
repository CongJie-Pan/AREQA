"""Resolve independent image providers concurrently within the preflight deadline."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from config import settings
from services.visual_answer.models import ImageBlock, ImageCandidate
from services.visual_grounding_agent import VisualBrief

logger = logging.getLogger(__name__)


async def _resolve_preflight_parallel_images(
    resolver,
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
            return await resolver._query_perplexity_images(client, query, conversation_id, visual_brief)

        async with httpx.AsyncClient(
            timeout=settings.perplexity_visual_search_timeout_seconds,
            follow_redirects=True,
        ) as client:
            return (
                "perplexity_images",
                await resolver._query_provider_candidates(
                    provider="perplexity_images",
                    query_func=query_perplexity_images,
                    client=client,
                    query=resolved_query,
                    conversation_id=conversation_id,
                ),
            )

    async def run_open_provider(provider: str) -> tuple[str, list[ImageCandidate]]:
        query_func = resolver._query_wikimedia if provider == "wikimedia" else resolver._query_openverse
        async with httpx.AsyncClient(timeout=resolver.open_provider_timeout_seconds, follow_redirects=True) as client:
            return (
                provider,
                await resolver._query_provider_candidates(
                    provider=provider,
                    query_func=query_func,
                    client=client,
                    query=resolved_query,
                    conversation_id=conversation_id,
                ),
            )

    async def run_paid_provider(provider: str) -> tuple[str, list[ImageCandidate]]:
        if provider == "tavily_images":
            query_func = resolver._query_tavily_images
            timeout_seconds = settings.tavily_visual_search_timeout_seconds
        else:
            query_func = resolver._query_serpapi_images
            timeout_seconds = settings.serpapi_visual_search_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            return (
                provider,
                await resolver._query_provider_candidates(
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
                blocks = await resolver._select_image_blocks(
                    provider_candidates,
                    resolved_query,
                    provider,
                    conversation_id,
                    visual_context,
                    model_client,
                    visual_brief,
                    limit=max(1, int(selection_limit or resolver.max_images)),
                )
                if blocks:
                    for pending_task in pending:
                        pending_task.cancel()
                    block = blocks[0]
                    resolver._log_image_block_selected(conversation_id, block, provider)
                    return blocks
    finally:
        for task in pending:
            task.cancel()

    return []
