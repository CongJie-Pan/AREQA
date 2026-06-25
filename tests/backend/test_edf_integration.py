import pytest
import asyncio
import json
import os
import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from backend.main import app
from memory_store import init_global_store, get_global_store
import memory_store as mem_store_module
import backend.services.compeer_scheduler as compeer
from backend.gum_integration import async_evaluate_and_update_state
from backend.compaction import evaluate_student_state

@pytest.fixture
def tmp_store(tmp_path):
    hot_path = tmp_path / "hot_memory.json"
    profile_path = tmp_path / "user_profile.json"
    hot_path.write_text('{"current_learner_state": "RUN_REPEAT"}')
    profile_path.write_text("{}")
    
    old_store = mem_store_module._global_store
    init_global_store(str(hot_path), str(profile_path))
    store = get_global_store()
    yield store, hot_path, profile_path
    mem_store_module._global_store = old_store

@pytest.mark.asyncio
@patch("backend.main.AsyncOpenAI")
@patch("backend.gum_integration.gum_instance")
async def test_full_edf_dialogue_loop(mock_gum, mock_create, tmp_store):
    store, hot_path, _ = tmp_store
    
    # Mock Policy classification
    mock_resp_policy = MagicMock()
    mock_resp_policy.choices = [MagicMock()]
    mock_resp_policy.choices[0].message.content = '{"policy": "PROBE_UNDERSTANDING"}'
    
    # Mock stream response
    mock_resp_stream = MagicMock()
    mock_resp_stream.choices = [MagicMock()]
    mock_resp_stream.choices[0].delta.content = "Test stream chunk"
    
    # Let mock_create return policy response then stream response
    mock_create.side_effect = [mock_resp_policy, mock_resp_stream]
    
    # Mock RAG ZPD Generation
    mock_openai_instance = MagicMock()
    mock_create.return_value = mock_openai_instance
    mock_openai_instance.chat.completions.create = AsyncMock()
    
    mock_gum_resp = MagicMock()
    mock_gum_resp.choices = [MagicMock()]
    mock_gum_resp.choices[0].message.content = "Rewritten Query for RUN_REPEAT"
    mock_gum.client.chat.completions.create = AsyncMock(return_value=mock_gum_resp)
    mock_gum.model = "test-model"
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/stream", json={"messages": [{"role": "user", "content": "Help"}], "use_rag": True, "max_tokens": 2048})
        
    assert res.status_code == 200

@pytest.mark.asyncio
@patch("backend.gum_integration.gum_instance")
async def test_scaffolding_fading_flow(mock_gum, tmp_store):
    store, hot_path, _ = tmp_store
    hot_path.write_text('{"current_learner_state": "STARTING"}')
    store._atomic_write(str(hot_path), {"current_learner_state": "STARTING"})
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/api/v1/log_action", json={"action_type": "scroll", "timestamp": 12345, "context": {}})
        await ac.post("/api/v1/log_action", json={"action_type": "reread", "timestamp": 12345, "context": {}})
        await asyncio.sleep(0.1)
    
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = '{"learner_state": "TINKERING", "strategy": "PROBE_UNDERSTANDING"}'
    mock_gum.client.chat.completions.create = AsyncMock(return_value=mock_resp)
    mock_gum.model = "test-model"
    
    await async_evaluate_and_update_state(mock_gum.client, "test-model", [])
    
    hot = json.loads(hot_path.read_text())
    assert hot["current_learner_state"] == "TINKERING"

