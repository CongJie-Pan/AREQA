import pytest
from unittest.mock import AsyncMock, patch
from backend.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_proactive_check_returns_null_when_empty():
    from backend.main import get_current_user
    app.dependency_overrides[get_current_user] = lambda: "test_user"
    
    with patch("memory_store.get_global_store") as mock_get_store:
        mock_store = AsyncMock()
        mock_store.get_and_clear_pending_alert.return_value = None
        mock_get_store.return_value = mock_store
        response = client.get("/api/v1/proactive-check")
        assert response.status_code == 200
        assert response.json().get("has_alert") is False
    
    app.dependency_overrides = {}

def test_log_action_compeer_rejected_triggers_cooldown():
    from backend.main import get_current_user
    app.dependency_overrides[get_current_user] = lambda: "test_user"
    
    with patch("services.compeer_scheduler.set_cooldown", new_callable=AsyncMock) as mock_set_cooldown, \
         patch("memory_store.get_global_store") as mock_get_store, \
         patch("backend.main.push_observation", new_callable=AsyncMock) as mock_push_observation:
        mock_store = AsyncMock()
        mock_store.get_learner_state.return_value = "default"
        mock_get_store.return_value = mock_store
        response = client.post("/api/v1/log_action", json={
            "action_type": "compeer_rejected",
            "user_id": "test_user",
            "context": {},
            "timestamp": 1234567890
        })
        
        assert response.status_code == 200
        mock_set_cooldown.assert_called_once_with("test_user", state="default")
        
    app.dependency_overrides = {}
