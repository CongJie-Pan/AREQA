"""Model tool routing: the main model calls web_search, then answers in a bounded second step."""
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core import SearchMode
from policies import SearchReason
from services.conversation.stream import ConversationStreamService
from services.conversation.web_search_call import (
    MAX_TOOL_CONTEXT_CHARS, SEARCH_FAILED_NOTE, WEB_SEARCH_TOOL_SCHEMA, search_tool_content,
)
from tools import ToolDefinition, ToolRegistry, ToolResult

MESSAGES = [{"role": "system", "content": "policy"}, {"role": "user", "content": "2026 年的諾貝爾物理獎是誰？"}]
RESULTS = {"results": [{"title": "Nobel 2026", "url": "https://example.com/nobel", "snippet": "得主是某人"}]}


def _chunk(content=None, tool_calls=None, finish=None):
    return SimpleNamespace(id="gen-1", usage=None, choices=[SimpleNamespace(
        delta=SimpleNamespace(content=content, tool_calls=tool_calls), finish_reason=finish)])


def _search_call(arguments='{"query": "2026 諾貝爾物理獎 得主"}'):
    return [SimpleNamespace(index=0, id="search_1", function=SimpleNamespace(name="web_search", arguments=arguments))]


def _stream(*chunks):
    async def response():
        for chunk in chunks:
            yield chunk
    return response()


@pytest.fixture
def env(monkeypatch):
    import services.conversation.stream as module
    from services.conversation.history import HistoryContext

    async def passthrough(**kwargs):
        return HistoryContext(kwargs["messages"], "")

    monkeypatch.setattr(module, "prepare_history", passthrough)
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "server-only-key")


def _registry(handler):
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="web_search", external=True, handler=handler))
    return registry


async def _run(registry, responses, model_search=True):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=responses)
    service = ConversationStreamService(client, registry)
    frames = [frame async for frame in service.stream(
        user_id="u1", conversation_id="conv1", last_user_msg="q", messages=[dict(m) for m in MESSAGES],
        force_think=False, max_tokens=100, temperature=0.7, top_p=0.9, repetition_penalty=1,
        request=SimpleNamespace(is_disconnected=AsyncMock(return_value=False)), model_search=model_search)]
    final = json.loads(frames[-1].split("data: ", 1)[1])
    return frames, final, client.chat.completions.create


@pytest.mark.asyncio
async def test_model_search_runs_tool_then_answers_without_tools(env, caplog):
    caplog.set_level(logging.INFO)
    handler = AsyncMock(return_value=ToolResult("web_search", "ok", RESULTS, latency_ms=12))
    frames, final, create = await _run(_registry(handler), [
        _stream(_chunk(None, _search_call()), _chunk("", finish="tool_calls")),
        _stream(_chunk("得主是某人【文獻1】。"), _chunk("", finish="stop")),
    ])

    assert create.await_count == 2
    first, second = create.await_args_list
    assert WEB_SEARCH_TOOL_SCHEMA in first.kwargs["tools"]
    assert "tools" not in second.kwargs and "tool_choice" not in second.kwargs
    tool_message = second.kwargs["messages"][-1]
    assert tool_message["role"] == "tool" and tool_message["tool_call_id"] == "search_1"
    assert "[文獻1] Nobel 2026" in tool_message["content"]
    assert second.kwargs["messages"][-2]["tool_calls"][0]["function"]["name"] == "web_search"
    assert handler.await_args.args[0]["query"] == "2026 諾貝爾物理獎 得主"

    joined = "".join(frames)
    assert "event: tool_started" in joined and "event: sources" in joined
    assert joined.index("event: sources") < joined.index("得主是某人")
    assert final["accumulator"] == "得主是某人【文獻1】。"
    assert "called=True" in caplog.text
    assert "server-only-key" not in caplog.text and "諾貝爾" not in caplog.text


@pytest.mark.asyncio
async def test_model_answering_directly_makes_one_call(env, caplog):
    caplog.set_level(logging.INFO)
    handler = AsyncMock()
    frames, final, create = await _run(_registry(handler), [
        _stream(_chunk("你好！"), _chunk("", finish="stop")),
    ])
    assert create.await_count == 1
    handler.assert_not_awaited()
    assert final["accumulator"] == "你好！"
    assert "called=False" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ['{"query": ', '{"query": ""}', json.dumps({"query": "x" * 501})])
async def test_invalid_search_arguments_answer_with_failure_note(env, arguments):
    handler = AsyncMock()
    frames, final, create = await _run(_registry(handler), [
        _stream(_chunk(None, _search_call(arguments)), _chunk("", finish="tool_calls")),
        _stream(_chunk("我沒能查證，但一般而言……"), _chunk("", finish="stop")),
    ])
    handler.assert_not_awaited()
    assert create.await_args_list[1].kwargs["messages"][-1]["content"] == SEARCH_FAILED_NOTE
    assert "event: tool_started" not in "".join(frames)
    assert final["accumulator"] == "我沒能查證，但一般而言……"


@pytest.mark.asyncio
async def test_search_failure_is_fail_soft(env):
    handler = AsyncMock(side_effect=RuntimeError("provider down"))
    frames, final, create = await _run(_registry(handler), [
        _stream(_chunk(None, _search_call()), _chunk("", finish="tool_calls")),
        _stream(_chunk("目前無法查證。"), _chunk("", finish="stop")),
    ])
    assert create.await_args_list[1].kwargs["messages"][-1]["content"] == SEARCH_FAILED_NOTE
    assert "聯網搜尋服務暫時無法使用" in "".join(frames)
    assert final["accumulator"] == "目前無法查證。"


@pytest.mark.asyncio
async def test_tool_is_not_offered_without_model_search(env):
    _, _, create = await _run(ToolRegistry(), [_stream(_chunk("答"), _chunk("", finish="stop"))], model_search=False)
    assert WEB_SEARCH_TOOL_SCHEMA not in (create.await_args.kwargs.get("tools") or [])


def test_search_tool_content_is_bounded():
    content = search_tool_content(["[文獻1] a\n" + "x" * 20_000, "[文獻2] b\n" + "y" * 20_000])
    assert "[文獻1]" in content and "[文獻2]" not in content
    assert len(content) < MAX_TOOL_CONTEXT_CHARS + 500
    assert search_tool_content([]) == SEARCH_FAILED_NOTE


@pytest.mark.asyncio
async def test_plan_search_skips_routing_call_under_model_tool_routing():
    from services.orchestration.routing import plan_search

    service = SimpleNamespace(
        tutor_agent=SimpleNamespace(decide_search=AsyncMock()),
        turn_plan_service=SimpleNamespace(plan=lambda **_: SimpleNamespace(
            route=SimpleNamespace(value="GENERAL_CHAT"), reason_code="X", max_foreground_model_calls=1)),
    )
    trace = SimpleNamespace(mark=lambda *_: None, increment_model_call=lambda *_: None)
    run_context = SimpleNamespace(run_id="r", conversation_id="c", request_id="q")
    decision, _, _ = await plan_search(
        service, last_user_msg="2026 年的諾貝爾物理獎是誰？", run_context=run_context, trace=trace,
        effective_search_mode=SearchMode.AUTO, has_attachments=False, auto_routing_enabled=True,
        use_rag=False, attachments=[], model_tool_routing=True)
    assert decision.reason is SearchReason.MODEL_TOOL_ROUTING and not decision.should_search
    service.tutor_agent.decide_search.assert_not_awaited()
