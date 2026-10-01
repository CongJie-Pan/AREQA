"""Candidate scoring and safety mixin for visual answer enrichment.

The mixin owns deterministic candidate scoring and browser-display safety gates.
It uses only bounded metadata and domains; raw user messages, prompts, and full
image URLs stay outside the structured logging boundary.
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

from services.visual_answer.constants import (
    _IMAGE_CDN_DOMAIN_SUFFIXES,
    _INACCESSIBLE_IMAGE_DOMAIN_CACHE,
    _INACCESSIBLE_IMAGE_DOMAIN_TTL_SECONDS,
    _LOW_QUALITY_SOURCE_DOMAINS,
    _NEGATIVE_TERMS,
    _PLACEHOLDER_DOMAINS,
    _PROVIDER_PRIORITY,
    _PURPOSE_TERMS,
    _TRUSTED_SOURCE_DOMAINS,
    _UNSTABLE_IMAGE_INPUT_DOMAINS,
)
from services.visual_answer.models import ImageCandidate

logger = logging.getLogger(__name__)


class VisualAnswerScoringMixin:
    """Score image candidates and enforce deterministic safety filters."""

    def _heuristic_score(self, candidate: ImageCandidate, query: str) -> float:
        """Score candidate relevance using provider metadata only."""

        query_tokens = self._tokens(query)
        metadata = " ".join(
            [candidate.title, candidate.caption, candidate.creator, candidate.attribution_string]
        )
        metadata_tokens = self._tokens(metadata)
        overlap = len(query_tokens & metadata_tokens) / max(len(query_tokens), 1)
        purpose_bonus = 0.12 if _PURPOSE_TERMS & metadata_tokens else 0.0
        provider_bonus = _PROVIDER_PRIORITY.get(candidate.provider, 0.0)
        dimension_bonus = 0.08 if self._has_useful_dimensions(candidate) else 0.0
        pedagogy_bonus = min(self._pedagogical_score(candidate) * 0.2, 0.2)
        source_quality = self._source_quality_score(candidate)
        score = (
            overlap
            + purpose_bonus
            + provider_bonus
            + dimension_bonus
            + pedagogy_bonus
            + source_quality
        )
        return min(max(score, 0.0), 1.0)

    @classmethod
    def _source_quality_score(cls, candidate: ImageCandidate) -> float:
        """Score source-domain reliability using provider metadata only.

        Returns:
            A small positive boost for stable educational/archive/encyclopedic
            sources and a penalty for social, marketplace, or worksheet-hosting
            domains that often rank highly in image search but fail grounding.
        """

        domain = urlparse(candidate.source_url).netloc.lower().removeprefix("www.")
        if not domain:
            return 0.0
        if any(source in domain for source in _LOW_QUALITY_SOURCE_DOMAINS):
            return -0.25
        if any(
            cls._domain_matches_source_quality_pattern(domain, source)
            for source in _TRUSTED_SOURCE_DOMAINS
        ):
            return 0.18
        return 0.0

    @staticmethod
    def _domain_matches_source_quality_pattern(domain: str, pattern: str) -> bool:
        """Return whether a sanitized domain matches a source-quality pattern."""

        if pattern.startswith("."):
            return domain.endswith(pattern)
        return domain == pattern or domain.endswith(f".{pattern}") or pattern in domain

    @classmethod
    def _pedagogical_score(cls, candidate: ImageCandidate) -> float:
        """Score cheap metadata signals for instructional usefulness."""

        metadata = f"{candidate.title} {candidate.caption} {candidate.attribution_string}".lower()
        signals = (
            "annotated",
            "labeled",
            "diagram",
            "chart",
            "map",
            "timeline",
            "process",
            "flow",
            "overview",
            "comparison",
            "structure",
            "model",
            "figure",
            "illustration",
            "visualization",
            "framework",
            "steps",
            "axis",
            "legend",
        )
        score = sum(0.1 for signal in signals if signal in metadata)
        if candidate.provider == "wikimedia":
            score += 0.15
        if len(candidate.caption) >= 80:
            score += 0.1
        if cls._has_useful_dimensions(candidate):
            score += 0.1
        return min(score, 1.0)

    @classmethod
    def mark_inaccessible_image_domain(cls, image_url: str, *, reason: str) -> None:
        """Temporarily penalize domains that block backend image input.

        Args:
            image_url: Selected image URL that failed backend-side download.
            reason: Stable reason code such as ``HTTPStatusError:403``.

        Side Effects:
            Writes an in-process TTL entry used by candidate safety checks.
            Logs only the domain and reason code, never the full image URL.
        """

        domain = cls._safe_image_domain(image_url)
        if not domain:
            return
        _INACCESSIBLE_IMAGE_DOMAIN_CACHE[domain] = int(time.time()) + _INACCESSIBLE_IMAGE_DOMAIN_TTL_SECONDS
        logger.info(
            "visual.input_domain_penalized source_domain=%s reason=%s ttl_seconds=%s",
            domain,
            cls._safe_cache_reason(reason),
            _INACCESSIBLE_IMAGE_DOMAIN_TTL_SECONDS,
        )

    @classmethod
    def _is_safe_candidate(cls, candidate: ImageCandidate) -> bool:
        """Reject candidates that cannot be safely rendered or attributed."""

        for url in (candidate.image_url, candidate.source_url):
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return False
            domain = parsed.netloc.lower().removeprefix("www.")
            if domain in _UNSTABLE_IMAGE_INPUT_DOMAINS:
                return False
            if cls._is_inaccessible_image_domain(domain):
                return False
        if not cls._display_image_url(candidate):
            return False
        lowered = f"{candidate.image_url} {candidate.title} {candidate.caption}".lower()
        if any(term in lowered for term in _NEGATIVE_TERMS):
            return False
        if candidate.width is not None and candidate.width < 240:
            return False
        if candidate.height is not None and candidate.height < 160:
            return False
        return True

    @staticmethod
    def _safe_image_domain(image_url: str) -> str:
        """Return a safe lowercase domain label for an image URL."""

        parsed = urlparse(str(image_url or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        return parsed.netloc.lower().removeprefix("www.")

    @staticmethod
    def _is_inaccessible_image_domain(domain: str) -> bool:
        """Return whether a domain is temporarily blocked for image input."""

        normalized = str(domain or "").lower().removeprefix("www.")
        if not normalized:
            return False
        expires_at = _INACCESSIBLE_IMAGE_DOMAIN_CACHE.get(normalized)
        if not expires_at:
            return False
        if expires_at <= int(time.time()):
            _INACCESSIBLE_IMAGE_DOMAIN_CACHE.pop(normalized, None)
            return False
        return True

    @classmethod
    def _display_image_url(cls, candidate: ImageCandidate) -> str:
        """Return the best browser-displayable image URL for a candidate."""

        for url in (candidate.thumbnail_url, candidate.image_url):
            if cls._is_browser_display_image_url(url):
                return url
        return ""

    @staticmethod
    def _is_browser_display_image_url(url: str) -> bool:
        """Return whether a URL is likely renderable by browser img/lightbox."""

        parsed = urlparse(str(url or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        domain = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.lower()
        unsupported_extensions = (".tif", ".tiff", ".pdf", ".djvu", ".jp2")
        supported_extensions = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")
        if path.endswith(unsupported_extensions):
            return False
        if path.endswith(supported_extensions):
            return True
        if any(f"{extension}/" in path for extension in supported_extensions):
            return True
        return any(domain == suffix or domain.endswith(f".{suffix}") for suffix in _IMAGE_CDN_DOMAIN_SUFFIXES)

    @staticmethod
    def _has_useful_dimensions(candidate: ImageCandidate) -> bool:
        """Return whether known dimensions are suitable for a learning card."""

        if candidate.width is None or candidate.height is None:
            return False
        ratio = candidate.width / max(candidate.height, 1)
        return candidate.width >= 480 and candidate.height >= 240 and 0.4 <= ratio <= 3.2
