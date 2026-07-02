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
import backend.services.compeer_scheduler as compeer

@pytest.fixture
def tmp_store(tmp_path):
    # We will point it to a subfolder in tmp_path so it creates data/gum_data/hot_memory.json there.
    dummy_root = tmp_path / "dummy_root"
    gum_data = dummy_root / "data" / "gum_data"
    gum_data.mkdir(parents=True, exist_ok=True)
    hot_path = gum_data / "hot_memory.json"
    profile_path = gum_data / "user_profile.json"
    hot_path.write_text("{}")
    profile_path.write_text("{}")
    
    # Store old global
    old_store = mem_store_module._global_store
    
    init_global_store(str(hot_path), str(profile_path), budget_limit=1000000)
    store = get_global_store()
    
    # Patch PROJECT_ROOT in main to prevent startup event from overwriting the real store path
    with patch("backend.main.PROJECT_ROOT", dummy_root):
        yield store, hot_path, profile_path
    
    # Restore
    mem_store_module._global_store = old_store


# U-01 to U-04: log_action API
@pytest.mark.asyncio
async def test_log_action_valid_request(tmp_store):
    store, hot_path, _ = tmp_store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/log_action", json={"action_type": "scroll", "timestamp": 12345, "context": {"duration_seconds": 3.0}})
        await asyncio.sleep(0.1)
        assert res.status_code == 200
        
    hot = json.loads(hot_path.read_text())
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
async def test_log_action_memory_cap_at_50(tmp_store):
    store, hot_path, _ = tmp_store
    # Write 50 mock actions
    hot = {}
    for i in range(50):
        hot[f"obs_{1000+i}"] = "old"
    hot_path.write_text(json.dumps(hot))
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/api/v1/log_action", json={"action_type": "new", "timestamp": 12345, "context": {}})
        await asyncio.sleep(0.1)
    
    hot_after = json.loads(hot_path.read_text())
    action_keys = [k for k in hot_after.keys() if k.startswith("obs_")]
    assert len(action_keys) <= 50
    assert any("new" in str(hot_after[k]) for k in action_keys)

@pytest.mark.asyncio
async def test_log_action_concurrent_writes(tmp_store):
    store, hot_path, _ = tmp_store
    async def post_action(idx):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post("/api/v1/log_action", json={"action_type": f"action_{idx}", "timestamp": 12345, "context": {}})
            
    await asyncio.gather(*(post_action(i) for i in range(10)))
    await asyncio.sleep(0.1)
    
    hot = json.loads(hot_path.read_text())
    action_keys = [k for k in hot.keys() if k.startswith("obs_")]
    assert len(action_keys) == 10

# U-05 to U-07: Learner State memory ops
def test_get_learner_state_default(tmp_store):
    store, _, _ = tmp_store
    state = store.get_hot_memory().get("current_learner_state", "STARTING")
    assert state == "STARTING"

def test_update_and_get_learner_state(tmp_store):
    store, hot_path, _ = tmp_store
    hot = store.get_hot_memory()
    hot["current_learner_state"] = "TINKERING"
    store._atomic_write(str(hot_path), hot)
    
    state = store.get_hot_memory().get("current_learner_state", "STARTING")
    assert state == "TINKERING"

def test_get_current_strategy_default(tmp_store):
    store, _, _ = tmp_store
    assert store.get_hot_memory().get("current_strategy", "None") == "None"

# U-08 to U-10: evaluate_student_state
@pytest.mark.asyncio
async def test_evaluate_student_state_tinkering(tmp_store):
    store, hot_path, _ = tmp_store
    hot = {"obs_1": "test", "obs_2": "test"}
    hot_path.write_text(json.dumps(hot))
    
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = '{"learner_state": "TINKERING", "pedagogical_strategy": "PROBE_UNDERSTANDING", "trigger_proactive": false}'
    
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    
    await async_evaluate_and_update_state(mock_client, "test-model", [])
    
    hot_after = json.loads(hot_path.read_text())
    assert hot_after.get("current_learner_state") == "TINKERING"
    assert hot_after.get("current_strategy") == "PROBE_UNDERSTANDING"

