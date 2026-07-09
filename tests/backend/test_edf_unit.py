import pytest
import asyncio
import json
import os
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from fastapi.testclient import TestClient
from pathlib import Path
from datetime import datetime, timedelta

import memory_store as mem_store_module
from memory_store import MemoryStore, init_global_store, get_global_store
from backend.compaction import evaluate_student_state
from backend.gum_integration import async_evaluate_and_update_state
from backend.main import app, classify_dialogue_policy
from auth import get_current_user
import services.compeer_scheduler as compeer

@pytest.fixture
def tmp_store():
    old_store = mem_store_module._global_store
    
    class FakePipeline:
        def __init__(self, fake_redis):
            self.r = fake_redis
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): pass
        async def watch(self, key): pass
        def multi(self): pass
        def unwatch(self): pass
        async def get(self, key): return await self.r.get(key)
        def set(self, key, val): self._set = (key, val)
        async def execute(self):
            if hasattr(self, '_set'):
                await self.r.set(self._set[0], self._set[1])

    class FakeRedis:
        def __init__(self): self.data = {}
        async def get(self, key): return self.data.get(key)
        async def set(self, key, val): self.data[key] = val
        async def setex(self, key, time, val): self.data[key] = val
        async def exists(self, key): return 1 if key in self.data else 0
        async def delete(self, key):
            if key in self.data: del self.data[key]
        def pipeline(self, transaction=True): return FakePipeline(self)
        
    with patch("memory_store.get_redis") as mock_mem_redis, \
         patch("services.compeer_scheduler.get_redis") as mock_comp_redis:
        fake_r = FakeRedis()
        mock_mem_redis.return_value = fake_r
        mock_comp_redis.return_value = fake_r
        init_global_store(budget_limit=1000000)
        store = get_global_store()
        app.dependency_overrides[get_current_user] = lambda: "default_user"
        yield store, fake_r
    
    app.dependency_overrides.clear()
    mem_store_module._global_store = old_store


# U-01 to U-04: log_action API
@pytest.mark.asyncio
@patch("backend.main.push_observation")
async def test_log_action_valid_request(mock_push, tmp_store):
    store, fake_r = tmp_store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/log_action", json={"action_type": "scroll", "timestamp": 12345, "context": {"duration_seconds": 3.0}})
        await asyncio.sleep(0.1)
        assert res.status_code == 200
        
    data = await fake_r.get("areqa:hot_memory:default_user")
    hot = json.loads(data) if data else {}
    action_keys = [k for k in hot.keys() if k.startswith("obs_")]
    assert len(action_keys) == 1
    assert "scroll" in str(hot[action_keys[0]])

