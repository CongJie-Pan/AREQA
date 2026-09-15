"""Regression tests for AREQA Live Tutor Realtime backend routes."""

from __future__ import annotations

import io
import json
import logging

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

import backend.app.routes.realtime as realtime_routes
from backend.app.routes.realtime import (
    RealtimeContextMessage,
    RealtimeContextRequest,
    RealtimeSessionRequest,
    LiveKitAvatarSessionRequest,
    _build_realtime_session_config,
    _build_speech_transcription_prompt,
    _client_secret_from_response,
    _livekit_avatar_agent_metadata,
    _livekit_avatar_room_name,
    _livekit_participant_identity,
    _normalize_model,
    _safe_realtime_user_identifier,
    create_livekit_avatar_session,
    create_realtime_session,
    get_realtime_context,
    read_speech,
    SpeechReadRequest,
    transcribe_speech,
)


def test_realtime_session_config_uses_allowed_mvp_model_as_live_agent():
    payload = RealtimeSessionRequest(
        model="gpt-realtime-2.1-mini",
        voice="marin",
        conversation_id="conv_123",
        interface_language="zh-TW",
    )

    config = _build_realtime_session_config(payload)

    assert config["type"] == "realtime"
    assert config["model"] == "gpt-realtime-2.1-mini"
    assert config["output_modalities"] == ["audio"]
    assert config["audio"]["output"]["voice"] == "marin"
    assert config["audio"]["output"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert "AREQA Live Tutor" in config["instructions"]
    assert "ah-ray-kah" in config["instructions"]
    assert "阿瑞卡" in config["instructions"]
    assert "write the speakable form" in config["instructions"]
    assert "internal: never explain, spell out, or describe the pronunciation guide" in config["instructions"]
    assert "Choose spoken depth from the learner's intent: BRIEF, EXPLAIN, or DEEP" in config["instructions"]
    assert "BRIEF is for greetings" in config["instructions"]
    assert "DEEP is for detailed paper walkthroughs" in config["instructions"]
    assert "do not apply the one-to-three-sentence limit" in config["instructions"]
    assert "Do not ask a follow-up question until the learner's current request has been substantively answered" in config["instructions"]
    assert "latest turn contains any Chinese characters" in config["instructions"]
    assert "answer in Mandarin Chinese unless they explicitly ask for another language" in config["instructions"]
    assert "asks whether you remember something" in config["instructions"]
    assert "call get_areqa_context before answering" in config["instructions"]
    assert "Never say you cannot remember" in config["instructions"]
    assert "AREQA soul" in config["instructions"]
    assert "Traditional Chinese" in config["audio"]["input"]["transcription"]["prompt"]
    assert config["audio"]["input"]["turn_detection"] == {
        "type": "server_vad",
        "create_response": True,
        "interrupt_response": True,
    }
    assert config["tools"][0]["name"] == "get_areqa_context"
    assert config["tool_choice"] == "auto"


def test_realtime_session_config_preserves_simplified_chinese_preference():
    payload = RealtimeSessionRequest(interface_language="zh-CN")

    config = _build_realtime_session_config(payload)

    assert "Simplified Chinese" in config["instructions"]
    assert "Simplified Chinese" in config["audio"]["input"]["transcription"]["prompt"]


def test_livekit_avatar_metadata_includes_bounded_recent_context():
    metadata = json.loads(_livekit_avatar_agent_metadata(
        LiveKitAvatarSessionRequest(
            conversation_id="conv_livekit",
            interface_language="en",
            messages=[
                RealtimeContextMessage(role="user", content="ignored old message"),
                *[
                    RealtimeContextMessage(role="assistant" if index % 2 else "user", content=f"message {index}")
                    for index in range(9)
                ],
                RealtimeContextMessage(role="user", content="x" * 2000),
            ],
        ),
        memory_items=["preferred short explanations", "y" * 800],
    ))

    assert metadata["conversation_id"] == "conv_livekit"
    assert metadata["session_id"]
    assert metadata["interface_language"] == "en"
    assert metadata["provider"] == "livekit_anam"
    assert len(metadata["recent_messages"]) == 8
    assert metadata["recent_messages"][0]["content"] == "message 2"
    assert metadata["recent_messages"][-1] == {"role": "user", "content": "x" * 1000}
    assert metadata["memory_items"] == ["preferred short explanations", "y" * 500]
    assert metadata["parts_context"]["persona"]


def test_livekit_avatar_room_isolated_by_session_without_exposing_conversation():
    first_room = _livekit_avatar_room_name("conv_livekit", "session_one")
    second_room = _livekit_avatar_room_name("conv_livekit", "session_two")
    repeated_room = _livekit_avatar_room_name("conv_livekit", "session_one")

    assert first_room == repeated_room
    assert first_room != second_room
    assert first_room.startswith("areqa-live-")
    assert "conv_livekit" not in first_room
    assert "session_one" in first_room

    first_identity = _livekit_participant_identity("user_123", "conv_livekit")
    second_identity = _livekit_participant_identity("user_123", "conv_livekit")
    other_identity = _livekit_participant_identity("user_123", "conv_other")

    assert first_identity == second_identity
    assert first_identity != other_identity
    assert first_identity.startswith("learner-")
    assert "user_123" not in first_identity
    assert "conv_livekit" not in first_identity


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
async def test_create_livekit_avatar_session_fails_when_livekit_config_missing(monkeypatch):
    monkeypatch.setattr(realtime_routes.settings, "enable_livekit_avatar_mode", True)
    monkeypatch.setattr(realtime_routes.settings, "livekit_url", "")
    monkeypatch.setattr(realtime_routes.settings, "livekit_api_key", "")
    monkeypatch.setattr(realtime_routes.settings, "livekit_api_secret", "")

    with pytest.raises(HTTPException) as error:
        await create_livekit_avatar_session(
            LiveKitAvatarSessionRequest(conversation_id="conv_livekit"),
            current_user_id="user_123",
        )

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "LIVEKIT_CONFIG_MISSING"


@pytest.mark.asyncio
async def test_create_livekit_avatar_session_mints_dispatch_token_without_logging_secrets(monkeypatch, caplog):
    monkeypatch.setattr(realtime_routes.settings, "enable_livekit_avatar_mode", True)
    monkeypatch.setattr(realtime_routes.settings, "enable_live_tutor_debug_logs", True)
    monkeypatch.setattr(realtime_routes.settings, "livekit_url", "wss://example.livekit.cloud")
    monkeypatch.setattr(realtime_routes.settings, "livekit_api_key", "lk_test_key")
    monkeypatch.setattr(realtime_routes.settings, "livekit_api_secret", "lk_test_secret")
    monkeypatch.setattr(realtime_routes.settings, "livekit_agent_name", "areqa-live-tutor")
    monkeypatch.setattr(realtime_routes.settings, "livekit_avatar_token_ttl_seconds", 120)

    async def fake_memory_items(current_user_id: str | None, conversation_id: str) -> list[str]:
        return ["learner prefers Mandarin explanations"] if current_user_id else []

    monkeypatch.setattr(realtime_routes, "_livekit_avatar_memory_items", fake_memory_items)

    with caplog.at_level(logging.INFO):
        response = await create_livekit_avatar_session(
            LiveKitAvatarSessionRequest(conversation_id="conv_livekit", interface_language="zh-TW"),
            current_user_id="user_123",
        )

    assert response.livekit_url == "wss://example.livekit.cloud"
    assert response.agent_name == "areqa-live-tutor"
    assert response.expires_in == 120
    assert response.room_name.startswith("areqa-live-")
    assert response.session_id
    assert response.session_id in response.room_name
    assert response.participant_identity.startswith("learner-")
    assert "user_123" not in response.participant_identity
    assert response.token
    assert "livekit.avatar_session_created" in caplog.text
    assert "livekit.debug.avatar_session_token_created" in caplog.text
    assert "memory_count=1" in caplog.text
    assert "lk_test_secret" not in caplog.text
    assert response.token not in caplog.text


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
async def test_realtime_debug_logs_emit_safe_session_metadata(monkeypatch, caplog):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"value": "ek_test_secret", "expires_at": 1788510000}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, _url, *, headers, json):
            return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(realtime_routes.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(realtime_routes.settings, "enable_realtime_debug_logs", True)

    with caplog.at_level(logging.INFO):
        response = await create_realtime_session(
            RealtimeSessionRequest(conversation_id="conv_debug", interface_language="zh-TW"),
            current_user_id="user_123",
        )

    assert response["client_secret"] == "ek_test_secret"
    assert "realtime.debug.session_config_built" in caplog.text
    assert "realtime.debug.upstream_request_prepared" in caplog.text
    assert "realtime.debug.upstream_response_received" in caplog.text
    assert "realtime.debug.client_secret_issued" in caplog.text
    assert "model=gpt-realtime-2.1-mini" in caplog.text
    assert "tool_names=get_areqa_context" in caplog.text
    assert "test-key" not in caplog.text
    assert "ek_test_secret" not in caplog.text


@pytest.mark.asyncio
async def test_realtime_debug_logs_respect_config_switch(monkeypatch, caplog):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"value": "ek_test_secret"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, _url, *, headers, json):
            return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(realtime_routes.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(realtime_routes.settings, "enable_realtime_debug_logs", False)

    with caplog.at_level(logging.INFO):
        await create_realtime_session(RealtimeSessionRequest(conversation_id="conv_debug"), current_user_id=None)

    assert "realtime.debug." not in caplog.text


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
async def test_read_speech_uses_mini_tts_model_without_logging_text(monkeypatch, caplog):
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        content = b"mp3-bytes"
        headers = {"content-type": "audio/mpeg"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(realtime_routes.httpx, "AsyncClient", FakeAsyncClient)

    with caplog.at_level(logging.INFO):
        response = await read_speech(
            SpeechReadRequest(text="請朗讀這段私人回覆"),
            current_user_id="user_123",
        )

    assert response.status_code == 200
    assert response.body == b"mp3-bytes"
    assert captured["url"] == "https://api.openai.com/v1/audio/speech"
    assert captured["json"] == {
        "model": "gpt-4o-mini-tts",
        "voice": "cedar",
        "input": "請朗讀這段私人回覆",
        "response_format": "mp3",
        "instructions": "Read clearly in a warm, natural tutoring tone.",
    }
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["headers"]["OpenAI-Safety-Identifier"] != "user_123"
    assert "speech.read_started" in caplog.text
    assert "speech.read_completed" in caplog.text
    assert "請朗讀這段私人回覆" not in caplog.text
    assert "test-key" not in caplog.text


@pytest.mark.asyncio
async def test_read_speech_fails_when_openai_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(HTTPException) as error:
        await read_speech(SpeechReadRequest(text="hello"), current_user_id=None)

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "OPENAI_API_KEY_MISSING"


def test_speech_transcription_prompt_defaults_english_ui_chinese_to_traditional():
    prompt = _build_speech_transcription_prompt("en")

    assert "language spoken" in prompt
    assert "Taiwan Traditional Chinese" in prompt
    assert "Simplified Chinese" not in prompt


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
    assert response["parts_context"]["persona"]
    assert response["parts_context"]["instruction"]
    assert "parts_context" in response["guidance"]
    assert "answer the requested content before asking a follow-up" in response["guidance"]
    assert "do not omit key ideas merely to be brief" in response["guidance"]
    assert "use memory_items and recent_messages before saying you do not know" in response["guidance"]


@pytest.mark.asyncio
async def test_live_tutor_debug_logs_emit_context_counts_without_raw_text(monkeypatch, caplog):
    monkeypatch.setattr(realtime_routes.settings, "enable_live_tutor_debug_logs", True)
    payload = RealtimeContextRequest(
        conversation_id="conv_live_debug",
        messages=[
            RealtimeContextMessage(role="user", content="private learner question"),
            RealtimeContextMessage(role="assistant", content="private assistant answer"),
        ],
        interface_language="en",
    )

    with caplog.at_level(logging.INFO):
        response = await get_realtime_context(payload, current_user_id=None)

    assert response["recent_messages"]
    assert "live_tutor.debug.context_request_received" in caplog.text
    assert "live_tutor.debug.context_response_built" in caplog.text
    assert "supplied_message_count=2" in caplog.text
    assert "recent_message_count=2" in caplog.text
    assert "private learner question" not in caplog.text
    assert "private assistant answer" not in caplog.text


@pytest.mark.asyncio
async def test_live_tutor_debug_logs_respect_config_switch(monkeypatch, caplog):
    monkeypatch.setattr(realtime_routes.settings, "enable_live_tutor_debug_logs", False)
    payload = RealtimeContextRequest(
        conversation_id="conv_live_debug",
        messages=[RealtimeContextMessage(role="user", content="private learner question")],
        interface_language="en",
    )

    with caplog.at_level(logging.INFO):
        await get_realtime_context(payload, current_user_id=None)

    assert "live_tutor.debug." not in caplog.text
    assert "private learner question" not in caplog.text
