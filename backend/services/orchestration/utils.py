"""Utility functions shared by orchestration service modules."""

from __future__ import annotations

import logging
from typing import Any, Dict, List
from urllib.parse import urlparse

from openai import AsyncOpenAI

from services.query_policy.classifier import (
    classify_response_policy_impl,
    parse_and_decompose_query_impl,
)

logger = logging.getLogger(__name__)
InterfaceLanguage = str


def _localized_greeting_reply(interface_language: InterfaceLanguage) -> str:
    if interface_language == "en":
        return "Hello, I am here. You can tell me what you want to work on now."
    if interface_language == "zh-CN":
        return "你好，我在。你可以直接告诉我现在想处理什么。"
    return "你好，我在。你可以直接告訴我現在想處理什麼。"


def reorder_for_attention(results):
    """Reorder search results to reduce lost-in-the-middle effects."""

    if len(results) <= 2:
        return results
    top = [results[0]]
    bottom = [results[1]]
    middle = results[2:]
    return top + middle + bottom


def _build_valid_web_sources(results: List[Dict[str, Any]]) -> tuple[List[str], List[Dict[str, Any]]]:
    """Build prompt context and structured source payload from valid web results."""

    context_texts: List[str] = []
    sources_payload: List[Dict[str, Any]] = []
    for source_index, result in enumerate(results, 1):
        title = str(result.get("title") or "").strip()
        url = str(result.get("url") or "").strip()
        snippet = str(result.get("snippet") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            logger.info(
                "orchestration.web_source_omitted reason=invalid_url source_index=%s",
                source_index,
            )
            continue

        citation_index = len(sources_payload) + 1
        context_texts.append(f"[文獻{citation_index}] {title}\nURL: {url}\n內容段落: {snippet}")
        sources_payload.append({
            "title": title,
            "chunk_id": url,
            "url": url,
            "snippet": snippet,
            "score": float(result.get("score", 1.0) or 1.0),
        })
    return context_texts, sources_payload


async def parse_and_decompose_query(query: str, client: AsyncOpenAI) -> List[Dict[str, str]]:
    """Parse and decompose a complex user query into retrieval sub-queries."""

    return await parse_and_decompose_query_impl(query, client)


async def classify_dialogue_policy(
    client: AsyncOpenAI,
    model: str,
    user_msg: str,
    chat_history: list,
    *,
    has_pdf_attachment: bool = False,
    pdf_attachment_count: int = 0,
):
    """Return the structured EDF response policy for orchestration."""

    return await classify_response_policy_impl(
        client,
        model,
        user_msg,
        chat_history,
        has_pdf_attachment=has_pdf_attachment,
        pdf_attachment_count=pdf_attachment_count,
    )
