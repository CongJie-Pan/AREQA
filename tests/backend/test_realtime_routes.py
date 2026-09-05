"""Regression tests for AREQA Live Tutor Realtime backend routes."""

from __future__ import annotations

import io

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

import backend.app.routes.realtime as realtime_routes
from backend.app.routes.realtime import (
    RealtimeContextMessage,
    RealtimeContextRequest,
    RealtimeSessionRequest,
    _build_realtime_session_config,
    _client_secret_from_response,
    _normalize_model,
    _safe_realtime_user_identifier,
    create_realtime_session,
    get_realtime_context,
    transcribe_speech,
)


def test_realtime_session_config_uses_allowed_mvp_model_without_auto_answers():
    payload = RealtimeSessionRequest(
        model="gpt-realtime-2.1-mini",
        voice="marin",
        conversation_id="conv_123",
        interface_language="zh-TW",
    )

    config = _build_realtime_session_config(payload)

    assert config["type"] == "realtime"
    assert config["model"] == "gpt-realtime-2.1-mini"
    assert config["audio"]["output"]["voice"] == "marin"
    assert "Traditional Chinese" in config["audio"]["input"]["transcription"]["prompt"]
    assert config["audio"]["input"]["turn_detection"] == {
        "type": "server_vad",
        "create_response": False,
        "interrupt_response": True,
    }
    assert config["tools"] == []
    assert config["tool_choice"] == "none"


def test_realtime_session_config_preserves_simplified_chinese_preference():
    payload = RealtimeSessionRequest(interface_language="zh-CN")

    config = _build_realtime_session_config(payload)

    assert "Simplified Chinese" in config["instructions"]
    assert "Simplified Chinese" in config["audio"]["input"]["transcription"]["prompt"]


def test_realtime_session_rejects_unsupported_models():
    with pytest.raises(HTTPException) as error:
        _normalize_model("gpt-4o")

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "REALTIME_MODEL_UNSUPPORTED"


def test_client_secret_extraction_accepts_official_ephemeral_token_shape():
    value, expires_at = _client_secret_from_response({
        "value": "ek_test",
        "expires_at": 1788510000,
    })

    assert value == "ek_test"
    assert expires_at == "1788510000"


def test_client_secret_extraction_accepts_nested_client_secret_shape():
    value, expires_at = _client_secret_from_response({
        "client_secret": {
            "value": "ek_test",
            "expires_at": 1788510000,
        }
    })

    assert value == "ek_test"
    assert expires_at == "1788510000"


def test_client_secret_extraction_rejects_missing_secret():
    with pytest.raises(ValueError):
        _client_secret_from_response({"client_secret": {}})


def test_safe_realtime_user_identifier_hashes_authenticated_user_id():
    identifier = _safe_realtime_user_identifier("user_123")

    assert identifier
    assert identifier != "user_123"
    assert _safe_realtime_user_identifier("user_123") == identifier
    assert _safe_realtime_user_identifier(None) is None


@pytest.mark.asyncio
async def test_create_realtime_session_fails_when_openai_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(HTTPException) as error:
        await create_realtime_session(RealtimeSessionRequest(), current_user_id="user_123")

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "OPENAI_API_KEY_MISSING"


@pytest.mark.asyncio
async def test_create_realtime_session_preserves_openai_rate_limit(monkeypatch):
    class FakeResponse:
        status_code = 429

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.headers = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, _url, *, headers, json):
            self.headers = headers
            assert json["session"]["model"] == "gpt-realtime-2.1-mini"
            assert "OpenAI-Safety-Identifier" in headers
            assert headers["OpenAI-Safety-Identifier"] != "user_123"
            return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(realtime_routes.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(HTTPException) as error:
        await create_realtime_session(RealtimeSessionRequest(), current_user_id="user_123")

    assert error.value.status_code == 429
    assert error.value.detail["code"] == "OPENAI_REALTIME_RATE_LIMITED"


@pytest.mark.asyncio
async def test_create_realtime_session_maps_openai_auth_failure_to_service_error(monkeypatch):
    class FakeResponse:
        status_code = 403

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, _url, *, headers, json):
            assert "OpenAI-Safety-Identifier" not in headers
            return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(realtime_routes.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(HTTPException) as error:
        await create_realtime_session(RealtimeSessionRequest(), current_user_id=None)

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "OPENAI_REALTIME_AUTH_FAILED"


@pytest.mark.asyncio
async def test_transcribe_speech_uses_mini_transcribe_model(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"text": "請解釋這篇論文"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, headers, data, files):
            captured["url"] = url
            captured["headers"] = headers
            captured["data"] = data
            captured["files"] = files
            return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(realtime_routes.httpx, "AsyncClient", FakeAsyncClient)
    upload = UploadFile(filename="speech.webm", file=io.BytesIO(b"audio-bytes"))

    response = await transcribe_speech(upload, interface_language="zh-TW", current_user_id=None)

    assert response == {"text": "請解釋這篇論文"}
    assert captured["data"]["model"] == "gpt-4o-mini-transcribe"
    assert captured["data"]["response_format"] == "json"
    assert "Traditional Chinese" in captured["data"]["prompt"]
    assert captured["files"]["file"][0] == "speech.webm"
    assert captured["headers"]["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_transcribe_speech_rejects_empty_upload(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    upload = UploadFile(filename="empty.webm", file=io.BytesIO(b""))

    with pytest.raises(HTTPException) as error:
        await transcribe_speech(upload, interface_language="zh-TW", current_user_id=None)

    assert error.value.status_code == 400
    assert error.value.detail["code"] == "SPEECH_AUDIO_EMPTY"


@pytest.mark.asyncio
async def test_realtime_context_returns_bounded_recent_messages_for_guest():
    payload = RealtimeContextRequest(
        conversation_id="conv_123",
        messages=[
            RealtimeContextMessage(role="user", content="請用白話說明史記。"),
            RealtimeContextMessage(role="assistant", content="可以，我們先看背景。"),
        ],
        interface_language="zh-TW",
    )

    response = await get_realtime_context(payload, current_user_id=None)

    assert response["conversation_id"] == "conv_123"
    assert response["recent_messages"] == [
        {"role": "user", "content": "請用白話說明史記。"},
        {"role": "assistant", "content": "可以，我們先看背景。"},
    ]
    assert response["memory_items"] == []
