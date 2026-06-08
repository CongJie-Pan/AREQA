import pytest
from httpx import AsyncClient, ASGITransport
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backEnd")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from main import app, settings_store
from core import gum_manager

import pytest_asyncio

@pytest_asyncio.fixture(autouse=True)
async def cleanup():
    # Setup
    with patch('main.set_key') as mock_set_key:
        yield
    # Teardown
    await gum_manager.stop_recording()

@pytest.mark.asyncio
async def test_recording_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/recording/status")
    assert response.status_code == 200
    data = response.json()
    assert "is_recording" in data
    assert data["is_recording"] is False

@pytest.mark.asyncio
async def test_update_settings():
    payload = {
        "user_name": "test_user_api",
        "llm_api_key": "fake-key",
        "enable_screen_capture": False,
        "model_name": "gpt-4o-mini"
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/settings", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    
    # Verify manager settings updated
    assert gum_manager.gum_instance is not None
    assert gum_manager.gum_instance.user_name == "test_user_api"

@pytest.mark.asyncio
async def test_start_stop_recording_api():
    # Make sure settings have api key
    settings_store["llm_api_key"] = "sk-fake"
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/recording/start")
        assert response.status_code == 200
        
        status_res = await ac.get("/api/recording/status")
        assert status_res.json()["is_recording"] is True
        
        stop_res = await ac.post("/api/recording/stop")
        assert stop_res.status_code == 200
        
        status_res2 = await ac.get("/api/recording/status")
        assert status_res2.json()["is_recording"] is False

@pytest.mark.asyncio
async def test_get_memory_api():
    # Need to be initialized
    settings_store["llm_api_key"] = "fake"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/memory")
    assert response.status_code == 200
    assert "propositions" in response.json()

@pytest.mark.asyncio
async def test_put_memory():
    settings_store["llm_api_key"] = "fake"
    payload = {"text": "Updated prop", "confidence": 9}
    
    # We mock gum_manager.update_prop for this api test to isolate failure
    original_update = gum_manager.update_prop
    async def mock_update(*args): return True
    gum_manager.update_prop = mock_update
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.put("/api/memory/1", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    finally:
        gum_manager.update_prop = original_update

@pytest.mark.asyncio
async def test_delete_memory():
    settings_store["llm_api_key"] = "fake"
    
    original_delete = gum_manager.delete_prop
    async def mock_delete(*args): return True
    gum_manager.delete_prop = mock_delete
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.delete("/api/memory/1")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    finally:
        gum_manager.delete_prop = original_delete

@pytest.mark.asyncio
async def test_get_suggestions():
    settings_store["llm_api_key"] = "fake"
    
    original_gen = gum_manager.generate_suggestions
    async def mock_gen():
        return [{"id": "s1", "title": "Test Sug", "description": "Desc", "benefit": 8, "confidence": 7}]
    gum_manager.generate_suggestions = mock_gen
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/suggestions")
        assert response.status_code == 200
        assert "suggestions" in response.json()
        assert len(response.json()["suggestions"]) == 1
    finally:
        gum_manager.generate_suggestions = original_gen

@pytest.mark.asyncio
async def test_post_feedback():
    settings_store["llm_api_key"] = "fake"
    payload = {
        "suggestion_id": "s1",
        "is_positive": False,
        "text_feedback": "Not relevant"
    }
    
    # init gum to prevent 400 error
    await gum_manager.init_gum("test", "gpt-4o-mini", "fake")
    
    # Mock push to prevent real validation failing
    original_push = gum_manager.gum_instance.batcher.push
    def mock_push(*args, **kwargs): return "mock_obs_id"
    gum_manager.gum_instance.batcher.push = mock_push
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/feedback", json=payload)
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    finally:
        gum_manager.gum_instance.batcher.push = original_push

from unittest.mock import patch

@pytest.mark.asyncio
async def test_update_settings_with_openrouter_qwen_models():
    """
    Ensure the settings endpoint correctly configures OpenRouter URL
    and Qwen models, and writes to .env without breaking.
    """
    payload = {
        "user_name": "test_qwen_user",
        "llm_api_key": "sk-or-v1-fake-test-key",
        "enable_screen_capture": False,
        "model_name": "qwen/qwen3-235b-a22b-2507"
    }
    
    with patch("main.set_key") as mock_set_key:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/settings", json=payload)
            
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        # Verify set_key was called twice to update .env
        assert mock_set_key.call_count == 2
        calls = mock_set_key.call_args_list
        assert any(call.args[1] == "OPENROUTER_API_KEY" and call.args[2] == "sk-or-v1-fake-test-key" for call in calls)
        assert any(call.args[1] == "GUM_LM_API_BASE" and call.args[2] == "https://openrouter.ai/api/v1" for call in calls)
        
        # Verify GUM instance initialized with correct model
        assert gum_manager.gum_instance is not None
        assert gum_manager.gum_instance.model == "qwen/qwen3-235b-a22b-2507"
        
        # Verify environment variables were set for GUM internal usage
        assert os.environ.get("OPENROUTER_API_KEY") == "sk-or-v1-fake-test-key"
        assert os.environ.get("GUM_LM_API_BASE") == "https://openrouter.ai/api/v1"
