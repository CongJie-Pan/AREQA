"""Golden SSE sequences for ConversationStreamService.stream.

These pin the exact frames for the stream's distinct paths so refactors of the
provider step loop stay behavior-preserving. Regenerate deliberately with:

    STREAM_GOLDEN_UPDATE=1 python -m pytest tests/backend/test_stream_golden.py
"""
import asyncio
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.conversation import image_generation as image_tool
from services.conversation.stream import ConversationStreamService
from services.generated_image_service import GeneratedImage
from tools import ToolRegistry

GOLDEN = Path(__file__).parent / "fixtures" / "stream_golden.json"
_IDS = re.compile(r"[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class ContextError(Exception):
    status_code = 400
    body = {"error": {"code": "context_length_exceeded"}}


def _chunk(content=None, tool_calls=None, finish=None):
    return SimpleNamespace(id="gen-1", usage=None, choices=[SimpleNamespace(
        delta=SimpleNamespace(content=content, tool_calls=tool_calls), finish_reason=finish)])


def _tool(arguments, call_id="call_1"):
    return [SimpleNamespace(index=0, id=call_id, function=SimpleNamespace(name="generate_image", arguments=arguments))]


def _stream(*chunks):
    async def response():
        for chunk in chunks:
            yield chunk
    return response()


MESSAGES = [
    {"role": "system", "content": "policy"},
    {"role": "user", "content": "earlier question"},
    {"role": "assistant", "content": "earlier answer"},
    {"role": "user", "content": "請解釋效果量"},
]

SCENARIOS = {
    "completed": lambda: [_stream(_chunk("效果量"), _chunk("是差異大小。"), _chunk("", finish="stop"))],
    "output_limit": lambda: [_stream(_chunk("說到一半"), _chunk("", finish="length"))],
    "context_overflow_retry": lambda: [ContextError(), _stream(_chunk("重試後的回答"), _chunk("", finish="stop"))],
    "context_overflow_exhausted": lambda: [ContextError(), ContextError()],
    "image_tool": lambda: [_stream(_chunk(None, _tool(json.dumps({
        "prompt": "效果量示意圖", "presentation": "text_and_image", "explanation": "圖解說明", "reference": "none"}))),
        _chunk("", finish="tool_calls"))],
    "image_tool_invalid_arguments": lambda: [_stream(_chunk("先說明"), _chunk(None, _tool('{"prompt": ')),
                                                     _chunk("", finish="tool_calls"))],
}


def _normalize(frame: str) -> str:
    return _IDS.sub("<id>", frame)


async def _events(name, monkeypatch):
    import services.conversation.stream as module
    from services.conversation.history import HistoryContext

    async def passthrough(**kwargs):
        return HistoryContext(kwargs["messages"], "")

    monkeypatch.setattr(module, "prepare_history", passthrough)
    monkeypatch.setattr(image_tool, "consume_image_quota", AsyncMock(return_value=True))
    monkeypatch.setattr(image_tool, "generate_teaching_image", AsyncMock(
        return_value=GeneratedImage("https://example.com/private.png", "flare", "教學圖", None, False)))
    monkeypatch.setattr(image_tool, "prepare_image_reference", AsyncMock(return_value="facts"))
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=SCENARIOS[name]())
    service = ConversationStreamService(client, ToolRegistry())
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    frames = [frame async for frame in service.stream(
        user_id="u1", conversation_id="conv1", last_user_msg="請解釋效果量", messages=[dict(m) for m in MESSAGES],
        force_think=False, max_tokens=100, temperature=0.7, top_p=0.9, repetition_penalty=1, request=request)]
    return [_normalize(frame) for frame in frames], client.chat.completions.create.await_count


@pytest.mark.asyncio
async def test_stream_frames_match_golden(monkeypatch):
    actual = {}
    for name in SCENARIOS:
        frames, calls = await _events(name, monkeypatch)
        actual[name] = {"provider_calls": calls, "frames": frames}
    if os.environ.get("STREAM_GOLDEN_UPDATE") == "1":
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(actual, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for name in SCENARIOS:
        assert actual[name] == expected[name], name


@pytest.mark.asyncio
async def test_closing_stream_mid_answer_closes_provider_response(monkeypatch):
    import services.conversation.stream as module
    from services.conversation.history import HistoryContext

    async def passthrough(**kwargs):
        return HistoryContext(kwargs["messages"], "")

    monkeypatch.setattr(module, "prepare_history", passthrough)
    closed = AsyncMock()

    class Response:
        """Streams paragraphs until a bounded count, then never finishes."""

        def __init__(self):
            self.aclose = closed
            self.sent = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            self.sent += 1
            if self.sent > 200:
                await asyncio.Event().wait()
            return _chunk(f"第 {self.sent} 段回答。\n\n")

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=Response())
    stream = ConversationStreamService(client, ToolRegistry()).stream(
        user_id="u1", conversation_id="conv1", last_user_msg="q", messages=[dict(m) for m in MESSAGES],
        force_think=False, max_tokens=100, temperature=0.7, top_p=0.9, repetition_penalty=1,
        request=SimpleNamespace(is_disconnected=AsyncMock(return_value=False)))
    # The client stops reading after the first answer frame, mid-stream.
    frame = await asyncio.wait_for(stream.__anext__(), timeout=5)
    assert frame.startswith("data: ")
    await stream.aclose()
    closed.assert_awaited_once()


def test_step_outcome_prefers_tool_calls_then_output_limit():
    from services.conversation.stream import StepOutcome, _StepState

    assert _StepState().outcome is StepOutcome.COMPLETED
    assert _StepState(finish_reason="length").outcome is StepOutcome.OUTPUT_LIMIT
    assert _StepState(finish_reason="length", tool_calls={0: {"name": "x"}}).outcome is StepOutcome.TOOL_CALLS