@pytest.mark.asyncio
@patch("backend.services.compeer_scheduler.Path")
async def test_compeer_daily_schedule_e2e(mock_path, tmp_path, tmp_store):
    # Setup Paths
    mock_path_instance = MagicMock()
    mock_path.return_value = mock_path_instance
    mock_path_instance.resolve.return_value.parents = [None, None, tmp_path]
    mock_path_instance.__truediv__.side_effect = lambda x: tmp_path / x
    
    log_path = tmp_path / "data" / "gum_data" / "reflection_log_default_user.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text('{"role": "user", "content": "hi"}\n')
    
    # Mock LLM calls inside compeer via gum_instance
    with patch("gum_integration.gum_instance") as mock_gum:
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        now = datetime.datetime.now()
        timing = now.strftime("%H:%M")
        mock_resp.choices[0].message.content = '{"events": [{"Timing": "' + timing + '", "Content": "Test", "importance": 1.0}]}'
        mock_gum.client.chat.completions.create = AsyncMock(return_value=mock_resp)
        mock_gum.model = "test-model"
        
        # 2. 每日初始化
        await compeer.run_reflection_and_initialization("default_user")
        
    schedule_path = tmp_path / "data" / "gum_data" / "schedule_default_user.json"
    print(f"DEBUG: Does schedule_path exist? {schedule_path.exists()}")
    if not schedule_path.exists():
        print(f"DEBUG: Tmp dir contents: {list(tmp_path.glob('**/*'))}")
    assert schedule_path.exists()
    
    # 3. 輪詢觸發
    compeer.user_flag["default_user"] = True
    await compeer.tick_proactive_schedule("default_user")
    
    # 4. Frontend Polling
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/proactive-check?user_id=default_user")
        assert res.json() == {"has_alert": True, "content": "Test"}
        
        # Second call should be empty
        res2 = await ac.get("/api/v1/proactive-check?user_id=default_user")
        assert res2.json() == {"has_alert": False}

@pytest.mark.asyncio
@patch.dict(os.environ, clear=True)
async def test_stream_missing_api_key_graceful_degradation(tmp_store):
    """Regression Test: Ensure missing API key yields an error chunk and does not crash with UnboundLocalError."""
    # Ensure OPENROUTER_API_KEY is not set
    if "OPENROUTER_API_KEY" in os.environ:
        del os.environ["OPENROUTER_API_KEY"]
        
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        async with ac.stream("POST", "/api/v1/stream", json={"messages": [{"role": "user", "content": "Help"}], "stream": True}) as response:
            assert response.status_code == 200
            content = await response.aread()
            content_str = content.decode("utf-8")
            assert "OPENROUTER_API_KEY is missing" in content_str
            # Should end gracefully
            assert "[DONE]" in content_str

@pytest.mark.asyncio
@patch("backend.main.AsyncOpenAI")
async def test_stream_graceful_fallback_without_unbound_full_content(mock_openai, tmp_store):
    """Regression Test: Ensure an exception during generation yields error chunk without UnboundLocalError on 'full_content'."""
    os.environ["OPENROUTER_API_KEY"] = "dummy"
    mock_client = MagicMock()
    # Mock chat completion to raise an exception
    mock_client.chat.completions.create.side_effect = Exception("Mocked API Timeout Error")
    mock_openai.return_value = mock_client
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        async with ac.stream("POST", "/api/v1/stream", json={"messages": [{"role": "user", "content": "Hello"}], "stream": True}) as response:
            assert response.status_code == 200
            content = await response.aread()
            content_str = content.decode("utf-8")
            assert "Mocked API Timeout Error" in content_str
            assert "[DONE]" in content_str

@pytest.mark.asyncio
@patch("backend.main.AsyncOpenAI")
async def test_user_flag_reset_on_message(mock_openai, tmp_store):
    """Verify that sending a message via /stream resets the compeer user_flag to True (Cooldown reset)."""
    os.environ["OPENROUTER_API_KEY"] = "dummy"
    # First, simulate the scheduler putting the user into cooldown mode
    import services.compeer_scheduler as compeer
    compeer.user_flag["default_user"] = False
    
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].delta.content = "Test stream chunk"
    mock_client.chat.completions.create.return_value = [mock_resp]
    mock_openai.return_value = mock_client
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        async with ac.stream("POST", "/api/v1/stream", json={"messages": [{"role": "user", "content": "Hello"}], "stream": True}) as response:
            assert response.status_code == 200
            
    # Allow background tasks to run briefly so the flag is updated
    await asyncio.sleep(0.1)
            
    # Assert that the cooldown flag was reset to True
    assert compeer.user_flag.get("default_user") is True
