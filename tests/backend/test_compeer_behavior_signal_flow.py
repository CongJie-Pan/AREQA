import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import memory_store as mem_store_module
from auth import get_current_user
from backend.main import app
from config import settings
from memory_store import get_global_store, init_global_store
import services.compeer_scheduler as compeer


class FakePipeline:
    """Provide the Redis pipeline methods used by behavior-signal storage tests.

    The regression path must exercise the same append and consume methods as
    production code. This fake keeps those operations deterministic without
    requiring a real Redis server.
    """

    def __init__(self, fake_redis):
        self.redis = fake_redis
        self.pending_set = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def watch(self, key):
        return None

    def multi(self):
        return None

    async def get(self, key):
        return await self.redis.get(key)

    def set(self, key, value):
        self.pending_set = (key, value)

    async def execute(self):
        if self.pending_set:
            await self.redis.set(*self.pending_set)


class FakeRedis:
    """In-memory Redis subset for API telemetry and scheduler regression tests."""

    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = value

    async def delete(self, key):
        self.data.pop(key, None)

    async def incr(self, key):
        value = int(self.data.get(key) or 0) + 1
        self.data[key] = str(value)
        return value

    async def expire(self, key, seconds):
        return True

    async def exists(self, key):
        return int(key in self.data)

    def pipeline(self, transaction=True):
        return FakePipeline(self)


@pytest.fixture
def behavior_signal_store():
    """Install a global MemoryStore backed by FakeRedis for one test."""

    old_store = mem_store_module._global_store
    fake_redis = FakeRedis()
    with patch("memory_store.get_redis", return_value=fake_redis), patch(
        "services.compeer_scheduler.get_redis",
        return_value=fake_redis,
    ):
        init_global_store(budget_limit=1000000)
        app.dependency_overrides[get_current_user] = lambda: "test_user"
        yield get_global_store(), fake_redis

    app.dependency_overrides.clear()
    mem_store_module._global_store = old_store


@pytest.mark.asyncio
async def test_log_action_behavior_signals_drive_compeer_schedule_once(
    behavior_signal_store,
    monkeypatch,
):
    monkeypatch.setattr(settings, "enable_compeer_auto_proactive", True)
    store, fake_redis = behavior_signal_store

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        for index in range(6):
            response = await client.post(
                "/api/v1/log_action",
                json={
                    "action_type": "scroll",
                    "timestamp": 1234567890 + index,
                    "context": {"scrollY": 1000 + index},
                },
            )
            assert response.status_code == 200

    await asyncio.sleep(0)
    signals_data = await fake_redis.get("areqa:behavior_signals:test_user")
    signals = json.loads(signals_data) if signals_data else []
    assert len(signals) == 6

    scheduled = AsyncMock(return_value="task-1")
    with patch.object(
        compeer,
        "get_last_interaction_time",
        new=AsyncMock(return_value=time.time() - 120),
    ), patch.object(
        compeer,
        "is_in_cooldown",
        new=AsyncMock(return_value=False),
    ), patch.object(
        compeer,
        "tick_proactive_schedule",
        new=AsyncMock(),
    ), patch(
        "gum_integration.get_hot_memory_snapshot",
        new=AsyncMock(return_value="【工作記憶 (Working Memory)】\n- Current focus: force"),
    ), patch(
        "gum_integration.detect_proactive_event_via_llm",
        new=AsyncMock(
            return_value={
                "has_event": True,
                "importance": 0.9,
                "event_summary": "User paused while reviewing force.",
            }
        ),
    ), patch(
        "gum_integration.query_cold_memory_for_context",
        new=AsyncMock(return_value=""),
    ), patch.object(
        compeer,
        "_schedule_areqa_care_letter_safely",
        new=scheduled,
    ), patch.object(
        compeer,
        "set_cooldown",
        new=AsyncMock(),
    ):
        await compeer._process_proactive_user(store, "test_user")
        await compeer._process_proactive_user(store, "test_user")

    scheduled.assert_awaited_once()
    remaining_data = await fake_redis.get("areqa:behavior_signals:test_user")
    remaining = json.loads(remaining_data) if remaining_data else []
    assert remaining == []
    assert await fake_redis.get(compeer._compeer_daily_counter_key("test_user")) == "1"
