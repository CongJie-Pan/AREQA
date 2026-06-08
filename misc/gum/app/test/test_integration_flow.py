import pytest
import asyncio
import sys
import os
from httpx import AsyncClient, ASGITransport

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backEnd")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from main import app, settings_store
from core import gum_manager

@pytest.mark.asyncio
async def test_full_user_journey():
    """
    Integration test simulating a complete user flow through the FastAPI backend.
    """
    # 1. User configures settings
    payload = {
        "user_name": "E2E_User",
        "llm_api_key": "fake-e2e-key",
        "enable_screen_capture": False,
        "model_name": "gpt-4o-mini"
    }
    
    # We will mock LLM methods on the gum instance later
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Settings
        res_settings = await client.post("/api/settings", json=payload)
        assert res_settings.status_code == 200
        
        # Step 2: Start Recording
        res_start = await client.post("/api/recording/start")
        assert res_start.status_code == 200
        
        # Verify recording started
        res_status = await client.get("/api/recording/status")
        assert res_status.json()["is_recording"] is True
        
        # Mock LLM generation to avoid real API calls in integration test
        original_gen_suggestions = gum_manager.generate_suggestions
        async def mock_suggestions():
            return [
                {
                    "id": "e2e_sug_1",
                    "title": "Use shortcut",
                    "description": "Press Ctrl+C",
                    "benefit": 9,
                    "confidence": 8
                }
            ]
        gum_manager.generate_suggestions = mock_suggestions
        
        # Let MockObserver run for a bit
        await asyncio.sleep(0.2)
        
        # Step 3: Fetch Memory
        res_memory = await client.get("/api/memory")
        assert res_memory.status_code == 200
        assert "propositions" in res_memory.json()
        
        # Step 4: Fetch Suggestions
        res_sug = await client.get("/api/suggestions")
        assert res_sug.status_code == 200
        assert len(res_sug.json()["suggestions"]) == 1
        assert res_sug.json()["suggestions"][0]["title"] == "Use shortcut"
        
        # Step 5: Provide Feedback
        # Also mock batcher push to avoid side-effects
        original_push = gum_manager.gum_instance.batcher.push
        gum_manager.gum_instance.batcher.push = lambda *args, **kwargs: "mock_id"
        
        res_feedback = await client.post("/api/feedback", json={
            "suggestion_id": "e2e_sug_1",
            "is_positive": True,
            "text_feedback": ""
        })
        assert res_feedback.status_code == 200
        
        # Cleanup mocks
        gum_manager.generate_suggestions = original_gen_suggestions
        gum_manager.gum_instance.batcher.push = original_push
        
        # Step 6: Stop Recording
        res_stop = await client.post("/api/recording/stop")
        assert res_stop.status_code == 200
        
        res_status2 = await client.get("/api/recording/status")
        assert res_status2.json()["is_recording"] is False
