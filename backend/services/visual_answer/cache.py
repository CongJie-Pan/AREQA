"""Redis cache mixin and text codecs for visual answer enrichment.

This mixin owns visual cache keys, cache payload validation, and frontend-payload
restoration. Cache logs expose only conversation ids and reason/status buckets;
cache payloads may contain image metadata but logs must never include raw user
text, prompts, credentials, or image URLs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

from config import settings
from services.visual_answer.constants import (
    _NEGATIVE_CACHE_SENTINEL,
    _PLACEHOLDER_DOMAINS,
    _POSITIVE_CACHE_TTL_SECONDS,
    _UNSTABLE_IMAGE_INPUT_DOMAINS,
    _VISUAL_CACHE_CAPABILITY_SCHEMA,
    _VISUAL_CACHE_VERSION,
    _TITLE_PATTERN,
)
from services.visual_answer.models import ImageBlock
from services.visual_grounding_agent import VisualBrief

logger = logging.getLogger(__name__)


class VisualAnswerCacheMixin:
    """Read, write, validate, and restore visual answer cache entries."""

    async def _read_cache(self, cache_key: str, conversation_id: str) -> dict[str, Any] | None:
        """Read a cached visual image block or negative sentinel from Redis."""

        redis_url = os.environ.get("REDIS_URL", "")
        if not redis_url:
            return None
        redis_client = None
        try:
            redis_client = self._redis_factory(redis_url, decode_responses=True)
            cached = await redis_client.get(cache_key)
            if not cached:
                logger.info("visual.cache_miss conversation_id=%s", conversation_id)
                return None
            payload = json.loads(cached)
            logger.info(
                "visual.cache_hit conversation_id=%s status=%s",
                conversation_id,
                payload.get("status", "hit"),
            )
            if payload.get("status") == "negative":
                cached_capability = str(payload.get("capability_fingerprint") or "")
                if cached_capability != self._visual_cache_capability_fingerprint():
                    logger.info(
                        "visual.cache_rejected conversation_id=%s reason=stale_negative_capability",
                        conversation_id,
                    )
                    return None
                return _NEGATIVE_CACHE_SENTINEL
            image_block = payload.get("image_block")
            if not isinstance(image_block, dict):
                return None
            if not self._is_safe_cached_image_block(image_block):
                logger.info(
                    "visual.cache_rejected conversation_id=%s reason=unsafe_cached_image",
                    conversation_id,
                )
                return None
            return image_block
        except Exception:
            logger.info("visual.cache_miss conversation_id=%s", conversation_id)
            return None
        finally:
            if redis_client:
                await redis_client.aclose()

    async def _write_cache(
        self,
        cache_key: str,
        image_block: dict[str, Any],
        ttl_seconds: int,
        conversation_id: str,
        *,
        negative_reason: str = "",
    ) -> None:
        """Write a selected image block or negative sentinel to Redis.

        Negative entries include a capability fingerprint so transient misses
        from an older vision/provider configuration do not suppress image
        retrieval after deployment changes. Logs only expose cache state and
        safe correlation ids; user text, prompts, image URLs, and credentials
        remain outside the logging boundary.
        """

        redis_url = os.environ.get("REDIS_URL", "")
        if not redis_url:
            return
        redis_client = None
        try:
            redis_client = self._redis_factory(redis_url, decode_responses=True)
            status = "negative" if image_block == _NEGATIVE_CACHE_SENTINEL else "hit"
            payload: dict[str, Any] = {
                "status": status,
                "image_block": None if status == "negative" else image_block,
                "retrieved_at": int(time.time()),
                "cache_version": _VISUAL_CACHE_VERSION,
                "capability_fingerprint": self._visual_cache_capability_fingerprint(),
            }
            if status == "negative":
                payload["negative_reason"] = self._safe_cache_reason(negative_reason)
            await redis_client.set(
                cache_key,
                json.dumps(payload, ensure_ascii=False),
                ex=ttl_seconds,
            )
        except Exception:
            logger.info("visual.cache_write_skipped conversation_id=%s", conversation_id)
        finally:
            if redis_client:
                await redis_client.aclose()

    async def commit_positive_cache(self, block: ImageBlock, *, conversation_id: str) -> None:
        """Commit a selected image to cache after vision understanding succeeds.

        Args:
            block: Image block that survived output understanding.
            conversation_id: Correlation id for safe structured logs.

        Side Effects:
            Writes a positive Redis cache entry only when ``block.cache_key`` is
            present. This deliberately moves positive-cache ownership after the
            output understanding gate so inaccessible provider URLs do not get
            cached as successful image answers.
        """

        if not block.cache_key:
            logger.info(
                "visual.output_cache_rejected conversation_id=%s slot_id=%s reason=missing_cache_key",
                conversation_id,
                block.slot_id,
            )
            return
        await self._write_cache(
            block.cache_key,
            block.to_frontend(),
            block.cache_ttl_seconds or _POSITIVE_CACHE_TTL_SECONDS,
            conversation_id,
        )
        logger.info(
            "visual.output_cache_committed conversation_id=%s slot_id=%s provider=%s source_domain=%s",
            conversation_id,
            block.slot_id,
            block.provider,
            block.source_domain or "unknown",
        )

    @classmethod
    def _cache_key(cls, query: str, purpose: str) -> str:
        """Return a privacy-preserving cache key for a visual slot."""

        normalized = " ".join(sorted(cls._tokens(query)))
        capability = cls._visual_cache_capability_fingerprint()
        digest = hashlib.sha256(
            f"{_VISUAL_CACHE_VERSION}:{purpose}:{normalized}:{capability}".encode("utf-8")
        ).hexdigest()
        return f"visual_image:{_VISUAL_CACHE_VERSION}:{purpose}:{digest}"

    @classmethod
    def _visual_cache_capability_fingerprint(cls) -> str:
        """Return a non-secret fingerprint for visual retrieval capabilities.

        The fingerprint intentionally excludes raw queries, prompts, image URLs,
        API keys, and provider credentials. It includes only coarse capability
        switches and safety policy inputs that affect whether a previously empty
        visual result should still be trusted.
        """

        payload = {
            "schema": _VISUAL_CACHE_CAPABILITY_SCHEMA,
            "cache_version": _VISUAL_CACHE_VERSION,
            "enable_perplexity_visual_search": bool(settings.enable_perplexity_visual_search),
            "enable_serpapi_visual_search": bool(settings.enable_serpapi_visual_search),
            "enable_tavily_visual_search": bool(settings.enable_tavily_visual_search),
            "enable_visual_preflight_open_provider_fallback": bool(
                settings.enable_visual_preflight_open_provider_fallback
            ),
            "enable_visual_understanding": bool(settings.enable_visual_understanding),
            "model_visual_understanding": str(settings.model_visual_understanding or ""),
            "unstable_image_input_domains": sorted(_UNSTABLE_IMAGE_INPUT_DOMAINS),
            "visual_grounding_max_candidates": int(settings.visual_grounding_max_candidates),
            "visual_preflight_grounding_max_candidates": int(
                settings.visual_preflight_grounding_max_candidates
            ),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def _visual_brief_cache_key(cls, brief: VisualBrief) -> str:
        """Return a preflight cache key scoped to the agent's visual intent.

        Preflight images are selected before answer generation and grounded
        against a model-planned brief. They must not reuse older generic
        diagram cache entries, because stale images can bypass the stricter
        grounding path. The key intentionally hashes normalized brief metadata
        and logs only the safe scope/type metadata at call sites.
        """

        purpose = f"preflight_{cls._safe_cache_purpose(brief.visual_type)}"
        fingerprint = json.dumps(
            {
                "caption_goal": brief.caption_goal,
                "reject_if": list(brief.reject_if),
                "search_query": brief.search_query,
                "teaching_context": (
                    brief.teaching_context.to_prompt_payload()
                    if brief.teaching_context is not None
                    else None
                ),
                "visual_type": brief.visual_type,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return cls._cache_key(fingerprint, purpose)

    @staticmethod
    def _safe_cache_purpose(value: str) -> str:
        """Normalize cache purpose fragments to stable non-empty identifiers."""

        normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").lower()).strip("_")
        return normalized or "visual"

    @staticmethod
    def _safe_cache_reason(value: str) -> str:
        """Normalize negative cache reasons to bounded operational labels."""

        normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").lower()).strip("_")
        return (normalized or "unknown")[:64]

    @staticmethod
    def _is_safe_cached_image_block(payload: dict[str, Any]) -> bool:
        """Return whether a cached frontend image block is still renderable.

        Cached visual blocks can outlive provider behavior changes. Revalidating
        the public URL shape on read prevents stale placeholder blocks from
        bypassing the provider safety gates after a deployment.
        """

        image_url = str(payload.get("imageUrl") or "")
        thumbnail_url = str(payload.get("thumbnailUrl") or image_url)
        source_url = str(payload.get("sourceUrl") or "")
        source_domain = str(payload.get("sourceDomain") or "")
        provider = str(payload.get("provider") or "")

        if provider not in {"perplexity_images", "wikimedia", "openverse", "og_image"}:
            return False

        for url in (image_url, thumbnail_url, source_url):
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return False
            if parsed.netloc.lower().removeprefix("www.") in _PLACEHOLDER_DOMAINS:
                return False

        parsed_source = urlparse(source_url)
        normalized_source_domain = parsed_source.netloc.lower().removeprefix("www.")
        if source_domain and source_domain.lower().removeprefix("www.") in _PLACEHOLDER_DOMAINS:
            return False
        if normalized_source_domain in _PLACEHOLDER_DOMAINS:
            return False

        return True

    @staticmethod
    def _image_block_from_frontend(payload: dict[str, Any]) -> ImageBlock:
        """Convert cached frontend payload back into an ImageBlock."""

        return ImageBlock(
            slot_id=str(payload.get("slotId") or "visual-1"),
            topic=str(payload.get("topic") or ""),
            purpose=str(payload.get("purpose") or "diagram"),
            image_url=str(payload.get("imageUrl") or ""),
            thumbnail_url=str(payload.get("thumbnailUrl") or payload.get("imageUrl") or ""),
            source_url=str(payload.get("sourceUrl") or ""),
            source_domain=str(payload.get("sourceDomain") or ""),
            caption=str(payload.get("caption") or ""),
            provider=str(payload.get("provider") or "cache"),
            license=str(payload.get("license") or "unknown"),
            license_url=str(payload.get("licenseUrl") or ""),
            creator=str(payload.get("creator") or ""),
            attribution_string=str(payload.get("attributionString") or ""),
            attribution_caption=str(payload.get("attributionCaption") or ""),
            explanatory_caption=str(payload.get("explanatoryCaption") or ""),
            width=VisualAnswerService._optional_int(payload.get("width")),
            height=VisualAnswerService._optional_int(payload.get("height")),
            safety_status=str(payload.get("safetyStatus") or "pass"),
            match_confidence=float(payload.get("matchConfidence") or 0.0),
            heuristic_score=float(payload.get("heuristicScore") or 0.0),
            pedagogical_score=float(payload.get("pedagogicalScore") or 0.0),
            vision_summary=str(payload.get("visionSummary") or ""),
            visible_elements=VisualAnswerService._string_tuple(payload.get("visibleElements"), 10, 140),
            how_to_read=VisualAnswerService._string_tuple(payload.get("howToRead"), 8, 180),
            vision_confidence=str(payload.get("visionConfidence") or "unknown"),
            vision_limitations=VisualAnswerService._string_tuple(payload.get("visionLimitations"), 6, 160),
            vision_source=str(payload.get("visionSource") or "unavailable"),
            storage_bucket=str(payload.get("storageBucket") or ""),
            storage_path=str(payload.get("storagePath") or ""),
            storage_expires_at=VisualAnswerService._optional_int(payload.get("storageExpiresAt")),
            transient=bool(payload.get("transient")),
        )

    @staticmethod
    def _string_tuple(value: Any, max_items: int, max_length: int) -> tuple[str, ...]:
        """Convert cached list payloads into bounded string tuples."""

        if not isinstance(value, list):
            return ()
        output: list[str] = []
        for item in value[:max_items]:
            text = VisualAnswerService._clean_text(str(item or ""))[:max_length]
            if text:
                output.append(text)
        return tuple(output)

    @staticmethod
    def _split_paragraphs(answer_text: str) -> list[str]:
        """Split completed answer Markdown into non-empty paragraph blocks."""

        return [part.strip() for part in re.split(r"\n{2,}", answer_text) if part.strip()]

    @staticmethod
    def _extract_title(html: str) -> str:
        """Extract a plain page title from HTML."""

        match = _TITLE_PATTERN.search(html)
        return match.group(1) if match else ""

    @staticmethod
    def _clean_text(text: str) -> str:
        """Collapse whitespace for safe captions."""

        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _clean_html(text: str) -> str:
        """Remove simple HTML tags frequently returned by provider metadata."""

        return VisualAnswerService._clean_text(re.sub(r"<[^>]+>", "", text))

    @staticmethod
    def _metadata_value(metadata: dict[str, Any], key: str) -> str:
        """Read Wikimedia extmetadata values safely."""

        value = metadata.get(key)
        if isinstance(value, dict):
            return str(value.get("value") or "")
        return ""

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        """Convert provider numeric metadata to optional int."""

        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _tokens(text: str) -> set[str]:
        """Tokenize mixed Chinese/English metadata for cheap relevance scoring."""

        lowered = text.lower()
        ascii_tokens = re.findall(r"[a-z0-9]{2,}", lowered)
        cjk_tokens = re.findall(r"[\u4e00-\u9fff]{2,}", lowered)
        return set(ascii_tokens + cjk_tokens)
