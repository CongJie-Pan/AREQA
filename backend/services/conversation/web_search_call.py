"""Web search provider configuration and result formatting for the search node.

Searching is the learner's choice (search mode), and ``retrieval.py`` runs it
before the answer. Configuration resolves at call time so environment
overrides apply. Keys stay server-side: they go only into the registry tool
arguments.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from config import settings


@dataclass(frozen=True, slots=True)
class WebSearchConfig:
    """Provider settings resolved from the environment, then ``settings``."""

    provider: str
    model: str
    engine: str
    max_tool_calls: int
    api_key: str
    max_results: int
    search_context_size: str


def web_search_config() -> WebSearchConfig:
    """Resolve provider settings at call time so environment overrides apply."""
    provider = os.environ.get("WEB_SEARCH_PROVIDER", settings.web_search_provider).strip().lower() or "openrouter"
    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
    elif provider == "tavily":
        api_key = os.environ.get("TAVILY_API_KEY", "")
    else:
        api_key = os.environ.get("PERPLEXITY_API_KEY", "")
    context_size = os.environ.get("WEB_SEARCH_CONTEXT_SIZE", "high").lower()
    return WebSearchConfig(
        provider=provider,
        model=os.environ.get("MODEL_WEB_SEARCH", settings.model_web_search).strip(),
        engine=os.environ.get("OPENROUTER_WEB_SEARCH_ENGINE", settings.openrouter_web_search_engine).strip().lower() or "auto",
        max_tool_calls=int(os.environ.get(
            "OPENROUTER_WEB_SEARCH_MAX_TOOL_CALLS", str(settings.openrouter_web_search_max_tool_calls))),
        api_key=api_key,
        max_results=min(max(int(os.environ.get("WEB_SEARCH_MAX_RESULTS", "15")), 3), 20),
        search_context_size=context_size if context_size in {"low", "medium", "high"} else "high",
    )


def web_search_arguments(config: WebSearchConfig, *, query: str, user_id: str, conversation_id: str,
                         max_results: int | None = None) -> dict[str, Any]:
    """Build the registry arguments for one ``web_search`` call."""
    return {
        "query": query,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "api_key": config.api_key,
        "provider": config.provider,
        "model": config.model,
        "engine": config.engine,
        "max_tool_calls": config.max_tool_calls,
        "max_results": config.max_results if max_results is None else max_results,
        "search_context_size": config.search_context_size,
        "tavily_search_depth": os.environ.get("TAVILY_WEB_SEARCH_DEPTH", settings.tavily_web_search_depth),
        "redis_url": os.environ.get("REDIS_URL", "redis://localhost:6379"),
    }


def format_web_results(content: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], bool]:
    """Turn a web search tool result into prompt context and learner-visible sources.

    Returns:
        ``(results, context_texts, sources_payload, used_summary)``; the provider
        summary stands in for context only when no result has a valid URL.
    """
    # Imported here so this conversation-level module never loads the orchestration package at import time.
    from services.orchestration.utils import _build_valid_web_sources

    results = list(content["results"])
    summary = str(content.get("summary") or "").strip()
    context_texts, sources_payload = _build_valid_web_sources(results)
    used_summary = False
    if not context_texts and summary:
        context_texts = [f"[網路搜尋摘要]\n{summary}"]
        used_summary = True
    return results, context_texts, sources_payload, used_summary