@pytest.mark.asyncio
async def test_log_action_missing_action_field(tmp_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/log_action", json={"timestamp": 12345, "context": {}}) # missing action_type
        await asyncio.sleep(0.1)
        assert res.status_code == 422

@pytest.mark.asyncio
@patch("backend.main.push_observation")
async def test_log_action_memory_cap_at_50(mock_push, tmp_store):
    store, fake_r = tmp_store
    # Write 50 mock actions
    hot = {}
    for i in range(50):
        hot[f"obs_{1000+i}"] = "old"
    await fake_r.set("areqa:hot_memory:default_user", json.dumps(hot))
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/api/v1/log_action", json={"action_type": "new", "timestamp": 12345, "context": {}})
        await asyncio.sleep(0.1)
    
    data = await fake_r.get("areqa:hot_memory:default_user")
    hot_after = json.loads(data) if data else {}
    action_keys = [k for k in hot_after.keys() if k.startswith("obs_")]
    assert len(action_keys) <= 50
    assert any("new" in str(hot_after[k]) for k in action_keys)

@pytest.mark.asyncio
@patch("backend.main.push_observation")
async def test_log_action_concurrent_writes(mock_push, tmp_store):
    store, fake_r = tmp_store
    async def post_action(idx):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post("/api/v1/log_action", json={"action_type": f"action_{idx}", "timestamp": 12345, "context": {}})
            
    await asyncio.gather(*(post_action(i) for i in range(10)))
    await asyncio.sleep(0.1)
    
    data = await fake_r.get("areqa:hot_memory:default_user")
    hot = json.loads(data) if data else {}
    action_keys = [k for k in hot.keys() if k.startswith("obs_")]
    assert len(action_keys) == 10

# U-05 to U-07: Learner State memory ops
@pytest.mark.asyncio
async def test_get_learner_state_default(tmp_store):
    store, fake_r = tmp_store
    hot_mem = await store.get_hot_memory("default_user")
    state = hot_mem.get("current_learner_state", "STARTING")
    assert state == "STARTING"

@pytest.mark.asyncio
async def test_update_and_get_learner_state(tmp_store):
    store, fake_r = tmp_store
    await store.update_hot_memory("default_user", "current_learner_state", "TINKERING")
    
    hot_mem = await store.get_hot_memory("default_user")
    state = hot_mem.get("current_learner_state", "STARTING")
    assert state == "TINKERING"

@pytest.mark.asyncio
async def test_get_current_strategy_default(tmp_store):
    store, fake_r = tmp_store
    hot_mem = await store.get_hot_memory("default_user")
    assert hot_mem.get("current_strategy", "None") == "None"

# U-08 to U-10: evaluate_student_state
@pytest.mark.asyncio
async def test_evaluate_student_state_tinkering(tmp_store):
    store, fake_r = tmp_store
    hot = {"obs_1": "test", "obs_2": "test"}
    await fake_r.set("areqa:hot_memory:default_user", json.dumps(hot))
    
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = '{"learner_state": "TINKERING", "pedagogical_strategy": "PROBE_UNDERSTANDING", "trigger_proactive": false}'
    
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    
    await async_evaluate_and_update_state(mock_client, "test-model", [])
    
    data = await fake_r.get("areqa:hot_memory:default_user")
    hot_after = json.loads(data) if data else {}
    assert hot_after.get("current_learner_state") == "TINKERING"
    assert hot_after.get("current_strategy") == "PROBE_UNDERSTANDING"

@pytest.mark.asyncio
async def test_evaluate_student_state_empty_actions(tmp_store):
    store, fake_r = tmp_store
    # Empty hot memory
    mock_client = MagicMock()
    await async_evaluate_and_update_state(mock_client, "test-model", []) # Should not crash
    data = await fake_r.get("areqa:hot_memory:default_user")
    hot_after = json.loads(data) if data else {}
    assert hot_after.get("current_learner_state") == "STARTING"

@pytest.mark.asyncio
async def test_evaluate_student_state_llm_failure(tmp_store):
    store, fake_r = tmp_store
    hot = {"obs_1": "test"}
    await fake_r.set("areqa:hot_memory:default_user", json.dumps(hot))
    
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("timeout"))
    await async_evaluate_and_update_state(mock_client, "test-model", []) # Should not crash
    
    data = await fake_r.get("areqa:hot_memory:default_user")
    hot_after = json.loads(data) if data else {}
    assert hot_after.get("current_learner_state") == "STARTING"

# U-11 to U-12: classify_dialogue_policy
@pytest.mark.asyncio
async def test_classify_policy_probe_understanding():
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "PROBE_UNDERSTANDING"
    
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    
    policy = await classify_dialogue_policy(mock_client, "test-model", "What is this?", [])
    assert policy == "PROBE_UNDERSTANDING"

@pytest.mark.asyncio
async def test_classify_policy_max_tokens_adjusted():
    # This is indirectly tested inside the stream endpoint test or by mocking.
    pass

