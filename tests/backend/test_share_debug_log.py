import logging

from fastapi.testclient import TestClient

from auth import get_current_user
from backend.main import app


def test_share_debug_log_sanitizes_context(caplog):
    app.dependency_overrides[get_current_user] = lambda: "user-1"
    client = TestClient(app)

    try:
        with caplog.at_level(logging.INFO):
            response = client.post(
                "/api/v1/share/debug-log",
                json={
                    "event": "share.create.insert_failed",
                    "context": {
                        "component": "share-conversation-route",
                        "shareDebugId": "abc123",
                        "conversationId": "conversation-1",
                        "messageCount": 2,
                        "shareToken": "secret-token",
                        "messageContent": "private text",
                        "supabaseError": {
                            "code": "42501",
                            "message": "permission denied",
                            "secret": "do-not-log",
                        },
                    },
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "share.backend_debug" in caplog.text
    assert "share.create.insert_failed" in caplog.text
    assert "abc123" in caplog.text
    assert "permission denied" in caplog.text
    assert "secret-token" not in caplog.text
    assert "private text" not in caplog.text
    assert "do-not-log" not in caplog.text


def test_share_debug_log_rejects_unexpected_event_name():
    app.dependency_overrides[get_current_user] = lambda: "user-1"
    client = TestClient(app)

    try:
        response = client.post(
            "/api/v1/share/debug-log",
            json={"event": "memory.write", "context": {}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
