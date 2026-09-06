"""Opt-in integration tests for OpenAI Realtime WebSocket behavior.

These tests intentionally call the live OpenAI Realtime API. They are skipped
by default because they depend on credentials, network availability, provider
quota, model access, and paid model calls. Run them only when validating the
production-like WebSocket contract used by AREQA live voice.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import pytest
import websockets

from backend.app.routes.realtime import RealtimeSessionRequest, create_realtime_session


logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_REALTIME_WEBSOCKET_INTEGRATION") != "1",
    reason="set RUN_REALTIME_WEBSOCKET_INTEGRATION=1 to call live OpenAI Realtime WebSocket",
)

REALTIME_WEBSOCKET_URL = "wss://api.openai.com/v1/realtime"
DEFAULT_REALTIME_MODEL = "gpt-realtime-2.1-mini"
INTEGRATION_TIMEOUT_SECONDS = 30


def _load_live_env() -> None:
    """Load root environment files without logging sensitive values.

    Side Effects:
        Reads `.env.local` or `.env` when present so local developers can run
        this test the same way the app loads provider credentials. The function
        never returns or logs secrets.
    """

    root = Path(__file__).resolve().parents[2]
    for name in (".env.local", ".env"):
        candidate = root / name
        if candidate.exists():
            load_dotenv(candidate)
            return


def _live_openai_api_key() -> str:
    """Return a configured OpenAI key or skip the live integration test."""

    _load_live_env()
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        pytest.skip("OPENAI_API_KEY is not configured")
    return api_key


def _safe_provider_error(event: dict[str, Any]) -> str:
    """Return a sanitized provider error label for assertion failures."""

    error = event.get("error")
    if not isinstance(error, dict):
        return "unknown_realtime_error"
    code = str(error.get("code") or "unknown_code")[:80]
    error_type = str(error.get("type") or "unknown_type")[:80]
    parameter = str(error.get("param") or "unknown_param")[:120]
    return f"{error_type}:{code}:param={parameter}"


async def _assert_short_audio_response_contract(socket: websockets.ClientConnection) -> set[str]:
    """Request a minimal response and assert streaming audio plus captions."""

    seen_event_types: set[str] = set()
    saw_audio_delta = False
    saw_text_or_transcript_delta = False
    saw_response_done = False

    await socket.send(json.dumps({
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Say pong."}],
        },
    }))
    await socket.send(json.dumps({
        "type": "response.create",
        "response": {
            "output_modalities": ["audio"],
            "instructions": "Reply with only the word pong.",
        },
    }))

    deadline = asyncio.get_running_loop().time() + INTEGRATION_TIMEOUT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        remaining = max(0.1, deadline - asyncio.get_running_loop().time())
        raw_event = await asyncio.wait_for(socket.recv(), timeout=remaining)
        event = json.loads(raw_event)
        event_type = str(event.get("type") or "")
        seen_event_types.add(event_type)

        if event_type == "error":
            pytest.fail(f"OpenAI Realtime returned {_safe_provider_error(event)}")
        if event_type in {"response.audio.delta", "response.output_audio.delta"}:
            saw_audio_delta = True
        if event_type in {
            "response.audio_transcript.delta",
            "response.output_audio_transcript.delta",
            "response.text.delta",
            "response.output_text.delta",
        }:
            saw_text_or_transcript_delta = True
        if event_type == "response.done":
            saw_response_done = True
            break

    assert saw_response_done, f"response.done was not observed; event_types={sorted(seen_event_types)}"
    assert saw_audio_delta, f"audio delta was not observed; event_types={sorted(seen_event_types)}"
    assert saw_text_or_transcript_delta, (
        "text/transcript delta was not observed; "
        f"event_types={sorted(seen_event_types)}"
    )
    return seen_event_types


@pytest.mark.asyncio
async def test_live_openai_realtime_websocket_streams_audio_and_transcript_events():
    """Validate that the live Realtime WebSocket contract supports AREQA's path.

    The test sends a short text item and asks the provider for both audio and
    text-compatible transcript output. It succeeds only when the live session
    reaches `response.done`, emits at least one output audio delta, and emits
    either transcript or text output events. This catches provider access,
    endpoint, model, event-name, and output-modality drift without requiring a
    real browser microphone.
    """

    api_key = _live_openai_api_key()
    model = os.environ.get("REALTIME_WEBSOCKET_INTEGRATION_MODEL", DEFAULT_REALTIME_MODEL).strip()
    uri = f"{REALTIME_WEBSOCKET_URL}?model={model}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Safety-Identifier": "areqa-realtime-integration-test",
    }

    async with websockets.connect(
        uri,
        additional_headers=headers,
        open_timeout=10,
        ping_interval=20,
        max_size=4 * 1024 * 1024,
    ) as socket:
        await socket.send(json.dumps({
            "type": "session.update",
            "session": {
                "type": "realtime",
                "instructions": (
                    "You are an integration test assistant. Reply with one short word only. "
                    "Do not include private data or long explanations."
                ),
                "audio": {
                    "output": {
                        "voice": "marin",
                        "format": {"type": "audio/pcm", "rate": 24000},
                    },
                },
            },
        }))
        await _assert_short_audio_response_contract(socket)


@pytest.mark.asyncio
async def test_areqa_backend_client_secret_connects_to_live_realtime_websocket():
    """Exercise AREQA's backend delegation and browser WebSocket contract."""

    _live_openai_api_key()
    session = await create_realtime_session(
        RealtimeSessionRequest(
            model=os.environ.get("REALTIME_WEBSOCKET_INTEGRATION_MODEL", DEFAULT_REALTIME_MODEL),
            voice="marin",
            conversation_id="realtime_websocket_integration",
            interface_language="zh-TW",
        ),
        current_user_id="realtime_websocket_integration_user",
    )
    assert session["client_secret"]
    assert session["model"] in {"gpt-realtime-2.1-mini", "gpt-realtime-2.1"}
    assert session["voice"] == "marin"

    uri = f"{REALTIME_WEBSOCKET_URL}?model={session['model']}"
    async with websockets.connect(
        uri,
        subprotocols=[
            "realtime",
            f"openai-insecure-api-key.{session['client_secret']}",
        ],
        open_timeout=10,
        ping_interval=20,
        max_size=4 * 1024 * 1024,
    ) as socket:
        await _assert_short_audio_response_contract(socket)
