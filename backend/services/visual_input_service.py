"""Build OpenRouter-ready image input parts for output-image understanding.

This module mirrors the successful chat attachment image path for images that
AREQA retrieves itself. It downloads a selected public image with the same
declared crawler identity used by the visual retrieval pipeline, validates the
bytes as an image, and converts them to the same ``image_url`` data URI content
part used by user-uploaded attachments. The fallback remains a remote URL
content part for downstream diagnostics and compatibility, but callers that
require pixel-grounded understanding should treat it as unavailable input.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import io
import logging
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image, UnidentifiedImageError

from config import settings
from services.attachment_service import IMAGE_TYPES, MAX_ATTACHMENT_BYTES, MAX_IMAGE_PIXELS


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VisualImageInput:
    """Model input part for one selected output image.

    Args:
        content_part: OpenRouter-compatible multimodal content part.
        source: Stable source label, either ``data_uri`` or ``remote_url``.
        media_type: Detected image media type when known.
        size_bytes: Downloaded byte count when known.
        reason: Stable unavailable reason when source is ``remote_url``.
    """

    content_part: dict[str, Any]
    source: str
    media_type: str = "unknown"
    size_bytes: int = 0
    reason: str = ""


class VisualInputService:
    """Prepare selected remote images for vision-model requests.

    The service downloads only HTTP(S) image URLs already selected by the visual
    pipeline. Logs are intentionally privacy-safe: they record conversation id,
    source domain, reason codes, content type, and coarse size buckets, but
    never full URLs, prompts, raw user text, image bytes, credentials, or tokens.
    """

    def __init__(self, *, timeout_seconds: float = 3.0, max_bytes: int = MAX_ATTACHMENT_BYTES) -> None:
        """Initialize the input service.

        Args:
            timeout_seconds: Maximum time spent downloading a selected image.
            max_bytes: Maximum response body size accepted for data URI input.
        """

        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    async def prepare_image_part(self, *, image_url: str, conversation_id: str) -> VisualImageInput:
        """Return a data URI image part or a remote URL fallback.

        Args:
            image_url: Selected public image URL from ``ImageBlock``.
            conversation_id: Correlation id for safe structured logs.

        Returns:
            ``VisualImageInput`` with a data URI content part when download and
            validation succeed; otherwise a remote URL content part marked with
            ``source="remote_url"`` so callers can avoid provider-side URL
            fetching when they require deterministic vision input.
        """

        source_domain = self._safe_domain(image_url)
        if not self._is_safe_http_url(image_url):
            self._log_unavailable(conversation_id, source_domain, "invalid_image_url")
            return self.remote_url_part(image_url, reason="invalid_image_url")

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": settings.areqa_visual_user_agent},
            ) as client:
                response = await client.get(image_url)
                response.raise_for_status()
                data = response.content
        except httpx.HTTPStatusError as exc:
            self._log_unavailable(
                conversation_id,
                source_domain,
                f"HTTPStatusError:{exc.response.status_code}",
            )
            return self.remote_url_part(image_url, reason=f"HTTPStatusError:{exc.response.status_code}")
        except Exception as exc:
            self._log_unavailable(conversation_id, source_domain, type(exc).__name__)
            return self.remote_url_part(image_url, reason=type(exc).__name__)

        if not data:
            self._log_unavailable(conversation_id, source_domain, "empty_response")
            return self.remote_url_part(image_url, reason="empty_response")
        if len(data) > self.max_bytes:
            self._log_unavailable(conversation_id, source_domain, "image_too_large")
            return self.remote_url_part(image_url, reason="image_too_large")

        media_type = self._detect_image_type(data, response.headers.get("content-type", ""))
        if media_type not in IMAGE_TYPES:
            self._log_unavailable(conversation_id, source_domain, "unsupported_content_type")
            return self.remote_url_part(image_url, reason="unsupported_content_type")

        if not self._verify_image(data):
            self._log_unavailable(conversation_id, source_domain, "invalid_image_content")
            return self.remote_url_part(image_url, reason="invalid_image_content")

        encoded = base64.b64encode(data).decode("ascii")
        logger.info(
            "visual.input_data_uri_ready conversation_id=%s source_domain=%s media_type=%s size_bucket=%s",
            conversation_id,
            source_domain or "unknown",
            media_type,
            self._size_bucket(len(data)),
        )
        return VisualImageInput(
            content_part={"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}"}},
            source="data_uri",
            media_type=media_type,
            size_bytes=len(data),
        )

    @staticmethod
    def remote_url_part(image_url: str, *, reason: str = "") -> VisualImageInput:
        """Build a remote URL fallback image part."""

        return VisualImageInput(
            content_part={"type": "image_url", "image_url": {"url": str(image_url or "")}},
            source="remote_url",
            reason=reason,
        )

    @staticmethod
    def _detect_image_type(data: bytes, declared_content_type: str) -> str:
        """Detect a supported image type from bytes and optional content type."""

        if data.startswith(IMAGE_TYPES["image/png"][1]):
            return "image/png"
        if data.startswith(IMAGE_TYPES["image/jpeg"][1]):
            return "image/jpeg"
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return "image/webp"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        normalized = declared_content_type.split(";", 1)[0].strip().lower()
        return normalized if normalized in IMAGE_TYPES else "unknown"

    @staticmethod
    def _verify_image(data: bytes) -> bool:
        """Return whether Pillow can safely parse the image bytes."""

        try:
            Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                return width * height <= MAX_IMAGE_PIXELS
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError, SyntaxError, ValueError):
            return False

    @staticmethod
    def _is_safe_http_url(image_url: str) -> bool:
        """Validate URL shape before outbound download."""

        parsed = urlparse(str(image_url or ""))
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _safe_domain(image_url: str) -> str:
        """Extract a safe source domain label."""

        return urlparse(str(image_url or "")).netloc.lower().removeprefix("www.")

    @staticmethod
    def _size_bucket(size_bytes: int) -> str:
        """Bucket image size for privacy-safe logs."""

        if size_bytes < 100_000:
            return "lt_100kb"
        if size_bytes < 1_000_000:
            return "lt_1mb"
        return "lt_5mb"

    @staticmethod
    def _log_unavailable(conversation_id: str, source_domain: str, reason: str) -> None:
        """Emit the stable data URI fallback event."""

        logger.info(
            "visual.input_data_uri_unavailable conversation_id=%s source_domain=%s reason=%s",
            conversation_id,
            source_domain or "unknown",
            reason,
        )
