"""Regression tests for AREQA Live Tutor Realtime backend routes."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.app.routes.realtime import (
    RealtimeContextMessage,
    RealtimeContextRequest,
    RealtimeSessionRequest,
    _build_realtime_session_config,
    _client_secret_from_response,
    _normalize_model,
    create_realtime_session,
    get_realtime_context,
)


def test_realtime_session_config_uses_allowed_mvp_model_and_context_tool():
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
    assert config["tools"][0]["name"] == "get_areqa_context"


def test_realtime_session_rejects_unsupported_models():
    with pytest.raises(HTTPException) as error:
        _normalize_model("gpt-4o")

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "REALTIME_MODEL_UNSUPPORTED"


def test_client_secret_extraction_accepts_current_response_shape():
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


@pytest.mark.asyncio
async def test_create_realtime_session_fails_when_openai_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(HTTPException) as error:
        await create_realtime_session(RealtimeSessionRequest(), current_user_id="user_123")

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "OPENAI_API_KEY_MISSING"


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
