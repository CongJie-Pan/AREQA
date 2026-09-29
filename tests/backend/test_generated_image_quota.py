"""Quota and authenticated route contracts for paid image generation."""

import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.routes import generated_images as route
from auth import get_current_user
from services import generated_image_quota as quota
from services.generated_image_service import GeneratedImage


@pytest.mark.asyncio
async def test_image_quota_blocks_seventh_request_across_workers(monkeypatch):
    counts = {}

    class Redis:
        async def incr(self, key):
            counts[key] = counts.get(key, 0) + 1
            return counts[key]

        async def expire(self, key, ttl):
            assert ttl == 120
            return True

    monkeypatch.setattr(quota, "get_redis", lambda: Redis())
    monkeypatch.setattr(quota.time, "time", lambda: 120.0)
    assert [await quota.consume_image_quota("user-a") for _ in range(7)] == [True] * 6 + [False]
    assert await quota.consume_image_quota("user-b") is True


@pytest.mark.asyncio
async def test_image_quota_keeps_a_local_guard_when_redis_is_unavailable(monkeypatch):
    quota._fallback_counts.clear()
    monkeypatch.setattr(quota, "get_redis", lambda: (_ for _ in ()).throw(ConnectionError()))
    monkeypatch.setattr(quota.time, "time", lambda: 120.0)
    assert [await quota.consume_image_quota("user-a") for _ in range(7)] == [True] * 6 + [False]
    quota._fallback_counts.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("debug_logs", [False, True])
async def test_image_route_requires_auth_and_enforces_backend_quota(monkeypatch, caplog, debug_logs):
    app = FastAPI()
    app.include_router(route.router)
    seen = []
    monkeypatch.setattr(route.settings, "enable_generated_image_debug_logs", debug_logs)

    async def generate(*args, **kwargs):
        seen.append(kwargs)
        return GeneratedImage(image_url="https://example.test/image.png", model="test/model", caption="cat", cost_usd=0.01, transient=False)

    monkeypatch.setattr(route, "generate_teaching_image", generate)
    monkeypatch.setattr(route, "consume_image_quota", lambda user_id: _allowed(user_id))
    request = {"prompt": "Draw a cat", "conversation_id": "conv-a", "interface_language": "en"}
    with caplog.at_level(logging.INFO, logger=route.logger.name):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            unauthenticated = await client.post("/api/v1/images/generate", json=request)
            assert unauthenticated.status_code in {401, 403}
            app.dependency_overrides[get_current_user] = lambda: "user-a"
            valid = await client.post("/api/v1/images/generate", json=request)
            assert valid.status_code == 200
            assert valid.json()["block"]["provider"] == "generated_image"
            assert "model" not in valid.json()["block"]
            assert len(seen) == 1
            monkeypatch.setattr(route, "consume_image_quota", lambda user_id: _denied(user_id))
            limited = await client.post("/api/v1/images/generate", json=request)
            assert limited.status_code == 429
            assert len(seen) == 1
    assert ("image_generation.request_received" in caplog.text) is debug_logs
    assert ("image_generation.quota_rejected" in caplog.text) is debug_logs
    assert "Draw a cat" not in caplog.text


@pytest.mark.asyncio
async def test_refresh_route_uses_authenticated_owner_and_rejects_invalid_ids(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_current_user] = lambda: "user-a"
    seen = []

    async def refresh(self, **kwargs):
        seen.append(kwargs)
        return {"url": "https://example.test/renewed.png", "expires_at": 123}

    monkeypatch.setattr(route.AttachmentImageStorageService, "refresh_generated_image_url", refresh)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        invalid = await client.post("/api/v1/images/refresh", json={"conversation_id": "../other", "image_id": "image-a"})
        assert invalid.status_code == 400
        assert seen == []
        valid = await client.post("/api/v1/images/refresh", json={"conversation_id": "conv-a", "image_id": "image-a"})
        assert valid.status_code == 200
        assert valid.json()["imageUrl"] == "https://example.test/renewed.png"
        assert seen == [{"user_id": "user-a", "conversation_id": "conv-a", "image_id": "image-a"}]


@pytest.mark.asyncio
async def test_download_route_uses_authenticated_owner(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_current_user] = lambda: "user-a"
    seen = []

    async def download(self, **kwargs):
        seen.append(kwargs)
        return b"\x89PNG\r\n\x1a\n" + b"test"

    monkeypatch.setattr(route.AttachmentImageStorageService, "download_generated_image", download)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/images/download", json={"conversation_id": "conv-a", "image_id": "image-a"})
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.headers["content-disposition"].startswith("attachment")
        assert seen == [{"user_id": "user-a", "conversation_id": "conv-a", "image_id": "image-a"}]


async def _allowed(user_id):
    assert user_id == "user-a"
    return True


async def _denied(user_id):
    assert user_id == "user-a"
    return False


@pytest.mark.asyncio
async def test_reference_upload_reuses_parser_and_brief_is_passed_to_image_generation(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_current_user] = lambda: "user-a"
    seen = []

    async def prepare(attachments, **kwargs):
        assert attachments[0].plain_text == "Light becomes sugar."
        return "Light → sugar"

    async def generate(*args, **kwargs):
        seen.append(kwargs)
        return GeneratedImage(image_url="https://example.test/image.png", model="test/model", caption="source", cost_usd=0.03, transient=False)

    async def allowed(user_id):
        return True

    monkeypatch.setattr(route, "consume_image_quota", allowed)
    monkeypatch.setattr(route, "prepare_image_reference", prepare)
    monkeypatch.setattr(route, "generate_teaching_image", generate)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        prepared = await client.post("/api/v1/images/reference", data={"prompt": "Explain this source", "conversation_id": "conv-a"},
                                     files={"attachments": ("source.txt", b"Light becomes sugar.", "text/plain")})
        assert prepared.status_code == 200
        brief = prepared.json()["reference_brief"]
        result = await client.post("/api/v1/images/generate", json={"prompt": "Explain this source", "conversation_id": "conv-a", "reference_brief": brief})
        assert result.status_code == 200
        assert seen[0]["reference_brief"] == brief
        assert result.json()["block"]["generationRequest"]["referenceBrief"] == brief
        invalid = await client.post("/api/v1/images/generate", json={"prompt": "Explain", "conversation_id": "conv-a", "reference_brief": "a" * 4001})
        assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_routing_quota_is_independent_and_does_not_reduce_image_allowance(monkeypatch):
    quota._fallback_counts.clear()
    monkeypatch.setattr(quota, "get_redis", lambda: (_ for _ in ()).throw(ConnectionError()))
    monkeypatch.setattr(quota.time, "time", lambda: 120.0)
    assert [await quota.consume_image_quota("user-a:intent", limit=30) for _ in range(31)] == [True] * 30 + [False]
    assert [await quota.consume_image_quota("user-a") for _ in range(7)] == [True] * 6 + [False]
    quota._fallback_counts.clear()
