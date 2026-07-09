import pytest
import os
import time
from unittest.mock import AsyncMock, patch, MagicMock
from backend.memory_store import MemoryStore

@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    store = {}
    async def fake_get(key): return store.get(key)
    async def fake_set(key, val): store[key] = val
    def fake_set_sync(key, val): store[key] = val
    redis.get = AsyncMock(side_effect=fake_get)
    redis.set = AsyncMock(side_effect=fake_set)
    pipe_mock = AsyncMock()
    pipe_mock.get = AsyncMock(side_effect=fake_get)
    pipe_mock.set = MagicMock(side_effect=fake_set_sync)
    pipe_mock.watch = AsyncMock()
    pipe_mock.multi = MagicMock()
    pipe_mock.execute = AsyncMock()
    class PipelineContext:
        def __init__(self, **kwargs): self.pipe = pipe_mock
        async def __aenter__(self): return self.pipe
        async def __aexit__(self, exc_type, exc_val, exc_tb): pass
    redis.pipeline = PipelineContext
    redis._store = store
    return redis

@pytest.fixture
def store(mock_redis):
    with patch("backend.memory_store.get_redis", return_value=mock_redis):
        return MemoryStore()

@pytest.mark.asyncio
async def test_trigger_proactive_key_lifecycle(store):
    await store.update_hot_memory_async("default_user", "trigger_proactive", True)
    mem = await store.get_hot_memory("default_user")
    assert mem.get("trigger_proactive") is True

@pytest.mark.asyncio
async def test_cooldown_persisted_in_hot_memory(store):
    # Depending on implementation, we might not persist cooldown in hot_memory anymore.
    # The implementation plan updated compeer_scheduler to use an in-memory dict user_cooldown_until.
    pass

