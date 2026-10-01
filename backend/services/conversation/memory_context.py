"""Bound long-term recall with policy-approved queries, timeout and caching."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger("services.conversation.context")

async def _query_long_term_memory(
    memory_query_tool: Any,
    *,
    user_id: str,
    conversation_id: str,
    query: str,
    decision: Any,
    client: Any,
    model: str,
    trace: Any,
    timeout_ms: int,
    cache_enabled: bool,
    cache_ttl_seconds: int,
) -> dict[str, str]:
    """Query long-term memory with explicit-recall timeout and cache.

        Explicit recall is the production-verified slow path. Other memory
        routes keep legacy behavior so this phase does not broaden behavior
        changes beyond the measured bottleneck.
        """

    is_explicit_recall = decision.reason_code == "EXPLICIT_RECALL_REQUEST"
    if is_explicit_recall and cache_enabled:
        from services.explicit_memory_cache import explicit_memory_cache

        cache_key = explicit_memory_cache.make_key(
            user_id=user_id,
            conversation_id=conversation_id,
            query=query,
        )
        cached_content = explicit_memory_cache.get(cache_key)
        if cached_content is not None:
            if trace:
                trace.mark("memory_query_cache_hit")
                trace.increment_tool_call("memory_query", "cache_hit")
            logger.info(
                "orchestration.long_term_memory_cache_hit conversation_id=%s reason=%s",
                conversation_id,
                decision.reason_code,
            )
            return cached_content
        if trace:
            trace.mark("memory_query_cache_miss")

    if trace:
        trace.mark("long_term_memory_started")

    from services.memory_retrieval_trace import MemoryRetrievalTrace

    retrieval_trace = MemoryRetrievalTrace(route_reason=decision.reason_code)

    async def execute_memory_query() -> Any:
        return await memory_query_tool.execute(
            user_id=user_id,
            query=query,
            decision=decision,
            client=client,
            model=model,
            retrieval_trace=retrieval_trace,
        )

    try:
        if is_explicit_recall and timeout_ms > 0:
            memory_result = await asyncio.wait_for(
                execute_memory_query(),
                timeout=timeout_ms / 1000,
            )
        else:
            memory_result = await execute_memory_query()
    except asyncio.TimeoutError:
        retrieval_trace.finish(
            outcome="timeout",
            cache_status="timeout",
            result_count=0,
        )
        if trace:
            trace.mark("long_term_memory_timeout")
            trace.increment_tool_call("memory_query", "timeout")
        logger.warning(
            "orchestration.long_term_memory_timeout conversation_id=%s reason=%s timeout_ms=%s",
            conversation_id,
            decision.reason_code,
            timeout_ms,
        )
        logger.info(
            "orchestration.long_term_memory_retrieval_summary conversation_id=%s summary=%s",
            conversation_id,
            json.dumps(retrieval_trace.snapshot(), ensure_ascii=False, sort_keys=True),
        )
        return {"cold": "", "working": "", "_status": "timeout"}

    if trace:
        trace.mark("long_term_memory_finished")
        trace.increment_tool_call(
            "memory_query",
            "cache_miss" if is_explicit_recall and cache_enabled else "not_applicable",
        )

    retrieval_summary = None
    if isinstance(getattr(memory_result, "metadata", None), Mapping):
        retrieval_summary = memory_result.metadata.get("memory_retrieval")
    if retrieval_summary:
        logger.info(
            "orchestration.long_term_memory_retrieval_summary conversation_id=%s summary=%s",
            conversation_id,
            json.dumps(retrieval_summary, ensure_ascii=False, sort_keys=True),
        )

    content = {
        "cold": str(memory_result.content.get("cold") or ""),
        "working": str(memory_result.content.get("working") or ""),
        "_status": (
            "fallback"
            if memory_result.content.get("_status") == "fallback"
            else "retrieved"
        ),
    }
    if is_explicit_recall and cache_enabled and (content["cold"] or content["working"]):
        from services.explicit_memory_cache import explicit_memory_cache

        explicit_memory_cache.set(
            explicit_memory_cache.make_key(
                user_id=user_id,
                conversation_id=conversation_id,
                query=query,
            ),
            content,
            ttl_seconds=cache_ttl_seconds,
        )
    return content