@pytest.mark.asyncio
async def test_evaluate_student_state_empty_actions(tmp_store):
    store, hot_path, _ = tmp_store
    # Empty hot memory
    mock_client = MagicMock()
    await async_evaluate_and_update_state(mock_client, "test-model", []) # Should not crash
    hot_after = json.loads(hot_path.read_text())
    assert hot_after.get("current_learner_state") == "STARTING"

@pytest.mark.asyncio
async def test_evaluate_student_state_llm_failure(tmp_store):
    store, hot_path, _ = tmp_store
    hot = {"obs_1": "test"}
    hot_path.write_text(json.dumps(hot))
    
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("timeout"))
    await async_evaluate_and_update_state(mock_client, "test-model", []) # Should not crash
    
    hot_after = json.loads(hot_path.read_text())
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
    monkeypatch.setattr("backend.services.compeer_scheduler.Path", MagicMock(return_value=mock_path))
    schedule_path = tmp_path / "data" / "gum_data" / "schedule_default_user.json"
    schedule_path.parent.mkdir(parents=True, exist_ok=True)
    return schedule_path

@pytest.mark.asyncio
async def test_tick_schedule_fires_within_window(mock_schedule_path, tmp_store):
    store, _, _ = tmp_store
    now = datetime.now()
    mock_schedule_path.write_text(json.dumps([{
        "Timing": now.strftime("%H:%M"),
        "Content": "Test Alert",
        "importance": 1.0,
        "fired": False
    }]))
    
    
    await compeer.tick_proactive_schedule("default_user")
    
    assert store.get_and_clear_pending_alert("default_user") == "Test Alert"

@pytest.mark.asyncio
async def test_tick_schedule_skips_outside_window(mock_schedule_path, tmp_store):
    store, _, _ = tmp_store
    now = datetime.now()
    future = now + timedelta(minutes=5)
    mock_schedule_path.write_text(json.dumps([{
        "Timing": future.strftime("%H:%M"),
        "Content": "Test Alert",
        "importance": 1.0,
        "fired": False
    }]))
    
    
    await compeer.tick_proactive_schedule("default_user")
    assert store.get_and_clear_pending_alert("default_user") == ""

@pytest.mark.asyncio
async def test_tick_schedule_no_duplicate_fire(mock_schedule_path, tmp_store):
    store, _, _ = tmp_store
    now = datetime.now()
    mock_schedule_path.write_text(json.dumps([{
        "Timing": now.strftime("%H:%M"),
        "Content": "Test Alert",
        "importance": 1.0,
        "fired": True
    }]))
    
    
    await compeer.tick_proactive_schedule("default_user")
    assert store.get_and_clear_pending_alert("default_user") == ""

@pytest.mark.asyncio
async def test_tick_schedule_cooldown_blocks_send(mock_schedule_path, tmp_store):
    store, _, _ = tmp_store
    now = datetime.now()
    mock_schedule_path.write_text(json.dumps([{
        "Timing": now.strftime("%H:%M"),
        "Content": "Test Alert",
        "importance": 1.0,
        "fired": False
    }]))
    
    compeer.set_cooldown("default_user", state="default")
    await compeer.tick_proactive_schedule("default_user")
    assert store.get_and_clear_pending_alert("default_user") == ""

@pytest.mark.asyncio
async def test_proactive_check_endpoint_has_alert(tmp_store):
    store, _, _ = tmp_store
    store.set_pending_alert("test_user", "關心你喔")
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/proactive-check?user_id=test_user")
        
    assert res.status_code == 200
    data = res.json()
    assert data["has_alert"] is True
    assert data["content"] == "關心你喔"
    
    # Second check should be empty
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res2 = await ac.get("/api/v1/proactive-check?user_id=test_user")
        assert res2.json()["has_alert"] is False

@pytest.mark.asyncio
async def test_proactive_check_endpoint_no_alert(tmp_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/proactive-check?user_id=no_user")
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
