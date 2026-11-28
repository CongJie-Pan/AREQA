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
from services.query_policy.policy_backend import classify_with_backend

logger = logging.getLogger(__name__)
InterfaceLanguage = str


_GREETING_REPLIES = {
    "en": "Hello, I am here. You can tell me what you want to work on now.",
    "zh-CN": "你好，我在。你可以直接告诉我现在想处理什么。",
    "zh-TW": "你好，我在。你可以直接告訴我現在想處理什麼。",
}

# Topic Finder's greeting is the coach's first step: ask for the pain point.
_TOPIC_FINDER_GREETING_REPLIES = {
    "en": (
        "Hi! This is Topic Finder. Start with one sentence about what you are stuck on or curious about: "
        "\"I'm stuck on / curious about ___\". Ideally it is something you have actually run into or care about."
    ),
    "zh-CN": "你好！这里是选题空间。先用一句话说说你最近卡住或好奇的问题：「我卡在／我好奇＿＿」，最好是你真的遇过或在乎的事。",
    "zh-TW": "你好！這裡是選題空間。先用一句話說說你最近卡住或好奇的問題：「我卡在／我好奇＿＿」，最好是你真的遇過或在乎的事。",
}


def _localized_greeting_reply(interface_language: InterfaceLanguage, last_user_msg: str = "",
                              topic_finder: bool = False) -> str:
    """Canned reply for a bare greeting, in the language of the greeting itself.

    Args:
        interface_language: UI language, used only when the message has no language signal.
        last_user_msg: The greeting; "你好" in an English UI is answered in Chinese.
        topic_finder: Topic Finder conversations get the coach's opening question.
    """
    from services.conversation.language import detect_reply_language

    language = detect_reply_language(interface_language, last_user_msg)
    replies = _TOPIC_FINDER_GREETING_REPLIES if topic_finder else _GREETING_REPLIES
    return replies.get(language, replies["zh-TW"])


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
    """Return the structured EDF response policy from the configured backend."""

    return await classify_with_backend(
        lambda: classify_response_policy_impl(
            client,
            model,
            user_msg,
            chat_history,
            has_pdf_attachment=has_pdf_attachment,
            pdf_attachment_count=pdf_attachment_count,
        ),
        client,
        user_msg,
        chat_history,
        has_pdf_attachment=has_pdf_attachment,
    )
