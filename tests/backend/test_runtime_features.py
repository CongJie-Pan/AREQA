from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.main import app

app.router.on_startup.clear()
app.router.on_shutdown.clear()

client = TestClient(app)


def test_runtime_features_are_disabled_by_default():
    response = client.get("/api/v1/features")

    assert response.status_code == 200
    assert response.json() == {
        "mailbox": False,
        "compeer": False,
        "compeerTelemetry": False,
        "conversationHistoryDebugLogs": True,
    }


def test_runtime_features_follow_backend_settings():
    with (
        patch("config.settings.enable_mailbox_feature", True),
        patch("config.settings.enable_compeer_feature", True),
        patch("config.settings.enable_compeer_telemetry", True),
        patch("config.settings.enable_conversation_history_debug_logs", False),
    ):
        response = client.get("/api/v1/features")

    assert response.status_code == 200
    assert response.json() == {
        "mailbox": True,
        "compeer": True,
        "compeerTelemetry": True,
        "conversationHistoryDebugLogs": False,
    }


def test_runtime_features_do_not_enable_telemetry_without_compeer():
    with (
        patch("config.settings.enable_compeer_feature", False),
        patch("config.settings.enable_compeer_telemetry", True),
    ):
        response = client.get("/api/v1/features")

    assert response.status_code == 200
    assert response.json()["compeer"] is False
    assert response.json()["compeerTelemetry"] is False
