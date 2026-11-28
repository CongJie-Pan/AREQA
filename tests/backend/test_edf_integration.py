import pytest
import asyncio
import json
import os
import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from backend.main import app
from auth import get_current_user
from services.memory.store.service import init_global_store, get_global_store
import services.memory.store.service as mem_store_module
from services.memory.gum.runtime import async_evaluate_and_update_state
from services.memory.scoring import evaluate_student_state

@pytest.fixture
def tmp_store():
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
        
    with patch("services.memory.store.service.get_redis") as mock_mem_redis:
        fake_r = FakeRedis()
        fake_r.data["areqa:hot_memory:default_user"] = '{"current_learner_state": "RUN_REPEAT"}'
        mock_mem_redis.return_value = fake_r
        init_global_store(budget_limit=1000000)
        store = get_global_store()
        app.dependency_overrides[get_current_user] = lambda: "default_user"
        yield store, fake_r
    
    app.dependency_overrides.clear()
    # Async Redis clients are event-loop bound; never leak one fixture's
    # client into a later pytest loop.
    mem_store_module._global_store = None

@pytest.mark.asyncio
@patch("backend.main.AsyncOpenAI")
@patch("services.memory.gum.runtime.get_gum_instance")
async def test_full_edf_dialogue_loop(mock_get_gum, mock_create, tmp_store):
    mock_gum = MagicMock()
    mock_get_gum.return_value = (mock_gum, MagicMock())
    store, fake_r = tmp_store
    
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
@patch("services.memory.gum.runtime.get_gum_instance")
@patch("backend.main.push_observation")
async def test_scaffolding_fading_flow(mock_push, mock_get_gum, tmp_store):
    mock_gum = MagicMock()
    mock_get_gum.return_value = (mock_gum, MagicMock())
    store, fake_r = tmp_store
    await store.update_hot_memory("default_user", "current_learner_state", "STARTING")
    
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
    
    data = await fake_r.get("areqa:hot_memory:default_user")
    hot = json.loads(data) if data else {}
    assert hot["current_learner_state"] == "TINKERING"

@pytest.mark.asyncio
@patch.dict(os.environ, clear=True)
async def test_stream_missing_api_key_graceful_degradation(tmp_store):
    """Regression Test: Ensure missing API key yields an error chunk and does not crash with UnboundLocalError."""
    # Ensure OPENROUTER_API_KEY is not set
    if "OPENROUTER_API_KEY" in os.environ:
        del os.environ["OPENROUTER_API_KEY"]
        
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        async with ac.stream("POST", "/api/v1/stream", json={"messages": [{"role": "user", "content": "王熙鳳是誰"}], "stream": True}) as response:
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
    async def side_effect(*args, **kwargs):
        raise Exception("Mocked API Timeout Error")
    mock_client.chat.completions.create = AsyncMock(side_effect=side_effect)
    mock_openai.return_value = mock_client
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        async with ac.stream("POST", "/api/v1/stream", json={"messages": [{"role": "user", "content": "王熙鳳是誰"}], "stream": True}) as response:
            assert response.status_code == 200
            content = await response.aread()
            content_str = content.decode("utf-8")
            assert "生成回答時發生錯誤" in content_str
            assert "Mocked API Timeout Error" not in content_str
            assert "[DONE]" in content_str
