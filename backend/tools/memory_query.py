from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Awaitable, Callable

from policies.memory_policy import MemoryDecision
from services.memory.retrieval_trace import MemoryRetrievalTrace

from .registry import ToolResult

ColdQuery = Callable[..., Awaitable[str]]
WorkingQuery = Callable[..., Awaitable[str]]


class MemoryQueryTool:
    """Query policy-approved memory sources with privacy-safe attribution."""

    def __init__(
        self,
        cold_query: ColdQuery,
        working_query: WorkingQuery,
        *,
        max_content_chars: int = 16000,
    ) -> None:
        self._cold_query = cold_query
        self._working_query = working_query
        self._max_content_chars = max_content_chars

    async def execute(
        self,
        *,
        user_id: str,
        query: str,
        decision: MemoryDecision,
        client: Any,
        model: str,
        retrieval_trace: MemoryRetrievalTrace | None = None,
    ) -> ToolResult:
        """Execute long-term memory retrieval without logging raw memory text."""

        if not decision.allow_long_term_query:
            raise PermissionError(f"memory query denied: {decision.reason_code}")

        started = time.monotonic()
        memory_trace = retrieval_trace or MemoryRetrievalTrace(
            route_reason=decision.reason_code
        )
        cold, working = await asyncio.gather(
            self._query_cold_memory(
                user_id=user_id,
                query=query,
                client=client,
                model=model,
                trace=memory_trace,
            ),
            self._query_working_memory(
                user_id=user_id,
                query=query,
                trace=memory_trace,
            ),
        )
        cold_embedding_degraded = memory_trace.has_step_outcome(
            "cold_memory_embedding",
            {"timeout", "error", "fallback"},
        )
        if cold_embedding_degraded:
            # Treat partial cold-memory retrieval as no long-term memory usage.
            # This keeps prompt behavior honest when vector retrieval was not
            # available within the foreground latency budget.
            content = {"cold": "", "working": "", "_status": "fallback"}
        else:
            content = {"cold": cold or "", "working": working or ""}
        serialized_length = len(content["cold"]) + len(content["working"])
        truncated = serialized_length > self._max_content_chars
        if truncated:
            remaining = self._max_content_chars
            content["cold"] = content["cold"][:remaining]
            remaining -= len(content["cold"])
            content["working"] = content["working"][:max(remaining, 0)]
        result_count = int(bool(content["cold"])) + int(bool(content["working"]))
        memory_trace.finish(
            outcome=(
                "fallback"
                if cold_embedding_degraded
                else "retrieved" if result_count else "empty"
            ),
            result_count=result_count,
            truncated=truncated,
        )

        return ToolResult(
            tool_name="memory_query",
            status="ok",
            content=content,
            provenance=("cold_memory", "working_memory"),
            truncated=truncated,
            latency_ms=int((time.monotonic() - started) * 1000),
            metadata={"memory_retrieval": memory_trace.snapshot()},
        )

    async def _query_cold_memory(
        self,
        *,
        user_id: str,
        query: str,
        client: Any,
        model: str,
        trace: MemoryRetrievalTrace,
    ) -> str:
        """Query cold memory and record only safe duration metadata."""

        async with trace.measure("cold_memory"):
            kwargs = {"top_k": 5, "client": client, "model": model}
            if _accepts_keyword(self._cold_query, "memory_trace"):
                kwargs["memory_trace"] = trace
            return await self._cold_query(user_id, query, **kwargs)

    async def _query_working_memory(
        self,
        *,
        user_id: str,
        query: str,
        trace: MemoryRetrievalTrace,
    ) -> str:
        """Query working memory and record only safe duration metadata."""

        async with trace.measure("working_memory"):
            return await self._working_query(query, limit=3, user_id=user_id)


def _accepts_keyword(callable_obj: ColdQuery, keyword: str) -> bool:
    """Return whether a callable accepts a keyword without invoking it."""

    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return True
    for parameter in signature.parameters.values():
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            return True
        if parameter.name == keyword:
            return True
    return False