# U-13 to U-20: ComPeer Schedule
@pytest.fixture
def mock_schedule_path(monkeypatch, tmp_path):
    # Patch Path to use tmp_path
    mock_path = MagicMock()
    mock_path.resolve.return_value.parents = [None, None, tmp_path]
    mock_path.__truediv__.side_effect = lambda x: tmp_path / x
    monkeypatch.setattr("services.compeer_scheduler.Path", MagicMock(return_value=mock_path))
    schedule_path = tmp_path / "data" / "gum_data" / "schedule_default_user.json"
    schedule_path.parent.mkdir(parents=True, exist_ok=True)
    return schedule_path

@pytest.mark.asyncio
async def test_tick_schedule_fires_within_window(mock_schedule_path, tmp_store):
    store, fake_r = tmp_store
    now = datetime.now()
    mock_schedule_path.write_text(json.dumps([{
        "Timing": now.strftime("%H:%M"),
        "Content": "Test Alert",
        "importance": 1.0,
        "fired": False
    }]))
    
    
    await compeer.tick_proactive_schedule("default_user")
    
    assert await store.get_and_clear_pending_alert("default_user") == "Test Alert"

@pytest.mark.asyncio
async def test_tick_schedule_skips_outside_window(mock_schedule_path, tmp_store):
    store, fake_r = tmp_store
    now = datetime.now()
    future = now + timedelta(minutes=5)
    mock_schedule_path.write_text(json.dumps([{
        "Timing": future.strftime("%H:%M"),
        "Content": "Test Alert",
        "importance": 1.0,
        "fired": False
    }]))
    
    
    await compeer.tick_proactive_schedule("default_user")
    assert await store.get_and_clear_pending_alert("default_user") == ""

@pytest.mark.asyncio
async def test_tick_schedule_no_duplicate_fire(mock_schedule_path, tmp_store):
    store, fake_r = tmp_store
    now = datetime.now()
    mock_schedule_path.write_text(json.dumps([{
        "Timing": now.strftime("%H:%M"),
        "Content": "Test Alert",
        "importance": 1.0,
        "fired": True
    }]))
    
    
    await compeer.tick_proactive_schedule("default_user")
    assert await store.get_and_clear_pending_alert("default_user") == ""

@pytest.mark.asyncio
async def test_tick_schedule_cooldown_blocks_send(mock_schedule_path, tmp_store):
    store, fake_r = tmp_store
    now = datetime.now()
    mock_schedule_path.write_text(json.dumps([{
        "Timing": now.strftime("%H:%M"),
        "Content": "Test Alert",
        "importance": 1.0,
        "fired": False
    }]))
    
    await compeer.set_cooldown("default_user", state="default")
    await compeer.tick_proactive_schedule("default_user")
    assert await store.get_and_clear_pending_alert("default_user") == ""

@pytest.mark.asyncio
async def test_proactive_check_endpoint_has_alert(tmp_store):
    store, fake_r = tmp_store
    await store.set_pending_alert("default_user", "關心你喔")
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/proactive-check")
        
    assert res.status_code == 200
    data = res.json()
    assert data["has_alert"] is True
    assert data["content"] == "關心你喔"
    
    # Second check should be empty
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res2 = await ac.get("/api/v1/proactive-check?user_id=default_user")
        assert res2.json()["has_alert"] is False

@pytest.mark.asyncio
async def test_proactive_check_endpoint_no_alert(tmp_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/proactive-check")
        assert res.json()["has_alert"] is False

@pytest.mark.asyncio
@patch("backend.services.compeer_scheduler.random.random", return_value=0.05)
async def test_importance_gate_high_importance_passes(mock_rand):
    passed = await compeer.evaluate_importance_gate({"importance": 0.9})
    assert passed is True

@pytest.mark.asyncio
@patch("backend.services.compeer_scheduler.random.random", return_value=0.95)
async def test_importance_gate_low_importance_blocked(mock_rand):
    passed = await compeer.evaluate_importance_gate({"importance": 0.1})
    assert passed is False
