import logging
from unittest.mock import AsyncMock

import pytest

import backend.redis_client as redis_client


@pytest.fixture(autouse=True)
def reset_redis_client():
    original_client = redis_client._redis_client
    original_url = redis_client.settings.redis_url
    redis_client._redis_client = None
    yield
    redis_client._redis_client = original_client
    redis_client.settings.redis_url = original_url


@pytest.mark.asyncio
async def test_log_redis_open_status_logs_safe_open_endpoint(monkeypatch, caplog):
    fake_redis = AsyncMock()
    fake_redis.ping = AsyncMock(return_value=True)
    redis_client.settings.redis_url = "rediss://:secret-password@cloud.example.com:6380/2"
    monkeypatch.setattr(redis_client.redis, "from_url", lambda *args, **kwargs: fake_redis)

    with caplog.at_level(logging.INFO):
        is_open = await redis_client.log_redis_open_status()

    assert is_open is True
    assert "system.redis_open_status status=open endpoint=rediss://cloud.example.com:6380/2" in caplog.text
    assert "secret-password" not in caplog.text
    fake_redis.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_log_redis_open_status_logs_closed_reason_without_secret(monkeypatch, caplog):
    fake_redis = AsyncMock()
    fake_redis.ping = AsyncMock(side_effect=ConnectionError("cannot connect"))
    redis_client.settings.redis_url = "redis://:secret-password@cloud.example.com:6379/0"
    monkeypatch.setattr(redis_client.redis, "from_url", lambda *args, **kwargs: fake_redis)

    with caplog.at_level(logging.WARNING):
        is_open = await redis_client.log_redis_open_status()

    assert is_open is False
    assert "system.redis_open_status status=closed endpoint=redis://cloud.example.com:6379/0 reason=ConnectionError" in caplog.text
    assert "secret-password" not in caplog.text
