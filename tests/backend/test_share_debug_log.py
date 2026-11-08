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


def test_conversation_history_debug_log_sanitizes_context(caplog):
    app.dependency_overrides[get_current_user] = lambda: "user-1"
    client = TestClient(app)

    try:
        with caplog.at_level(logging.INFO):
            response = client.post(
                "/api/v1/conversation-history/debug-log",
                json={
                    "event": "chat_history_switch_completed",
                    "context": {
                        "component": "chatService",
                        "conversationId": "conversation-1",
                        "activeConversationId": "conversation-1",
                        "displayMessageCount": 0,
                        "pendingSyncCount": 0,
                        "messageContent": "private text",
                        "token": "secret-token",
                    },
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "conversation_history.backend_debug" in caplog.text
    assert "chat_history_switch_completed" in caplog.text
    assert "conversation-1" in caplog.text
    assert "private text" not in caplog.text
    assert "secret-token" not in caplog.text


def test_conversation_history_debug_log_rejects_unexpected_event_name():
    app.dependency_overrides[get_current_user] = lambda: "user-1"
    client = TestClient(app)

    try:
        response = client.post(
            "/api/v1/conversation-history/debug-log",
            json={"event": "memory.write", "context": {}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


def test_search_diagnostics_keep_settings_and_drop_private_or_invalid_fields(caplog):
    client = TestClient(app)
    with caplog.at_level(logging.INFO):
        response = client.post('/api/v1/conversation-history/debug-log', json={
            'event': 'chat_history_search_stream_request', 'context': {
                'component': 'chatStream', 'conversationId': 'chat-1', 'requestId': 'search-request-1',
                'searchMode': 'always', 'uiSearchMode': 'never', 'useWebSearch': True,
                'useRag': False, 'sourceCount': 12, 'clientTimestampMs': 123456,
                'previousSearchMode': 'PRIVATE INVALID ENUM', 'uiUseWebSearch': 'PRIVATE BOOLEAN',
                'attachmentCount': -1, 'messageContent': 'PRIVATE MESSAGE', 'token': 'PRIVATE TOKEN',
            },
        })
    assert response.status_code == 200
    assert 'chat_history_search_stream_request' in caplog.text
    assert '"requestId": "search-request-1"' in caplog.text
    assert '"searchMode": "always"' in caplog.text
    assert '"uiSearchMode": "never"' in caplog.text
    assert '"sourceCount": 12' in caplog.text
    assert 'PRIVATE' not in caplog.text
    assert 'attachmentCount' not in caplog.text


def test_stream_acceptance_logs_actual_search_parameters_and_request_id(caplog, monkeypatch):
    from unittest.mock import patch
    from types import SimpleNamespace
    monkeypatch.setenv('OPENROUTER_API_KEY', 'mock-token')
    async def execute(**kwargs):
        yield 'data: [DONE]\n\n'
    with patch('services.orchestration_service.OrchestrationService', return_value=SimpleNamespace(execute=execute)):
        with caplog.at_level(logging.INFO):
            response = TestClient(app).post('/api/v1/stream', headers={'x-request-id': 'search-request-1'}, json={
                'messages': [{'role': 'user', 'content': 'PRIVATE QUESTION'}],
                'conversation_id': 'chat-1', 'search_mode': 'never', 'use_web_search': True,
            })
    assert response.status_code == 200
    assert 'request_id=search-request-1 search_mode=never use_web_search=True use_rag=False' in caplog.text
    assert 'PRIVATE QUESTION' not in caplog.text
