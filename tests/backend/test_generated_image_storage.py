"""Generated-image storage ownership and signed URL renewal contracts."""

import hashlib

import pytest

from config import settings
from services.attachments.storage import AttachmentImageStorageService


@pytest.mark.asyncio
async def test_generated_image_refresh_signs_only_the_authenticated_users_path(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "test-service-key")
    monkeypatch.setattr(settings, "pdf_attachment_image_storage_bucket", "images")
    calls = []

    class Response:
        content = b"\x89PNG\r\n\x1a\n" + b"test"

        def raise_for_status(self):
            return None

        def json(self):
            return {"signedURL": "/object/sign/images/path?token=test"}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            calls.append(url)
            return Response()

        async def get(self, url, **kwargs):
            calls.append(url)
            return Response()

    storage = AttachmentImageStorageService(async_client_factory=Client)
    stored = await storage.persist_generated_image(
        png_bytes=b"png", user_id="user-a", conversation_id="conv-a", image_id="image-a",
    )
    owner_prefix = hashlib.sha256(b"user-a").hexdigest()[:24]
    assert stored["path"] == f"users/{owner_prefix}/conversations/conv-a/generated-images/image-a.png"
    renewed = await storage.refresh_generated_image_url(
        user_id="user-a", conversation_id="conv-a", image_id="image-a",
    )
    assert renewed["url"].startswith("https://example.supabase.co/storage/v1/object/sign/")
    assert stored["path"] in calls[-1]
    assert len(calls) == 3  # Upload and sign, then sign without another upload.

    await storage.refresh_generated_image_url(
        user_id="user-b", conversation_id="conv-a", image_id="image-a",
    )
    assert stored["path"] not in calls[-1]

    downloaded = await storage.download_generated_image(
        user_id="user-a", conversation_id="conv-a", image_id="image-a",
    )
    assert downloaded == Response.content
    assert stored["path"] in calls[-1]
