from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from policies.memory_policy import MemoryDecision

from .registry import ToolResult

ColdQuery = Callable[..., Awaitable[str]]
WorkingQuery = Callable[..., Awaitable[str]]


class MemoryQueryTool:
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
    ) -> ToolResult:
        if not decision.allow_long_term_query:
            raise PermissionError(f"memory query denied: {decision.reason_code}")

        started = time.monotonic()
        cold, working = await asyncio.gather(
            self._cold_query(user_id, query, top_k=5, client=client, model=model),
            self._working_query(query, limit=3, user_id=user_id),
        )
        content = {"cold": cold or "", "working": working or ""}
        serialized_length = len(content["cold"]) + len(content["working"])
        truncated = serialized_length > self._max_content_chars
        if truncated:
            remaining = self._max_content_chars
            content["cold"] = content["cold"][:remaining]
            remaining -= len(content["cold"])
            content["working"] = content["working"][:max(remaining, 0)]

        return ToolResult(
            tool_name="memory_query",
            status="ok",
            content=content,
            provenance=("cold_memory", "working_memory"),
            truncated=truncated,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
