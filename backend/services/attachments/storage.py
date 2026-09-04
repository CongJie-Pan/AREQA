"""Persist PDF attachment image blocks to Supabase Storage.

Rendered PDF visuals start as request-scoped data URIs so the vision model can
inspect the exact pixels produced during the chat turn. Durable conversations
cannot safely store those data URIs in IndexedDB/Supabase rows because they are
large and derived from uploaded files. This service converts only approved PDF
attachment image blocks into private Supabase Storage objects and returns signed
URLs that the existing frontend can persist and render after refresh.
"""

from __future__ import annotations

import base64
from dataclasses import replace
import hashlib
import logging
import re
import time
from typing import Any, Callable
from urllib.parse import quote

import httpx

from config import settings
from services.attachments.parsing import MAX_ATTACHMENT_BYTES
from services.pdf_visual_extraction_service import PDF_ATTACHMENT_IMAGE_PROVIDER
from services.visual_answer_service import ImageBlock


logger = logging.getLogger(__name__)

_PNG_DATA_URI_PREFIX = "data:image/png;base64,"
_SAFE_OBJECT_SEGMENT_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_PERSISTED_PNG_BYTES = min(MAX_ATTACHMENT_BYTES, 2 * 1024 * 1024)


class AttachmentImageStorageService:
    """Upload selected PDF visual PNGs and return persistent image metadata.

    Args:
        async_client_factory: Factory compatible with ``httpx.AsyncClient``.
            Tests pass a fake factory so no network request is made.

    Side Effects:
        On success, writes one PNG object to the configured Supabase Storage
        bucket and requests a signed URL. Expected structured logs:
        - INFO ``pdf_visual.storage_uploaded`` with safe counters and hashes.
        - INFO ``pdf_visual.storage_skipped`` for disabled/misconfigured/input
          paths.
        - WARNING ``pdf_visual.storage_failed`` for unexpected provider errors.

    Privacy:
        Logs never include image bytes, data URIs, signed URLs, service-role
        keys, raw user text, prompts, model output, or filenames from user
        uploads.
    """

    def __init__(
        self,
        *,
        async_client_factory: Callable[..., Any] = httpx.AsyncClient,
    ) -> None:
        """Initialize the Supabase Storage adapter."""

        self._async_client_factory = async_client_factory

    async def persist_pdf_image_block(
        self,
        *,
        block: ImageBlock,
        conversation_id: str,
    ) -> ImageBlock:
        """Return ``block`` with signed Supabase URLs when persistence succeeds.

        Args:
            block: Image block produced from a PDF visual candidate.
            conversation_id: Conversation correlation id used for object
                namespacing and logs.

        Returns:
            A non-transient ``ImageBlock`` with signed URLs and storage metadata
            when upload/signing succeeds. Returns the original block for all
            disabled, invalid, or failed paths so live streaming remains
            fail-soft.

        Side Effects:
            May upload a PNG object and create a signed URL via Supabase
            Storage REST API.
        """

        if block.provider != PDF_ATTACHMENT_IMAGE_PROVIDER:
            return block
        if not getattr(settings, "enable_pdf_attachment_image_storage", True):
            self._log_skipped(conversation_id, block.slot_id, "disabled")
            return block

        storage_config = self._storage_config()
        if storage_config is None:
            self._log_skipped(conversation_id, block.slot_id, "missing_config")
            return block

        png_bytes = self._decode_png_data_uri(block.image_url)
        if png_bytes is None:
            self._log_skipped(conversation_id, block.slot_id, "invalid_data_uri")
            return block
        if len(png_bytes) > _MAX_PERSISTED_PNG_BYTES:
            self._log_skipped(conversation_id, block.slot_id, "oversized_image")
            return block

        supabase_url, service_role_key, bucket, ttl_seconds = storage_config
        digest = hashlib.sha256(png_bytes).hexdigest()
        object_path = self._object_path(
            conversation_id=conversation_id,
            slot_id=block.slot_id,
            sha256=digest,
        )
        encoded_path = "/".join(quote(segment, safe="") for segment in object_path.split("/"))
        upload_url = f"{supabase_url}/storage/v1/object/{quote(bucket, safe='')}/{encoded_path}"
        sign_url = f"{supabase_url}/storage/v1/object/sign/{quote(bucket, safe='')}/{encoded_path}"

        try:
            async with self._async_client_factory(timeout=8.0) as client:
                upload_response = await client.post(
                    upload_url,
                    content=png_bytes,
                    headers={
                        "apikey": service_role_key,
                        "Authorization": f"Bearer {service_role_key}",
                        "Content-Type": "image/png",
                        "Cache-Control": "31536000",
                        "x-upsert": "true",
                    },
                )
                upload_response.raise_for_status()
                signed_response = await client.post(
                    sign_url,
                    json={"expiresIn": ttl_seconds},
                    headers={
                        "apikey": service_role_key,
                        "Authorization": f"Bearer {service_role_key}",
                        "Content-Type": "application/json",
                    },
                )
                signed_response.raise_for_status()
                signed_payload = signed_response.json()
        except Exception as exc:
            logger.warning(
                "pdf_visual.storage_failed conversation_id=%s slot_id=%s reason=%s",
                conversation_id,
                block.slot_id,
                type(exc).__name__,
            )
            return block

        signed_url = self._absolute_signed_url(supabase_url, signed_payload)
        if not signed_url:
            self._log_skipped(conversation_id, block.slot_id, "missing_signed_url")
            return block

        expires_at = int(time.time()) + ttl_seconds
        logger.info(
            "pdf_visual.storage_uploaded conversation_id=%s slot_id=%s bucket=%s object_hash=%s size_bytes=%s signed_url_ttl_seconds=%s",
            conversation_id,
            block.slot_id,
            bucket,
            digest[:16],
            len(png_bytes),
            ttl_seconds,
        )
        return replace(
            block,
            image_url=signed_url,
            thumbnail_url=signed_url,
            storage_bucket=bucket,
            storage_path=object_path,
            storage_expires_at=expires_at,
            transient=False,
        )

    @staticmethod
    def _storage_config() -> tuple[str, str, str, int] | None:
        """Return validated Supabase Storage config or ``None``."""

        supabase_url = (
            str(getattr(settings, "supabase_url", "") or "")
            or str(getattr(settings, "next_public_supabase_url", "") or "")
        ).strip().rstrip("/")
        service_role_key = str(getattr(settings, "supabase_service_role_key", "") or "").strip()
        bucket = str(
            getattr(settings, "pdf_attachment_image_storage_bucket", "areqa-pdf-visuals") or ""
        ).strip()
        ttl_seconds = max(
            60,
            min(
                int(getattr(settings, "pdf_attachment_image_signed_url_ttl_seconds", 2592000) or 2592000),
                60 * 60 * 24 * 365,
            ),
        )
        if not supabase_url or not service_role_key or not bucket:
            return None
        return supabase_url, service_role_key, bucket, ttl_seconds

    @staticmethod
    def _decode_png_data_uri(image_url: str) -> bytes | None:
        """Decode a bounded PNG data URI without accepting arbitrary media."""

        value = str(image_url or "").strip()
        if not value.startswith(_PNG_DATA_URI_PREFIX):
            return None
        try:
            return base64.b64decode(value[len(_PNG_DATA_URI_PREFIX) :], validate=True)
        except Exception:
            return None

    @staticmethod
    def _object_path(*, conversation_id: str, slot_id: str, sha256: str) -> str:
        """Build a deterministic object path scoped to one conversation."""

        safe_conversation = AttachmentImageStorageService._safe_segment(conversation_id, "unknown")
        safe_slot = AttachmentImageStorageService._safe_segment(slot_id, "pdf_img")
        return f"conversations/{safe_conversation}/pdf-visuals/{safe_slot}-{sha256[:16]}.png"

    @staticmethod
    def _safe_segment(value: str, fallback: str) -> str:
        """Return a bounded Storage object-path segment."""

        normalized = _SAFE_OBJECT_SEGMENT_PATTERN.sub("-", str(value or "")).strip(".-")
        return (normalized or fallback)[:80]

    @staticmethod
    def _absolute_signed_url(supabase_url: str, payload: Any) -> str:
        """Extract a signed URL from Supabase's JSON response."""

        if not isinstance(payload, dict):
            return ""
        signed_url = str(payload.get("signedURL") or payload.get("signedUrl") or "").strip()
        if not signed_url:
            return ""
        if signed_url.startswith("http://") or signed_url.startswith("https://"):
            return signed_url
        if signed_url.startswith("/"):
            if signed_url.startswith("/storage/v1/"):
                return f"{supabase_url}{signed_url}"
            return f"{supabase_url}/storage/v1{signed_url}"
        return f"{supabase_url}/storage/v1/{signed_url.lstrip('/')}"

    @staticmethod
    def _log_skipped(conversation_id: str, slot_id: str, reason: str) -> None:
        """Emit a safe storage skip log with a stable reason code."""

        logger.info(
            "pdf_visual.storage_skipped conversation_id=%s slot_id=%s reason=%s",
            conversation_id,
            slot_id,
            reason,
        )
