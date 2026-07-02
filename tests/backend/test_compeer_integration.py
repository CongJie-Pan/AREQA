import pytest
from unittest.mock import AsyncMock, patch

from backend.main import app
from fastapi.testclient import TestClient
from backend.memory_store import init_global_store

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_store(tmp_path):
    store_dir = tmp_path / "gum_data"
    store_dir.mkdir()
    init_global_store(str(store_dir / "hot_memory.json"), str(store_dir / "profile.json"))

def test_proactive_check_returns_null_when_empty():
    response = client.get("/api/v1/proactive-check")
    assert response.status_code == 200
    assert response.json().get("has_alert") is False

def test_log_action_compeer_rejected_triggers_cooldown():
    import services.compeer_scheduler as compeer
    compeer.user_cooldown_until.clear()
    response = client.post("/api/v1/log_action", json={
        "action_type": "compeer_rejected",
        "user_id": "test_user",
        "context": {},
        "timestamp": 1234567890
    })
    
    assert response.status_code == 200
    assert compeer.is_in_cooldown("test_user") is True
