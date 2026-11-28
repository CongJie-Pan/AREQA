from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.main import app

app.router.on_startup.clear()
app.router.on_shutdown.clear()

client = TestClient(app)


def test_runtime_features_default_shape():
    response = client.get("/api/v1/features")

    assert response.status_code == 200
    assert response.json() == {"conversationHistoryDebugLogs": True}


def test_runtime_features_follow_backend_settings():
    with patch("config.settings.enable_conversation_history_debug_logs", False):
        response = client.get("/api/v1/features")

    assert response.status_code == 200
    assert response.json() == {"conversationHistoryDebugLogs": False}
