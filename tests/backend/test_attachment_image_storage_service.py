"""Tests for Supabase Storage persistence of PDF attachment visuals."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.services.attachment_image_storage_service import AttachmentImageStorageService
from backend.services.visual_answer_service import ImageBlock


@dataclass
class FakeResponse:
    """Minimal httpx response test double."""

    payload: dict

    def raise_for_status(self) -> None:
        """Simulate a successful HTTP response."""

    def json(self) -> dict:
        """Return deterministic JSON response data."""

        return self.payload


class FakeAsyncClient:
    """Capture Supabase Storage requests without network I/O."""

    def __init__(self, **kwargs):
        """Store constructor kwargs for assertions when needed."""

        self.kwargs = kwargs
        self.calls: list[dict] = []

    async def __aenter__(self):
        """Return the fake client for async context manager usage."""

        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """No-op async context manager cleanup."""

    async def post(self, url: str, **kwargs):
        """Record requests and return upload/sign responses."""

        self.calls.append({"url": url, **kwargs})
        if "/object/sign/" in url:
            return FakeResponse({"signedURL": "/object/sign/bucket/path?token=abc"})
        return FakeResponse({"Key": "ok"})


def _pdf_block() -> ImageBlock:
    """Build a request-scoped PDF image block."""

    return ImageBlock(
        slot_id="pdf_img_1",
        topic="paper.pdf 第 1 頁",
        purpose="chart",
        image_url="data:image/png;base64,iVBORw0KGgo=",
        thumbnail_url="data:image/png;base64,iVBORw0KGgo=",
        source_url="#pdf-attachment-page-1",
        source_domain="uploaded PDF",
        caption="Figure 1",
        provider="pdf_attachment",
        license="user_provided_attachment",
        transient=True,
    )


@pytest.mark.asyncio
async def test_persist_pdf_image_block_uploads_to_supabase_and_returns_signed_url(monkeypatch):
    """Persisted PDF visuals should become non-transient signed URL blocks."""

    clients: list[FakeAsyncClient] = []

    def factory(**kwargs):
        client = FakeAsyncClient(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr("backend.services.attachment_image_storage_service.settings.supabase_url", "https://example.supabase.co")
    monkeypatch.setattr("backend.services.attachment_image_storage_service.settings.next_public_supabase_url", "")
    monkeypatch.setattr("backend.services.attachment_image_storage_service.settings.supabase_service_role_key", "service-role")
    monkeypatch.setattr("backend.services.attachment_image_storage_service.settings.pdf_attachment_image_storage_bucket", "bucket")
    monkeypatch.setattr("backend.services.attachment_image_storage_service.settings.enable_pdf_attachment_image_storage", True)
    monkeypatch.setattr("backend.services.attachment_image_storage_service.settings.pdf_attachment_image_signed_url_ttl_seconds", 120)

    service = AttachmentImageStorageService(async_client_factory=factory)

    persisted = await service.persist_pdf_image_block(
        block=_pdf_block(),
        conversation_id="conversation 1",
    )

    assert persisted.transient is False
    assert persisted.image_url == "https://example.supabase.co/storage/v1/object/sign/bucket/path?token=abc"
    assert persisted.thumbnail_url == persisted.image_url
    assert persisted.storage_bucket == "bucket"
    assert persisted.storage_path.startswith("conversations/conversation-1/pdf-visuals/pdf_img_1-")
    assert persisted.storage_expires_at is not None
    assert len(clients[0].calls) == 2
    assert clients[0].calls[0]["headers"]["x-upsert"] == "true"
    assert clients[0].calls[1]["json"] == {"expiresIn": 120}


def test_absolute_signed_url_normalizes_supabase_storage_relative_path():
    """Supabase signed URL payloads may omit the `/storage/v1` prefix."""

    signed_url = AttachmentImageStorageService._absolute_signed_url(
        "https://example.supabase.co",
        {"signedURL": "/object/sign/bucket/path.png?token=abc"},
    )

    assert signed_url == "https://example.supabase.co/storage/v1/object/sign/bucket/path.png?token=abc"


@pytest.mark.asyncio
async def test_persist_pdf_image_block_missing_config_returns_transient_block(monkeypatch, caplog):
    """Storage misconfiguration should not break live PDF visual answers."""

    caplog.set_level("INFO")
    monkeypatch.setattr("backend.services.attachment_image_storage_service.settings.supabase_url", "")
    monkeypatch.setattr("backend.services.attachment_image_storage_service.settings.next_public_supabase_url", "")
    monkeypatch.setattr("backend.services.attachment_image_storage_service.settings.supabase_service_role_key", "")
    monkeypatch.setattr("backend.services.attachment_image_storage_service.settings.enable_pdf_attachment_image_storage", True)

    original = _pdf_block()
    service = AttachmentImageStorageService()

    persisted = await service.persist_pdf_image_block(
        block=original,
        conversation_id="conversation-1",
    )

    assert persisted is original
    assert persisted.transient is True
    assert "pdf_visual.storage_skipped" in caplog.text
    assert "missing_config" in caplog.text
