"""Regression coverage for long-conversation context ownership and fallbacks."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.conversation.history import _CACHE, prepare_history, token_bound


def client(text='Goals: preserve the original constraint.'):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(
        return_value=SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=text), finish_reason='stop')])
    ))))


def history(count=100):
    return [{'role': 'system', 'content': 'System policy'}] + [
        {'role': role, 'content': f'{i}: ' + ('history data ' * 80)}
        for i in range(count) for role in ('user', 'assistant')
    ] + [{'role': 'user', 'content': 'What was the original constraint?'}]


async def run(messages, model_client=None, **kwargs):
    return await prepare_history(
        messages=messages, tools=[], client=model_client or client(),
        user_id='alice', conversation_id='chat', model='test',
        output_tokens=500, context_tokens=8000, summary_tokens=256,
        **kwargs,
    )


@pytest.fixture(autouse=True)
def clear_cache():
    _CACHE.clear()


@pytest.mark.asyncio
async def test_short_history_over_100_messages_is_not_a_model_limit():
    messages = [{'role': 'user', 'content': 'hi'}] * 101
    c = client()
    result = await run(messages, c)
    assert result.messages == messages
    c.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_summary_budget_and_unchanged_transcript():
    messages = history()
    before = [dict(m) for m in messages]
    result = await run(messages)
    assert messages == before
    assert result.messages[0] == messages[0]
    assert result.messages[-1] == messages[-1]
    assert token_bound(result.messages) + token_bound([]) + 500 + 1024 <= 8000
    assert any('Historical conversation summary' in m['content'] for m in result.messages)
    assert not result.notice


@pytest.mark.asyncio
async def test_cache_reuse_edits_and_user_isolation():
    c = client()
    messages = history(10)
    await run(messages, c)
    calls = c.chat.completions.create.await_count
    await run(messages, c)
    assert c.chat.completions.create.await_count == calls
    messages[1]['content'] = 'edited ' + messages[1]['content']
    await run(messages, c)
    assert c.chat.completions.create.await_count > calls
    calls = c.chat.completions.create.await_count
    await prepare_history(messages=messages, tools=[], client=c, user_id='bob',
                          conversation_id='chat', model='test', output_tokens=500,
                          context_tokens=8000, summary_tokens=256)
    assert c.chat.completions.create.await_count > calls


@pytest.mark.asyncio
async def test_failure_falls_back_and_logs_no_content(caplog):
    c = client()
    c.chat.completions.create.side_effect = RuntimeError('PRIVATE PROVIDER DATA')
    result = await run(history(), c)
    assert result.notice
    assert result.messages[-1]['content'] == 'What was the original constraint?'
    assert 'history.summary_failed' in caplog.text
    assert 'PRIVATE PROVIDER DATA' not in caplog.text


@pytest.mark.asyncio
async def test_timeout_and_truncated_summary_are_not_cached():
    c = client()
    async def slow(**kwargs):
        await asyncio.sleep(10)
    c.chat.completions.create.side_effect = slow
    assert (await run(history(), c, timeout_seconds=0.01)).notice
    assert not _CACHE
    c = client()
    c.chat.completions.create.return_value.choices[0].finish_reason = 'length'
    assert (await run(history(), c)).notice
    assert not _CACHE


@pytest.mark.asyncio
async def test_current_input_is_never_silently_truncated():
    with pytest.raises(ValueError, match='current_turn_too_large'):
        await run([{'role': 'user', 'content': '中' * 10_000}])


@pytest.mark.asyncio
async def test_disabled_feature_rejects_instead_of_unbounded_call():
    with pytest.raises(ValueError, match='compaction_disabled'):
        await run(history(), enabled=False)


@pytest.mark.asyncio
async def test_recall_returns_early_original_including_chinese():
    messages = history(20)
    messages[1]['content'] = '原先約定：所有程式範例都必須使用 Python。'
    messages[-1]['content'] = '原先約定的程式範例語言是什麼？'
    result = await run(messages)
    assert any('Historical source message' in m['content'] and 'Python' in m['content'] for m in result.messages)


@pytest.mark.asyncio
async def test_incremental_summary_reuses_covered_prefix():
    c = client()
    messages = history(12)
    await run(messages, c)
    c.chat.completions.create.reset_mock()
    messages.extend([{'role': 'assistant', 'content': 'answered ' * 120},
                     {'role': 'user', 'content': 'new question ' * 100}])
    await run(messages, c)
    # Updated summaries carry the previous summary and only newly aged messages.
    calls = c.chat.completions.create.call_args_list
    assert calls
    import json
    payload = json.loads(calls[0].kwargs['messages'][1]['content'])
    assert payload['previous_summary']
    assert payload['messages'][0]['turn'] > 1


@pytest.mark.asyncio
async def test_keeps_tool_calls_and_results_in_the_same_recent_turn():
    messages = history(10)
    messages.extend([
        {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'call1', 'type': 'function', 'function': {'name': 'lookup', 'arguments': '{}'}}]},
        {'role': 'tool', 'tool_call_id': 'call1', 'content': 'result'},
        {'role': 'assistant', 'content': 'done'},
    ])
    result = await run(messages)
    assert result.messages[-4:] == messages[-4:]


@pytest.mark.asyncio
async def test_summary_debug_logs_use_safe_metadata(caplog):
    import logging
    caplog.set_level(logging.INFO, logger='services.conversation.history')
    c = client('PRIVATE SUMMARY TEXT')
    c.chat.completions.create.return_value.usage = SimpleNamespace(prompt_tokens=123, completion_tokens=20)
    await run(history(10), c)
    assert 'history.summary_started model=test' in caplog.text
    assert 'history.summary_completed model=test elapsed_ms=' in caplog.text
    assert 'input_tokens=123 output_tokens=20 finish_reason=stop' in caplog.text
    assert 'PRIVATE SUMMARY TEXT' not in caplog.text
    caplog.clear()
    await run(history(10), c)
    assert 'cache_hit=True' in caplog.text
    assert 'history.summary_started' not in caplog.text
