from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable, Mapping

import httpx
import redis.asyncio as aioredis

from .registry import ToolResult


class WebSearchTool:
    def __init__(
        self,
        *,
        endpoint: str = "https://api.perplexity.ai/search",
        timeout_seconds: float = 8.0,
        cache_ttl_seconds: int = 86400,
        max_content_chars: int = 16000,
        redis_factory: Callable[..., Any] = aioredis.from_url,
        http_client_factory: Callable[..., Any] = httpx.AsyncClient,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_content_chars = max_content_chars
        self._redis_factory = redis_factory
        self._http_client_factory = http_client_factory

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        query = str(arguments.get("query", "")).strip()
        api_key = str(arguments.get("api_key", "")).strip()
        conversation_id = str(arguments.get("conversation_id", "")).strip()
        user_id = str(arguments.get("user_id", "")).strip()
        if not query:
            raise ValueError("web search query must not be empty")
        if not api_key:
            raise PermissionError("web search API key is missing")

        max_results = min(max(int(arguments.get("max_results", 15)), 3), 20)
        context_size = str(arguments.get("search_context_size", "high")).lower()
        if context_size not in {"low", "medium", "high"}:
            context_size = "high"
        redis_url = str(arguments.get("redis_url", "redis://localhost:6379"))
        cache_key = "websearch:" + hashlib.md5(
            f"{user_id}_{conversation_id}_{query}".encode("utf-8")
        ).hexdigest()
        started = time.monotonic()
        redis_client = None
        data: dict[str, Any] | None = None
        cache_status = "miss"

        try:
            try:
                redis_client = self._redis_factory(redis_url, decode_responses=True)
                cached = await redis_client.get(cache_key)
                if cached:
                    data = json.loads(cached)
                    cache_status = "hit"
            except Exception:
                cache_status = "unavailable"

            if data is None:
                async with self._http_client_factory(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        self.endpoint,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "query": query,
                            "max_results": max_results,
                            "search_context_size": context_size,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                raw_results = list(data.get("results", []))
                data["results"] = raw_results[:max_results]
                if redis_client:
                    try:
                        await redis_client.set(
                            cache_key,
                            json.dumps(data, ensure_ascii=False),
                            ex=self.cache_ttl_seconds,
                        )
                    except Exception:
                        pass

            raw_results = list(data.get("results", []))
            results: list[dict[str, Any]] = []
            remaining_chars = self.max_content_chars
            content_truncated = len(raw_results) > max_results
            for raw_item in raw_results[:max_results]:
                item = dict(raw_item)
                snippet = str(item.get("snippet", ""))
                if len(snippet) > remaining_chars:
                    snippet = snippet[:max(remaining_chars, 0)]
                    content_truncated = True
                item["snippet"] = snippet
                remaining_chars -= len(snippet)
                results.append(item)
                if remaining_chars <= 0:
                    content_truncated = True
                    break
            provenance = tuple(
                str(item.get("url")) for item in results if item.get("url")
            )
            return ToolResult(
                tool_name="web_search",
                status="ok",
                content={"results": results},
                provenance=provenance,
                truncated=content_truncated,
                latency_ms=int((time.monotonic() - started) * 1000),
                cache_status=cache_status,
            )
        finally:
            if redis_client:
                try:
                    await redis_client.aclose()
                except Exception:
                    pass
