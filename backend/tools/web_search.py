from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import httpx
import redis.asyncio as aioredis

from .registry import ToolResult

_BLOCKED_OPENROUTER_CITATION_HOSTS = {
    "vertexaisearch.cloud.google.com",
    "rephrase-it.com",
    "www.rephrase-it.com",
}


class WebSearchTool:
    def __init__(
        self,
        *,
        provider: str = "perplexity",
        endpoint: str = "https://api.perplexity.ai/search",
        openrouter_endpoint: str = "https://openrouter.ai/api/v1/chat/completions",
        openrouter_model: str = "google/gemini-3.8-flash",
        openrouter_engine: str = "auto",
        openrouter_max_tool_calls: int = 2,
        timeout_seconds: float = 8.0,
        cache_ttl_seconds: int = 86400,
        max_content_chars: int = 16000,
        redis_factory: Callable[..., Any] = aioredis.from_url,
        http_client_factory: Callable[..., Any] = httpx.AsyncClient,
    ) -> None:
        self.provider = provider
        self.endpoint = endpoint
        self.openrouter_endpoint = openrouter_endpoint
        self.openrouter_model = openrouter_model
        self.openrouter_engine = openrouter_engine
        self.openrouter_max_tool_calls = openrouter_max_tool_calls
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
        provider = str(arguments.get("provider", self.provider)).strip().lower() or self.provider
        cache_key = "websearch:" + hashlib.md5(
            f"{provider}_{user_id}_{conversation_id}_{query}".encode("utf-8")
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
                    if provider == "openrouter":
                        response = await self._post_openrouter_search(
                            client,
                            api_key=api_key,
                            query=query,
                            max_results=max_results,
                            context_size=context_size,
                            arguments=arguments,
                        )
                    else:
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
                    if provider == "openrouter":
                        payload = response.json()
                        data = {
                            "results": self._extract_openrouter_results(
                                payload,
                                max_results,
                            ),
                            "summary": self._extract_openrouter_summary(payload),
                        }
                    else:
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
                content={
                    "results": results,
                    **({"summary": data["summary"]} if data.get("summary") else {}),
                },
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

    async def _post_openrouter_search(
        self,
        client: Any,
        *,
        api_key: str,
        query: str,
        max_results: int,
        context_size: str,
        arguments: Mapping[str, Any],
    ) -> Any:
        """Run a non-streaming OpenRouter server-tool search request.

        Args:
            client: Async HTTP client used for the provider call.
            api_key: Backend-only OpenRouter API key.
            query: Standalone search query prepared by orchestration.
            max_results: Maximum normalized citations to return.
            context_size: Provider context-size preset.
            arguments: Runtime overrides supplied by orchestration.

        Returns:
            The HTTP response object returned by the injected client.

        Side Effects:
            Sends one OpenRouter Chat Completions request with the beta
            ``openrouter:web_search`` server tool enabled. The request is
            intentionally non-streaming so provider SSE comments, usage chunks,
            and mid-stream error frames cannot enter AREQA's public SSE stream.
        """

        model = str(arguments.get("model") or self.openrouter_model).strip()
        engine = str(arguments.get("engine") or self.openrouter_engine).strip().lower() or "auto"
        max_tool_calls = max(int(arguments.get("max_tool_calls", self.openrouter_max_tool_calls)), 1)
        return await client.post(
            self.openrouter_endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://congjie-pan.github.io/",
                "X-OpenRouter-Title": "AREQA",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Use web search for the user's query and answer briefly. "
                            "Citations must be exposed through OpenRouter url_citation annotations."
                        ),
                    },
                    {"role": "user", "content": query},
                ],
                "tools": [
                    {
                        "type": "openrouter:web_search",
                        "parameters": {
                            "engine": engine,
                            "max_results": max_results,
                            "max_total_results": max_results,
                            "search_context_size": context_size,
                        },
                    }
                ],
                "max_tool_calls": max_tool_calls,
                "temperature": 0.1,
                "max_tokens": 1200,
                "stream": False,
            },
        )

    @staticmethod
    def _extract_openrouter_summary(payload: Mapping[str, Any]) -> str:
        """Extract the assistant summary returned with OpenRouter web search."""

        choices = payload.get("choices") or []
        if not choices:
            return ""
        message = dict((choices[0] or {}).get("message") or {})
        return str(message.get("content") or "").strip()

    @staticmethod
    def _is_usable_openrouter_citation(url: str, snippet: str) -> bool:
        """Return whether an OpenRouter citation is useful to show as evidence."""

        if not snippet:
            return False
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        host = parsed.netloc.lower()
        if host in _BLOCKED_OPENROUTER_CITATION_HOSTS:
            return False
        if host.endswith(".google.com") and "grounding-api-redirect" in parsed.path:
            return False
        return True

    @staticmethod
    def _extract_openrouter_results(payload: Mapping[str, Any], max_results: int) -> list[dict[str, Any]]:
        """Normalize OpenRouter url citation annotations into search results.

        Args:
            payload: Non-streaming OpenRouter Chat Completions response body.
            max_results: Maximum citation records to return.

        Returns:
            A list of dictionaries matching AREQA's existing web-search result
            shape: ``title``, ``url``, ``snippet``, and ``score``.
        """

        choices = payload.get("choices") or []
        if not choices:
            return []
        message = dict((choices[0] or {}).get("message") or {})
        annotations = message.get("annotations") or []
        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for annotation in annotations:
            if not isinstance(annotation, Mapping):
                continue
            citation = annotation.get("url_citation") or {}
            if not isinstance(citation, Mapping):
                continue
            url = str(citation.get("url") or "").strip()
            snippet = str(citation.get("content") or "").strip()
            if (
                not url
                or url in seen_urls
                or not WebSearchTool._is_usable_openrouter_citation(url, snippet)
            ):
                continue
            seen_urls.add(url)
            results.append(
                {
                    "title": str(citation.get("title") or url).strip(),
                    "url": url,
                    "snippet": snippet,
                    "score": 1.0,
                }
            )
            if len(results) >= max_results:
                break
        return results
