"""Deterministic provider parser and rewrite helpers for visual answers.

This mixin contains provider payload parsers, request header construction,
privacy-safe query rewrite helpers, and HTTP error metadata extraction. It must
not emit raw queries, prompts, image URLs, credentials, or model output in logs.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

from config import settings
from services.visual_affordance_registry import match_visual_affordance
from services.visual_answer.constants import (
    _DEFAULT_VISUAL_USER_AGENT,
    _PROVIDER_PRIORITY,
    _VISUAL_QUERY_REWRITE_RULES,
    _VISUAL_TYPE_HINTS,
)
from services.visual_answer.models import ImageCandidate
from services.visual_grounding_agent import VisualBrief

logger = logging.getLogger(__name__)


class VisualAnswerProviderHelperMixin:
    """Normalize provider payloads and maintain provider query helpers."""

    @classmethod
    def _provider_headers(cls, provider: str) -> dict[str, str]:
        """Build provider request headers without exposing credentials in logs.

        Wikimedia and Openverse both accept public requests, but a stable
        User-Agent makes AREQA identifiable to provider infrastructure and
        reduces anonymous-client blocking. Openverse can optionally use an
        OAuth bearer token to raise rate limits when configured.
        """

        headers = {
            "User-Agent": settings.areqa_visual_user_agent.strip() or _DEFAULT_VISUAL_USER_AGENT,
        }
        if provider == "openverse":
            token = (
                os.environ.get("OPENVERSE_ACCESS_TOKEN", "").strip()
                or os.environ.get("OPENVERSE_API_TOKEN", "").strip()
            )
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _perplexity_image_messages(query: str, visual_brief: VisualBrief | None) -> list[dict[str, str]]:
        """Build the Sonar prompt used only for image retrieval."""

        system_prompt = (
            "You are retrieving images for an educational answer. Find concrete, "
            "non-decorative images that directly support the current teaching "
            "strategy, not just the topic keywords. Match the requested visual "
            "type and learning purpose so the image can be embedded next to an "
            "explanation. Prefer diagrams, maps, charts, timelines, labeled "
            "figures, or historically/source-relevant photos when those match "
            "the request. Prefer educational, museum, archive, university, and "
            "Wikimedia-style sources. Avoid book covers, document scans, logos, "
            "shopping/product pages, unrelated photos, and generic thumbnails "
            "unless the user explicitly asks for them."
        )
        teaching_context = (
            visual_brief.teaching_context.to_prompt_payload()
            if visual_brief and visual_brief.teaching_context is not None
            else None
        )
        user_payload = {
            "image_search_query": query,
            "visual_brief": (
                {
                    "visual_type": visual_brief.visual_type,
                    "caption_goal": visual_brief.caption_goal,
                    "reject_if": list(visual_brief.reject_if),
                    "teaching_context": teaching_context,
                }
                if visual_brief
                else None
            ),
            "source_preferences": {
                "prefer": [
                    "educational diagrams",
                    "labeled maps",
                    "timelines",
                    "charts",
                    "museums",
                    "archives",
                    "universities",
                    "Wikimedia Commons",
                ],
                "reject": [
                    "shopping pages",
                    "product photos",
                    "book covers",
                    "document scans",
                    "decorative thumbnails",
                    "generic stock images",
                ],
            },
            "instruction": "Return image results with direct image URLs and source/origin URLs.",
        }
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]

    @classmethod
    def _perplexity_image_candidate(cls, item: Any) -> ImageCandidate | None:
        """Convert one Sonar image result into AREQA's provider candidate model."""

        if not isinstance(item, dict):
            return None
        image_url = str(item.get("image_url") or item.get("url") or "").strip()
        source_url = str(item.get("origin_url") or item.get("source_url") or image_url).strip()
        title = cls._clean_text(str(item.get("title") or ""))
        if not image_url or not source_url:
            return None
        return ImageCandidate(
            provider="perplexity_images",
            image_url=image_url,
            thumbnail_url=str(item.get("thumbnail_url") or image_url).strip(),
            source_url=source_url,
            title=title,
            caption=title,
            license="unknown",
            width=cls._optional_int(item.get("width")),
            height=cls._optional_int(item.get("height")),
        )

    @classmethod
    def _tavily_image_candidates(cls, payload: Any) -> list[ImageCandidate]:
        """Normalize Tavily image payloads into provider-agnostic candidates."""

        if not isinstance(payload, dict):
            return []

        candidates: list[ImageCandidate] = []
        for item in payload.get("images") or []:
            candidate = cls._tavily_image_candidate(item, None)
            if candidate is not None:
                candidates.append(candidate)

        for result in payload.get("results") or []:
            if not isinstance(result, dict):
                continue
            source_url = str(result.get("url") or "").strip() or None
            result_title = cls._clean_text(str(result.get("title") or ""))
            for item in result.get("images") or []:
                candidate = cls._tavily_image_candidate(item, source_url, result_title)
                if candidate is not None:
                    candidates.append(candidate)

        return candidates

    @classmethod
    def _tavily_image_candidate(
        cls,
        item: Any,
        source_url: str | None,
        fallback_title: str = "",
    ) -> ImageCandidate | None:
        """Convert one Tavily image result into AREQA's candidate model."""

        if isinstance(item, str):
            image_url = item.strip()
            title = fallback_title
            description = fallback_title
            resolved_source_url = source_url or image_url
        elif isinstance(item, dict):
            image_url = str(item.get("url") or item.get("image_url") or item.get("src") or "").strip()
            title = cls._clean_text(str(item.get("title") or fallback_title))
            description = cls._clean_text(str(item.get("description") or item.get("alt") or title))
            resolved_source_url = str(
                item.get("source_url")
                or item.get("source")
                or item.get("origin_url")
                or source_url
                or image_url
            ).strip()
        else:
            return None

        if not image_url or not resolved_source_url:
            return None
        return ImageCandidate(
            provider="tavily_images",
            image_url=image_url,
            thumbnail_url=image_url,
            source_url=resolved_source_url,
            title=title,
            caption=description or title,
            license="unknown",
        )

    @classmethod
    def _serpapi_image_candidate(cls, item: Any) -> ImageCandidate | None:
        """Convert one SerpAPI Google Images result into AREQA's candidate model."""

        if not isinstance(item, dict):
            return None
        image_url = str(item.get("original") or item.get("image") or "").strip()
        thumbnail_url = str(item.get("thumbnail") or image_url).strip()
        source_url = str(item.get("link") or item.get("source_url") or image_url).strip()
        title = cls._clean_text(str(item.get("title") or item.get("source") or ""))
        if not image_url or not source_url:
            return None
        return ImageCandidate(
            provider="serpapi_images",
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            source_url=source_url,
            title=title,
            caption=title,
            license="unknown",
            creator=cls._clean_text(str(item.get("source") or "")),
            width=cls._optional_int(item.get("original_width") or item.get("width")),
            height=cls._optional_int(item.get("original_height") or item.get("height")),
        )

    @staticmethod
    def _visual_search_query(user_msg: str) -> tuple[str, str]:
        """Rewrite a user prompt into image-provider metadata language.

        Open image providers primarily match titles, captions, and filenames.
        For abstract learning questions, stable rule-based rewrites improve hit
        rate without adding another foreground model call. Unknown non-English
        prompts keep a bounded topic string and append generic visual/source
        hints so public image search has enough topic context. Structured logs
        only emit the rewrite rule name, never this provider query.
        """

        normalized = " ".join(str(user_msg or "").strip().split())
        affordance = match_visual_affordance(normalized)
        if affordance is not None:
            return affordance.search_query, affordance.rule_name
        for rule_name, pattern, rewritten_query in _VISUAL_QUERY_REWRITE_RULES:
            if pattern.search(normalized):
                return rewritten_query, rule_name
        if normalized and not normalized.isascii():
            return (
                VisualAnswerService._generic_visual_search_query(normalized),
                "generic_non_english_visual_query",
            )
        fallback = normalized[:120] if normalized else "educational diagram"
        return fallback, "identity"

    @staticmethod
    def _generic_visual_search_query(normalized_prompt: str) -> str:
        """Build a provider-ready query for non-English prompts without topic loss.

        Args:
            normalized_prompt: User text after whitespace normalization.

        Returns:
            A bounded query that preserves the topic and adds provider-neutral
            visual/source hints. The string is intended for outbound image
            provider requests only and must not be written to structured logs.
        """

        lowered = normalized_prompt.lower()
        visual_hint = "educational explanatory diagram"
        source_hint = "Wikimedia Commons educational source"
        for _, keywords, hint in _VISUAL_TYPE_HINTS:
            if any(keyword in lowered for keyword in keywords):
                visual_hint = hint
                if "map" in hint:
                    source_hint = "Wikimedia Commons archive university source"
                break
        topic = normalized_prompt[:90].strip()
        return f"{topic} {visual_hint} {source_hint}".strip()[:160]

    @staticmethod
    def _http_status_code(exc: Exception) -> int | None:
        """Extract an HTTP status code from httpx exceptions when available."""

        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        return status_code if isinstance(status_code, int) else None

    @staticmethod
    def _safe_result_domain(result: dict[str, Any]) -> str:
        """Return a sanitized source domain for fallback logs."""

        source_url = str(result.get("url") or "")
        parsed = urlparse(source_url)
        return parsed.netloc.replace("www.", "") if parsed.netloc else ""

    @staticmethod
    def _http_response_header(exc: Exception, header: str) -> str:
        """Return one safe response header from an httpx exception."""

        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if not headers:
            return ""
        return str(headers.get(header, "")).strip()[:80]

    @staticmethod
    def _wikimedia_error_code(exc: Exception) -> str:
        """Return the MediaWiki API error code for debug logs, if present."""

        response = getattr(exc, "response", None)
        if not response:
            return ""
        try:
            payload = response.json()
        except Exception:
            return ""
        error = payload.get("error") if isinstance(payload, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        return str(code or "").strip()[:80]

    @staticmethod
    def _wikimedia_debug_logs_enabled() -> bool:
        """Return whether detailed Wikimedia failure logs are enabled."""

        return bool(settings.wikimedia_image_debug_logs)
